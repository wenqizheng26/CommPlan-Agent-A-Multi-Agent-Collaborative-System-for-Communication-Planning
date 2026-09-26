"""Execute the frozen H1-H4 attacks; no real model is required for trust-boundary tests."""
import argparse
import copy
import io
import json
from pathlib import Path
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from formula_rag.catalog import load_catalog
from formula_rag.core import evaluate
from planning.agents.requirements import RequirementsAgent
from planning.agents.planner import compile_proposal,proposal_for
from planning.services.requirement_validation import check_report
from test_requirements_contract import request


def run(case):
    scenario=case['scenario'];cards=load_catalog(ROOT)
    q=request('按自由空间基准，频率 2 GHz，距离 1 km，求路径损耗')
    r=RequirementsAgent(ROOT,selector=False).run(q)
    if scenario in {'unverified_formula','injected_unknown_formula','forged_source_quote'}:
        try:
            if scenario=='unverified_formula':
                next(c for c in cards if c['id']=='fspl_ghz')['status']='draft'
                compile_proposal(proposal_for(r),r,cards)
            elif scenario=='injected_unknown_formula':
                p=proposal_for(r);p['steps'][0]['card']='unknown_tool';compile_proposal(p,r,cards)
            else:
                p=next(p for p in r['parameters_proposal'] if p['canonical_name']=='frequency_ghz')
                p['origins'][0]['span']=[0,2];check_report(r,q,cards,ROOT)
        except ValueError as exc:return dict(passed=True,block_code=str(exc))
        return dict(passed=False,error='attack accepted')
    if scenario=='negative_distance':
        result=evaluate(next(c for c in cards if c['id']=='fspl_ghz'),dict(frequency_ghz=2,distance_km=-1))
        return dict(passed=result['status']=='invalid_parameters' and 'value' not in result,result=result)
    tests={
        'beyond_horizon':'test_plan_goal.PlanGoalTests.test_a_link_beyond_the_radio_horizon_stops_before_the_path_loss',
        'conflicting_device_power':'test_requirement_facts.FactSourceTests.test_a_text_value_that_differs_from_the_record_is_a_conflict',
        'invented_answer_number':'test_review_answer.ReviewAnswerTests.test_text_that_fails_twice_is_withheld_and_the_rest_is_kept',
        'invented_step_number':'test_review_answer.ReviewAnswerTests.test_text_that_fails_twice_is_withheld_and_the_rest_is_kept'}
    log=io.StringIO();result=unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromName(tests[scenario]))
    return dict(passed=result.wasSuccessful(),test=tests[scenario],log=log.getvalue())


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    cases=[json.loads(x) for x in (ROOT/'tests/eval/m1_cases.jsonl').read_text(encoding='utf-8').splitlines()]
    with args.output.open('x',encoding='utf-8') as f:
        for case in cases:
            if case['category']!='hard_rule':continue
            result=run(case);row=dict(id=case['id'],rule=case['rule'],**result)
            f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();print(case['id'],result['passed'],flush=True)


if __name__=='__main__':main()
