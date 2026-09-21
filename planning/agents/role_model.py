"""Bounded local structured suggestions. Never returns trusted task state."""
import copy
import json
import urllib.request
from planning.requirements_contract import strict_json
from planning.workflow.activity import observe


class LocalRoleSelector:
    def __call__(self, role, prompt, view, schema):
        payload = dict(model='signal-formula-qwen3', temperature=0, max_tokens=700,
            chat_template_kwargs={'enable_thinking': False},
            response_format={'type': 'json_schema', 'json_schema': {
                'name': role, 'strict': True, 'schema': schema}},
            messages=[{'role': 'system', 'content': prompt},
                      {'role': 'user', 'content': json.dumps(view, ensure_ascii=False)}])
        request = urllib.request.Request('http://127.0.0.1:18081/v1/chat/completions',
            json.dumps(payload, ensure_ascii=False).encode(), {'Content-Type': 'application/json'})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=30) as response:
            envelope = json.load(response)
        return dict(output=strict_json(envelope['choices'][0]['message']['content']),
                    model=envelope.get('model'), usage=envelope.get('usage', {}))


def suggest(role, prompt, view, schema, fallback, validate, selector=False, observer=None):
    """Two structural attempts maximum; transport failure falls back immediately."""
    if selector is False:
        return dict(proposal=copy.deepcopy(fallback), mode='deterministic', attempts=0, diagnostics=[])
    caller = LocalRoleSelector() if selector is None else selector
    diagnostics = []
    for attempt in range(1, 3):
        observe(observer, 'llm', 'started', caller=role, purpose=role, attempt=attempt)
        try:
            envelope = caller(role, prompt, copy.deepcopy(view), copy.deepcopy(schema))
            proposal = validate(envelope['output'])
            observe(observer, 'llm', 'completed', caller=role, purpose=role, attempt=attempt)
            return dict(proposal=copy.deepcopy(proposal), mode='llm' if isinstance(caller, LocalRoleSelector) else 'stub',
                        attempts=attempt, diagnostics=diagnostics, model=envelope.get('model'), usage=envelope.get('usage', {}))
        except (OSError, TimeoutError) as exc:
            diagnostics.append(dict(code='MODEL_UNAVAILABLE', exception=type(exc).__name__, attempt=attempt))
            observe(observer, 'llm', 'failed', caller=role, purpose=role, fallback=True)
            break
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            diagnostics.append(dict(code='MODEL_OUTPUT_INVALID', exception=type(exc).__name__, attempt=attempt))
            observe(observer, 'llm', 'failed', caller=role, purpose=role, attempt=attempt)
            view = dict(view, correction='前次输出未通过合同核验，请严格引用当前候选和身份，不添加字段。')
    return dict(proposal=copy.deepcopy(fallback), mode='deterministic_fallback', attempts=attempt,
                diagnostics=diagnostics)
