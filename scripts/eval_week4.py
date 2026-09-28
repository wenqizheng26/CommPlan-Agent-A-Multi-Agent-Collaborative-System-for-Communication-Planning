"""Week-4 checks on the real local model: drafts from manuals, and swap follow-ups.

Runs on a temporary copy of the knowledge folders, so drafts and approvals never reach the
repository. Each run writes one new JSON file and never overwrites evidence.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from planning.agents.extraction import extract
from planning.agents.role_model import LocalRoleSelector
from planning.knowledge.drafts import DraftStore
from planning.services.entity_followup import replace_entities
from planning.services.model_status import probe_model
from planning.workflow.task_service import TaskService

TASK = '按自由空间基准，A 站到 B 站用 XX-100 电台、2 GHz，要留 10 dB 余量，能通吗？'
XX300 = dict(names=['XX-300'], model='XX-300', tx_power_dbm=40, antenna_gain_dbi=6, rx_sensitivity_dbm=-97,
             band_ghz=[1.0, 3.0])
XX100 = dict(names=['XX-100'], model='XX-100', tx_power_dbm=37, antenna_gain_dbi=5, rx_sensitivity_dbm=-92,
             band_ghz=[1.4, 2.7])
# (case, kind, chunk ids, expected)
EXTRACTIONS = [
    ('xx300_device', 'device', ['doc:sim-xx300:s2-1'], dict(values=XX300, approvable=True)),
    ('xx300_eirp_formula', 'formula', ['doc:sim-xx300:s3-1'], dict(example=True, approvable=True)),
    ('xx300_preamble_no_device', 'device', ['doc:sim-xx300:s0-1'], dict(found=False)),
    ('xx300_table_no_formula', 'formula', ['doc:sim-xx300:s2-1'], dict(found=False)),
    ('xx100_device_already_in_library', 'device', ['doc:sim-xx100:s2-1'], dict(values=XX100, approvable=False)),
]
# (message, expected): ('apply', [(field, before, after)]), ('ask', part of the question) or ('none', None)
FOLLOWUPS = [
    ('换 XX-200 呢', ('apply', [('device', 'XX-100', 'XX-200')])),
    ('改用 XX-200 吧', ('apply', [('device', 'XX-100', 'XX-200')])),
    ('换成 XX-200 试试', ('apply', [('device', 'XX-100', 'XX-200')])),
    ('B 站换成 C 站呢', ('apply', [('site', 'B站', 'C站')])),
    ('A 站换成 C 站呢', ('apply', [('site', 'A站', 'C站')])),
    ('把 B 站改成 F 站', ('apply', [('site', 'B站', 'F站')])),
    ('换 XX-200 电台，B 站换成 C 站', ('apply', [('device', 'XX-100', 'XX-200'), ('site', 'B站', 'C站')])),
    ('换成 C 站呢', ('ask', '要把哪一端换成 C站')),
    ('要不换 XX-200 呢', ('ask', '说法不确定')),
    ('换 XX-200 还是不换', ('ask', '说法不确定')),
    ('换 XX-100 呢', ('ask', '用的已经是 XX-100')),
    ('换 XX-999 呢', ('ask', '库里没有 XX-999')),
    ('XX-200 的灵敏度是多少？', ('none', None)),
    ('频率改为 2.4 GHz', ('none', None)),
]
BEFORE_REVIEW = [('换 XX-300 呢', ('ask', '只有未审核的草稿'))]
AFTER_REVIEW = [('换 XX-300 呢', ('apply', [('device', 'XX-100', 'XX-300')]))]


def command(action, state=None, **extra):
    return dict(action=action, task_id=state['task_id'] if state else str(uuid.uuid4()), event_id=str(uuid.uuid4()),
                expected_revision=state['revision'] if state else 0,
                expected_state_version=state['state_version'] if state else 0, **extra)


def copy_app(target):
    for folder in ('knowledge/documents', 'knowledge/facts', 'config'):
        shutil.copytree(ROOT / folder, target / folder)
    for name in ('knowledge/formulas.json', 'runtime_config.json'):
        shutil.copy(ROOT / name, target / name)


def margin(state):
    outputs = (state.get('final_report') or {}).get('outputs') or [{}]
    return outputs[0].get('value')


def run_extraction(root, selector, case):
    name, kind, chunks, want = case
    start = time.monotonic()
    result = extract(root, kind, chunks, selector)
    row = dict(case=name, kind=kind, chunks=chunks, seconds=round(time.monotonic() - start, 2), mode=result['mode'],
               attempts=result['attempts'], message=result['message'], diagnostics=result['diagnostics'])
    draft, errors = result['draft'], []
    if want.get('found') is False:
        if draft is not None:
            errors.append('unexpected_draft')
    elif draft is None:
        errors.append('no_draft')
    else:
        record = draft['record']
        row.update(draft_id=draft['id'], record=record, approvable=draft['approvable'], problems=draft['problems'],
                   checks={c['field']: c['status'] for c in draft['checks']}, example=draft.get('example'))
        for field, value in want.get('values', {}).items():
            if record.get(field) != value:
                errors.append('value:' + field)
        if any(c['status'] != 'match' for c in draft['checks'] if c['field'] in want.get('values', {})):
            errors.append('quotes')
        if want.get('example') and not (draft.get('example') or {}).get('passed'):
            errors.append('example')
        if draft['approvable'] != want['approvable']:
            errors.append('approvable')
    row.update(errors=errors, passed=not errors)
    return row, draft


def run_followup(root, state, selector, message, want):
    start = time.monotonic()
    result = replace_entities(state, message, str(uuid.uuid4()), root, selector=selector)
    seconds = round(time.monotonic() - start, 2)
    if result is None:
        got, turn = ('none', None), {}
    else:
        turn = result[1]['turns'][-1]
        got = (('apply', [(c['field'], c['before'], c['after']) for c in turn['changes']]) if turn['applied']
               else ('ask', turn['questions'][0]))
    kind, detail = want
    passed = got[0] == kind and (got[1] == detail if kind == 'apply' else kind == 'none' or detail in got[1])
    return dict(message=message, expected=[kind, detail], got=list(got), passed=passed, seconds=seconds,
                mode=turn.get('mode'), reading=turn.get('reading'), diagnostics=turn.get('diagnostics', []))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--model', default='qwen35-9b-q4', help='registered chat model for every role')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output already exists; retain earlier evidence')
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp) / 'app'
        copy_app(root)
        service = TaskService(root, Path(temp) / 'tasks.sqlite')
        model = service.registry.models[args.model]
        live = probe_model(model['endpoint'], model['alias'])
        if live['status'] != 'ready':
            raise RuntimeError('EVAL_MODEL_NOT_READY: ' + str(live))
        saved = service.settings.get()
        settings = saved['settings']
        settings['chat']['default'] = args.model
        service.settings.put(settings, saved['version'])
        _, bindings, _ = service.run_settings('llm')
        result = dict(source_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                      source_dirty=bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()),
                      model=args.model, model_revision=model.get('revision'), live=live,
                      started_at=time.strftime('%Y-%m-%dT%H:%M:%S%z'), extraction=[], followups=[])

        drafts = {}
        for case in EXTRACTIONS:
            row, draft = run_extraction(root, LocalRoleSelector(bindings['requirements']), case)
            drafts[case[0]] = draft
            result['extraction'].append(row)
            print(json.dumps({k: row[k] for k in ('case', 'passed', 'seconds', 'message')}, ensure_ascii=False), flush=True)

        start = time.monotonic()
        base = service.apply(command('create', input=dict(raw_text=TASK, manual_parameters={}, condition=None, target=None),
                                     mode='llm'))['state']
        result['base_task'] = dict(status=base['status'], seconds=round(time.monotonic() - start, 2),
                                   entities=[dict(kind=e['kind'], mention=e['mention'])
                                             for e in (base.get('report') or {}).get('entities') or []])
        selector = LocalRoleSelector(bindings['supplement'])
        for message, want in FOLLOWUPS + BEFORE_REVIEW:
            row = run_followup(root, base, selector, message, want)
            result['followups'].append(dict(row, stage='before_review'))
            print(json.dumps({k: row[k] for k in ('message', 'passed', 'got')}, ensure_ascii=False), flush=True)
        draft = drafts['xx300_device']
        if draft is not None:
            DraftStore(root).review(draft['id'], '评测脚本', draft['content_hash'], 'approve')
            for message, want in AFTER_REVIEW:
                row = run_followup(root, base, selector, message, want)
                result['followups'].append(dict(row, stage='after_review'))
                print(json.dumps({k: row[k] for k in ('message', 'passed', 'got')}, ensure_ascii=False), flush=True)

        # One saved chain: confirm, swap the radio, confirm the new version.
        chain, state = [], base
        for action, extra in (('confirm', lambda s: dict(review_hash=s['review']['review_hash'])),
                              ('supplement', lambda s: dict(message='换 XX-200 呢', mode='llm')),
                              ('confirm', lambda s: dict(review_hash=s['review']['review_hash']))):
            start = time.monotonic()
            state = service.apply(command(action, state, **extra(state)))['state']
            chain.append(dict(action=action, status=state['status'], revision=state['revision'],
                              seconds=round(time.monotonic() - start, 2), margin_db=margin(state)))
        first, last = chain[0]['margin_db'], chain[-1]['margin_db']
        swap = state['conversation']['turns'][-1]
        result['chain'] = dict(steps=chain, swap=swap.get('changes'), passed=(
            chain[0]['status'] == chain[-1]['status'] == 'COMPLETED' and swap.get('applied') is True
            and first is not None and last is not None and abs(first - 5.9334) < 0.01 and abs(last - 20.9334) < 0.01))

        rows = result['extraction'] + result['followups']
        called = [r for r in result['followups'] if r['mode'] == 'llm']
        result['summary'] = dict(
            extraction=f"{sum(r['passed'] for r in result['extraction'])}/{len(result['extraction'])}",
            followups=f"{sum(r['passed'] for r in result['followups'])}/{len(result['followups'])}",
            model_called=len(called), model_agreed=sum(r['got'][0] == 'apply' for r in called),
            chain=result['chain']['passed'])
        result['passed'] = all(r['passed'] for r in rows) and result['chain']['passed']
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result['summary'], ensure_ascii=False))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
