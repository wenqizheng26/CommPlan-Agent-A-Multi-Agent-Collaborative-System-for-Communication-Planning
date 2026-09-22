"""Content identity captured at server startup, independent of uncommitted Git state."""
import hashlib
from pathlib import Path

def build_fingerprint(root):
    root=Path(root)
    files=[p for folder in ('planning','formula_rag') for p in (root/folder).rglob('*')
           if p.is_file() and p.suffix in {'.py','.js','.mjs','.html','.css'}]
    h=hashlib.sha256()
    for p in sorted(files):
        h.update(p.relative_to(root).as_posix().encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:20]
