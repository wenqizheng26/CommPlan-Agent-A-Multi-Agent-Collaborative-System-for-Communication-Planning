import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from formula_rag.model_transport import chat, ModelResponseError
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
                         ('validator_agent', 'Report', 'commplan-qwen35-9b', 'commplan-qwen35-9b'))
        self.assertEqual(row['messages'], PAYLOAD['messages'])
        self.assertEqual((row['response'], row['status'], row['revision']), ('{"ok":true}', 'ok', 0))
        self.assertTrue(row['at'] and row['call_id'] and row['latency_ms'] >= 0)
        self.assertEqual(row['usage'], {'total_tokens': 9})

    def test_a_failed_call_is_recorded_with_its_code(self):
        with self.log.recording(COMMAND), answer('', model='commplan-qwen35-9b'):
            with self.assertRaises(ModelResponseError):
                chat(PAYLOAD, agent='requirements')
        [row] = self.log.calls('t1')
        self.assertEqual((row['agent_name'], row['status']), ('Requirement', 'MODEL_OUTPUT_INVALID'))

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


if __name__ == '__main__':
    unittest.main()
