"""Local-only confirmation UI. The task service owns every state transition."""
import argparse
from contextlib import contextmanager, nullcontext
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import os
import secrets
import sqlite3
import re
import threading
import time
from urllib.parse import urlsplit, parse_qs
from formula_rag.catalog import load_catalog
from planning.requirements_contract import strict_json, digest
from planning.workflow.task_service import TaskService, identifier
from planning.services.model_status import probe_model, probe_registry
from planning.services.model_switch import Gate, ModelSwitcher
from planning.build_info import build_fingerprint
from planning.instance_info import instance_info, label

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
    'SETTINGS_UNKNOWN_MODEL':'模型未登记。',
    'MODEL_SWITCHING':'正在切换模型，完成后再提交。',
    'MODEL_SWITCH_BUSY':'正在处理任务，完成后才能切换模型。',
    'MODEL_SWITCH_RUNNING':'已有一次模型切换在进行。',
    'MODEL_NOT_INSTALLED':'本机没有该模型的权重，不能切换。',
    'MODEL_SWITCH_DISABLED':'这个工作台由独立实例工具管理，不在页面里切换模型。',
    'INSTANCE_STOPPING':'工作台正在关闭，本次操作未提交。',
    'INSTANCE_BUSY':'仍有操作在处理，工作台暂不关闭。',
    'DOCUMENT_FORMAT':'只支持 PDF、Word（docx）、Excel（xlsx、xls）、PowerPoint（pptx）、HTML、Markdown 和纯文本文件。',
    'DOCUMENT_SIZE':'文件为空或超过 20 MB。',
    'DOCUMENT_NAME':'文件名无效。',
    'DOCUMENT_EXISTS':'这份文件已经在资料库里。',
    'DOCUMENT_CONVERTER_MISSING':'缺少文档转换组件。请在项目环境中安装 requirements-docs.txt。',
    'DOCUMENT_UNREADABLE':'文件无法读取，可能已损坏或加密。',
    'DOCUMENT_PDF_UNREADABLE':'PDF 无法读取，可能已损坏或加密。',
    'DOCUMENT_EMPTY':'文件里没有可读取的文字；扫描件需要先做文字识别。',
    'DOCUMENT_NOT_FOUND':'资料库里没有这份文档。',
    'DOCUMENT_BUILTIN':'内置文档不能删除，可以停用。',
    'CARD_BUILTIN':'内置公式卡不能删除，可以停用。',
    'CARD_NOT_FOUND':'公式库里没有这张卡。',
    'EXTRACTION_CHUNKS':'请选择 1–6 个片段。',
    'EXTRACTION_ONE_DOCUMENT':'一次只能从同一份文档抽取。',
    'DRAFT_KIND':'请选择站点、设备或公式。',
    'DRAFT_ID':'草稿不存在。',
    'DRAFT_CHANGED':'草稿文件已被改动，不能审核。',
    'DRAFT_STALE_REVIEW':'草稿内容已变化，请刷新后再审核。',
    'DRAFT_NOT_APPROVABLE':'草稿未通过核对，不能入库：',
    'DRAFT_ALREADY_REVIEWED':'这份草稿已经审核过。',
    'DRAFT_REVIEWER':'请填写审核人（不超过 40 字）。',
    'DRAFT_REASON':'驳回时请写明原因（不超过 500 字）。',
}
# These codes carry a detail after ': ' that the page shows.
DETAILED={'DRAFT_NOT_APPROVABLE'}
# An owned instance (scripts/owned_instance.py) passes its secret here; it is never on the command line.
INSTANCE_SECRET_ENV='COMMPLAN_INSTANCE_SECRET'
DRAIN_S=20


class Writes:
    """In-flight POST requests. Closing an owned instance waits for them; it never interrupts one."""

    def __init__(self):
        self._cond=threading.Condition()
        self.running=0
        self.stopping=False

    @contextmanager
    def hold(self):
        with self._cond:
            admitted=not self.stopping
            self.running+=admitted
        try:
            yield admitted
        finally:
            if admitted:
                with self._cond:
                    self.running-=1
                    self._cond.notify_all()

    def drain(self,seconds):
        """Refuse new writes, then wait for the running ones; on timeout admit writes again."""
        with self._cond:
            if self.stopping:
                raise ValueError('INSTANCE_STOPPING')
            self.stopping=True
            if self._cond.wait_for(lambda:self.running==0,timeout=seconds):
                return
            self.stopping=False
        raise ValueError('INSTANCE_BUSY')


def instance_id(secret):
    return hashlib.sha256(secret.encode('utf-8')).hexdigest()


