"""Capture real deterministic TaskService states for the T4 report view.

Run from any directory with the project's Python environment::

    python tests/generate_teacher_report_fixtures.py

Each fixture retains the actual completed state and all recorded activity events.
SQLite databases exist only inside a temporary directory. UUIDs, hashes and UTC
timestamps inside the returned state/events are deliberately not rewritten: this
script reproduces the workflow and numerical results, not identical capture bytes.
No model or workbench HTTP service is required or contacted.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))

from planning.workflow.task_service import TaskService
from test_calculation_plans import MARGIN, command
from test_teacher_path import CASES, TEXT3, manual


def capture(name, text, source, adopt_suggestions=False, target=None):
    """Execute the test's create/answer/confirm path without synthesizing state."""
    with tempfile.TemporaryDirectory(prefix=f't4-report-{name}-') as temporary:
        service = TaskService(ROOT, Path(temporary) / 'tasks.sqlite')
        settings = service.settings.get()['settings']
        assert settings['mode_default'] == 'deterministic', settings
        assert settings['retrieval']['mode'] == 'lexical', settings
        commands = []

        def apply(action='create', state=None, **changes):
            request = command(action, state, text=text, **changes)
            commands.append(request)
            return service.apply(request)['state']

        changes = manual(text, target) if target else {}
        draft = apply(**changes)
        initial_status = draft['status']
        if adopt_suggestions:
            assert initial_status == 'AWAITING_INPUT', draft
            issues = draft['input_issues']
            assert {i['field'] for i in issues} == {
                'distance_km', 'tx_power_dbm', 'tx_gain_dbi', 'rx_gain_dbi', 'modulation'
            }, issues
            answers = {i['id']: i['suggestion']['value'] for i in issues}
            draft = apply('answer', draft, answers=answers)
            turn = draft['conversation']['turns'][-1]
            assert turn['mode'] == 'suggestion', turn
            assert all(a['suggested'] for a in turn['answers']), turn
        assert draft['status'] == 'AWAITING_CONFIRMATION', draft
        state = apply('confirm', draft)
        assert state['status'] == 'COMPLETED', state
        assert state['mode'] == 'deterministic', state['mode']
        events = service.activity.events(state['task_id'])
        model_calls = service.model_calls.calls(state['task_id'])
        assert not model_calls, model_calls
        assert not any(e['node'] == 'llm' for e in events), events
        assert all(v['passed'] for v in state['validations']), state['validations']
        tool_events = [e for e in events if e['node'] == 'tool' and e['phase'] == 'completed']
        return {
            'provenance': {
                'kind': 'real-deterministic-task-service',
                'generator': 'tests/generate_teacher_report_fixtures.py',
                'source': source,
                'git_commit': subprocess.check_output(
                    ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True
                ).strip(),
                'captured_at': state['updated_at'],
                'mode': 'deterministic',
                'retrieval_mode': settings['retrieval']['mode'],
                'storage': 'temporary SQLite database, removed after capture',
                'initial_status': initial_status,
                'model_call_count': len(model_calls),
                'tool_event_count': len(tool_events),
                'notes': ('Native single-step FSPL result shape has no result.steps.'
                          if name == 'fspl_legacy' else
                          'Complete returned state and activity events; no synthetic values.'),
            },
            'commands': commands,
            'state': state,
            'events': events,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path,
                        default=ROOT / 'tests/fixtures/teacher_report')
    destination = parser.parse_args().output_dir
    destination.mkdir(parents=True, exist_ok=True)
    specifications = [
        ('margin', MARGIN, 'tests/test_calculation_plans.py:MARGIN', False, None),
        ('comparison', TEXT3,
         'tests/test_teacher_path.py:TEXT3/manual; teacher_03 antenna gain labels made explicit',
         False, 'link_margin'),
        ('defaults', CASES['teacher_02']['text'],
         'tests/test_teacher_path.py:test_case_two_lists_the_gaps_with_table_suggestions_that_one_answer_adopts',
         True, 'link_margin'),
        ('fspl_legacy', '按自由空间基准计算，频率2GHz，距离1km，求路径损耗。',
         'tests/test_calculation_plans.py:test_single_step_fspl_keeps_the_v010_result_shape',
         False, None),
    ]
    for name, text, source, suggestions, target in specifications:
        fixture = capture(name, text, source, suggestions, target)
        if name == 'comparison':
            assert len(fixture['state']['final_report']['comparison']['rows']) == 2
        if name == 'fspl_legacy':
            assert 'steps' not in fixture['state']['result']
        output = destination / f'{name}.json'
        output.write_text(json.dumps(fixture, ensure_ascii=False, indent=2, allow_nan=False) + '\n',
                          encoding='utf-8')
        print(f'{output.name}: COMPLETED; model calls 0; '
              f'tool events {fixture["provenance"]["tool_event_count"]}')


if __name__ == '__main__':
    main()
