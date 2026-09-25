"""Structured confirmed inputs enter existing numeric and applicability gates."""
import copy
import math
from formula_rag import core
from formula_rag.applicability import scope_issues, result_issues, describe_result, FARFIELD_NOTE, RULE_VERSION
from planning.requirements_contract import digest, require
from planning.services.confirmation import validate_snapshot
from planning.agents.calculation import propose_calculation
from planning.workflow.requirements_graph import stamp
from planning.workflow.activity import observe
from planning.services.domain_calculation import evaluate_domains, validate_domains, conclusion
from planning.services.reference_models import agrees, REFERENCE

MARGIN_NOTE = '余量只表示所填预算条件下与接收门限的关系，不保证现场可靠通信。'
SOLVE_ERRORS = {'SOLVE_NO_ROOT': '搜索区间内没有满足要求的值', 'SOLVE_NOT_MONOTONIC': '结果随该量不单调，无法唯一反求',
                'SOLVE_BRACKET': '该量没有登记搜索区间', 'SOLVE_PLAN': '计划中找不到该量', 'SOLVE_CONDITION': '要求与计算目标不符'}


class Blocked(ValueError):
    """A plan check stopped the calculation (H2). The steps before it and the reason are kept, no later value."""

    def __init__(self, code, message, steps, details):
        super().__init__(code)
        self.message, self.steps, self.details = message, steps, details


def check_plan(plan, done, steps):
    """Plan checks whose steps have both run. A distance from coordinates must be within the radio horizon."""
    for check in plan.get('checks', []):
        if check['kind'] == 'line_of_sight' and check['distance'] in done and check['horizon'] in done:
            distance, horizon = done[check['distance']]['value'], done[check['horizon']]['value']
            if distance > horizon:
                raise Blocked('BEYOND_LINE_OF_SIGHT',
                              f'两站直线距离 {distance:.2f} km，超过两端天线的无线电视距 {horizon:.2f} km；'
                              '自由空间链路预算在视距外不适用，未计算路径损耗及之后各步。',
                              steps, dict(distance_km=distance, radio_horizon_km=horizon))


def single_fspl(plan):
    # v0.1.0 path: kept byte-identical, including result shape and tool version.
    return [s['tool_id'] for s in plan['steps']] == ['fspl_ghz']


def run_steps(plan, cards, parameters, parameter_names, conditions):
    by_id = {c['id']: c for c in cards}
    done, steps = {}, []
    for step in plan['steps']:
        card = by_id[step['tool_id']]
        require(card['status']=='verified', 'MODEL_NOT_VERIFIED')
        require(set(step['inputs'])==set(card['parameters']), 'PLAN_INPUTS_MISMATCH')
        inputs = {}
        for name, binding in step['inputs'].items():
            if binding['kind']=='parameter':
                require(parameter_names.get(binding['ref'])==name and name in parameters, 'PLAN_BINDING')
                inputs[name] = parameters[name]
            else:
                require(binding['ref'] in done and done[binding['ref']]['name']==name, 'PLAN_BINDING')
                inputs[name] = done[binding['ref']]['value']
        require(all(type(v) in (int, float) for v in inputs.values()), 'PLAN_DOMAIN_UNSUPPORTED')
        require(not scope_issues(card['id'], inputs, {'conditions':conditions}), 'MODEL_NOT_APPLICABLE')
        result = core.evaluate(card, inputs)
        require(result['status']=='ok', 'CALCULATION_DOMAIN_ERROR')
        value = result.get('value')
        require(type(value) in (int,float) and math.isfinite(value), 'NONFINITE_RESULT')
        require(result['unit']==card['output']['unit']==step['expected_unit'], 'RESULT_UNIT_MISMATCH')
        require(result['inputs']==inputs, 'RESULT_INPUT_MISMATCH')
        require(not result_issues(card['id'],value), 'RESULT_NOT_APPLICABLE')
        out = dict(name=card['output']['name'], value=value, unit=result['unit'])
        done[step['step_id']] = out
        steps.append(dict(step_id=step['step_id'], tool_id=card['id'], version=card['version'], inputs=inputs, output=out))
        check_plan(plan, done, steps)
    return steps