def create_server(root, db_path=None, port=18082, instance_secret=None):
    root=Path(root)
    service=TaskService(root,db_path or root/'outputs/planning.sqlite')
    try:
        service.activity.interrupt_open()
    except sqlite3.Error:
        pass
    token=secrets.token_urlsafe(32)
    build=build_fingerprint(root)
    gate=Gate()
    switcher=ModelSwitcher(service,gate)
    writes=Writes()
    session={'token':token,'profile':'confirmed-fspl-loop-v1','build':build,'instance':instance_info(root)}
    if instance_secret is not None:
        session['instance_id']=instance_id(instance_secret)
    assets={'/':('index.html','text/html'),'/app.js':('app.js','text/javascript'),
            '/text.mjs':('text.mjs','text/javascript'),'/flow.mjs':('flow.mjs','text/javascript'),
            '/details.mjs':('details.mjs','text/javascript'),'/m1.mjs':('m1.mjs','text/javascript'),'/conversation.mjs':('conversation.mjs','text/javascript'),
            '/roles.mjs':('roles.mjs','text/javascript'),
            '/model-status.mjs':('model-status.mjs','text/javascript'),
            '/drafts.mjs':('drafts.mjs','text/javascript'),
            '/progress.mjs':('progress.mjs','text/javascript'),
            '/settings.mjs':('settings.mjs','text/javascript'),
            '/timing.mjs':('timing.mjs','text/javascript'),'/marquee.mjs':('marquee.mjs','text/javascript'),
            '/library.mjs':('library.mjs','text/javascript'),'/compare.mjs':('compare.mjs','text/javascript'),
            '/questions.mjs':('questions.mjs','text/javascript'),'/values.mjs':('values.mjs','text/javascript'),
            '/records.mjs':('records.mjs','text/javascript'),'/report.mjs':('report.mjs','text/javascript'),
            '/i18n.mjs':('i18n.mjs','text/javascript'),'/i18n-en.mjs':('i18n-en.mjs','text/javascript'),
            '/lang.js':('lang.js','text/javascript'),'/app.css':('app.css','text/css')}

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
            base,_,detail=code.partition(': ')
            message=MESSAGES.get(code) or MESSAGES.get(base,'请求格式或内容无效，请核对输入后重新提交。')
            if base in DETAILED and detail:
                message+=detail
            self.respond(status,{'error':{'code':code,'message':message}})

        def reject(self,status,code,limit=1024*1024,seconds=2):
            # A POST answered before its body is read: take a bounded body first, otherwise
            # Windows may abort the connection before the client reads this answer.
            if self.command=='POST':
                try:
                    size=int(self.headers.get('Content-Length','0'))
                except ValueError:
                    size=-1
                self.drain(size,limit,seconds)
            self.error(status,code)

        def allowed(self,write=False):
            host=self.headers.get('Host','')
            valid={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
            origin=self.headers.get('Origin')
            if host not in valid or (origin is not None and origin!='http://'+host):
                self.reject(403,'FORBIDDEN'); return False
            if write and not secrets.compare_digest(self.headers.get('X-Planning-Token',''),token):
                self.reject(403,'FORBIDDEN'); return False
            return True

        def do_GET(self):
            if not self.allowed():
                return
            path=urlsplit(self.path).path
            if path in assets:
                name,kind=assets[path]
                self.respond(200,(root/'planning/web'/name).read_text(encoding='utf-8'),kind)
            elif path=='/api/session':
                self.respond(200,session)
            elif path=='/api/tasks':
                self.respond(200,{'tasks':service.store.recent()})
            elif path=='/api/model-status':
                model=service.registry.models[service.settings.get()['settings']['chat']['default']]
                self.respond(200,probe_model(model['endpoint'].rstrip('/'),model['alias']))
            elif path=='/api/model-switch':
                self.respond(200,switcher.status())
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
            elif path=='/api/tools':
                from formula_rag.registry import load_tools
                self.respond(200,{'tools':load_tools(service.root)})
            elif path=='/api/documents' or path.startswith('/api/documents/') or path=='/api/drafts':
                self.knowledge(path)
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
            elif path=='/api/formula-library':
                from planning.knowledge.library import cards
                try:
                    self.respond(200,{'cards':cards(root)})
                except (OSError,ValueError):
                    self.error(500,'SERVER_ERROR')
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
                    elif len(parts)==4 and parts[3]=='model-calls':
                        identifier(parts[2])
                        run_id=parse_qs(urlsplit(self.path).query,keep_blank_values=True).get('run_id',[None])[0]
                        if run_id is not None:
                            identifier(run_id)
                        self.respond(200,{'calls':service.model_calls.calls(parts[2],run_id=run_id),'file':service.model_calls.path.name})
                    else:
                        self.error(404,'NOT_FOUND')
                except ValueError as exc:
                    self.error(404 if str(exc)=='TASK_NOT_FOUND' else 400,str(exc))
            else:
                self.error(404,'NOT_FOUND')

        def knowledge(self,path):
            """Documents, their sections and the extraction drafts (the 资料 page)."""
            from planning.knowledge import sources
            from planning.knowledge.drafts import DraftStore
            try:
                if path=='/api/documents':
                    self.respond(200,sources.describe(root))
                elif path=='/api/drafts':
                    self.respond(200,{'drafts':DraftStore(root).views()})
                else:
                    self.respond(200,{'sections':sources.sections(root,path[len('/api/documents/'):])})
            except ValueError as exc:
                self.error(404 if str(exc)=='DOCUMENT_NOT_FOUND' else 400,str(exc))
            except Exception as exc:
                print('knowledge request failed:',type(exc).__name__,flush=True)
                self.error(500,'SERVER_ERROR')

        def drain(self,size,limit,seconds=5):
            # Read a bounded rejected body so Windows delivers the error instead of a reset.
            # One deadline covers the whole body, so a slow sender cannot hold the request.
            if not 0<size<=limit:
                return
            previous=self.connection.gettimeout()
            deadline=time.monotonic()+seconds
            try:
                while size>0:
                    left=deadline-time.monotonic()
                    if left<=0:
                        break
                    self.connection.settimeout(left)
                    chunk=self.rfile.read1(min(size,65536))
                    if not chunk:
                        break
                    size-=len(chunk)
            except (OSError,TimeoutError):
                pass
            finally:
                self.connection.settimeout(previous)

        def upload(self,query):
            from planning.knowledge.sources import add_document, describe, MAX_BYTES
            try:
                size=int(self.headers.get('Content-Length','0'))
            except ValueError:
                size=-1
            if self.headers.get_content_type()!='application/octet-stream':
                self.drain(size,MAX_BYTES); self.error(400,'INVALID_REQUEST'); return
            if not 0<size<=MAX_BYTES:
                self.drain(size,3*MAX_BYTES); self.error(413,'DOCUMENT_SIZE'); return
            data=self.rfile.read(size)
            try:
                record=add_document(root,query.get('name',[''])[0],data,query.get('title',[''])[0])
                self.respond(200,{'document':record,'library':describe(root)})
            except ImportError:
                self.error(400,'DOCUMENT_CONVERTER_MISSING')
            except ValueError as exc:
                self.error(409 if str(exc)=='DOCUMENT_EXISTS' else 400,str(exc))
            except Exception as exc:
                print('document upload failed:',type(exc).__name__,flush=True)
                self.error(500,'SERVER_ERROR')

        def draft_command(self,payload):
            from planning.knowledge.drafts import DraftStore
            if self.path=='/api/drafts/extract':
                if type(payload) is not dict or set(payload)!={'kind','chunk_ids'}:
                    raise ValueError('INVALID_REQUEST')
                from planning.agents.extraction import extract
                from planning.agents.role_model import LocalRoleSelector
                binding=service.settings.bindings(service.settings.get()['settings'])['requirements']
                return extract(root,payload['kind'],payload['chunk_ids'],LocalRoleSelector(binding))
            if type(payload) is not dict or set(payload)!={'id','decision','reviewer','reason','content_hash'}:
                raise ValueError('INVALID_REQUEST')
            return {'draft':DraftStore(root).review(payload['id'],payload['reviewer'],payload['content_hash'],
                                                    payload['decision'],payload['reason'])}

        def library_command(self,payload):
            from planning.knowledge import sources, library
            document = self.path.startswith('/api/documents/')
            switching = self.path.endswith('/switch')
            key = 'doc_id' if document else 'id'
            if type(payload) is not dict or set(payload) != ({key,'enabled'} if switching else {key}):
                raise ValueError('INVALID_REQUEST')
            if switching and type(payload['enabled']) is not bool:
                raise ValueError('INVALID_REQUEST')
            operation = (sources.switch_document if switching else sources.delete_document) if document else (
                library.switch_card if switching else library.delete_card)
            operation(root,payload[key],*([payload['enabled']] if switching else []))
            service.refresh_knowledge()
            return {'library':sources.describe(root)} if document else {'cards':library.cards(root)}

        def stop_instance(self):
            # Only an owned instance has this: page token and the secret from its record, no body.
            if instance_secret is None:
                self.reject(404,'NOT_FOUND'); return
            if not secrets.compare_digest(self.headers.get('X-Instance-Secret',''),instance_secret):
                self.reject(403,'FORBIDDEN'); return
            if self.headers.get('Content-Length','0')!='0':
                self.reject(400,'INVALID_REQUEST'); return
            try:
                writes.drain(DRAIN_S)
            except ValueError as exc:
                self.error(409,str(exc)); return
            self.respond(200,{'stopping':True})
            threading.Thread(target=self.server.shutdown,daemon=True).start()

        def do_POST(self):
            if not self.allowed(write=True):
                return
            if self.path=='/api/instance/shutdown':
                self.stop_instance(); return
            if self.path=='/api/cancel-operation':
                # Cancelling only rolls back, and is how a long command ends while a close waits.
                self.post(); return
            with writes.hold() as admitted:
                if not admitted:
                    self.reject(409,'INSTANCE_STOPPING'); return
                self.post()

        def post(self):
            if urlsplit(self.path).path=='/api/documents':
                try:
                    with gate.command(), service.store.transaction():
                        self.upload(parse_qs(urlsplit(self.path).query))
                        service.refresh_knowledge()
                except ValueError as exc:
                    self.reject(409,str(exc))
                except sqlite3.OperationalError:
                    self.reject(503,'DATABASE_BUSY')
                return
            library_paths={'/api/documents/switch','/api/documents/delete','/api/formula-cards/switch','/api/formula-cards/delete'}
            if self.path not in {'/api/commands','/api/cancel-operation','/api/settings','/api/drafts/extract','/api/drafts/review','/api/model-switch',*library_paths}:
                self.reject(404,'NOT_FOUND'); return
            if self.headers.get_content_type()!='application/json':
                self.reject(400,'JSON_REQUIRED'); return
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=65536:
                    self.reject(413,'REQUEST_SIZE'); return
                payload=strict_json(self.rfile.read(size).decode('utf-8'))
                if self.path=='/api/settings':
                    if type(payload) is not dict or set(payload)!={'settings','expected_version'}:
                        raise ValueError('INVALID_REQUEST')
                    result=service.update_settings(payload['settings'],payload['expected_version'])
                elif self.path=='/api/cancel-operation':
                    if type(payload) is not dict or set(payload)!={'task_id','event_id'}:
                        raise ValueError('INVALID_REQUEST')
                    result=service.cancel_operation(payload['task_id'],payload['event_id'])
                elif self.path=='/api/model-switch':
                    if type(payload) is not dict or set(payload)!={'model_id'}:
                        raise ValueError('INVALID_REQUEST')
                    # An owned instance runs only the models its tool started and verifies.
                    if instance_secret is not None:
                        raise ValueError('MODEL_SWITCH_DISABLED')
                    result=switcher.start(payload['model_id'])
                elif self.path in library_paths:
                    with gate.command(), service.store.transaction():
                        result=self.library_command(payload)
                elif self.path.startswith('/api/drafts/'):
                    # Extraction calls the model: it and a model switch exclude each other.
                    with gate.command(), service.store.transaction():
                        result=self.draft_command(payload)
                        service.refresh_knowledge()
                else:
                    with nullcontext() if type(payload) is dict and payload.get('action')=='cancel' else gate.command():
                        result=service.apply(payload)
                self.respond(200,result)
            except (ValueError,TypeError,KeyError,OverflowError) as exc:
                code=str(exc) if isinstance(exc,ValueError) and not isinstance(exc,UnicodeError) else 'INVALID_REQUEST'
                status=409 if code in {'STALE_SETTINGS','STALE_REVISION','STALE_STATE_VERSION','REVIEW_HASH_MISMATCH','KNOWLEDGE_CHANGED',
                    'TASK_EXISTS','NOT_CONFIRMABLE','NOT_CANCELLABLE','IDEMPOTENCY_CONFLICT','CHECKPOINT_STATE_MISMATCH',
                    'DOCUMENT_BUILTIN','CARD_BUILTIN','DRAFT_STALE_REVIEW','DRAFT_ALREADY_REVIEWED','MODEL_SWITCHING','MODEL_SWITCH_BUSY','MODEL_SWITCH_RUNNING','MODEL_SWITCH_DISABLED'} or code.startswith('DRAFT_NOT_APPROVABLE') else 404 if code in {'DOCUMENT_NOT_FOUND','CARD_NOT_FOUND'} else 400
                self.error(status,code)
            except sqlite3.OperationalError:
                self.error(503,'DATABASE_BUSY')
            except Exception as exc:
                print('planning command failed:',type(exc).__name__,flush=True)
                self.error(500,'SERVER_ERROR')

    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.daemon_threads=True
    server.instance_info=session['instance']
    return server


def main(argv=None):
    parser=argparse.ArgumentParser(description='本地通信筹划确认计算闭环')
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--db',type=Path)
    parser.add_argument('--port',type=int,default=18082)
    args=parser.parse_args(argv)
    server=create_server(args.root,args.db,args.port,os.environ.pop(INSTANCE_SECRET_ENV,None) or None)
    print('CommPlan 工作台 · '+label(server.instance_info),flush=True)
    print(f'通信筹划已启动：http://127.0.0.1:{server.server_port}  （Ctrl+C 停止，任务保存在本地）',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__=='__main__':
    main()
