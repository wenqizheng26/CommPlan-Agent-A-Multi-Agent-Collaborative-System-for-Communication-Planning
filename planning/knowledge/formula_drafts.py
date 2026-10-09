"""Untrusted formula proposals and independent human review inputs."""
import copy
import math
import re
from urllib.parse import urlsplit

from formula_rag.catalog import validate_card
from formula_rag.core import evaluate
from planning.requirements_contract import require


def finite(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def validate_formula(record, *, require_example=False):
    """Check expression declarations and every supplied numeric example."""
    from planning.services.card_units import supported_unit
    require(type(record) is dict, 'DRAFT_FORMULA')
    require(type(record.get('id')) is str and re.fullmatch(r'[a-z0-9_]{1,64}', record['id']), 'DRAFT_ID')
    require(record.get('kind', 'expression') == 'expression', 'DRAFT_PYTHON_FORBIDDEN')
    errors = validate_card(dict(record, status='draft'))
    require(not errors, 'DRAFT_FORMULA: ' + '; '.join(errors)[:300])
    require(all(len(record[key]) <= limit for key, limit in
                (('title', 200), ('description', 2000), ('version', 40))), 'DRAFT_FORMULA_LENGTH')
    require(type(record['parameters']) is dict and 1 <= len(record['parameters']) <= 16, 'DRAFT_PARAMETERS')
    require(supported_unit(record['output']['unit']), 'DRAFT_UNIT: output')
    for name, spec in record['parameters'].items():
        require(supported_unit(spec['unit']), 'DRAFT_UNIT: ' + name)
    notes = record['applicability'].get('notes', [])
    from planning.requirements_contract import CONDITIONS
    require(set(record['applicability']['requires']) <= CONDITIONS, 'DRAFT_APPLICABILITY')
    require(type(notes) is list and len(notes) <= 16
            and all(type(note) is str and len(note) <= 1000 for note in notes), 'DRAFT_APPLICABILITY')
    examples = record['examples']
    require(len(examples) <= 16 and (examples or not require_example), 'DRAFT_FORMULA_EXAMPLE')
    for example in examples:
        require(check_example(record, example)['passed'], 'DRAFT_EXAMPLE_FAILED')
    return record


def check_example(record, example):
    """No caller-selected tolerance; extra, missing, nonfinite or out-of-domain inputs fail."""
    require(type(example) is dict and type(example.get('inputs')) is dict
            and set(example['inputs']) == set(record['parameters'])
            and all(finite(value) for value in example['inputs'].values())
            and finite(example.get('expected')), 'DRAFT_EXAMPLE_FAILED')
    expected = example['expected']
    tolerance = max(1e-6, abs(expected) * 1e-6)
    result = evaluate(dict(record, status='verified'), example['inputs'])
    value = result.get('value')
    passed = result.get('status') == 'ok' and finite(value) and abs(value - expected) <= tolerance
    return dict(inputs=copy.deepcopy(example['inputs']), expected=expected,
                value=value if finite(value) else None, tolerance=tolerance,
                unit=record['output']['unit'], passed=passed)


def review_inputs(record, source, example):
    require(type(source) is dict and {'title', 'locator'} <= set(source) <= {'title', 'locator', 'url'}
            and all(type(source[key]) is str and 1 <= len(source[key].strip()) <= 1000
                    for key in ('title', 'locator'))
            and type(example) is dict and set(example) == {'inputs', 'expected', 'note'}
            and type(example['note']) is str and 1 <= len(example['note'].strip()) <= 1000,
            'DRAFT_SOURCE_REQUIRED')
    clean_source = {key: value.strip() for key, value in source.items() if type(value) is str}
    if 'url' in source:
        require(type(source['url']) is str and len(source['url']) <= 2000, 'DRAFT_SOURCE_REQUIRED')
        parsed = urlsplit(source['url'])
        require(parsed.scheme in ('https', 'http') and parsed.netloc and not parsed.username,
                'DRAFT_SOURCE_REQUIRED')
    checked = check_example(record, example)
    require(checked['passed'], 'DRAFT_EXAMPLE_FAILED')
    clean_example = dict(inputs=copy.deepcopy(example['inputs']), expected=example['expected'],
                         tolerance=checked['tolerance'], note=example['note'].strip())
    return clean_source, clean_example


def model_schema():
    """A flat bounded form avoids arbitrary nested record output from the model."""
    text = dict(type='string')
    number = dict(type='number')
    named = lambda fields: dict(type='array', minItems=1, maxItems=16,
        items=dict(type='object', properties=dict(name=text, **fields),
                   required=['name', *fields], additionalProperties=False))
    fields = dict(id=text, title=text, description=text, expression=text, output_name=text, output_unit=text,
                  parameters=named(dict(unit=text, description=text)),
                  notes=dict(type='array', maxItems=8, items=text),
                  example_inputs=named(dict(value=number)), example_expected=number)
    return dict(type='object', properties=fields, required=list(fields), additionalProperties=False)


def model_record(output):
    require(type(output) is dict and set(output) == set(model_schema()['properties']), 'DRAFT_MODEL_SHAPE')
    parameters, inputs = output['parameters'], output['example_inputs']
    require(type(parameters) is list and type(inputs) is list
            and all(type(p) is dict and set(p) == {'name', 'unit', 'description'} for p in parameters)
            and all(type(p) is dict and set(p) == {'name', 'value'} for p in inputs), 'DRAFT_MODEL_SHAPE')
    names = [p['name'] for p in parameters]
    input_names = [p['name'] for p in inputs]
    require(all(type(name) is str for name in names + input_names)
            and len(set(names)) == len(names) and len(set(input_names)) == len(input_names)
            and set(names) == set(input_names), 'DRAFT_FORMULA_EXAMPLE')
    return dict(id=output['id'], title=output['title'], description=output['description'], version='1.0.0',
                status='draft', expression=output['expression'],
                output=dict(name=output['output_name'], unit=output['output_unit']),
                parameters={p['name']: dict(unit=p['unit'], description=p['description']) for p in parameters},
                applicability=dict(requires=[], notes=output['notes']), sources=[],
                examples=[dict(inputs={p['name']: p['value'] for p in inputs}, expected=output['example_expected'])])
