"""Strict JSON boundaries for requirements-slice-v1, not the full task contract."""
import copy
import hashlib
import json
import math
import re
from formula_rag.parsing import FIELDS, convert
from planning.services.fact_fields import FACT_FIELDS
from planning.services.input_domains import numbers, convert_domain

VERSION = '1.0.0'
PROFILE = 'requirements-slice-v1'
STATUSES = {'AWAITING_INPUT', 'AWAITING_CONFIRMATION', 'NEEDS_MODEL', 'FAILED'}
CONDITIONS = {'free_space', 'free_space_reference', 'non_free_space', 'maximum_doppler', 'two_way', 'single_knife_edge', 'smooth_sea'}
REQUEST_FIELDS = 'schema_version task_id revision request_id raw_text manual_parameters condition target'
REPORT_FIELDS = 'schema_version profile task_id revision request_id parameters_proposal conflicts missing_parameters candidate_models calculation_plan_proposal evidence_ids evidence_refs knowledge_snapshot questions assumptions conditions targets requirement solve entities execution_status component_modes runtime_health diagnostics'
SOLVE_UNKNOWNS = {'tx_power_dbm'}
# The service a request names, kept as a report label (requirement_policy.service_label).
SERVICE_LABELS = {'video': '视频', 'voice': '语音', 'data': '数据'}
# Where a parameter value came from: the text, the form, a site or device record, the modulation table,
# or an assumption (a card's, or the registered link tool's).
ORIGIN_KINDS = {'user_text', 'manual_form', 'site', 'device', 'modulation', 'default'}
PLAN_FIELDS = 'plan_id task_id revision objective steps required_parameters selected_model assumptions evidence_ids plan_hash'
# Only plans that need them carry these.
PLAN_OPTIONAL = {'checks', 'requirement', 'solve_if_unmet', 'assumed', 'origin', 'origin_note', 'assessment', 'tool', 'variants'}


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('NONFINITE_JSON: ' + value)
    return json.loads(text, object_pairs_hook=pairs, parse_constant=invalid)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def obj(value, fields):
    require(type(value) is dict and set(value) == set(fields.split()), 'SCHEMA_FIELDS: ' + fields)


def string(value):
    require(type(value) is str and bool(value.strip()), 'NONEMPTY_STRING_REQUIRED')


def number(value):
    try:
        valid = type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        valid = False
    require(valid, 'FINITE_NUMBER_REQUIRED')


def revision(value):
    require(type(value) is int and value >= 0, 'INVALID_REVISION')


def strings(values, unique=True):
    require(type(values) is list, 'LIST_REQUIRED')
    for value in values:
        string(value)
    require(not unique or len(values) == len(set(values)), 'DUPLICATE_ID')


def json_value(value):
    if value is None or type(value) in (str, bool):
        return
    if type(value) in (int, float):
        number(value)
    elif type(value) is list:
        for item in value:
            json_value(item)
    elif type(value) is dict:
        for key, item in value.items():
            string(key)
            json_value(item)
    else:
        raise ValueError('JSON_VALUE_REQUIRED')


def digest(value):
    json_value(value)
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def identity(value):
    require(value['schema_version'] == VERSION, 'SCHEMA_VERSION')
    string(value['task_id']); string(value['request_id']); revision(value['revision'])


