"""Hash-verified local documents. Nothing is downloaded or approved at runtime."""
import hashlib
import copy
from functools import lru_cache
import json
from pathlib import Path, PurePosixPath
import re

CHUNK_LIMIT = 800


def split_text(text):
    """Stable paragraph packing, bounded even for a PDF page without line breaks."""
    current = ''
    for paragraph in re.split(r'\n\s*\n', text.replace('\r\n', '\n')):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        for start in range(0, len(paragraph), CHUNK_LIMIT):
            piece = paragraph[start:start + CHUNK_LIMIT]
            if current and len(current) + len(piece) + 2 > CHUNK_LIMIT:
                yield current
                current = ''
            current = current + '\n\n' + piece if current else piece
    if current:
        yield current


def chunks(path, record):
    sections = []
    if path.suffix.lower() == '.pdf':
        from pypdf import PdfReader
        from pypdf.errors import PyPdfError
        try:
            for page, item in enumerate(PdfReader(path).pages, 1):
                sections.append((f'p{page}', f'page {page}', item.extract_text() or ''))
        except PyPdfError as exc:
            raise ValueError('DOCUMENT_PDF_UNREADABLE') from exc
    elif path.suffix.lower() == '.md':
        headings, lines, sequence = [], [], 0
        locator = '正文'
        for line in path.read_text(encoding='utf-8').splitlines():
            match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if match:
                if lines:
                    sections.append((f's{sequence}', locator, '\n'.join(lines)))
                sequence += 1
                level = len(match[1])
                headings = headings[:level-1] + [match[2].strip()]
                locator, lines = ' / '.join(headings), []
            lines.append(line)
        if lines:
            sections.append((f's{sequence}', locator, '\n'.join(lines)))
    else:
        raise ValueError('DOCUMENT_FORMAT')
    result = []
    for prefix, locator, text in sections:
        for index, excerpt in enumerate(split_text(text), 1):
            result.append(dict(id=f"doc:{record['doc_id']}:{prefix}-{index}",
                source_type='document_chunk', doc_id=record['doc_id'], title=record['title'],
                description=excerpt, version=record['version'],
                sources=[dict(title=record['title'], url=record['source'],
                    locator=f'{locator}, chunk {index}', sha256=record['sha256'],
                    doc_id=record['doc_id'], simulated=record['simulated'])]))
    return result


class DocumentStore:
    def __init__(self, root):
        self.root = Path(root)
        self.records, self.chunks, self.status = [], [], []
        path = self.root / 'knowledge/documents/manifest.json'
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('schema_version') != 1 or not isinstance(data.get('documents'), list):
            raise ValueError('DOCUMENT_MANIFEST')
        seen = set()
        for record in data['documents']:
            self._validate(record, seen)
            seen.add(record['doc_id'])
            self.records.append(record)
            item = dict(doc_id=record['doc_id'], title=record['title'], status='not_installed', chunks=0)
            file = self.root / record['local_path']
            if file.is_file():
                if hashlib.sha256(file.read_bytes()).hexdigest() != record['sha256']:
                    item['status'] = 'changed'
                else:
                    try:
                        parts = copy.deepcopy(cached_chunks(str(file.resolve()), json.dumps(record,sort_keys=True)))
                        self.chunks.extend(parts)
                        item.update(status='ready', chunks=len(parts))
                    except (ImportError, ValueError, OSError) as exc:
                        item.update(status='unreadable', error=type(exc).__name__)
            self.status.append(item)

    @staticmethod
    def _validate(record, seen):
        required = ('doc_id', 'title', 'version', 'language', 'source', 'local_path', 'sha256')
        if not isinstance(record, dict) or any(type(record.get(k)) is not str or not record[k] for k in required):
            raise ValueError('DOCUMENT_MANIFEST')
        path = PurePosixPath(record['local_path'])
        if (record['doc_id'] in seen or not re.fullmatch(r'[a-z0-9][a-z0-9-]*', record['doc_id'])
                or path.is_absolute() or '..' in path.parts or ':' in str(path) or '\\' in str(path)
                or path.parts[:2] not in (('knowledge', 'sources'), ('knowledge', 'documents'))
                or not re.fullmatch(r'[a-f0-9]{64}', record['sha256'])
                or type(record.get('simulated')) is not bool or type(record.get('redistributable')) is not bool):
            raise ValueError('DOCUMENT_MANIFEST')

    def describe(self):
        return dict(documents=self.status, chunks=len(self.chunks))


def expand_query(root, query):
    path = Path(root) / 'knowledge/documents/glossary.json'
    if not path.is_file():
        return query
    glossary = json.loads(path.read_text(encoding='utf-8'))
    return query + ' ' + ' '.join(term for word, terms in glossary.items() if word in query for term in terms)


@lru_cache(maxsize=32)
def cached_chunks(path, record_json):
    # Caller rechecks bytes against the record SHA before using this parse cache.
    return chunks(Path(path), json.loads(record_json))
