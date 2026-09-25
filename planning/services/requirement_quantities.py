"""Numbers with units in the request text, for the model to label.

The model only says what each quantity means. Every value and unit still comes
from the text itself, so a label can never introduce a number.
"""
import re
import unicodedata
from formula_rag.parsing import FIELDS, NUMBER, UNITS, convert
from planning.services.input_domains import extract_domains

REQUIREMENT = 'required_margin_db'
OTHER = 'other'
# Inputs of the plan-capable cards, in link order. Heights and sites come from the site store.
LABEL_FIELDS = ['frequency_ghz', 'distance_km', 'tx_power_dbm', 'tx_gain_dbi', 'rx_gain_dbi', 'tx_loss_db',
                'rx_loss_db', 'extra_loss_db', 'path_loss_db', 'rx_power_dbm', 'rx_threshold_dbm', 'reserve_db',
                REQUIREMENT, OTHER]
SOLVE_UNKNOWNS = ['tx_power_dbm']

# "10个dB" is spoken Chinese for 10 dB; the value and unit are still read from the text.
QUANTITY = re.compile(rf'(?P<value>{NUMBER})\s*(?:个\s*)?(?P<unit>{UNITS})(?![A-Za-z/\d])', re.I)
# Contexts in which extract_request refuses to read a value; the model gets no say there either.
UNCERTAIN = re.compile(r'不是|不为|不用|不要用|不能用|未知|不确定|不知道|是否|例如|假如|如果')
RANGE = re.compile(rf'{NUMBER}\s*(?:{UNITS})?\s*(?:~|～|至|到|—|–|/|±|或者|或|、)\s*{NUMBER}\s*{UNITS}'
                   rf'|(?:{NUMBER}\s*[×*x]\s*)?10\s*\^\s*{NUMBER}\s*{UNITS}|\d+(?:,\d{{3}})+\s*{UNITS}', re.I)
AT_LEAST = re.compile(r'(?:>=|≥|至少|不少于|不低于|不小于|最少|起码)\s*$')
AT_MOST = re.compile(r'(?:<=|≤|至多|不超过|不高于|不大于|最多)\s*$')
CLAUSE = re.compile(r'[^，,。；;\n？?！!]+')


def normalized(text):
    """NFKC per character, with a map from each normalized position back to the text."""
    chars, index = [], []
    for i, ch in enumerate(text):
        n = unicodedata.normalize('NFKC', ch).replace('−', '-')
        chars.append(n)
        index.extend([i] * len(n))
    index.append(len(text))
    return ''.join(chars), index


def find_quantities(text):
    norm, index = normalized(text)
    span = lambda m: [index[m.start()], index[m.end() - 1] + 1]
    blocked = [span(m) for m in RANGE.finditer(norm)]
    domains, issues = extract_domains(text)
    blocked += [d['span'] for d in domains] + [i['details']['span'] for i in issues]
    clauses = [m for m in CLAUSE.finditer(text)]
    blocked += [[c.start(), c.end()] for c in clauses if UNCERTAIN.search(c.group())]
    found = []
    for m in QUANTITY.finditer(norm):
        a, b = span(m)
        if any(x < b and a < y for x, y in blocked):
            continue
        prefix = norm[max(0, m.start() - 4):m.start()]
        clause = next((c.group().strip() for c in clauses if c.start() <= a < c.end()), text[a:b])
        found.append(dict(id=f'q{len(found) + 1}', span=[a, b], text=text[a:b], value=float(m['value']),
                          unit=m['unit'], comparison='>=' if AT_LEAST.search(prefix) else '<=' if AT_MOST.search(prefix) else None,
                          context=clause[:60]))
    return found


