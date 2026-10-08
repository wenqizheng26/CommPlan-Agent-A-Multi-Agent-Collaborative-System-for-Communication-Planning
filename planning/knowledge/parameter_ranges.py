"""One engineering-range table for requirement checks and tool schemas."""
import copy
import json
from pathlib import Path
from formula_rag.schema import BOUNDS, check_schema, validate


UNITS = {'distance_km': 'km', 'frequency_mhz': 'MHz', 'tx_power_dbm': 'dBm',
         'tx_gain_dbi': 'dBi', 'rx_gain_dbi': 'dBi'}
LABELS = {'distance_km': '路径距离', 'frequency_mhz': '载波频率', 'tx_power_dbm': '发射功率',
          'tx_gain_dbi': '发射天线增益', 'rx_gain_dbi': '接收天线增益'}


def load_ranges(root):
    table = json.loads((Path(root) / 'knowledge/facts/parameter_ranges.json').read_text(encoding='utf-8-sig'))
    if type(table) is not dict or set(table) != set(UNITS):
        raise ValueError('PARAMETER_RANGES_INVALID')
    for field, entry in table.items():
        if (type(entry) is not dict or entry.get('unit') != UNITS[field]
                or type(entry.get('reason')) is not str or not entry['reason'].strip()
                or set(entry) not in ({'unit', 'reason', 'minimum', 'maximum'},
                                     {'unit', 'reason', 'exclusiveMinimum', 'maximum'})):
            raise ValueError('PARAMETER_RANGES_INVALID')
        check_schema(range_schema(entry))
        lower = entry.get('minimum', entry.get('exclusiveMinimum'))
        if lower >= entry['maximum']:
            raise ValueError('PARAMETER_RANGES_INVALID')
    return table


def range_schema(entry):
    return dict(type='number', **{key: entry[key] for key in BOUNDS if key in entry})


def expand_range_schema(schema, ranges):
    """Expand private table references; duplicated numeric limits are refused."""
    if type(schema) is list:
        return [expand_range_schema(item, ranges) for item in schema]
    if type(schema) is not dict:
        return copy.deepcopy(schema)
    expanded = {key: expand_range_schema(value, ranges) for key, value in schema.items() if key != 'x-range-from'}
    if 'x-range-from' in schema:
        field = schema['x-range-from']
        if type(field) is not str or field not in ranges or set(schema) & BOUNDS or schema.get('type') != 'number':
            raise ValueError('TOOL_RANGE_SOURCE_INVALID')
        expanded.update(range_schema(ranges[field]))
    return expanded


def range_issues(parameters, root):
    """Inspect every interval endpoint or candidate in canonical parameter units."""
    # Keep this shared facts module free of a contract/input-domain import cycle.
    from planning.services.input_domains import numbers

    ranges = load_ranges(root)
    issues = []
    for parameter in parameters:
        field, value = parameter['canonical_name'], parameter['value']
        table_field = 'frequency_mhz' if field == 'frequency_ghz' else field
        if table_field not in ranges or value is None:
            continue
        entry = ranges[table_field]
        multiplier = 1000 if field == 'frequency_ghz' else 1
        values = [v * multiplier for v in numbers(value)]
        invalid = [v for v in values if validate(v, range_schema(entry))]
        if not invalid:
            continue
        shown = lambda number: f'{number:g}'.replace('-', '−')
        limits = (f"大于 {shown(entry['exclusiveMinimum'])} 且不超过 {shown(entry['maximum'])}"
                  if 'exclusiveMinimum' in entry else f"{shown(entry['minimum'])}～{shown(entry['maximum'])}")
        message = (f"{LABELS[table_field]} {' / '.join(shown(v) for v in invalid)} {entry['unit']} "
                   f"超出工程范围（{limits} {entry['unit']}），请核对")
        issues.append(dict(code='PARAMETER_OUT_OF_RANGE', message=message,
                           details=dict(field=field, table_field=table_field, values=invalid,
                                        unit=entry['unit'], reason=entry['reason'])))
    return issues
