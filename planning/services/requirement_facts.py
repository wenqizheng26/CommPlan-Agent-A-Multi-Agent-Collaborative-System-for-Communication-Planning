"""Sites, devices and card assumptions as parameter sources (AGENT_LED §4, H3).

The model names the sites and the radio in the request; the program looks each name up in
the reviewed fact store and reads coordinates, antenna heights and radio figures from the
records. An input that the text does not state and no record supplies takes the assumption
its card declares, and the user confirms it with the plan. Every value keeps its source: a
record id and field, or a card and parameter. A value typed in the form overrides the store.
"""
import json
from pathlib import Path
import re
from planning.knowledge.facts import FactService
from planning.services.fact_fields import POSITION, field_label, field_unit
from planning.services.plans import chain, with_line_of_sight, GEOMETRY, TEACHER, ALIASES, LINK_TOOL

ROOT = Path(__file__).resolve().parents[2]
# The same radio at both ends: power and gain at the transmitter, gain and sensitivity at the receiver.
DEVICE = (('tx_power_dbm', 'tx_power_dbm'), ('antenna_gain_dbi', 'tx_gain_dbi'),
          ('antenna_gain_dbi', 'rx_gain_dbi'), ('rx_sensitivity_dbm', 'rx_threshold_dbm'))
KIND = {'site': '站点', 'device': '设备'}
MODULATION = re.compile(r'(?<![A-Za-z0-9])(?:[BQ]PSK|\d+\s*-?\s*(?:QAM|A?PSK)|QAM\s*-?\s*\d+)(?![A-Za-z0-9])', re.I)
MODULATION_NEGATION = re.compile(r'不要|不用|(?<!分)别用|不采用|排除|除了|非(?!常)')
MODULATION_BOUNDARY = re.compile(r'[，,。；;！？!?：:\n]')
# The teacher's link tool takes these as zero; a stated value means the general link budget instead.
ZERO = ('tx_loss_db', 'rx_loss_db', 'extra_loss_db', 'reserve_db')


def diagnostic(code, message, **details):
    return {'code': code, 'message': message, 'details': details}


def shown(value):
    return f'{value:g}'


def resolve(entities, root=None, store=None):
    """The named sites in text order and the named device, plus an issue for each name that does not resolve."""
    store = store or FactService(root or ROOT)
    found = {'site': [], 'device': []}
    issues = []
    for e in entities:
        records = [c['record'] for c in (store.find_site if e['kind'] == 'site' else store.find_device)(e['mention'])['candidates']]
        if not records:
            issues.append(diagnostic('ENTITY_UNKNOWN', f"{KIND[e['kind']]}库中没有“{e['mention']}”。",
                                     kind=e['kind'], mention=e['mention'], span=e['span']))
        elif len(records) > 1:
            issues.append(diagnostic('ENTITY_AMBIGUOUS', f"“{e['mention']}”对应{len(records)}个{KIND[e['kind']]}，请选定一个。",
                                     kind=e['kind'], mention=e['mention'], span=e['span'], choices=[r['names'][0] for r in records]))
        elif all(r['id'] != records[0]['id'] for r in found[e['kind']]):
            found[e['kind']].append(records[0])  # "A站" and "A岸站" name one site
    sites, devices = found['site'], found['device']
    # With one site the distance is simply asked for; more than two cannot be one link.
    if len(sites) > 2:
        issues.append(diagnostic('SITE_COUNT', '一次只计算两站之间的一条链路。', sites=[s['names'][0] for s in sites]))
    if len(devices) > 1:
        issues.append(diagnostic('DEVICE_COUNT', '两端按同一型号的电台计算，请只指定一种。', devices=[d['model'] for d in devices]))
    return sites, devices, issues


def fact_observations(request, sites, devices):
    """Values from the fact store, by parameter. A site without an antenna height leaves that input missing."""
    observations = {}
    def add(field, kind, ref, value):
        if field not in request['manual_parameters']:  # a value typed in the form overrides the store
            observations.setdefault(field, []).append(dict(kind=kind, source_ref=ref, span=None, value=value,
                                                           unit=field_unit(field)))
    if len(sites) == 2:
        for end, site in enumerate(sites, 1):
            for key, pattern, _, _ in POSITION:
                if site['position'].get(key) is not None:
                    add(pattern.format(end), 'site', f"{site['id']}#position.{key}", site['position'][key])
    if len(devices) == 1:
        for key, field in DEVICE:
            add(field, 'device', f"{devices[0]['id']}#{key}", devices[0][key])
    return observations


def modulations(text, store):
    """Affirmative table records, unknown names and explicitly excluded mentions, in text order."""
    found, unknown, excluded = [], [], []
    for m in MODULATION.finditer(text):
        records = [c['record'] for c in store.find_modulation(m.group())['candidates']]
        prefix = MODULATION_BOUNDARY.split(text[max(0, m.start() - 6):m.start()])[-1]
        if MODULATION_NEGATION.search(prefix) or re.match(r'[ \t]*除外', text[m.end():]):
            excluded.append(dict(mention=m.group(), span=list(m.span()), modulations=[r['names'][0] for r in records]))
            continue
        if len(records) == 1:
            if all(r['id'] != records[0]['id'] for r in found):
                found.append(records[0])
        elif all(u['mention'] != m.group() for u in unknown):
            unknown.append(dict(mention=m.group(), span=list(m.span())))
    return found, unknown, excluded


