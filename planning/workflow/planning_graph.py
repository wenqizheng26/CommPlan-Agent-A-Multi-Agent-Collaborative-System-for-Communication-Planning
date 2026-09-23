"""Bounded confirm/calculate/validate/publish graph with a durable human interrupt."""
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from planning.requirements_contract import require
from planning.services.confirmation import review_for, validate_snapshot
from planning.services import calculation
from planning.agents.calculation import CalculationAgent
from planning.agents.review import ReviewAgent, validate_assessment, REASONS
from planning.agents.role_model import LocalRoleSelector
from planning.agents.orchestrator import decide, MAX_CALCULATIONS
from planning.workflow.requirements_graph import run_requirements, stamp
from planning.workflow.activity import observe


class PlanningState(TypedDict):
    request: dict
    report: dict | None
    review: dict | None
    confirmed_snapshot: dict | None
    result: dict | None
    validations: list
    final_report: dict | None
    status: str
    trace: list
    failure: dict | None
    calculation_role: dict | None
    review_assessment: dict | None
    calculation_attempts: int
    execution_results: list
    review_history: list
    calculation_roles: list
    routing_decisions: list
    routed_action: str


def trace(state, node, status):
    return state['trace']+[dict(node=node,status=status,at=stamp())]


def failed(state, node, exc):
    return dict(status='FAILED', result=None, final_report=None,
                failure=dict(code=str(exc) if isinstance(exc,ValueError) else 'EXECUTION_ERROR',
                             responsible_node=node, message='当前步骤未通过，未发布计算结果。',
                             next_action='保留当前需求，核对模型目录或运行环境；修正后通过编辑重新规划。'),
                trace=trace(state,node,'FAILED'))


def role_selector(agent, bindings, role):
    # False: deterministic. None: default local model. A bound selector: the model this command chose.
    if not getattr(agent, 'selector', None):
        return False
    return LocalRoleSelector(bindings[role]) if bindings else None


