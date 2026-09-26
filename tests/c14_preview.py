"""Local C14 viewport harness; real UI/API, deterministic seeded model responses.

Production UI, headers and routes are used unchanged.
Run: python tests/c14_preview.py --db outputs/c14-preview/tasks.sqlite --port 18085
"""
import argparse
import copy
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from planning.web_server import create_server
from planning.workflow.task_service import TaskService
from planning.agents.review import ReviewAgent
from planning.agents.planner import PlanningAgent, proposal_for
from test_requirement_facts import ask, labeller
from test_plan_goal import command


def seed(db):
    db.parent.mkdir(parents=True,exist_ok=True)
    service=TaskService(ROOT,db)
    tasks={}
    original=PlanningAgent.run
    def plan(self,request,report,cards,observer=None):
        proposal=proposal_for(report)
        proposal['assessment']=dict(verdict='ready',notes=[
            dict(kind='goal',text='计算链路余量并核对要求，不满足时反求发射功率。',refs=['target']),
            dict(kind='applicability',text='自由空间结果仅作基准，未计反射与地形遮挡。',refs=['conditions'])])
        return original(PlanningAgent(lambda *a:dict(output=copy.deepcopy(proposal))),request,report,cards,observer)
    for case,end in [('B','B'),('C','C'),('F','F'),('edit','B')]:
        text=ask(end)
        with patch('planning.workflow.task_service.LocalSelector',return_value=labeller(text,end)),patch.object(PlanningAgent,'run',plan):
            state=service.apply(command(text=text))['state']
        assert state['status']=='AWAITING_CONFIRMATION'
        if case!='edit':
            def review(*args):
                enough=end=='F'
                return dict(output=dict(decision='pass' if enough else 'caution',
                    answer='余量 15.01 dB，满足 10 dB 要求。' if enough else '余量 5.93 dB，不满足 10 dB；发射功率至少 41.07 dBm，超过额定值。',
                    opinions=[] if enough else [dict(kind='risk',text='所需发射功率超过所选电台额定值。',refs=['solve'])],steps=[]))
            with patch('planning.workflow.planning_graph.role_selector',return_value=False),patch('planning.workflow.planning_graph.ReviewAgent',return_value=ReviewAgent(review)):
                state=service.apply(command('confirm',state))['state']
        tasks[case]=state['task_id']
    (db.parent/'tasks.json').write_text(json.dumps(tasks,indent=2),encoding='utf-8')
    return tasks


def main():
    p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);p.add_argument('--port',type=int,default=18085);a=p.parse_args()
    tasks=seed(a.db) if not a.db.exists() else json.loads((a.db.parent/'tasks.json').read_text())
    server=create_server(ROOT,a.db,a.port)
    print(json.dumps(tasks),flush=True)
    server.serve_forever()


if __name__=='__main__':main()