def ground_labels(text, quantities, model):
    """Check the model's labels against the text; never a new value.

    Returns (accepted, rejected, dropped). A rejected quantity fails the whole answer, because a
    wrong label could move a number. A mention or solve request that is not in the text is only
    dropped: without it the program asks the user instead.
    """
    by_id = {q['id']: q for q in quantities}
    accepted, rejected, dropped = [], [], []
    for item in model.get('quantities', []):
        q, field = by_id[item['id']], item['field']
        if field == OTHER:
            continue
        if field == REQUIREMENT:
            if q['unit'].lower() != 'db' or q['comparison'] == '<=':
                rejected.append(dict(kind='quantity', id=q['id'], reason=f'{q["text"]} 不是以 dB 表示的余量下限'))
                continue
            accepted.append(dict(kind='requirement', span=q['span'], field=field, value=q['value'], unit='dB'))
            continue
        if q['comparison']:
            rejected.append(dict(kind='quantity', id=q['id'], reason=f'{q["text"]} 是上限或下限，不是参数的取值'))
            continue
        try:
            convert(field, q['value'], q['unit'])
        except ValueError:
            rejected.append(dict(kind='quantity', id=q['id'],
                                 reason=f'{q["text"]} 的单位与{FIELDS[field][0]}（{FIELDS[field][1]}）不符'))
            continue
        accepted.append(dict(kind='quantity', span=q['span'], field=field, value=q['value'], unit=q['unit']))
    if sum(a['kind'] == 'requirement' for a in accepted) > 1:
        rejected.append(dict(kind='quantity', reason='余量要求只能有一个'))
    for item in model.get('solve', []):
        found = solve_span(text, item['evidence'])
        if not found:
            dropped.append(dict(kind='solve', evidence=item['evidence'][:60], reason='原文中没有询问发射功率的问句'))
            continue
        accepted.append(dict(kind='solve', unknown=item['unknown'], span=found))
    for kind in ('site', 'device'):
        for item in model.get(kind + 's', []):
            found = mention_span(text, item['evidence'], item['mention'], kind == 'site')
            if not found:
                dropped.append(dict(kind=kind, mention=item['mention'][:30], reason='原文中没有这个名称'))
                continue
            if any(a['kind'] == kind and a['span'] == found for a in accepted):
                continue
            accepted.append(dict(kind=kind, mention=text[found[0]:found[1]], span=found))
    return accepted, rejected, dropped


def solve_span(text, evidence):
    """The clause asking for transmit power, in the sentence the model quoted. A quote of only the
    condition ("如果不能") is pointed to its question in the same sentence."""
    start = text.find(evidence) if isinstance(evidence, str) and evidence else -1
    if start < 0:
        return None
    ends = [m.end() for m in re.finditer(r'[。？?！!\n]', text)]
    left = max([0] + [e for e in ends if e <= start])
    right = min([len(text)] + [e for e in ends if e > start])
    for clause in CLAUSE.finditer(text, left, right):
        if re.search(r'功率|发射电平', clause.group()):
            a = clause.start() + len(clause.group()) - len(clause.group().lstrip())
            return [a, clause.end()]
    return None


def mention_span(text, evidence, mention, site=False):
    """Where a mention sits in the text: inside its quoted evidence if it is there, else its first
    occurrence anywhere in the text. Spaces may differ; the characters may not, except that a site
    written as "A站" may appear in the text as just "A"."""
    names = [mention]
    if site and isinstance(mention, str) and len(mention.strip()) > 1 and mention.strip().endswith('站'):
        names.append(mention.strip()[:-1])
    start = text.find(evidence) if isinstance(evidence, str) and evidence else -1
    for name in names:
        if start >= 0:
            found = find_in(text, start, start + len(evidence), name)
            if found:
                return found
        found = find_in(text, 0, len(text), name)
        if found:
            return found
    return None


def find_in(text, start, end, mention):
    target = re.sub(r'\s+', '', mention or '')
    if not target:
        return None
    for i in range(start, end):
        j, k = i, 0
        while j < end and k < len(target):
            if text[j].isspace():
                j += 1
            elif text[j] == target[k]:
                j, k = j + 1, k + 1
            else:
                break
        if k == len(target) and not text[i].isspace():
            return [i, j]
    return None


def summary(labels):
    """Requirement, solve request and mentions implied by accepted labels."""
    req = next((a for a in labels if a['kind'] == 'requirement'), None)
    solve = next((a for a in labels if a['kind'] == 'solve'), None)
    return (dict(quantity='link_margin_db', op='>=', value=req['value'], unit='dB', span=req['span']) if req else None,
            dict(unknown=solve['unknown'], span=solve['span']) if solve else None,
            [dict(kind=a['kind'], mention=a['mention'], span=a['span']) for a in labels if a['kind'] in {'site', 'device'}])
