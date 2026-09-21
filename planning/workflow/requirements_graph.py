"""Four bounded nodes; reaching END never authorizes a calculation."""
import copy
from datetime import datetime, timezone
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from planning.requirements_contract import validate_request
from planning.services.requirement_validation import check_report


class RequirementSliceState(TypedDict):
    request: dict
    report: dict | None
    trace: list[dict]
    status: str


def stamp():
    return datetime.now(timezone.utc).isoformat()


def event(state, node, status, reason='', message='', started=None):
    request = state.get('request')
    request = request if isinstance(request,dict) else {}
    return dict(node=node, task_id=request.get('task_id'), revision=request.get('revision'),
                started_at=started or stamp(), finished_at=stamp(), status=status, reason_code=reason,
                message=message, attempt=1,
                component_modes=(state.get('report') or {}).get('component_modes', {}))


def failure_state(request, code, message, node='receive_request'):
    state = dict(request=request, report=None, trace=[], status='FAILED')
    state['trace'] = [event(state,node,'FAILED',code,message)]
    return state


def build_requirements_graph(agent, *, expected_revision=None):
    trusted_cards = copy.deepcopy(agent.cards)
    def receive(state):
        started = stamp()
        try:
            request = validate_request(state['request'],expected_revision=expected_revision)
            return dict(request=request,status='RECEIVED',trace=state['trace']+[event(state,'receive_request','RECEIVED',started=started)])
        except (ValueError, TypeError, KeyError) as exc:
            code = 'STALE_REVISION' if str(exc)=='STALE_REVISION' else 'INVALID_REQUEST'
            return dict(status='FAILED',report=None,trace=state['trace']+[event(state,'receive_request','FAILED',code,'请求格式或版本无效，请核对输入后重新提交。',started)])

    def propose(state):
        started = stamp()
        try:
            report = agent.run(copy.deepcopy(state['request']),expected_revision=expected_revision)
            return dict(report=report,status='PROPOSED',trace=state['trace']+[event(state,'propose_requirements','PROPOSED',started=started)])
        except Exception as exc:
            return dict(report=None,status='FAILED',trace=state['trace']+[event(state,'propose_requirements','FAILED','AGENT_FAILED',f'需求处理失败（{type(exc).__name__}），请核对服务和知识目录后重试。',started)])

    def check(state):
        started = stamp()
        try:
            report = check_report(state['report'],state['request'],trusted_cards)
            status = report['execution_status']
            return dict(report=report,status=status,trace=state['trace']+[event(state,'check_requirements',status,started=started)])
        except Exception as exc:
            return dict(report=None,status='FAILED',trace=state['trace']+[event(state,'check_requirements','FAILED','REPORT_INVALID',f'报告未通过确定性复核（{type(exc).__name__}），草稿不可使用。',started)])

    def finish(state):
        return dict(trace=state['trace']+[event(state,'finish',state['status'])])

    graph = StateGraph(RequirementSliceState)
    for name, fn in [('receive_request',receive),('propose_requirements',propose),('check_requirements',check),('finish',finish)]:
        graph.add_node(name,fn)
    graph.add_edge(START,'receive_request')
    graph.add_conditional_edges('receive_request',lambda s:'finish' if s['status']=='FAILED' else 'propose_requirements')
    graph.add_conditional_edges('propose_requirements',lambda s:'finish' if s['status']=='FAILED' else 'check_requirements')
    graph.add_edge('check_requirements','finish')
    graph.add_edge('finish',END)
    return graph.compile()


def run_requirements(request, agent, expected_revision=None):
    initial = dict(request=copy.deepcopy(request),report=None,trace=[],status='RECEIVED')
    try:
        return build_requirements_graph(agent,expected_revision=expected_revision).invoke(initial,{'recursion_limit':8})
    except Exception as exc:
        code = 'STEP_LIMIT' if type(exc).__name__=='GraphRecursionError' else 'WORKFLOW_FAILED'
        return failure_state(request,code,'工作流未完成，请检查运行环境后重试。','workflow')
