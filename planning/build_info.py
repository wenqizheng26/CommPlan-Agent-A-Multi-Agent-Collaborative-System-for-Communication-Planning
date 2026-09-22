"""Content identity captured at server startup, independent of uncommitted Git state."""
import hashlib
from pathlib import Path

def build_fingerprint(root):
    root=Path(root)
    files=[p for folder in ('planning','formula_rag') for p in (root/folder).rglob('*')
           if p.is_file() and p.suffix in {'.py','.js','.mjs','.html','.css'}]
    # Immutable product inputs affect the running service just as source does.
    # Planning loads formulas.json; runtime_config controls launcher/model identity.
    # Never include mutable history, logs, PID files or local model weights.
    files.extend(root/name for name in ('knowledge/formulas.json', 'runtime_config.json')
                 if (root/name).is_file())
    h=hashlib.sha256()
    for p in sorted(files):
        h.update(p.relative_to(root).as_posix().encode() + b'\0')
        h.update(hashlib.sha256(p.read_bytes()).digest())
    return h.hexdigest()[:20]
