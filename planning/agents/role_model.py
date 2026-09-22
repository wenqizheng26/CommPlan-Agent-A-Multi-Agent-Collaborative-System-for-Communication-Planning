"""Bounded local structured suggestions. Never returns trusted task state."""
import copy
import json
import urllib.request
from planning.requirements_contract import strict_json
from formula_rag.model_transport import chat, parse_output, ModelResponseError, check_cancelled
from planning.workflow.activity import observe


class LocalRoleSelector:
    def __call__(self, role, prompt, view, schema):
        payload = dict(model='signal-formula-qwen3', temperature=0, max_tokens=700,
            chat_template_kwargs={'enable_thinking': False},
            response_format={'type': 'json_schema', 'json_schema': {
                'name': role, 'strict': True, 'schema': schema}},
            messages=[{'role': 'system', 'content': prompt},
                      {'role': 'user', 'content': json.dumps(view, ensure_ascii=False)}])
        envelope, content = chat(payload)
        return dict(output=parse_output(content),raw_output=content,
                    model=envelope.get('model'), usage=envelope.get('usage', {}))


def suggest(role, prompt, view, schema, fallback, validate, selector=False, observer=None):
    """Two structural attempts maximum; transport failure falls back immediately."""
    if selector is False:
        return dict(proposal=copy.deepcopy(fallback), mode='deterministic', attempts=0, diagnostics=[])
    caller = LocalRoleSelector() if selector is None else selector
    diagnostics = []
    for attempt in range(1, 3):
        observe(observer, 'llm', 'started', caller=role, purpose=role, attempt=attempt)
        envelope={}
        check_cancelled()
        try:
            envelope = caller(role, prompt, copy.deepcopy(view), copy.deepcopy(schema))
            proposal = validate(envelope['output'])
            observe(observer, 'llm', 'completed', caller=role, purpose=role, attempt=attempt)
            return dict(proposal=copy.deepcopy(proposal), mode='llm' if isinstance(caller, LocalRoleSelector) else 'stub',
                        attempts=attempt, diagnostics=diagnostics, model=envelope.get('model'), usage=envelope.get('usage', {}))
        except ModelResponseError as exc:
            diagnostics.append(dict(code=exc.code,reason=str(exc),model_output=exc.raw_output,attempt=attempt))
            observe(observer,'llm','failed',caller=role,purpose=role,fallback=True)
            if not exc.retryable:
                break
        except (OSError, TimeoutError) as exc:
            diagnostics.append(dict(code='MODEL_UNAVAILABLE', exception=type(exc).__name__, attempt=attempt))
            observe(observer, 'llm', 'failed', caller=role, purpose=role, fallback=True)
            break
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            diagnostics.append(dict(code='MODEL_OUTPUT_INVALID', exception=type(exc).__name__, reason=str(exc)[:300], model_output=str(envelope.get('raw_output',''))[:4000], attempt=attempt))
            observe(observer, 'llm', 'failed', caller=role, purpose=role, attempt=attempt)
            view = dict(view, correction='前次输出未通过合同核验，请严格引用当前候选和身份，不添加字段。')
    return dict(proposal=copy.deepcopy(fallback), mode='deterministic_fallback', attempts=attempt,
                diagnostics=diagnostics)
