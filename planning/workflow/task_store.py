"""One transaction owns task state, event receipts and LangGraph checkpoints.

The saver adapter targets langgraph-checkpoint-sqlite==3.1.1. No async graph
methods or direct use outside TaskStore.transaction are supported.
"""
from contextlib import contextmanager, closing
import json
from pathlib import Path
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver
from planning.requirements_contract import require, strict_json


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


class TransactionSaver(SqliteSaver):
    @contextmanager
    def cursor(self, transaction=True):
        # setup uses executescript, which commits: it must run BEFORE BEGIN.
        require(self.is_setup and self.conn.in_transaction, 'CHECKPOINT_OUTSIDE_TRANSACTION')
        with self.lock:
            cursor = self.conn.cursor()
            try:
                yield cursor
            finally:
                cursor.close()


class TaskStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path, timeout=30)) as conn:
            SqliteSaver(conn).setup()
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS tasks(task_id TEXT PRIMARY KEY, state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events(task_id TEXT, event_id TEXT, payload_hash TEXT,
                    ack TEXT NOT NULL, PRIMARY KEY(task_id,event_id));
                CREATE TABLE IF NOT EXISTS history(task_id TEXT, state_version INTEGER,
                    revision INTEGER, state TEXT NOT NULL, PRIMARY KEY(task_id,state_version));
            ''')

    @contextmanager
    def transaction(self):
        conn = sqlite3.connect(self.path, timeout=30, check_same_thread=False)
        saver = TransactionSaver(conn)
        saver.is_setup = True  # schema initialized before any business transaction
        try:
            conn.execute('BEGIN IMMEDIATE')
            yield conn, saver
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def get_in(conn, task_id):
        row = conn.execute('SELECT state FROM tasks WHERE task_id=?', (task_id,)).fetchone()
        return strict_json(row[0]) if row else None

    def get(self, task_id):
        with closing(sqlite3.connect(self.path)) as conn:
            state = self.get_in(conn, task_id)
        require(state is not None, 'TASK_NOT_FOUND')
        return state

    def history(self, task_id):
        with closing(sqlite3.connect(self.path)) as conn:
            rows = conn.execute('SELECT state_version,revision,state FROM history WHERE task_id=? ORDER BY state_version', (task_id,)).fetchall()
        return [dict(state_version=v, revision=r, state=strict_json(s)) for v, r, s in rows]

    @staticmethod
    def save(conn, state, event_id, payload_hash, ack):
        encoded = encode(state)
        conn.execute('INSERT INTO tasks VALUES(?,?) ON CONFLICT(task_id) DO UPDATE SET state=excluded.state', (state['task_id'], encoded))
        conn.execute('INSERT INTO history VALUES(?,?,?,?)', (state['task_id'], state['state_version'], state['revision'], encoded))
        conn.execute('INSERT INTO events VALUES(?,?,?,?)', (state['task_id'], event_id, payload_hash, encode(ack)))