def validate_request(value, *, expected_revision=None):
    obj(value, REQUEST_FIELDS)
    identity(value)
    if expected_revision is not None:
        revision(expected_revision)
        require(value['revision'] == expected_revision, 'STALE_REVISION')
    require(type(value['raw_text']) is str and len(value['raw_text']) <= 12000, 'INVALID_TEXT')
    require(value['condition'] is None or value['condition'] in {'free_space', 'free_space_reference', 'non_free_space'}, 'INVALID_CONDITION')
    if value['target'] is not None:
        string(value['target'])
    require(type(value['manual_parameters']) is dict, 'MANUAL_PARAMETERS_OBJECT')
    for name, item in value['manual_parameters'].items():
        from planning.services.plans import TARGETS
        generic = value['target'] is not None and value['target'] not in TARGETS
        require(name in FIELDS or name in FACT_FIELDS or
                (generic and re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', name)), 'UNKNOWN_PARAMETER')
        obj(item, 'value unit'); number(item['value']); string(item['unit'])
        if generic:
            from planning.services.card_units import convert_unit
            convert_unit(item['value'],item['unit'],item['unit'])
        elif name in FACT_FIELDS:
            require(item['unit'] == FACT_FIELDS[name][1], 'UNIT_MISMATCH')
        else:
            number(convert(name, item['value'], item['unit']))
    return copy.deepcopy(value)


def validate_report(value, request):
    request = validate_request(request)
    require(type(value) is dict and set(REPORT_FIELDS.split())<=set(value)<=set(REPORT_FIELDS.split())|{'planning_role','document_retrieval','suggestions','service','disabled_goals','available_goals','unit_suggestions','generic_card','generic_parameters','generic_choices'},'SCHEMA_FIELDS: report')
    json_value(value); identity(value)
    require(value['profile'] == PROFILE, 'PROFILE')
    for key in ('task_id', 'revision', 'request_id'):
        require(value[key] == request[key], 'REPORT_IDENTITY_MISMATCH')
    require(value['execution_status'] in STATUSES, 'INVALID_STATUS')
    if 'suggestions' in value:
        found = value['suggestions']
        obj(found, 'mode items source')
        require(value['execution_status'] == 'AWAITING_INPUT' and type(found['items']) is list and bool(found['items']), 'SUGGESTIONS')
        for item in found['items']:
            obj(item, 'field value unit reason note'); string(item['reason']); string(item['unit'])
            require(item['field'] in {'distance_km', 'tx_power_dbm', 'tx_gain_dbi', 'rx_gain_dbi', 'modulation'}, 'SUGGESTIONS')
    require(value['runtime_health'] in {'ready', 'degraded', 'unavailable'}, 'INVALID_HEALTH')
    obj(value['component_modes'], 'interpretation retrieval')
    require(value['component_modes']['interpretation'] in {'llm', 'deterministic', 'stub'}, 'INVALID_MODE')
    require(value['component_modes']['retrieval'] in {'lexical_fallback', 'dense', 'stub'}, 'INVALID_MODE')
    for key in ('missing_parameters', 'evidence_ids', 'questions', 'assumptions', 'conditions', 'targets'):
        strings(value[key])
    require(set(value['conditions']) <= CONDITIONS, 'INVALID_CONDITIONS')
    text = request['raw_text']
    def text_span(span):
        require(type(span) is list and len(span) == 2 and all(type(i) is int for i in span)
                and 0 <= span[0] < span[1] <= len(text), 'TEXT_SPAN')
    if value['requirement'] is not None:
        req = value['requirement']
        obj(req, 'quantity op value unit span'); number(req['value']); text_span(req['span'])
        require(req['quantity'] == 'link_margin_db' and req['op'] == '>=' and req['unit'] == 'dB', 'REQUIREMENT_SHAPE')
    if value['solve'] is not None:
        obj(value['solve'], 'unknown span'); text_span(value['solve']['span'])
        require(value['solve']['unknown'] in SOLVE_UNKNOWNS, 'SOLVE_UNKNOWN')
    require(type(value['entities']) is list and len(value['entities']) <= 6, 'ENTITIES_LIST')
    for e in value['entities']:
        obj(e, 'kind mention span'); string(e['mention']); text_span(e['span'])
        require(e['kind'] in {'site', 'device'} and text[e['span'][0]:e['span'][1]] == e['mention'], 'ENTITY_SPAN')
    if 'service' in value:
        s = value['service']
        obj(s, 'kind label mention span'); string(s['mention']); text_span(s['span'])
        require(type(s['kind']) is str and s['kind'] in SERVICE_LABELS and s['label'] == SERVICE_LABELS[s['kind']]
                and text[s['span'][0]:s['span'][1]] == s['mention'], 'SERVICE_LABEL')
    require(type(value['diagnostics']) is list, 'DIAGNOSTICS_LIST')
    for item in value['diagnostics']:
        obj(item, 'code message details'); string(item['code']); string(item['message'])
        require(type(item['details']) is dict, 'DIAGNOSTIC_DETAILS')
    ids, names, origins = set(), set(), {}
    require(type(value['parameters_proposal']) is list, 'PARAMETERS_LIST')
    for p in value['parameters_proposal']:
        obj(p, 'parameter_id canonical_name value unit original_value original_unit status origins evidence_ids created_revision')
        string(p['parameter_id']); string(p['canonical_name']); string(p['unit'])
        require(p['parameter_id'] not in ids and p['canonical_name'] not in names, 'DUPLICATE_PARAMETER')
        ids.add(p['parameter_id']); names.add(p['canonical_name'])
        revision(p['created_revision']); require(p['created_revision'] == request['revision'], 'STALE_PARAMETER')
        require(p['status'] in {'user_provided', 'missing', 'conflicting'}, 'SLICE_PARAMETER_STATUS')
        if p['value'] is not None:
            numbers(p['value'])
        require((p['value'] is None) == (p['status'] in {'missing', 'conflicting'}), 'PARAMETER_STATUS_VALUE')
        if p['original_value'] is not None:
            numbers(p['original_value']); string(p['original_unit'])
        else:
            require(p['original_unit'] is None, 'ORIGINAL_UNIT_WITHOUT_VALUE')
        strings(p['evidence_ids']); require(set(p['evidence_ids']) <= set(value['evidence_ids']), 'UNKNOWN_EVIDENCE')
        require(type(p['origins']) is list, 'ORIGINS_LIST')
        for origin in p['origins']:
            obj(origin, 'origin_id kind source_ref span value unit')
            string(origin['origin_id']); string(origin['source_ref']); string(origin['unit']); numbers(origin['value'])
            require(origin['kind'] in ORIGIN_KINDS, 'ORIGIN_KIND')
            require(origin['kind'] in {'user_text', 'manual_form'} or (origin['span'] is None and
                    re.fullmatch(r'(?:site|device|modulation):[a-z0-9-]+#[a-z_.]+|(?:card|tool):[a-z0-9_]+#[a-z0-9_]+',
                                 origin['source_ref'])),
                    'ORIGIN_SOURCE')
            require(origin['origin_id'] not in origins, 'DUPLICATE_ORIGIN')
            origins[origin['origin_id']] = p['canonical_name']
            span = origin['span']
            require(span is None or (type(span) is list and len(span) == 2 and all(type(i) is int for i in span) and 0 <= span[0] < span[1] <= len(request['raw_text'])), 'ORIGIN_SPAN')
        require(p['status'] != 'user_provided' or bool(p['origins']), 'MISSING_ORIGIN')
        require(p['status'] != 'conflicting' or len(p['origins']) >= 2, 'CONFLICT_ORIGINS')
    require(set(value['missing_parameters']) <= names, 'MISSING_PARAMETER_REFERENCE')
    conflict_ids = set()
    require(type(value['conflicts']) is list, 'CONFLICTS_LIST')
    for c in value['conflicts']:
        obj(c, 'conflict_id parameter_name origin_ids resolution'); string(c['conflict_id']); string(c['parameter_name'])
        strings(c['origin_ids']); require(len(c['origin_ids']) >= 2 and all(origins.get(i) == c['parameter_name'] for i in c['origin_ids']), 'CONFLICT_REFERENCE')
        require(c['resolution'] is None and c['conflict_id'] not in conflict_ids, 'CONFLICT_RESOLUTION')
        conflict_ids.add(c['conflict_id'])
    s = value['knowledge_snapshot']
    obj(s, 'snapshot_id catalog_hash source_manifest_hash embedding_weights_hash tokenizer_config_hash encoder_rule_version retrieval_rule_version')
    for key, item in s.items():
        if key in {'embedding_weights_hash', 'tokenizer_config_hash'} and item is None:
            continue
        string(item)
        if key.endswith('_hash'):
            require(bool(re.fullmatch('[a-f0-9]{64}', item)), 'INVALID_HASH')
    evidence_ids = []
    require(type(value['evidence_refs']) is list, 'EVIDENCE_LIST')
    for e in value['evidence_refs']:
        obj(e, 'evidence_id kind source_title source_url source_id locator excerpt content_hash catalog_id card_version status knowledge_snapshot_id parameter_names relevance_rank')
        for key in ('evidence_id', 'source_title', 'locator', 'excerpt', 'catalog_id', 'content_hash'):
            string(e[key])
        require(e['kind'] == 'formula_card' and e['status'] in {'verified', 'draft'}, 'EVIDENCE_KIND_STATUS')
        require(bool(re.fullmatch('[a-f0-9]{64}', e['content_hash'])), 'INVALID_HASH')
        require(e['knowledge_snapshot_id'] == s['snapshot_id'], 'EVIDENCE_SNAPSHOT')
        require((e['source_url'] is None) != (e['source_id'] is None), 'EVIDENCE_SOURCE')
        string(e['source_url'] or e['source_id']); string(e['card_version']); strings(e['parameter_names'])
        require(type(e['relevance_rank']) is int and e['relevance_rank'] > 0, 'EVIDENCE_RANK')
        evidence_ids.append(e['evidence_id'])
    strings(evidence_ids); require(evidence_ids == value['evidence_ids'], 'EVIDENCE_IDS')
    require(type(value['candidate_models']) is list, 'CANDIDATES_LIST')
    candidate_ids = []
    for c in value['candidate_models']:
        obj(c, 'model_id version status evidence_ids'); string(c['model_id']); string(c['version'])
        require(c['status'] in {'verified', 'draft'}, 'MODEL_STATUS'); strings(c['evidence_ids'])
        require(set(c['evidence_ids']) <= set(evidence_ids), 'MODEL_EVIDENCE')
        candidate_ids.append(c['model_id'])
    strings(candidate_ids)
    plan = value['calculation_plan_proposal']
    if plan is not None:
        require(type(plan) is dict and set(PLAN_FIELDS.split()) <= set(plan) <= set(PLAN_FIELDS.split()) | PLAN_OPTIONAL,
                'SCHEMA_FIELDS: plan')
        string(plan['plan_id']); string(plan['objective']); revision(plan['revision'])
        require(plan['task_id'] == request['task_id'] and plan['revision'] == request['revision'], 'PLAN_IDENTITY')
        strings(plan['required_parameters']); strings(plan['selected_model']); strings(plan['assumptions']); strings(plan['evidence_ids'])
        require(set(plan['evidence_ids']) <= set(evidence_ids), 'PLAN_EVIDENCE')
        require(set(plan['selected_model']) <= set(candidate_ids), 'PLAN_MODEL')
        require(plan['plan_hash'] == digest({k: v for k, v in plan.items() if k != 'plan_hash'}), 'PLAN_HASH')
        require(type(plan['steps']) is list and bool(plan['steps']), 'PLAN_STEPS')
        seen = set()
        for step in plan['steps']:
            obj({k:v for k,v in step.items() if k!='why'}, 'step_id tool_id inputs expected_unit dependencies required_conditions')
            if 'why' in step:string(step['why'])
            string(step['step_id']); string(step['tool_id']); string(step['expected_unit'])
            strings(step['dependencies']); strings(step['required_conditions'])
            require(step['step_id'] not in seen and set(step['dependencies']) <= seen, 'PLAN_DAG')
            require(step['tool_id'] in candidate_ids, 'PLAN_TOOL')
            require(set(step['required_conditions']) <= CONDITIONS, 'PLAN_CONDITION')
            require(type(step['inputs']) is dict, 'PLAN_INPUTS')
            for name, binding in step['inputs'].items():
                string(name); obj(binding, 'kind ref unit'); string(binding['ref']); string(binding['unit'])
                require(binding['kind'] in {'parameter', 'step'}, 'PLAN_BINDING')
                require(binding['ref'] in (ids if binding['kind'] == 'parameter' else seen), 'PLAN_BINDING_REFERENCE')
            seen.add(step['step_id'])
        for check in plan.get('checks', []):
            obj(check, 'check_id kind distance horizon'); string(check['check_id'])
            require(check['kind'] == 'line_of_sight' and {check['distance'], check['horizon']} <= seen, 'PLAN_CHECK')
        if 'requirement' in plan:
            obj(plan['requirement'], 'quantity op value unit'); number(plan['requirement']['value'])
            require(plan['requirement']['quantity'] == 'link_margin_db' and plan['requirement']['op'] == '>='
                    and plan['requirement']['unit'] == 'dB', 'PLAN_REQUIREMENT')
        if 'assumed' in plan:
            strings(plan['assumed']); require(plan['assumed'] == plan['assumptions'][:len(plan['assumed'])], 'PLAN_ASSUMED')
        if 'tool' in plan:
            require(plan['tool'] == 'calc_link_margin' and plan['selected_model'][-1] == 'link_margin', 'PLAN_TOOL')
        if 'variants' in plan:
            require('tool' in plan and type(plan['variants']) is list and bool(plan['variants']), 'PLAN_VARIANTS')
            for variant in plan['variants']:
                obj(variant, 'label parameter value unit source_ref'); string(variant['label']); number(variant['value'])
                require(variant['parameter'] == 'rx_threshold_dbm' and variant['unit'] == 'dBm' and
                        re.fullmatch(r'modulation:[a-z0-9-]+#rx_sensitivity_dbm', variant['source_ref']), 'PLAN_VARIANTS')
            require(len({v['label'] for v in plan['variants']}) == len(plan['variants']), 'PLAN_VARIANTS')
        if 'solve_if_unmet' in plan:
            require('requirement' in plan and plan['solve_if_unmet'] in SOLVE_UNKNOWNS
                    and plan['solve_if_unmet'] in plan['required_parameters'], 'PLAN_SOLVE')
    if value['execution_status'] == 'AWAITING_CONFIRMATION':
        require(plan is not None and bool(evidence_ids) and not value['conflicts'] and not value['missing_parameters'] and not value['questions'], 'PREMATURE_CONFIRMATION')
    return copy.deepcopy(value)
