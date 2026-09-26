"""Deterministic trust-boundary checks against source input and loaded catalog."""
import copy
import re
from formula_rag.parsing import extract_request, FIELDS
from planning.services.fact_fields import FACT_FIELDS
from planning.services.requirement_facts import sources_for, band_issues, plan_goal
from formula_rag.interpretation import merge_interpretation
from formula_rag.applicability import scope_issues
from planning.services.input_domains import numbers, scenarios
from planning.requirements_contract import require, validate_report
from formula_rag.parsing import convert
from planning.services.requirement_parameters import collect_parameters
from planning.services.requirement_quantities import find_quantities, summary, SOLVE_UNKNOWNS
from planning.services.requirement_evidence import snapshot_for, evidence_for

LABEL_KINDS = {'quantity', 'requirement', 'solve', 'site', 'device'}


def check_labels(text, labels):
    """Every recorded model label must still sit on the text; none can carry its own number."""
    quantities = {tuple(q['span']): q for q in find_quantities(text)}
    for a in labels:
        if a['kind'] in {'quantity', 'requirement'}:
            q = quantities.get(tuple(a.get('span') or ()))
            require(q is not None and a['value'] == q['value'], 'LABEL_NOT_GROUNDED')
            if a['kind'] == 'requirement':
                require(a['unit'] == 'dB' and q['unit'].lower() == 'db' and q['comparison'] != '<=', 'LABEL_NOT_GROUNDED')
            else:
                require(a['unit'] == q['unit'] and a['field'] in FIELDS and not q['comparison'], 'LABEL_NOT_GROUNDED')
                convert(a['field'], a['value'], a['unit'])
        else:
            a0, b0 = a['span']
            require(0 <= a0 < b0 <= len(text), 'LABEL_NOT_GROUNDED')
            if a['kind'] == 'solve':
                require(a['unknown'] in SOLVE_UNKNOWNS and re.search(r'功率|发射电平', text[a0:b0]), 'LABEL_NOT_GROUNDED')
            else:
                require(text[a0:b0] == a['mention'], 'LABEL_NOT_GROUNDED')
from planning.services.plans import SUPPORTED, TARGETS, chain, final_target, plan_for, requires_free_space, bound_issues
from planning.services.requirement_policy import validate_target_semantics, intent_conflict, outside_scope


def check_source_labels(parameters, text):
    """Independent binding guard: never infer the physical quantity from its unit.

    Recollection checks report consistency; this guard separately checks explicit
    physical labels at every trusted source. It does not claim open-ended semantic
    understanding or independently verify the original scientific literature.
    """
    labels={'frequency_ghz':r'载波频率|工作频率|频率|载频',
            'distance_km':r'路径距离|通信距离|链路距离|距离|相距',
            'other':r'带宽|高度|海拔|波长|半径|宽度'}
    for p in parameters:
        field=p['canonical_name']
        if field not in {'frequency_ghz','distance_km'}:continue
        for origin in p['origins']:
            if origin['kind']!='user_text' or origin['span'] is None:continue
            start,end=origin['span']
            require(0<=start<end<=len(text),'SOURCE_SPAN_INVALID')
            clause_start=max([0]+[m.end() for m in re.finditer(r'[，,。；;\n]',text[:start])])
            fragment=text[clause_start:end]
            occurrences=[(m.start(),kind) for kind,pattern in labels.items() for m in re.finditer(pattern,fragment)]
            if occurrences:
                require(max(occurrences)[1]==field,'SOURCE_LABEL_MISMATCH')


