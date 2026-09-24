"""Global model/retrieval defaults. Commands copy them at start; saved tasks keep their copy."""
import copy
from contextlib import closing
import json
import sqlite3
from planning.providers.registry import ROLES
from planning.requirements_contract import require, obj
from planning.workflow.requirements_graph import stamp

RETRIEVAL_MODES = ('lexical', 'dense', 'hybrid')
MAX_TOP_K = 20


def factory(registry):
    # Lexical by default: the minimal install has no torch and dense cold start is ~48 s.
    return dict(mode_default='deterministic',
                chat=dict(default=registry.defaults['chat'], roles={r: None for r in ROLES}),
                params=dict(temperature=None, timeout_s=None),
                retrieval=dict(mode='lexical', embedding=registry.defaults.get('embedding'), top_k=8, top_n=3))


def validate(settings, registry):
    obj(settings, 'mode_default chat params retrieval')
    require(settings['mode_default'] in ('deterministic', 'llm'), 'SETTINGS_MODE')
    chat = settings['chat']
    obj(chat, 'default roles')
    obj(chat['roles'], ' '.join(ROLES))
    for model_id in [chat['default'], *(m for m in chat['roles'].values() if m is not None)]:
        require(registry.kind(model_id) == 'chat', 'SETTINGS_UNKNOWN_MODEL')
        require(registry.strict(model_id), 'SETTINGS_MODEL_NOT_STRUCTURED')
    params = settings['params']
    obj(params, 'temperature timeout_s')
    t = params['temperature']
    require(t is None or (type(t) in (int, float) and 0 <= t <= 1), 'SETTINGS_TEMPERATURE')
    s = params['timeout_s']
    require(s is None or (type(s) in (int, float) and 5 <= s <= 120), 'SETTINGS_TIMEOUT')
    r = settings['retrieval']
    obj(r, 'mode embedding top_k top_n')
    require(r['mode'] in RETRIEVAL_MODES, 'SETTINGS_RETRIEVAL_MODE')
    require(r['embedding'] is None or registry.kind(r['embedding']) == 'embedding', 'SETTINGS_UNKNOWN_EMBEDDING')
    require(r['mode'] == 'lexical' or r['embedding'] is not None, 'SETTINGS_EMBEDDING_REQUIRED')
    require(type(r['top_k']) is int and 1 <= r['top_k'] <= MAX_TOP_K, 'SETTINGS_TOP_K')
    require(type(r['top_n']) is int and 1 <= r['top_n'] <= r['top_k'], 'SETTINGS_TOP_N')
    return copy.deepcopy(settings)


class SettingsStore:
    """One row, optimistic version. Kept outside the task transaction on purpose:
    a settings change never rewrites or invalidates saved tasks."""

    def __init__(self, path, registry):
        self.path, self.registry = str(path), registry
        with closing(sqlite3.connect(self.path, timeout=30)) as conn, conn:
            conn.execute('CREATE TABLE IF NOT EXISTS settings(id INTEGER PRIMARY KEY CHECK(id=1), '
                         'version INTEGER NOT NULL, body TEXT NOT NULL, updated_at TEXT NOT NULL)')

    def get(self):
        with closing(sqlite3.connect(self.path, timeout=30)) as conn:
            row = conn.execute('SELECT version, body, updated_at FROM settings WHERE id=1').fetchone()
        if row:
            try:
                return dict(version=row[0], settings=validate(json.loads(row[1]), self.registry), updated_at=row[2])
            except ValueError:
                pass  # A registry edit removed a model: fall back instead of refusing to start.
        return dict(version=row[0] if row else 0, settings=factory(self.registry), updated_at=None)

    def put(self, settings, expected_version):
        require(type(expected_version) is int, 'SETTINGS_VERSION')
        clean = validate(settings, self.registry)
        with closing(sqlite3.connect(self.path, timeout=30)) as conn, conn:
            row = conn.execute('SELECT version FROM settings WHERE id=1').fetchone()
            require((row[0] if row else 0) == expected_version, 'STALE_SETTINGS')
            version, at = expected_version + 1, stamp()
            conn.execute('INSERT INTO settings(id,version,body,updated_at) VALUES(1,?,?,?) '
                         'ON CONFLICT(id) DO UPDATE SET version=excluded.version, body=excluded.body, '
                         'updated_at=excluded.updated_at', (version, json.dumps(clean, ensure_ascii=False), at))
        return dict(version=version, settings=clean, updated_at=at)

    def bindings(self, settings):
        chat, params = settings['chat'], settings['params']
        return {role: self.registry.binding(role, chat['roles'][role] or chat['default'], params) for role in ROLES}
