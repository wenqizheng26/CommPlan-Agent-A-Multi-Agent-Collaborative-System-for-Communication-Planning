"""Explicit numeric domains; bounds are not probability distributions."""
import itertools
import math
import re
from formula_rag.parsing import NUMBER, convert, FIELDS

UNIT = r'(?:GHz|MHz|kHz|Hz|吉赫兹|兆赫兹|千赫兹|赫兹|km|千米|公里|m|米)'
PAIR = re.compile(rf'(?<![0-9A-Za-z_.-])(?P<a>{NUMBER})\s*(?P<u>{UNIT})?\s*(?P<op>\+/-|\+-|±|至|到|~|～|–|—|-(?!\d*[eE]))\s*(?P<b>{NUMBER})\s*(?P<v>{UNIT})(?![A-Za-z/\d])', re.I)
CHOICES = re.compile(rf'(?<![0-9A-Za-z_.-]){NUMBER}\s*(?:{UNIT})?(?:\s*(?:或者|或|、)\s*{NUMBER}\s*(?:{UNIT})?)+', re.I)
TOKEN = re.compile(rf'(?P<n>{NUMBER})\s*(?P<u>{UNIT})?', re.I)
APPROX = re.compile(rf'(?:大约|大概|差不多|近似|约)\s*{NUMBER}\s*{UNIT}|{NUMBER}\s*{UNIT}\s*(?:左右|上下)', re.I)


def numbers(value):
    if type(value) in (float, int):
        if not math.isfinite(value):
            raise ValueError('FINITE_NUMBER_REQUIRED')
        return [value]
    if type(value) is not dict:
        raise ValueError('NUMERIC_DOMAIN_REQUIRED')
    if value.get('kind') == 'interval' and set(value) == {'kind', 'lower', 'upper'}:
        out = numbers(value['lower']) + numbers(value['upper'])
        if len(out) != 2 or out[0] > out[1]:
            raise ValueError('INVALID_INTERVAL')
        return out
    if value.get('kind') == 'choices' and set(value) == {'kind', 'values'}:
        vals = value['values']
        if type(vals) is not list or not 2 <= len(vals) <= 8 or any(type(x) not in (float, int) for x in vals):
            raise ValueError('INVALID_CHOICES')
        out = [numbers(x)[0] for x in vals]
        if len(set(out)) != len(out):
            raise ValueError('DUPLICATE_CHOICES')
        return out
    raise ValueError('NUMERIC_DOMAIN_REQUIRED')


def convert_domain(field, value, unit):
    vals = [convert(field, n, unit) for n in numbers(value)]
    if type(value) is not dict:
        return vals[0]
    return (dict(kind='interval', lower=vals[0], upper=vals[1]) if value['kind'] == 'interval'
            else dict(kind='choices', values=vals))


def same(a, b):
    if type(a) is dict or type(b) is dict:
        return a == b
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=0)


def scenarios(parameters):
    keys = sorted(parameters)
    domains = [numbers(parameters[k]) for k in keys]
    if math.prod(map(len, domains)) > 64:
        raise ValueError('TOO_MANY_SCENARIOS')
    return [dict(zip(keys, row)) for row in itertools.product(*domains)]


def field_for(unit):
    return 'frequency_ghz' if re.search(r'hz|赫兹', unit, re.I) else 'distance_km'


def labelled_field(text, start, unit):
    prefix = re.split(r'[，,。；;\n？?！!]', text[:start])[-1]
    labels = [(m.start(), field) for field, (_, _, aliases) in FIELDS.items()
              for alias in aliases for m in re.finditer(re.escape(alias), prefix)]
    if labels:
        field = max(labels)[1]
        if field not in {'frequency_ghz', 'distance_km'} or field != field_for(unit):
            raise ValueError('DOMAIN_LABEL_MISMATCH')
        return field
    if re.search(r'高度|宽度|长度|半径|波长|海拔|带宽', prefix):
        raise ValueError('DOMAIN_LABEL_MISMATCH')
    return field_for(unit)


def extract_domains(text):
    found, issues = [], []
    # A boundary before a Chinese field label is unnecessary; numeric boundaries
    # only prevent a match beginning halfway through a number.
    for pattern, choice in ((PAIR, False), (CHOICES, True)):
        for match in pattern.finditer(text):
            if any(match.start() < x['span'][1] and match.end() > x['span'][0] for x in found):
                continue
            try:
                if choice:
                    tokens = list(TOKEN.finditer(match.group()))
                    unit = next((t['u'] for t in reversed(tokens) if t['u']), None)
                    if not unit:
                        continue
                    field = labelled_field(text, match.start(), unit)
                    vals = [convert(field, float(t['n']), t['u'] or unit) for t in tokens]
                    value = dict(kind='choices', values=vals)
                else:
                    unit = match['v']; field = labelled_field(text, match.start(), unit)
                    a = convert(field, float(match['a']), match['u'] or unit)
                    b = convert(field, float(match['b']), unit)
                    tolerance = match['op'] in ('±', '+-', '+/-')
                    if tolerance and b < 0:
                        raise ValueError('NEGATIVE_TOLERANCE')
                    value = dict(kind='interval', lower=a-b if tolerance else a, upper=a+b if tolerance else b)
                numbers(value)
                found.append(dict(field=field, value=value, unit='GHz' if field=='frequency_ghz' else 'km',
                                  span=[match.start(), match.end()], excerpt=match.group()))
            except (ValueError, OverflowError):
                issues.append(dict(code='INPUT_PARSE_ISSUE', message='区间或候选值格式无效，请核对顺序、单位与数量。',
                                   details=dict(excerpt=match.group(), span=list(match.span()))))
    return found, issues


def format_value(value):
    if type(value) is not dict:
        return f'{value:g}'
    if value['kind'] == 'interval':
        return f"{value['lower']:g}–{value['upper']:g}"
    return ' / '.join(f'{x:g}' for x in value['values'])
