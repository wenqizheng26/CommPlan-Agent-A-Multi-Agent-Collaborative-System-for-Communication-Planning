"""Deterministic trust-boundary checks against source input and loaded catalog."""
import copy
from formula_rag.parsing import extract_request
from formula_rag.interpretation import merge_interpretation
from formula_rag.applicability import scope_issues
from planning.services.input_domains import numbers, scenarios
from planning.requirements_contract import require, validate_report
from planning.services.requirement_parameters import collect_parameters
from planning.services.requirement_evidence import snapshot_for, evidence_for, plan_for
from planning.services.requirement_policy import validate_target_semantics, intent_conflict, outside_scope


def check_report(report, request, cards):
    r = validate_report(report, request)
    require(r['component_modes']['retrieval']=='lexical_fallback', 'UNVERIFIED_RETRIEVAL_MODE')
    calls = [d for d in r['diagnostics'] if d['code']=='MODEL_CALL']
    if r['component_modes']['interpretation'] in {'llm','stub'}:
        require(len(calls)==1, 'MODEL_CALL_EVIDENCE_REQUIRED')
    if r['component_modes']['interpretation']=='llm':
        details=calls[0]['details']
        require(type(details.get('model')) is str and bool(details['model']) and
                type(details.get('usage')) is dict and bool(details['usage']), 'MODEL_IDENTITY_REQUIRED')
    parsed = extract_request(request['raw_text'])
    needed = ['frequency_ghz', 'distance_km'] if any(p['canonical_name'] in {'frequency_ghz','distance_km'} and p['status']=='missing' for p in r['parameters_proposal']) or r['targets'] == ['fspl_ghz'] else []
    parameters, conflicts, issues = collect_parameters(request, parsed, needed)
    require(r['parameters_proposal'] == parameters, 'PARAMETER_SOURCE_MISMATCH')
    require(r['conflicts'] == conflicts, 'CONFLICT_MISMATCH')
    require(r['missing_parameters'] == [p['canonical_name'] for p in parameters if p['status']=='missing'], 'MISSING_MISMATCH')
    snapshot = snapshot_for(cards)
    require(r['knowledge_snapshot'] == snapshot, 'SNAPSHOT_MISMATCH')
    by_id = {c['id']:c for c in cards}
    candidates = r['candidate_models']
    require(all(c['model_id']=='fspl_ghz' and c['model_id'] in by_id for c in candidates), 'MODEL_NOT_ALLOWED')
    ranks = {e['catalog_id']:e['relevance_rank'] for e in r['evidence_refs']}
    selected_cards = [by_id[c['model_id']] for c in candidates]
    require(all(c['id'] in ranks for c in selected_cards), 'MODEL_WITHOUT_EVIDENCE')
    refs = evidence_for(selected_cards, snapshot, ranks)
    require(r['evidence_refs'] == refs, 'EVIDENCE_MISMATCH')
    for c in candidates:
        card = by_id[c['model_id']]
        require(c == dict(model_id=card['id'], version=card['version'], status=card['status'], evidence_ids=r['evidence_ids']), 'MODEL_VERSION_MISMATCH')
    if r['calculation_plan_proposal'] is not None:
        require(r['targets']==['fspl_ghz'] and 'fspl_ghz' in by_id, 'PLAN_TARGET')
        expected = plan_for(request, by_id['fspl_ghz'], parameters, r['evidence_ids'])
        require(r['calculation_plan_proposal'] == expected, 'PLAN_SOURCE_MISMATCH')
        require(r['assumptions']==expected['assumptions'], 'ASSUMPTIONS_MISMATCH')
    if r['execution_status'] != 'AWAITING_CONFIRMATION':
        return r
    require(r['runtime_health'] != 'unavailable', 'UNAVAILABLE_CONFIRMATION')
    require(not intent_conflict(request, parsed), 'INTENT_CONFLICT')
    # Re-ground model evidence; neither report status nor its condition list is trusted.
    interpreted = copy.deepcopy(parsed)
    for d in r['diagnostics']:
        if d['code'] != 'MODEL_CALL':
            continue
        accepted = d['details'].get('accepted', [])
        model = {'targets':[{k:a[k] for k in ('id','evidence')} for a in accepted if a.get('kind')=='target'],
                 'conditions':[{k:a[k] for k in ('id','evidence')} for a in accepted if a.get('kind')=='condition']}
        validate_target_semantics(model)
        info = merge_interpretation(interpreted, model, ['fspl_ghz'], request['target'], request['condition'])
        require(not info['rejected'], 'MODEL_GROUNDING_MISMATCH')
    if request['target']:
        require(parsed['target_origin'] != 'explicit_text' or parsed['targets']==[request['target']], 'INTENT_CONFLICT')
        target = [request['target']]
    else:
        target = interpreted['targets']
        require(parsed['target_origin']=='explicit_text' or interpreted['targets'] != parsed['targets'] or any(d['code']=='MODEL_CALL' and any(a.get('kind')=='target' for a in d['details'].get('accepted',[])) for d in r['diagnostics']), 'TARGET_NOT_GROUNDED')
    require(target == ['fspl_ghz'] and not parsed['unsupported_targets'], 'UNSUPPORTED_SCOPE')
    conditions = set(interpreted['conditions'])
    if request['condition']:
        conditions.add(request['condition'])
        if request['condition']=='free_space_reference':
            conditions.add('free_space')
    require(r['conditions']==sorted(conditions) and 'free_space' in conditions, 'CONDITION_MISMATCH')
    require(not outside_scope(request['raw_text'],parsed,target,conditions), 'UNSUPPORTED_SCOPE')
    require('non_free_space' not in conditions or 'free_space_reference' in conditions, 'MODEL_NOT_APPLICABLE')
    require(not any(d['code'] in {'INPUT_PARSE_ISSUE','SOURCE_AMBIGUOUS','PARAMETER_APPROXIMATE'} for d in issues), 'INPUT_NOT_RESOLVED')
    values = {p['canonical_name']:p['value'] for p in parameters if p['value'] is not None}
    require(all(k in values and min(numbers(values[k]))>0 for k in ('frequency_ghz','distance_km')), 'INPUT_DOMAIN_INVALID')
    require(not any(scope_issues('fspl_ghz', case, parsed) for case in scenarios(values)), 'MODEL_NOT_APPLICABLE')
    require(by_id['fspl_ghz']['status']=='verified', 'MODEL_NOT_VERIFIED')
    return r