def solve_for(plan, cards, parameters, names, report):
    """Invert the confirmed plan for the unknown the user asked about (C11), and compare with the radio's rating."""
    from planning.services.solve import solve  # solve imports run_steps from here
    requirement, unknown = plan['requirement'], plan['solve_if_unmet']
    envelope = dict(steps=plan['steps'], cards=cards, parameters=parameters, parameter_names=names,
                    conditions=report['conditions'])
    try:
        found = solve(envelope, unknown, {k: requirement[k] for k in ('quantity', 'op', 'value')})
    except ValueError as exc:
        return dict(unknown=unknown, error=str(exc))
    rated = next((o for p in report['parameters_proposal'] if p['canonical_name'] == unknown
                  for o in p['origins'] if o['kind'] == 'device'), None)
    if rated:
        found['rated'] = dict(value=rated['value'], unit=rated['unit'], source_ref=rated['source_ref'],
                              exceeded=found['value'] > rated['value'])
    return found


def execute(snapshot, review, cards, proposal, observer=None, attempt=1, root=None):
    require(type(attempt) is int and 1 <= attempt <= 2, 'INVALID_CALCULATION_ATTEMPT')
    snapshot = validate_snapshot(snapshot, review, cards, root)
    require(proposal == propose_calculation(snapshot), 'SNAPSHOT_INPUT_MISMATCH')
    report = snapshot['review']['report']
    plan = report['calculation_plan_proposal']
    if not single_fspl(plan):
        return execute_plan(snapshot, cards, observer, attempt)
    card = next(c for c in cards if c['id']=='fspl_ghz')
    require(card['status']=='verified', 'MODEL_NOT_VERIFIED')
    parameters = {p['canonical_name']:p['value'] for p in report['parameters_proposal'] if p['value'] is not None}
    require(set(card['parameters']) <= set(parameters), 'MISSING_PARAMETERS')
    require(set(card['applicability']['requires']) <= set(report['conditions']), 'MISSING_CONDITIONS')
    domain_mode=any(type(v) is dict for v in parameters.values())
    started = stamp()
    observe(observer,'model','started',caller='compute_agent',model_id=card['id'])
    try:
        if domain_mode:
            parameters={k:parameters[k] for k in card['parameters']}
            outputs=evaluate_domains(card,parameters,report['conditions'])
        else:
            require(not scope_issues(card['id'], parameters, {'conditions':report['conditions']}), 'MODEL_NOT_APPLICABLE')
            result=core.evaluate(card,parameters)
            require(result['status']=='ok', 'CALCULATION_DOMAIN_ERROR')
            value=result.get('value')
            require(type(value) in (int,float) and math.isfinite(value), 'NONFINITE_RESULT')
            require(result['unit']==card['output']['unit'], 'RESULT_UNIT_MISMATCH')
            require(result['inputs']=={k:parameters[k] for k in card['parameters']}, 'RESULT_INPUT_MISMATCH')
            require(not result_issues(card['id'],value), 'RESULT_NOT_APPLICABLE')
            parameters=result['inputs']
            outputs=[dict(name=card['output']['name'],value=value,unit=result['unit'])]
    except Exception:
        observe(observer,'model','failed',caller='compute_agent')
        raise
    observe(observer,'model','completed',caller='compute_agent',model_id=card['id'])
    output = dict(result_id=snapshot['snapshot_id']+':result'+('' if attempt==1 else f':attempt-{attempt}'), task_id=snapshot['task_id'],
                  revision=snapshot['revision'], snapshot_id=snapshot['snapshot_id'],
                  snapshot_hash=snapshot['content_hash'], plan_hash=report['calculation_plan_proposal']['plan_hash'],
                  model_id=card['id'], model_version=card['version'], formula=card['expression'],
                  normalized_inputs=parameters, outputs=outputs,
                  evidence_ids=copy.deepcopy(report['evidence_ids']), runtime_mode='deterministic',
                  tool_version='confirmed-fspl-v1/'+RULE_VERSION, started_at=started, finished_at=stamp())
    output['result_hash'] = digest(output)
    return output


