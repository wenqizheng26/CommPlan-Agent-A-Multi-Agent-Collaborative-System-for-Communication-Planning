"""Machine-local knowledge switches. Missing entries are enabled."""
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import threading
from planning.requirements_contract import require

FILE = 'runtime/knowledge_switches.json'
_lock = threading.RLock()


def read(root):
    path = Path(root) / FILE
    value = json.loads(path.read_text(encoding='utf-8')) if path.exists() else dict(
        schema_version=1, documents={}, cards={})
    require(type(value) is dict and set(value) == {'schema_version', 'documents', 'cards'}
            and type(value['schema_version']) is int and value['schema_version'] == 1, 'KNOWLEDGE_SWITCHES')
    for kind in ('documents', 'cards'):
        require(type(value[kind]) is dict and all(type(k) is str and v is False
                for k, v in value[kind].items()), 'KNOWLEDGE_SWITCHES')
    return value


def enabled(root, kind, identifier):
    return identifier not in read(root)[kind]


@contextmanager
def mutation(root):
    """Serialize local file mutations, including CLI callers, with a bounded SQLite lock."""
    folder = Path(root) / 'runtime'
    folder.mkdir(parents=True, exist_ok=True)
    with _lock:
        conn = sqlite3.connect(folder / 'knowledge-writes.sqlite', timeout=10)
        try:
            conn.execute('BEGIN IMMEDIATE')
            yield
        finally:
            conn.rollback()
            conn.close()


def set_enabled(root, kind, identifier, value):
    require(kind in ('documents', 'cards') and type(identifier) is str and type(value) is bool,
            'KNOWLEDGE_SWITCH_VALUE')
    with mutation(root):
        data = read(root)
        if value:
            data[kind].pop(identifier, None)
        else:
            data[kind][identifier] = False
        save(root, data)


def save(root, data):
    from planning.knowledge.drafts import write_json
    write_json(Path(root) / FILE, data)


def disabled_dependencies(root, targets):
    """Check actual plan card IDs; alternate paths must not inherit the default chain."""
    from formula_rag.catalog import load_catalog
    off = read(root)['cards']
    if not off:
        return []
    all_cards = load_catalog(root, include_disabled=True)
    wanted = set(targets)
    return [c for c in all_cards if c['id'] in wanted and c['id'] in off]
