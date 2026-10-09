"""Structured confirmed inputs enter existing numeric and applicability gates."""
import copy
import math
from pathlib import Path
from formula_rag import core
from formula_rag.applicability import scope_issues, result_issues, describe_result, FARFIELD_NOTE, RULE_VERSION
from planning.requirements_contract import digest, require
from planning.services.confirmation import validate_snapshot
from planning.agents.calculation import propose_calculation
from planning.workflow.requirements_graph import stamp
from planning.workflow.activity import observe
from planning.services.domain_calculation import evaluate_domains, validate_domains, conclusion
from planning.services.reference_models import agrees, REFERENCE
from planning.services.plans import bound

ROOT = Path(__file__).resolve().parents[2]

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


def run_steps(plan, cards, parameters, parameter_names, conditions, raw_text=''):
    by_id = {c['id']: c for c in cards}
    done, steps = {}, []
    for step in plan['steps']:
        card = by_id[step['tool_id']]
        require(card['status']=='verified', 'MODEL_NOT_VERIFIED')
        require(set(step['inputs'])==set(card['parameters']), 'PLAN_INPUTS_MISMATCH')
        inputs = {}
        for name, binding in step['inputs'].items():
            if binding['kind']=='parameter':
                source = parameter_names.get(binding['ref'])
                require(source in parameters, 'PLAN_BINDING')
                inputs[name] = bound(name, source, parameters)
            else:
                require(binding['ref'] in done and done[binding['ref']]['name']==name, 'PLAN_BINDING')
                inputs[name] = done[binding['ref']]['value']
        require(all(type(v) in (int, float) for v in inputs.values()), 'PLAN_DOMAIN_UNSUPPORTED')
        from formula_rag.applicability import noise_confirmation
        require(not scope_issues(card['id'], inputs, {'conditions':conditions,'noise_reference':noise_confirmation(raw_text)}), 'MODEL_NOT_APPLICABLE')
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
        return execute_plan(snapshot, cards, observer, attempt, root)
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
    if not domain_mode:
        observe(observer,'tool','completed',caller='compute_agent',step_id='fspl-step',tool_id=card['id'],
                inputs=parameters,output=outputs[0])
    output = dict(result_id=snapshot['snapshot_id']+':result'+('' if attempt==1 else f':attempt-{attempt}'), task_id=snapshot['task_id'],
                  revision=snapshot['revision'], snapshot_id=snapshot['snapshot_id'],
                  snapshot_hash=snapshot['content_hash'], plan_hash=report['calculation_plan_proposal']['plan_hash'],
                  model_id=card['id'], model_version=card['version'], formula=card['expression'],
                  normalized_inputs=parameters, outputs=outputs,
                  evidence_ids=copy.deepcopy(report['evidence_ids']), runtime_mode='deterministic',
                  tool_version='confirmed-fspl-v1/'+RULE_VERSION, started_at=started, finished_at=stamp())
    output['result_hash'] = digest(output)
    return output


def link_label(parameter, store):
    """What a call is named after: the modulation its sensitivity came from, or the stated sensitivity."""
    if [o['kind'] for o in parameter['origins']] == ['modulation']:
        ident = parameter['origins'][0]['source_ref'].split('#')[0]
        return next(r['names'][0] for r in store.modulation_records() if r['id'] == ident), True
    return f"接收灵敏度 {parameter['value']:g} dBm", False


