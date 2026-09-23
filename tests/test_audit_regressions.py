import tempfile
import unittest
from pathlib import Path
from tests.test_planning_loop import command, ROOT
from planning.workflow.task_service import TaskService


class AuditRegressionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.service=TaskService(ROOT,Path(self.tmp.name)/'audit.sqlite')

    def create(self, text, **extra):
        return self.service.apply(command(text=text,**extra))['state']

    def test_domain_to_scalar_replaces_entire_observation(self):
        for old, field, reply, expected in [('1-2km','distance_km','距离改为3km',3),
            ('2±0.1GHz','frequency_ghz','频率改为5GHz',5),
            ('2GHz或3GHz','frequency_ghz','频率改为5GHz',5),
            ('大约2GHz','frequency_ghz','频率改为5GHz',5)]:
            text='按自由空间基准，'+('频率2GHz，距离'+old if field=='distance_km' else '频率'+old+'，距离1km')+'，求路径损耗'
            with self.subTest(old=old):
                s=self.create(text)
                s=self.service.apply(command('supplement',s,message=reply,mode='deterministic'))['state']
                self.assertEqual(s['status'],'AWAITING_CONFIRMATION',s['request'])
                self.assertEqual(next(p['value'] for p in s['report']['parameters_proposal'] if p['canonical_name']==field),expected)
                done=self.service.apply(command('confirm',s))['state']
                self.assertEqual(done['result']['normalized_inputs'][field],expected)

    def test_quantity_labels_and_negative_intent_cannot_be_bypassed(self):
        for body in ['频率2GHz，天线高度1-2m','带宽1-2MHz，距离1km',
                     '频率2GHz，距离1km，不采用自由空间模型',
                     '频率2GHz，距离1km，不要计算路径损耗',
                     '频率2GHz，距离1km，距离大约3']:
            with self.subTest(body=body):
                s=self.create('按自由空间基准，'+body+'，求路径损耗')
                self.assertNotEqual(s['status'],'AWAITING_CONFIRMATION')
        s=self.create('',input=dict(raw_text='不要计算路径损耗，频率2GHz，距离1km',target='fspl_ghz',condition='free_space_reference',manual_parameters={}))
        self.assertNotEqual(s['status'],'AWAITING_CONFIRMATION')

    def test_answers_replace_unresolved_fragments_and_keep_original_history(self):
        for fragment,field,answer in [('频率不是2GHz','frequency_ghz','3GHz'),('距离2+-1','distance_km','0.9-1.1km')]:
            text='按自由空间基准，'+fragment+('，距离1km' if field=='frequency_ghz' else '，频率5GHz')+'，求路径损耗'
            s=self.create(text); issue=next(i for i in s['input_issues'] if i['field']==field)
            s=self.service.apply(command('answer',s,answers={issue['id']:answer},mode='deterministic'))['state']
            self.assertEqual(s['status'],'AWAITING_CONFIRMATION',s['request'])
            self.assertNotIn(fragment,s['request']['raw_text'])
            self.assertIn(fragment,s['conversation']['original_input']['raw_text'])

    def test_all_shape_transitions_and_multi_answer_offsets(self):
        shapes=['2GHz','1-3GHz','2GHz或3GHz']
        for old in shapes:
            for new in shapes:
                with self.subTest(old=old,new=new):
                    s=self.create('按自由空间基准，频率'+old+'，距离1km，求路径损耗。保留测试备注。')
                    s=self.service.apply(command('supplement',s,message='频率改为'+new,mode='deterministic'))['state']
                    self.assertEqual(s['status'],'AWAITING_CONFIRMATION',s['request'])
                    self.assertTrue(s['request']['raw_text'].endswith('保留测试备注。'))
                    done=self.service.apply(command('confirm',s))['state']
                    self.assertEqual(done['status'],'COMPLETED')
        s=self.create('按自由空间基准，频率大约2GHz，距离大约1km，求路径损耗')
        answers={i['id']:'3±0.1GHz' if i['field']=='frequency_ghz' else '2km' for i in s['input_issues']}
        s=self.service.apply(command('answer',s,answers=answers,mode='deterministic'))['state']
        self.assertEqual(s['status'],'AWAITING_CONFIRMATION')
        self.assertNotIn('大约',s['request']['raw_text'])

    def test_cancel_rolls_back_task_history_and_checkpoint(self):
        import threading
        from concurrent.futures import ThreadPoolExecutor
        from unittest.mock import patch
        from planning.agents.requirements import RequirementsAgent
        saved=self.create('按自由空间基准，频率2GHz，距离1km，求路径损耗')
        entered,release=threading.Event(),threading.Event()
        original=RequirementsAgent.run
        def slow(agent,*args,**kwargs):
            entered.set()
            if not release.wait(10):raise RuntimeError('test timed out')
            return original(agent,*args,**kwargs)
        c=command('edit',saved,text='按自由空间基准，频率5GHz，距离2km，求路径损耗')
        with patch.object(RequirementsAgent,'run',slow),ThreadPoolExecutor() as pool:
            future=pool.submit(self.service.apply,c)
            try:
                self.assertTrue(entered.wait(10))
                self.assertTrue(self.service.cancel_operation(c['task_id'],c['event_id'])['accepted'])
            finally:release.set()
            with self.assertRaisesRegex(ValueError,'OPERATION_CANCELLED'):future.result()
        self.assertEqual(self.service.get(saved['task_id']),saved)
        self.assertEqual(len(self.service.history(saved['task_id'])),1)
        self.assertEqual(self.service.activity.events(saved['task_id'])[-1]['phase'],'cancelled')
        restarted=TaskService(ROOT,self.service.store.path)
        done=restarted.apply(command('confirm',saved))['state']
        self.assertEqual(done['status'],'COMPLETED')
        self.assertEqual(done['result']['normalized_inputs']['frequency_ghz'],2)

    def test_independent_source_guard_rejects_wrong_physical_label(self):
        from planning.services.requirement_validation import check_source_labels
        for text,field in [('天线高度1-2m','distance_km'),('带宽1-2MHz','frequency_ghz')]:
            with self.subTest(text=text),self.assertRaisesRegex(ValueError,'SOURCE_LABEL_MISMATCH'):
                check_source_labels([dict(canonical_name=field,origins=[dict(kind='user_text',span=[4,len(text)])])],text)
