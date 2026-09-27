"""Documents added on the 资料 page.

The original is saved on this machine only (knowledge/sources/added is ignored by Git, like
the ITU originals); its manifest entry, with the SHA-256, goes into the tracked manifest.
A file that cannot be converted is not registered.
"""
from datetime import date
import hashlib
import json
from pathlib import Path, PurePath
import re
import threading
from planning.knowledge.drafts import write_text
from planning.requirements_contract import require
from planning.retrieval.convert import FORMATS, converted

MAX_BYTES = 20 * 1024 * 1024
MANIFEST = 'knowledge/documents/manifest.json'
_lock = threading.Lock()


def converter_installed():
    import importlib.util
    return importlib.util.find_spec('markitdown') is not None


def language(text):
    cjk = sum('一' <= c <= '鿿' for c in text)
    letters = sum(c.isalpha() for c in text) or 1
    return 'zh' if cjk / letters > 0.1 else 'en'


def add_document(root, name, data, title=''):
    root = Path(root)
    require(type(name) is str and 1 <= len(name) <= 200, 'DOCUMENT_NAME')
    suffix = PurePath(name).suffix.lower()
    require(suffix in FORMATS, 'DOCUMENT_FORMAT')
    require(type(data) is bytes and 0 < len(data) <= MAX_BYTES, 'DOCUMENT_SIZE')
    title = re.sub(r'\s+', ' ', (title or PurePath(name).stem)).strip()[:80]
    require(title, 'DOCUMENT_TITLE')
    sha = hashlib.sha256(data).hexdigest()
    doc_id = 'added-' + sha[:12]
    record = dict(doc_id=doc_id, title=title, version=date.today().isoformat(), language='zh',
                  source='本机添加：' + PurePath(name).name[:120], local_path=f'knowledge/sources/added/{doc_id}{suffix}',
                  sha256=sha, redistributable=False, simulated=False)
    with _lock:
        manifest = root / MANIFEST
        data_json = json.loads(manifest.read_text(encoding='utf-8'))
        existing = next((d for d in data_json['documents'] if d['sha256'] == sha), None)
        require(existing is None, 'DOCUMENT_EXISTS')
        path = root / record['local_path']
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        try:
            text = converted(root, record)
        except (ImportError, ValueError, OSError):
            path.unlink(missing_ok=True)
            raise
        record['language'] = language(text)
        data_json['documents'].append(record)
        write_text(manifest, json.dumps(data_json, ensure_ascii=False, indent=2) + '\n')
    return record


def describe(root):
    """Documents for the page: no local paths, and chunk text only on request."""
    from planning.retrieval.documents import DocumentStore
    store = DocumentStore(root)
    status = {s['doc_id']: s for s in store.status}
    rows = [dict(doc_id=r['doc_id'], title=r['title'], version=r['version'], language=r['language'],
                 simulated=r['simulated'], added=r['local_path'].startswith('knowledge/sources/added/'),
                 source=r['source'], status=status[r['doc_id']]['status'], chunks=status[r['doc_id']]['chunks'],
                 code=status[r['doc_id']].get('code'))
            for r in store.records]
    return dict(documents=rows, formats=list(FORMATS), converter=converter_installed(), max_bytes=MAX_BYTES)


def sections(root, doc_id):
    from planning.retrieval.documents import DocumentStore
    require(type(doc_id) is str and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,80}', doc_id), 'DOCUMENT_ID')
    store = DocumentStore(root)
    require(any(r['doc_id'] == doc_id for r in store.records), 'DOCUMENT_NOT_FOUND')
    return [dict(id=c['id'], locator=c['sources'][0]['locator'], text=c['description'])
            for c in store.chunks if c['doc_id'] == doc_id]