def build_planning_graph(agent, saver, cards, observer=None, pending_questions=(), calculation_agent=None, review_agent=None,
                         review_context=None, bindings=None):
    calculation_agent = calculation_agent or CalculationAgent(role_selector(agent, bindings, 'compute_agent'))
    review_agent = review_agent or ReviewAgent(role_selector(agent, bindings, 'validator_agent'), context=review_context)
    def propose(state):
        observe(observer,'requirements','started',caller='orchestrator')
        output = run_requirements(state['request'],agent,expected_revision=state['request']['revision'])
        report, status = output['report'], output['status']
        if pending_questions and report and status!='FAILED':
            report['questions']=list(dict.fromkeys(report['questions']+list(pending_questions)))
            status=report['execution_status']='AWAITING_INPUT'
        observe(observer,'requirements','failed' if status=='FAILED' else 'completed',status=status,caller='orchestrator')
        if status in {'AWAITING_INPUT','NEEDS_MODEL'}:
            observe(observer,'supplement' if status=='AWAITING_INPUT' else 'gap','waiting',status=status)
        return dict(report=report,status=status,review=review_for(state['request'],report,cards) if report else None,
                    trace=output['trace'],failure=None if status!='FAILED' else dict(code='REQUIREMENTS_FAILED',
                    responsible_node='requirements',message='需求解析未完成。',next_action='核对输入或选择确定性模式重试。'))

    def confirm(state):
        # No writes before interrupt: this node re-enters on Command(resume).
        observe(observer,'confirmation','waiting',caller='requirements')
        decision = interrupt({'review_hash':state['review']['review_hash'],'task_id':state['request']['task_id'],
                              'revision':state['request']['revision']})
        if decision['action']=='cancel':
            observe(observer,'confirmation','cancelled')
            return dict(status='CANCELLED',trace=trace(state,'human_confirmation','CANCELLED'))
        require(decision['action']=='confirm','INVALID_CONFIRM_ACTION')
        snapshot = validate_snapshot(decision['snapshot'],state['review'],cards)
        observe(observer,'confirmation','completed',caller='requirements')
        return dict(confirmed_snapshot=snapshot,status='READY_TO_CALCULATE',trace=trace(state,'human_confirmation','CONFIRMED'))

    def calculate(state):
        observe(observer,'calculation','started',caller='orchestrator')
        attempt = state.get('calculation_attempts', 0) + 1
        role = None
        try:
            require(attempt <= MAX_CALCULATIONS, 'CALCULATION_BUDGET_EXHAUSTED')
            role = calculation_agent.run(state['confirmed_snapshot'], observer=observer)
            result = calculation.execute(state['confirmed_snapshot'],state['review'],cards,role['proposal'],observer=observer,attempt=attempt)
            observe(observer,'calculation','completed',caller='orchestrator')
            return dict(result=result,calculation_role=role,calculation_attempts=attempt,
                        calculation_roles=state.get('calculation_roles',[])+[dict(attempt=attempt,role=role)],
                        execution_results=state.get('execution_results',[])+[result],
                        review_assessment=None,validations=[],final_report=None,failure=None,
                        status='VALIDATING_RESULT',trace=trace(state,'calculation','CALCULATED'))
        except Exception as exc:
            observe(observer,'calculation','failed',error=type(exc).__name__)
            output = failed(state,'calculation',exc)
            output.update(calculation_attempts=attempt,calculation_role=role,review_assessment=None,validations=[],
                calculation_roles=state.get('calculation_roles',[])+[dict(attempt=attempt,role=role)])
            # Only a tool transport failure is retryable. Model/schema/domain/storage
            # failures cannot use this route to bypass the existing hard gates.
            if role is not None and isinstance(exc,(TimeoutError,ConnectionError)):
                output['status']='RETRYABLE_CALCULATION_FAILURE'
                output['failure']['code']='TRANSIENT_TOOL_FAILURE'
            return output

    def validate(state):
        observe(observer,'validation','started',caller='orchestrator')
        try:
            values=calculation.validate_result(state['result'],state['confirmed_snapshot'])
            require(all(v['passed'] for v in values),'VALIDATION_FAILED')
            observe(observer,'validation','completed',checks=len(values),caller='orchestrator')
            return dict(validations=values,status='REVIEWING_RESULT',trace=trace(state,'validate_result','PASSED'))
        except Exception as exc:
            observe(observer,'validation','failed',error=type(exc).__name__)
            return failed(state,'validate_result',exc)

    def review_result(state):
        observe(observer,'review','started',caller='orchestrator')
        try:
            assessment = review_agent.run(state['result'], state['confirmed_snapshot'], observer=observer)
            decision = validate_assessment(assessment, state['result'], state['confirmed_snapshot'])['decision']
            status = {'pass':'VALIDATING_REPORT','needs_input':'AWAITING_INPUT',
                      'not_applicable':'NEEDS_MODEL','recalculate':'RECALCULATION_REQUESTED'}[decision]
            observe(observer,'review','completed',caller='orchestrator',decision=decision)
            return dict(review_assessment=assessment,review_history=state.get('review_history',[])+[assessment],
                        status=status,trace=trace(state,'review_result',decision.upper()))
        except Exception as exc:
            observe(observer,'review','failed',caller='orchestrator',error=type(exc).__name__)
            return failed(state,'review_result',exc)

    def route(state):
        observe(observer,'orchestrator','started',mode='bounded_policy')
        decision = decide(state)
        output = dict(routed_action=decision['action'],
            routing_decisions=state.get('routing_decisions',[])+[decision],
            trace=trace(state,'orchestrator',decision['reason_code']))
        if decision['reason_code']=='calculation_budget_exhausted':
            output.update(status='FAILED',final_report=None,
                failure=dict(code='CALCULATION_BUDGET_EXHAUSTED',responsible_node='orchestrator',
                    message='本版本计算次数已达到上限，未发布结果。',next_action='核对工具或审查意见，编辑后重新确认。'))
        elif decision['action']=='calculation':
            output['status']='RETRY_WAIT'
        observe(observer,'orchestrator','completed',mode='bounded_policy',**{k:v for k,v in decision.items() if k!='mode'})
        return output

    def publish(state):
        observe(observer,'publish','started',caller='validator_agent')
        try:
            require(validate_assessment(state['review_assessment'],state['result'],state['confirmed_snapshot'])['decision']=='pass', 'REVIEW_NOT_PASSED')
            report = calculation.publish(state['result'],state['confirmed_snapshot'],state['validations'])
            assessment = state['review_assessment']
            report['review'] = dict(assessment_hash=assessment['assessment_hash'],
                decision=assessment['role']['proposal']['decision'], mode=assessment['role']['mode'],
                summary=REASONS['pass'][1], fact_ids=assessment['role']['proposal']['fact_ids'])
            report['component_modes'].update(calculation=state['calculation_role']['mode'],review=assessment['role']['mode'])
            report['component_modes']['orchestrator']='bounded_policy'
            if 'deterministic_fallback' in report['component_modes'].values(): report['runtime_health']='degraded'
            observe(observer,'publish','completed',caller='validator_agent')
            return dict(final_report=report,status='COMPLETED',trace=trace(state,'publish','COMPLETED'))
        except Exception as exc:
            observe(observer,'publish','failed',error=type(exc).__name__)
            return failed(state,'publish',exc)

    graph=StateGraph(PlanningState)
    for name,node in [('requirements',propose),('human_confirmation',confirm),('calculation',calculate),('validate_result',validate),('review_result',review_result),('orchestrator',route),('publish',publish)]:
        graph.add_node(name,node)
    graph.add_edge(START,'requirements')
    graph.add_conditional_edges('requirements',lambda s:'human_confirmation' if s['status']=='AWAITING_CONFIRMATION' else END)
    graph.add_conditional_edges('human_confirmation',lambda s:END if s['status']=='CANCELLED' else 'calculation')
    graph.add_edge('calculation','orchestrator')
    graph.add_conditional_edges('validate_result',lambda s:END if s['status']=='FAILED' else 'review_result')
    graph.add_edge('review_result','orchestrator')
    graph.add_conditional_edges('orchestrator',lambda s:END if s['routed_action']=='stop' else s['routed_action'])
    graph.add_edge('publish',END)
    return graph.compile(checkpointer=saver)
