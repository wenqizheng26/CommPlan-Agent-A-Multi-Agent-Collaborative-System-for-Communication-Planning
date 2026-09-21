import copy
from contextlib import closing
import importlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
TEXT = '按自由空间基准计算，频率2GHz，距离1km，求路径损耗。'


def command(action='create', state=None, text=TEXT, **changes):
    c = dict(action=action, task_id=state['task_id'] if state else str(uuid.uuid4()),
             event_id=str(uuid.uuid4()), expected_revision=state['revision'] if state else 0,
             expected_state_version=state['state_version'] if state else 0)
    if action in {'create', 'edit'}:
        c.update(input=dict(raw_text=text, manual_parameters={}, condition=None, target=None), mode='deterministic')
    if action == 'confirm':
        c['review_hash'] = state['review']['review_hash']
    c.update(changes)
    return c


class PlanningLoopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / 'tasks.sqlite'
        try:
            self.module = importlib.import_module('planning.workflow.task_service')
        except ModuleNotFoundError:
            self.fail('task service / durable confirmation loop not implemented')
        self.service = self.module.TaskService(ROOT, self.db)

    def create(self, text=TEXT):
        return self.service.apply(command(text=text))['state']

    def test_no_calculation_until_confirmation_then_golden_result(self):
        with patch('formula_rag.core.evaluate', side_effect=AssertionError('too early')):
            draft = self.create()
        self.assertEqual(draft['status'], 'AWAITING_CONFIRMATION')
        self.assertIsNone(draft['result'])
        self.assertIsNone(draft['confirmed_snapshot'])
        self.assertTrue(draft['pending_interrupt'])
        done = self.service.apply(command('confirm', draft))['state']
        self.assertEqual(done['status'], 'COMPLETED')
        self.assertAlmostEqual(done['result']['outputs'][0]['value'], 98.42059991327963)
        self.assertEqual(done['result']['outputs'][0]['unit'], 'dB')
        self.assertEqual(done['result']['runtime_mode'], 'deterministic')
        self.assertEqual(done['final_report']['result_hash'], done['result']['result_hash'])
        self.assertTrue(all(v['passed'] for v in done['validations']))

    def test_blocked_inputs_never_calculate(self):
        for text, status in [('自由空间基准，频率2GHz，求路径损耗', 'AWAITING_INPUT'),
                             (TEXT + '频率3GHz', 'AWAITING_INPUT'),
                             ('计算实际海面损耗，频率2GHz，距离1km', 'NEEDS_MODEL')]:
            with self.subTest(text=text), patch('formula_rag.core.evaluate', side_effect=AssertionError('blocked')):
                s = self.create(text)
                self.assertEqual(s['status'], status)
                with self.assertRaisesRegex(ValueError, 'NOT_CONFIRMABLE'):
                    self.service.apply(command('confirm', s, review_hash='x'))

    def test_edit_invalidates_completed_artifacts_and_rejects_old_confirmation(self):
        draft = self.create()
        stale = command('confirm', draft)
        done = self.service.apply(command('confirm', draft))['state']
        edited = self.service.apply(command('edit', done, text=TEXT.replace('2GHz', '3GHz')))['state']
        self.assertEqual(edited['revision'], 1)
        self.assertIsNone(edited['result'])
        self.assertIsNone(edited['confirmed_snapshot'])
        self.assertIsNone(edited['final_report'])
        with self.assertRaisesRegex(ValueError, 'STALE_REVISION'):
            self.service.apply(stale)
        again = self.service.apply(command('confirm', edited))['state']
        self.assertAlmostEqual(again['result']['outputs'][0]['value'], 101.94242509439326)
        history = self.service.history(draft['task_id'])
        self.assertTrue(any(h['state']['status'] == 'COMPLETED' and h['revision'] == 0 for h in history))

    def test_idempotent_replay_does_not_restore_old_revision(self):
        create = command()
        draft = self.service.apply(create)['state']
        confirm = command('confirm', draft)
        first = self.service.apply(confirm)
        with patch('formula_rag.core.evaluate', side_effect=AssertionError('duplicate computation')):
            replay = self.service.apply(confirm)
        self.assertTrue(replay['replayed'])
        self.assertEqual(first['acknowledgement'], replay['acknowledgement'])
        current = self.service.apply(command('edit', first['state']))['state']
        old = self.service.apply(confirm)
        self.assertEqual(old['state']['revision'], current['revision'])
        self.assertEqual(old['acknowledgement']['revision'], 0)
        with self.assertRaisesRegex(ValueError, 'IDEMPOTENCY_CONFLICT'):
            self.service.apply({**confirm, 'review_hash': 'other'})

    def test_two_clients_only_one_confirmation_commits(self):
        draft = self.create()
        commands = [command('confirm', draft), command('confirm', draft)]
        def apply(c):
            try:
                return self.module.TaskService(ROOT, self.db).apply(c)['state']['status']
            except ValueError as e:
                return str(e)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(apply, commands))
        self.assertEqual(results.count('COMPLETED'), 1)
        self.assertEqual(results.count('STALE_STATE_VERSION'), 1)

    def test_confirmation_cannot_inject_or_change_snapshot(self):
        draft = self.create()
        for extra in ({'result': {}}, {'parameters': {'frequency_ghz': 100}}, {'review_hash': 'wrong'}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                self.service.apply(command('confirm', draft, **extra))
        self.assertEqual(self.service.get(draft['task_id'])['status'], 'AWAITING_CONFIRMATION')

    def test_new_process_resumes_persisted_interrupt(self):
        draft = self.create()
        c = command('confirm', draft)
        code = "import json,sys; from planning.workflow.task_service import TaskService; print(json.dumps(TaskService(sys.argv[1],sys.argv[2]).apply(json.load(sys.stdin)),ensure_ascii=True))"
        run = subprocess.run([sys.executable, '-B', '-c', code, str(ROOT), str(self.db)],
                             input=json.dumps(c), text=True, capture_output=True, cwd=ROOT, timeout=30)
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(json.loads(run.stdout)['state']['status'], 'COMPLETED')
        self.assertEqual(self.service.get(draft['task_id'])['status'], 'COMPLETED')

    def test_commit_failure_rolls_back_checkpoint_and_confirmation(self):
        draft = self.create()
        c = command('confirm', draft)
        with closing(sqlite3.connect(self.db)) as db:
            before = db.execute('select count(*) from checkpoints').fetchone()[0]
        with patch('planning.workflow.task_store.TaskStore.save', side_effect=OSError('disk fail')):
            with self.assertRaises(OSError):
                self.service.apply(c)
        self.assertEqual(self.service.get(draft['task_id'])['status'], 'AWAITING_CONFIRMATION')
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute('select count(*) from checkpoints').fetchone()[0], before)
        self.assertEqual(self.service.apply(c)['state']['status'], 'COMPLETED')

    def test_process_exit_before_commit_leaves_recoverable_confirmation(self):
        draft = self.create()
        c = command('confirm', draft)
        code = '''import json,os,sys
from planning.workflow.task_service import TaskService
from planning.workflow.task_store import TaskStore
TaskStore.save = staticmethod(lambda *args: os._exit(17))
TaskService(sys.argv[1],sys.argv[2]).apply(json.load(sys.stdin))
'''
        run = subprocess.run([sys.executable,'-B','-c',code,str(ROOT),str(self.db)],input=json.dumps(c),
                             text=True,capture_output=True,cwd=ROOT,timeout=30)
        self.assertEqual(run.returncode,17,run.stderr)
        self.assertEqual(self.service.get(draft['task_id'])['status'],'AWAITING_CONFIRMATION')
        self.assertEqual(self.service.apply(c)['state']['status'],'COMPLETED')

    def test_catalog_change_before_confirmation_rejected(self):
        from formula_rag.catalog import load_catalog
        draft = self.create()
        cards = copy.deepcopy(load_catalog(ROOT))
        cards[0]['version'] += '-changed'
        with patch('planning.workflow.task_service.load_catalog', return_value=cards):
            with self.assertRaisesRegex(ValueError, 'KNOWLEDGE_CHANGED'):
                self.service.apply(command('confirm', draft))

    def test_calculation_exception_is_visible_and_has_no_published_result(self):
        draft = self.create()
        with patch('formula_rag.core.evaluate', side_effect=RuntimeError('test outage')):
            failed = self.service.apply(command('confirm', draft))['state']
        self.assertEqual(failed['status'], 'FAILED')
        self.assertIsNone(failed['final_report'])
        self.assertEqual(failed['failure']['responsible_node'], 'calculation')
        self.assertTrue(failed['failure']['next_action'])
        self.assertTrue(failed['report']['parameters_proposal'])

    def test_invalid_numeric_result_is_not_publishable(self):
        draft = self.create()
        with patch('formula_rag.core.evaluate', return_value={'status':'ok', 'value':float('nan'), 'unit':'dB', 'inputs':{}}):
            failed = self.service.apply(command('confirm', draft))['state']
        self.assertEqual(failed['status'], 'FAILED')
        self.assertIsNone(failed['final_report'])
        self.assertIsNone(failed['result'])

    def test_cancel_prevents_confirmation(self):
        draft = self.create()
        cancelled = self.service.apply(command('cancel', draft))['state']
        self.assertEqual(cancelled['status'], 'CANCELLED')
        with self.assertRaisesRegex(ValueError, 'NOT_CONFIRMABLE'):
            self.service.apply(command('confirm', cancelled))

    def test_cancel_does_not_require_available_catalog(self):
        draft = self.create()
        with patch('planning.workflow.task_service.load_catalog', side_effect=OSError('unreadable')):
            cancelled = self.service.apply(command('cancel', draft))['state']
        self.assertEqual(cancelled['status'], 'CANCELLED')
        self.assertEqual(cancelled['pending_interrupt'], [])

    def test_final_report_is_self_contained(self):
        draft = self.create()
        done = self.service.apply(command('confirm', draft))['state']
        final = done['final_report']
        self.assertEqual(final.get('normalized_inputs'), done['result']['normalized_inputs'])
        self.assertEqual(final.get('model_version'), done['result']['model_version'])
        self.assertEqual(final.get('formula'), done['result']['formula'])
        self.assertEqual(final.get('outputs'), done['result']['outputs'])

    def test_result_validation_binds_model_and_rejects_false_positive_number(self):
        from planning.services.calculation import validate_result
        from planning.requirements_contract import digest
        draft = self.create()
        done = self.service.apply(command('confirm', draft))['state']
        for field,value in [('model_id','other'),('model_version','999'),('formula','999'),
                            ('outputs',[{'name':'wrong','value':98.42059991327963,'unit':'dB'}]),
                            ('outputs',[{'name':'path_loss_db','value':900,'unit':'dB'}])]:
            with self.subTest(field=field,value=value):
                result=copy.deepcopy(done['result']); result[field]=value
                result['result_hash']=digest({k:v for k,v in result.items() if k!='result_hash'})
                self.assertFalse(all(v['passed'] for v in validate_result(result,done['confirmed_snapshot'])))

    def test_strict_boundary_and_unit_equivalence(self):
        for changes in ({'expected_revision': True}, {'expected_state_version': -1}, {'mode':'cloud'}, {'task_id':'../oops'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.service.apply(command(**changes))
        s = self.create(TEXT.replace('2GHz', '2000MHz').replace('1km','1000m'))
        done = self.service.apply(command('confirm', s))['state']
        self.assertAlmostEqual(done['result']['outputs'][0]['value'], 98.42059991327963)


if __name__ == '__main__':
    unittest.main()
