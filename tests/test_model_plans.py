import copy
from pathlib import Path
import unittest
import uuid
from planning.agents.requirements import RequirementsAgent
from planning.agents.planner import PlanningAgent, compile_proposal, proposal_for
from planning.agents.planner import validate_assessment
from planning.services.requirement_validation import check_report
from formula_rag.catalog import load_catalog
from planning.requirements_contract import digest

ROOT=Path(__file__).resolve().parents[1]


class ModelPlanTests(unittest.TestCase):
    def setUp(self):
        self.cards=load_catalog(ROOT)
        self.request=dict(schema_version='1.0.0',task_id=str(uuid.uuid4()),revision=0,request_id=str(uuid.uuid4()),
            raw_text='按自由空间基准，频率2GHz，距离1km，求路径损耗。',manual_parameters={},condition=None,target=None)
        self.report=RequirementsAgent(ROOT,selector=False).run(self.request)
        self.assertEqual(self.report['execution_status'],'AWAITING_CONFIRMATION')

    def test_model_selects_steps_and_program_bindings_are_replayed_at_confirmation(self):
        seen=[]
        def model(role,prompt,view,schema):
            seen.append(view)
            self.assertNotIn('allowed_call',view)
            self.assertNotIn('plan',view)
            return dict(output=proposal_for(self.report),model='fake',usage={'total_tokens':1})
        plan,role=PlanningAgent(model).run(self.request,self.report,self.cards)
        self.assertEqual(role['mode'],'stub')
        checked=copy.deepcopy(self.report);checked.update(calculation_plan_proposal=plan,planning_role=role)
        check_report(checked,self.request,self.cards,ROOT)
        self.assertEqual(len(seen),1)
        checked['planning_role']['proposal']['steps'][0]['why']='预测损耗9999 dB'
        with self.assertRaises(ValueError):check_report(checked,self.request,self.cards,ROOT)

    def test_bad_plans_retry_once_then_fall_back_without_executing(self):
        attempts=[]
        def bad(*args):
            attempts.append(1);p=proposal_for(self.report);p['steps'][0]['why']='预测损耗9999 dB'
            return dict(output=p)
        plan,role=PlanningAgent(bad).run(self.request,self.report,self.cards)
        self.assertEqual(len(attempts),2)
        self.assertEqual(role['mode'],'deterministic_fallback')
        self.assertEqual(plan['steps'],self.report['calculation_plan_proposal']['steps'])
        self.assertEqual(plan['origin'],'program')

    def test_assessment_rewrite_keeps_plan_and_hides_only_failed_note(self):
        calls=[]
        def model(*args):
            calls.append(args)
            p=proposal_for(self.report)
            p['assessment']['notes'].append(dict(kind='assumption',text='损耗9999 dB',refs=['target']))
            return dict(output=p)
        plan,role=PlanningAgent(model).run(self.request,self.report,self.cards)
        self.assertEqual(len(calls),2)
        self.assertEqual(calls[0][0],'compute_agent')
        self.assertEqual(plan['origin'],'model')
        self.assertEqual(plan['assessment']['mode'],'stub')
        self.assertFalse(plan['assessment']['notes'][0].get('withheld',False))
        self.assertTrue(plan['assessment']['notes'][1]['withheld'])
        self.assertIsNone(plan['assessment']['notes'][1]['text'])
        checked=copy.deepcopy(self.report);checked.update(calculation_plan_proposal=plan,planning_role=role)
        check_report(checked,self.request,self.cards,ROOT)
        checked['planning_role']['proposal']['assessment']['notes'][1]['text']='篡改隐藏条目'
        with self.assertRaisesRegex(ValueError,'ASSESSMENT_TEXT'):
            check_report(checked,self.request,self.cards,ROOT)

    def test_assessment_can_be_repaired_on_second_attempt(self):
        calls=[]
        def model(*args):
            p=proposal_for(self.report);calls.append(1)
            if len(calls)==1:p['assessment']['notes'][0]['text']='损耗9999 dB'
            return dict(output=p)
        plan,role=PlanningAgent(model).run(self.request,self.report,self.cards)
        self.assertEqual(role['attempts'],2)
        self.assertNotIn('withheld',plan['assessment']['notes'][0])
        self.assertEqual(plan['origin'],'model')

    def test_all_assessment_notes_hidden_means_skipped_without_losing_plan(self):
        def model(*args):
            p=proposal_for(self.report);p['assessment']['notes'][0]['text']='损耗9999 dB'
            return dict(output=p)
        plan,role=PlanningAgent(model).run(self.request,self.report,self.cards)
        self.assertEqual(plan['origin'],'model')
        self.assertEqual(plan['assessment']['mode'],'skipped')
        self.assertTrue(plan['assessment']['notes'][0]['withheld'])
        checked=copy.deepcopy(self.report);checked.update(calculation_plan_proposal=plan,planning_role=role)
        check_report(checked,self.request,self.cards,ROOT)

    def test_bad_assessment_refs_do_not_reject_valid_plan(self):
        def model(*args):
            p=proposal_for(self.report);p['assessment']['notes'][0]['refs']=['invented']
            return dict(output=p)
        plan,role=PlanningAgent(model).run(self.request,self.report,self.cards)
        self.assertEqual(role['attempts'],2)
        self.assertEqual(plan['origin'],'model')
        self.assertEqual(plan['assessment']['mode'],'skipped')
        checked=copy.deepcopy(self.report);checked.update(calculation_plan_proposal=plan,planning_role=role)
        check_report(checked,self.request,self.cards,ROOT)

    def test_assessment_rewrite_transport_failure_keeps_valid_first_plan(self):
        calls=[]
        def model(*args):
            calls.append(1)
            if len(calls)==2:raise OSError('offline during rewrite')
            p=proposal_for(self.report);p['assessment']['notes'][0]['text']='损耗9999 dB'
            return dict(output=p)
        plan,role=PlanningAgent(model).run(self.request,self.report,self.cards)
        self.assertEqual(plan['origin'],'model')
        self.assertEqual(plan['assessment']['mode'],'skipped')
        checked=copy.deepcopy(self.report);checked.update(calculation_plan_proposal=plan,planning_role=role)
        check_report(checked,self.request,self.cards,ROOT)

    def test_origin_reasons_are_readable_and_target_specific(self):
        from planning.agents.planner import origin_note
        for code,text in [('PLAN_MISSING_RADIO_HORIZON','缺视距一步'),('PLAN_UNUSED_STEP','有用不到的步骤'),('PLAN_TARGET','最后一步不是链路余量')]:
            role=dict(diagnostics=[dict(code='MODEL_OUTPUT_INVALID',reason=code)])
            self.assertEqual(origin_note(role,dict(steps=[dict(tool_id='link_margin')])),text)

    def test_offline_and_deterministic_have_no_rejection_note(self):
        def offline(*args):raise OSError('offline')
        for selector in (False,offline):
            plan,role=PlanningAgent(selector).run(self.request,self.report,self.cards)
            self.assertEqual(plan['origin'],'program')
            self.assertNotIn('origin_note',plan)
            self.assertEqual(plan['assessment']['mode'],'skipped')

    def test_pending_questions_skip_planner_and_keep_program_preview(self):
        from unittest.mock import Mock
        from langgraph.checkpoint.memory import MemorySaver
        from planning.workflow.planning_graph import build_planning_graph
        planner=Mock();planner.run.side_effect=AssertionError('must not call model')
        graph=build_planning_graph(RequirementsAgent(ROOT,selector=False),MemorySaver(),self.cards,
            pending_questions=['请裁决来源冲突'],planning_agent=planner)
        state=graph.invoke(dict(request=self.request,trace=[]),dict(configurable=dict(thread_id=str(uuid.uuid4()))))
        self.assertEqual(state['status'],'AWAITING_INPUT')
        self.assertIn('请裁决来源冲突',state['report']['questions'])
        self.assertNotIn('planning_role',state['report'])
        plan=state['report']['calculation_plan_proposal']
        self.assertNotIn('origin',plan)
        self.assertNotIn('assessment',plan)
        planner.run.assert_not_called()

    def test_unverified_and_invented_cards_are_blocked(self):
        p=proposal_for(self.report)
        cards=copy.deepcopy(self.cards)
        next(c for c in cards if c['id']=='fspl_ghz')['status']='draft'
        with self.assertRaisesRegex(ValueError,'MODEL_NOT_VERIFIED'):compile_proposal(p,self.report,cards)
        p['steps'][0]['card']='invented'
        with self.assertRaisesRegex(ValueError,'MODEL_NOT_VERIFIED'):compile_proposal(p,self.report,self.cards)

    def test_assessment_cannot_create_unsupported_numbers_or_refs(self):
        for note in [dict(kind='goal',text='结果为9999 dB',refs=['target']),dict(kind='goal',text='请填写',refs=['invented'])]:
            with self.assertRaises(ValueError):validate_assessment(dict(verdict='review',notes=[note]),self.report)
        result=validate_assessment(dict(verdict='review',notes=[dict(kind='goal',text='计划回答路径损耗',refs=['target'])]),self.report)
        self.assertEqual(result['verdict'],'review')

    def test_advisory_review_allows_confirmation_without_another_compute_model_call(self):
        import tempfile
        from unittest.mock import patch
        from tests.test_planning_loop import command
        from planning.workflow.task_service import TaskService
        calls=[]
        def selector(role,prompt,view,schema):
            calls.append(role)
            return dict(output=proposal_for(self.report))
        with tempfile.TemporaryDirectory() as tmp:
            service=TaskService(ROOT,Path(tmp)/'tasks.sqlite')
            with patch('planning.workflow.planning_graph.PlanningAgent',return_value=PlanningAgent(selector)):
                draft=service.apply(command())['state']
            self.assertEqual(draft['status'],'AWAITING_CONFIRMATION')
            self.assertEqual(draft['report']['calculation_plan_proposal']['assessment']['verdict'],'review')
            self.assertIsNone(draft['result'])
            with patch('planning.agents.role_model.LocalRoleSelector.__call__',side_effect=AssertionError('unexpected model')):
                done=service.apply(command('confirm',draft))['state']
            self.assertEqual(done['status'],'COMPLETED')
            self.assertEqual(calls,['compute_agent'])


