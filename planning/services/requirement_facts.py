"""Sites, devices and card assumptions as parameter sources (AGENT_LED §4, H3).

The model names the sites and the radio in the request; the program looks each name up in
the reviewed fact store and reads coordinates, antenna heights and radio figures from the
records. An input that the text does not state and no record supplies takes the assumption
its card declares, and the user confirms it with the plan. Every value keeps its source: a
record id and field, or a card and parameter. A value typed in the form overrides the store.
"""
from pathlib import Path
from planning.knowledge.facts import FactService
from planning.services.fact_fields import POSITION, field_label, field_unit
from planning.services.plans import chain, with_line_of_sight

ROOT = Path(__file__).resolve().parents[2]
# The same radio at both ends: power and gain at the transmitter, gain and sensitivity at the receiver.
DEVICE = (('tx_power_dbm', 'tx_power_dbm'), ('antenna_gain_dbi', 'tx_gain_dbi'),
          ('antenna_gain_dbi', 'rx_gain_dbi'), ('rx_sensitivity_dbm', 'rx_threshold_dbm'))
KIND = {'site': '站点', 'device': '设备'}


def diagnostic(code, message, **details):
    return {'code': code, 'message': message, 'details': details}


def shown(value):
    return f'{value:g}'


def resolve(entities, root=None):
    """The named sites in text order and the named device, plus an issue for each name that does not resolve."""
    store = FactService(root or ROOT)
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


def default_observations(order, cards, observed):
    """Card assumptions for plan inputs nothing else supplies."""
    by_id = {c['id']: c for c in cards}
    observations = {}
    for card_id in order:
        for name, spec in by_id[card_id]['parameters'].items():
            if 'default' in spec and name not in observed and name not in observations:
                observations[name] = [dict(kind='default', source_ref=f'card:{card_id}#{name}', span=None,
                                           value=spec['default']['value'], unit=spec['default']['unit'])]
    return observations


def sources_for(request, entities, cards, final, observed, root=None):
    """Plan order, extra parameter sources and the assumptions to confirm, for one request.

    observed holds the inputs the text and the form already give. The distance is taken from
    coordinates only when both sites resolve; the radio horizon then runs next to check it.
    """
    sites, devices, issues = resolve(entities, root)
    facts = fact_observations(request, sites, devices)
    order, leaves = [], []
    if final:
        known = set(observed) | set(facts)
        order, leaves = chain(final, cards, known, **({'exclude': ()} if len(sites) == 2 else {}))
        order = with_line_of_sight(order)
        by_id = {c['id']: c for c in cards}
        leaves += [n for i in order for n in by_id[i]['parameters'] if n not in leaves and n not in
                   {by_id[j]['output']['name'] for j in order}]
    defaults = default_observations(order, cards, set(observed) | set(facts))
    by_id = {c['id']: c for c in cards}
    notes = []
    if len(sites) == 2 and 'slant_range_wgs84' in order:
        titles = '、'.join(dict.fromkeys(s['source']['title'] for s in sites))
        notes.append(f"两端站点 {sites[0]['names'][0]}、{sites[1]['names'][0]} 的坐标与天线高度取自{titles}。")
    if len(devices) == 1 and any(o['kind'] == 'device' for f in facts.values() for o in f):
        notes.append(f"两端电台均按 {devices[0]['model']}，参数取自{devices[0]['source']['title']}。")
    for name, (origin,) in defaults.items():
        card, param = origin['source_ref'][len('card:'):].split('#')
        note = by_id[card]['parameters'][param]['default']['note']
        notes.append(f"{field_label(name)}按假设取 {shown(origin['value'])} {origin['unit']}：{note}。")
    sources = {}
    for extra in (facts, defaults):
        for field, origins in extra.items():
            sources.setdefault(field, []).extend(origins)
    return dict(order=order, leaves=leaves, sources=sources, notes=notes, issues=issues, sites=sites, devices=devices)


def plan_goal(requirement, solve, final, leaves):
    """The margin requirement a plan compares against, and what to solve for when it is not met."""
    wanted = {k: requirement[k] for k in ('quantity', 'op', 'value', 'unit')} if requirement and final == 'link_margin' else None
    return wanted, (solve['unknown'] if solve and wanted and solve['unknown'] in leaves else None)


def fact_questions(issues):
    """What to ask for each name that did not resolve."""
    asks = {'ENTITY_UNKNOWN': lambda d: '请改用库中的名称，或直接写出距离与设备参数。',
            'ENTITY_AMBIGUOUS': lambda d: '可选：' + '、'.join(d['details']['choices']) + '。',
            'SITE_COUNT': lambda d: '', 'DEVICE_COUNT': lambda d: ''}
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
