"""Bounded local structured suggestions. Never returns trusted task state."""
import copy
from contextvars import ContextVar
import json
import re
import urllib.error
from formula_rag.model_transport import chat, parse_output, ModelResponseError, check_cancelled
from planning.workflow.activity import observe

# Output budget per role; the reviewer writes the answer and the review opinions.
MAX_TOKENS = {'validator_agent': 900, 'compute_agent': 1600, 'extraction': 1800}
# Language of the text a model writes for the user, set per command from the page language.
output_language = ContextVar('output_language', default='zh')
ENGLISH_FIRST = '写给用户看的文字一律用英文。\n'
ENGLISH = ('\n输出语言：写给用户看的文字一律用英文，简洁、专业，用通信工程的英文术语；{limits}。'
           'JSON 键名、id、型号、标准编号和单位照原样写；数字规则不变。')
HAN = re.compile('[㐀-鿿]')


def english():
    return output_language.get() == 'en'


def for_language(prompt, limits, swaps=()):
    """The prompt as is, or with English output instructions when the page is in English.

    `swaps` replace the Chinese length rules and examples, which otherwise pull the model back to Chinese.
    """
    if not english():
        return prompt
    for old, new in swaps:
        prompt = prompt.replace(old, new)
    return ENGLISH_FIRST + prompt.replace('用中文', '') + ENGLISH.format(limits=limits)


def in_chinese(text):
    """Written in Chinese, rather than an English sentence that quotes a Chinese name."""
    return type(text) is str and len(HAN.findall(text)) * 2 > len(re.findall('[A-Za-z]', text))


def language_hint(texts):
    """The rewrite hint when the page is in English but some text came back in Chinese; empty otherwise."""
    return '写给用户看的文字要用英文写，名称照原样写。' if english() and any(in_chinese(t) for t in texts) else ''


class Rewrite(ValueError):
    """The output is well formed but some text must be rewritten.

    `kept` is the output with that text withheld; it is used when no attempt is left.
    `reason` is the cause shown in the timing view.
    """
    def __init__(self, code, kept, hint, reason='numbers'):
        super().__init__(code)
        self.kept, self.hint, self.reason = kept, hint, reason


def failure_reason(exc):
    """Coarse cause for statistics: offline, timeout, rejected or structure."""
    if isinstance(exc, ModelResponseError):
        return {'MODEL_TIME_BUDGET': 'timeout', 'MODEL_REQUEST_REJECTED': 'rejected', 'MODEL_NOT_LOADED': 'offline',
                'MODEL_CONTEXT_LIMIT': 'rejected'}.get(exc.code, 'structure')
    if isinstance(exc, TimeoutError) or isinstance(getattr(exc, 'reason', None), TimeoutError):
        return 'timeout'
    if isinstance(exc, OSError):
        return 'offline'
    return 'structure'


def call_details(binding, envelope=None):
    details = dict(model_id=binding.model_id, timeout_s=binding.timeout_s) if binding else {}
    if envelope:
        details.update(latency_ms=envelope.get('latency_ms'), usage=envelope.get('usage') or {})
    return details


class LocalRoleSelector:
    def __init__(self, binding=None):
        self.binding = binding

    def __call__(self, role, prompt, view, schema):
        b = self.binding
        payload = dict(model=b.alias if b else None, temperature=b.temperature if b else 0,
            max_tokens=MAX_TOKENS.get(role, 700), chat_template_kwargs={'enable_thinking': False},
            response_format={'type': 'json_schema', 'json_schema': {
                'name': role, 'strict': True, 'schema': schema}},
            messages=[{'role': 'system', 'content': prompt},
                      {'role': 'user', 'content': json.dumps(view, ensure_ascii=False)}])
        envelope, content = chat(payload, *([b.url] if b else []), agent=role,
                                 **(dict(timeout=b.timeout_s, context=b.context) if b else {}))
        return dict(output=parse_output(content), raw_output=content, model=envelope.get('model'),
                    usage=envelope.get('usage', {}), latency_ms=envelope.get('latency_ms'))


def suggest(role, prompt, view, schema, fallback, validate, selector=False, observer=None, retain_rewrite_on_unavailable=False):
    """Two attempts maximum; callers may keep checked content when its rewrite goes offline or fails."""
    if selector is False:
        return dict(proposal=copy.deepcopy(fallback), mode='deterministic', attempts=0, diagnostics=[])
    caller = LocalRoleSelector() if selector is None else selector
    binding = getattr(caller, 'binding', None)
    diagnostics = []
    retained = None
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
        except Rewrite as exc:
            retained = dict(proposal=copy.deepcopy(exc.kept), mode='llm' if isinstance(caller, LocalRoleSelector) else 'stub',
                model=envelope.get('model'), usage=envelope.get('usage', {}),
                **({'model_id': binding.model_id} if binding else {}))
            diagnostics.append(dict(code=str(exc), reason=exc.hint[:300],
                                    model_output=str(envelope.get('raw_output', ''))[:4000], attempt=attempt))
            if attempt == 2:
                observe(observer, 'llm', 'completed', caller=role, purpose=role, attempt=attempt,
                        **call_details(binding, envelope))
                return dict(proposal=copy.deepcopy(exc.kept), mode='llm' if isinstance(caller, LocalRoleSelector) else 'stub',
                            attempts=attempt, diagnostics=diagnostics, model=envelope.get('model'), usage=envelope.get('usage', {}),
                            **({'model_id': binding.model_id} if binding else {}))
            observe(observer, 'llm', 'failed', caller=role, purpose=role, attempt=attempt, reason=exc.reason,
                    **call_details(binding))
            view = dict(view, correction=exc.hint)
        except ModelResponseError as exc:
            diagnostics.append(dict(code=exc.code,reason=str(exc),model_output=exc.raw_output,attempt=attempt))
            observe(observer,'llm','failed',caller=role,purpose=role,fallback=not (retain_rewrite_on_unavailable and retained is not None),reason=failure_reason(exc),
                    **call_details(binding))
            if not exc.retryable:
                if retain_rewrite_on_unavailable and retained:
                    return dict(retained,attempts=attempt,diagnostics=diagnostics)
                break
        except (OSError, TimeoutError) as exc:
            diagnostics.append(dict(code='MODEL_UNAVAILABLE', exception=type(exc).__name__, attempt=attempt))
            observe(observer, 'llm', 'failed', caller=role, purpose=role, fallback=not (retain_rewrite_on_unavailable and retained is not None), reason=failure_reason(exc),
                    **call_details(binding))
            if retain_rewrite_on_unavailable and retained:
                return dict(retained,attempts=attempt,diagnostics=diagnostics)
            break
        except (ValueError, KeyError, TypeError, IndexError) as exc:
            if str(exc) == 'OPERATION_CANCELLED':
                raise  # a user stop rolls the command back; it is not a bad model answer
            diagnostics.append(dict(code='MODEL_OUTPUT_INVALID', exception=type(exc).__name__, reason=str(exc)[:300], model_output=str(envelope.get('raw_output',''))[:4000], attempt=attempt))
            observe(observer, 'llm', 'failed', caller=role, purpose=role, attempt=attempt, reason='structure',
                    **call_details(binding))
            view = dict(view, correction='前次输出未通过合同核验：'+str(exc)[:200]+'。请根据失败原因修改，只引用当前候选和身份。')
    if retain_rewrite_on_unavailable and retained:
        return dict(retained, attempts=attempt, diagnostics=diagnostics)  # the rewrite broke what had passed
    return dict(proposal=copy.deepcopy(fallback), mode='deterministic_fallback', attempts=attempt,
                diagnostics=diagnostics)
