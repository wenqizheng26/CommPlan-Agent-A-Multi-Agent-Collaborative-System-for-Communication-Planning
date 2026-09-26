"""Retrieval interface of the workbench and its default implementation.

Other implementations (dense chunk stores, rerankers) replace ``DefaultRetrievalService``
and must pass tests/test_retrieval_contract.py. Retrieval proposes candidates with
sources; it is never numerical authority.
"""
from dataclasses import dataclass, field, asdict
import math
from pathlib import Path
import threading
import queue
import time
from typing import Literal, Protocol
from formula_rag.retrieval import document, tokens, digest_cards
from planning.retrieval.documents import DocumentStore, expand_query

MODES = ('lexical', 'dense', 'hybrid')
MAX_TOP_K = 20
EXCERPT_LIMIT = 800
RRF_K = 60


class RetrievalError(ValueError):
    pass


@dataclass
class Hit:
    id: str
    source_type: Literal['formula_card', 'document_chunk']
    title: str
    excerpt: str
    source: dict
    scores: dict
    rank: int


@dataclass
class RetrievalResult:
    hits: list
    used: list
    mode_requested: str
    mode_used: str
    degraded: bool
    embedding_model_id: str | None
    reranker_id: str | None
    latency_ms: dict
    corpus: dict
    top_k: int
    top_n: int
    diagnostics: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


class RetrievalService(Protocol):
    def search(self, query: str, *, top_k: int, top_n: int, mode: str,
               filters: dict | None = None) -> RetrievalResult: ...

    def describe(self) -> dict: ...


def bge_encoder(path):
    from formula_rag.retrieval import LocalEncoder
    return LocalEncoder(path)