def link_calls(plan, report, steps, cards, root):
    """Run the confirmed chain as the registered link tool, once per modulation (TEACHER_CASES).

    The tool calls the same three cards; its first call must give exactly the chain's step values,
    and every call the sensitivity the user confirmed. Its arguments are the chain's own step inputs,
    so a distance from site coordinates is passed on as computed.
    """
    from formula_rag.registry import call_tool
    from planning.knowledge.facts import FactService
    root = root or ROOT
    store = FactService(root)
    hashes = {c['id']: digest(c) for c in cards}
    base = link_arguments(steps)
    if plan.get('requirement'):
        base['required_margin_db'] = plan['requirement']['value']
    threshold = next(p for p in report['parameters_proposal'] if p['canonical_name'] == 'rx_threshold_dbm')
    label, from_table = link_label(threshold, store)
    runs = [(label, dict(base, modulation=label) if from_table else dict(base, rx_sensitivity_dbm=threshold['value']),
             threshold['value'])]
    runs += [(v['label'], dict(base, modulation=v['label']), v['value']) for v in plan.get('variants', [])]
    calls = []
    for label, arguments, sensitivity in runs:
        response = call_tool(root, plan['tool'], arguments)
        require(response['status'] == 'ok', 'LINK_TOOL_FAILED: ' + '; '.join(response['errors']))
        require(all(s['content_hash'] == hashes.get(s['card']) for s in response['steps']), 'LINK_TOOL_CARD_CHANGED')
        require(response['result']['rx_sensitivity_dbm'] == sensitivity, 'LINK_TOOL_SENSITIVITY_CHANGED')
        calls.append(dict(tool=plan['tool'], label=label, arguments=response['arguments'], result=response['result'],
                          status=response['status'],
                          steps=[{k: s[k] for k in ('card', 'inputs', 'value', 'unit')} for s in response['steps']]))
    first, chain = calls[0]['steps'], steps[-3:]
    require([s['card'] for s in first] == [s['tool_id'] for s in chain] and
            all(a['value'] == b['output']['value'] and a['inputs'] == b['inputs'] for a, b in zip(first, chain)),
            'LINK_TOOL_MISMATCH')
    return calls


def link_arguments(steps):
    """The link tool's common arguments, read from the path-loss and received-power steps of the chain."""
    loss, power = steps[-3]['inputs'], steps[-2]['inputs']
    return dict(distance_km=loss['distance_km'], frequency_mhz=loss['frequency_mhz'],
                **{k: power[k] for k in ('tx_power_dbm', 'tx_gain_dbi', 'rx_gain_dbi')})


def compare(calls):
    """The comparison table: one row per modulation, the margin spread, and the one with the largest margin."""
    rows = [dict(label=c['label'], **{k: c['result'][k] for k in ('rx_sensitivity_dbm', 'path_loss_db', 'rx_power_dbm',
                                                                     'link_margin_db', 'meets')}) for c in calls]
    margins = [r['link_margin_db'] for r in rows]
    best = rows[margins.index(max(margins))]
    return dict(parameter='rx_threshold_dbm', rows=rows, margin_diff_db=max(margins) - min(margins), recommend=best['label'])


def execute_plan(snapshot, cards, observer, attempt, root=None):
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
        steps = run_steps(plan, cards, parameters, names, report['conditions'],snapshot['review']['request']['raw_text'])
    except Exception:
        observe(observer,'model','failed',caller='compute_agent')
        raise
    observe(observer,'model','completed',caller='compute_agent',model_id=final['id'],steps=len(steps))
    for step in steps:  # each tool call, for the page to list as it happens
        observe(observer,'tool','completed',caller='compute_agent',step_id=step['step_id'],tool_id=step['tool_id'],
                inputs=step['inputs'],output=step['output'])
    extra = {}
    if plan.get('tool'):
        calls = link_calls(plan, report, steps, cards, root)
        for call in calls:
            observe(observer,'tool','completed',caller='compute_agent',tool_id=call['tool'],label=call['label'],
                    arguments=call['arguments'],result=call['result'],steps=call['steps'])
        extra['tool_calls'] = [{k: call[k] for k in ('tool', 'label', 'arguments', 'result', 'status')} for call in calls]
        if plan.get('variants'):
            extra['comparison'] = compare(calls)
    if plan.get('requirement'):
        # A margin requirement is compared, never deducted; only an unmet one is solved for.
        actual = steps[-1]['output']['value']
        extra['requirement'] = dict(plan['requirement'], actual=actual, met=actual >= plan['requirement']['value'])
        if not extra['requirement']['met'] and plan.get('solve_if_unmet'):
            extra['solve'] = solve_for(plan, cards, parameters, names, report)
    output = dict(result_id=snapshot['snapshot_id']+':result'+('' if attempt==1 else f':attempt-{attempt}'), task_id=snapshot['task_id'],
                  revision=snapshot['revision'], snapshot_id=snapshot['snapshot_id'],
                  snapshot_hash=snapshot['content_hash'], plan_hash=plan['plan_hash'],
                  model_id=final['id'], model_version=final['version'], formula=final.get('expression', final.get('algorithm')),
                  normalized_inputs={k:parameters[k] for k in plan['required_parameters']},
                  outputs=[copy.deepcopy(steps[-1]['output'])], steps=steps, **extra,
                  evidence_ids=copy.deepcopy(report['evidence_ids']), runtime_mode='deterministic',
                  tool_version='confirmed-plan-v1/'+RULE_VERSION, started_at=started, finished_at=stamp())
    if 'generic_card' in report:
        from planning.services.generic_cards import LIMITATION
        output.update(calculation_mode='generic_card',card=dict(id=final['id'],version=final['version'],content_hash=digest(final)),
            verification=dict(method='registered_examples_and_finite_result',independent_model=False),
            limitations=[LIMITATION])
    output['result_hash'] = digest(output)
    return output


