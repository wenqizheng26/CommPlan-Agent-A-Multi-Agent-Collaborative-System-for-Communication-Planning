"""Frozen-case end-to-end acceptance. Each run is append-only and never overwrites evidence."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import time
import uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from planning.workflow.task_service import TaskService


def command(action,state=None,**extra):
    return dict(action=action,task_id=state['task_id'] if state else str(uuid.uuid4()),event_id=str(uuid.uuid4()),
        expected_revision=state['revision'] if state else 0,expected_state_version=state['state_version'] if state else 0,**extra)


def run_task(service,text,mode,condition_answer=True):
    states=[];timings=[]
    def apply(c):
        start=time.monotonic();s=service.apply(c)['state'];timings.append(dict(action=c['action'],seconds=time.monotonic()-start));states.append(s);return s
    s=apply(command('create',input=dict(raw_text=text,manual_parameters={},condition=None,target=None),mode=mode))
    # Only the explicitly allowed free-space clarification is answered. No target or numerical repair.
    issue=next((i for i in s.get('input_issues',[]) if i['field']=='condition'),None)
    if issue and condition_answer:
        s=apply(command('answer',s,answers={issue['id']:'free_space_reference'},mode=mode))
    if s['status']=='AWAITING_CONFIRMATION':
        assert s['result'] is None and s.get('confirmed_snapshot') is None
        s=apply(command('confirm',s,review_hash=s['review']['review_hash']))
    return dict(state=s,states=states,timings=timings)


def assess(case,run):
    s=run['state'];want=case['expected'];errors=[]
    def check(ok,message):
        if not ok:errors.append(message)
    check(s['status'].lower()==want.get('status',s['status'].lower()),'status')
    report=s.get('final_report') or {};requirements=s.get('report') or {}
    if case['category']=='main':
        check(requirements.get('targets')==[want['target']],'target')
        req=requirements.get('requirement') or {}
        check(all(req.get(k)==v for k,v in want['requirement'].items()),'requirement')
        check((requirements.get('solve') or {}).get('unknown')==want['solve'],'solve_request')
        sources={o.get('source_ref','').split('#')[0] for p in requirements.get('parameters_proposal',[]) for o in p.get('origins',[])}
        check(set(want['sites'])<=sources,'site_sources')
        check(want['device'] in sources,'device_source')
    if 'margin_db' in want:
        value=(report.get('outputs') or [{}])[0].get('value')
        check(type(value) in (float,int) and abs(value-want['margin_db'])<=want['tolerance'],'margin')
    if 'power_dbm' in want:
        value=report.get('solve',{}).get('value')
        check(type(value) in (float,int) and abs(value-want['power_dbm'])<=want['tolerance'],'solved_power')
        check(report.get('solve',{}).get('rated',{}).get('exceeded') is True,'rated')
    if want.get('no_solve'):check('solve' not in report,'unexpected_solve')
    if want.get('no_loss'):
        check(s.get('failure',{}).get('code')=='BEYOND_LINE_OF_SIGHT' and s['result'] is None,'horizon')
        check(all(x['tool_id'] in {'slant_range_wgs84','radio_horizon'} for x in s.get('failure',{}).get('details',{}).get('steps',[])),'loss_after_horizon')
    if 'question' in want:
        issues=[i for i in s.get('input_issues',[]) if i['field']==want['question']]
        check(bool(issues),'missing_question')
        if 'choices' in want:
            p=next((p for p in requirements.get('parameters_proposal',[]) if p['canonical_name']==want['question']),{})
            check(p.get('status')=='conflicting','missing_conflict')
    if 'sites' in want and case['category']=='variant':
        ids={c['id'] for d in requirements.get('diagnostics',[]) for c in d.get('details',{}).get('candidates',[]) if isinstance(c,dict) and 'id' in c}
        check(any(i['field']=='entity' and len(i.get('choices',[]))>=2 for i in s.get('input_issues',[])),'missing_ambiguity')
    return errors


def bits(outputs):
    return [(o['name'],o['unit'],struct.pack('!d',o['value']).hex()) for o in outputs]


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True)
    p.add_argument('--models',default='qwen35-9b-q4',help='Registered chat model id for this run')
    p.add_argument('--categories',default='main,variant,offline_equivalence');p.add_argument('--ids',default='');args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    cases_path=ROOT/'tests/eval/m1_cases.jsonl'
    cases=[json.loads(line) for line in cases_path.read_text(encoding='utf-8').splitlines()]
    from planning.build_info import build_fingerprint
    fingerprint=build_fingerprint(ROOT)
    service=TaskService(ROOT,args.output/'tasks.sqlite');rows=[]
    from planning.services.model_status import probe_model
    model=service.registry.models[args.models]
    if model['kind']!='chat':raise ValueError('EVAL_CHAT_MODEL_REQUIRED')
    live=probe_model(model['endpoint'],model['alias'])
    if live['status']!='ready':raise RuntimeError('EVAL_MODEL_NOT_READY: '+str(live))
    saved=service.settings.get();settings=saved['settings'];settings['chat']['default']=args.models
    service.settings.put(settings,saved['version'])
    metadata=dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_dirty=bool(subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip()),
        model=args.models,model_revision=model.get('revision'),live=live)
    for case in cases:
        if case['category'] not in args.categories.split(','):continue
        if args.ids and case['id'] not in args.ids.split(','):continue
        if build_fingerprint(ROOT)!=fingerprint:raise RuntimeError('EVAL_SOURCE_CHANGED: freeze source throughout the run')
        start=time.monotonic()
        try:
            result=run_task(service,case['text'],'llm')
            errors=assess(case,result)
            if case['category']=='offline_equivalence':
                offline=run_task(service,case['text'],'deterministic');result['offline']=offline
                online_report=result['state'].get('final_report') or {};off_report=offline['state'].get('final_report') or {}
                target={'fspl':'fspl_ghz'}.get(case['expected']['target'],case['expected']['target'])
                if result['state']['status']!='COMPLETED' or offline['state']['status']!='COMPLETED':errors.append('incomplete_equivalence')
                elif bits(online_report['outputs'])!=bits(off_report['outputs']):errors.append('bitwise_mismatch')
                if result['state'].get('result',{}).get('model_id')!=target:errors.append('target')
            row=dict(id=case['id'],category=case['category'],passed=not errors,errors=errors,seconds=time.monotonic()-start)
            role=(result['state'].get('report') or {}).get('planning_role') or {}
            row.update(plan_mode=role.get('mode'),plan_attempts=role.get('attempts',0),
                model_plan_accepted=role.get('mode')=='llm',agrees_with_program=role.get('agrees_with_program'))
            events=service.activity.events(result['state']['task_id'])
            row['model_calls']=sum(e['node']=='llm' and e['phase']=='started' for e in events)
        except Exception as exc:
            result=dict(exception=type(exc).__name__,error=str(exc));row=dict(id=case['id'],category=case['category'],passed=False,errors=[str(exc)],seconds=time.monotonic()-start)
        (args.output/(case['id']+'.json')).write_text(json.dumps(dict(case=case,result=result,summary=row),ensure_ascii=False,indent=2),encoding='utf-8')
        rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
        if build_fingerprint(ROOT)!=fingerprint:raise RuntimeError('EVAL_SOURCE_CHANGED: freeze source throughout the run')
        (args.output/'summary.json').write_text(json.dumps(dict(**metadata,build=fingerprint,cases_sha256=hashlib.sha256(cases_path.read_bytes()).hexdigest(),rows=rows),ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if rows and all(r['passed'] for r in rows) else 1


if __name__=='__main__':raise SystemExit(main())