def check_report(report, request, cards, root=None):
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
    # Model labels are replayed from the recorded call; each must still sit on the text.
    labels = [a for d in calls for a in d['details'].get('accepted', []) if a.get('kind') in LABEL_KINDS]
    check_labels(request['raw_text'], labels)
    numeric = [a for a in labels if a['kind'] in {'quantity', 'requirement'}]
    require((r['requirement'], r['solve'], r['entities']) == summary(labels), 'LABEL_SUMMARY_MISMATCH')
    # A missing entry only claims absence; every observed value is re-collected from source.
    needed = [p['canonical_name'] for p in r['parameters_proposal'] if p['status']=='missing']
    require(all(n in FIELDS or n in FACT_FIELDS for n in needed), 'UNKNOWN_PARAMETER')
    # Fact-store values and card assumptions are looked up again, for the same target as the agent chose.
    final = None if outside_scope(request['raw_text'], parsed, r['targets'], set(r['conditions'])) else final_target(r['targets'], cards)
    observed = {p['canonical_name'] for p in collect_parameters(request, parsed, [], numeric)[0]}
    facts = sources_for(request, r['entities'], cards, final, observed, root)
    parameters, conflicts, issues = collect_parameters(request, parsed, needed, numeric, facts['sources'])
    require(r['parameters_proposal'] == parameters, 'PARAMETER_SOURCE_MISMATCH')
    require(r['conflicts'] == conflicts, 'CONFLICT_MISMATCH')
    require(r['missing_parameters'] == [p['canonical_name'] for p in parameters if p['status']=='missing'], 'MISSING_MISMATCH')
    snapshot = snapshot_for(cards, root)
    require(r['knowledge_snapshot'] == snapshot, 'SNAPSHOT_MISMATCH')
    by_id = {c['id']:c for c in cards}
    candidates = r['candidate_models']
    require(all(c['model_id'] in SUPPORTED and c['model_id'] in by_id for c in candidates), 'MODEL_NOT_ALLOWED')
    ranks = {e['catalog_id']:e['relevance_rank'] for e in r['evidence_refs']}
    selected_cards = [by_id[c['model_id']] for c in candidates]
    require(all(c['id'] in ranks for c in selected_cards), 'MODEL_WITHOUT_EVIDENCE')
    refs = evidence_for(selected_cards, snapshot, ranks)
    require(r['evidence_refs'] == refs, 'EVIDENCE_MISMATCH')
    for c in candidates:
        card = by_id[c['model_id']]
        require(c == dict(model_id=card['id'], version=card['version'], status=card['status'], evidence_ids=r['evidence_ids']), 'MODEL_VERSION_MISMATCH')
    order = []
    if r['calculation_plan_proposal'] is not None:
        require(final is not None, 'PLAN_TARGET')
        order = facts['order']
        require([c['model_id'] for c in candidates] == order, 'PLAN_CANDIDATES')
        wanted, solve_if_unmet = plan_goal(r['requirement'], r['solve'], final, facts['leaves'])
        expected = plan_for(request, order, cards, parameters, r['evidence_ids'], wanted, solve_if_unmet, facts['notes'])
        if 'planning_role' in r:
            from planning.agents.planner import (equivalent_plan, compile_proposal, decorate_plan, validate_assessment,
                                                 planning_view, available_cards)
            role=r['planning_role']
            require(type(role) is dict and role.get('mode') in {'llm','stub','deterministic','deterministic_fallback'},'PLAN_ROLE')
            # The facts the model was shown are rebuilt from the program's own plan; H4 is replayed against them.
            base=dict(r,calculation_plan_proposal=expected)
            shown=planning_view(request,base,available_cards(cards),root)
            validate_assessment(role['proposal']['assessment'],base,stored=True,facts=shown)
            equivalent_plan(r['calculation_plan_proposal'],expected)
            replay=decorate_plan(compile_proposal(role['proposal'],base,cards,shown),role)
            require(replay==r['calculation_plan_proposal'],'PLAN_ROLE_MISMATCH')
        else:
            require(r['calculation_plan_proposal'] == expected, 'PLAN_SOURCE_MISMATCH')
        require(r['assumptions']==expected['assumptions'], 'ASSUMPTIONS_MISMATCH')
    if r['execution_status'] != 'AWAITING_CONFIRMATION':
        return r
    check_source_labels(parameters,request['raw_text'])
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
        info = merge_interpretation(interpreted, model, list(TARGETS), request['target'], request['condition'])
        require(not info['rejected'], 'MODEL_GROUNDING_MISMATCH')
    if request['target']:
        require(parsed['target_origin'] != 'explicit_text' or parsed['targets']==[request['target']], 'INTENT_CONFLICT')
        target = [request['target']]
    else:
        target = interpreted['targets']
        require(parsed['target_origin']=='explicit_text' or interpreted['targets'] != parsed['targets'] or any(d['code']=='MODEL_CALL' and any(a.get('kind')=='target' for a in d['details'].get('accepted',[])) for d in r['diagnostics']), 'TARGET_NOT_GROUNDED')
    require(final_target(target, cards) is not None and not parsed['unsupported_targets'], 'UNSUPPORTED_SCOPE')
    require(r['targets'] == target, 'TARGET_MISMATCH')
    conditions = set(interpreted['conditions'])
    if request['condition']:
        conditions.add(request['condition'])
        if request['condition']=='free_space_reference':
            conditions.add('free_space')
    require(r['conditions']==sorted(conditions) and ('free_space' in conditions or not requires_free_space(order, cards)), 'CONDITION_MISMATCH')
    require(not outside_scope(request['raw_text'],parsed,target,conditions), 'UNSUPPORTED_SCOPE')
    require('non_free_space' not in conditions or 'free_space_reference' in conditions, 'MODEL_NOT_APPLICABLE')
    require(not any(d['code'] in {'INPUT_PARSE_ISSUE','SOURCE_AMBIGUOUS','PARAMETER_APPROXIMATE','LABEL_CONFLICT'} for d in issues), 'INPUT_NOT_RESOLVED')
    values = {p['canonical_name']:p['value'] for p in parameters if p['value'] is not None}
    require(not facts['issues'] and not band_issues(facts['devices'], values), 'ENTITY_NOT_RESOLVED')
    leaves = r['calculation_plan_proposal']['required_parameters']
    require(all(k in values for k in leaves) and not bound_issues(order, cards, values), 'INPUT_DOMAIN_INVALID')
    if 'fspl_ghz' in order:
        fspl_values = {k: values[k] for k in ('frequency_ghz','distance_km') if k in values}  # a distance may come from coordinates
        require(all(min(numbers(v))>0 for v in fspl_values.values()), 'INPUT_DOMAIN_INVALID')
        require(not any(scope_issues('fspl_ghz', case, parsed) for case in scenarios(fspl_values)), 'MODEL_NOT_APPLICABLE')
    require(order == ['fspl_ghz'] or not any(type(values[k]) is dict for k in leaves), 'PLAN_DOMAIN_UNSUPPORTED')
    require(all(by_id[i]['status']=='verified' for i in order), 'MODEL_NOT_VERIFIED')
    return r
