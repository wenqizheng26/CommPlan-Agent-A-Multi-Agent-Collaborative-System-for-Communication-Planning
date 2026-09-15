"""Loopback-only local UI and JSON API for the communication formula RAG."""
import argparse
import json
import threading
import mimetypes
import uuid
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from formula_rag.catalog import load_catalog
from formula_rag.parsing import FIELDS
from formula_rag.pipeline import Engine
from formula_rag.presentation import formula_view


def create_server(root, engine, port=18080, output_dir=None):
    root = Path(root)
    gate = threading.Lock()
    results = {}
    output_dir = Path(output_dir) if output_dir else root/'outputs'
    asset_root = (root/'web/assets').resolve()
    assets = {'/assets/' + p.relative_to(asset_root).as_posix(): p for p in asset_root.rglob('*') if p.is_file() and p.resolve().is_relative_to(asset_root)}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def respond(self, code, body, content_type='application/json; charset=utf-8'):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False, allow_nan=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def valid_host(self):
            return self.headers.get('Host', '') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

        def do_GET(self):
            if not self.valid_host():
                return self.respond(403, {'error': '仅支持本地访问'})
            path = urlparse(self.path).path
            if path == '/':
                return self.respond(200, (root/'web/index.html').read_bytes(), 'text/html; charset=utf-8')
            if path in assets:
                asset = assets[path]
                return self.respond(200, asset.read_bytes(), mimetypes.guess_type(asset.name)[0] or 'application/octet-stream')
            if path == '/api/status':
                return self.respond(200, {'application': 'signal-formula-rag', 'dense_enabled': engine.retriever.dense,
                                         'llm_enabled': engine.selector is not None, 'formula_count': len(load_catalog(root))})
            if path == '/api/catalog':
                return self.respond(200, {'formulas': [{**c, 'display': formula_view(c)} for c in load_catalog(root)], 'fields': FIELDS})
            return self.respond(404, {'error': '未找到页面'})

        def do_POST(self):
            if not self.valid_host():
                return self.respond(403, {'error': '仅支持本地访问'})
            origin = self.headers.get('Origin')
            if origin and origin not in {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'}:
                return self.respond(403, {'error': '拒绝外部网页提交'})
            path = urlparse(self.path).path
            if path not in ('/api/query', '/api/save-result'):
                return self.respond(404, {'error': '接口不存在'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if length <= 0 or length > 64000:
                    raise ValueError('请求大小不正确')
                def invalid_constant(value):
                    raise ValueError('JSON不允许NaN或Infinity')
                body = json.loads(self.rfile.read(length), parse_constant=invalid_constant)
                if not isinstance(body, dict):
                    raise ValueError('请求必须是JSON对象')
                if path == '/api/save-result':
                    identifier = body.get('result_id')
                    if set(body) != {'result_id'} or not isinstance(identifier, str):
                        raise ValueError('保存时仅接受已有计算记录的标识')
                    with gate:
                        if identifier not in results:
                            raise ValueError('计算记录已失效，请重新计算后保存')
                        result, filename = results[identifier]
                        output_dir.mkdir(parents=True, exist_ok=True)
                        output = output_dir/filename
                        # Never accept a client-supplied path or calculated value.
                        with output.open('w', encoding='utf-8') as stream:
                            json.dump(result, stream, ensure_ascii=False, indent=2, allow_nan=False)
                    return self.respond(200, {'saved': True, 'filename': filename, 'path': str(output.resolve())})
                if not isinstance(body.get('text'), str):
                    raise ValueError('请输入问题文本')
                with gate:
                    result = engine.query(body['text'], parameters=body.get('parameters'),
                                          condition=body.get('condition'), target=body.get('target'))
                    identifier = uuid.uuid4().hex
                    result['result_id'] = identifier
                    filename = '计算结果-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + identifier + '.json'
                    results[identifier] = (result, filename)
                    while len(results) > 64:
                        results.pop(next(iter(results)))
                return self.respond(200, result)
            except (ValueError, TypeError, KeyError) as exc:
                return self.respond(400, {'error': str(exc)})
            except Exception as exc:
                return self.respond(500, {'error': f'本地计算未完成：{type(exc).__name__}: {exc}'})

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=18080)
    parser.add_argument('--query')
    parser.add_argument('--calculator-only', action='store_true', help='Explicitly disable dense retrieval and LLM; not full RAG')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    engine = Engine(root, dense=not args.calculator_only, llm=not args.calculator_only)
    if args.query:
        print(json.dumps(engine.query(args.query), ensure_ascii=False, indent=2, allow_nan=False))
    else:
        print(f'本地通信公式 RAG：http://127.0.0.1:{args.port}', flush=True)
        create_server(root, engine, args.port).serve_forever()


if __name__ == '__main__':
    main()