class PlanFactsTests(unittest.TestCase):
    """What the compute agent sees for the demo question, and which numbers it may quote (§2a, H4)."""
    def setUp(self):
        from test_requirement_facts import ask, labeller
        self.cards=load_catalog(ROOT)
        text=ask('B')
        self.request=dict(schema_version='1.0.0',task_id=str(uuid.uuid4()),revision=0,request_id=str(uuid.uuid4()),
            raw_text=text,manual_parameters={},condition=None,target=None)
        self.report=RequirementsAgent(ROOT,selector=labeller(text,'B')).run(self.request)
        self.assertEqual(self.report['execution_status'],'AWAITING_CONFIRMATION')

    def output(self,**notes):
        """A model answer in the shape the schema asks for: one entry per kind."""
        steps=[dict(card=s['tool_id'],why='按登记公式连接所需物理量') for s in self.report['calculation_plan_proposal']['steps']]
        assessment=dict(verdict='ready',
            goal=dict(text='计算链路余量并与 10 dB 要求比较，低于要求时反求发射功率。',refs=['question','requirement','solve']),
            applicability=dict(text='A站在海岸、B站在海岛，路径跨海面；自由空间未计海面反射与多径，结果偏乐观。',refs=['site:sim-a','site:sim-b']),
            assumption=dict(text='馈线损耗每端按假设取 2 dB，实际取决于馈线长度与型号。',refs=['tx_loss_db','rx_loss_db']))
        assessment.update(notes)
        return dict(steps=steps,assessment=assessment)

    def run_model(self,*outputs):
        seen=[]
        def model(role,prompt,view,schema):
            seen.append((view,schema))
            return dict(output=copy.deepcopy(outputs[min(len(seen),len(outputs))-1]))
        plan,role=PlanningAgent(model).run(self.request,self.report,self.cards)
        return plan,role,seen

    def replay(self,plan,role):
        checked=copy.deepcopy(self.report);checked.update(calculation_plan_proposal=plan,planning_role=role)
        return check_report(checked,self.request,self.cards,ROOT)

    def test_the_agent_sees_the_task_facts_in_words_and_not_the_program_chain(self):
        plan,role,seen=self.run_model(self.output())
        view,schema=seen[0]
        facts=view['facts']
        self.assertEqual(set(facts),{'question','target','requirement','solve','conditions','sites','radios','inputs','assumed','cards'})
        self.assertEqual([(s['name'],s['end'],s['environment']) for s in facts['sites']],
                         [('A站','发射端','海岸'),('B站','接收端','海岛')])
        self.assertEqual(facts['radios'][0]['rated_tx_power'],dict(value=37,unit='dBm'))
        sources={i['id']:i['source'] for i in facts['inputs']}
        self.assertEqual((sources['frequency_ghz'],sources['tx_loss_db'],sources['lat1_deg']),
                         ('原文“2 GHz”','假设（卡片默认值）','站点库 A站'))
        self.assertEqual(list(schema['properties']['assessment']['properties']),['verdict','goal','applicability','assumption'])
        self.assertEqual([n['kind'] for n in plan['assessment']['notes']],['goal','applicability','assumption'])
        self.assertEqual((plan['origin'],role['agrees_with_program']),('model',True))
        self.replay(plan,role)

    def test_a_task_with_nothing_assumed_and_no_radio_is_offered_no_assumption_note(self):
        request=dict(self.request,raw_text='按自由空间基准，频率2GHz，距离1km，求路径损耗。')
        report=RequirementsAgent(ROOT,selector=False).run(request)
        schemas=[]
        def model(role,prompt,view,schema):
            schemas.append(schema)
            return dict(output=proposal_for(report))
        PlanningAgent(model).run(request,report,self.cards)
        self.assertEqual(list(schemas[0]['properties']['assessment']['properties']),['verdict','goal','applicability'])

    def test_a_note_may_quote_a_record_value_it_was_shown_and_a_changed_number_fails_the_replay(self):
        note=dict(text='XX-100 额定发射功率 37 dBm，频段 1.4–2.7 GHz，2 GHz 在频段内。',refs=['device:sim-xx100','frequency_ghz'])
        plan,role,_=self.run_model(self.output(assumption=note))
        self.assertEqual((role['attempts'],plan['assessment']['notes'][2]['text']),(1,note['text']))
        self.replay(plan,role)
        for held in (role['proposal']['assessment']['notes'][2],plan['assessment']['notes'][2]):
            held['text']='XX-100 额定发射功率 38 dBm。'
        plan['plan_hash']=digest({k:v for k,v in plan.items() if k!='plan_hash'})
        with self.assertRaisesRegex(ValueError,'ASSESSMENT_NUMBERS'):
            self.replay(plan,role)

    def test_notes_are_listed_goal_first_and_cite_each_fact_once(self):
        out=self.output()
        a=out['assessment']
        out['assessment']=dict(verdict='ready',assumption=a['assumption'],applicability=a['applicability'],
                               goal=dict(a['goal'],refs=['question','question']))
        plan,role,_=self.run_model(out)
        self.assertEqual([n['kind'] for n in plan['assessment']['notes']],['goal','applicability','assumption'])
        self.assertEqual(plan['assessment']['notes'][0]['refs'],['question'])
        self.replay(plan,role)

    def test_a_text_cut_off_at_its_cap_is_rewritten(self):
        plan,role,seen=self.run_model(self.output(applicability=dict(text='海'*60,refs=['site:sim-b'])),self.output())
        self.assertEqual(role['attempts'],2)
        self.assertIn('截断',seen[1][0]['correction'])
        self.assertFalse(any(n.get('withheld') for n in plan['assessment']['notes']))
        cut=self.output()
        cut['steps'][0]['why']='由'*20
        plan,role,_=self.run_model(cut)
        self.assertEqual((plan['origin'],plan.get('origin_note')),('program','步骤理由不符合字数要求'))


    def test_a_rewrite_that_breaks_the_plan_keeps_the_plan_that_passed(self):
        broken=self.output()
        broken['steps']=[s for s in broken['steps'] if s['card']!='radio_horizon']
        plan,role,_=self.run_model(self.output(goal=dict(text='余量 9999 dB',refs=['question'])),broken)
        self.assertEqual((role['attempts'],plan['origin']),(2,'model'))
        self.assertEqual([s['tool_id'] for s in plan['steps']],self.report['calculation_plan_proposal']['selected_model'])
        self.assertTrue(plan['assessment']['notes'][0]['withheld'])
        self.replay(plan,role)

if __name__=='__main__':unittest.main()