class DefaultRetrievalService:
    """Formula cards by default; explicitly selected, verified document evidence on demand."""

    def __init__(self, root, cards, *, embedding_id=None, embedding_path=None, encoder_factory=bge_encoder, remote_encoder=False):
        self.root = Path(root)
        self.embedding_id = embedding_id
        self.embedding_path = self.root / embedding_path if embedding_path else None
        self.encoder_factory = encoder_factory
        self.remote_encoder=remote_encoder
        self.retry_after=0
        self.encoder, self.vectors, self.vector_hash = None, None, None
        self.dense_status = 'disabled' if embedding_id is None else 'cold'
        self.dense_error = None
        self.warm_ms = None
        self._lock = threading.Lock()
        self._thread = None
        self._query_slot=threading.BoundedSemaphore(1)
        self.update(cards)

    def update(self, cards):
        documents = DocumentStore(self.root)
        entries = list(cards) + documents.chunks
        fingerprint = digest_cards(entries)
        self.documents = documents
        if getattr(self, 'hash', None) == fingerprint:
            return
        self.cards, self.hash = list(cards), fingerprint
        self.entries = entries
        self.counts = [tokens(document(c)) for c in entries]

    # --- dense warm-up -------------------------------------------------
    def warm(self, wait=False):
        """Start loading the embedding model once; searches degrade until it is ready."""
        with self._lock:
            if self.remote_encoder and self.dense_status=='failed' and time.monotonic()>=self.retry_after:
                self.dense_status='cold'
            if self.embedding_id is None or self.dense_status in ('loading', 'ready', 'not_installed', 'failed'):
                thread = self._thread
            else:
                if not self.remote_encoder and self.embedding_path is not None and not self.embedding_path.exists():
                    self.dense_status = 'not_installed'
                    return self.dense_status
                self.dense_status = 'loading'
                thread = self._thread = threading.Thread(target=self._load, name='embedding-warmup', daemon=True)
                thread.start()
        if wait and thread is not None:
            thread.join()
        return self.dense_status

    def _load(self):
        started = time.perf_counter()
        cards, card_hash = self.entries, self.hash
        try:
            # A catalog change re-encodes the cards but keeps the loaded model.
            encoder = self.encoder or self.encoder_factory(self.embedding_path)
            if hasattr(encoder, 'corpus_hash'):
                encoder.corpus_hash = card_hash
            vectors = encoder.encode([document(c) for c in cards])
            with self._lock:
                self.encoder, self.vectors, self.vector_hash = encoder, vectors, card_hash
                self.dense_status = 'ready'
                self.dense_error = None
                self.warm_ms = round((time.perf_counter() - started) * 1000)
        except ImportError as exc:
            with self._lock:
                self.dense_status, self.dense_error = 'not_installed', type(exc).__name__
        except Exception as exc:  # noqa: BLE001 - reported as status, never raised into a command
            with self._lock:
                self.dense_status, self.dense_error = 'failed', type(exc).__name__
                self.retry_after=time.monotonic()+5

    def _query(self,encoder,query,budget):
        if not getattr(encoder,'query_budget',False):
            return encoder.encode([query],query=True)[0]
        if budget<=0 or not self._query_slot.acquire(blocking=False):
            raise TimeoutError('EMBEDDING_QUERY_BUSY')
        result=queue.Queue(maxsize=1)
        def work():
            try:result.put((True,encoder.encode([query],query=True,timeout=budget)[0]))
            except Exception as exc:result.put((False,exc))
            finally:self._query_slot.release()
        threading.Thread(target=work,name='embedding-query',daemon=True).start()
        try:ok,value=result.get(timeout=budget)
        except queue.Empty:raise TimeoutError('EMBEDDING_QUERY_BUDGET') from None
        if not ok:raise value
        return value

    def describe(self):
        return dict(corpus=dict(size=len(self.cards), version=self.hash[:12], source_type='formula_card'),
                    documents=self.documents.describe(),
                    modes=list(MODES), embedding=dict(id=self.embedding_id, status=self.dense_status,
                                                      warm_ms=self.warm_ms, error=self.dense_error))

    # --- search ----------------------------------------------------------
    def search(self, query, *, top_k, top_n, mode, filters=None):
        # An empty query is legal (target and parameters chosen by hand): every score is zero.
        if type(query) is not str or len(query) > 8192:
            raise RetrievalError('RETRIEVAL_QUERY')
        if type(top_k) is not int or not 1 <= top_k <= MAX_TOP_K:
            raise RetrievalError('RETRIEVAL_TOP_K')
        if type(top_n) is not int or not 1 <= top_n <= top_k:
            raise RetrievalError('RETRIEVAL_TOP_N')
        if mode not in MODES:
            raise RetrievalError('RETRIEVAL_MODE')
        if filters is not None and (type(filters) is not dict or set(filters) - {'source_type', 'doc_ids'}):
            raise RetrievalError('RETRIEVAL_FILTERS_UNSUPPORTED')
        filters = filters or {}
        kind = filters.get('source_type', 'document_chunk' if 'doc_ids' in filters else 'formula_card')
        doc_ids = filters.get('doc_ids')
        if kind not in ('formula_card', 'document_chunk') or (doc_ids is not None and (
                type(doc_ids) is not list or len(doc_ids) > 100 or any(type(x) is not str for x in doc_ids)
                or kind != 'document_chunk')):
            raise RetrievalError('RETRIEVAL_FILTERS_UNSUPPORTED')
        indices = [i for i, c in enumerate(self.entries)
                   if c.get('source_type', 'formula_card') == kind
                   and (doc_ids is None or c.get('doc_id') in doc_ids)]
        entries = [self.entries[i] for i in indices]
        total = time.perf_counter()
        latency, diagnostics = {}, []
        n = len(entries)

        t = time.perf_counter()
        q = tokens(expand_query(self.root, query) if kind == 'document_chunk' else query)
        qnorm = math.sqrt(sum(v * v for v in q.values())) or 1
        lexical = []
        for terms in (self.counts[i] for i in indices):
            norm = math.sqrt(sum(v * v for v in terms.values())) or 1
            lexical.append(sum(q[k] * v for k, v in terms.items()) / (qnorm * norm))
        latency['lexical'] = round((time.perf_counter() - t) * 1000, 2)

        dense, mode_used, degraded = [None] * n, mode, False
        if mode != 'lexical' and not query.strip():
            mode_used = 'lexical'
            diagnostics.append(dict(code='EMPTY_QUERY', message='描述为空，无可比较的语义，按词项返回零分结果。'))
        elif mode != 'lexical':
            with self._lock:
                ready = self.dense_status == 'ready' and self.vector_hash == self.hash
                encoder, vectors = self.encoder, self.vectors
            if not ready:
                with self._lock:
                    stale = self.dense_status == 'ready'  # cards changed after warm-up
                    if stale:
                        self.dense_status = 'cold'
                if stale:
                    diagnostics.append(dict(code='EMBEDDING_STALE', message='知识库已更新，向量索引重建前按词项检索。'))
                self.warm()
                mode_used, degraded = 'lexical', True
                diagnostics.append(dict(code='EMBEDDING_NOT_READY', status=self.dense_status,
                                        message='向量模型未就绪，本次按词项检索。'))
            else:
                t = time.perf_counter()
                try:
                    vector=self._query(encoder,query,1.4-(time.perf_counter()-total))
                    dense = [float(x) for x in (vectors[indices] @ vector).tolist()]
                    latency['dense'] = round((time.perf_counter() - t) * 1000, 2)
                except Exception as exc:  # local service stopped after warm-up
                    mode_used, degraded = 'lexical', True
                    diagnostics.append(dict(code='EMBEDDING_QUERY_FAILED', error=type(exc).__name__,
                                            message='向量查询失败，本次按词项检索。'))

        t = time.perf_counter()
        order_of = lambda scores: sorted(range(n), key=lambda i: (-scores[i], entries[i]['id']))
        if mode_used == 'lexical':
            fused = [None] * n
            order = order_of(lexical)
        elif mode_used == 'dense':
            fused = [None] * n
            order = order_of(dense)
        else:
            fused = [0.0] * n
            for scores in (lexical, dense):
                for rank, i in enumerate(order_of(scores), 1):
                    fused[i] += 1 / (RRF_K + rank)
            order = order_of(fused)
        latency['fusion'] = round((time.perf_counter() - t) * 1000, 2)

        hits = []
        for rank, i in enumerate(order[:top_k], 1):
            c = entries[i]
            src = (c.get('sources') or [{}])[0]
            source = dict(title=src.get('title'), uri=src.get('url'), version=c.get('version'))
            if kind == 'document_chunk':
                source.update({key: src[key] for key in ('doc_id', 'locator', 'sha256', 'simulated')})
            hits.append(Hit(id=c['id'], source_type=kind, title=c['title'],
                            excerpt=(c.get('description') or c['title'])[:EXCERPT_LIMIT],
                            source=source,
                            scores=dict(lexical=round(lexical[i], 6),
                                        dense=None if dense[i] is None else round(dense[i], 6),
                                        fused=None if fused[i] is None else round(fused[i], 6), rerank=None),
                            rank=rank))
        latency['total'] = round((time.perf_counter() - total) * 1000, 2)
        return RetrievalResult(hits=[asdict(h) for h in hits], used=[h.id for h in hits[:top_n]],
                               mode_requested=mode, mode_used=mode_used, degraded=degraded,
                               embedding_model_id=self.embedding_id if mode_used != 'lexical' else None,
                               reranker_id=None, latency_ms=latency,
                               corpus=dict(size=n, version=self.hash[:12]), top_k=top_k, top_n=top_n,
                               diagnostics=diagnostics)