def execute_plan(snapshot, cards, observer, attempt):
    report = snapshot['review']['report']
    plan = report['calculation_plan_proposal']
    by_id = {c['id']: c for c in cards}
    final = by_id[plan['steps'][-1]['tool_id']]
    parameters = {p['canonical_name']:p['value'] for p in report['parameters_proposal'] if p['value'] is not None}
    names = {p['parameter_id']:p['canonical_name'] for p in report['parameters_proposal']}
    require(set(plan['required_parameters']) <= set(parameters), 'MISSING_PARAMETERS')
    required = {c for s in plan['steps'] for c in s['required_conditions']}
    require(required <= set(report['conditions']), 'MISSING_CONDITIONS')
    started = stamp()
    observe(observer,'model','started',caller='compute_agent',model_id=final['id'],steps=len(plan['steps']))
    try:
        steps = run_steps(plan, cards, parameters, names, report['conditions'])
    except Exception:
        observe(observer,'model','failed',caller='compute_agent')
        raise
    observe(observer,'model','completed',caller='compute_agent',model_id=final['id'],steps=len(steps))
    extra = {}
    if plan.get('requirement'):
        # A margin requirement is compared, never deducted; only an unmet one is solved for.
        actual = steps[-1]['output']['value']
        extra['requirement'] = dict(plan['requirement'], actual=actual, met=actual >= plan['requirement']['value'])
        if not extra['requirement']['met'] and plan.get('solve_if_unmet'):
            extra['solve'] = solve_for(plan, cards, parameters, names, report)
    output = dict(result_id=snapshot['snapshot_id']+':result'+('' if attempt==1 else f':attempt-{attempt}'), task_id=snapshot['task_id'],
                  revision=snapshot['revision'], snapshot_id=snapshot['snapshot_id'],
                  snapshot_hash=snapshot['content_hash'], plan_hash=plan['plan_hash'],
                  model_id=final['id'], model_version=final['version'], formula=final['expression'],
                  normalized_inputs={k:parameters[k] for k in plan['required_parameters']},
                  outputs=[copy.deepcopy(steps[-1]['output'])], steps=steps, **extra,
                  evidence_ids=copy.deepcopy(report['evidence_ids']), runtime_mode='deterministic',
                  tool_version='confirmed-plan-v1/'+RULE_VERSION, started_at=started, finished_at=stamp())
    output['result_hash'] = digest(output)
    return output


def validate_plan_result(result, snapshot, expected_inputs):
    report = snapshot['review']['report']
    plan, model = report['calculation_plan_proposal'], snapshot['review']['model']
    versions = {e['catalog_id']:e['card_version'] for e in report['evidence_refs']}
    steps = result.get('steps')
    chain_ok = type(steps) is list and len(steps)==len(plan['steps'])
    magnitude_ok = chain_ok
    done = {}
    if chain_ok:
        for got, step in zip(steps, plan['steps']):
            try:
                ok = (set(got)=={'step_id','tool_id','version','inputs','output'} and got['step_id']==step['step_id']
                      and got['tool_id']==step['tool_id'] and got['version']==versions.get(step['tool_id'])
                      and set(got['inputs'])==set(step['inputs']) and got['output']['unit']==step['expected_unit'])
                for name, binding in step['inputs'].items():
                    want = expected_inputs.get(name) if binding['kind']=='parameter' else done.get(binding['ref'], {}).get('value')
                    ok = ok and want is not None and got['inputs'][name]==want
                value = got['output']['value']
                ok = ok and type(value) in (int,float) and math.isfinite(value)
            except (KeyError, TypeError, AttributeError):
                ok = False
            chain_ok = chain_ok and ok
            magnitude_ok = magnitude_ok and ok and agrees(step['tool_id'], got['inputs'], got['output']['value'])
            done[step['step_id']] = got['output'] if ok else {}
    numeric_ok = chain_ok and result['outputs']==[steps[-1]['output']] and result['outputs'][0]['name']==model['output']['name']
    return dict(
        model_identity=result['model_id']==model['id']==plan['steps'][-1]['tool_id'] and result['model_version']==model['version']
            and result['formula']==model['expression'],
        numeric_domain=numeric_ok, step_chain=chain_ok, independent_magnitude=magnitude_ok,
        plan_checks=chain_ok and all(done[c['distance']]['value'] <= done[c['horizon']]['value'] for c in plan.get('checks', [])),
        requirement_and_solve=numeric_ok and goal_ok(result, snapshot, expected_inputs))


def reference_value(plan, inputs, unknown, x):
    """The plan's final value with the unknown set to x, from the independent reference models only."""
    values, done = dict(inputs, **{unknown: x}), {}
    for step in plan['steps']:
        args = {name: values[name] if b['kind'] == 'parameter' else done[b['ref']] for name, b in step['inputs'].items()}
        done[step['step_id']] = REFERENCE[step['tool_id']][0](args)
    return done[plan['steps'][-1]['step_id']]


