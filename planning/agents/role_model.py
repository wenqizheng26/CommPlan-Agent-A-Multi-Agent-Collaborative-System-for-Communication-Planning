"""Bounded local structured suggestions. Never returns trusted task state."""
import copy
import json
import urllib.error
from formula_rag.model_transport import chat, parse_output, ModelResponseError, check_cancelled
from planning.workflow.activity import observe


def failure_reason(exc):
    """Coarse cause for statistics: offline, timeout, rejected or structure."""
    if isinstance(exc, ModelResponseError):
        return {'MODEL_TIME_BUDGET': 'timeout', 'MODEL_REQUEST_REJECTED': 'rejected',
                'MODEL_CONTEXT_LIMIT': 'rejected'}.get(exc.code, 'structure')
    if isinstance(exc, TimeoutError) or isinstance(getattr(exc, 'reason', None), TimeoutError):
        return 'timeout'
    if isinstance(exc, OSError):
        return 'offline'
    return 'structure'


def call_details(binding, envelope=None):
    details = dict(model_id=binding.model_id) if binding else {}
    if envelope:
        details.update(latency_ms=envelope.get('latency_ms'), usage=envelope.get('usage') or {})
    return details


class LocalRoleSelector:
    def __init__(self, binding=None):
        self.binding = binding

    def __call__(self, role, prompt, view, schema):
        b = self.binding
        payload = dict(model=b.alias if b else 'signal-formula-qwen3', temperature=b.temperature if b else 0,
            max_tokens=700, chat_template_kwargs={'enable_thinking': False},
            response_format={'type': 'json_schema', 'json_schema': {
                'name': role, 'strict': True, 'schema': schema}},
            messages=[{'role': 'system', 'content': prompt},
                      {'role': 'user', 'content': json.dumps(view, ensure_ascii=False)}])
        envelope, content = chat(payload, *([b.url] if b else []),
                                 **(dict(timeout=b.timeout_s, context=b.context) if b else {}))
        return dict(output=parse_output(content), raw_output=content, model=envelope.get('model'),
                    usage=envelope.get('usage', {}), latency_ms=envelope.get('latency_ms'))


def suggest(role, prompt, view, schema, fallback, validate, selector=False, observer=None):
    """Two structural attempts maximum; transport failure falls back immediately."""
    if selector is False:
        return dict(proposal=copy.deepcopy(fallback), mode='deterministic', attempts=0, diagnostics=[])
    caller = LocalRoleSelector() if selector is None else selector
    binding = getattr(caller, 'binding', None)
    diagnostics = []
    for attempt in range(1, 3):
        observe(observer, 'llm', 'started', caller=role, purpose=role, attempt=attempt, **call_details(binding))
        envelope={}
        check_cancelled()
        try:
            envelope = caller(role, prompt, copy.deepcopy(view), copy.deepcopy(schema))
            proposal = validate(envelope['output'])
            observe(observer, 'llm', 'completed', caller=role, purpose=role, attempt=attempt,
                    **call_details(binding, envelope))
            return dict(proposal=copy.deepcopy(proposal), mode='llm' if isinstance(caller, LocalRoleSelector) else 'stub',
                        attempts=attempt, diagnostics=diagnostics, model=envelope.get('model'), usage=envelope.get('usage', {}),
                        **({'model_id': binding.model_id} if binding else {}))
        except ModelResponseError as exc:
            diagnostics.append(dict(code=exc.code,reason=str(exc),model_output=exc.raw_output,attempt=attempt))
            observe(observer,'llm','failed',caller=role,purpose=role,fallback=True,reason=failure_reason(exc),
                    **call_details(binding))
            if not exc.retryable:
                break
        except (OSError, TimeoutError) as exc:
            diagnostics.append(dict(code='MODEL_UNAVAILABLE', exception=type(exc).__name__, attempt=attempt))
            observe(observer, 'llm', 'failed', caller=role, purpose=role, fallback=True, reason=failure_reason(exc),
                    **call_details(binding))
            break
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            if str(exc) == 'OPERATION_CANCELLED':
                raise  # a user stop rolls the command back; it is not a bad model answer
            diagnostics.append(dict(code='MODEL_OUTPUT_INVALID', exception=type(exc).__name__, reason=str(exc)[:300], model_output=str(envelope.get('raw_output',''))[:4000], attempt=attempt))
            observe(observer, 'llm', 'failed', caller=role, purpose=role, attempt=attempt, reason='structure',
                    **call_details(binding))
            view = dict(view, correction='前次输出未通过合同核验，请严格引用当前候选和身份，不添加字段。')
    return dict(proposal=copy.deepcopy(fallback), mode='deterministic_fallback', attempts=attempt,
                diagnostics=diagnostics)
