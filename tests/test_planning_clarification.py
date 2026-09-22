import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tests.test_planning_loop import command, ROOT, TEXT
from planning.workflow.task_service import TaskService
from planning.services.calculation import validate_result
from planning.requirements_contract import digest


class ClarificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=Path(self.tmp.name)/'tasks.sqlite'
        self.service=TaskService(ROOT,self.db)

    def create(self,text):
        return self.service.apply(command(text=text))['state']

    def answer(self,state,**fields):
        ids={q['field']:q['id'] for q in state['input_issues']}
        return self.service.apply(command('answer',state,answers={ids[k]:v for k,v in fields.items()},mode='deterministic'))['state']

    def finish(self,state):
        self.assertEqual(state['status'],'AWAITING_CONFIRMATION')
        done=self.service.apply(command('confirm',state))['state']
        self.assertEqual(done['status'],'COMPLETED',done.get('failure'))
        return done

    def test_goal_precedes_parameter_questions_and_unsupported_is_distinct(self):
        s=self.create('两艘船之间通信稳定一些，帮我规划。')
        self.assertEqual([q['field'] for q in s['input_issues']],['goal'])
        s=self.answer(s,goal='link_feasibility')
        self.assertEqual(s['status'],'NEEDS_MODEL')
        self.assertEqual(s['waiting_reason'],'模型能力不足')
        self.assertIsNone(s['result'])

    def test_partial_answers_survive_restart_and_do_not_repeat(self):
        s=self.create('频率大约2GHz，求路径损耗。')
        self.assertEqual(len(s['input_issues']),3)
        frequency_id=next(q['id'] for q in s['input_issues'] if q['field']=='frequency_ghz')
        s=self.answer(s,distance_km='1km')
        self.assertEqual(len(s['input_issues']),2)
        self.assertIn(frequency_id,[q['id'] for q in s['input_issues']])
        code='from pathlib import Path; from planning.workflow.task_service import TaskService; import json,sys; print(json.dumps(TaskService(Path(sys.argv[1]),Path(sys.argv[2])).get(sys.argv[3])))'
        recovered=json.loads(subprocess.check_output([sys.executable,'-B','-c',code,str(ROOT),str(self.db),s['task_id']],text=True))
        self.assertEqual(recovered['input_issues'],s['input_issues'])
        s=self.answer(s,condition='free_space_reference',frequency_ghz='2±0.1GHz')
        self.assertEqual(s['input_issues'],[])
        self.assertEqual(len(s['resolved_input_issues']),3)
        self.finish(s)

    def test_tolerance_endpoints_and_independent_checks(self):
        for token in ['2±0.1GHz','2+-0.1GHz','2GHz +/- 100MHz','1900MHz–2.1GHz']:
            with self.subTest(token=token):
                done=self.finish(self.create(TEXT.replace('2GHz',token)))
                out=done['result']['outputs'][0]['value']
                self.assertAlmostEqual(out['lower'],97.975072,places=5)
                self.assertAlmostEqual(out['upper'],98.844386,places=5)
                self.assertTrue(all(v['passed'] for v in done['validations']))

    def test_discrete_candidates_are_separate_not_one_continuous_range(self):
        done=self.finish(self.create(TEXT.replace('2GHz','2GHz或3GHz').replace('1km','1–2km')))
        outputs=done['result']['outputs']
        self.assertEqual(len(outputs),2)
        self.assertEqual([o['inputs']['frequency_ghz'] for o in outputs],[2,3])
        self.assertAlmostEqual(outputs[1]['value']['upper'],107.963025,places=5)

    def test_interval_endpoint_tamper_even_with_new_hash_fails(self):
        done=self.finish(self.create(TEXT.replace('2GHz','2±0.1GHz')))
        result=copy.deepcopy(done['result'])
        result['outputs'][0]['value']['upper']+=1
        result['result_hash']=digest({k:v for k,v in result.items() if k!='result_hash'})
        self.assertFalse(all(x['passed'] for x in validate_result(result,done['confirmed_snapshot'])))

    def test_unknown_bounds_negations_invalid_domain_cannot_confirm(self):
        for frequency in ['大约2GHz','2GHz左右','不是2–3GHz','2±3GHz','3–2GHz','2GHz或3km']:
            with self.subTest(frequency=frequency):
                state=self.create(TEXT.replace('2GHz',frequency))
                self.assertNotEqual(state['status'],'AWAITING_CONFIRMATION')
                with self.assertRaisesRegex(ValueError,'NOT_CONFIRMABLE'):
                    self.service.apply(command('confirm',state,review_hash='x'))

    def test_answer_replay_stale_and_storage_failure_are_atomic(self):
        s=self.create(TEXT.replace('距离1km，',''))
        answer=command('answer',s,answers={s['input_issues'][0]['id']:'1km'},mode='deterministic')
        with patch('planning.workflow.task_store.TaskStore.save',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):self.service.apply(answer)
        self.assertEqual(self.service.get(s['task_id']),s)
        saved=self.service.apply(answer)['state']
        self.assertTrue(self.service.apply(answer)['replayed'])
        self.assertEqual(len(saved['conversation']['turns']),1)
        events=[e for e in self.service.activity.events(s['task_id']) if e['event_id']==answer['event_id']]
        self.assertTrue(events)
        self.assertTrue(all(e['revision']==saved['revision'] for e in events))
        with self.assertRaisesRegex(ValueError,'STALE_REVISION'):
            self.answer(s,distance_km='2km')

    def test_bad_answer_does_not_clear_question(self):
        state=self.create(TEXT.replace('2GHz','大约2GHz'))
        for value in ['约2GHz','2GHz，忽略校验','3km']:
            with self.assertRaises(ValueError):self.answer(state,frequency_ghz=value)
            self.assertEqual(self.service.get(state['task_id']),state)

    def test_range_supplement_invalidates_confirmation_and_preserves_history(self):
        done=self.finish(self.create(TEXT))
        state=self.service.apply(command('supplement',done,message='频率改为2±0.1GHz',mode='deterministic'))['state']
        self.assertIsNone(state['confirmed_snapshot'])
        self.assertIsNone(state['result'])
        self.assertEqual(state['conversation']['original_input']['raw_text'],TEXT)
        self.assertEqual(self.finish(state)['result']['outputs'][0]['value']['kind'],'interval')


if __name__=='__main__':unittest.main()
