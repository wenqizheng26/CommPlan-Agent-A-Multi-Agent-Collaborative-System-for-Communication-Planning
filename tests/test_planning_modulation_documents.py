"""Modulation explanations remain source evidence, separate from simulated numeric facts."""
import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
from urllib.request import urlopen

from formula_rag.catalog import load_catalog
from planning.retrieval.documents import DocumentStore
from planning.retrieval.service import DefaultRetrievalService
from planning.workflow.task_service import TaskService
from tests.test_calculation_plans import command

ROOT = Path(__file__).resolve().parents[1]
DOC_ID = 'sim-modulation'
QUERY = 'QPSK 16QAM 接收灵敏度 余量'
FILTERS = {'source_type': 'document_chunk'}
CASE3 = next(c for c in map(json.loads, (ROOT / 'tests/eval/teacher_cases.jsonl').read_text(encoding='utf-8').splitlines())
             if c['id'] == 'teacher_03')
TEXT3 = CASE3['text'].replace('天线 12dBi', '天线增益 12dBi')


class ModulationDocumentTests(unittest.TestCase):
    def test_source_is_registered_ready_and_uses_exact_lf_bytes(self):
        store = DocumentStore(ROOT)
        records = {r['doc_id']: r for r in store.records}
        self.assertIn(DOC_ID, records)
        record = records[DOC_ID]
        content = (ROOT / record['local_path']).read_bytes()
        self.assertNotIn(b'\r', content)
        self.assertEqual(hashlib.sha256(content).hexdigest(), record['sha256'])
        self.assertTrue(record['simulated'] and record['redistributable'])
        self.assertEqual(next(s for s in store.status if s['doc_id'] == DOC_ID)['status'], 'ready')
        text = content.decode('utf-8')
        self.assertIn('knowledge/facts/modulations.json', text)
        # Keep numeric receiver thresholds in the single fact table.
        for row in json.loads((ROOT / 'knowledge/facts/modulations.json').read_text(encoding='utf-8')):
            self.assertNotIn(str(row['rx_sensitivity_dbm']) + ' dBm', text)

    def test_lexical_top_three_contains_the_source_without_network(self):
        service = DefaultRetrievalService(ROOT, load_catalog(ROOT))
        with patch.object(socket.socket, 'connect', side_effect=AssertionError('unexpected network')):
            result = service.search(QUERY, top_k=3, top_n=3, mode='lexical', filters=FILTERS)
        self.assertIn(DOC_ID, [h['source']['doc_id'] for h in result.hits])
        self.assertFalse(result.degraded)

    def test_case_three_freezes_source_in_review_and_publishes_it_after_restart(self):
        # Reuse the existing deterministic teacher path: labelled gains and selected target.
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / 'tasks.sqlite'
            service = TaskService(ROOT, database)
            draft = service.apply(command(text=TEXT3,
                input=dict(raw_text=TEXT3, manual_parameters={}, condition=None, target='link_margin')))['state']
            self.assertEqual(draft['status'], 'AWAITING_CONFIRMATION', draft['report']['questions'])
            found = draft['report'].get('document_retrieval') or {}
            hits = found.get('hits', [])
            self.assertIn(DOC_ID, [h['source']['doc_id'] for h in hits if h['id'] in found.get('used', [])])
            # A new service instance resumes the persisted confirmation and its frozen evidence.
            done = TaskService(ROOT, database).apply(command('confirm', draft))['state']
            self.assertEqual(done['status'], 'COMPLETED', done.get('failure'))
            documents = done['review_assessment']['facts']['documents']
            self.assertIn(DOC_ID, [d['source']['doc_id'] for d in documents])
            self.assertEqual(done['final_report']['document_evidence'], documents)
            comparison = done['final_report']['comparison']
            expected = CASE3['expected']
            self.assertEqual(comparison['recommend'], expected['recommend'])
            self.assertAlmostEqual(comparison['margin_diff_db'], expected['margin_diff_db'], places=9)
            for got, want in zip(comparison['rows'], expected['results']):
                self.assertEqual(got['rx_sensitivity_dbm'], want['rx_sensitivity_dbm'])
                self.assertAlmostEqual(got['link_margin_db'], want['link_margin_db'], places=9)


class RealModulationRetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Explicit opt-in avoids warming a shared model during another acceptance run.
        if os.environ.get('COMMPLAN_TEST_MODULATION_DENSE') != '1':
            raise unittest.SkipTest('Real vector service check requires COMMPLAN_TEST_MODULATION_DENSE=1 in a free service window')
        from planning.retrieval.http_encoder import HTTPEncoder
        config = json.loads((ROOT / 'config/models.json').read_text(encoding='utf-8'))
        model_id = config['defaults']['embedding']
        model = next(m for m in config['models'] if m['id'] == model_id)
        try:
            with urlopen(model['endpoint'].rstrip('/') + '/health', timeout=2) as response:
                if response.status != 200:
                    raise ValueError('embedding health is not ready')
        except (OSError, ValueError) as exc:
            raise unittest.SkipTest(f'Real vector service unavailable: {type(exc).__name__}')
        cache = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cache.cleanup)
        cls.service = DefaultRetrievalService(ROOT, load_catalog(ROOT), embedding_id=model_id,
            encoder_factory=lambda path: HTTPEncoder(model, Path(cache.name)), remote_encoder=True)
        cls.service.warm()
        cls.service._thread.join(timeout=120)
        if cls.service.dense_status != 'ready':
            raise unittest.SkipTest('Real vector index unavailable: ' + str(cls.service.dense_error))

    def assert_mode(self, mode):
        result = self.service.search(QUERY, top_k=3, top_n=3, mode=mode, filters=FILTERS)
        self.assertFalse(result.degraded, result.diagnostics)
        self.assertEqual(result.mode_used, mode)
        self.assertIn(DOC_ID, [h['source']['doc_id'] for h in result.hits])

    def test_dense_top_three_contains_the_source(self):
        self.assert_mode('dense')

    def test_hybrid_top_three_contains_the_source(self):
        self.assert_mode('hybrid')


if __name__ == '__main__':
    unittest.main()
