import copy
import importlib
from pathlib import Path
import unittest
from unittest.mock import patch
from test_requirements_contract import request

ROOT = Path(__file__).resolve().parents[1]


class GraphTests(unittest.TestCase):
    def module(self):
        try:
            return importlib.import_module('planning.workflow.requirements_graph')
        except ModuleNotFoundError:
            self.fail('requirements graph is not implemented')

    def agent(self):
        from planning.agents.requirements import RequirementsAgent
        return RequirementsAgent(ROOT, selector=False)

    def test_normal_trace_and_no_calculation(self):
        with patch('formula_rag.core.evaluate', side_effect=AssertionError('forbidden')):
            state = self.module().run_requirements(request(), self.agent())
        self.assertEqual(state['status'], 'AWAITING_CONFIRMATION')
        self.assertEqual([t['node'] for t in state['trace']], ['receive_request','propose_requirements','check_requirements','finish'])
        self.assertEqual(state['request'], request())

    def test_stale_and_bad_request_do_not_call_agent(self):
        a = self.agent()
        with patch.object(a, 'run', side_effect=AssertionError('called')):
            state = self.module().run_requirements(request(), a, expected_revision=9)
            self.assertEqual(state['status'], 'FAILED')
            self.assertEqual(state['trace'][0]['reason_code'], 'STALE_REVISION')
            self.assertIsNone(state['report'])

    def test_failure_has_visible_trace_and_no_report(self):
        a = self.agent()
        with patch.object(a, 'run', side_effect=OSError('broken')):
            state = self.module().run_requirements(request(), a)
        self.assertEqual(state['status'], 'FAILED')
        self.assertIsNone(state['report'])
        self.assertEqual(state['trace'][1]['reason_code'], 'AGENT_FAILED')

    def test_tampered_reports_fail_closed(self):
        a = self.agent(); q = request(); good = a.run(q)
        mutations = [lambda r: r['parameters_proposal'][0].update(value=999),
                     lambda r: r['evidence_refs'][0].update(content_hash='a'*64),
                     lambda r: r['evidence_refs'][0].update(source_url='https://fake.example'),
                     lambda r: r['candidate_models'][0].update(version='invented'),
                     lambda r: r['parameters_proposal'][0]['origins'][0].update(value=999),
                     lambda r: r['component_modes'].update(retrieval='dense'),
                     lambda r: r['component_modes'].update(interpretation='llm'),
                     lambda r: r.update(runtime_health='unavailable'),
                     lambda r: r.update(assumptions=[])]
        for mutate in mutations:
            bad = copy.deepcopy(good); mutate(bad)
            with self.subTest(mutation=mutate), patch.object(a, 'run', return_value=bad):
                state = self.module().run_requirements(q, a)
                self.assertEqual(state['status'], 'FAILED')
                self.assertIsNone(state['report'])

    def test_missing_conflict_scope_routes(self):
        for text, status in [('按自由空间基准求路径损耗，频率2GHz','AWAITING_INPUT'),
                             ('按自由空间基准求路径损耗，频率2GHz，频率3GHz，距离1km','AWAITING_INPUT'),
                             ('求真实海面传播损耗，频率2GHz，距离1km','NEEDS_MODEL')]:
            self.assertEqual(self.module().run_requirements(request(text),self.agent())['status'], status)

    def test_recheck_request_scope_even_if_report_omits_it(self):
        a=self.agent(); good=a.run(request())
        q=request(request()['raw_text']+'同时求真实海面传播损耗')
        with patch.object(a,'run',return_value=good):
            self.assertEqual(self.module().run_requirements(q,a)['status'],'FAILED')

    def test_rehashed_bad_plan_rejected_against_catalog(self):
        from planning.requirements_contract import digest
        a=self.agent(); q=request(); bad=a.run(q)
        plan=bad['calculation_plan_proposal']; plan['steps'][0]['expected_unit']='W'
        plan['plan_hash']=digest({k:v for k,v in plan.items() if k!='plan_hash'})
        with patch.object(a,'run',return_value=bad):
            self.assertEqual(self.module().run_requirements(q,a)['status'],'FAILED')

    def test_framework_budget_exception_is_visible(self):
        from langgraph.errors import GraphRecursionError
        g=self.module(); a=self.agent()
        with patch.object(g,'build_requirements_graph') as build:
            build.return_value.invoke.side_effect=GraphRecursionError('budget')
            s=g.run_requirements(request(),a)
        self.assertEqual(s['status'],'FAILED')
        self.assertEqual(s['trace'][0]['reason_code'],'STEP_LIMIT')

    def test_multiple_tasks_and_revisions_are_independent(self):
        a=self.agent(); q=request(); before=copy.deepcopy(q)
        first=self.module().run_requirements(q,a)
        second_request=request('按自由空间基准，频率3GHz，求路径损耗')
        second_request.update(task_id='another',request_id='another-request',revision=2)
        second=self.module().run_requirements(second_request,a,expected_revision=2)
        self.assertEqual(first['status'],'AWAITING_CONFIRMATION')
        self.assertEqual(second['status'],'AWAITING_INPUT')
        self.assertEqual(q,before)
        self.assertEqual(second['report']['revision'],2)

    def test_contrast_and_double_negation_do_not_hide_real_model_request(self):
        for suffix in ['不要只给基准而要计算实际海面传播损耗','不代表不需要计算实际海面传播损耗']:
            q=request(request()['raw_text']+suffix)
            self.assertNotEqual(self.module().run_requirements(q,self.agent())['status'],'AWAITING_CONFIRMATION')