def link_tool(root):
    """The registered link tool's declared assumptions (knowledge/tools.json)."""
    tools = json.loads((Path(root or ROOT) / 'knowledge' / 'tools.json').read_text(encoding='utf-8-sig'))
    return next(t for t in tools if t['id'] == LINK_TOOL)


def default_observations(order, cards, observed, teacher=False):
    """Card assumptions for plan inputs nothing else supplies; the link tool's zero losses on its path."""
    by_id = {c['id']: c for c in cards}
    observations = {}
    for card_id in order:
        for name, spec in by_id[card_id]['parameters'].items():
            if teacher and name in ZERO and name not in observed and name not in observations:
                observations[name] = [dict(kind='default', source_ref=f'tool:{LINK_TOOL}#{name}', span=None,
                                           value=0, unit=spec['unit'])]
            elif 'default' in spec and name not in observed and name not in observations:
                observations[name] = [dict(kind='default', source_ref=f'card:{card_id}#{name}', span=None,
                                           value=spec['default']['value'], unit=spec['default']['unit'])]
    return observations


def sources_for(request, entities, cards, final, observed, root=None):
    """Plan order, extra parameter sources and the assumptions to confirm, for one request.

    observed holds the inputs the text and the form already give. The distance is taken from
    coordinates only when both sites resolve; the radio horizon then runs next to check it.
    A distance the user states is used as is: the site names are then only labels, so "A 楼顶"
    is not matched to the library's A 站 (TEACHER_CASES).

    A link margin by modulation, or one with no stated receiver sensitivity, runs as the registered
    calc_link_margin tool (TEACHER_CASES): free space, path loss with the frequency in MHz, losses zero,
    and the sensitivity of each named modulation from the modulation table. Site names the library
    does not know are then only labels too, and so is a placeholder such as a bare "A" that only
    resembles the library's "A站": coordinates are read only for names written as in the library.
    """
    store = FactService(root or ROOT)
    labels = [e['mention'] for e in entities if e['kind'] == 'site'] if 'distance_km' in observed else []
    sites, devices, issues = resolve([e for e in entities if not (labels and e['kind'] == 'site')], root, store)
    facts = fact_observations(request, sites, devices)
    supplied = set(observed) | set(facts)
    found, unknown, excluded = modulations(request['raw_text'], store) if final == 'link_margin' else ([], [], [])
    issues.extend(diagnostic('MODULATION_EXCLUDED', f"已按原文排除调制方式“{e['mention']}”。", **e) for e in excluded)
    # A radio named in the text supplies the sensitivity once its record is read: the general link budget.
    text = request['raw_text'].lower()
    radio = bool(devices) or any(n.lower() in text for r in store.records() if r['type'] == 'device' for n in r['names'])
    teacher = (final == 'link_margin' and not set(ZERO) & set(observed)
               and bool(found or unknown or ('rx_threshold_dbm' not in supplied and not radio)))
    named = []
    written = {n for r in store.records() if r['type'] == 'site' for n in r['names']}
    loose = [e for e in entities if e['kind'] == 'site' and e['mention'] not in labels
             and ''.join(e['mention'].split()) not in written]
    if teacher and (len(sites) < 2 or loose):
        named = [e['mention'] for e in entities if e['kind'] == 'site' and e['mention'] not in labels]
        issues = [d for d in issues if not (d['code'] in {'ENTITY_UNKNOWN', 'ENTITY_AMBIGUOUS'} and d['details']['kind'] == 'site')]
        sites = []
        facts = fact_observations(request, sites, devices)
        supplied = set(observed) | set(facts)
    order, leaves = [], []
    if final:
        exclude = (() if len(sites) == 2 else GEOMETRY) + (('fspl_ghz',) if teacher else TEACHER)
        order, leaves = chain(final, cards, supplied, exclude)
        order = with_line_of_sight(order)
        by_id = {c['id']: c for c in cards}
        leaves += [n for i in order for n in by_id[i]['parameters'] if n not in leaves and n not in
                   {by_id[j]['output']['name'] for j in order}]
        leaves = list(dict.fromkeys(ALIASES.get(n, (n,))[0] for n in leaves))
    # The receiver sensitivity of the first named modulation; the others are compared with it.
    chosen, variants = {}, []
    if 'rx_threshold_dbm' in leaves and 'rx_threshold_dbm' not in observed and found:
        first = found[0]
        chosen['rx_threshold_dbm'] = [dict(kind='modulation', source_ref=f"{first['id']}#rx_sensitivity_dbm", span=None,
                                           value=first['rx_sensitivity_dbm'], unit='dBm')]
        if teacher:
            variants = [dict(label=r['names'][0], parameter='rx_threshold_dbm', value=r['rx_sensitivity_dbm'], unit='dBm',
                             source_ref=f"{r['id']}#rx_sensitivity_dbm") for r in found[1:]]
        elif len(found) > 1:
            issues.append(diagnostic('MODULATION_COUNT', '写了损耗时一次只按一种调制方式计算，请只保留一种。',
                                     modulations=[r['names'][0] for r in found]))
    excluded_names = {name for e in excluded for name in e['modulations']}
    choices = [r['names'][0] for r in store.modulation_records() if r['names'][0] not in excluded_names] if unknown or teacher else []
    for u in unknown:
        issues.append(diagnostic('MODULATION_UNKNOWN', f"调制表中没有“{u['mention']}”。", mention=u['mention'],
                                 span=u['span'], choices=choices))
    if teacher and not found and not unknown and 'rx_threshold_dbm' not in supplied:
        issues.append(diagnostic('MODULATION_NEEDED', '还没有调制方式，无法查调制表得到接收灵敏度。', choices=choices))
    defaults = default_observations(order, cards, supplied | set(chosen), teacher)
    by_id = {c['id']: c for c in cards}
    notes = []
    if len(sites) == 2 and 'slant_range_wgs84' in order:
        titles = '、'.join(dict.fromkeys(s['source']['title'] for s in sites))
        notes.append(f"两端站点 {sites[0]['names'][0]}、{sites[1]['names'][0]} 的坐标与天线高度取自{titles}。")
    if labels:
        notes.append('距离按原文；' + '、'.join(f'“{m}”' for m in dict.fromkeys(labels)) + '只作标签，未查站点库。')
    if named:
        notes.append('、'.join(f'“{m}”' for m in dict.fromkeys(named)) + '不在站点库，只作标签；距离按原文或补充的数值。')
    if teacher:
        notes.extend(a.rstrip('。') + '。' for a in link_tool(root)['assumptions'])
    if chosen:
        used = found if teacher else found[:1]
        notes.append('接收灵敏度取调制表（模拟参数，可配置）：'
                     + '、'.join(f"{r['names'][0]} {shown(r['rx_sensitivity_dbm'])} dBm" for r in used) + '。')
    if len(devices) == 1 and any(o['kind'] == 'device' for f in facts.values() for o in f):
        notes.append(f"两端电台均按 {devices[0]['model']}，参数取自{devices[0]['source']['title']}。")
    for name, (origin,) in defaults.items():
        if not origin['source_ref'].startswith('card:'):
            continue  # the link tool's zero losses are stated once, above
        card, param = origin['source_ref'][len('card:'):].split('#')
        note = by_id[card]['parameters'][param]['default']['note']
        notes.append(f"{field_label(name)}按假设取 {shown(origin['value'])} {origin['unit']}：{note}。")
    sources = {}
    for extra in (facts, chosen, defaults):
        for field, origins in extra.items():
            sources.setdefault(field, []).extend(origins)
    return dict(order=order, leaves=leaves, sources=sources, notes=notes, issues=issues, sites=sites, devices=devices,
                labels=list(dict.fromkeys(labels + named)), tool=LINK_TOOL if teacher else None, variants=variants,
                conditions=['free_space'] if teacher else [], modulations=[r['names'][0] for r in found])


