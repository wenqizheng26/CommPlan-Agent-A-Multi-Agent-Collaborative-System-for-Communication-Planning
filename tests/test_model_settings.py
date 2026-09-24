import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from planning.providers.registry import Registry, ROLES
from planning.providers.settings import SettingsStore, factory
from planning.workflow.task_service import TaskService

ROOT = Path(__file__).resolve().parents[1]
TEXT = '按自由空间基准计算，频率2GHz，距离1km，求路径损耗。'


def registry_with(tmp, mutate):
    data = json.loads((ROOT / 'config/models.json').read_text(encoding='utf-8'))
    mutate(data)
    path = Path(tmp) / 'models.json'
    path.write_text(json.dumps(data), encoding='utf-8')
    return Registry(ROOT, path)


class RegistryTests(unittest.TestCase):
    def test_shipped_registry_loads(self):
        r = Registry(ROOT)
        self.assertEqual(r.kind(r.defaults['chat']), 'chat')
        self.assertTrue(all(r.strict(m) for m in r.models if r.kind(m) == 'chat'))
        listing = r.describe()
        self.assertNotIn('weights', json.dumps(listing))  # no filesystem paths reach the page

    def test_rejects_remote_endpoint_and_escaping_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            for mutate in (lambda d: d['models'][0].update(endpoint='http://10.0.0.5:18081'),
                           lambda d: d['models'][0].update(endpoint='https://example.com'),
                           lambda d: d['models'][0].update(weights='../outside.gguf'),
                           lambda d: d['models'][0].update(weights='C:/models/x.gguf'),
                           lambda d: d['models'].append(dict(d['models'][0])),
                           lambda d: d['defaults'].update(chat='bge-small-zh-v1.5')):
                with self.subTest(), self.assertRaises(ValueError):
                    registry_with(tmp, mutate)

    def test_binding_applies_overrides(self):
        r = Registry(ROOT)
        b = r.binding('requirements', 'qwen3-4b-q4-fast-fail', dict(temperature=None, timeout_s=None))
        self.assertEqual((b.timeout_s, b.temperature, b.url), (12.0, 0, 'http://127.0.0.1:18081/v1/chat/completions'))
        self.assertEqual(r.binding('requirements', 'qwen3-4b-q4', dict(temperature=0.2, timeout_s=45)).timeout_s, 45.0)


class SettingsStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.registry = Registry(ROOT)
        self.store = SettingsStore(Path(self.tmp.name) / 'p.sqlite', self.registry)

    def tearDown(self):
        self.tmp.cleanup()

    def test_factory_defaults_and_versioned_put(self):
        got = self.store.get()
        self.assertEqual((got['version'], got['settings']['retrieval']['mode']), (0, 'lexical'))
        s = copy.deepcopy(got['settings'])
        s['retrieval'].update(mode='hybrid', top_k=5, top_n=2)
        self.assertEqual(self.store.put(s, 0)['version'], 1)
        self.assertEqual(self.store.get()['settings']['retrieval']['top_k'], 5)
        with self.assertRaisesRegex(ValueError, 'STALE_SETTINGS'):
            self.store.put(s, 0)

    def test_invalid_settings_rejected(self):
        base = factory(self.registry)
        cases = [lambda s: s['retrieval'].update(top_n=9), lambda s: s['retrieval'].update(top_k=21),
                 lambda s: s['retrieval'].update(mode='semantic'), lambda s: s['chat'].update(default='nope'),
                 lambda s: s['chat']['roles'].update(requirements='bge-small-zh-v1.5'),
                 lambda s: s['params'].update(timeout_s=1), lambda s: s['params'].update(extra=1),
                 lambda s: s.update(mode_default='auto'),
                 lambda s: s['retrieval'].update(mode='dense', embedding=None)]
        for mutate in cases:
            s = copy.deepcopy(base)
            mutate(s)
            with self.subTest(), self.assertRaises(ValueError):
                self.store.put(s, 0)

    def test_unstructured_model_cannot_be_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            reg = registry_with(tmp, lambda d: d['models'].append(dict(d['models'][0], id='loose',
                                capabilities={'json_schema_strict': False})))
            store = SettingsStore(Path(tmp) / 'p.sqlite', reg)
            s = factory(reg)
            s['chat']['roles']['validator_agent'] = 'loose'
            with self.assertRaisesRegex(ValueError, 'SETTINGS_MODEL_NOT_STRUCTURED'):
                store.put(s, 0)


