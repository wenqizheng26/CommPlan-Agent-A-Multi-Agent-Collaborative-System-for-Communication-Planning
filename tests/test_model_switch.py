"""Model switching: one chat model on the shared port, never during a command."""
import io
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from formula_rag.model_transport import chat, ModelResponseError
from planning.providers.registry import Registry
from planning.providers.settings import SettingsStore
from planning.services.model_status import probe_registry
from planning.services.model_switch import Gate, ModelSwitcher, SwitchFailed
from test_planning_loop import ROOT

NINE, FOUR, FAST = 'qwen35-9b-q4', 'qwen3-4b-q4', 'qwen3-4b-q4-fast-fail'


class FakeRuntime:
    """Serves one alias; records stops and starts; can refuse to start a model."""

    def __init__(self, registry, served, fail=()):
        self.registry, self.alias, self.fail, self.calls = registry, served, set(fail), []

    def assets(self, model):
        return Path('.') if model['id'] != 'missing' else None

    def served(self, model):
        return ('ok', {self.alias}) if self.alias else ('unreachable', set())

    def stop(self, model):
        self.calls.append(('stop', self.alias))
        self.alias = None

    def start(self, model):
        self.calls.append(('start', model['id']))
        if model['id'] in self.fail:
            raise SwitchFailed('模型提前退出，请查看 runtime 中的 commplan-*.err.log。')
        self.alias = model['alias']


class Service:
    def __init__(self, db):
        self.root = ROOT
        self.registry = Registry(ROOT)
        self.settings = SettingsStore(db, self.registry)

    def update_settings(self, settings, version):
        return self.settings.put(settings, version)


class SwitchTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.service = Service(Path(tmp.name) / 's.sqlite')
        self.gate = Gate()

    def switch(self, runtime, model_id):
        switcher = ModelSwitcher(self.service, self.gate, runtime)
        state = switcher.start(model_id)
        self.assertEqual(state['model_id'], model_id)  # a fake runtime may already have finished
        deadline = time.monotonic() + 5
        while switcher.status()['state'] == 'switching' and time.monotonic() < deadline:
            time.sleep(0.01)
        return switcher.status()

    def test_switch_stops_the_old_model_starts_the_new_and_saves_the_default(self):
        r = self.service.registry
        s = self.service.settings.get()
        roles = dict(s['settings']['chat']['roles'], validator_agent=NINE, compute_agent=FAST)
        self.service.settings.put(dict(s['settings'], chat=dict(default=NINE, roles=roles)), 0)
        runtime = FakeRuntime(r, r.models[NINE]['alias'])
        state = self.switch(runtime, FOUR)
        self.assertEqual(state['state'], 'done', state)
        self.assertEqual(runtime.calls, [('stop', 'commplan-qwen35-9b'), ('start', FOUR)])
        saved = self.service.settings.get()['settings']['chat']
        self.assertEqual(saved['default'], FOUR)
        # A role bound to the unloaded 9B follows the default; the 4B fast-fail profile shares the loaded model.
        self.assertEqual((saved['roles']['validator_agent'], saved['roles']['compute_agent']), (None, FAST))
        self.assertEqual(state['cleared_roles'], ['validator_agent'])
        self.assertIn('已切换到 Qwen3 4B · 标准', state['message'])
        self.assertIn('1 个角色', state['message'])
        self.assertGreaterEqual(state['elapsed_ms'], 0)
        self.assertFalse(self.gate.switching)

    def test_a_loaded_model_is_not_restarted(self):
        r = self.service.registry
        runtime = FakeRuntime(r, r.models[FOUR]['alias'])
        state = self.switch(runtime, FAST)
        self.assertEqual((state['state'], runtime.calls), ('done', []))
        self.assertEqual(self.service.settings.get()['settings']['chat']['default'], FAST)

    def test_failed_start_restores_the_previous_model(self):
        r = self.service.registry
        runtime = FakeRuntime(r, r.models[NINE]['alias'], fail={FOUR})
        state = self.switch(runtime, FOUR)
        self.assertEqual(state['state'], 'failed')
        self.assertEqual(runtime.calls, [('stop', 'commplan-qwen35-9b'), ('start', FOUR), ('start', NINE)])
        self.assertIn('已恢复 Qwen3.5 9B', state['message'])
        self.assertEqual(self.service.settings.get()['version'], 0)  # nothing saved
        runtime = FakeRuntime(r, r.models[NINE]['alias'], fail={FOUR, NINE})
        self.assertIn('原模型未能恢复', self.switch(runtime, FOUR)['message'])

    def test_foreign_program_on_the_port_is_left_alone(self):
        r = self.service.registry
        runtime = FakeRuntime(r, 'someone-else')
        runtime.stop = Mock(side_effect=SwitchFailed('18081 端口被其他程序占用，没有切换。'))
        state = self.switch(runtime, FOUR)
        self.assertEqual(state['state'], 'failed')
        self.assertIn('其他程序', state['message'])
        self.assertEqual(runtime.calls, [])

    def test_invalid_targets_are_refused_before_anything_stops(self):
        r = self.service.registry
        switcher = ModelSwitcher(self.service, self.gate, FakeRuntime(r, None))
        for bad, code in [('nope', 'SETTINGS_UNKNOWN_MODEL'), (None, 'SETTINGS_UNKNOWN_MODEL'),
                          ('qwen3-embedding-0.6b-q8', 'SETTINGS_UNKNOWN_MODEL')]:
            with self.subTest(bad=bad), self.assertRaises(ValueError) as caught:
                switcher.start(bad)
            self.assertEqual(str(caught.exception), code)
        runtime = FakeRuntime(r, None)
        runtime.assets = lambda model: None
        with self.assertRaises(ValueError) as caught:
            ModelSwitcher(self.service, self.gate, runtime).start(FOUR)
        self.assertEqual(str(caught.exception), 'MODEL_NOT_INSTALLED')
        self.assertFalse(self.gate.switching)

    def test_commands_and_switches_exclude_each_other(self):
        gate = Gate()
        with gate.command():
            with self.assertRaises(ValueError) as caught:
                gate.claim()
            self.assertEqual(str(caught.exception), 'MODEL_SWITCH_BUSY')
        gate.claim()
        for code, action in [('MODEL_SWITCH_RUNNING', gate.claim), ('MODEL_SWITCHING', lambda: gate.command().__enter__())]:
            with self.subTest(code=code), self.assertRaises(ValueError) as caught:
                action()
            self.assertEqual(str(caught.exception), code)
        gate.release()
        with gate.command():
            self.assertEqual(gate.running, 1)
        self.assertEqual(gate.running, 0)


