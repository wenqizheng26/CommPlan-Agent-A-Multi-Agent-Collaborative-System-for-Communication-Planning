"""Local-only confirmation UI. The task service owns every state transition."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import sqlite3
import re
from urllib.parse import urlsplit, parse_qs
from formula_rag.catalog import load_catalog
from planning.requirements_contract import strict_json, digest
from planning.workflow.task_service import TaskService, identifier
from planning.services.model_status import probe_model, probe_registry
from planning.build_info import build_fingerprint

MESSAGES={
    'OPERATION_CANCELLED':'本次操作已停止并回滚；此前保存的版本保持有效。',
    'ANSWER_REPLACEMENT_CONFLICT':'替换后仍有冲突，请编辑当前描述，统一该参数。',
    'STALE_REVISION':'任务输入已更新。请刷新查看当前版本，再重新核对。',
    'STALE_STATE_VERSION':'任务状态已变化。请刷新后操作，不能沿用旧确认。',
    'REVIEW_HASH_MISMATCH':'核对内容不匹配。请刷新并核对当前计划。',
    'KNOWLEDGE_CHANGED':'知识目录已变化。请重新提交需求，生成新计划后确认。',
    'STALE_QUESTION':'问题已随任务版本变化，请刷新后回答。',
    'ANSWER_PARAMETER_REQUIRED':'请为该参数填写大于零的单值、区间或候选，并包含正确单位。',
    'ANSWER_STILL_AMBIGUOUS':'回答仍不明确，请填写单值、明确区间或离散候选及单位。',
    'INVALID_ANSWER_CHOICE':'请选择当前问题提供的选项。',
    'ANSWER_REQUIRES_EDIT':'请编辑当前任务描述以处理这项问题。',
    'NOT_CONFIRMABLE':'当前任务不能确认，请先解决缺项、冲突或模型缺口。',
    'TASK_NOT_FOUND':'未找到该任务，请检查任务编号或新建任务。',
    'IDEMPOTENCY_CONFLICT':'同一操作编号对应了不同内容，请刷新后重新操作。',
    'TASK_EXISTS':'该任务已存在，请恢复查看。',
    'FORBIDDEN':'请求来源或会话无效，请从本机页面重新打开。',
    'SERVER_ERROR':'本次操作未提交。可刷新核对状态后重试；请检查服务器终端。',
    'DATABASE_BUSY':'另一项操作正在处理，请稍后刷新重试。',
    'STALE_SETTINGS':'设置已被其他页面修改。已载入最新设置，请核对后再保存。',
    'SETTINGS_MODEL_NOT_STRUCTURED':'该模型不支持严格结构化输出，不能用于这个角色。',
    'SETTINGS_TOP_N':'送入模型的条数不能超过召回数。',
}


def create_server(root, db_path=None, port=18082):
    root=Path(root)
    service=TaskService(root,db_path or root/'outputs/planning.sqlite')
    try:
        service.activity.interrupt_open()
    except sqlite3.Error:
        pass
    token=secrets.token_urlsafe(32)
    build=build_fingerprint(root)
    assets={'/':('index.html','text/html'),'/app.js':('app.js','text/javascript'),
            '/text.mjs':('text.mjs','text/javascript'),'/flow.mjs':('flow.mjs','text/javascript'),
            '/details.mjs':('details.mjs','text/javascript'),'/m1.mjs':('m1.mjs','text/javascript'),'/conversation.mjs':('conversation.mjs','text/javascript'),
            '/roles.mjs':('roles.mjs','text/javascript'),
            '/model-status.mjs':('model-status.mjs','text/javascript'),
            '/drafts.mjs':('drafts.mjs','text/javascript'),
            '/progress.mjs':('progress.mjs','text/javascript'),
            '/settings.mjs':('settings.mjs','text/javascript'),
            '/timing.mjs':('timing.mjs','text/javascript'),
            '/questions.mjs':('questions.mjs','text/javascript'),'/values.mjs':('values.mjs','text/javascript'),
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
                self.respond(200,{'token':token,'profile':'confirmed-fspl-loop-v1','build':build})
            elif path=='/api/tasks':
                self.respond(200,{'tasks':service.store.recent()})
            elif path=='/api/model-status':
                self.respond(200,probe_model())
            elif path=='/api/models':
                embeddings={e:service.retrieval_for(e).describe()['embedding'] for e,m in service.registry.models.items()
                            if m['kind']=='embedding'}
                self.respond(200,dict(service.registry.describe(),status=probe_registry(service.registry),
                                      embeddings=embeddings,corpus=service.retrieval_for(None).describe()['corpus']))
            elif path=='/api/settings':
                self.respond(200,service.settings.get())
            elif path=='/api/metrics':
                self.respond(200,service.activity.metrics())
            elif path=='/api/facts':
                from planning.knowledge.facts import FactService
                self.respond(200,FactService(service.root).public_records())
            elif path=='/api/formula-cards':
                # Read-only registered cards. content_hash uses the same digest as task evidence,
                # so the page shows a formula only when it is the card the task actually used.
                ids=[i for i in parse_qs(urlsplit(self.path).query).get('ids',[''])[0].split(',') if i]
                if not ids or len(ids)>20 or not all(re.fullmatch(r'[a-z0-9_]{1,64}',i) for i in ids):
                    self.error(400,'INVALID_REQUEST');return
                try:
                    cards={c['id']:c for c in load_catalog(root)}
                except (OSError,ValueError):
                    self.error(500,'SERVER_ERROR');return
                self.respond(200,{'cards':[dict(cards[i],content_hash=digest(cards[i])) for i in ids if i in cards],
                                  'missing':[i for i in ids if i not in cards]})
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
            if self.path not in {'/api/commands','/api/cancel-operation','/api/settings'}:
                self.error(404,'NOT_FOUND'); return
            if self.headers.get_content_type()!='application/json':
                self.error(400,'JSON_REQUIRED'); return
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=65536:
                    # Drain a bounded local request body before closing so Windows
                    # does not reset the socket before the 413 can be delivered.
                    if 0<size<=1024*1024:
                        self.connection.settimeout(2)
                        try:
                            self.rfile.read(size)
                        except (OSError,TimeoutError):
                            pass
                    self.error(413,'REQUEST_SIZE'); return
                payload=strict_json(self.rfile.read(size).decode('utf-8'))
                if self.path=='/api/settings':
                    if type(payload) is not dict or set(payload)!={'settings','expected_version'}:
                        raise ValueError('INVALID_REQUEST')
                    result=service.update_settings(payload['settings'],payload['expected_version'])
                elif self.path=='/api/cancel-operation':
                    if type(payload) is not dict or set(payload)!={'task_id','event_id'}:
                        raise ValueError('INVALID_REQUEST')
                    result=service.cancel_operation(payload['task_id'],payload['event_id'])
                else:
                    result=service.apply(payload)
                self.respond(200,result)
            except (ValueError,TypeError,KeyError,OverflowError) as exc:
                code=str(exc) if isinstance(exc,ValueError) and not isinstance(exc,UnicodeError) else 'INVALID_REQUEST'
                status=409 if code in {'STALE_SETTINGS','STALE_REVISION','STALE_STATE_VERSION','REVIEW_HASH_MISMATCH','KNOWLEDGE_CHANGED',
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
