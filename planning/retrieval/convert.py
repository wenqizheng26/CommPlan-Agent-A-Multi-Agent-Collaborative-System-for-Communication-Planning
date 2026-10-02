"""Local document conversion to Markdown through MarkItDown converters, chosen by file type.

The file type decides the converter; there is no guessing and no fallback to another
converter, so a damaged file is reported instead of being read as something else.
PDFs use a page converter written against MarkItDown's converter interface (pypdf text,
one marker per page): MarkItDown's own PDF path turned ITU equations and tables into broken
pipe tables in the 2026-09-27 comparison, and the page is the locator. Nothing is fetched
from the network.
"""
import hashlib
import io
import os
from pathlib import Path
import re

VERSION = 1
FORMATS = ('.md', '.txt', '.pdf', '.docx', '.pptx', '.xlsx', '.xls', '.html', '.htm')
PAGE = re.compile(r'^<!-- page (\d+) -->$', re.M)
HEADER = re.compile(r'^<!-- commplan-converted v(\d+) source=([a-f0-9]{64}) text=([a-f0-9]{64}) -->\n')


def pdf_pages(stream):
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError
    try:
        return [page.extract_text() or '' for page in PdfReader(stream).pages]
    except PyPdfError as exc:
        raise ValueError('DOCUMENT_PDF_UNREADABLE') from exc


def paged(pages):
    return '\n\n'.join(f'<!-- page {n} -->\n{text.strip()}' for n, text in enumerate(pages, 1))


def converter_for(suffix):
    import markitdown.converters as built_in
    from markitdown import DocumentConverter, DocumentConverterResult

    class PagedPdf(DocumentConverter):
        def convert(self, file_stream, stream_info, **kwargs):
            return DocumentConverterResult(markdown=paged(pdf_pages(io.BytesIO(file_stream.read()))))

    return {'.pdf': PagedPdf, '.txt': built_in.PlainTextConverter, '.docx': built_in.DocxConverter,
            '.pptx': built_in.PptxConverter, '.xlsx': built_in.XlsxConverter, '.xls': built_in.XlsConverter,
            '.html': built_in.HtmlConverter, '.htm': built_in.HtmlConverter}[suffix]()


def chinese(text):
    wide = [c for c in text if ord(c) > 127]
    return bool(wide) and sum('一' <= c <= '鿿' or '　' <= c <= '〿'
                              or '＀' <= c <= '￯' for c in wide) >= 0.9 * len(wide)


def charset(data):
    """UTF-8, then GB18030 when it reads as Chinese; generic detection misreads short Chinese text."""
    try:
        data.decode('utf-8')
        return 'utf-8'
    except UnicodeDecodeError:
        pass
    try:
        if chinese(data.decode('gb18030')):
            return 'gb18030'
    except UnicodeDecodeError:
        pass
    from charset_normalizer import from_bytes
    best = from_bytes(data).best()
    return best.encoding if best else 'utf-8'


def convert(path):
    """Markdown text of one local document."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in FORMATS:
        raise ValueError('DOCUMENT_FORMAT')
    if suffix == '.md':
        return path.read_text(encoding='utf-8')
    data = path.read_bytes()
    try:
        converter = converter_for(suffix)
    except ImportError:
        if suffix != '.pdf':
            raise ImportError('DOCUMENT_CONVERTER_MISSING') from None
        text = paged(pdf_pages(io.BytesIO(data)))  # minimal install: the same page text without MarkItDown
    else:
        from markitdown import StreamInfo, MissingDependencyException
        info = StreamInfo(extension=suffix, filename=path.name, local_path=str(path),
                          charset=charset(data) if suffix in ('.txt', '.html', '.htm') else None)
        try:
            text = converter.convert(io.BytesIO(data), info).markdown
        except MissingDependencyException:
            raise ImportError('DOCUMENT_CONVERTER_MISSING') from None
        except ValueError:
            raise
        except Exception as exc:  # noqa: BLE001 - any parser failure means the file is unreadable
            raise ValueError('DOCUMENT_UNREADABLE') from exc
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    if not text.strip():
        raise ValueError('DOCUMENT_EMPTY')
    return text


def converted(root, record):
    """Converted text, cached beside the originals (ignored by Git) and checked on every read."""
    root = Path(root)
    source = root / record['local_path']
    if source.suffix.lower() == '.md':
        return convert(source)
    folder = root / 'knowledge/sources/converted'
    target = folder / f"{record['doc_id']}.{record['sha256'][:16]}.md"
    if target.is_file():
        cached = target.read_text(encoding='utf-8')
        match = HEADER.match(cached)
        body = cached[match.end():] if match else ''
        if (match and int(match[1]) == VERSION and match[2] == record['sha256']
                and match[3] == hashlib.sha256(body.encode('utf-8')).hexdigest()):
            return body
    text = convert(source)
    header = (f"<!-- commplan-converted v{VERSION} source={record['sha256']} "
              f"text={hashlib.sha256(text.encode('utf-8')).hexdigest()} -->\n")
    try:
        folder.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix('.tmp')
        temporary.write_text(header + text, encoding='utf-8', newline='\n')
        os.replace(temporary, target)
        for old in folder.glob(record['doc_id'] + '.*.md'):
            if old != target:
                old.unlink()
    except OSError:
        pass  # a read-only copy still converts; it only loses the cache
    return text