def validate_plan_result(result, snapshot, expected_inputs):
    report = snapshot['review']['report']
    plan, model = report['calculation_plan_proposal'], snapshot['review']['model']
    versions = {e['catalog_id']:e['card_version'] for e in report['evidence_refs']}
    names = {p['parameter_id']:p['canonical_name'] for p in report['parameters_proposal']}
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
                    source = names.get(binding['ref'])
                    want = ((bound(name, source, expected_inputs) if source in expected_inputs else None)
                            if binding['kind']=='parameter' else done.get(binding['ref'], {}).get('value'))
                    ok = ok and want is not None and got['inputs'][name]==want
                value = got['output']['value']
                ok = ok and type(value) in (int,float) and math.isfinite(value)
            except (KeyError, TypeError, AttributeError, ValueError):
                ok = False
            chain_ok = chain_ok and ok
            if 'generic_card' in report:
                card=model
                examples_ok=bool(card.get('examples'))
                for example in card.get('examples',[]):
                    replay=core.evaluate(card,example['inputs'])
                    examples_ok=examples_ok and replay.get('status')=='ok' and abs(replay['value']-example['expected'])<=example.get('tolerance',1e-6)
                replay=core.evaluate(card,got['inputs']) if ok else {}
                magnitude_ok=magnitude_ok and ok and examples_ok and replay.get('status')=='ok' and replay.get('value')==value
            else:
                magnitude_ok = magnitude_ok and ok and agrees(step['tool_id'], got['inputs'], got['output']['value'])
            done[step['step_id']] = got['output'] if ok else {}
    numeric_ok = chain_ok and result['outputs']==[steps[-1]['output']] and result['outputs'][0]['name']==model['output']['name']
    checks = dict(
        model_identity=result['model_id']==model['id']==plan['steps'][-1]['tool_id'] and result['model_version']==model['version']
            and result['formula']==model.get('expression', model.get('algorithm')),
        numeric_domain=numeric_ok, step_chain=chain_ok, independent_magnitude=magnitude_ok,
        plan_checks=chain_ok and all(done[c['distance']]['value'] <= done[c['horizon']]['value'] for c in plan.get('checks', [])),
        requirement_and_solve=numeric_ok and goal_ok(result, snapshot, expected_inputs),
        link_tool=numeric_ok and tools_ok(result, plan, expected_inputs))
    if 'generic_card' in report:
        checks['registered_examples_and_finite_result']=checks.pop('independent_magnitude')
        checks['generic_card_identity']=(result.get('calculation_mode')=='generic_card' and
            result.get('card')==dict(id=model['id'],version=model['version'],content_hash=digest(model)) and
            result.get('verification')==dict(method='registered_examples_and_finite_result',independent_model=False))
    return checks


