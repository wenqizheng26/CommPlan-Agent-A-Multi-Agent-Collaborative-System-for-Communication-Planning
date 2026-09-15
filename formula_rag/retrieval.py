"""Local BGE CLS vectors + lexical rank fusion; no runtime downloads."""
import hashlib
import json
import math
import os
import re
from collections import Counter
from pathlib import Path


def digest_cards(cards):
    return hashlib.sha256(json.dumps(cards, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def document(card):
    return '\n'.join((card['title'], card.get('description', ''),
                      ' '.join(card.get('keywords', [])),
                      json.dumps(card.get('parameters', {}), ensure_ascii=False),
                      json.dumps(card.get('applicability', {}), ensure_ascii=False)))


def tokens(text):
    text = text.lower()
    parts = re.findall(r'[a-z0-9_]+|[\u4e00-\u9fff]+', text)
    result = []
    for part in parts:
        if re.match(r'[\u4e00-\u9fff]', part):
            result.extend(part[i:i + 2] for i in range(max(1, len(part) - 1)))
        else:
            result.append(part)
    return Counter(result)


class LocalEncoder:
    def __init__(self, model_dir):
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
        from transformers import AutoModel, AutoTokenizer
        import torch
        self.torch = torch
        torch.set_num_threads(4)
        model_dir = Path(model_dir)
        self.tokenizer = AutoTokenizer.from_pretrained(str(model_dir), local_files_only=True, trust_remote_code=False)
        self.model = AutoModel.from_pretrained(str(model_dir), local_files_only=True, trust_remote_code=False, use_safetensors=True).eval()
        self.fingerprint = hashlib.sha256((model_dir / 'model.safetensors').read_bytes()).hexdigest()

    def encode(self, texts, query=False):
        import numpy as np
        rows = []
        if query:
            texts = ['为这个句子生成表示以用于检索相关文章：' + text for text in texts]
        for start in range(0, len(texts), 16):
            inputs = self.tokenizer(texts[start:start + 16], padding=True, truncation=True, max_length=512, return_tensors='pt')
            with self.torch.inference_mode():
                embeddings = self.model(**inputs).last_hidden_state[:, 0]
                embeddings = self.torch.nn.functional.normalize(embeddings, p=2, dim=1)
            rows.append(embeddings.cpu().numpy())
        return np.concatenate(rows) if rows else np.empty((0, 512))


class Retriever:
    def __init__(self, root, cards, dense=True):
        self.root = Path(root)
        self.encoder = LocalEncoder(self.root / 'models/bge-small-zh-v1.5') if dense else None
        self.dense = dense
        self.hash = None
        self.update(cards)

    def update(self, cards):
        fingerprint = digest_cards(cards)
        if fingerprint == self.hash:
            return
        self.cards, self.hash = cards, fingerprint
        self.counts = [tokens(document(c)) for c in cards]
        if not self.dense:
            return
        import numpy as np
        cache = self.root / 'runtime/formula_index.npz'
        cache.parent.mkdir(parents=True, exist_ok=True)
        if cache.exists():
            with np.load(cache, allow_pickle=False) as data:
                if str(data['catalog_hash']) == fingerprint and str(data['model_hash']) == self.encoder.fingerprint:
                    self.vectors = data['vectors']
                    return
        self.vectors = self.encoder.encode([document(c) for c in cards])
        np.savez_compressed(cache, vectors=self.vectors, catalog_hash=fingerprint, model_hash=self.encoder.fingerprint)

    def search(self, query, limit=8):
        q = tokens(query)
        qnorm = math.sqrt(sum(v*v for v in q.values())) or 1
        lexical = []
        for terms in self.counts:
            norm = math.sqrt(sum(v*v for v in terms.values())) or 1
            lexical.append(sum(q[t]*v for t, v in terms.items()) / (qnorm*norm))
        lexical_order = sorted(range(len(self.cards)), key=lambda i: (-lexical[i], self.cards[i]['id']))
        ranks = {i: 1/(60+r) for r, i in enumerate(lexical_order, 1)}
        dense_scores = [None] * len(self.cards)
        if self.dense:
            dense_scores = (self.vectors @ self.encoder.encode([query], query=True)[0]).tolist()
            dense_order = sorted(range(len(self.cards)), key=lambda i: (-dense_scores[i], self.cards[i]['id']))
            for rank, index in enumerate(dense_order, 1):
                ranks[index] += 1/(60+rank)
        order = sorted(ranks, key=lambda i: (-ranks[i], self.cards[i]['id']))[:limit]
        return [{'id': self.cards[i]['id'], 'rank': rank,
                 'lexical_similarity': lexical[i], 'dense_similarity': dense_scores[i]}
                for rank, i in enumerate(order, 1)]
