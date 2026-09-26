import hashlib
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

from planning.retrieval.documents import DocumentStore, split_text
from planning.retrieval.service import DefaultRetrievalService, RetrievalError
from tests.test_retrieval_contract import FakeEncoder


class DocumentRetrievalTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.folder = self.root / 'knowledge/documents'
        self.folder.mkdir(parents=True)
        self.file = self.folder / 'sample.md'
        self.file.write_text('# Local guide\n\n## Reflection\nSea reflection causes multipath fading.\n\n## Rain\nRain attenuation reduces signal power.', encoding='utf-8')
        self.record = dict(doc_id='sample', title='Example', version='1', language='en',
            source='knowledge/documents/sample.md', local_path='knowledge/documents/sample.md',
            sha256=hashlib.sha256(self.file.read_bytes()).hexdigest(), simulated=True, redistributable=True)
        self.save_manifest([self.record])
        (self.folder/'glossary.json').write_text(json.dumps({'海面':['sea'], '多径':['multipath']}), encoding='utf-8')

    def save_manifest(self, records):
        (self.folder/'manifest.json').write_text(json.dumps(dict(schema_version=1, documents=records)), encoding='utf-8')

    def service(self, **kw):
        return DefaultRetrievalService(self.root, [], **kw)

    def test_chunks_are_deterministic_bounded_and_located(self):
        first = DocumentStore(self.root).chunks
        self.assertEqual(first, DocumentStore(self.root).chunks)
        self.assertIn('Reflection', first[1]['sources'][0]['locator'])
        self.assertEqual(first[1]['sources'][0]['sha256'], self.record['sha256'])
        parts = list(split_text('a'*1900+'\n\n'+'b'*200))
        self.assertTrue(all(len(p)<=800 for p in parts))
        self.assertEqual(''.join(parts).replace('\n',''), 'a'*1900+'b'*200)

    def test_missing_and_changed_documents_never_enter_index(self):
        self.save_manifest([self.record, dict(self.record,doc_id='missing',local_path='knowledge/sources/missing.pdf',simulated=False,redistributable=False)])
        store = DocumentStore(self.root)
        self.assertEqual([x['status'] for x in store.status], ['ready','not_installed'])
        self.file.write_text('changed',encoding='utf-8')
        store = DocumentStore(self.root)
        self.assertEqual(store.chunks, [])
        self.assertEqual(store.status[0]['status'], 'changed')

    def test_invalid_pdf_is_unreadable_without_breaking_other_documents(self):
        pdf=self.folder/'broken.pdf';pdf.write_bytes(b'%PDF-1.7\ninvalid')
        self.save_manifest([self.record,dict(self.record,doc_id='broken',local_path='knowledge/documents/broken.pdf',
            sha256=hashlib.sha256(pdf.read_bytes()).hexdigest())])
        store=DocumentStore(self.root)
        self.assertEqual([r['status'] for r in store.status],['ready','unreadable'])
        self.assertTrue(store.chunks)

    def test_filters_translation_and_no_network(self):
        service = self.service()
        with patch.object(socket.socket,'connect',side_effect=AssertionError('unexpected network')):
            result = service.search('海面多径',top_k=3,top_n=1,mode='lexical',filters={'source_type':'document_chunk'})
        self.assertIn('multipath',result.hits[0]['excerpt'])
        self.assertEqual(result.used,[result.hits[0]['id']])
        self.assertGreater(result.hits[0]['scores']['lexical'],0)
        self.assertEqual(result.hits[0]['source']['doc_id'],'sample')
        self.assertEqual(service.search('海面',top_k=3,top_n=1,mode='lexical').hits,[])
        self.assertEqual(service.search('海面',top_k=3,top_n=1,mode='lexical',filters={'doc_ids':['absent']}).hits,[])

    def test_dense_contract_and_missing_model_degradation(self):
        service = self.service(embedding_id='fake',encoder_factory=lambda path:FakeEncoder())
        self.assertEqual(service.warm(wait=True),'ready')
        for mode in ('lexical','dense','hybrid'):
            result=service.search('sea reflection',top_k=3,top_n=2,mode=mode,filters={'doc_ids':['sample']})
            self.assertFalse(result.degraded)
            self.assertEqual(result.used,[h['id'] for h in result.hits[:2]])
            self.assertTrue(all(h['source_type']=='document_chunk' for h in result.hits))
        missing=self.service(embedding_id='missing',embedding_path='models/absent')
        self.assertTrue(missing.search('sea',top_k=3,top_n=1,mode='hybrid',filters={'doc_ids':['sample']}).degraded)

    def test_invalid_filters_paths_and_limits(self):
        for filters in ({'doc_ids':'sample'},{'doc_ids':[1]},{'source_type':'anything'}, {'source_type':'formula_card','doc_ids':[]}):
            with self.subTest(filters=filters),self.assertRaises(RetrievalError):
                self.service().search('x',top_k=3,top_n=1,mode='lexical',filters=filters)
        with self.assertRaises(RetrievalError):
            self.service().search('x'*8193,top_k=3,top_n=1,mode='lexical')
        for path in ('../secret.md','C:/private.md','knowledge/documents/../../secret.md'):
            self.save_manifest([dict(self.record,local_path=path)])
            with self.assertRaises(ValueError):
                DocumentStore(self.root)

    def test_changed_source_invalidates_dense_index(self):
        service=self.service(embedding_id='fake',encoder_factory=lambda path:FakeEncoder())
        service.warm(wait=True)
        self.file.write_text('changed',encoding='utf-8')
        service.update([])
        result=service.search('sea',top_k=3,top_n=1,mode='dense',filters={'doc_ids':['sample']})
        self.assertEqual(result.hits,[])
        self.assertTrue(result.degraded)


if __name__ == '__main__':
    unittest.main()
