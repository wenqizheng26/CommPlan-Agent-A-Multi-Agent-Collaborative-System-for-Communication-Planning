"""Runner fixtures only: no real model, browser or shared TaskService."""
import copy
from contextlib import redirect_stderr, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from scripts import eval_teacher as runner


def case(case_id='fixture', **expected):
    return dict(id=case_id, category='fixture', text='fixture input',
                expected=dict(first_stop='AWAITING_CONFIRMATION', **expected))


def report(service=None, distance=10, nodes=()):
    value = dict(parameters_proposal=[dict(canonical_name='distance_km', value=distance),
                                     dict(canonical_name='frequency_ghz', value=5.8)],
                 diagnostics=[], missing_parameters=[],
                 entities=[dict(kind='site', mention=name) for name in nodes],
                 calculation_plan_proposal=dict(selected_model=['fspl_mhz'], tool='fspl_mhz', origin='program'),
                 component_modes=dict(interpretation='deterministic'), planning_role=dict(mode='deterministic'))
    if service is not None:
        value['service'] = dict(label=service, kind='video', mention=service)
    return value


def state(status='AWAITING_CONFIRMATION', **extra):
    return dict(status=status, revision=0, state_version=1, report=report(), input_issues=[],
                review=dict(review_hash='fixture-review'), run_settings={}, **extra)