class WebTests(unittest.TestCase):
    def setUp(self):
        from planning import web_server
        from test_planning_loop import command
        self.command = command
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.gate = Gate()
        registry = Registry(ROOT)
        self.runtime = FakeRuntime(registry, registry.models[NINE]['alias'])
        make = lambda service, gate: ModelSwitcher(service, gate, self.runtime)
        with patch.object(web_server, 'Gate', return_value=self.gate), patch.object(web_server, 'ModelSwitcher', side_effect=make):
            self.server = web_server.create_server(ROOT, Path(tmp.name) / 'web.sqlite', port=0)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(timeout=5)))
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.token = self.call('/api/session')[1]['token']

    def call(self, path, body=None):
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        headers = {'Content-Type': 'application/json', **({'X-Planning-Token': self.token} if hasattr(self, 'token') else {})}
        try:
            response = urlopen(Request(self.base + path, data=json.dumps(body).encode() if body is not None else None,
                                       headers=headers), timeout=15)
        except HTTPError as exc:
            response = exc
        with response:
            return response.status, json.loads(response.read())

    def test_switch_endpoint_saves_the_default_and_blocks_commands_meanwhile(self):
        self.assertEqual(self.call('/api/model-switch'), (200, {'state': 'idle'}))
        for body in ({}, {'model_id': FOUR, 'extra': 1}, {'model_id': 'nope'}):
            with self.subTest(body=body):
                self.assertEqual(self.call('/api/model-switch', body)[0], 400)
        self.gate.claim()  # a switch in progress
        code, data = self.call('/api/commands', self.command())
        self.assertEqual((code, data['error']['code']), (409, 'MODEL_SWITCHING'))
        self.assertEqual(self.call('/api/model-switch', {'model_id': FOUR})[1]['error']['code'], 'MODEL_SWITCH_RUNNING')
        self.gate.release()
        code, state = self.call('/api/model-switch', {'model_id': FOUR})
        self.assertEqual((code, state['model_id']), (200, FOUR))
        deadline = time.monotonic() + 5
        while state['state'] == 'switching' and time.monotonic() < deadline:
            time.sleep(0.02)
            state = self.call('/api/model-switch')[1]
        self.assertEqual(state['state'], 'done')
        self.assertEqual(self.call('/api/settings')[1]['settings']['chat']['default'], FOUR)
        self.assertEqual(self.call('/api/commands', self.command())[0], 200)
        # The live status line checks the model the settings now choose.
        with patch('planning.web_server.probe_model', return_value={'status': 'ready'}) as probe:
            self.call('/api/model-status')
        self.assertEqual(probe.call_args.args, ('http://127.0.0.1:18081', 'signal-formula-qwen3'))


class StatusTests(unittest.TestCase):
    def test_other_registered_model_on_the_port_is_standby(self):
        registry = Registry(ROOT)

        def endpoint(base):
            return ('ok', {'commplan-qwen35-9b'}) if base.endswith('18081') else ('unreachable', set())
        with patch('planning.services.model_status.probe_endpoint', side_effect=endpoint), \
             patch.object(registry, 'installed', return_value=True):
            status = probe_registry(registry)
        self.assertEqual((status[NINE], status[FOUR], status[FAST]), ('ready', 'standby', 'standby'))
        self.assertEqual(status['qwen3-embedding-0.6b-q8'], 'unreachable')
        with patch('planning.services.model_status.probe_endpoint', side_effect=endpoint), \
             patch.object(registry, 'installed', return_value=False):
            self.assertEqual(probe_registry(registry)[FOUR], 'not_installed')
        with patch('planning.services.model_status.probe_endpoint', return_value=('ok', {'foreign'})):
            self.assertEqual(probe_registry(registry)[NINE], 'unexpected')


class TransportTests(unittest.TestCase):
    def reply(self, model):
        opener = Mock()
        opener.open.side_effect = lambda *a, **k: io.BytesIO(json.dumps(
            {'choices': [{'message': {'content': '{}'}}], 'model': model}).encode())
        return patch('urllib.request.build_opener', return_value=opener), opener

    def test_the_named_model_must_be_the_one_that_answered(self):
        patcher, _ = self.reply('commplan-qwen35-9b')
        with patcher, self.assertRaises(ModelResponseError) as caught:
            chat({'model': 'signal-formula-qwen3', 'messages': [{'content': 'x'}]})
        self.assertEqual(caught.exception.code, 'MODEL_NOT_LOADED')
        self.assertFalse(caught.exception.retryable)
        self.assertIn('commplan-qwen35-9b', str(caught.exception))
        patcher, _ = self.reply('commplan-qwen35-9b')
        with patcher:
            self.assertEqual(chat({'model': 'commplan-qwen35-9b', 'messages': [{'content': 'x'}]})[1], '{}')

    def test_a_request_without_a_model_name_takes_the_loaded_one(self):
        patcher, opener = self.reply('commplan-qwen35-9b')
        with patcher:
            chat({'model': None, 'messages': [{'content': 'x'}]})
        self.assertNotIn('model', json.loads(opener.open.call_args.args[0].data))


if __name__ == '__main__':
    unittest.main()
