"""H4: numbers in model-written text must be this task's own results or confirmed inputs.

A written number quotes a known value when it rounds from it at the precision it is
written with: 5.93, 5.9 and 6 all quote 5.928, while 5.94 does not. A number with a unit
must also be the same kind of quantity: km and m convert, but dB, dBm and dBi never stand
in for each other. Model names, standard numbers, dates and ordinals are not quantities.
"""
import math
import re
import unicodedata
from formula_rag.parsing import FIELDS

# unit -> (dimension, scale to the dimension's base unit)
SCALE = {'dbm/hz': ('dbm/hz', 1), 'dbm': ('dbm', 1), 'dbi': ('dbi', 1), 'dbw': ('dbw', 1), 'db': ('db', 1),
         'ghz': ('hz', 1e9), 'mhz': ('hz', 1e6), 'khz': ('hz', 1e3), 'hz': ('hz', 1),
         'km': ('m', 1e3), 'm': ('m', 1), 'kw': ('w', 1e3), 'w': ('w', 1), 'mw': ('w', 1e-3),
         '%': ('%', 1), '°': ('deg', 1), 'k': ('k', 1)}
ALIAS = {'分贝': 'db', '吉赫兹': 'ghz', '吉赫': 'ghz', '千兆赫': 'ghz', '兆赫兹': 'mhz', '兆赫': 'mhz',
         '千赫兹': 'khz', '千赫': 'khz', '赫兹': 'hz', '千米': 'km', '公里': 'km', '米': 'm',
         '千瓦': 'kw', '毫瓦': 'mw', '瓦': 'w', '度': '°'}
UNIT = '|'.join(re.escape(u) for u in sorted({*SCALE, *ALIAS}, key=len, reverse=True))
# A minus sign is not a hyphen: "1.4-2.7 GHz" is a range, "-92 dBm" is negative.
NUMBER = re.compile(rf'(?:(?<![A-Za-z0-9_.)）])(?P<sign>[-+])|(?P<neg>负))?(?P<num>\d+(?:\.\d+)?)'
                    rf'(?:\s*/\s*(?P<den>\d+(?:\.\d+)?))?(?:\s*(?:个\s*)?(?P<unit>{UNIT})(?![A-Za-z]))?', re.I)
IDENTIFIER = re.compile(r'[A-Za-z][A-Za-z0-9]*(?:[-.][A-Za-z0-9]+)*')
NOT_QUANTITY = re.compile(
    r'\d{4}\s*年(?:\s*\d{1,2}\s*月)?(?:\s*\d{1,2}\s*日)?|\d{1,2}\s*月\s*\d{1,2}\s*日|\d{4}-\d{1,2}-\d{1,2}'
    r'|[(（]\s*\d{1,2}\s*/\s*\d{4}\s*[)）]'
    r'|第\s*\d+(?:\.\d+)*\s*(?:步|项|条|点|个|段|种|次|节|章|页|式|部分)|步骤\s*\d+|§\s*\d+(?:\.\d+)*'
    r'|^\s*\d+\s*[.、)）](?!\d)|[(（]\s*\d+\s*[)）]', re.M)
DIGIT = '零一二两三四五六七八九十'
CHINESE_NUMERAL = re.compile(rf'[{DIGIT}百千万]*[{DIGIT}][{DIGIT}百千万]*(?:点[{DIGIT}]+)?\s*(?:个\s*)?'
                             r'(?:分贝|dBm|dBi|dB|千米|公里|米|毫瓦|瓦|千兆赫|吉赫|兆赫)')
IDENTITY_KEYS = {'id', 'refs', 'uses', 'tool_id', 'step_id'}


def normalized(text):
    text = re.sub('[①-⓿❶-➓]', ' ', text)  # circled ordinals would become digits
    return unicodedata.normalize('NFKC', text).replace('−', '-')


def blank(text, pattern, keep=lambda m: False):
    return pattern.sub(lambda m: m.group() if keep(m) else ' ' * len(m.group()), text)


def unit_of(unit):
    if not unit:
        return None, 1
    key = ALIAS.get(unit, unit.lower())
    return SCALE.get(key, (key, 1))


def written(text):
    """Every number in the text: (as written, value, decimals or None if exact, dimension, scale)."""
    text = blank(normalized(text), IDENTIFIER, keep=lambda m: not re.search(r'\d', m.group()))
    text = blank(text, NOT_QUANTITY)
    found = []
    for m in NUMBER.finditer(text):
        value = float(m['num'])
        decimals = len(m['num'].split('.')[1]) if '.' in m['num'] else 0
        if m['den']:
            if float(m['den']) == 0:
                continue
            value, decimals = value / float(m['den']), None
        if m['sign'] == '-' or m['neg']:
            value = -value
        found.append((m.group().strip(), value, decimals, *unit_of(m['unit'])))
    return found


def known(facts):
    """(value, dimension, scale) for every number in the facts; text fields keep their own units."""
    out = []

    def walk(x, unit=None):
        if isinstance(x, dict):
            own = x.get('unit') if isinstance(x.get('unit'), str) else None
            for key, value in x.items():
                if key == 'unit' or key in IDENTITY_KEYS:
                    continue
                if key in FIELDS:
                    walk(value, FIELDS[key][1])
                else:
                    walk(value, own or unit if key in {'value', 'lower', 'upper', 'values'} else None)
        elif isinstance(x, list):
            for value in x:
                walk(value, unit)
        elif isinstance(x, str):
            out.extend((value, dimension, scale) for _, value, _, dimension, scale in written(x))
        elif type(x) in (int, float) and math.isfinite(x):
            out.append((float(x), *unit_of(unit)))

    walk(facts)
    return out


def quotes(number, values):
    _, value, decimals, dimension, scale = number
    for v, d, s in values:
        if dimension is None:  # a bare number may quote any value, in the unit that value was given in
            target, got, tolerance = v, value, 0.5 * 10 ** -decimals if decimals is not None else 0
        elif d == dimension:
            target, got = v * s, value * scale
            tolerance = 0.5 * 10 ** -decimals * scale if decimals is not None else 0
        else:
            continue
        if abs(got - target) <= tolerance + 1e-9 * max(1, abs(target)):
            return True
    return False


def unquoted(text, values):
    """Numbers in the text that quote none of the values; empty when the text passes H4."""
    bad = [m.group() for m in CHINESE_NUMERAL.finditer(normalized(text))]
    return bad + [n[0] for n in written(text) if not quotes(n, values)]
