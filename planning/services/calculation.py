"""Structured confirmed inputs enter existing numeric and applicability gates."""
import copy
import math
from formula_rag import core
from formula_rag.applicability import scope_issues, result_issues, FARFIELD_NOTE, RULE_VERSION
from planning.requirements_contract import digest, require
from planning.services.confirmation import validate_snapshot
from planning.agents.calculation import propose_calculation
from planning.workflow.requirements_graph import stamp
from planning.workflow.activity import observe


def execute(snapshot, review, cards, proposal, observer=None, attempt=1):
    require(type(attempt) is int and 1 <= attempt <= 2, 'INVALID_CALCULATION_ATTEMPT')
    snapshot = validate_snapshot(snapshot, review, cards)
    require(proposal == propose_calculation(snapshot), 'SNAPSHOT_INPUT_MISMATCH')
    report = snapshot['review']['report']
    card = next(c for c in cards if c['id']=='fspl_ghz')
    require(card['status']=='verified', 'MODEL_NOT_VERIFIED')
    parameters = {p['canonical_name']:p['value'] for p in report['parameters_proposal'] if p['value'] is not None}
    require(set(card['parameters']) <= set(parameters), 'MISSING_PARAMETERS')
    require(set(card['applicability']['requires']) <= set(report['conditions']), 'MISSING_CONDITIONS')
    require(not scope_issues(card['id'], parameters, {'conditions':report['conditions']}), 'MODEL_NOT_APPLICABLE')
    started = stamp()
    observe(observer,'model','started',caller='compute_agent',model_id=card['id'])
    try:
        result = core.evaluate(card, parameters)
    except Exception:
        observe(observer,'model','failed',caller='compute_agent')
        raise
    observe(observer,'model','completed',caller='compute_agent',model_id=card['id'])
    require(result['status']=='ok', 'CALCULATION_DOMAIN_ERROR')
    value = result.get('value')
    require(type(value) in (float,int) and math.isfinite(value), 'NONFINITE_RESULT')
    require(result['unit']==card['output']['unit'], 'RESULT_UNIT_MISMATCH')
    require(result['inputs']=={k:parameters[k] for k in card['parameters']}, 'RESULT_INPUT_MISMATCH')
    require(not result_issues(card['id'], value), 'RESULT_NOT_APPLICABLE')
    output = dict(result_id=snapshot['snapshot_id']+':result'+('' if attempt==1 else f':attempt-{attempt}'), task_id=snapshot['task_id'],
                  revision=snapshot['revision'], snapshot_id=snapshot['snapshot_id'],
                  snapshot_hash=snapshot['content_hash'], plan_hash=report['calculation_plan_proposal']['plan_hash'],
                  model_id=card['id'], model_version=card['version'], formula=card['expression'],
                  normalized_inputs=result['inputs'], outputs=[dict(name=card['output']['name'],value=value,unit=result['unit'])],
                  evidence_ids=copy.deepcopy(report['evidence_ids']), runtime_mode='deterministic',
                  tool_version='confirmed-fspl-v1/'+RULE_VERSION, started_at=started, finished_at=stamp())
    output['result_hash'] = digest(output)
    return output


def validate_result(result, snapshot):
    report = snapshot['review']['report']
    model = snapshot['review']['model']
    expected_inputs = {p['canonical_name']:p['value'] for p in report['parameters_proposal']
                       if p['canonical_name'] in report['calculation_plan_proposal']['required_parameters']}
    # Independent magnitude check against the dimensionless 4*pi*d*f/c ratio.
    # The registered P.525 card uses a rounded constant, ~0.048 dB below this
    # reference. This is a validator only; published values always use the card.
    reference = 20*(math.log10(expected_inputs['frequency_ghz'])+math.log10(expected_inputs['distance_km'])
                    +12+math.log10(4*math.pi/299792458))
    checks = dict(
        result_integrity=result['result_hash']==digest({k:v for k,v in result.items() if k!='result_hash'}),
        snapshot_identity=result['snapshot_hash']==snapshot['content_hash'] and result['snapshot_id']==snapshot['snapshot_id']
            and result['task_id']==snapshot['task_id'] and result['revision']==snapshot['revision'],
        input_consistency=result['normalized_inputs']==expected_inputs,
        plan_identity=result['plan_hash']==report['calculation_plan_proposal']['plan_hash'],
        evidence_consistency=result['evidence_ids']==report['evidence_ids'],
        model_identity=result['model_id']==model['id']=='fspl_ghz' and result['model_version']==model['version']
            and result['formula']==model['expression'],
        numeric_domain=len(result['outputs'])==1 and result['outputs'][0]['unit']=='dB'
            and result['outputs'][0]['name']==model['output']['name']
            and type(result['outputs'][0]['value']) in (int,float)
            and math.isfinite(result['outputs'][0]['value']) and result['outputs'][0]['value']>=0,
        fspl_magnitude=len(result['outputs'])==1 and abs(result['outputs'][0]['value']-reference)<=0.05)
    return [dict(validation_id=result['result_id']+':'+key, validator_id=key, severity='hard',
                 passed=bool(ok), target_hash=result['result_hash']) for key,ok in checks.items()]


def publish(result, snapshot, validations):
    require(validations==validate_result(result,snapshot) and all(v['passed'] for v in validations), 'VALIDATION_FAILED')
    report = snapshot['review']['report']
    return dict(report_id=result['result_id']+':report', result_id=result['result_id'],result_hash=result['result_hash'],
                snapshot_id=snapshot['snapshot_id'], snapshot_hash=snapshot['content_hash'],
                task_id=snapshot['task_id'],revision=snapshot['revision'],
                normalized_inputs=copy.deepcopy(result['normalized_inputs']),outputs=copy.deepcopy(result['outputs']),
                model_id=result['model_id'],model_version=result['model_version'],formula=result['formula'],
                parameters=copy.deepcopy(report['parameters_proposal']),conditions=copy.deepcopy(report['conditions']),
                validation_ids=[v['validation_id'] for v in validations],
                conclusion=f"按已确认条件，自由空间单程路径损耗为 {result['outputs'][0]['value']:.6f} dB。",
                limitations=list(dict.fromkeys(report['assumptions']+[FARFIELD_NOTE,
                    '结果仅为自由空间基准，未估计真实海面反射、散射或遮挡，也不代表链路通信可行。'])),
                evidence_refs=copy.deepcopy(report['evidence_refs']), component_modes=copy.deepcopy(report['component_modes']),
                runtime_health=report['runtime_health'], generated_at=stamp())
