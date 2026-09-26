"""Local llama.cpp embedding adapter; no external requests or runtime downloads."""
import hashlib
import json
from pathlib import Path
import threading
import time
from urllib.request import Request, build_opener, ProxyHandler
from planning.providers.registry import loopback
from planning.services.model_status import NoRedirect

INSTRUCTION = 'Given a communication engineering question, retrieve relevant technical passages'
ENCODER_VERSION = 'qwen3-last-v1'


class HTTPEncoder:
    def __init__(self, model, cache_dir=None):
        if not loopback(model['endpoint']):
            raise ValueError('EMBEDDING_NOT_LOOPBACK')
        self.model = model
        self.cache_dir = Path(cache_dir) if cache_dir else None
        self.corpus_hash = None
        self._lock = threading.Lock()

    query_budget = True

    def encode(self, texts, query=False, timeout=1.4):
        import numpy as np
        rows = []
        deadline=time.monotonic()+timeout if query else None
        # One input per request bounds non-causal attention memory and batch tokens.
        for text in texts:
            content = f'Instruct: {INSTRUCTION}\nQuery: {text}' if query else text
            key = hashlib.sha256(json.dumps([self.model['id'], self.model.get('revision'),
                self.model['dimension'], ENCODER_VERSION, self.corpus_hash, content], ensure_ascii=False).encode()).hexdigest()
            cache = self.cache_dir / (key + '.json') if self.cache_dir and not query else None
            vector = None
            if cache and cache.is_file():
                try:
                    vector = self._validate(json.loads(cache.read_text(encoding='utf-8')))
                except (ValueError, OSError, TypeError):
                    pass
            if vector is None:
                payload = dict(model=self.model['alias'], input=[content], encoding_format='float')
                request = Request(self.model['endpoint'].rstrip('/') + '/v1/embeddings',
                    data=json.dumps(payload).encode(), headers={'Content-Type':'application/json'})
                remaining=lambda:max(0,deadline-time.monotonic()) if deadline else 60
                if not self._lock.acquire(timeout=remaining()):raise TimeoutError('EMBEDDING_QUERY_BUDGET')
                try:
                    budget=remaining()
                    if budget<=0:raise TimeoutError('EMBEDDING_QUERY_BUDGET')
                    with build_opener(ProxyHandler({}), NoRedirect()).open(request, timeout=budget) as response:
                        data = json.loads(response.read(1024 * 1024))
                    if deadline and time.monotonic()>deadline:raise TimeoutError('EMBEDDING_QUERY_BUDGET')
                finally:
                    self._lock.release()
                if data.get('model') != self.model['alias'] or len(data.get('data', [])) != 1 or data['data'][0].get('index') != 0:
                    raise ValueError('EMBEDDING_RESPONSE')
                vector = self._validate(data['data'][0]['embedding'])
                if cache:
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    cache.write_text(json.dumps(vector.tolist()), encoding='utf-8')
            rows.append(vector)
        return np.array(rows) if rows else np.empty((0, self.model['dimension']))

    def _validate(self, row):
        import numpy as np
        vector = np.asarray(row, dtype=float)
        if vector.shape != (self.model['dimension'],) or not np.isfinite(vector).all():
            raise ValueError('EMBEDDING_VECTOR')
        norm = np.linalg.norm(vector)
        if norm == 0:
            raise ValueError('EMBEDDING_ZERO')
        return vector / norm
