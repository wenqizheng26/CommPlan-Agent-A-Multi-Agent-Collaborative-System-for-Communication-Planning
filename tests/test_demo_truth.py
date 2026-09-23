"""Release correctness gates for knowledge identity and explicit input residue."""
from contextlib import closing
import sqlite3
import tempfile
import unittest
from pathlib import Path

from planning.build_info import build_fingerprint
from planning.workflow.task_service import TaskService
from tests.test_planning_loop import ROOT, command


class BuildIdentityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / 'knowledge').mkdir()
        (self.root / 'knowledge/formulas.json').write_text('[]', encoding='utf-8')

    def test_formula_knowledge_changes_build_identity(self):
        before = build_fingerprint(self.root)
        (self.root / 'knowledge/formulas.json').write_text('[{"version":"2"}]', encoding='utf-8')
        self.assertNotEqual(before, build_fingerprint(self.root))

    def test_runtime_config_changes_build_identity(self):
        config = self.root / 'runtime_config.json'
        config.write_text('{"generation":{"context_size":4096}}', encoding='utf-8')
        before = build_fingerprint(self.root)
        config.write_text('{"generation":{"context_size":8192}}', encoding='utf-8')
        self.assertNotEqual(before, build_fingerprint(self.root))

    def test_history_logs_and_pids_do_not_change_build_identity(self):
        before = build_fingerprint(self.root)
        (self.root / 'runtime').mkdir()
        (self.root / 'outputs').mkdir()
        (self.root / 'runtime/commplan-web.out.log').write_text('started', encoding='utf-8')
        (self.root / 'runtime/commplan-web.pid').write_text('1234', encoding='ascii')
        with closing(sqlite3.connect(self.root / 'outputs/planning.sqlite')) as db, db:
            db.execute('CREATE TABLE history (revision INTEGER)')
            db.execute('INSERT INTO history VALUES (1)')
        self.assertEqual(before, build_fingerprint(self.root))


class UnitlessDistanceTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.service = TaskService(ROOT, Path(tmp.name) / 'tasks.sqlite')

    def test_unitless_distance_cannot_hide_behind_valid_observation(self):
        for fragment in ('距离3', '距离大约3', '距离1km，距离3', '距离1km，距离大约3'):
            with self.subTest(fragment=fragment):
                state = self.service.apply(command(text='按自由空间基准，频率2GHz，' + fragment + '，求路径损耗'))['state']
                self.assertEqual(state['status'], 'AWAITING_INPUT')
                self.assertTrue(any(d['code'] == 'INPUT_PARSE_ISSUE' and
                                    d['details'].get('field') == 'distance_km'
                                    for d in state['report']['diagnostics']))
                with self.assertRaisesRegex(ValueError, 'NOT_CONFIRMABLE'):
                    self.service.apply(command('confirm', state, review_hash='blocked'))
                self.assertIsNone(self.service.get(state['task_id'])['result'])

    def test_shared_trailing_unit_candidates_remain_confirmable(self):
        state = self.service.apply(command(text='按自由空间基准，频率2GHz，距离3或4km，求路径损耗'))['state']
        self.assertEqual(state['status'], 'AWAITING_CONFIRMATION')
        distance = next(p for p in state['report']['parameters_proposal'] if p['canonical_name'] == 'distance_km')
        self.assertEqual(distance['value'], {'kind': 'choices', 'values': [3.0, 4.0]})
        done = self.service.apply(command('confirm', state))['state']
        self.assertEqual(done['status'], 'COMPLETED')
        self.assertEqual([output['inputs']['distance_km'] for output in done['result']['outputs']], [3.0, 4.0])
        self.assertTrue(all(check['passed'] for check in done['validations']))
