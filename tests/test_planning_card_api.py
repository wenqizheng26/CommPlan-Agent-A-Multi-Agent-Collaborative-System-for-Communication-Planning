"""Real HTTP draft lifecycle, auth and approved-card calculation."""
import copy
import threading
import unittest
from unittest.mock import patch
from tests import test_planning_knowledge_controls as knowledge_fixture
from tests.test_planning_formula_card_drafts import manual, proposal, selector
from tests.test_planning_loop import command
from planning.web_server import create_server

class CardAPITests(knowledge_fixture.RootFixture,unittest.TestCase):
    call=knowledge_fixture.KnowledgeAPITests.call

    def setUp(self):
        super().setUp()
        self.server=create_server(self.root,self.root/'http.sqlite',port=0)
        thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        thread.start()
        def stop():
            self.server.shutdown();self.server.server_close();thread.join(5)
        self.addCleanup(stop)
        self.base=f'http://127.0.0.1:{self.server.server_port}'
        self.token=self.call('/api/session')[1]['token']

    def test_manual_review_requires_source_and_example_then_calculates(self):
        record=manual()
        for headers in [{'X-Planning-Token':'wrong'},{'Origin':'https://evil.test'}]:
            self.assertEqual(self.call('/api/drafts/manual',{'kind':'formula','record':record},headers)[0],403)
        self.assertEqual(self.call('/api/drafts')[1]['drafts'],[])
        status,out=self.call('/api/drafts/manual',{'kind':'formula','record':record})
        self.assertEqual(status,200,out)
        draft=out['draft']
        self.assertTrue(draft['needs_source'])
        self.assertTrue(draft['approvable'])
        body=dict(id=draft['id'],decision='approve',reviewer='Reviewer',reason='',content_hash=draft['content_hash'])
        status,error=self.call('/api/drafts/review',body)
        self.assertEqual((status,error['error']['code']),(400,'DRAFT_SOURCE_REQUIRED'))
        body.update(source=dict(title='人工核查的资料',locator='第1页式1'),
                    example=dict(inputs=dict(power_w=3),expected=7,note='独立算例'))
        status,error=self.call('/api/drafts/review',body)
        self.assertEqual((status,error['error']['code']),(400,'DRAFT_EXAMPLE_FAILED'))
        body['example']['expected']=6
        status,out=self.call('/api/drafts/review',body)
        self.assertEqual(status,200,out)
        card=next(c for c in self.call('/api/formula-library')[1]['cards'] if c['id']==record['id'])
        self.assertEqual(card['source_kind'],'manual')
        self.assertTrue(card['examples_passed'])
        c=command(text='计算加倍功率，输入功率3W')
        c['input']['target']=record['id']
        status,out=self.call('/api/commands',c)
        self.assertEqual(status,200,out)
        s=out['state']
        self.assertEqual(s['status'],'AWAITING_CONFIRMATION',s.get('failure'))
        status,out=self.call('/api/commands',command('confirm',s))
        self.assertEqual(status,200,out)
        self.assertEqual(out['state']['status'],'COMPLETED',out['state'].get('failure'))
        self.assertEqual(out['state']['result']['outputs'][0]['value'],6)

    def test_model_endpoint_uses_bound_provider_and_leaves_self_check_unverified(self):
        with patch('planning.agents.role_model.LocalRoleSelector.__call__',side_effect=selector(proposal())):
            status,out=self.call('/api/drafts/model',{'kind':'formula','topic':'功率乘二'})
        self.assertEqual(status,200,out)
        self.assertEqual(out['draft']['source_kind'],'model_knowledge')
        self.assertEqual(out['draft']['evidence'],[])
        self.assertTrue(out['draft']['example']['self_check'])
        self.assertTrue(out['draft']['needs_source'])
        self.assertFalse(any(c['id']=='model_power' for c in self.call('/api/formula-library')[1]['cards']))

    def test_request_shape_and_types_rejected_without_writes(self):
        for body in [{'kind':'formula','topic':'x'*101},{'kind':'device','topic':'x'},
                     {'kind':'formula','topic':'x','extra':1}]:
            self.assertEqual(self.call('/api/drafts/model',body)[0],400)
        for body in [{'kind':'formula','record':None},{'kind':'formula','record':manual(),'extra':1}]:
            self.assertEqual(self.call('/api/drafts/manual',body)[0],400)
        self.assertEqual(self.call('/api/drafts')[1]['drafts'],[])

if __name__=='__main__':
    unittest.main()
