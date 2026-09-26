import importlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from test_planning_loop import ROOT, command


class PlanningWebTests(unittest.TestCase):
    def test_facts_are_read_only_reviewed_and_same_origin(self):
        code, data=self.call('/api/facts')
        self.assertEqual(code,200)
        self.assertEqual(len(data['records']),9)
        self.assertEqual(len(data['version']),64)
        for row in data['records']:
            self.assertTrue(row['simulated'])
            self.assertEqual(set(row['source']),{'title','version','locator'})
        self.assertEqual(self.call('/api/facts',headers={'Origin':'https://evil.example'})[0],403)
        self.assertNotEqual(self.call('/api/facts',body={})[0],200)

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
        self.assertEqual(self.call('/progress.mjs')[0],200)

    def test_activity_endpoint_does_not_require_committed_task(self):
        self.assertEqual(self.call('/api/tasks/future-task/activity')[1]['events'],[])
        c=command()
        self.call('/api/commands',c)
        code,body=self.call('/api/tasks/'+c['task_id']+'/activity')
        self.assertEqual(code,200)
        self.assertEqual(body['events'][-1]['phase'],'committed')
        self.assertEqual(self.call('/api/tasks/'+c['task_id']+'/activity',headers={'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.call('/api/tasks/bad!id/activity')[0],400)

    def test_live_model_status_is_separate_and_origin_checked(self):
        with patch('planning.web_server.probe_model', return_value={'status':'ready','checked_at':'now'}) as probe:
            self.assertEqual(self.call('/api/model-status')[1]['status'],'ready')
            self.assertEqual(self.call('/api/model-status',headers={'Origin':'https://evil.example'})[0],403)
            probe.assert_called_once()
        self.assertEqual(self.call('/model-status.mjs')[0],200)

    def test_task_list_build_identity_and_cancel_endpoint(self):
        from planning.build_info import build_fingerprint
        self.assertEqual(self.call('/api/session')[1]['build'],build_fingerprint(ROOT))
        saved=self.call('/api/commands',command())[1]['state']
        rows=self.call('/api/tasks')[1]['tasks']
        self.assertEqual(rows[0]['task_id'],saved['task_id'])
        self.assertNotIn('report',rows[0])
        body=dict(task_id=saved['task_id'],event_id='already-finished')
        self.assertFalse(self.call('/api/cancel-operation',body)[1]['accepted'])
        self.assertEqual(self.call('/api/cancel-operation',body,headers={'X-Planning-Token':'bad'})[0],403)

    def test_formula_cards_match_task_evidence_by_content_hash(self):
        budget='按自由空间基准计算链路余量：频率2GHz，距离10km，发射功率30dBm，发射天线增益10dBi，接收天线增益10dBi，发射馈线损耗2dB，接收馈线损耗2dB，额外损耗0dB，接收灵敏度-100dBm，预留余量10dB。'
        state=self.call('/api/commands',command(text=budget))[1]['state']
        steps=state['report']['calculation_plan_proposal']['steps']
        ids=[s['tool_id'] for s in steps]
        self.assertEqual(ids,['fspl_ghz','received_power','link_margin'])
        code,body=self.call('/api/formula-cards?ids='+','.join(ids+['no_such_card']))
        self.assertEqual(code,200)
        self.assertEqual(body['missing'],['no_such_card'])
        served={c['id']:c for c in body['cards']}
        for ref in state['report']['evidence_refs']:
            self.assertEqual(served[ref['catalog_id']]['content_hash'],ref['content_hash'])
        # The card stored in the review is the same registered card.
        model=state['review']['model']
        self.assertEqual(served[model['id']]['expression'],model['expression'])
        for bad in ('','?ids=','?ids=Bad-Id','?ids='+','.join(['a']*21)):
            with self.subTest(query=bad):
                self.assertEqual(self.call('/api/formula-cards'+bad)[0],400)
        self.assertEqual(self.call('/api/formula-cards?ids=fspl_ghz',headers={'Origin':'https://evil.example'})[0],403)

    def test_program_tool_card_exposes_algorithm_and_source_without_expression(self):
        code, body = self.call('/api/formula-cards?ids=slant_range_wgs84')
        self.assertEqual(code, 200)
        card = body['cards'][0]
        self.assertEqual(card['kind'], 'python_tool')
        self.assertIn('ECEF', card['algorithm'])
        self.assertNotIn('expression', card)
        self.assertTrue(card['sources'][0]['url'])
        self.assertEqual(len(card['content_hash']), 64)

    def test_models_settings_and_metrics_endpoints(self):
        with patch('planning.web_server.probe_registry', return_value={'qwen3-4b-q4': 'unreachable'}):
            code, models = self.call('/api/models')
        self.assertEqual(code, 200)
        self.assertEqual(models['defaults']['chat'], 'qwen35-9b-q4')
        self.assertIn('bge-small-zh-v1.5', models['embeddings'])
        self.assertEqual(models['corpus']['size'], 9)
        self.assertNotIn('weights', json.dumps(models))

        code, current = self.call('/api/settings')
        self.assertEqual((code, current['version']), (200, 0))
        s = current['settings']
        s['retrieval'].update(top_k=5, top_n=2)
        # Writes need the session token like every other command.
        self.assertEqual(self.call('/api/settings', dict(settings=s, expected_version=0),
                                   headers={'X-Planning-Token': 'wrong'})[0], 403)
        code, saved = self.call('/api/settings', dict(settings=s, expected_version=0))
        self.assertEqual((code, saved['version']), (200, 1))
        code, stale = self.call('/api/settings', dict(settings=s, expected_version=0))
        self.assertEqual((code, stale['error']['code']), (409, 'STALE_SETTINGS'))
        s['retrieval']['top_n'] = 9
        self.assertEqual(self.call('/api/settings', dict(settings=s, expected_version=1))[0], 400)

        self.assertEqual(self.call('/api/commands', command(), headers={'Origin': self.base})[0], 200)
        code, metrics = self.call('/api/metrics')
        self.assertEqual(code, 200)
        self.assertGreaterEqual(metrics['runs'], 1)
        self.assertIn('parse', {m['key'] for m in metrics['modules']})


if __name__=='__main__':
    unittest.main()
