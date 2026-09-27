"""Hash-verified local documents. Nothing is downloaded or approved at runtime."""
import hashlib
import copy
from functools import lru_cache
import json
from pathlib import Path, PurePosixPath
import re
from planning.retrieval.convert import PAGE, convert, converted

CHUNK_LIMIT = 800
TABLE_RULE = re.compile(r'\|?(\s*:?-+:?\s*\|)+\s*(:?-+:?\s*)?')
SLIDE = re.compile(r'^<!-- Slide number: (\d+) -->$')
COMMENT = re.compile(r'<!--.*-->')


def split_text(text):
    """Stable packing: whole paragraphs, else whole lines; only an overlong line is cut."""
    current = ''
    for paragraph in re.split(r'\n\s*\n', text.replace('\r\n', '\n')):
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        for piece in pieces(paragraph):
            if current and len(current) + len(piece) + 2 > CHUNK_LIMIT:
                yield current
                current = ''
            current = current + '\n\n' + piece if current else piece
    if current:
        yield current


def pieces(paragraph):
    """A long paragraph is cut at line ends. A table cut in two repeats its header row."""
    if len(paragraph) <= CHUNK_LIMIT:
        yield paragraph
        return
    lines = paragraph.split('\n')
    header = ''
    if (len(lines) > 2 and lines[0].startswith('|') and TABLE_RULE.fullmatch(lines[1])
            and len(lines[0]) + len(lines[1]) < CHUNK_LIMIT // 2):
        header = lines[0] + '\n' + lines[1]
    width = CHUNK_LIMIT - (len(header) + 1 if header else 0)
    current = header
    for line in lines[2:] if header else lines:
        for start in range(0, max(len(line), 1), width):
            part = line[start:start + width]
            if current and current != header and len(current) + len(part) + 1 > CHUNK_LIMIT:
                yield current
                current = header
            current = current + '\n' + part if current else part
    if current and current != header:
        yield current


def markdown_sections(text):
    """Sections under headings. A heading with no text of its own joins the next section."""
    sections, headings, lines, sequence = [], [], [], 0
    locator = '正文'

    def has_body():
        return any(line.strip() and not re.match(r'^#{1,6}\s', line) and not COMMENT.fullmatch(line.strip())
                   for line in lines)

    for line in text.splitlines():
        heading = re.match(r'^(#{1,6})\s+(.+)$', line)
        slide = SLIDE.match(line.strip())
        if heading or slide:
            if has_body():
                sections.append((f's{sequence}', locator, '\n'.join(lines)))
                lines = []
            sequence += 1
            if slide:
                headings = [f'幻灯片 {slide[1]}']
            else:
                # Headings inside a slide rank below the slide itself.
                level = len(heading[1]) + (1 if headings and headings[0].startswith('幻灯片 ') else 0)
                headings = headings[:level-1] + [heading[2].strip()]
            locator = ' / '.join(headings)
        lines.append(line)
    if lines and (has_body() or not sections):
        sections.append((f's{sequence}', locator, '\n'.join(lines)))
    return sections


def sections_of(text, paged):
    if paged:
        parts = PAGE.split(text)
        return [(f'p{page}', f'page {page}', body) for page, body in zip(parts[1::2], parts[2::2])]
    return markdown_sections(text)


def chunks(path, record, root=None):
    path = Path(path)
    text = convert(path) if root is None else converted(root, record)
    result = []
    for prefix, locator, section in sections_of(text, path.suffix.lower() == '.pdf'):
        for index, excerpt in enumerate(split_text(section), 1):
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
                        parts = copy.deepcopy(cached_chunks(str(self.root.resolve()), json.dumps(record,sort_keys=True)))
                        self.chunks.extend(parts)
                        item.update(status='ready', chunks=len(parts))
                    except (ImportError, ValueError, OSError) as exc:
                        item.update(status='unreadable', error=type(exc).__name__, code=str(exc)[:80])
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
def cached_chunks(root, record_json):
    # Caller rechecks bytes against the record SHA before using this parse cache.
    record = json.loads(record_json)
    return chunks(Path(root) / record['local_path'], record, Path(root))
