"""Single requirements/planning agent. All outputs are proposals, never results."""
import copy
from pathlib import Path
from formula_rag.catalog import load_catalog
from formula_rag.parsing import extract_request
from planning.retrieval import DefaultRetrievalService
from formula_rag.model import LocalSelector
from formula_rag.model_transport import ModelResponseError, check_cancelled
from formula_rag.interpretation import merge_interpretation
from formula_rag.applicability import scope_issues
from planning.services.input_domains import numbers, scenarios
from planning.requirements_contract import (PROFILE, VERSION, CONDITIONS, obj, require, strings,
    strict_json, validate_request, validate_report)
from planning.services.requirement_parameters import collect_parameters, diagnostic
from planning.services.requirement_evidence import snapshot_for, evidence_for, plan_for
from planning.services.requirement_policy import validate_target_semantics, intent_conflict, outside_scope
from planning.workflow.activity import observe

ALLOWED_MODEL = 'fspl_ghz'
REQUIRED = ['frequency_ghz', 'distance_km']


def model_proposal(envelope, candidate_ids):
    require(type(envelope) is dict and type(envelope.get('raw_output')) is str, 'MODEL_RAW_OUTPUT_REQUIRED')
    data = strict_json(envelope['raw_output'])
    obj(data, 'selected_ids targets conditions')
    strings(data['selected_ids'])
    require(set(data['selected_ids']) <= set(candidate_ids), 'MODEL_UNKNOWN_ID')
    for key, ids, limit in [('targets', candidate_ids, 3), ('conditions', CONDITIONS, 5)]:
        require(type(data[key]) is list and len(data[key]) <= limit, 'MODEL_LIST')
        seen = set()
        for item in data[key]:
            obj(item, 'id evidence')
            require(type(item['id']) is str and item['id'] in ids and item['id'] not in seen, 'MODEL_UNKNOWN_ID')
            require(type(item['evidence']) is str and 2 <= len(item['evidence']) <= 300, 'MODEL_EVIDENCE')
            seen.add(item['id'])
    return data


