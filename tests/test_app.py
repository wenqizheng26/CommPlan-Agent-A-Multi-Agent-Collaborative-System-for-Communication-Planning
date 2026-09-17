import json
import threading
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

try:
    from app import create_server
except ImportError:
    create_server = None


class AppTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(create_server, '本地HTTP入口尚未实现')
        from formula_rag.pipeline import Engine
        root = Path(__file__).resolve().parents[1]
        self.server = create_server(root, Engine(root, dense=False, llm=False), port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        if hasattr(self, 'server'):
            self.server.shutdown()
            self.server.server_close()

    def test_api_value_matches_direct_calculation(self):
        data = json.dumps({'text': '自由空间，4.5GHz，200米，求传输损耗'}).encode()
        req = urllib.request.Request(self.url+'/api/query', data, {'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as r:
            result = json.load(r)
        self.assertAlmostEqual(result['calculations'][0]['value'], 91.4848501888, places=8)

    def test_status_and_page_are_local(self):
        with urllib.request.urlopen(self.url+'/api/status') as r:
            self.assertFalse(json.load(r)['dense_enabled'])
        with urllib.request.urlopen(self.url) as r:
            html = r.read().decode()
        self.assertIn('/assets/app.js', html)
        self.assertNotIn('https://cdn.', html)
        with urllib.request.urlopen(self.url+'/assets/app.js') as r:
            self.assertIn('textContent', r.read().decode())
        with urllib.request.urlopen(self.url+'/assets/katex/katex.min.js') as r:
            self.assertIn('katex', r.read().decode())
        with urllib.request.urlopen(self.url+'/api/catalog') as r:
            self.assertTrue(json.load(r)['formulas'][0]['display']['latex'])

    def test_nonfinite_json_rejected(self):
        req = urllib.request.Request(self.url+'/api/query', b'{"text":"x","parameters":{"frequency_ghz":NaN}}', {'Content-Type': 'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 400)

    def test_noise_confirmation_is_forwarded_and_saved_with_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            from formula_rag.pipeline import Engine
            root = Path(__file__).resolve().parents[1]
            server = create_server(root, Engine(root, dense=False, llm=False), port=0, output_dir=Path(tmp))
            threading.Thread(target=server.serve_forever, daemon=True).start()
            def post(path, body):
                req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}'+path,
                    json.dumps(body).encode(), {'Content-Type':'application/json'})
                with urllib.request.urlopen(req) as response:
                    return json.load(response)
            try:
                body = {'text':'噪声谱密度-174dBm/Hz，比特率1000000bit/s，Eb/N0 10dB，噪声系数3dB，工程损失0dB，求接收门限'}
                blocked = post('/api/query', body)
                self.assertNotIn('value', blocked['calculations'][-1])
                body['noise_reference'] = {'mode':'standard_290k', 'confirmed':True}
                result = post('/api/query', body)
                self.assertEqual(result['calculations'][-1]['value'], -101)
                saved = post('/api/save-result', {'result_id':result['result_id']})
                stored = json.loads(Path(saved['path']).read_text(encoding='utf-8'))
                self.assertEqual(stored, result)
                self.assertEqual(stored['request']['noise_reference']['origin'], 'structured_input')
                self.assertEqual(stored['calculations'][-1]['assessment']['code'], 'power_level')
            finally:
                server.shutdown()
                server.server_close()

    def test_noise_confirmation_string_boolean_is_not_accepted(self):
        data = json.dumps({'text':'求接收门限','noise_reference':{'mode':'standard_290k','confirmed':'true'}}).encode()
        req = urllib.request.Request(self.url+'/api/query', data, {'Content-Type':'application/json'})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 400)

    def test_cross_origin_post_rejected(self):
        req = urllib.request.Request(self.url+'/api/query', b'{"text":"x"}', {'Content-Type': 'application/json', 'Origin': 'https://unrelated.example'})
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req)
        self.assertEqual(ctx.exception.code, 403)

    def test_no_arbitrary_file_serving(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.url+'/docs/design.md')
        self.assertEqual(ctx.exception.code, 404)

    def test_reference_workbook_is_not_runtime_data(self):
        with urllib.request.urlopen(self.url+'/api/catalog') as r:
            content = r.read().decode()
        self.assertNotIn('用户提供', content)
        self.assertNotIn('链路预算-传输.xls', content)
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(self.url+'/api/workbook')
        self.assertEqual(ctx.exception.code, 404)

    def test_static_assets_cannot_escape_root(self):
        for path in ['/assets/../../runtime_config.json', '/assets/%2e%2e/%2e%2e/runtime_config.json']:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                urllib.request.urlopen(self.url+path)
            self.assertEqual(ctx.exception.code, 404)

    def test_save_result_writes_server_computed_value(self):
        from formula_rag.pipeline import Engine
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(__file__).resolve().parents[1]
            server = create_server(root, Engine(root, dense=False, llm=False), port=0, output_dir=Path(tmp))
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            url = f'http://127.0.0.1:{server.server_port}'
            def post(path, body):
                request = urllib.request.Request(url+path, json.dumps(body).encode(), {'Content-Type':'application/json'})
                with urllib.request.urlopen(request) as response:
                    return json.load(response)
            try:
                result = post('/api/query', {'text':'自由空间，4.5GHz，200米，求路径损耗'})
                self.assertFalse(list(Path(tmp).iterdir()))
                saved = post('/api/save-result', {'result_id':result['result_id']})
                stored = json.loads(Path(saved['path']).read_text(encoding='utf-8'))
                self.assertAlmostEqual(stored['calculations'][0]['value'],91.48485018878651)
                self.assertTrue(Path(saved['path']).is_relative_to(Path(tmp)))
                with self.assertRaises(urllib.error.HTTPError):
                    post('/api/save-result',{'result_id':result['result_id'],'path':'../../wrong.json','value':999})
                with self.assertRaises(urllib.error.HTTPError):
                    post('/api/save-result',{'result_id':'unknown'})
            finally:
                server.shutdown()
                server.server_close()


if __name__ == '__main__':
    unittest.main()
