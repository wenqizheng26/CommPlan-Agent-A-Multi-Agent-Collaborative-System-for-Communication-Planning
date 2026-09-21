"""Reproducible acceptance matrix; simulated failures are explicitly labelled.

Run from the implementation root: .venv/Scripts/python.exe -B -X utf8 scripts/validate_role_slice.py
"""
import json
from pathlib import Path
import sys
import tempfile
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from planning.workflow.task_service import TaskService
from planning.agents.review import ReviewAgent
from planning.workflow.requirements_graph import stamp
from formula_rag import core

TEXT = '按自由空间基准计算，频率2GHz，距离1km，求路径损耗。'


def command(action='create', state=None, text=TEXT, **extra):
    c = dict(action=action, task_id=state['task_id'] if state else str(uuid.uuid4()),
        event_id=str(uuid.uuid4()), expected_revision=state['revision'] if state else 0,
        expected_state_version=state['state_version'] if state else 0)
    if action in {'create','edit'}:
        c.update(input=dict(raw_text=text,manual_parameters={},condition=None,target=None),mode='deterministic')
    if action=='confirm': c['review_hash']=state['review']['review_hash']
    return dict(c,**extra)


def main():
    records=[]
    with tempfile.TemporaryDirectory() as directory:
        db=Path(directory)/'acceptance.sqlite'
        service=TaskService(ROOT,db)
        def run(c): return service.apply(c)['state']
        def record(name,state,expected,simulation=None):
            assert state['status']==expected,(name,state['status'])
            records.append(dict(case=name,expected_status=expected,actual_status=state['status'],
                simulation=simulation,state=state))
        draft=run(command()); done=run(command('confirm',draft))
        record('successful_fspl',done,'COMPLETED')
        record('missing_distance',run(command(text='按自由空间基准计算，频率2GHz，求路径损耗。')),'AWAITING_INPUT')
        record('conflicting_frequency',run(command(text=TEXT+'频率3GHz。')),'AWAITING_INPUT')
        record('unsupported_sea_propagation',run(command(text='计算实际海面损耗，频率2GHz，距离1km。')),'NEEDS_MODEL')
        edited=run(command('edit',done,text=TEXT.replace('2GHz','3GHz')))
        assert edited['result'] is None and edited['confirmed_snapshot'] is None and not edited['execution_results']
        record('edit_invalidates',edited,'AWAITING_CONFIRMATION')
        # A new service uses the same on-disk checkpoint, not an in-memory saver.
        recovered=TaskService(ROOT,db).apply(command('confirm',edited))['state']
        record('persistent_checkpoint_resume',recovered,'COMPLETED')
        for exc, name in [(ValueError('TEST_DOMAIN_ERROR'),'tool_hard_failure'),(TimeoutError('TEST_TRANSIENT'),'retry_exhausted')]:
            draft=run(command())
            with patch('formula_rag.core.evaluate',side_effect=exc):
                state=run(command('confirm',draft))
            record(name,state,'FAILED',type(exc).__name__+' injected at tool')
        original=core.evaluate
        def wrong_number(*args):
            value=original(*args); value['value']+=20; return value
        draft=run(command())
        with patch('formula_rag.core.evaluate',side_effect=wrong_number):
            state=run(command('confirm',draft))
        record('independent_numeric_gate',state,'FAILED','tool returns a value 20 dB too high')
        for decision,reason,fact,status in [
            ('needs_input','assumptions_need_review','model_assumptions','AWAITING_INPUT'),
            ('not_applicable','scope_needs_review','confirmed_scope','NEEDS_MODEL'),
            ('recalculate','numerical_recheck','numeric_checks','FAILED')]:
            draft=run(command())
            def selector(*args): return dict(output=dict(decision=decision,reason_code=reason,fact_ids=[fact]))
            with patch('planning.workflow.planning_graph.ReviewAgent',return_value=ReviewAgent(selector)):
                state=run(command('confirm',draft))
            assert state['final_report'] is None
            record('review_'+decision,state,status,'structured reviewer stub; not a live model result')
    output=ROOT/'docs/codex/evidence/role-acceptance-matrix-20260921.json'
    output.write_text(json.dumps(dict(at=stamp(),cases=records),ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'{len(records)} acceptance cases passed: {output}')


if __name__=='__main__': main()
