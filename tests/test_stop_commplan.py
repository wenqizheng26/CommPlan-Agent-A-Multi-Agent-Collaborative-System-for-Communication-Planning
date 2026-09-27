"""Stopping only ever touches CommPlan's own workbench and model servers."""

from pathlib import Path
import tempfile
import unittest
from unittest import mock

import stop_commplan

ALIASES = {18081: {'commplan-qwen35-9b', 'signal-formula-qwen3'}, 18084: {'commplan-qwen3-embedding'}}
MODEL = {'port': 18081, 'pid': 11}
EMBEDDING = {'port': 18084, 'pid': 12}
WORKBENCH = {'port': 18082, 'pid': 13}
SERVED = {
    'http://127.0.0.1:18081/v1/models': {'data': [{'id': 'commplan-qwen35-9b'}]},
    'http://127.0.0.1:18084/v1/models': {'data': [{'id': 'commplan-qwen3-embedding'}]},
    'http://127.0.0.1:18082/api/session': {'profile': 'confirmed-fspl-loop-v1'},
}
NETSTAT = """
活动连接

  协议  本地地址          外部地址        状态           PID
  TCP    127.0.0.1:18081        0.0.0.0:0              LISTENING       11
  TCP    127.0.0.1:18081        127.0.0.1:51663        TIME_WAIT       0
  TCP    127.0.0.1:18082        0.0.0.0:0              LISTENING       13
  TCP    127.0.0.1:18082        127.0.0.1:50000        ESTABLISHED     13
  TCP    0.0.0.0:445            0.0.0.0:0              LISTENING       4
"""


class RoleTests(unittest.TestCase):
    def role(self, listener, served=SERVED, command=''):
        with (mock.patch.object(stop_commplan, 'read_json', side_effect=served.get),
              mock.patch.object(stop_commplan, 'command_line', return_value=command) as slow):
            return stop_commplan.commplan_role(listener, ALIASES, {18082}), slow.call_count

    def test_registered_model_and_workbench_answer_over_http(self):
        self.assertEqual(self.role(MODEL), ('model', 0))
        self.assertEqual(self.role(EMBEDDING), ('model', 0))
        self.assertEqual(self.role(WORKBENCH), ('workbench', 0))

    def test_loading_model_is_recognised_by_its_command_line(self):
        self.assertEqual(self.role(MODEL, {}, 'E:/x/llama-server.exe -m w.gguf --alias commplan-qwen35-9b'), ('model', 1))
        self.assertEqual(self.role(WORKBENCH, {}, 'python.exe -B -m planning.web_server --port 18082'), ('workbench', 1))

    def test_other_programs_are_not(self):
        other = {'http://127.0.0.1:18081/v1/models': {'data': [{'id': 'someone-else'}]}}
        self.assertIsNone(self.role(MODEL, other, 'llama-server.exe --alias someone-else')[0])
        wrong_port = {'http://127.0.0.1:18084/v1/models': {'data': [{'id': 'commplan-qwen35-9b'}]}}
        self.assertIsNone(self.role(dict(MODEL, port=18084), wrong_port)[0])  # alias registered for another port
        self.assertIsNone(self.role(MODEL, {}, 'other.exe --alias commplan-qwen35-9b')[0])
        self.assertIsNone(self.role(WORKBENCH, {}, 'python.exe -m http.server 18082')[0])
        self.assertEqual(self.role(dict(WORKBENCH, port=18090)), (None, 0))
        self.assertEqual(self.role({'port': 445, 'pid': 4}), (None, 0))


class ListenerTests(unittest.TestCase):
    def test_listening_ports_only(self):
        with mock.patch.object(stop_commplan, 'run', return_value=NETSTAT) as run:
            found = stop_commplan.listeners({18081, 18082, 18084})
        self.assertEqual(found, [MODEL, WORKBENCH])
        self.assertEqual(run.call_count, 1)

    def test_nothing_listening_or_no_ports(self):
        with mock.patch.object(stop_commplan, 'run', return_value=NETSTAT) as run:
            self.assertEqual(stop_commplan.listeners({18099}), [])
            self.assertEqual(stop_commplan.listeners(set()), [])
        self.assertEqual(run.call_count, 1)


class MainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'runtime').mkdir()
        (self.root / 'runtime' / 'commplan-model.pid').write_text('11', encoding='ascii')
        (self.root / 'runtime' / 'commplan-web-18095.pid').write_text('77', encoding='ascii')
        patches = [mock.patch.object(stop_commplan, 'ROOT', self.root),
                   mock.patch.object(stop_commplan, 'service_ports', return_value=(ALIASES, {18082, 18095})),
                   mock.patch.object(stop_commplan, 'wait_closed', return_value=True),
                   mock.patch.object(stop_commplan, 'read_json', side_effect=SERVED.get),
                   mock.patch.object(stop_commplan, 'command_line', return_value='')]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_stops_ours_and_leaves_the_rest(self):
        foreign = {'port': 18095, 'pid': 99}
        with (mock.patch.object(stop_commplan, 'listeners', return_value=[MODEL, WORKBENCH, foreign]) as found,
              mock.patch.object(stop_commplan, 'stop') as stop):
            self.assertEqual(stop_commplan.main([]), 0)
        self.assertEqual(found.call_args.args[0], {18081, 18082, 18084, 18095})
        self.assertEqual([c.args[0] for c in stop.call_args_list], [11, 13])
        self.assertFalse((self.root / 'runtime' / 'commplan-model.pid').exists())
        self.assertTrue((self.root / 'runtime' / 'commplan-web-18095.pid').exists())

    def test_reports_a_process_that_would_not_close(self):
        with (mock.patch.object(stop_commplan, 'listeners', return_value=[MODEL]),
              mock.patch.object(stop_commplan, 'stop'),
              mock.patch.object(stop_commplan, 'wait_closed', return_value=False)):
            self.assertEqual(stop_commplan.main([]), 1)


class StopWorkbenchTests(unittest.TestCase):
    def replace(self, served, command, found):
        with (mock.patch.object(stop_commplan, 'read_json', side_effect=served.get),
              mock.patch.object(stop_commplan, 'command_line', return_value=command),
              mock.patch.object(stop_commplan, 'wait_closed', return_value=True),
              mock.patch.object(stop_commplan, 'listeners', return_value=found),
              mock.patch.object(stop_commplan, 'stop') as stop):
            return stop_commplan.stop_workbench(18082), [c.args[0] for c in stop.call_args_list]

    def test_only_a_commplan_workbench_is_replaced(self):
        self.assertEqual(self.replace(SERVED, '', [WORKBENCH]), (True, [13]))
        self.assertEqual(self.replace({}, 'python.exe -m planning.web_server --port 18082', [WORKBENCH]), (True, [13]))
        self.assertEqual(self.replace({}, 'nginx.exe -p 18082', [WORKBENCH]), (False, []))
        self.assertEqual(self.replace(SERVED, '', []), (False, []))


if __name__ == '__main__':
    unittest.main()
