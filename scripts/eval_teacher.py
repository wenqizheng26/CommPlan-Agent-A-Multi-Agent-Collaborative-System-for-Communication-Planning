"""Evaluate fixed teacher/held-out cases; record functional and model evidence separately.

Adopt suggestions together only when every open issue has a default. The original
observations remain separate. Results do not establish browser/release acceptance.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import platform
import subprocess
import sys
import time
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))
from planning.build_info import build_fingerprint
from planning.workflow.task_service import TaskService

ROW = ('rx_sensitivity_dbm', 'path_loss_db', 'rx_power_dbm', 'link_margin_db')
EXPECTED = {'first_stop', 'parsed', 'nodes', 'service', 'missing', 'after_defaults',
            'results', 'tolerance', 'ask', 'margin_diff_db', 'recommend'}
OBSERVATIONS = {'status', 'parsed', 'nodes', 'service', 'missing', 'issues', 'plan', 'tool', 'plan_origin'}


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def _package_identity(cache, full):
    """Reuse the ZIP contract for unpacked members; hash fully before/after a run."""
    from build_planning_release import permitted, regular_file, source_files
    from validate_planning_release import inspect_archive

    manifest_path = ROOT / 'MANIFEST.json'
    manifest = strict_json(manifest_path.read_text(encoding='utf-8'))
    if type(manifest) is not dict or type(manifest.get('files')) is not dict:
        raise ValueError('invalid unpacked package manifest')
    names = [*manifest['files'], 'MANIFEST.json']
    paths = {}
    for name in names:
        if not permitted(name):
            raise ValueError(f'unsafe unpacked package member: {name}')
        path = ROOT / name
        if not regular_file(path) or any(p.is_symlink() or p.is_junction() for p in (path, *path.parents) if p != ROOT):
            raise ValueError(f'non-regular unpacked package member: {name}')
        paths[name] = path
    source_files(ROOT)  # Reject added executable product inputs outside the manifest.
    signature = {name: (p.stat().st_size, p.stat().st_mtime_ns, p.stat().st_ctime_ns)
                 for name, p in paths.items()}
    if full or cache.get('signature') != signature:
        class DirectoryPackage:
            def infolist(self):
                rows = []
                for name, path in paths.items():
                    row = zipfile.ZipInfo(name)
                    row.file_size = path.stat().st_size
                    rows.append(row)
                return rows

            def read(self, name):
                return paths[name].read_bytes()

        info = inspect_archive(DirectoryPackage())
        fingerprint = build_fingerprint(ROOT)
        if fingerprint != info['build_fingerprint']:
            raise ValueError('unpacked package build fingerprint mismatch')
        cache.update(signature=signature, identity=dict(source_kind='verified-source-package',
                     source_commit=info['source_commit'], dirty=info['source_dirty'],
                     dirty_entries=None, build_fingerprint=fingerprint,
                     manifest_sha256=sha256(manifest_path),
                     source_inputs_sha256=info['source_inputs_sha256'],
                     source_content_mode=info.get('source_content_mode', 'legacy-worktree-bytes')))
    return dict(cache['identity'])


def source_identity(cases_path, *, package_cache=None, full=True):
    """Observe Git and input bytes without changing Git."""
    def git(*args):
        return subprocess.check_output(['git', '--no-optional-locks', '-C', str(ROOT), *args])
    if (ROOT / '.git').exists():
        dirty = git('status', '--porcelain=v1', '-z', '--untracked-files=all').decode('utf-8')
        identity = dict(source_kind='git-worktree', source_commit=git('rev-parse', 'HEAD').decode('ascii').strip(),
                        dirty=bool(dirty), dirty_entries=dirty.split('\0')[:-1],
                        build_fingerprint=build_fingerprint(ROOT))
    else:
        identity = _package_identity({} if package_cache is None else package_cache, full)
    return dict(identity, runner_sha256=sha256(ROOT / 'scripts/eval_teacher.py'),
                cases_sha256=sha256(cases_path), tools_sha256=sha256(ROOT / 'knowledge/tools.json'),
                registry_sha256=sha256(ROOT / 'config/models.json'),
                runtime_config_sha256=sha256(ROOT / 'runtime_config.json'))


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'duplicate JSON key: {key}')
        result[key] = value
    return result


def strict_json(text):
    def invalid(value):
        raise ValueError(f'non-finite JSON number: {value}')
    return json.loads(text, object_pairs_hook=_object, parse_constant=invalid)


def numeric(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def close(a, b, tolerance):
    return numeric(a) and numeric(b) and numeric(tolerance) and tolerance >= 0 and abs(a - b) <= tolerance


def _strings(value, name):
    if type(value) is not list or any(type(item) is not str for item in value):
        raise ValueError(f'{name} must be a list of strings')


def _observation_schema(value, name):
    if type(value) is not dict or set(value) - OBSERVATIONS:
        raise ValueError(f'{name}: unsupported observation fields')
    for key, item in value.items():
        if key == 'parsed':
            if type(item) is not dict:
                raise ValueError(f'{name}.parsed must be an object')
            for field, number in item.items():
                if field == 'modulations':
                    _strings(number, f'{name}.parsed.modulations')
                elif not numeric(number):
                    raise ValueError(f'{name}.parsed.{field} must be a finite number')
        elif key in {'nodes', 'missing', 'issues', 'plan'}:
            _strings(item, f'{name}.{key}')
        elif item is not None and type(item) is not str:
            raise ValueError(f'{name}.{key} must be a string or null')


def default_expectation(value):
    # Frozen teacher JSONL uses a flat parsed-values object here. Also support
    # explicit observations in a fixture without rewriting the frozen input.
    if type(value) is dict and not (set(value) & OBSERVATIONS):
        return dict(parsed=value)
    return value


def load_cases(path, only=None):
    """Validate every declared assertion and selection before any output/service."""
    raw = Path(path).read_bytes()
    cases, seen = [], set()
    for line_no, line in enumerate(raw.decode('utf-8-sig').splitlines(), 1):
        if not line.strip():
            continue
        case = strict_json(line)
        if type(case) is not dict or any(type(case.get(k)) is not str or not case[k].strip()
                                         for k in ('id', 'category', 'text')):
            raise ValueError(f'line {line_no}: nonempty id/category/text required')
        if case['id'] in seen:
            raise ValueError(f'duplicate case id: {case["id"]}')
        seen.add(case['id'])
        want = case.get('expected')
        if type(want) is not dict or set(want) - EXPECTED or type(want.get('first_stop')) is not str:
            raise ValueError(f'{case["id"]}: unsupported or missing expected fields')
        if not numeric(want.get('tolerance', 1e-6)) or want.get('tolerance', 1e-6) < 0:
            raise ValueError(f'{case["id"]}: invalid tolerance')
        _observation_schema({k: v for k, v in want.items() if k in OBSERVATIONS}, case['id'])
        if 'ask' in want:
            _strings(want['ask'], f'{case["id"]}.ask')
        if 'after_defaults' in want:
            _observation_schema(default_expectation(want['after_defaults']), f'{case["id"]}.after_defaults')
        if 'results' in want:
            if type(want['results']) is not list:
                raise ValueError(f'{case["id"]}.results must be a list')
            for row in want['results']:
                if (type(row) is not dict or set(row) != {'modulation', 'meets', *ROW}
                        or type(row['modulation']) is not str or type(row['meets']) is not bool
                        or any(not numeric(row[k]) for k in ROW)):
                    raise ValueError(f'{case["id"]}: invalid result declaration')
        if 'margin_diff_db' in want and not numeric(want['margin_diff_db']):
            raise ValueError(f'{case["id"]}: invalid margin_diff_db')
        if 'recommend' in want and type(want['recommend']) is not str:
            raise ValueError(f'{case["id"]}: invalid recommend')
        cases.append(case)
    if not cases:
        raise ValueError('case file is empty')
    if only is not None:
        if not only or any(not item.strip() for item in only) or len(set(only)) != len(only):
            raise ValueError('--only must contain nonempty, unique case ids')
        unknown = set(only) - seen
        if unknown:
            raise ValueError(f'unknown case ids: {sorted(unknown)}')
        cases = [case for case in cases if case['id'] in only]
    return cases, hashlib.sha256(raw).hexdigest()


def command(action, state=None, **extra):
    return dict(action=action, task_id=state['task_id'] if state else str(uuid.uuid4()), event_id=str(uuid.uuid4()),
                expected_revision=state['revision'] if state else 0,
                expected_state_version=state['state_version'] if state else 0, **extra)


def observed(report):
    params = {p['canonical_name']: p['value'] for p in report.get('parameters_proposal', []) if p['value'] is not None}
    diagnostics = report.get('diagnostics', [])
    codes = {d['code']: d.get('details', {}) for d in diagnostics}
    parsed = {k: v for k, v in params.items() if k != 'frequency_ghz'}
    if numeric(params.get('frequency_ghz')):
        parsed['frequency_mhz'] = params['frequency_ghz'] * 1000
    modulations = list((codes.get('LINK_TOOL') or {}).get('modulations', []))
    modulations += [d['details']['mention'] for d in diagnostics if d['code'] == 'MODULATION_UNKNOWN']
    if modulations:
        parsed['modulations'] = modulations
    asked_modulation = bool({'MODULATION_NEEDED', 'MODULATION_UNKNOWN'} & codes.keys())
    missing = [m for m in report.get('missing_parameters', []) if not (m == 'rx_threshold_dbm' and asked_modulation)]
    if 'MODULATION_NEEDED' in codes:
        missing.append('modulation')
    plan = report.get('calculation_plan_proposal') or {}
    return dict(parsed=parsed, nodes=[e['mention'] for e in report.get('entities', []) if e['kind'] == 'site'],
                service=(report.get('service') or {}).get('label'), missing=missing,
                plan=plan.get('selected_model'), tool=plan.get('tool'), plan_origin=plan.get('origin'))


def _model_calls(service, task_id):
    """Read all original calls, without the UI's truncation or malformed-line skip."""
    path = service.model_calls.path
    if not path.is_file():
        return []
    rows = [strict_json(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]
    if any(type(row) is not dict for row in rows):
        raise ValueError('invalid original model-call record')
    return [row for row in rows if row.get('task_id') == task_id]


def _asset(service, binding, cache):
    model_id = binding.get('model_id')
    model = service.registry.models.get(model_id, {})
    relative = model.get('weights') or model.get('path')
    path = (Path(service.root) / relative).resolve() if relative else None
    if model_id not in cache:
        cache[model_id] = dict(model_id=model_id, alias=model.get('alias'), endpoint=model.get('endpoint'),
                              configured_runtime=model.get('runtime'), runtime_options=model.get('runtime_options'),
                              served_process_identity='unknown',
                              revision=model.get('revision'), configured_path=relative,
                              resolved_path=str(path) if path else None,
                              sha256=sha256(path) if path and path.is_file() else None,
                              status='hashed-local-file' if path and path.is_file() else 'unknown')
    return cache[model_id]


def model_evidence(service, state, c, calls, events, asset_cache):
    """Modes cannot establish a call: pair transport, accepted activity and bindings."""
    settings = state.get('run_settings') or {}
    phase = 'requirements' if c['action'] in {'create', 'answer'} else 'calculation'
    bindings = (settings.get(phase) or {}).get('chat') or {}
    report = state.get('report') or {}
    role_results = dict(requirements=dict(mode=(report.get('component_modes') or {}).get('interpretation')),
                        compute_agent=report.get('planning_role') or {},
                        validator_agent=(state.get('review_assessment') or {}).get('role') or {})
    rows = []
    for role in ('requirements', 'compute_agent', 'validator_agent'):
        role_calls = [call for call in calls if call.get('agent') == role]
        accepted_events = [event for event in events if event.get('node') == 'llm' and event.get('phase') == 'completed'
                           and (event.get('details') or {}).get('caller') == role]
        result = role_results[role]
        binding = bindings.get(role) or {}
        asset = _asset(service, binding, asset_cache) if binding and role_calls else None
        # Intent declares the accepted attempt in MODEL_CALL. The other roles
        # record it in completed activity. Transport-ok alone is insufficient.
        attempt, accepted = result.get('attempts'), []
        if role == 'requirements':
            accepted = [d.get('details', {}) for d in report.get('diagnostics', []) if d.get('code') == 'MODEL_CALL']
            attempt = accepted[-1].get('attempt') if accepted else None
        elif accepted_events:
            attempt = accepted_events[-1]['details'].get('attempt', attempt)
        chosen = role_calls[attempt - 1] if type(attempt) is int and 0 < attempt <= len(role_calls) else None
        completion = accepted_events[-1]['details'] if accepted_events else {}
        matched_event = bool(completion and binding and completion.get('model_id') == binding.get('model_id'))
        if role == 'requirements':
            # This role emits one completion after its retry loop, without an
            # attempt number. Its MODEL_CALL diagnostic supplies that number.
            matched_event = matched_event and len(accepted_events) == 1 and completion.get('mode') == 'llm'
        else:
            matched_event = matched_event and completion.get('attempt') == attempt
        matched_call = bool(chosen and chosen.get('status') == 'ok' and binding.get('alias')
                            and chosen.get('model') == chosen.get('served') == binding['alias'])
        accepted_llm = bool(result.get('mode') == 'llm' and matched_event and matched_call
                            and (role != 'requirements' or accepted))
        rows.append(dict(role=role, stage=c['action'], revision=state['revision'], task_id=state['task_id'],
                         event_id=c['event_id'], recorded_mode=result.get('mode'), binding=binding or None,
                         configured_asset=asset, call_ids=[call.get('call_id') for call in role_calls],
                         accepted_call_id=chosen.get('call_id') if accepted_llm else None,
                         accepted_llm=accepted_llm, accepted_details=accepted,
                         fallback=bool(role_calls and result.get('mode') not in {'llm', 'stub'}),
                         evidence_status='accepted-llm' if accepted_llm else ('unaccepted-calls' if role_calls else 'no-call'),
                         role_result=result))
    return rows


def run_case(service, case, mode, source_check=None, asset_cache=None):
    timings, stages, identity_checks = [], [], []
    asset_cache = {} if asset_cache is None else asset_cache

    def apply(c):
        if source_check:
            identity_checks.append(source_check())
        start = time.monotonic()
        state = service.apply(c)['state']
        timings.append(dict(action=c['action'], seconds=round(time.monotonic() - start, 2)))
        events = [event for event in service.activity.events(c['task_id']) if event.get('event_id') == c['event_id']]
        calls = [call for call in _model_calls(service, c['task_id']) if call.get('event_id') == c['event_id']]
        revision = c['expected_revision'] + (c['action'] in {'edit', 'supplement', 'answer'})
        if any(row.get('task_id') != state['task_id'] or row.get('revision') != revision for row in events + calls):
            raise ValueError('observation task/revision mismatch')
        if source_check:
            identity_checks.append(source_check())
        stages.append(dict(stage=c['action'], event_id=c['event_id'], task_id=state['task_id'], revision=state['revision'],
                           status=state['status'], observation=observed(state['report']) if state.get('report') else {},
                           run_settings=state.get('run_settings'), retrieval=state.get('retrieval'),
                           report=state.get('report'), calculation_role=state.get('calculation_role'),
                           review_assessment=state.get('review_assessment'), activity=events, model_calls=calls,
                           model_evidence=model_evidence(service, state, c, calls, events, asset_cache)))
        return state
    s = apply(command('create', input=dict(raw_text=case['text'], manual_parameters={}, condition=None, target=None), mode=mode))
    first = dict(status=s['status'], **(observed(s['report']) if s.get('report') else {}),
                 issues=[i['field'] for i in s.get('input_issues', [])], suggestions=(s.get('report') or {}).get('suggestions'))
    adopted, after_defaults = None, None
    issues = s.get('input_issues', [])
    if s['status'] == 'AWAITING_INPUT' and issues and all(i.get('suggestion') and 'value' in i['suggestion'] for i in issues):
        adopted = {i['field']: i['suggestion']['value'] for i in issues}
        s = apply(command('answer', s, answers={i['id']: i['suggestion']['value'] for i in issues}, mode=mode))
        after_defaults = dict(status=s['status'], **(observed(s['report']) if s.get('report') else {}),
                              issues=[i['field'] for i in s.get('input_issues', [])])
    if s['status'] == 'AWAITING_CONFIRMATION':
        s = apply(command('confirm', s, review_hash=s['review']['review_hash']))
    final = s.get('final_report') or {}
    return dict(first=first, after_defaults=after_defaults, adopted=adopted, status=s['status'], failure=s.get('failure'),
                timings=timings, stages=stages, source_checks=identity_checks, tool_calls=final.get('tool_calls'),
                comparison=final.get('comparison'), conclusion=final.get('conclusion'),
                answer=(final.get('answer') or {}).get('text'), review=(final.get('review') or {}).get('decision'),
                modes=final.get('component_modes'), task_id=s['task_id'])


def assess(case, run):
    want, got, errors = case['expected'], run['first'], []
    tolerance = want.get('tolerance', 1e-6)

    def check(ok, message):
        if not ok:
            errors.append(message)

    def observation(expected, actual, label):
        if actual is None:
            check(False, f'{label}: absent')
            return
        for key, value in expected.items():
            found = actual.get(key)
            if key == 'parsed':
                for field, number in value.items():
                    parsed = (found or {}).get(field)
                    check(parsed == number if field == 'modulations' else close(parsed, number, tolerance),
                          f'{label}.parsed {field} {parsed} != {number}')
            elif key in {'missing', 'issues'}:
                check(type(found) is list and sorted(found) == sorted(value), f'{label}.{key} {found} != {value}')
            else:
                check(found == value, f'{label}.{key} {found} != {value}')
    check(got.get('status') == want['first_stop'], f"first stop {got.get('status')} != {want['first_stop']}")
    if any(stage.get('stage') == 'confirm' for stage in run.get('stages', [])):
        check(run.get('status') == 'COMPLETED',
              f"execution failed: {(run.get('failure') or {}).get('code', run.get('status'))}")
    observation({k: v for k, v in want.items() if k in OBSERVATIONS}, got, 'first')
    if 'after_defaults' in want:
        observation(default_expectation(want['after_defaults']), run.get('after_defaults'), 'after_defaults')
    for field in want.get('ask', []):
        asked = {'frequency_mhz': 'frequency_ghz'}.get(field, field)
        check(asked in got.get('issues', []), f"asks {got.get('issues')} lacks {field}")
    if 'results' in want:
        calls = run.get('tool_calls') or []
        if want['results']:
            check(run['status'] == 'COMPLETED', f"final {run['status']} {(run.get('failure') or {}).get('code')}")
            check((run.get('modes') or {}).get('calculation') == 'deterministic', 'calculation is not deterministic')
        check([c.get('label') for c in calls] == [r['modulation'] for r in want['results']], 'result count/modulations differ')
        for call, row in zip(calls, want['results']):
            result = call.get('result') or {}
            for key in ROW:
                check(close(result.get(key), row[key], tolerance), f"{row['modulation']} {key} {result.get(key)} != {row[key]}")
            check(type(result.get('meets')) is bool and result['meets'] == row['meets'], f"{row['modulation']} meets differs")
    comparison = run.get('comparison') or {}
    if 'margin_diff_db' in want:
        check(close(comparison.get('margin_diff_db'), want['margin_diff_db'], tolerance), f"spread {comparison.get('margin_diff_db')}")
    if 'recommend' in want:
        check(comparison.get('recommend') == want['recommend'], f"recommend {comparison.get('recommend')} != {want['recommend']}")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['llm', 'deterministic'], default='deterministic')
    parser.add_argument('--cases', type=Path, default=ROOT / 'tests/eval/teacher_cases.jsonl')
    parser.add_argument('--only', nargs='*', help='nonempty unique case ids')
    parser.add_argument('--out', type=Path, default=ROOT / 'outputs/teacher-eval')
    args = parser.parse_args(argv)
    try:
        cases, cases_hash = load_cases(args.cases, args.only)
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ') + '-' + args.mode + '-' + uuid.uuid4().hex
    directory = args.out / run_id
    directory.mkdir(parents=True, exist_ok=False)
    out, metadata_path, db = directory / 'results.jsonl', directory / 'run.json', directory / 'teacher.sqlite'
    metadata = dict(schema_version=1, run_id=run_id, mode=args.mode, cases_path=str(args.cases.resolve()),
                    cases_sha256=cases_hash, selected_ids=[case['id'] for case in cases], task_database=str(db.resolve()),
                    results_path=str(out.resolve()), source_mid=[], source_checks=[], configured_assets=[],
                    runner_environment=dict(python_version=platform.python_version(), executable=sys.executable,
                                            platform=platform.platform()),
                    limitations=['Functional cases are not browser/release/clean-environment acceptance.',
                                 'Accepted calls use original transport/activity evidence; recorded modes are not calls.',
                                 'Registry aliases and local weight hashes do not prove server-process loaded weights.',
                                 'Held-out results are advisory, not M1 acceptance criteria.'])
    passed, rows, assets, fatal = 0, [], {}, None
    package_cache = {}

    def identity(full=False):
        return source_identity(args.cases, package_cache=package_cache, full=full)

    def save():
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')

    def stable():
        current = identity()
        metadata['source_checks'].append(current)
        if current != metadata['source_before']:
            raise RuntimeError('EVAL_SOURCE_CHANGED: SHA/dirty/fingerprint/input/runner/tools changed')
        return current
    try:
        before = identity(full=True)
        metadata['source_before'] = before
        if before['cases_sha256'] != cases_hash:
            raise RuntimeError('EVAL_SOURCE_CHANGED: case file changed during loading')
        save()
        service = TaskService(ROOT, db)
        for case in cases:
            start = time.monotonic()
            try:
                run = run_case(service, case, args.mode, source_check=stable, asset_cache=assets)
                errors = assess(case, run)
            except Exception as exc:  # retain failed DB/logs and attempt the remaining cases
                run, errors = dict(error=f'{type(exc).__name__}: {exc}'), [f'{type(exc).__name__}: {exc}']
            passed += not errors
            row = dict(id=case['id'], category=case['category'], passed=not errors, errors=errors,
                       seconds=round(time.monotonic() - start, 1), run=run)
            rows.append(row)
            with out.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n')
            metadata['source_mid'].append(dict(case_id=case['id'], identity=identity()))
            metadata['configured_assets'] = list(assets.values())
            save()
            print(f"{case['id']:<12} {'PASS' if not errors else 'FAIL'} {row['seconds']:>6}s {'; '.join(errors)[:300]}", flush=True)
    except Exception as exc:
        fatal = f'{type(exc).__name__}: {exc}'
    try:
        metadata['source_after'] = identity(full=True)
        source_stable = metadata.get('source_before') == metadata['source_after'] and all(
            item['identity'] == metadata.get('source_before') for item in metadata['source_mid']) and all(
            item == metadata.get('source_before') for item in metadata['source_checks'])
    except Exception as exc:
        source_stable = False
        metadata['source_after_error'] = f'{type(exc).__name__}: {exc}'
    categories = {}
    for category in sorted({case['category'] for case in cases}):
        subset = [row for row in rows if row['category'] == category]
        categories[category] = dict(total=sum(case['category'] == category for case in cases),
                                    completed=len(subset), passed=sum(row['passed'] for row in subset),
                                    advisory=category == 'heldout')
    evidence = Counter(item['evidence_status'] for row in rows for stage in row['run'].get('stages', [])
                       for item in stage['model_evidence'])
    ok = fatal is None and source_stable and passed == len(cases)
    metadata.update(fatal_error=fatal, configured_assets=list(assets.values()),
                    summary=dict(total=len(cases), completed=len(rows), functional_passed=passed,
                                 source_stable=source_stable, categories=categories, model_evidence=dict(evidence),
                                 evaluation_passed=ok, acceptance_status='not-assessed'))
    save()
    print(f'{passed}/{len(cases)} functional passed; source stable={source_stable} -> {out}', flush=True)
    if fatal:
        print(fatal, file=sys.stderr, flush=True)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
