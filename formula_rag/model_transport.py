"""Shared bounded loopback transport with actionable, source-preserving errors."""
import json
import time
import urllib.error
import urllib.request
from contextvars import ContextVar

operation_deadline = ContextVar('model_operation_deadline', default=None)
operation_cancel = ContextVar('model_operation_cancel', default=None)

class ModelResponseError(ValueError):
    def __init__(self, code, reason, raw_output='', retryable=False):
        super().__init__(reason)
        self.code, self.raw_output, self.retryable = code, raw_output[:4000], retryable


def check_cancelled():
    event=operation_cancel.get()
    if event is not None and event.is_set():
        raise ValueError('OPERATION_CANCELLED')


def chat(payload, url='http://127.0.0.1:18081/v1/chat/completions'):
    check_cancelled()
    deadline=operation_deadline.get()
    remaining=deadline-time.monotonic() if deadline else 30
    if remaining<=0:
        raise ModelResponseError('MODEL_TIME_BUDGET', '本次操作的模型调用时间预算已用尽。')
    # Conservative character estimate, not an exact tokenizer claim. Leave room
    # for template/schema and output in the configured 4096-token local model.
    content=''.join(m['content'] for m in payload['messages'])
    estimate=sum(1.5 if ord(c)>127 else 0.34 for c in content)+payload.get('max_tokens',700)+500
    if estimate>4096:
        raise ModelResponseError('MODEL_CONTEXT_LIMIT', '输入和输出预算可能超过本机 4096 token 上下文，请缩短当前描述。')
    request=urllib.request.Request(url,json.dumps(payload,ensure_ascii=False).encode(),{'Content-Type':'application/json'})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request,timeout=min(30,max(0.1,remaining))) as response:
            raw=response.read(1024*1024).decode('utf-8')
    except urllib.error.HTTPError as exc:
        body=exc.read(8000).decode('utf-8',errors='replace')
        context=any(x in body.lower() for x in ('context','token limit','too long','n_ctx'))
        raise ModelResponseError('MODEL_CONTEXT_LIMIT' if context else 'MODEL_REQUEST_REJECTED',
                                 f'模型服务拒绝请求（HTTP {exc.code}）：'+body[:500],body) from exc
    check_cancelled()
    try:
        envelope=json.loads(raw)
        content=envelope['choices'][0]['message']['content']
        if not isinstance(content,str) or not content.strip():
            raise ValueError('empty content')
    except (ValueError,KeyError,TypeError,IndexError) as exc:
        raise ModelResponseError('MODEL_OUTPUT_INVALID','模型返回的响应缺少有效 choices/message/content。',raw,True) from exc
    return envelope,content


def parse_output(content):
    try:
        def pairs(items):
            result={}
            for key,value in items:
                if key in result:
                    raise ValueError('duplicate key')
                result[key]=value
            return result
        def constant(value):
            raise ValueError('nonfinite literal')
        return json.loads(content,object_pairs_hook=pairs,parse_constant=constant)
    except (ValueError,TypeError) as exc:
        raise ModelResponseError('MODEL_OUTPUT_INVALID','模型内容不是合法 JSON。',content,True) from exc
