import io
import json
from datetime import datetime
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from urllib.request import urlopen

from formula_rag.model_transport import chat, ModelResponseError, call_log, operation_cancel, operation_deadline
from planning.agents.requirements import RequirementsAgent
from planning.agents.role_model import output_language
from planning.workflow.model_log import ModelCallLog
from planning.workflow.task_service import TaskService
from test_calculation_plans import ROOT, MARGIN, command

COMMAND = dict(task_id='t1', event_id='e1', action='create', expected_revision=0)
PAYLOAD = {'model': 'commplan-qwen35-9b', 'messages': [{'role': 'system', 'content': '提示'}, {'role': 'user', 'content': '需求'}]}


def answer(content, model='commplan-qwen35-9b'):
    body = json.dumps({'model': model, 'choices': [{'message': {'content': content}}], 'usage': {'total_tokens': 9}})
    opener = Mock()
    opener.open.side_effect = lambda *a, **k: io.BytesIO(body.encode())
    return patch('urllib.request.build_opener', return_value=opener)


class ModelCallLogTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.log = ModelCallLog(Path(tmp.name) / 'tasks.sqlite')

    def test_each_call_records_agent_model_prompt_response_and_time(self):
        with self.log.recording(COMMAND), answer('{"ok":true}'):
            chat(PAYLOAD, agent='validator_agent')
        [row] = self.log.calls('t1')
        self.assertEqual((row['agent'], row['agent_name'], row['model'], row['served']),
                         ('validator_agent', 'Validation', 'commplan-qwen35-9b', 'commplan-qwen35-9b'))
        self.assertEqual(row['messages'], PAYLOAD['messages'])
        self.assertEqual((row['response'], row['status'], row['revision']), ('{"ok":true}', 'ok', 0))
        self.assertTrue(row['at'] and row['call_id'] and row['latency_ms'] >= 0)
        self.assertEqual(row['usage'], {'total_tokens': 9})

    def test_call_timestamps_preserve_at_as_the_end_and_measured_duration(self):
        with self.log.recording(COMMAND), answer('{}'):
            chat(PAYLOAD, agent='requirements')
        [row] = self.log.calls('t1')
        self.assertEqual(row['end_time'], row['at'])
        start, end = map(datetime.fromisoformat, (row['start_time'], row['end_time']))
        self.assertAlmostEqual((end - start).total_seconds() * 1000, row['latency_ms'], places=3)

    def test_run_filter_is_applied_before_the_limit_and_keeps_legacy_rows_readable(self):
        rows = [dict(task_id='t1', run_id='first', call_id='a'),
                dict(task_id='t1', call_id='legacy'),
                *[dict(task_id='t1', run_id='second', call_id=str(i)) for i in range(205)],
                dict(task_id='other', run_id='first', call_id='other')]
        self.log.path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
        self.assertEqual(self.log.calls('t1', run_id='first'), [rows[0]])
        self.assertEqual(self.log.calls('t1', limit=2, run_id='second'), rows[-3:-1])
        self.assertIn(rows[1], self.log.calls('t1', limit=300))

    def test_a_failed_call_is_recorded_with_its_code(self):
        with self.log.recording(COMMAND), answer('', model='commplan-qwen35-9b'):
            with self.assertRaises(ModelResponseError):
                chat(PAYLOAD, agent='requirements')
        [row] = self.log.calls('t1')
        self.assertEqual((row['agent_name'], row['status']), ('Requirements', 'MODEL_OUTPUT_INVALID'))
        self.assertEqual(row['end_time'], row['at'])
        self.assertLessEqual(datetime.fromisoformat(row['start_time']), datetime.fromisoformat(row['end_time']))

    def test_nothing_is_recorded_outside_a_command_and_other_tasks_are_filtered(self):
        with answer('{}'):
            chat(PAYLOAD, agent='requirements')
        self.assertEqual(self.log.calls('t1'), [])
        with self.log.recording(dict(COMMAND, task_id='t2')), answer('{}'):
            chat(PAYLOAD, agent='requirements')
        with open(self.log.path, 'a', encoding='utf-8') as f:
            f.write('not json\n')
        self.assertEqual(self.log.calls('t1'), [])
        self.assertEqual(len(self.log.calls('t2')), 1)

    def test_an_answer_revision_is_the_next_one(self):
        with self.log.recording(dict(COMMAND, action='answer', expected_revision=2)), answer('{}'):
            chat(PAYLOAD, agent='supplement')
        self.assertEqual(self.log.calls('t1')[0]['revision'], 3)


