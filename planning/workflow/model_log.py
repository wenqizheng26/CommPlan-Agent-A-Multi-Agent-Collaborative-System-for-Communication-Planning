"""Every model call a command makes, with its prompt and response (observation only).

One JSON line per call next to the task database. The page shows a summary of each call;
the full prompt and response are read back from this file on request.
"""
from contextlib import contextmanager
import json
from pathlib import Path
import threading
import uuid
from formula_rag.model_transport import call_log

# The teacher's agent names for the roles that call the model.
AGENTS = {'requirements': 'Requirement', 'supplement': 'Requirement', 'followup': 'Requirement',
          'compute_agent': 'LinkBudget', 'validator_agent': 'Report', 'extraction': 'Extraction'}


class ModelCallLog:
    def __init__(self, db_path):
        self.path = Path(str(db_path) + '.model-calls.jsonl')
        self._lock = threading.Lock()

    @contextmanager
    def recording(self, command):
        # Same revision rule as the activity run: these actions create the next revision.
        context = dict(task_id=command['task_id'], event_id=command['event_id'], action=command['action'],
                       revision=command['expected_revision'] + (command['action'] in {'edit', 'supplement', 'answer'}))

        def write(record):
            line = dict(context, call_id=str(uuid.uuid4()), agent_name=AGENTS.get(record['agent'], record['agent']), **record)
            with self._lock, open(self.path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(line, ensure_ascii=False) + '\n')
        token = call_log.set(write)
        try:
            yield
        finally:
            call_log.reset(token)

    def calls(self, task_id, limit=200):
        """This task's calls, oldest first; a damaged line is skipped."""
        if not self.path.is_file():
            return []
        rows = []
        with self._lock, open(self.path, encoding='utf-8') as f:
            for line in f:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if isinstance(row, dict) and row.get('task_id') == task_id:
                    rows.append(row)
        return rows[-limit:]