class FakeService:
    """Mimic the public observation interface, retaining fixture files on disk."""
    def __init__(self, root, db, states=None, calls=None, events=None):
        self.root = Path(db).parent
        self.db = Path(db)
        self.db.write_bytes(b'fixture database')
        self.states = states or [state(), state('COMPLETED', final_report=dict(component_modes=dict(calculation='deterministic')))]
        self.commands, self.events_list = [], []
        self.calls_input, self.events_input = calls or [], events or []
        self.model_calls = SimpleNamespace(path=Path(str(db) + '.model-calls.jsonl'))
        self.activity = SimpleNamespace(events=lambda task_id: copy.deepcopy(self.events_list))
        weights = self.root / 'fixture.gguf'
        weights.write_bytes(b'fixture weights, not a model')
        self.registry = SimpleNamespace(models={'fixture-model': dict(weights='fixture.gguf', alias='fixture-alias',
                                                                       endpoint='http://127.0.0.1:1', revision='fixture-revision')})

    def apply(self, c):
        self.commands.append(copy.deepcopy(c))
        index = len(self.commands) - 1
        if isinstance(self.states[index], Exception):
            raise self.states[index]
        s = copy.deepcopy(self.states[index])
        s['task_id'] = c['task_id']
        s['revision'] = c['expected_revision'] + (c['action'] == 'answer')
        s['state_version'] = index + 1
        context = dict(task_id=c['task_id'], event_id=c['event_id'], revision=s['revision'], action=c['action'])
        for row in self.calls_input:
            with self.model_calls.path.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(dict(context, **row)) + '\n')
        self.events_list.extend(dict(context, **row) for row in self.events_input)
        return dict(state=s)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        # Any accidental connection from a fixture is a test failure.
        self.addCleanup(patch.stopall)
        patch('socket.create_connection', side_effect=AssertionError('fixture attempted network')).start()
        patch('urllib.request.urlopen', side_effect=AssertionError('fixture attempted network')).start()

    def write_cases(self, rows):
        path = self.base / 'cases.jsonl'
        path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')
        return path

    def invoke(self, rows, *, states=None, only=None, identity=None, mode=None):
        path = self.write_cases(rows)
        out = self.base / 'out'
        existing = set(out.iterdir()) if out.exists() else set()
        fixed = dict(source_commit='a' * 40, dirty=True, dirty_entries=[' M scripts/eval_teacher.py'],
                     build_fingerprint='b' * 20, cases_sha256=runner.sha256(path), runner_sha256='c' * 64,
                     tools_sha256='d' * 64, registry_sha256='e' * 64, runtime_config_sha256='f' * 64)
        services = []

        def factory(root, db):
            value = FakeService(root, db, states)
            services.append(value)
            return value
        args = ['--cases', str(path), '--out', str(out)]
        if only is not None:
            args += ['--only', *only]
        if mode:
            args += ['--mode', mode]
        with patch.object(runner, 'TaskService', side_effect=factory), patch.object(
                runner, 'source_identity', side_effect=lambda path, **_: identity(path) if identity else copy.deepcopy(fixed)), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            code = runner.main(args)
        directory = next(path for path in out.iterdir() if path not in existing)
        metadata = json.loads((directory / 'run.json').read_text(encoding='utf-8'))
        records = [json.loads(line) for line in (directory / 'results.jsonl').read_text(encoding='utf-8').splitlines()] \
            if (directory / 'results.jsonl').exists() else []
        return code, metadata, records, services

    def test_default_and_external_cases_success_retains_unique_database(self):
        code, metadata, rows, services = self.invoke([case(nodes=[], parsed=dict(distance_km=10))])
        self.assertEqual(code, 0)
        self.assertEqual(metadata['mode'], 'deterministic')
        self.assertEqual(metadata['summary']['acceptance_status'], 'not-assessed')
        self.assertTrue(metadata['summary']['source_stable'])
        self.assertEqual(metadata['source_before'], metadata['source_after'])
        self.assertEqual(metadata['source_mid'][0]['identity'], metadata['source_before'])
        self.assertTrue(Path(metadata['task_database']).is_file())
        self.assertEqual(rows[0]['run']['task_id'], services[0].commands[0]['task_id'])
        self.assertEqual(rows[0]['run']['stages'][0]['observation']['plan_origin'], 'program')
        first_db = metadata['task_database']
        _, again, _, _ = self.invoke([case()])
        self.assertNotEqual(first_db, again['task_database'])

    def test_empty_unknown_and_duplicate_selection_fail_before_service_or_output(self):
        path = self.write_cases([case()])
        for selected in ([], ['unknown'], ['fixture', 'fixture'], ['']):
            with self.subTest(selected=selected), patch.object(runner, 'TaskService') as factory, \
                    redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                runner.main(['--cases', str(path), '--out', str(self.base / 'invalid'), '--only', *selected])
            self.assertEqual(caught.exception.code, 2)
            factory.assert_not_called()
            self.assertFalse((self.base / 'invalid').exists())

    def test_invalid_cases_fail_before_service_or_output(self):
        variants = [[], [case(), case()], [case(parsed=dict(distance_km=True))],
                    [case(parsed=dict(distance_km=10 ** 400))],
                    [case(tolerance=-1)], [case(unchecked_field=12)],
                    [case(after_defaults=dict(unchecked_field='unsupported'))]]
        for rows in variants:
            with self.subTest(rows=rows):
                path = self.write_cases(rows)
                with patch.object(runner, 'TaskService') as factory, redirect_stderr(io.StringIO()), \
                        self.assertRaises(SystemExit) as caught:
                    runner.main(['--cases', str(path), '--out', str(self.base / 'invalid')])
                self.assertEqual(caught.exception.code, 2)
                factory.assert_not_called()
                self.assertFalse((self.base / 'invalid').exists())

    def test_frozen_teacher_and_external_heldout_schemas_are_supported(self):
        cases, _ = runner.load_cases(runner.ROOT / 'tests/eval/teacher_cases.jsonl')
        self.assertEqual(len(cases), 20)
        selected, _ = runner.load_cases(runner.ROOT / 'tests/eval/teacher_cases.jsonl', ['teacher_02'])
        self.assertEqual([row['id'] for row in selected], ['teacher_02'])
        # An external corpus need not live in a sibling developer worktree.
        external = case('external', nodes=[], service=None)
        external['category'] = 'heldout'
        heldout, _ = runner.load_cases(self.write_cases([external]))
        self.assertEqual(heldout, [external])

    def test_unpacked_package_identity_without_git_and_tamper_rejected(self):
        import build_planning_release as builder
        import validate_planning_release as validator
        root = self.base / 'unpacked'
        root.mkdir()
        files = {name: b'fixture source\n' for name in builder.REQUIRED_FILES}
        for name, data in files.items():
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        fingerprint = runner.build_fingerprint(root)
        info = dict(version=builder.VERSION, source_commit='a' * 40, source_dirty=False,
                    source_uncommitted_inputs=[], source_modified_inputs=[], build_fingerprint=fingerprint,
                    source_content_mode='git-blobs', workspace_build_fingerprint=fingerprint,
                    source_core_autocrlf=None, source_inputs_sha256=builder.inputs_digest(files),
                    source_status_sha256=hashlib.sha256(b'').hexdigest(),
                    built_at_utc='2026-10-04T00:00:00+00:00', intended_platform='Windows, Python 3.12',
                    validation_record=builder.VALIDATION_RECORD, package_type=builder.PACKAGE_TYPE,
                    acceptance_status='NOT_EVALUATED')
        files.update({'VERSION': (builder.VERSION + '\n').encode(), 'BUILD_INFO.json': json.dumps(info).encode()})
        for name in ('VERSION', 'BUILD_INFO.json'):
            (root / name).write_bytes(files[name])
        (root / 'MANIFEST.json').write_text(json.dumps(dict(format=1, files={
            name: hashlib.sha256(data).hexdigest() for name, data in files.items()})), encoding='utf-8')
        cache = {}
        with patch.object(runner, 'ROOT', root), patch.object(runner.subprocess, 'check_output') as git, \
                patch.object(validator, 'inspect_archive', wraps=validator.inspect_archive) as inspect:
            first = runner.source_identity(root / 'tests/eval/teacher_cases.jsonl', package_cache=cache)
            self.assertEqual(first['source_kind'], 'verified-source-package')
            self.assertEqual(first['source_commit'], 'a' * 40)
            self.assertEqual(first['build_fingerprint'], fingerprint)
            self.assertIsNone(first['dirty_entries'])
            self.assertEqual(runner.source_identity(root / 'tests/eval/teacher_cases.jsonl',
                                                   package_cache=cache, full=False), first)
            self.assertEqual(inspect.call_count, 1)
            runner.source_identity(root / 'tests/eval/teacher_cases.jsonl', package_cache=cache)
            self.assertEqual(inspect.call_count, 2)
            git.assert_not_called()
            (root / 'planning/demo.py').write_text('tampered', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
                runner.source_identity(root / 'tests/eval/teacher_cases.jsonl', package_cache=cache, full=False)

    def test_nonfinite_and_duplicate_json_keys_are_rejected(self):
        for text in ('{"value":NaN}', '{"value":Infinity}', '{"value":1,"value":2}'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                runner.strict_json(text)
        self.assertFalse(runner.close(True, 1, 0))
        self.assertFalse(runner.close(float('inf'), float('inf'), 1))
        self.assertFalse(runner.close(1, 1, float('nan')))
        self.assertFalse(runner.numeric(10 ** 400))

    def test_service_and_empty_nodes_are_real_assertions(self):
        s = state()
        s['report'] = report(service='视频', nodes=['invented'])
        code, _, rows, _ = self.invoke([case(service='语音', nodes=[])], states=[s, state('COMPLETED')])
        self.assertEqual(code, 1)
        self.assertTrue(any('service' in error for error in rows[0]['errors']))
        self.assertTrue(any('nodes' in error for error in rows[0]['errors']))

    def test_original_awaiting_input_and_defaults_remain_separate(self):
        original = state('AWAITING_INPUT')
        original['report'] = report(service='视频', distance=None)
        original['input_issues'] = [dict(id='distance', field='distance_km', suggestion=dict(value=0))]
        defaults = state()
        defaults['report'] = report(service='视频', distance=0)
        c = dict(id='teacher_02', category='teacher', text='unchanged raw input', expected=dict(
            first_stop='AWAITING_INPUT', service='视频', nodes=[], parsed=dict(frequency_mhz=5800),
            after_defaults=dict(status='AWAITING_CONFIRMATION', service='视频', nodes=[], parsed=dict(distance_km=0))))
        code, _, rows, services = self.invoke([c], states=[original, defaults, state('COMPLETED')])
        self.assertEqual(code, 0)
        run = rows[0]['run']
        self.assertNotIn('distance_km', run['first']['parsed'])
        self.assertEqual(run['after_defaults']['parsed']['distance_km'], 0)
        self.assertEqual([s['stage'] for s in run['stages']], ['create', 'answer', 'confirm'])
        self.assertEqual([s['revision'] for s in run['stages']], [0, 1, 1])
        self.assertEqual(services[0].commands[0]['input']['raw_text'], 'unchanged raw input')
        self.assertEqual(services[0].commands[1]['answers'], {'distance': 0})

    def test_missing_after_defaults_and_undeclared_suggestions_do_not_pass(self):
        original = state('AWAITING_INPUT')
        original['input_issues'] = [dict(id='distance', field='distance_km', suggestion=None)]
        c = case(after_defaults=dict(parsed=dict(distance_km=10)))
        c['expected']['first_stop'] = 'AWAITING_INPUT'
        code, _, rows, services = self.invoke([c], states=[original])
        self.assertEqual(code, 1)
        self.assertEqual(len(services[0].commands), 1)
        self.assertIn('after_defaults: absent', rows[0]['errors'])

    def test_all_result_numbers_bool_count_and_recommendation_are_checked(self):
        expected_row = dict(modulation='QPSK', rx_sensitivity_dbm=-100, path_loss_db=127.7,
                            rx_power_dbm=-71.7, link_margin_db=28.3, meets=True)
        run = dict(first=dict(status='AWAITING_CONFIRMATION'), status='COMPLETED',
                   modes=dict(calculation='deterministic'),
                   tool_calls=[dict(label='QPSK', result={k: v for k, v in expected_row.items() if k != 'modulation'})],
                   comparison=dict(margin_diff_db=5, recommend='QPSK'))
        c = case(results=[expected_row], margin_diff_db=5, recommend='QPSK')
        self.assertEqual(runner.assess(c, run), [])
        for key in runner.ROW:
            for value in (True, float('inf'), run['tool_calls'][0]['result'][key] + 1):
                bad = copy.deepcopy(run)
                bad['tool_calls'][0]['result'][key] = value
                self.assertTrue(runner.assess(c, bad), (key, value))
        for key, value in (('meets', 1), ('meets', False)):
            bad = copy.deepcopy(run)
            bad['tool_calls'][0]['result'][key] = value
            self.assertTrue(runner.assess(c, bad))
        self.assertTrue(runner.assess(case(results=[]), run))
        self.assertTrue(runner.assess(case(recommend='16QAM'), run))
        run['modes']['calculation'] = 'llm'
        self.assertTrue(runner.assess(c, run))

    def test_case_failure_and_exception_return_one_and_keep_next_case(self):
        original = state('AWAITING_INPUT')
        code, metadata, rows, _ = self.invoke([case('bad'), case('good')], states=[RuntimeError('fixture failure'),
                                                                                 state(), state('COMPLETED')])
        self.assertEqual(code, 1)
        self.assertFalse(rows[0]['passed'])
        self.assertTrue(rows[1]['passed'])
        self.assertEqual(metadata['summary']['completed'], 2)
        self.assertTrue(Path(metadata['task_database']).exists())

    def test_failed_confirmation_is_not_hidden_by_first_stop_only_expectation(self):
        code, metadata, rows, _ = self.invoke([case()], states=[state(), state(
            'FAILED', failure=dict(code='CALCULATION_BUDGET_EXHAUSTED'))])
        self.assertEqual(code, 1)
        self.assertFalse(metadata['summary']['evaluation_passed'])
        self.assertIn('execution failed: CALCULATION_BUDGET_EXHAUSTED', rows[0]['errors'])

    def test_source_changes_fail_before_task_apply_and_after_run(self):
        c = case()
        path = self.write_cases([c])
        baseline = dict(cases_sha256=runner.sha256(path), source_commit='a', dirty=False, build_fingerprint='b')
        calls = [0]

        def changed(_):
            calls[0] += 1
            return dict(baseline, source_commit='changed' if calls[0] > 1 else 'a')
        code, metadata, rows, services = self.invoke([c], identity=changed)
        self.assertEqual(code, 1)
        self.assertFalse(metadata['summary']['source_stable'])
        self.assertEqual(services[0].commands, [])
        self.assertIn('EVAL_SOURCE_CHANGED', rows[0]['errors'][0])

    def test_cases_loaded_bytes_changing_before_run_are_rejected(self):
        code, metadata, rows, services = self.invoke([case()], identity=lambda _: dict(cases_sha256='wrong'))
        self.assertEqual(code, 1)
        self.assertEqual(services, [])
        self.assertEqual(rows, [])
        self.assertIn('during loading', metadata['fatal_error'])

    def test_plain_llm_mode_and_fallback_are_not_real_call_evidence(self):
        s = state('AWAITING_INPUT')
        s['report']['component_modes']['interpretation'] = 'llm'
        c = case()
        c['expected']['first_stop'] = 'AWAITING_INPUT'
        code, metadata, rows, _ = self.invoke([c], states=[s], mode='llm')
        self.assertEqual(code, 0)  # functional result, not a claim of real-model acceptance
        evidence = rows[0]['run']['stages'][0]['model_evidence'][0]
        self.assertEqual(evidence['recorded_mode'], 'llm')
        self.assertFalse(evidence['accepted_llm'])
        self.assertEqual(evidence['evidence_status'], 'no-call')
        self.assertNotIn('accepted-llm', metadata['summary']['model_evidence'])

    def test_actual_calls_activity_bindings_weights_pair_and_alias_mismatch(self):
        binding = dict(model_id='fixture-model', alias='fixture-alias')
        s = state('AWAITING_INPUT')
        s['task_id'] = 'fixture-task'
        s['run_settings'] = dict(requirements=dict(chat={'requirements': binding}))
        s['report']['component_modes']['interpretation'] = 'llm'
        s['report']['diagnostics'] = [dict(code='MODEL_CALL', details=dict(attempt=2, accepted=['source label']))]
        c = dict(action='create', event_id='fixture-event')
        calls = [dict(agent='requirements', call_id='rejected', status='ok', model='fixture-alias', served='fixture-alias'),
                 dict(agent='requirements', call_id='accepted', status='ok', model='fixture-alias', served='fixture-alias')]
        events = [dict(node='llm', phase='completed', details=dict(caller='requirements', model_id='fixture-model', mode='llm'))]
        service = FakeService(runner.ROOT, self.base / 'teacher.sqlite')
        evidence = runner.model_evidence(service, s, c, calls, events, {})[0]
        self.assertTrue(evidence['accepted_llm'])
        self.assertEqual(evidence['accepted_call_id'], 'accepted')
        self.assertEqual(evidence['configured_asset']['sha256'], hashlib.sha256(b'fixture weights, not a model').hexdigest())
        self.assertEqual(evidence['configured_asset']['revision'], 'fixture-revision')
        for mutation in ('wrong-alias', 'missing-activity', 'wrong-model-event', 'ambiguous-completion', 'fallback'):
            cc, ee, ss = copy.deepcopy(calls), copy.deepcopy(events), copy.deepcopy(s)
            if mutation == 'wrong-alias':
                cc[-1]['served'] = 'another-model'
            elif mutation == 'missing-activity':
                ee = []
            elif mutation == 'wrong-model-event':
                ee[0]['details']['model_id'] = 'another-model'
            elif mutation == 'ambiguous-completion':
                ee.append(copy.deepcopy(ee[0]))
            else:
                ss['report']['component_modes']['interpretation'] = 'deterministic_fallback'
            self.assertFalse(runner.model_evidence(service, ss, c, cc, ee, {})[0]['accepted_llm'])

    def test_calculation_roles_match_their_own_completed_attempt_and_binding(self):
        service = FakeService(runner.ROOT, self.base / 'teacher.sqlite')
        for role, index in (('compute_agent', 1), ('validator_agent', 2)):
            s = state('COMPLETED')
            s['task_id'] = 'fixture-task'
            s['run_settings'] = dict(calculation=dict(chat={role: dict(model_id='fixture-model', alias='fixture-alias')}))
            result = dict(mode='llm', attempts=2)
            if role == 'compute_agent':
                s['report']['planning_role'] = result
            else:
                s['review_assessment'] = dict(role=result)
            calls = [dict(agent=role, call_id=str(i), status='ok', model='fixture-alias', served='fixture-alias')
                     for i in range(2)]
            events = [dict(node='llm', phase='completed', details=dict(caller=role, attempt=2, model_id='fixture-model'))]
            c = dict(action='confirm', event_id='fixture-event')
            evidence = runner.model_evidence(service, s, c, calls, events, {})[index]
            self.assertTrue(evidence['accepted_llm'])
            self.assertEqual(evidence['accepted_call_id'], '1')
            # A different completed attempt cannot donate its model identity.
            events.append(dict(node='llm', phase='completed', details=dict(caller=role, attempt=1, model_id='another-model')))
            self.assertFalse(runner.model_evidence(service, s, c, calls, events, {})[index]['accepted_llm'])

    def test_unknown_assets_are_recorded_and_call_log_is_not_truncated(self):
        service = FakeService(runner.ROOT, self.base / 'teacher.sqlite')
        service.registry.models['fixture-model']['weights'] = 'missing.gguf'
        self.assertEqual(runner._asset(service, dict(model_id='fixture-model'), {})['status'], 'unknown')
        service.model_calls.path.write_text(''.join(json.dumps(dict(task_id='task', call_id=str(i))) + '\n'
                                                   for i in range(250)), encoding='utf-8')
        self.assertEqual(len(runner._model_calls(service, 'task')), 250)
        with service.model_calls.path.open('a', encoding='utf-8') as stream:
            stream.write('{broken\n')
        with self.assertRaises(ValueError):
            runner._model_calls(service, 'task')

    def test_heldout_category_is_advisory_and_separate(self):
        c = case()
        c['category'] = 'heldout'
        code, metadata, _, _ = self.invoke([c])
        self.assertEqual(code, 0)
        self.assertEqual(metadata['summary']['categories']['heldout'],
                         dict(total=1, completed=1, passed=1, advisory=True))


if __name__ == '__main__':
    unittest.main()
