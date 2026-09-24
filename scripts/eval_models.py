"""Compare local chat profiles with a deterministic requirements baseline.

The script never downloads models. An offline service produces an explicit
unscored report, not a passing or failing model score.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from formula_rag.model import LocalSelector  # noqa: E402
from planning.agents.requirements import RequirementsAgent  # noqa: E402
from planning.providers.registry import Registry  # noqa: E402
from planning.requirements_contract import STATUSES, strict_json  # noqa: E402

DEFAULT_CASES = ROOT / 'tests/eval/requirements_cases.jsonl'
REQUIRED_CATEGORIES = {'complete', 'missing', 'conflict', 'interval', 'choices',
                       'no_unit', 'out_of_scope', 'manual'}


def load_cases(path):
    cases, identifiers, categories = [], set(), set()
    for number, line in enumerate(Path(path).read_text(encoding='utf-8-sig').splitlines(), 1):
        if not line.strip():
            continue
        case = strict_json(line)
        if type(case) is not dict or set(case) != {'id', 'category', 'request', 'expected'}:
            raise ValueError(f'case {number}: invalid fields')
        if type(case['id']) is not str or not case['id'] or case['id'] in identifiers:
            raise ValueError(f'case {number}: duplicate or empty id')
        if case['category'] not in REQUIRED_CATEGORIES:
            raise ValueError(f'case {number}: unknown category')
        request, expected = case['request'], case['expected']
        if type(request) is not dict or set(request) != {'raw_text', 'manual_parameters', 'condition', 'target'}:
            raise ValueError(f'case {number}: invalid request')
        if type(expected) is not dict or set(expected) != {'parameters', 'targets', 'conditions', 'status', 'diagnostic_codes', 'questions_required'}:
            raise ValueError(f'case {number}: invalid expected fields')
        if type(expected['parameters']) is not dict or type(expected['targets']) is not list or type(expected['conditions']) is not list:
            raise ValueError(f'case {number}: invalid expectations')
        for value in expected['parameters'].values():
            if type(value) is not dict or set(value) != {'value', 'unit'}:
                raise ValueError(f'case {number}: invalid parameter expectation')
        if (type(expected['diagnostic_codes']) is not list or type(expected['status']) is not str
                or expected['status'] not in STATUSES
                or type(expected['questions_required']) is not bool):
            raise ValueError(f'case {number}: invalid status expectation')
        identifiers.add(case['id'])
        categories.add(case['category'])
        cases.append(case)
    if not cases or (Path(path).resolve() == DEFAULT_CASES.resolve() and categories != REQUIRED_CATEGORIES):
        raise ValueError('evaluation set is empty or missing required categories')
    return cases


def equivalent(actual, expected):
    if type(expected) is dict:
        return type(actual) is dict and set(actual) == set(expected) and all(
            equivalent(actual[k], value) for k, value in expected.items())
    if type(expected) is list:
        return type(actual) is list and len(actual) == len(expected) and all(
            equivalent(a, b) for a, b in zip(actual, expected))
    if type(expected) in (int, float):
        return type(actual) in (int, float) and math.isclose(actual, expected, rel_tol=1e-10, abs_tol=1e-12)
    return actual == expected


def score(report, expected):
    parameters = {p['canonical_name']: {'value': p['value'], 'unit': p['unit']}
                  for p in report['parameters_proposal']}
    diagnostics = {item['code'] for item in report['diagnostics']}
    return {
        'parameters': equivalent(parameters, expected['parameters']),
        'targets': report['targets'] == expected['targets'],
        'conditions': set(report['conditions']) == set(expected['conditions']),
        'status': report['execution_status'] == expected['status'],
        'diagnostics': set(expected['diagnostic_codes']) <= diagnostics,
        'questions': bool(report['questions']) == expected['questions_required'],
    }


def percentile(values, percent):
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(len(ordered) * percent / 100))
    return ordered[rank - 1]


def model_available(binding):
    base = binding.url.rsplit('/v1/chat/completions', 1)[0]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(base + '/health', timeout=2) as response:
            healthy = json.load(response).get('status') == 'ok'
        with opener.open(base + '/v1/models', timeout=2) as response:
            listing = json.load(response)
        return healthy and any(item.get('id') == binding.alias for item in listing.get('data', []))
    except (OSError, ValueError, urllib.error.URLError):
        return False


def case_result(agent, case):
    request = dict(schema_version='1.0.0', task_id='eval-' + case['id'], revision=0,
                   request_id='eval-' + case['id'], **case['request'])
    start = time.perf_counter()
    report = agent.run(request)
    elapsed_ms = round((time.perf_counter() - start) * 1000)
    checks = score(report, case['expected'])
    diagnostics = [item['code'] for item in report['diagnostics']]
    calls = [item['details'] for item in report['diagnostics'] if item['code'] == 'MODEL_CALL']
    attempts = [item for item in report['diagnostics']
                if item['code'].startswith('MODEL_') and type(item['details'].get('attempt')) is int]
    attempted = bool(attempts)
    usage = Counter()
    for call in calls:
        for key in ('prompt_tokens', 'completion_tokens'):
            value = call.get('usage', {}).get(key)
            if type(value) is int and value >= 0:
                usage[key] += value
    failures = [item['code'] for item in attempts if item['code'] != 'MODEL_CALL']
    return dict(id=case['id'], category=case['category'], elapsed_ms=elapsed_ms,
                checks=checks, passed=all(checks.values()),
                actual_status=report['execution_status'], runtime_health=report['runtime_health'],
                interpretation=report['component_modes']['interpretation'],
                model_attempted=attempted, structured_success=bool(calls) if attempted else None,
                degradation_reasons=failures if report['runtime_health'] != 'ready' else [],
                usage=dict(usage), diagnostic_codes=diagnostics)


def summarize(rows):
    measured = [row for row in rows if row.get('checks') is not None]
    attempted = [row for row in measured if row['model_attempted']]
    degraded = [row for row in measured if row['runtime_health'] != 'ready']
    token = Counter()
    reasons = Counter()
    for row in measured:
        token.update(row['usage'])
        reasons.update(row['degradation_reasons'])
    return dict(cases=len(rows), scored=len(measured),
                accuracy={key: {'passed': sum(row['checks'][key] for row in measured), 'total': len(measured)}
                          for key in ('parameters', 'targets', 'conditions', 'status', 'diagnostics', 'questions')},
                structured={'passed': sum(row['structured_success'] is True for row in attempted),
                            'attempted': len(attempted)},
                degraded_cases=len(degraded), degradation_reasons=dict(reasons),
                latency_ms={'p50': percentile([row['elapsed_ms'] for row in measured], 50),
                            'p95': percentile([row['elapsed_ms'] for row in measured], 95)},
                tokens=dict(token))


def evaluate(root, cases, model_id, registry):
    if model_id == 'deterministic':
        agent = RequirementsAgent(root, selector=False)
        availability = 'ready'
    else:
        binding = registry.binding('requirements', model_id, {})
        availability = ('not_installed' if not registry.installed(model_id) else
                        'ready' if model_available(binding) else 'offline')
        if availability != 'ready':
            rows = [dict(id=case['id'], category=case['category'], checks=None,
                         reason=availability + '_at_preflight') for case in cases]
            return dict(model_id=model_id, availability=availability, cases=rows, summary=summarize(rows))
        selector = LocalSelector(binding.url, model=binding.alias,
                                 temperature=binding.temperature, timeout=binding.timeout_s,
                                 context=binding.context)
        selector.model_id = binding.model_id
        agent = RequirementsAgent(root, selector=selector)
    rows = [case_result(agent, case) for case in cases]
    return dict(model_id=model_id, availability=availability, cases=rows, summary=summarize(rows))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--cases', type=Path, default=DEFAULT_CASES)
    parser.add_argument('--models', nargs='*', help='Registry chat ids; empty means deterministic baseline only')
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    registry = Registry(root)
    cases = load_cases(args.cases)
    ids = ['deterministic', *(args.models if args.models is not None else
                             [name for name in registry.models if registry.kind(name) == 'chat'])]
    if len(ids) != len(set(ids)) or any(name != 'deterministic' and
                                       (registry.kind(name) != 'chat' or not registry.strict(name)) for name in ids):
        parser.error('--models must list unique structured chat model ids from the registry')
    output = args.output_dir or root / 'outputs/eval'
    output.mkdir(parents=True, exist_ok=True)
    source_digest = hashlib.sha256(Path(args.cases).read_bytes()).hexdigest()
    stamp = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%M%SZ')
    for model_id in ids:
        result = evaluate(root, cases, model_id, registry)
        result.update(generated_at_utc=datetime.now(timezone.utc).isoformat(),
                      case_set_sha256=source_digest, source='RequirementsAgent; no numeric calculation')
        path = output / f'{stamp}-{model_id}.json'
        path.write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
        print(json.dumps(dict(model_id=model_id, availability=result['availability'],
                              summary=result['summary'], path=str(path)), ensure_ascii=False), flush=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