def plan_goal(requirement, solve, final, leaves):
    """The margin requirement a plan compares against, and what to solve for when it is not met."""
    wanted = {k: requirement[k] for k in ('quantity', 'op', 'value', 'unit')} if requirement and final == 'link_margin' else None
    return wanted, (solve['unknown'] if solve and wanted and solve['unknown'] in leaves else None)


def fact_questions(issues):
    """What to ask for each name that did not resolve."""
    asks = {'ENTITY_UNKNOWN': lambda d: '请改用库中的名称，或直接写出距离与设备参数。',
            'ENTITY_AMBIGUOUS': lambda d: '可选：' + '、'.join(d['details']['choices']) + '。',
            'MODULATION_UNKNOWN': lambda d: '可选：' + '、'.join(d['details']['choices']) + '。',
            'MODULATION_NEEDED': lambda d: ('请选择调制方式（' + '、'.join(d['details']['choices']) + '），或直接写出接收灵敏度。'
                if d['details']['choices'] else '已排除全部登记调制方式，请核对选择或直接写出接收灵敏度。'),
            'SITE_COUNT': lambda d: '', 'DEVICE_COUNT': lambda d: '', 'MODULATION_COUNT': lambda d: ''}
    return [d['message'] + asks[d['code']](d) for d in issues if d['code'] in asks]


def band_issues(devices, values):
    """A radio is used only inside its declared band."""
    frequency = values.get('frequency_ghz')
    if len(devices) != 1 or type(frequency) not in (int, float):
        return []
    low, high = devices[0]['band_ghz']
    if low <= frequency <= high:
        return []
    return [diagnostic('DEVICE_BAND', f"频率 {shown(frequency)} GHz 不在 {devices[0]['model']} 的工作频段 "
                                      f"{shown(low)}–{shown(high)} GHz 内。", device=devices[0]['id'])]
