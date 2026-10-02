import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from planning import web_server
from tests.test_document_convert import pdf
from tests.test_knowledge_drafts import TABLE, model
from tests.teacher_fixtures import copy_teacher_dependencies

ROOT = Path(__file__).resolve().parents[1]


class KnowledgeApiTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / 'app'
        for folder in ('knowledge/documents', 'knowledge/facts', 'config'):
            shutil.copytree(ROOT / folder, self.root / folder)
        shutil.copy(ROOT / 'knowledge/formulas.json', self.root / 'knowledge/formulas.json')
        copy_teacher_dependencies(self.root)
        self.server = web_server.create_server(self.root, Path(temp.name) / 'web.sqlite', port=0)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (self.server.shutdown(), self.server.server_close(), thread.join(timeout=5)))
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.token = self.call('/api/session', token=False)[1]['token']

    def call(self, path, body=None, raw=None, kind='application/json', token=True):
        headers = {'Content-Type': kind}
        if token:
            headers['X-Planning-Token'] = self.token
        data = raw if raw is not None else json.dumps(body).encode() if body is not None else None
        try:
            response = urlopen(Request(self.base + path, data=data, headers=headers), timeout=30)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read().decode())

    def test_documents_list_sections_and_upload(self):
        code, library = self.call('/api/documents')
        self.assertEqual(code, 200)
        rows = {d['doc_id']: d for d in library['documents']}
        self.assertEqual(rows['sim-xx300']['status'], 'ready')
        self.assertNotIn('local_path', rows['sim-xx300'])
        code, found = self.call('/api/documents/sim-xx300')
        self.assertEqual(code, 200)
        self.assertTrue(any(TABLE in s['text'] for s in found['sections']))
        self.assertEqual(self.call('/api/documents/absent')[0], 404)
        data = pdf(['Free space loss 92.4 dB'])
        self.assertEqual(self.call('/api/documents?name=link.pdf', raw=data, kind='application/octet-stream', token=False)[0], 403)
        code, added = self.call('/api/documents?name=link.pdf&title=%E9%93%BE%E8%B7%AF', raw=data, kind='application/octet-stream')
        self.assertEqual(code, 200)
        record = added['document']
        self.assertEqual((record['title'], record['language'], record['simulated']), ('链路', 'en', False))
        self.assertTrue((self.root / record['local_path']).is_file())
        manifest = json.loads((self.root / 'knowledge/documents/manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['documents'][-1], record)
        code, again = self.call('/api/documents?name=copy.pdf', raw=data, kind='application/octet-stream')
        self.assertEqual((code, again['error']['code']), (409, 'DOCUMENT_EXISTS'))
        code, bad = self.call('/api/documents?name=virus.exe', raw=b'MZ', kind='application/octet-stream')
        self.assertEqual((code, bad['error']['code']), (400, 'DOCUMENT_FORMAT'))
        code, broken = self.call('/api/documents?name=broken.pdf', raw=b'%PDF-1.7 broken', kind='application/octet-stream')
        self.assertEqual((code, broken['error']['code']), (400, 'DOCUMENT_PDF_UNREADABLE'))
        self.assertEqual(len(list((self.root / 'knowledge/sources/added').iterdir())), 1)

    def test_extract_review_and_errors(self):
        chunk = next(s['id'] for s in self.call('/api/documents/sim-xx300')[1]['sections'] if TABLE in s['text'])
        output = dict(found=True, names=['XX-300'], model='XX-300', tx_power_dbm=40, antenna_gain_dbi=6,
                      rx_sensitivity_dbm=-97, band_low_ghz=1.0, band_high_ghz=3.0,
                      evidence=[dict(field=f, chunk_id=chunk, quote=TABLE) for f in
                                ('names', 'model', 'tx_power_dbm', 'antenna_gain_dbi', 'rx_sensitivity_dbm', 'band_ghz')])
        with patch('planning.agents.role_model.LocalRoleSelector.__call__', side_effect=lambda *a: model(output)(*a)):
            code, result = self.call('/api/drafts/extract', {'kind': 'device', 'chunk_ids': [chunk]})
        self.assertEqual(code, 200)
        draft = result['draft']
        self.assertEqual((result['mode'], draft['approvable']), ('llm', True))
        self.assertEqual(self.call('/api/drafts')[1]['drafts'][0]['id'], draft['id'])
        review = dict(id=draft['id'], decision='approve', reviewer='', reason='', content_hash=draft['content_hash'])
        code, body = self.call('/api/drafts/review', review)
        self.assertEqual((code, body['error']['code']), (400, 'DRAFT_REVIEWER'))
        code, body = self.call('/api/drafts/review', dict(review, reviewer='审核人'))
        self.assertEqual((code, body['draft']['status']), (200, 'approved'))
        facts = self.call('/api/facts')[1]['records']
        self.assertIn('XX-300', [n for r in facts for n in r['names']])
        with patch('planning.agents.role_model.LocalRoleSelector.__call__', side_effect=lambda *a: model(output)(*a)):
            second = self.call('/api/drafts/extract', {'kind': 'device', 'chunk_ids': [chunk]})[1]['draft']
        code, body = self.call('/api/drafts/review', dict(review, id=second['id'], reviewer='审核人', content_hash=second['content_hash']))
        self.assertEqual(code, 409)
        self.assertIn('库里已有编号 device:xx-300', body['error']['message'])
        other = next(s['id'] for s in self.call('/api/documents/sim-xx100')[1]['sections'])
        code, body = self.call('/api/drafts/extract', {'kind': 'device', 'chunk_ids': [chunk, other]})
        self.assertEqual((code, body['error']['code']), (400, 'EXTRACTION_ONE_DOCUMENT'))


if __name__ == '__main__':
    unittest.main()
