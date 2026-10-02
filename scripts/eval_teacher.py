"""The teacher's cases (tests/eval/teacher_cases.jsonl) end to end with the local model.

Each case is submitted as written. Where the first stop asks only for inputs that have a suggested
default, all suggestions are adopted with one answer (as the page's one-click button does); any
other question is left open. A confirmable plan is confirmed. The run is written to a new file
and compared with the frozen expectations: first stop, parsed inputs, site labels, open inputs,
and the link tool's results, spread and recommendation.
"""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from planning.workflow.task_service import TaskService

ROW = ('rx_sensitivity_dbm', 'path_loss_db', 'rx_power_dbm', 'link_margin_db')


def command(action, state=None, **extra):
    return dict(action=action, task_id=state['task_id'] if state else str(uuid.uuid4()), event_id=str(uuid.uuid4()),
                expected_revision=state['revision'] if state else 0,
                expected_state_version=state['state_version'] if state else 0, **extra)


def observed(report):
    """What the requirement step read: values, modulations, site labels and the open inputs."""
    params = {p['canonical_name']: p['value'] for p in report['parameters_proposal'] if p['value'] is not None}
    codes = {d['code']: d['details'] for d in report['diagnostics']}
    parsed = {k: params[k] for k in ('distance_km', 'tx_power_dbm', 'tx_gain_dbi', 'rx_gain_dbi') if k in params}
    if isinstance(params.get('frequency_ghz'), (int, float)):
        parsed['frequency_mhz'] = params['frequency_ghz'] * 1000
    modulations = list((codes.get('LINK_TOOL') or {}).get('modulations', []))
    modulations += [d['details']['mention'] for d in report['diagnostics'] if d['code'] == 'MODULATION_UNKNOWN']
    if modulations:
        parsed['modulations'] = modulations
    asked_modulation = any(d['code'] in {'MODULATION_NEEDED', 'MODULATION_UNKNOWN'} for d in report['diagnostics'])
    missing = [m for m in report['missing_parameters'] if not (m == 'rx_threshold_dbm' and asked_modulation)]
    if 'MODULATION_NEEDED' in codes:
        missing.append('modulation')
    return dict(parsed=parsed, nodes=[e['mention'] for e in report['entities'] if e['kind'] == 'site'], missing=missing,
                plan=(report.get('calculation_plan_proposal') or {}).get('selected_model'),
                tool=(report.get('calculation_plan_proposal') or {}).get('tool'))


def run_case(service, case, mode):
    timings, states = [], []

    def apply(c):
        start = time.monotonic()
        state = service.apply(c)['state']
        timings.append(dict(action=c['action'], seconds=round(time.monotonic() - start, 2)))
        states.append(state)
        return state
    s = apply(command('create', input=dict(raw_text=case['text'], manual_parameters={}, condition=None, target=None), mode=mode))
    first = dict(status=s['status'], **(observed(s['report']) if s.get('report') else {}),
                 issues=[i['field'] for i in s.get('input_issues', [])],
                 suggestions=(s.get('report') or {}).get('suggestions'))
    adopted = None
    issues = s.get('input_issues', [])
    if s['status'] == 'AWAITING_INPUT' and issues and all(i.get('suggestion') for i in issues):
        adopted = {i['field']: i['suggestion']['value'] for i in issues}
        s = apply(command('answer', s, answers={i['id']: i['suggestion']['value'] for i in issues}, mode=mode))
    if s['status'] == 'AWAITING_CONFIRMATION':
        s = apply(command('confirm', s, review_hash=s['review']['review_hash']))
    final = s.get('final_report') or {}
    return dict(first=first, adopted=adopted, status=s['status'], failure=s.get('failure'), timings=timings,
                tool_calls=final.get('tool_calls'), comparison=final.get('comparison'), conclusion=final.get('conclusion'),
                answer=(final.get('answer') or {}).get('text'), review=(final.get('review') or {}).get('decision'),
                modes=final.get('component_modes'), task_id=s['task_id'])


def close(a, b, tolerance):
    return isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(a - b) <= tolerance


def assess(case, run):
    want, got, errors = case['expected'], run['first'], []
    tolerance = want.get('tolerance', 1e-6)

    def check(ok, message):
        if not ok:
            errors.append(message)
    check(got['status'] == want['first_stop'], f"first stop {got['status']} != {want['first_stop']}")
    for key, value in want.get('parsed', {}).items():
        actual = got.get('parsed', {}).get(key)
        check(actual == value if key == 'modulations' else close(actual, value, tolerance), f'parsed {key} {actual} != {value}')
    check(not want.get('nodes') or got.get('nodes') == want['nodes'], f"nodes {got.get('nodes')} != {want.get('nodes')}")
    if 'missing' in want:
        check(sorted(got.get('missing', [])) == sorted(want['missing']), f"missing {got.get('missing')} != {want['missing']}")
    for field in want.get('ask', []):
        asked = {'frequency_mhz': 'frequency_ghz'}.get(field, field)
        check(asked in got.get('issues', []), f"asks {got.get('issues')} lacks {field}")
    if want.get('results'):
        calls = run['tool_calls'] or []
        check(run['status'] == 'COMPLETED', f"final {run['status']} {(run['failure'] or {}).get('code')}")
        check([c['label'] for c in calls] == [r['modulation'] for r in want['results']],
              f"modulations {[c['label'] for c in calls]} != {[r['modulation'] for r in want['results']]}")
        for call, row in zip(calls, want['results']):
            for key in ROW:
                check(close(call['result'][key], row[key], tolerance), f"{row['modulation']} {key} {call['result'][key]} != {row[key]}")
            check(call['result']['meets'] == row['meets'], f"{row['modulation']} meets")
    if 'margin_diff_db' in want:
        c = run['comparison'] or {}
        check(close(c.get('margin_diff_db'), want['margin_diff_db'], tolerance), f"spread {c.get('margin_diff_db')}")
        check(c.get('recommend') == want['recommend'], f"recommend {c.get('recommend')} != {want['recommend']}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['llm', 'deterministic'], default='llm')
    parser.add_argument('--only', nargs='*', help='case ids')
    parser.add_argument('--out', type=Path, default=ROOT / 'outputs' / 'teacher-eval')
    args = parser.parse_args()
    cases = [json.loads(line) for line in (ROOT / 'tests/eval/teacher_cases.jsonl').read_text(encoding='utf-8').splitlines()]
    cases = [c for c in cases if not args.only or c['id'] in args.only]
    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out / f"{time.strftime('%Y%m%d-%H%M%S')}-{args.mode}.jsonl"
    service = TaskService(ROOT, Path(tempfile.mkdtemp()) / 'teacher.sqlite')
    passed = 0
    for case in cases:
        start = time.monotonic()
        try:
            run = run_case(service, case, args.mode)
            errors = assess(case, run)
        except Exception as exc:  # one broken case must not hide the others
            run, errors = dict(error=f'{type(exc).__name__}: {exc}'), [f'{type(exc).__name__}: {exc}']
        passed += not errors
        row = dict(id=case['id'], category=case['category'], passed=not errors, errors=errors,
                   seconds=round(time.monotonic() - start, 1), run=run)
        with open(out, 'a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
        print(f"{case['id']:<12} {'PASS' if not errors else 'FAIL'} {row['seconds']:>6}s {'; '.join(errors)[:300]}", flush=True)
    print(f'{passed}/{len(cases)} passed -> {out}', flush=True)


if __name__ == '__main__':
    main()
