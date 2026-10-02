"""Confirmed supplementary chains, domain rejection and replay trust boundary."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from planning.workflow.task_service import TaskService
from planning.services.requirement_validation import check_report
from formula_rag.catalog import load_catalog
from test_planning_loop import command

ROOT = Path(__file__).resolve().parents[1]
CASES = [
    ('计算第一菲涅耳区半径，频率2GHz，d1=15km，d2=15km。', ['fresnel_radius'], 33.50074626034471),
    ('计算绕射参数，频率2GHz，d1=15km，d2=15km，障碍物相对高度20m。', ['knife_edge_nu'], 0.843565890659271),
    ('采用单刃形障碍物模型，计算单刃形绕射损耗，频率2GHz，d1=15km，d2=15km，障碍物相对高度20m。', ['knife_edge_nu','knife_edge_loss'], 12.876),
    ('采用单刃形障碍物模型，计算单刃形绕射损耗，绕射参数0 1。', ['knife_edge_loss'], 6.0329),
    ('采用光滑海面单点镜面反射两径模型，计算海面反射附加损耗，频率2GHz，距离30km，起点天线海面高度30m，终点天线海面高度25m。', ['sea_reflection_two_ray'], 5.13),
]


class CoastalTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.service=TaskService(ROOT,Path(self.tmp.name)/'tasks.sqlite')

    def test_confirmed_chains_independent_validation_and_restart(self):
        for text,chain,value in CASES:
            with self.subTest(text=text):
                with patch('formula_rag.core.evaluate',side_effect=AssertionError('before confirmation')):
                    draft=self.service.apply(command(text=text))['state']
                self.assertEqual(draft['status'],'AWAITING_CONFIRMATION',draft['report']['diagnostics'])
                self.assertEqual(draft['report']['calculation_plan_proposal']['selected_model'],chain)
                # Confirmation is replayed from persisted input by a fresh service.
                fresh=TaskService(ROOT,Path(self.tmp.name)/'tasks.sqlite')
                done=fresh.apply(command('confirm',draft))['state']
                self.assertEqual(done['status'],'COMPLETED',done.get('failure'))
                self.assertAlmostEqual(done['result']['outputs'][0]['value'],value,delta=.002)
                self.assertTrue(all(v['passed'] for v in done['validations']))

    def test_missing_conditions_and_parameters(self):
        for text in [CASES[2][0].replace('采用单刃形障碍物模型，','').replace('单刃形绕射损耗','刃形绕射损耗'),
                     CASES[4][0].replace('采用光滑海面单点镜面反射两径模型，',''),
                     CASES[0][0].replace('，d2=15km','')]:
            draft=self.service.apply(command(text=text))['state']
            self.assertEqual(draft['status'],'AWAITING_INPUT')
            self.assertTrue(draft['input_issues'])

    def test_scalar_bounds_and_actual_sea_scope(self):
        for text in [CASES[0][0].replace('d1=15km','d1=0km'), CASES[4][0].replace('30m','0m'),
                     CASES[3][0].replace('0 1','-0.78 1')]:
            draft=self.service.apply(command(text=text))['state']
            self.assertEqual(draft['status'],'AWAITING_INPUT')
        draft=self.service.apply(command(text='计算实际海面损耗，频率2GHz，距离30km。'))['state']
        self.assertEqual(draft['status'],'NEEDS_MODEL')

    def test_tool_domain_rejection_after_confirmation(self):
        for text in [CASES[4][0].replace('距离30km','距离100km'),
                     CASES[4][0].replace('频率2GHz','频率0.0001GHz')]:
            draft=self.service.apply(command(text=text))['state']
            done=self.service.apply(command('confirm',draft))['state']
            self.assertNotEqual(done['status'],'COMPLETED')
            self.assertIsNone(done.get('result'))

    def test_forged_condition_is_rejected(self):
        draft=self.service.apply(command(text=CASES[4][0]))['state']
        report=copy.deepcopy(draft['report']); report['conditions'].remove('smooth_sea')
        request=dict(draft['request'],schema_version='1.0.0',task_id=draft['task_id'],revision=0,
                     request_id=report['request_id'])
        with self.assertRaisesRegex(ValueError,'CONDITION_MISMATCH'):
            check_report(report,request,load_catalog(ROOT),ROOT)
