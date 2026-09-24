"""Contract every RetrievalService implementation must pass (docs/design/MODEL_RETRIEVAL.md §4.3).

To check another implementation, set RETRIEVAL_FACTORY=module:callable; the callable
receives (root, cards) and returns a service with dense capability available.
"""
import importlib
import os
import socket
import unittest
from pathlib import Path
from unittest.mock import patch
from formula_rag.catalog import load_catalog
from planning.retrieval import DefaultRetrievalService, RetrievalError, MAX_TOP_K

ROOT = Path(__file__).resolve().parents[1]
QUERY = '按自由空间基准计算，频率2GHz，距离1km，求路径损耗。'


class FakeEncoder:
    """Deterministic stand-in for BGE: bag of characters, L2-normalised."""
    def encode(self, texts, query=False):
        import numpy as np
        rows = []
        for text in texts:
            v = np.zeros(64)
            for ch in text:
                v[ord(ch) % 64] += 1
            rows.append(v / (np.linalg.norm(v) or 1))
        return np.array(rows)


def default_factory(root, cards):
    service = DefaultRetrievalService(root, cards, embedding_id='fake-embedding',
                                      encoder_factory=lambda path: FakeEncoder())
    service.warm(wait=True)
    return service


def factory():
    name = os.environ.get('RETRIEVAL_FACTORY')
    if not name:
        return default_factory
    module, attr = name.split(':')
    return getattr(importlib.import_module(module), attr)


class RetrievalContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards = load_catalog(ROOT)
        cls.ids = {c['id'] for c in cls.cards}
        cls.service = factory()(ROOT, cls.cards)

    def search(self, **kw):
        return self.service.search(QUERY, **dict(dict(top_k=8, top_n=3, mode='hybrid'), **kw))

    def test_shape_and_top_n(self):
        for mode in ('lexical', 'dense', 'hybrid'):
            r = self.search(mode=mode, top_k=5, top_n=2)
            self.assertLessEqual(len(r.hits), 5)
            self.assertEqual(r.used, [h['id'] for h in r.hits[:2]])
            self.assertEqual([h['rank'] for h in r.hits], list(range(1, len(r.hits) + 1)))
            for h in r.hits:
                self.assertEqual(set(h), {'id', 'source_type', 'title', 'excerpt', 'source', 'scores', 'rank'})
                self.assertEqual(set(h['scores']), {'lexical', 'dense', 'fused', 'rerank'})
            self.assertEqual(r.mode_used, mode)
            self.assertFalse(r.degraded)

    def test_deterministic(self):
        first = self.search().to_dict()
        for _ in range(2):
            again = self.search().to_dict()
            again['latency_ms'] = first['latency_ms']
            self.assertEqual(again, first)

    def test_out_of_range_arguments_are_rejected(self):
        for kw in (dict(top_k=0), dict(top_k=MAX_TOP_K + 1), dict(top_k=3, top_n=4), dict(top_n=0),
                   dict(mode='semantic'), dict(filters={'x': 1})):
            with self.subTest(kw=kw), self.assertRaises(RetrievalError):
                self.search(**kw)

    def test_ids_exist_and_excerpt_is_bounded(self):
        r = self.search(top_k=MAX_TOP_K, top_n=1)
        self.assertLessEqual(len(r.hits), len(self.cards))
        for h in r.hits:
            self.assertIn(h['id'], self.ids)
            self.assertLessEqual(len(h['excerpt']), 800)

    def test_no_network(self):
        def refuse(*args, **kwargs):
            raise AssertionError('retrieval must not open network connections')
        with patch.object(socket, 'create_connection', refuse), patch.object(socket.socket, 'connect', refuse):
            self.search()

    def test_latency_reported(self):
        total = self.search().latency_ms['total']
        self.assertIsInstance(total, (int, float))
        self.assertGreaterEqual(total, 0)

    def test_empty_query_is_legal(self):
        r = self.service.search('', top_k=8, top_n=3, mode='hybrid')
        self.assertTrue(all(h['scores']['lexical'] == 0 for h in r.hits))
        self.assertFalse(r.degraded)


class DefaultServiceDegradationTests(unittest.TestCase):
    """Specific to the shipped implementation: missing or cold vectors fall back to lexical."""

    def test_missing_embedding_degrades_to_lexical(self):
        cards = load_catalog(ROOT)
        service = DefaultRetrievalService(ROOT, cards, embedding_id='absent', embedding_path='models/does-not-exist')
        r = service.search(QUERY, top_k=8, top_n=3, mode='hybrid')
        self.assertEqual((r.mode_used, r.degraded), ('lexical', True))
        self.assertEqual(service.describe()['embedding']['status'], 'not_installed')
        self.assertEqual(r.hits[0]['id'], 'fspl_ghz')

    def test_encoder_failure_is_a_status_not_an_exception(self):
        def broken(path):
            raise RuntimeError('corrupt weights')
        service = DefaultRetrievalService(ROOT, load_catalog(ROOT), embedding_id='broken', encoder_factory=broken)
        self.assertEqual(service.warm(wait=True), 'failed')
        self.assertTrue(service.search(QUERY, top_k=8, top_n=3, mode='dense').degraded)

    def test_catalog_change_reencodes_without_reloading_model(self):
        loads = []
        def counting(path):
            loads.append(path)
            return FakeEncoder()
        cards = load_catalog(ROOT)
        service = DefaultRetrievalService(ROOT, cards, embedding_id='fake', encoder_factory=counting)
        service.warm(wait=True)
        service.update(cards[:-1])
        self.assertTrue(service.search(QUERY, top_k=8, top_n=3, mode='hybrid').degraded)
        service.warm(wait=True)
        self.assertFalse(service.search(QUERY, top_k=8, top_n=3, mode='hybrid').degraded)
        self.assertEqual(len(loads), 1)

    def test_lexical_order_matches_previous_retriever(self):
        from formula_rag.retrieval import Retriever
        cards = load_catalog(ROOT)
        old = [h['id'] for h in Retriever(ROOT, cards, dense=False).search(QUERY)]
        new = [h['id'] for h in DefaultRetrievalService(ROOT, cards).search(QUERY, top_k=8, top_n=3, mode='lexical').hits]
        self.assertEqual(new, old)


if __name__ == '__main__':
    unittest.main()
