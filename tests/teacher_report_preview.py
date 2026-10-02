"""T4 browser QA: production UI/API, isolated SQLite and an ephemeral port.

Replay the deterministic report fixtures without changing the running workbench.
Run with the repository Python: python tests/teacher_report_preview.py
"""
import copy
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from planning.web_server import create_server
from planning.workflow.task_service import TaskService


def main():
    with tempfile.TemporaryDirectory(prefix='commplan-t4-browser-') as temporary:
        db = Path(temporary) / 'tasks.sqlite'
        service = TaskService(ROOT, db)
        tasks = {}
        for name in ('margin', 'comparison', 'defaults', 'fspl_legacy'):
            fixture = json.loads((ROOT / 'tests/fixtures/teacher_report' / (name + '.json')).read_text(encoding='utf-8'))
            state = None
            for saved in fixture['commands']:
                command = copy.deepcopy(saved)
                if state is not None:
                    command.update(expected_revision=state['revision'], expected_state_version=state['state_version'])
                    if command['action'] == 'confirm':
                        command['review_hash'] = state['review']['review_hash']
                state = service.apply(command)['state']
            assert state['status'] == 'COMPLETED', (name, state['status'])
            assert state['mode'] == 'deterministic'
            tasks[name] = state['task_id']
        server = create_server(ROOT, db, port=0)
        print(json.dumps({'url': f'http://127.0.0.1:{server.server_port}', 'tasks': tasks,
                          'db': str(db), 'mode': 'deterministic'}, ensure_ascii=False), flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == '__main__':
    main()
