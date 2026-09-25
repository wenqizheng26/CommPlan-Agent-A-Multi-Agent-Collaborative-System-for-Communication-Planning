import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tests.test_planning_loop import ROOT, command
from planning.agents.calculation import CalculationAgent, propose_calculation
from planning.services.confirmation import confirm_review
from planning.workflow.task_service import TaskService
from formula_rag.catalog import load_catalog
from planning.agents.review import ReviewAgent, validate_assessment
from planning.services.calculation import execute
from planning.requirements_contract import digest
from planning.agents.orchestrator import decide


class RoleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.service = TaskService(ROOT, Path(self.tmp.name)/'roles.sqlite')
        self.draft = self.service.apply(command())['state']
        self.snapshot = confirm_review(self.draft['review'], load_catalog(ROOT))

    def test_compute_rejects_injected_values_and_identity_changes(self):
        expected = propose_calculation(self.snapshot)
        for changes in [{'tool_id':'thermal_noise'}, {'snapshot_id':'other'},
                        {'plan_step_id':'other'}, {'expected_revision':True}, {'value':123}]:
            with self.subTest(changes=changes):
                def selector(*args):
                    return dict(output=dict(expected, **changes))
                result = CalculationAgent(selector).run(self.snapshot)
                self.assertEqual(result['mode'], 'deterministic_fallback')
                self.assertEqual(result['attempts'], 2)
                self.assertEqual(result['proposal'], expected)

    def test_compute_readonly_view_and_valid_suggestion(self):
        before = copy.deepcopy(self.snapshot)
        def selector(role, prompt, view, schema):
            answer = copy.deepcopy(view['allowed_call'])
            view['allowed_call']['snapshot_id'] = 'tampered'
            return dict(output=answer, model='test')
        result = CalculationAgent(selector).run(self.snapshot)
        self.assertEqual(result['mode'], 'stub')
        self.assertEqual(self.snapshot, before)

    def test_compute_unavailable_stops_after_one_call_and_falls_back(self):
        with patch('planning.agents.role_model.LocalRoleSelector.__call__',side_effect=ConnectionError) as call:
            result = CalculationAgent(None).run(self.snapshot)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(result['mode'], 'deterministic_fallback')

    def test_confirm_records_calculation_role_and_edit_discards_it(self):
        done = self.service.apply(command('confirm', self.draft))['state']
        self.assertEqual(done['calculation_role']['mode'], 'deterministic')
        self.assertEqual(done['status'], 'COMPLETED')
        edited = self.service.apply(command('edit',done))['state']
        self.assertIsNone(edited.get('calculation_role'))

    def result(self):
        return execute(self.snapshot,self.draft['review'],load_catalog(ROOT),propose_calculation(self.snapshot))

    def test_review_cannot_override_bad_numeric_result(self):
        result = self.result()
        result['outputs'][0]['value'] += 10
        result['result_hash'] = digest({k:v for k,v in result.items() if k!='result_hash'})
        with patch('planning.agents.role_model.LocalRoleSelector.__call__') as model:
            with self.assertRaisesRegex(ValueError, 'VALIDATION_FAILED'):
                ReviewAgent(None).run(result,self.snapshot)
            model.assert_not_called()

    def test_review_invalid_references_cannot_be_published_as_model_review(self):
        def selector(*args):
            return dict(output=dict(decision='caution', answer='路径损耗为 98.42 dB。', steps=[],
                                    opinions=[dict(kind='risk', text='需要核对。', refs=['invented'])]))
        result = self.result()
        assessment = ReviewAgent(selector).run(result,self.snapshot)
        self.assertEqual(assessment['role']['mode'],'deterministic_fallback')
        self.assertEqual(validate_assessment(assessment,result,self.snapshot)['decision'],'pass')
        result['result_id'] = 'other'
        with self.assertRaisesRegex(ValueError,'REVIEW_IDENTITY'):
            validate_assessment(assessment,result,self.snapshot)

    def test_review_out_of_scope_blocks_publication_and_preserves_readonly_result(self):
        def selector(*args):
            return dict(output=dict(decision='not_applicable', answer='所问的真实海面损耗超出自由空间基准。', steps=[],
                                    opinions=[dict(kind='risk', text='自由空间基准不含海面反射。', refs=['scope'])]))
        reviewer = ReviewAgent(selector)
        with patch('planning.workflow.planning_graph.ReviewAgent',return_value=reviewer):
            done = self.service.apply(command('confirm',self.draft))['state']
        self.assertEqual(done['status'],'NEEDS_MODEL')
        self.assertIsNone(done['final_report'])
        self.assertAlmostEqual(done['result']['outputs'][0]['value'],98.42059991327963)
        self.assertEqual(done['review_assessment']['role']['mode'],'stub')

    def test_a_caution_is_published_with_its_opinions_and_an_edit_clears_all_roles(self):
        def selector(*args):
            return dict(output=dict(decision='caution', answer='按自由空间基准，2 GHz、1 km 的路径损耗约为 98.42 dB。',
                                    opinions=[dict(kind='assumption', text='结果不含海面反射与遮挡。', refs=['scope'])],
                                    steps=[dict(id='step:fspl-step', note='按 ITU-R P.525-5 的自由空间公式计算。')]))
        with patch('planning.workflow.planning_graph.ReviewAgent',return_value=ReviewAgent(selector)):
            done=self.service.apply(command('confirm',self.draft))['state']
        self.assertEqual(done['status'],'COMPLETED')
        report = done['final_report']
        self.assertEqual((report['review']['decision'], report['review']['label']), ('caution', '请核对'))
        self.assertEqual(report['answer'], dict(text='按自由空间基准，2 GHz、1 km 的路径损耗约为 98.42 dB。', mode='stub', withheld=False))
        self.assertEqual(report['explanation'][0]['id'], 'step:fspl-step')
        self.assertTrue(report['conclusion'].startswith('按已确认自由空间条件'))
        edited=self.service.apply(command('edit',done))['state']
        for key in ('execution_results','review_history','calculation_roles','routing_decisions'):
            self.assertEqual(edited[key],[])
        self.assertIsNone(edited['review_assessment'])
        self.assertEqual(edited['calculation_attempts'],0)

    def test_transient_tool_failure_recovers_once_and_replay_never_reexecutes(self):
        from formula_rag import core
        evaluate = core.evaluate
        calls=[]
        def flaky(*args):
            calls.append(1)
            if len(calls)==1: raise TimeoutError('temporary')
            return evaluate(*args)
        c=command('confirm',self.draft)
        with patch('formula_rag.core.evaluate',side_effect=flaky):
            done=self.service.apply(c)['state']
            replay=self.service.apply(c)
        self.assertEqual(len(calls),2)
        self.assertEqual(done['status'],'COMPLETED')
        self.assertTrue(replay['replayed'])
        self.assertEqual(done['calculation_attempts'],2)
        self.assertEqual(len(done['execution_results']),1)
        self.assertEqual(done['routing_decisions'][0]['reason_code'],'transient_tool_retry')

    def test_persistent_transport_failure_and_hard_failure_are_bounded(self):
        for exc, count in [(TimeoutError('temporary'),2),(ValueError('DOMAIN_ERROR'),1)]:
            with self.subTest(exc=exc), patch('formula_rag.core.evaluate',side_effect=exc) as evaluate:
                done=self.service.apply(command('confirm',self.draft))['state']
                self.assertEqual(evaluate.call_count,count)
                self.assertEqual(done['status'],'FAILED')
                self.assertIsNone(done['final_report'])
            self.draft=self.service.apply(command())['state']

    def test_orchestrator_cannot_publish_unreviewed_or_unconfirmed_state(self):
        with self.assertRaisesRegex(ValueError,'REVIEW_REQUIRED'):
            decide(dict(status='VALIDATING_REPORT',calculation_attempts=1))
        with self.assertRaisesRegex(ValueError,'CONFIRMATION_REQUIRED'):
            decide(dict(status='RETRYABLE_CALCULATION_FAILURE',calculation_attempts=1))


if __name__ == '__main__': unittest.main()