class RequirementsAgent:
    def __init__(self, root, selector=None, allow_fallback=True, retrieval=None, retrieval_params=None):
        self.root = Path(root)
        self.selector = LocalSelector() if selector is None else (None if selector is False else selector)
        self.allow_fallback = allow_fallback
        # Loading errors are handled by the graph/CLI as failures, not fake snapshots.
        self.cards = load_catalog(self.root)
        # A long-lived service (warm vectors) may be shared; it follows this command's catalog.
        self.retrieval = retrieval or DefaultRetrievalService(self.root, self.cards)
        self.retrieval.update(self.cards)
        self.retrieval_params = dict(mode='lexical', top_k=8, top_n=3) | (retrieval_params or {})
        self.last_retrieval = None

    def run(self, request, *, expected_revision=None):
        observer=getattr(self,'observer',None)
        observe(observer,'parse','started')
        request = validate_request(request, expected_revision=expected_revision)
        parsed = extract_request(request['raw_text'])
        observe(observer,'parse','completed',mode='deterministic')
        original = copy.deepcopy(parsed)
        diagnostics, questions = [], []
        if request['target']:
            label = '路径损耗' if request['target'] == ALLOWED_MODEL else request['target']
            diagnostics.append(diagnostic('USER_TARGET_SELECTION', '计算目标来自用户选择：' + label + '。',
                value=request['target'], source_ref=request['request_id'] + ':target'))
        if request['condition']:
            label = {'free_space':'理想自由空间模型','free_space_reference':'自由空间基准',
                     'non_free_space':'实际非自由空间环境'}[request['condition']]
            diagnostics.append(diagnostic('USER_CONDITION_SELECTION', '模型条件来自用户选择：' + label + '。',
                value=request['condition'], source_ref=request['request_id'] + ':condition'))
        health, mode, failed = 'ready', 'deterministic', False
        card = next((c for c in self.cards if c['id'] == ALLOWED_MODEL), None)
        observe(observer,'retrieval','started')
        observe(observer,'rag','started',caller='requirements')
        observe(observer,'knowledge','started',caller='rag',operation='search_cards')
        found = self.retrieval.search(request['raw_text'], **self.retrieval_params)
        self.last_retrieval = found.to_dict()
        observe(observer,'knowledge','completed',caller='rag',operation='search_cards')
        observe(observer,'rag','completed',caller='requirements',mode=found.mode_used,degraded=found.degraded,
                latency_ms=found.latency_ms.get('total'))
        observe(observer,'retrieval','completed',mode=found.mode_used,hits=len(found.hits),used=len(found.used))
        # Only the top-n hits reach the model context, and a candidate still needs lexical
        # evidence from the request text: vector similarity alone never admits a formula.
        usable = {h['id']: h['rank'] for h in found.hits if h['id'] in found.used and h['scores']['lexical'] > 0}
        # A manual target is a direct lookup, not a semantic retrieval claim.
        if request['target'] == ALLOWED_MODEL and card:
            usable[ALLOWED_MODEL] = 1
            diagnostics.append(diagnostic('EXPLICIT_CARD_LOOKUP', '按用户显式目标查找登记卡。'))
        candidates = [card] if card and ALLOWED_MODEL in usable else []
        prelim_conditions = set(parsed['conditions'])
        if request['condition']:
            prelim_conditions.add(request['condition'])
        known_unsupported = outside_scope(request['raw_text'], original,
            [request['target']] if request['target'] else parsed['targets'], prelim_conditions)
        if self.selector and candidates and not known_unsupported:
            observe(observer,'interpretation','started')
            observe(observer,'llm','started',caller='requirements',purpose='intent')
            correction=None
            for attempt in range(1, 4):
                check_cancelled()
                envelope, info = {}, {}
                stage = 'model_response'
                try:
                    if isinstance(self.selector, LocalSelector):
                        envelope = self.selector(request['raw_text'], copy.deepcopy(candidates),
                            manual_target=request['target'], manual_condition=request['condition'], correction=correction)
                    else:
                        envelope = self.selector(request['raw_text'], copy.deepcopy(candidates))
                    stage = 'structure'
                    model = model_proposal(envelope, [c['id'] for c in candidates])
                    require(not request['target'] or not model['targets'], 'MODEL_SELECTED_TARGET_REPEATED')
                    require(not request['condition'] or not model['conditions'], 'MODEL_SELECTED_CONDITION_REPEATED')
                    stage = 'target_semantics'
                    validate_target_semantics(model)
                    stage = 'source_grounding'
                    checked = copy.deepcopy(parsed)
                    info = merge_interpretation(checked, model, [c['id'] for c in candidates],
                                               manual_target=request['target'], manual_condition=request['condition'])
                    require(not info['rejected'], 'MODEL_UNGROUNDED')
                    parsed = checked
                    mode = 'llm' if isinstance(self.selector, LocalSelector) else 'stub'
                    diagnostics.append(diagnostic('MODEL_CALL', '意图建议经原文核验。', attempt=attempt,
                        model=envelope.get('model'), usage=envelope.get('usage', {}), accepted=info['accepted'],
                        latency_ms=envelope.get('latency_ms')))
                    break
                except ModelResponseError as exc:
                    correction={'stage':stage,'reason':str(exc)[:300]}
                    diagnostics.append(diagnostic(exc.code,str(exc),attempt=attempt,stage=stage,
                        reason=str(exc),model_output=exc.raw_output,
                        next_action='缩短描述或检查模型服务返回的具体错误；可继续使用确定性解析。'))
                    if not exc.retryable or attempt==3:
                        health = 'degraded' if self.allow_fallback else 'unavailable'
                        failed = not self.allow_fallback
                        break
                except (OSError, TimeoutError) as exc:
                    diagnostics.append(diagnostic('MODEL_UNAVAILABLE', '本地模型未响应，已停止本次模型调用。',
                        attempt=attempt, exception=type(exc).__name__, next_action='启动模型服务或使用确定性模式。'))
                    health = 'degraded' if self.allow_fallback else 'unavailable'
                    failed = not self.allow_fallback
                    break
                except (ValueError, KeyError, TypeError, IndexError) as exc:
                    correction={'stage':stage,'reason':str(exc)[:300],'rejected':info.get('rejected',[])}
                    diagnostics.append(diagnostic('MODEL_OUTPUT_INVALID', '模型结构或原文证据不合法。', attempt=attempt,
                        exception=type(exc).__name__, reason=str(exc)[:300], stage=stage,
                        rejected=info.get('rejected', []),
                        model_output=str(envelope.get('raw_output', ''))[:4000] if isinstance(envelope, dict) else '',
                        next_action='查看逐次诊断记录；核对原文与用户选择，或采用确定性解析。'))
                    if attempt == 3:
                        health = 'degraded' if self.allow_fallback else 'unavailable'
                        failed = not self.allow_fallback
        elif self.selector:
            diagnostics.append(diagnostic('MODEL_SKIPPED', '目标已超出范围或没有有效候选，未调用模型。'))

        observe(observer,'interpretation','completed' if mode in {'llm','stub'} else 'skipped',
                mode=mode,health=health)
        if self.selector and candidates and not known_unsupported:
            observe(observer,'llm','completed' if mode in {'llm','stub'} else 'failed',
                    caller='requirements',purpose='intent',mode=mode,health=health)
        observe(observer,'planning','started')

        targets = parsed['targets'] if parsed['target_origin'] in {'explicit_text', 'manual'} else []
        # merge_interpretation keeps parser origin unchanged; accepted model targets are checked explicitly.
        if mode in {'stub', 'llm'} and 'info' in locals() and info['target_origin'] == 'model':
            targets = parsed['targets']
        conflicting_intent = intent_conflict(request, original)
        if request['target']:
            if original['target_origin'] == 'explicit_text' and set(original['targets']) != {request['target']}:
                conflicting_intent = True
            targets = [request['target']]
        conditions = set(parsed['conditions'])
        if request['condition']:
            manual = request['condition']
            if (manual == 'non_free_space' and 'free_space' in conditions) or (manual != 'non_free_space' and 'non_free_space' in conditions):
                conflicting_intent = True
            conditions.add(manual)
            if manual == 'free_space_reference':
                conditions.add('free_space')
        if conflicting_intent:
            diagnostics.append(diagnostic('INTENT_CONFLICT', '原文存在否定或互相冲突的目标、模型条件，或与用户选择不一致。', next_action='请统一原文与手工选择。'))
            questions.append('请统一原文中的目标、传播条件及用户选择，明确本次采用的内容。')

        # No guess from a bare keyword or the top retrieval result.
        unsupported = outside_scope(request['raw_text'], original, targets, conditions)
        if not targets and not unsupported:
            questions.append('请说明希望得到路径损耗、链路可用性判断，还是方案比较；当前仅支持自由空间路径损耗基准。')
        relevant = targets == [ALLOWED_MODEL] or unsupported
        parameters, conflicts, param_diagnostics = collect_parameters(request, original, REQUIRED if relevant else [])
        diagnostics.extend(param_diagnostics)
        missing = [p['canonical_name'] for p in parameters if p['status'] == 'missing']
        if missing:
            questions.append('请补充：' + '、'.join(missing))
            diagnostics.append(diagnostic('MISSING_INPUT', '必要参数尚未输入。', fields=missing))
        if conflicts:
            questions.append('请消除同一参数的来源冲突。')
            diagnostics.append(diagnostic('PARAMETER_CONFLICT', '同一参数存在不同数值。', fields=[c['parameter_name'] for c in conflicts]))
        if any(d['code'] in {'INPUT_PARSE_ISSUE', 'SOURCE_AMBIGUOUS', 'PARAMETER_APPROXIMATE'} for d in diagnostics):
            questions.append('请核对未能明确解析的数值及其来源。')
        values = {p['canonical_name']: p['value'] for p in parameters if p['value'] is not None}
        invalid = [k for k in REQUIRED if k in values and min(numbers(values[k])) <= 0]
        if invalid:
            questions.append('频率和距离必须大于零，请修正：' + '、'.join(invalid))
            diagnostics.append(diagnostic('INPUT_DOMAIN_INVALID', '必要参数超出定义域。', fields=invalid))
        if targets == [ALLOWED_MODEL] and 'free_space' not in conditions and not unsupported:
            questions.append('请明确采用自由空间模型或自由空间基准。')
            diagnostics.append(diagnostic('MISSING_CONDITION', '不能从视距、岸海或参数齐全推断自由空间条件。'))
        scope = [issue for case in scenarios(values) for issue in scope_issues(ALLOWED_MODEL, case, parsed)] if targets == [ALLOWED_MODEL] and not invalid else []
        if scope:
            unsupported = True
            diagnostics.append(diagnostic('MODEL_NOT_APPLICABLE', scope[0]['message'], next_action='核对单位或另选适用模型。'))
        snapshot = snapshot_for(self.cards)
        refs = evidence_for(candidates, snapshot, usable)
        evidence_ids = [e['evidence_id'] for e in refs]
        available = bool(card and refs and card['status'] == 'verified')
        if unsupported:
            diagnostics.append(diagnostic('UNSUPPORTED_SCOPE', '当前入口仅支持自由空间单链路损耗基准，不能替代实际海面、散射或链路预算。',
                                          next_action='明确改为自由空间基准，或等待对应模型接入。'))
        elif targets and not available:
            diagnostics.append(diagnostic('EVIDENCE_UNAVAILABLE', '没有可用的已登记模型证据。', next_action='检查知识目录与目标。'))
        plan = plan_for(request, card, parameters, evidence_ids) if available and targets == [ALLOWED_MODEL] and not unsupported else None
        status = ('FAILED' if failed else 'NEEDS_MODEL' if unsupported or (targets and not available) else
                  'AWAITING_INPUT' if questions or not plan else 'AWAITING_CONFIRMATION')
        diagnostics.append(diagnostic('SOURCE_REVIEW_LIMITATION', '来源状态来自库内登记，本次没有独立复核原始文献。'))
        report = dict(schema_version=VERSION, profile=PROFILE, **{k: request[k] for k in ('task_id','revision','request_id')},
            parameters_proposal=parameters, conflicts=conflicts, missing_parameters=missing,
            candidate_models=[dict(model_id=c['id'], version=c['version'], status=c['status'], evidence_ids=evidence_ids) for c in candidates],
            calculation_plan_proposal=plan, evidence_ids=evidence_ids, evidence_refs=refs, knowledge_snapshot=snapshot,
            questions=list(dict.fromkeys(questions)), assumptions=list(card['applicability'].get('notes', [])) if plan else [],
            conditions=sorted(conditions), targets=targets, execution_status=status,
            component_modes=dict(interpretation=mode, retrieval='lexical_fallback'), runtime_health=health, diagnostics=diagnostics)
        checked=validate_report(report, request)
        observe(observer,'planning','completed',status=status)
        return checked
