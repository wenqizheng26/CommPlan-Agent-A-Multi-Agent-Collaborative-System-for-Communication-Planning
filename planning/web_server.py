"""Local-only confirmation UI. The task service owns every state transition."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sqlite3
from urllib.parse import urlsplit
from planning.requirements_contract import strict_json
from planning.workflow.task_service import TaskService, identifier

MESSAGES={
    'STALE_REVISION':'任务输入已更新。请刷新查看当前版本，再重新核对。',
    'STALE_STATE_VERSION':'任务状态已变化。请刷新后操作，不能沿用旧确认。',
    'REVIEW_HASH_MISMATCH':'核对内容不匹配。请刷新并核对当前计划。',
    'KNOWLEDGE_CHANGED':'知识目录已变化。请重新提交需求，生成新计划后确认。',
    'NOT_CONFIRMABLE':'当前任务不能确认，请先解决缺项、冲突或模型缺口。',
    'TASK_NOT_FOUND':'未找到该任务，请检查任务编号或新建任务。',
    'IDEMPOTENCY_CONFLICT':'同一操作编号对应了不同内容，请刷新后重新操作。',
    'TASK_EXISTS':'该任务已存在，请恢复查看。',
    'FORBIDDEN':'请求来源或会话无效，请从本机页面重新打开。',
    'SERVER_ERROR':'本次操作未提交。可刷新核对状态后重试；请检查服务器终端。',
    'DATABASE_BUSY':'另一项操作正在处理，请稍后刷新重试。',
}


def create_server(root, db_path=None, port=18082):
    root=Path(root)
    service=TaskService(root,db_path or root/'outputs/planning.sqlite')
    try:
        service.activity.interrupt_open()
    except sqlite3.Error:
        pass
    token=secrets.token_urlsafe(32)
    assets={'/':('index.html','text/html'),'/app.js':('app.js','text/javascript'),
            '/text.mjs':('text.mjs','text/javascript'),'/flow.mjs':('flow.mjs','text/javascript'),
            '/details.mjs':('details.mjs','text/javascript'),'/conversation.mjs':('conversation.mjs','text/javascript'),
            '/roles.mjs':('roles.mjs','text/javascript'),
            '/app.css':('app.css','text/css')}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):
            pass

        def respond(self,status,data,kind='application/json'):
            payload=(json.dumps(data,ensure_ascii=False,allow_nan=False) if kind=='application/json' else data).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type',kind+'; charset=utf-8')
            self.send_header('Content-Length',str(len(payload)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
            self.wfile.write(payload)

        def error(self,status,code):
            self.respond(status,{'error':{'code':code,'message':MESSAGES.get(code,'请求格式或内容无效，请核对输入后重新提交。')}})

        def allowed(self,write=False):
            host=self.headers.get('Host','')
            valid={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
            origin=self.headers.get('Origin')
            if host not in valid or (origin is not None and origin!='http://'+host):
                self.error(403,'FORBIDDEN'); return False
            if write and not secrets.compare_digest(self.headers.get('X-Planning-Token',''),token):
                self.error(403,'FORBIDDEN'); return False
            return True

        def do_GET(self):
            if not self.allowed():
                return
            path=urlsplit(self.path).path
            if path in assets:
                name,kind=assets[path]
                self.respond(200,(root/'planning/web'/name).read_text(encoding='utf-8'),kind)
            elif path=='/api/session':
                self.respond(200,{'token':token,'profile':'confirmed-fspl-loop-v1'})
            elif path.startswith('/api/tasks/'):
                parts=path.strip('/').split('/')
                try:
                    if len(parts)==3:
                        self.respond(200,{'state':service.get(parts[2])})
                    elif len(parts)==4 and parts[3]=='history':
                        service.get(parts[2])
                        self.respond(200,{'history':service.history(parts[2])})
                    elif len(parts)==4 and parts[3]=='activity':
                        identifier(parts[2])
                        self.respond(200,{'events':service.activity.events(parts[2]),
                                         'available':service.activity.available,'authoritative':False})
                    else:
                        self.error(404,'NOT_FOUND')
                except ValueError as exc:
                    self.error(404 if str(exc)=='TASK_NOT_FOUND' else 400,str(exc))
            else:
                self.error(404,'NOT_FOUND')

        def do_POST(self):
            if not self.allowed(write=True):
                return
            if self.path!='/api/commands':
                self.error(404,'NOT_FOUND'); return
            if self.headers.get_content_type()!='application/json':
                self.error(400,'JSON_REQUIRED'); return
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=65536:
                    self.error(413,'REQUEST_SIZE'); return
                payload=strict_json(self.rfile.read(size).decode('utf-8'))
                result=service.apply(payload)
                self.respond(200,result)
            except (ValueError,TypeError,KeyError,OverflowError) as exc:
                code=str(exc) if isinstance(exc,ValueError) and not isinstance(exc,UnicodeError) else 'INVALID_REQUEST'
                status=409 if code in {'STALE_REVISION','STALE_STATE_VERSION','REVIEW_HASH_MISMATCH','KNOWLEDGE_CHANGED',
                    'TASK_EXISTS','NOT_CONFIRMABLE','NOT_CANCELLABLE','IDEMPOTENCY_CONFLICT','CHECKPOINT_STATE_MISMATCH'} else 400
                self.error(status,code)
            except sqlite3.OperationalError:
                self.error(503,'DATABASE_BUSY')
            except Exception as exc:
                print('planning command failed:',type(exc).__name__,flush=True)
                self.error(500,'SERVER_ERROR')

    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.daemon_threads=True
    return server


def main(argv=None):
    parser=argparse.ArgumentParser(description='本地通信筹划确认计算闭环')
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--db',type=Path)
    parser.add_argument('--port',type=int,default=18082)
    args=parser.parse_args(argv)
    server=create_server(args.root,args.db,args.port)
    print(f'通信筹划已启动：http://127.0.0.1:{server.server_port}  （Ctrl+C 停止，任务保存在本地）',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__=='__main__':
    main()
