"""Live local model acceptance of bilingual budgets and supplementary plans.

Uses a temporary knowledge copy and SQLite database. Refuses to overwrite output;
records fallback separately from task/numeric success. Does not download models.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from planning.workflow.task_service import TaskService
from planning.services.model_status import probe_model

CASES=[
 ('zh-budget','zh','按自由空间基准计算链路余量，频率2GHz，距离10km，发射功率30dBm，发射天线增益5dBi，接收天线增益5dBi，接收门限-100dBm。','link_margin'),
 ('zh-knife','zh','采用单刃形障碍物模型，计算单刃形绕射损耗，频率2GHz，d1=15km，d2=15km，障碍物相对高度20m。','knife_edge_loss'),
 ('zh-sea','zh','采用光滑海面单点镜面反射两径模型，计算海面反射附加损耗，频率2GHz，距离30km，起点天线海面高度30m，终点天线海面高度25m。','sea_reflection_two_ray'),
 ('en-fspl','en','Use the free-space reference; frequency 2GHz; distance 1km; calculate path loss.','fspl_ghz'),
 ('en-budget','en','Use the free-space reference; frequency 2GHz; distance 10km; transmit power 30dBm; tx gain 5dBi; rx gain 5dBi; receiver threshold -100dBm; calculate link margin.','link_margin'),
 ('en-fresnel','en','Calculate first Fresnel zone radius; frequency 2GHz; d1=15km; d2=15km.','fresnel_radius'),
 ('en-nu','en','Calculate diffraction parameter; frequency 2GHz; d1=15km; d2=15km; relative obstacle height 20m.','knife_edge_nu'),
 ('en-knife','en','Use a single knife-edge model; calculate knife-edge diffraction loss; frequency 2GHz; d1=15km; d2=15km; relative obstacle height 20m.','knife_edge_loss'),
 ('en-sea','en','Use a smooth sea single specular reflection two-ray model; calculate additional sea-reflection loss; frequency 2GHz; distance 30km; tx height above sea 30m; rx height above sea 25m.','sea_reflection_two_ray'),
]

def command(action,state=None,**kwargs):
    return dict(action=action,task_id=state['task_id'] if state else str(uuid.uuid4()),event_id=str(uuid.uuid4()),
                expected_revision=state['revision'] if state else 0,
                expected_state_version=state['state_version'] if state else 0,**kwargs)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--model',default='qwen35-9b-q4')
    args=parser.parse_args()
    if args.output.exists(): parser.error('output exists; retain the original run')
    output=dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                tracked_dirty=bool(subprocess.check_output(['git','diff','--name-only'],cwd=ROOT,text=True)),
                model_id=args.model,cases=[])
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)/'app'
        from eval_week4 import copy_app  # Same copy, including the files the fact tables cite.
        copy_app(root)
        service=TaskService(root,Path(temp)/'tasks.sqlite')
        model=service.registry.models[args.model]
        output['model_probe']=probe_model(model['endpoint'],model['alias'])
        if output['model_probe']['status']!='ready': raise RuntimeError('MODEL_NOT_READY')
        saved=service.settings.get(); settings=saved['settings']
        settings['chat']['default']=args.model
        for role in settings['chat']['roles']: settings['chat']['roles'][role]=None
        settings['retrieval']['mode']='lexical'
        service.settings.put(settings,saved['version'])
        for ident,lang,text,target in CASES:
            start=time.monotonic(); row=dict(id=ident,lang=lang,text=text,expected_target=target)
            print('start',ident,flush=True)
            try:
                draft=service.apply(command('create',input=dict(raw_text=text,manual_parameters={},condition=None,target=None),mode='llm',lang=lang))['state']
                row.update(create_status=draft['status'],requirements_mode=draft['report']['component_modes']['interpretation'],
                           planning_mode=(draft['report'].get('planning_role') or {}).get('mode'),
                           requirements_diagnostics=draft['report']['diagnostics'])
                if draft['status']=='AWAITING_CONFIRMATION':
                    done=service.apply(command('confirm',draft,review_hash=draft['review']['review_hash'],lang=lang))['state']
                    row.update(status=done['status'],targets=done['report']['targets'],
                               calculation_mode=(done.get('calculation_role') or {}).get('mode'),
                               review_mode=(done.get('review_assessment') or {}).get('role',{}).get('mode'),
                               validations=done.get('validations'),result=done.get('result'),
                               final_report=done.get('final_report'),failure=done.get('failure'))
                    row['passed']=done['status']=='COMPLETED' and done['result']['model_id']==target and all(v['passed'] for v in done['validations'])
                else:
                    row.update(status=draft['status'],passed=False,questions=draft['report']['questions'])
            except Exception as exc:
                row.update(passed=False,error=type(exc).__name__+': '+str(exc))
            row['latency_s']=round(time.monotonic()-start,3)
            row['all_roles_llm']=all(row.get(k)=='llm' for k in ('requirements_mode','planning_mode','review_mode'))
            output['cases'].append(row)
            print(ident,row.get('status'),row['passed'],{k:row.get(k) for k in ('requirements_mode','planning_mode','calculation_mode','review_mode')},flush=True)
    output['summary']=dict(total=len(output['cases']),task_and_numeric_pass=sum(r['passed'] for r in output['cases']),
                           all_roles_llm=sum(r['all_roles_llm'] for r in output['cases']))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as f: json.dump(output,f,ensure_ascii=False,indent=2); f.write('\n')
    print(json.dumps(output['summary']),flush=True)
    return 0 if all(r['passed'] for r in output['cases']) else 1

if __name__=='__main__': raise SystemExit(main())