def tools_ok(result, plan, inputs):
    """The link tool's calls and the comparison, checked again from the chain and the confirmed inputs."""
    if not plan.get('tool'):
        return 'tool_calls' not in result and 'comparison' not in result
    try:
        calls, variants, steps = result['tool_calls'], plan.get('variants', []), result['steps']
        if type(calls) is not list or len(calls) != 1 + len(variants):
            return False
        loss, power, margin = (s['output']['value'] for s in steps[-3:])
        required = plan['requirement']['value'] if plan.get('requirement') else 0
        wanted = [inputs['rx_threshold_dbm']] + [v['value'] for v in variants]
        for call, sensitivity, label in zip(calls, wanted, [None] + [v['label'] for v in variants]):
            out = call['result']
            args = {k: call['arguments'][k] for k in ('distance_km', 'frequency_mhz', 'tx_power_dbm', 'tx_gain_dbi', 'rx_gain_dbi')}
            if (call['tool'] != plan['tool'] or call['status'] != 'ok' or (label and call['label'] != label)
                    or args != link_arguments(steps)
                    or out['path_loss_db'] != loss or out['rx_power_dbm'] != power or out['rx_sensitivity_dbm'] != sensitivity
                    or abs(out['link_margin_db'] - (power - sensitivity)) > 1e-9
                    or out['required_margin_db'] != required or out['meets'] != (out['link_margin_db'] >= required)):
                return False
        if calls[0]['result']['link_margin_db'] != margin:
            return False
        if variants:
            return result.get('comparison') == compare(calls)
        return 'comparison' not in result
    except (KeyError, TypeError, ValueError, StopIteration):
        return False


def reference_value(plan, inputs, unknown, x):
    """The plan's final value with the unknown set to x, from the independent reference models only."""
    values, done = dict(inputs, **{unknown: x}), {}
    for step in plan['steps']:
        # A parameter id ends with its canonical name (requirement_parameters.collect_parameters).
        args = {name: bound(name, b['ref'].rsplit(':', 1)[1], values) if b['kind'] == 'parameter' else done[b['ref']]
                for name, b in step['inputs'].items()}
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
        # The displayed curve must be the plan's own values too.
        sides_ok = sides_ok and len(found['samples']) == 17 and all(
            abs(reference_value(plan, inputs, unknown, point['unknown_value']) - point['condition_value']) <= tolerance
            for point in found['samples'])
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
            and result['formula']==model.get('expression', model.get('algorithm')),
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
    text = '按已确认自由空间条件，' if {'fspl_ghz', 'fspl_mhz'} & set(tools) else '按已确认输入，'
    if result.get('comparison'):
        c = result['comparison']
        rows = '，'.join(f"{r['label']} 链路余量 {r['link_margin_db']:.2f} dB" for r in c['rows'])
        return text + rows + f"，相差 {c['margin_diff_db']:.2f} dB；{c['recommend']} 余量最大" + goal_text(result) + '。'
    if result['model_id']=='link_margin':
        meaning = describe_result('link_margin', out['value'])['message'].split('，')[0]
        return text + f"链路余量 {out['value']:.2f} dB（{meaning}）" + goal_text(result) + '。'
    label = {'received_power':'接收信号电平','fspl_ghz':'路径损耗','fresnel_radius':'第一菲涅耳区半径',
             'knife_edge_nu':'绕射参数','knife_edge_loss':'单刃形绕射损耗',
             'sea_reflection_two_ray':'海面反射附加损耗（相对自由空间）'}.get(result['model_id'], out['name'])
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
    if {'fspl_ghz', 'fspl_mhz'} & set(tools):
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
                **{k: copy.deepcopy(result[k]) for k in ('requirement', 'solve', 'tool_calls', 'comparison', 'calculation_mode', 'card', 'verification') if k in result})