def goal_ok(result, snapshot, inputs):
    """The requirement comparison and a solved value, checked again; the solution against the reference models."""
    report = snapshot['review']['report']
    plan = report['calculation_plan_proposal']
    requirement = plan.get('requirement')
    if not requirement:
        return 'requirement' not in result and 'solve' not in result
    actual = result['outputs'][0]['value']
    if result.get('requirement') != dict(requirement, actual=actual, met=actual >= requirement['value']):
        return False
    if result['requirement']['met'] or not plan.get('solve_if_unmet'):
        return 'solve' not in result
    found, unknown, target = result.get('solve'), plan['solve_if_unmet'], requirement['value']
    if type(found) is not dict or found.get('unknown') != unknown:
        return False
    if 'error' in found:
        return set(found) == {'unknown', 'error'} and found['error'] in SOLVE_ERRORS
    try:
        tolerance = sum(REFERENCE[s['tool_id']][1] for s in plan['steps']) + 1e-9
        x = found['value']
        sides_ok = all(abs(reference_value(plan, inputs, unknown, side['unknown_value']) - side['condition_value']) <= tolerance
                       and side['satisfies'] == (side['condition_value'] >= target) for side in (found['left'], found['right']))
        rated = next((o for p in report['parameters_proposal'] if p['canonical_name'] == unknown
                      for o in p['origins'] if o['kind'] == 'device'), None)
        rated_ok = (found.get('rated') == dict(value=rated['value'], unit=rated['unit'], source_ref=rated['source_ref'],
                                                exceeded=x > rated['value'])) if rated else 'rated' not in found
        return (sides_ok and rated_ok and found['left']['satisfies'] != found['right']['satisfies']
                and found['direction'] == ('minimum' if found['right']['satisfies'] else 'maximum')
                and found['condition'] == {k: requirement[k] for k in ('quantity', 'op', 'value')}
                and abs(found['condition_value'] - target) <= 1e-6 * max(1, abs(target))
                and abs(reference_value(plan, inputs, unknown, x) - target) <= tolerance)
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def validate_result(result, snapshot):
    report = snapshot['review']['report']
    model = snapshot['review']['model']
    expected_inputs = {p['canonical_name']:p['value'] for p in report['parameters_proposal']
                       if p['canonical_name'] in report['calculation_plan_proposal']['required_parameters']}
    if not single_fspl(report['calculation_plan_proposal']):
        checks = dict(
            result_integrity=result['result_hash']==digest({k:v for k,v in result.items() if k!='result_hash'}),
            snapshot_identity=result['snapshot_hash']==snapshot['content_hash'] and result['snapshot_id']==snapshot['snapshot_id']
                and result['task_id']==snapshot['task_id'] and result['revision']==snapshot['revision'],
            input_consistency=result['normalized_inputs']==expected_inputs,
            plan_identity=result['plan_hash']==report['calculation_plan_proposal']['plan_hash'],
            evidence_consistency=result['evidence_ids']==report['evidence_ids'],
            **validate_plan_result(result, snapshot, expected_inputs))
        return [dict(validation_id=result['result_id']+':'+key, validator_id=key, severity='hard',
                     passed=bool(ok), target_hash=result['result_hash']) for key,ok in checks.items()]
    # Independent magnitude check against the dimensionless 4*pi*d*f/c ratio.
    # The registered P.525 card uses a rounded constant, ~0.048 dB below this
    # reference. This is a validator only; published values always use the card.
    domain_mode=any(type(v) is dict for v in expected_inputs.values())
    if domain_mode:
        numeric_ok,magnitude_ok=validate_domains(result['outputs'],expected_inputs,model)
    else:
        reference=20*(math.log10(expected_inputs['frequency_ghz'])+math.log10(expected_inputs['distance_km'])+12+math.log10(4*math.pi/299792458))
        numeric_ok=(len(result['outputs'])==1 and result['outputs'][0]['unit']=='dB'
            and result['outputs'][0]['name']==model['output']['name']
            and type(result['outputs'][0]['value']) in (int,float)
            and math.isfinite(result['outputs'][0]['value']) and result['outputs'][0]['value']>=0)
        magnitude_ok=numeric_ok and abs(result['outputs'][0]['value']-reference)<=0.05
    checks = dict(
        result_integrity=result['result_hash']==digest({k:v for k,v in result.items() if k!='result_hash'}),
        snapshot_identity=result['snapshot_hash']==snapshot['content_hash'] and result['snapshot_id']==snapshot['snapshot_id']
            and result['task_id']==snapshot['task_id'] and result['revision']==snapshot['revision'],
        input_consistency=result['normalized_inputs']==expected_inputs,
        plan_identity=result['plan_hash']==report['calculation_plan_proposal']['plan_hash'],
        evidence_consistency=result['evidence_ids']==report['evidence_ids'],
        model_identity=result['model_id']==model['id']=='fspl_ghz' and result['model_version']==model['version']
            and result['formula']==model['expression'],
        numeric_domain=numeric_ok, fspl_magnitude=magnitude_ok)
    return [dict(validation_id=result['result_id']+':'+key, validator_id=key, severity='hard',
                 passed=bool(ok), target_hash=result['result_hash']) for key,ok in checks.items()]


