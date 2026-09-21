import importlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from test_planning_loop import ROOT, command


class PlanningWebTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        try:
            module=importlib.import_module('planning.web_server')
        except ModuleNotFoundError:
            self.fail('planning web server not implemented')
        self.server=module.create_server(ROOT,Path(self.tmp.name)/'web.sqlite',port=0)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.addCleanup(self.stop)
        self.base=f'http://127.0.0.1:{self.server.server_port}'
        self.token=self.call('/api/session')[1]['token']

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=5)

    def call(self,path,body=None,headers=None,raw=None):
        h={'Content-Type':'application/json'}
        if hasattr(self,'token'):
            h['X-Planning-Token']=self.token
        h.update(headers or {})
        data=raw if raw is not None else json.dumps(body).encode() if body is not None else None
        req=Request(self.base+path,data=data,headers=h)
        try:
            response=urlopen(req,timeout=15)
        except HTTPError as e:
            response=e
        with response:
            payload=response.read().decode()
            return response.status,json.loads(payload) if response.headers.get_content_type()=='application/json' else payload

    def test_http_loop_and_readback(self):
        code,draft=self.call('/api/commands',command())
        self.assertEqual(code,200)
        s=draft['state']
        code,done=self.call('/api/commands',command('confirm',s))
        self.assertEqual(done['state']['status'],'COMPLETED')
        self.assertEqual(self.call('/api/tasks/'+s['task_id'])[1]['state'],done['state'])
        self.assertEqual(len(self.call('/api/tasks/'+s['task_id']+'/history')[1]['history']),2)

    def test_stale_is_conflict_and_injection_is_bad_request(self):
        s=self.call('/api/commands',command())[1]['state']
        self.call('/api/commands',command('edit',s))
        code,body=self.call('/api/commands',command('confirm',s))
        self.assertEqual(code,409)
        self.assertEqual(body['error']['code'],'STALE_REVISION')
        self.assertEqual(self.call('/api/commands',command(result={}))[0],400)

    def test_cross_origin_missing_token_and_host_rejected(self):
        for h in ({'Origin':'https://evil.example'}, {'X-Planning-Token':'wrong'}, {'Host':'evil.example'}):
            with self.subTest(headers=h):
                self.assertEqual(self.call('/api/commands',command(),headers=h)[0],403)
        self.assertEqual(self.call('/api/commands',command(),headers={'Origin':self.base})[0],200)

    def test_strict_json_size_and_static_allowlist(self):
        for raw in (b'{"action":"create","action":"confirm"}', b'{"value":NaN}', b'\xff', b'x'*70000):
            self.assertIn(self.call('/api/commands',raw=raw)[0],{400,413})
        self.assertEqual(self.call('/../../knowledge/formulas.json')[0],404)
        self.assertEqual(self.call('/api/tasks/no-such-task')[0],404)
        code,html=self.call('/')
        self.assertEqual(code,200)
        self.assertIn('通信筹划',html)
        self.assertEqual(self.call('/app.js')[0],200)
        self.assertEqual(self.call('/text.mjs')[0],200)

    def test_activity_endpoint_does_not_require_committed_task(self):
        self.assertEqual(self.call('/api/tasks/future-task/activity')[1]['events'],[])
        c=command()
        self.call('/api/commands',c)
        code,body=self.call('/api/tasks/'+c['task_id']+'/activity')
        self.assertEqual(code,200)
        self.assertEqual(body['events'][-1]['phase'],'committed')
        self.assertEqual(self.call('/api/tasks/'+c['task_id']+'/activity',headers={'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.call('/api/tasks/bad!id/activity')[0],400)


if __name__=='__main__':
    unittest.main()
