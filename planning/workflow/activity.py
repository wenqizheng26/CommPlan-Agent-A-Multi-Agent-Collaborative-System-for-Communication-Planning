"""Best-effort observation only; never authorizes a business state transition.

Separate SQLite file allows reads while the main task transaction is open.
Events describe attempted work; only the main database is authoritative.
"""
from contextlib import closing
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import uuid


def now():
    return datetime.now(timezone.utc).isoformat()


def observe(observer, node, phase, **details):
    if observer:
        try:
            observer(node, phase, details)
        except Exception:
            # Loss of diagnostic progress must not roll back confirmed work.
            pass


class ActivityStore:
    def __init__(self, db_path):
        self.path = Path(str(db_path)+'.activity.sqlite')
        self.available = True
        try:
            with closing(sqlite3.connect(self.path, timeout=1)) as conn:
                conn.executescript('''
                    CREATE TABLE IF NOT EXISTS runs(
                        run_id TEXT PRIMARY KEY, task_id TEXT, event_id TEXT,
                        revision INTEGER, phase TEXT);
                    CREATE TABLE IF NOT EXISTS activity(
                        seq INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT,
                        task_id TEXT, event_id TEXT, revision INTEGER,
                        node TEXT, phase TEXT, at TEXT, details TEXT);
                    CREATE INDEX IF NOT EXISTS activity_task ON activity(task_id,seq);
                ''')
        except sqlite3.Error:
            self.available = False

    def start(self, command):
        run = dict(run_id=str(uuid.uuid4()),task_id=command['task_id'],event_id=command['event_id'],
                   revision=command['expected_revision']+(command['action'] in {'edit','supplement','answer'}))
        if self.available:
            with closing(sqlite3.connect(self.path, timeout=1)) as conn, conn:
                conn.execute('INSERT INTO runs VALUES(?,?,?,?,?)',
                             (*run.values(),'started'))
            self.append(run,'command','started',{'action':command['action']})
        return run

    def append(self, run, node, phase, details=None):
        if not self.available or run is None:
            return
        with closing(sqlite3.connect(self.path, timeout=1)) as conn, conn:
            conn.execute('INSERT INTO activity(run_id,task_id,event_id,revision,node,phase,at,details) VALUES(?,?,?,?,?,?,?,?)',
                         (run['run_id'],run['task_id'],run['event_id'],run['revision'],node,phase,now(),
                          json.dumps(details or {},ensure_ascii=False,allow_nan=False)))

    def finish(self, run, phase, **details):
        if not self.available or run is None:
            return
        self.append(run,'command',phase,details)
        with closing(sqlite3.connect(self.path, timeout=1)) as conn, conn:
            conn.execute('UPDATE runs SET phase=? WHERE run_id=?',(phase,run['run_id']))

    def events(self, task_id):
        if not self.available:
            return []
        with closing(sqlite3.connect(self.path, timeout=1)) as conn:
            conn.row_factory=sqlite3.Row
            rows=conn.execute('SELECT * FROM activity WHERE task_id=? ORDER BY seq DESC LIMIT 1000',(task_id,)).fetchall()
        return [dict(dict(row),details=json.loads(row['details'])) for row in reversed(rows)]

    def interrupt_open(self):
        if not self.available:
            return
        with closing(sqlite3.connect(self.path, timeout=1)) as conn:
            conn.row_factory=sqlite3.Row
            runs=conn.execute("SELECT * FROM runs WHERE phase='started'").fetchall()
        for run in runs:
            self.finish(dict(run),'interrupted',message='服务重启；该次观察未记录提交完成，请以任务保存状态为准。')