def publish(result, snapshot, validations):
    require(validations==validate_result(result,snapshot) and all(v['passed'] for v in validations), 'VALIDATION_FAILED')
    report = snapshot['review']['report']
    if not single_fspl(report['calculation_plan_proposal']):
        return publish_plan(result, snapshot, validations)
    return dict(report_id=result['result_id']+':report', result_id=result['result_id'],result_hash=result['result_hash'],
                snapshot_id=snapshot['snapshot_id'], snapshot_hash=snapshot['content_hash'],
                task_id=snapshot['task_id'],revision=snapshot['revision'],
                normalized_inputs=copy.deepcopy(result['normalized_inputs']),outputs=copy.deepcopy(result['outputs']),
                model_id=result['model_id'],model_version=result['model_version'],formula=result['formula'],
                parameters=copy.deepcopy(report['parameters_proposal']),conditions=copy.deepcopy(report['conditions']),
                validation_ids=[v['validation_id'] for v in validations],
                conclusion=conclusion(result['outputs']),
                limitations=list(dict.fromkeys(report['assumptions']+[FARFIELD_NOTE,
                    '结果仅为自由空间基准，未估计真实海面反射、散射或遮挡，也不代表链路通信可行。',
                    '区间按输入上下界的组合计算，不包含概率或置信度；离散候选分别报告。'])),
                evidence_refs=copy.deepcopy(report['evidence_refs']), component_modes=copy.deepcopy(report['component_modes']),
                runtime_health=report['runtime_health'], generated_at=stamp())


def plan_conclusion(result):
    tools = [s['tool_id'] for s in result['steps']]
    out = result['outputs'][0]
    text = '按已确认自由空间条件，' if 'fspl_ghz' in tools else '按已确认输入，'
    if result['model_id']=='link_margin':
        meaning = describe_result('link_margin', out['value'])['message'].split('，')[0]
        return text + f"链路余量 {out['value']:.2f} dB（{meaning}）" + goal_text(result) + '。'
    label = {'received_power':'接收信号电平','fspl_ghz':'路径损耗'}.get(result['model_id'], out['name'])
    return text + f"{label} {out['value']:.2f} {out['unit']}。"


def goal_text(result):
    """The comparison with the margin requirement, and the solved value with its rating note (decision 6)."""
    req = result.get('requirement')
    if not req:
        return ''
    if req['met']:
        return f"，满足不低于 {req['value']:g} dB 的要求"
    text = f"，低于要求的 {req['value']:g} dB"
    found = result.get('solve')
    if not found:
        return text
    if 'error' in found:
        return text + f"；反求没有结果：{SOLVE_ERRORS.get(found['error'], found['error'])}"
    word = '至少' if found['direction'] == 'minimum' else '至多'
    text += f"；发射功率{word}需 {found['value']:.2f} {found['unit']} 才能满足"
    rated = found.get('rated')
    if rated and rated['exceeded']:
        text += f"，超过所选电台的额定发射功率 {rated['value']:g} {rated['unit']}"
    return text


def publish_plan(result, snapshot, validations):
    report = snapshot['review']['report']
    tools = [s['tool_id'] for s in result['steps']]
    limits = list(report['assumptions'])
    if 'fspl_ghz' in tools:
        limits += [FARFIELD_NOTE, '路径损耗按自由空间基准计算，未估计真实海面反射、散射或遮挡。']
    if 'link_margin' in tools:
        limits.append(MARGIN_NOTE)
    return dict(report_id=result['result_id']+':report', result_id=result['result_id'],result_hash=result['result_hash'],
                snapshot_id=snapshot['snapshot_id'], snapshot_hash=snapshot['content_hash'],
                task_id=snapshot['task_id'],revision=snapshot['revision'],
                normalized_inputs=copy.deepcopy(result['normalized_inputs']),outputs=copy.deepcopy(result['outputs']),
                steps=copy.deepcopy(result['steps']),
                model_id=result['model_id'],model_version=result['model_version'],formula=result['formula'],
                parameters=copy.deepcopy(report['parameters_proposal']),conditions=copy.deepcopy(report['conditions']),
                validation_ids=[v['validation_id'] for v in validations],
                conclusion=plan_conclusion(result),
                limitations=list(dict.fromkeys(limits)),
                evidence_refs=copy.deepcopy(report['evidence_refs']), component_modes=copy.deepcopy(report['component_modes']),
                runtime_health=report['runtime_health'], generated_at=stamp(),
                **{k: copy.deepcopy(result[k]) for k in ('requirement', 'solve') if k in result})