def command(action, task_id='t1', event_id='e1', rev=0, ver=0, **extra):
    c = dict(action=action, task_id=task_id, event_id=event_id, expected_revision=rev, expected_state_version=ver)
    if action in ('create', 'edit'):
        c.update(input=dict(raw_text=TEXT, manual_parameters={}, condition=None, target=None), mode=extra.pop('mode', 'deterministic'))
    c.update(extra)
    return c


class RunSettingsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.service = TaskService(ROOT, Path(self.tmp.name) / 'p.sqlite')

    def tearDown(self):
        self.tmp.cleanup()

    def change(self, **retrieval):
        got = self.service.settings.get()
        s = copy.deepcopy(got['settings'])
        s['retrieval'].update(retrieval)
        return self.service.update_settings(s, got['version'])

    def test_each_phase_records_its_settings_and_changes_do_not_invalidate(self):
        state = self.service.apply(command('create'))['state']
        req = state['run_settings']['requirements']
        self.assertEqual((req['settings_version'], req['retrieval']['top_n'], req['chat']), (0, 3, None))
        self.assertEqual(state['retrieval']['used'][0], 'fspl_ghz')
        self.assertEqual(state['status'], 'AWAITING_CONFIRMATION')

        self.change(top_k=5, top_n=2)
        again = self.service.get('t1')
        self.assertEqual(again['status'], 'AWAITING_CONFIRMATION')  # settings never touch saved tasks
        self.assertEqual(again['run_settings'], state['run_settings'])

        done = self.service.apply(command('confirm', event_id='e2', ver=state['state_version'],
                                          review_hash=state['review']['review_hash']))['state']
        self.assertEqual(done['status'], 'COMPLETED')
        self.assertEqual(done['run_settings']['requirements'], req)
        self.assertEqual(done['run_settings']['calculation']['settings_version'], 1)
        self.assertEqual(done['retrieval'], state['retrieval'])

    def test_top_n_gates_model_context(self):
        self.change(top_k=3, top_n=1)
        state = self.service.apply(command('create'))['state']
        self.assertEqual(state['retrieval']['used'], ['fspl_ghz'])
        self.assertEqual(len(state['retrieval']['hits']), 3)

    def test_llm_mode_binds_each_role_to_the_selected_model(self):
        got = self.service.settings.get()
        s = copy.deepcopy(got['settings'])
        s['chat']['roles']['validator_agent'] = 'qwen3-4b-q4-fast-fail'
        s['params']['timeout_s'] = None
        self.service.update_settings(s, got['version'])
        seen = []

        def offline(selector, *args, **kwargs):
            seen.append(getattr(selector, 'binding', None) or selector)
            raise OSError('offline')
        with patch('formula_rag.model.LocalSelector.__call__', lambda self, *a, **k: offline(self)), \
             patch('planning.agents.role_model.LocalRoleSelector.__call__', lambda self, *a, **k: offline(self)):
            state = self.service.apply(command('create', mode='llm'))['state']
            chat = state['run_settings']['requirements']['chat']
            self.assertEqual(set(chat), set(ROLES))
            self.assertEqual(chat['validator_agent']['model_id'], 'qwen3-4b-q4-fast-fail')
            self.assertEqual(chat['validator_agent']['timeout_s'], 12.0)
            self.assertEqual(chat['requirements']['model_id'], 'qwen3-4b-q4')
            done = self.service.apply(command('confirm', event_id='e2', ver=state['state_version'],
                                              review_hash=state['review']['review_hash']))['state']
        self.assertEqual(done['status'], 'COMPLETED')  # offline models degrade, numbers stay deterministic
        self.assertEqual(done['final_report']['runtime_health'], 'degraded')
        bound = [b.model_id for b in seen if hasattr(b, 'model_id')]
        self.assertIn('qwen3-4b-q4-fast-fail', bound)

    def test_failed_model_calls_record_a_reason(self):
        with patch('planning.agents.role_model.LocalRoleSelector.__call__', side_effect=ConnectionRefusedError()),              patch('formula_rag.model.LocalSelector.__call__', side_effect=ConnectionRefusedError()):
            state = self.service.apply(command('create', mode='llm'))['state']
            self.service.apply(command('confirm', event_id='e2', ver=state['state_version'],
                                       review_hash=state['review']['review_hash']))
        failed = [e for e in self.service.activity.events('t1') if e['node'] == 'llm' and e['phase'] == 'failed'
                  and e['details'].get('caller') in ('compute_agent', 'validator_agent')]
        self.assertTrue(failed)
        self.assertTrue(all(e['details']['reason'] == 'offline' and e['details']['model_id'] for e in failed))


if __name__ == '__main__':
    unittest.main()