class ToolEventTests(unittest.TestCase):
    def test_every_calculation_step_is_an_activity_event_with_inputs_and_output(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        service = TaskService(ROOT, Path(tmp.name) / 'tasks.sqlite')
        draft = service.apply(command(text=MARGIN))['state']
        done = service.apply(command('confirm', draft))['state']
        tools = [e for e in service.activity.events(done['task_id']) if e['node'] == 'tool']
        self.assertEqual([e['details']['tool_id'] for e in tools], ['fspl_ghz', 'received_power', 'link_margin'])
        for event, step in zip(tools, done['result']['steps']):
            self.assertEqual(event['details']['inputs'], step['inputs'])
            self.assertEqual(event['details']['output'], step['output'])
            self.assertEqual(event['details']['caller'], 'compute_agent')


class CommandModelLogTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.service = TaskService(ROOT, Path(tmp.name) / 'tasks.sqlite')

    def model_during_requirements(self):
        original = RequirementsAgent.run
        def observed(agent, *args, **kwargs):
            chat(PAYLOAD, agent='requirements')
            chat(PAYLOAD, agent='requirements')
            return original(agent, *args, **kwargs)
        return patch.object(RequirementsAgent, 'run', observed)

    def test_every_command_call_has_its_activity_run_and_replay_makes_no_calls(self):
        c = command()
        with self.model_during_requirements(), answer('{}'):
            draft = self.service.apply(c)['state']
            replay = self.service.apply(c)
            self.service.apply(command('edit', draft))
        runs = [event for event in self.service.activity.events(c['task_id']) if event['node'] == 'command' and event['phase'] == 'started']
        rows = self.service.model_calls.calls(c['task_id'])
        self.assertTrue(replay['replayed'])
        self.assertEqual(len(rows), 4)
        self.assertEqual([row['run_id'] for row in rows], [runs[0]['run_id']] * 2 + [runs[2]['run_id']] * 2)
        self.assertEqual(self.service.model_calls.calls(c['task_id'], run_id=runs[1]['run_id']), [])

    def test_observation_start_failure_does_not_fail_the_command(self):
        with patch.object(self.service.activity, 'start', side_effect=OSError('observation unavailable')), self.model_during_requirements(), answer('{}'):
            draft = self.service.apply(command())['state']
        self.assertEqual(draft['status'], 'AWAITING_CONFIRMATION')
        self.assertEqual([row['run_id'] for row in self.service.model_calls.calls(draft['task_id'])], [None, None])

    def test_base_exception_marks_rejection_and_resets_command_context(self):
        class Abort(BaseException):
            pass
        c = command()
        prior = (call_log.get(), operation_cancel.get(), operation_deadline.get(), output_language.get())
        with patch.object(self.service, '_apply', side_effect=Abort('abort')):
            with self.assertRaises(Abort):
                self.service.apply(c)
        self.assertEqual(self.service.activity.events(c['task_id'])[-1]['phase'], 'rejected')
        self.assertEqual(self.service._running, [])
        self.assertEqual((call_log.get(), operation_cancel.get(), operation_deadline.get(), output_language.get()), prior)


class ModelCallEndpointTests(unittest.TestCase):
    def test_endpoint_filters_by_run_and_keeps_the_unfiltered_endpoint(self):
        from planning.web_server import create_server
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        service = TaskService(ROOT, Path(tmp.name) / 'tasks.sqlite')
        rows = [dict(task_id='t1', run_id='r1'), dict(task_id='t1', run_id='r2'), dict(task_id='t1')]
        service.model_calls.path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
        with patch('planning.web_server.TaskService', return_value=service):
            server = create_server(ROOT, port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        def stop():
            server.shutdown(); server.server_close(); thread.join(timeout=5)
        self.addCleanup(stop)
        base = f'http://127.0.0.1:{server.server_port}/api/tasks/t1/model-calls'
        with urlopen(base + '?run_id=r1', timeout=5) as response:
            self.assertEqual(json.load(response)['calls'], rows[:1])
        with urlopen(base, timeout=5) as response:
            self.assertEqual(json.load(response)['calls'], rows)


if __name__ == '__main__':
    unittest.main()
