"""Start, check and stop one CommPlan instance that this tool created and can prove it owns.

The everyday start/stop scripts act on whatever CommPlan service answers on this machine's
ports. An independent install check needs the opposite: it may touch only the processes it
started itself. The record names each of them by PID, creation time, image and command line.
Every operation re-reads those through an open process handle (a PID cannot be reused while a
handle is open), requires the port's listening process to be that process or its direct child,
and requires the workbench to answer with this instance's id. Anything else is reported and
left running. Closing the workbench goes through its own endpoint, which needs the page token
and the instance secret from the record and waits for running commands instead of cutting them.

  python scripts/owned_instance.py start  --app-root A --python P --db D --record R --asset-root M
  python scripts/owned_instance.py status --record R
  python scripts/owned_instance.py stop   --record R
"""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

SCHEMA = 'commplan-owned-instance-v1'
PROFILE = 'confirmed-fspl-loop-v1'
SECRET_ENV = 'COMMPLAN_INSTANCE_SECRET'
DEFAULT_PORT = 18098
READY_S = {'chat': 300, 'embedding': 120, 'workbench': 60}
EXIT_S = 30
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


class Refused(Exception):
    """An operation this tool will not perform; the message says why."""


# --- Windows process handles ---------------------------------------------------------------

_kernel32 = ctypes.WinDLL('kernel32', use_last_error=True) if os.name == 'nt' else None
_ntdll = ctypes.WinDLL('ntdll') if os.name == 'nt' else None
PROCESS_TERMINATE = 0x0001
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0, WAIT_TIMEOUT = 0, 0x102
STATUS_INFO_LENGTH_MISMATCH = 0xC0000004
PROCESS_COMMAND_LINE_INFORMATION = 60
TH32CS_SNAPPROCESS = 0x2


class _UnicodeString(ctypes.Structure):
    _fields_ = [('Length', wintypes.USHORT), ('MaximumLength', wintypes.USHORT), ('Buffer', wintypes.LPWSTR)]


class _ProcessEntry(ctypes.Structure):
    _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD), ('th32ProcessID', wintypes.DWORD),
                ('th32DefaultHeapID', ctypes.c_void_p), ('th32ModuleID', wintypes.DWORD),
                ('cntThreads', wintypes.DWORD), ('th32ParentProcessID', wintypes.DWORD),
                ('pcPriClassBase', ctypes.c_long), ('dwFlags', wintypes.DWORD),
                ('szExeFile', wintypes.WCHAR * 260)]


if _kernel32 is not None:
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    _kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    _kernel32.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
    _kernel32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                     ctypes.POINTER(wintypes.DWORD))
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD
    _kernel32.WaitForSingleObject.argtypes = (wintypes.HANDLE, wintypes.DWORD)
    _kernel32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
    _kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    _kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    _kernel32.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_ProcessEntry))
    _kernel32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(_ProcessEntry))
    _ntdll.NtQueryInformationProcess.restype = ctypes.c_ulong
    _ntdll.NtQueryInformationProcess.argtypes = (wintypes.HANDLE, ctypes.c_ulong, ctypes.c_void_p,
                                                 ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong))


class Process:
    """An open handle; while it is open the PID names this process and no later one."""

    def __init__(self, pid):
        self.pid = int(pid)
        self.handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE | PROCESS_TERMINATE,
                                            False, self.pid)
        if not self.handle:
            raise OSError(ctypes.get_last_error(), f'cannot open process {self.pid}')

    def close(self):
        if self.handle:
            _kernel32.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def created(self):
        times = [wintypes.FILETIME() for _ in range(4)]
        if not _kernel32.GetProcessTimes(self.handle, *[ctypes.byref(t) for t in times]):
            raise ctypes.WinError(ctypes.get_last_error())
        return times[0].dwHighDateTime << 32 | times[0].dwLowDateTime

    def image(self):
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not _kernel32.QueryFullProcessImageNameW(self.handle, 0, buffer, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        return buffer.value

    def command_line(self):
        needed = ctypes.c_ulong(0)
        status = _ntdll.NtQueryInformationProcess(self.handle, PROCESS_COMMAND_LINE_INFORMATION, None, 0,
                                                  ctypes.byref(needed))
        if status != STATUS_INFO_LENGTH_MISMATCH or not needed.value:
            raise OSError(status, 'command line unavailable')
        buffer = ctypes.create_string_buffer(needed.value)
        status = _ntdll.NtQueryInformationProcess(self.handle, PROCESS_COMMAND_LINE_INFORMATION, buffer,
                                                  needed, ctypes.byref(needed))
        if status:
            raise OSError(status, 'command line unavailable')
        text = ctypes.cast(buffer, ctypes.POINTER(_UnicodeString)).contents
        return ctypes.wstring_at(text.Buffer, text.Length // 2)

    def alive(self):
        return _kernel32.WaitForSingleObject(self.handle, 0) == WAIT_TIMEOUT

    def wait(self, seconds):
        return _kernel32.WaitForSingleObject(self.handle, int(seconds * 1000)) == WAIT_OBJECT_0

    def terminate(self):
        # A process already exiting refuses a second TerminateProcess; that is not a failure.
        if self.alive() and not _kernel32.TerminateProcess(self.handle, 1):
            error = ctypes.get_last_error()
            if not self.wait(5):
                raise ctypes.WinError(error)

    def identity(self):
        return {'pid': self.pid, 'created': self.created(), 'image': self.image(), 'command_line': self.command_line()}


def parents():
    """PID -> parent PID for every process now (a parent PID alone may be stale; callers check times)."""
    snapshot = _kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot in (None, wintypes.HANDLE(-1).value):
        raise ctypes.WinError(ctypes.get_last_error())
    found = {}
    try:
        entry = _ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        more = _kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            found[entry.th32ProcessID] = entry.th32ParentProcessID
            more = _kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        _kernel32.CloseHandle(snapshot)
    return found


def listeners(port):
    """PIDs listening on this TCP port on any local address (IPv4 and IPv6)."""
    output = subprocess.run(['netstat', '-ano'], capture_output=True, text=True, errors='replace',
                            timeout=60, creationflags=NO_WINDOW).stdout
    found = set()
    for line in output.splitlines():
        parts = line.split()
        if (len(parts) == 5 and parts[0].upper() == 'TCP' and parts[2] in {'0.0.0.0:0', '[::]:0'}
                and parts[4].isdigit() and parts[1].rpartition(':')[2] == str(port)):
            found.add(int(parts[4]))
    return found


def port_open(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=1):
            return True
    except OSError:
        return False


# --- HTTP ------------------------------------------------------------------------------------

def http_json(url, *, data=None, headers=None, timeout=3):
    """(status, body) or (None, None) when nothing answers; never follows a proxy."""
    request = urllib.request.Request(url, data=data, headers=headers or {}, method='POST' if data is not None else 'GET')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            return exc.code, json.load(exc)
        except ValueError:
            return exc.code, None
    except (urllib.error.URLError, OSError, ValueError):
        return None, None


def model_answers(port, alias):
    _, health = http_json(f'http://127.0.0.1:{port}/health')
    _, models = http_json(f'http://127.0.0.1:{port}/v1/models')
    return (isinstance(health, dict) and health.get('status') == 'ok' and isinstance(models, dict)
            and any(isinstance(m, dict) and m.get('id') == alias for m in models.get('data', [])))


def instance_id(secret):
    return hashlib.sha256(secret.encode('utf-8')).hexdigest()


def workbench_session(port):
    _, session = http_json(f'http://127.0.0.1:{port}/api/session')
    return session if isinstance(session, dict) else None


def workbench_answers(record, port):
    session = workbench_session(port)
    return (session is not None and session.get('profile') == PROFILE and session.get('build') == record['build']
            and session.get('instance_id', session.get('instance')) == record['instance'])


def answers(record, row):
    if row['role'] == 'workbench':
        return workbench_answers(record, row['port'])
    return model_answers(row['port'], row['alias'])


# --- record ----------------------------------------------------------------------------------

def now():
    return datetime.now(timezone.utc).isoformat()


def save(path, record):
    record['updated_at'] = now()
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


def load(path):
    try:
        record = json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        raise Refused(f'record unreadable: {exc}') from exc
    if not isinstance(record, dict) or record.get('schema') != SCHEMA:
        raise Refused('not an owned-instance record')
    return record


# --- ownership -------------------------------------------------------------------------------

def same(process, saved):
    """True when this open process is the one the record saved (PID reuse gives other values)."""
    try:
        return process.identity() == {k: saved[k] for k in ('pid', 'created', 'image', 'command_line')}
    except OSError:
        return False


def open_saved(saved):
    """('exited', None), ('foreign', None) or ('ours', open Process) for a saved identity."""
    try:
        process = Process(saved['pid'])
    except OSError:
        return 'exited', None
    if not process.alive():
        process.close()
        return 'exited', None
    if not same(process, saved):
        process.close()
        return 'foreign', None
    return 'ours', process


def server_of(started, port):
    """The process listening on port, if it is the started process or its direct child (a venv
    python.exe runs the interpreter as a child). Returns its identity, or None while not listening."""
    pids = listeners(port)
    if not pids:
        return None
    if len(pids) != 1:
        raise Refused(f'port {port}: several listeners {sorted(pids)}')
    pid = pids.pop()
    if pid == started.pid:
        return started.identity()
    if parents().get(pid) != started.pid:
        raise Refused(f'port {port}: listener PID {pid} was not started by this instance')
    with Process(pid) as child:
        identity = child.identity()
        if identity['created'] < started.created() or parents().get(pid) != started.pid:
            raise Refused(f'port {port}: listener PID {pid} was not started by this instance')
        return identity


def open_service(row):
    """(state, launched, server) for a recorded service; the handles are open only when state is 'ours'."""
    if row.get('process') is None:
        return 'not-started', None, None
    state, launched = open_saved(row['process'])
    if state != 'ours':
        return state, None, None
    saved = row.get('server')
    if saved is None:
        return 'ours', launched, None
    if saved['pid'] == row['process']['pid']:
        return 'ours', launched, launched
    server_state, server = open_saved(saved)
    if server_state != 'ours':
        launched.close()
        return 'server-' + server_state, None, None
    return 'ours', launched, server


def close(*processes):
    for process in {id(p): p for p in processes if p is not None}.values():
        process.close()


def check(record, row):
    """Status of one recorded service; keeps no handle open."""
    state, launched, server = open_service(row)
    if state != 'ours':
        return state
    try:
        if server is None or listeners(row['port']) != {server.pid}:
            return 'port-mismatch'
        return 'running' if answers(record, row) else 'not-answering'
    finally:
        close(launched, server)


def status(record):
    services = {row['role']: check(record, row) for row in record['services']}
    states = set(services.values())
    overall = 'running' if states == {'running'} else 'stopped' if states <= {'exited'} else 'mismatch'
    return {'record_state': record['state'], 'state': overall, 'services': services}


# --- start -----------------------------------------------------------------------------------

def plan_from_app(args):
    """Commands for chat, embedding and workbench, from the app root's own registry and launcher."""
    app_root = args.app_root.resolve()
    if not (app_root / 'planning/web_server.py').is_file() or not (app_root / 'config/models.json').is_file():
        raise Refused(f'not a CommPlan app root: {app_root}')
    sys.path.insert(0, str(app_root))
    from launch import embedding_command, model_command
    from planning.build_info import build_fingerprint
    from planning.providers.registry import Registry
    registry = Registry(app_root)
    services = []
    if not args.without_model:
        if args.asset_root is None:
            raise Refused('--asset-root is required unless --without-model')
        asset_root = args.asset_root.resolve()
        chat = registry.models[args.chat_model or registry.defaults['chat']]
        services.append({'role': 'chat', 'alias': chat['alias'], 'port': int(chat['endpoint'].rsplit(':', 1)[1]),
                         'command': model_command(asset_root, args.cpu, registry_root=app_root, model_id=chat['id']),
                         'cwd': str(asset_root)})
        if not args.without_embedding:
            embedding = registry.models[registry.defaults['embedding']]
            services.append({'role': 'embedding', 'alias': embedding['alias'],
                             'port': int(embedding['endpoint'].rsplit(':', 1)[1]),
                             'command': embedding_command(asset_root, registry_root=app_root),
                             'cwd': str(asset_root)})
    python = args.python.resolve()
    db = args.db.resolve()
    services.append({'role': 'workbench', 'alias': None, 'port': args.port,
                     'command': [str(python), '-B', '-X', 'utf8', '-m', 'planning.web_server',
                                 '--root', str(app_root), '--db', str(db), '--port', str(args.port)],
                     'cwd': str(app_root)})
    return {'app_root': str(app_root), 'python': str(python), 'db': str(db),
            'asset_root': None if args.without_model else str(args.asset_root.resolve()),
            'build': build_fingerprint(app_root), 'services': services}


def preflight(record_path, plan):
    if record_path.exists() or record_path.with_name(record_path.name + '.tmp').exists():
        raise Refused(f'record already exists: {record_path} (use a new record path)')
    if not record_path.parent.is_dir():
        raise Refused(f'record folder missing: {record_path.parent}')
    if not Path(plan['python']).is_file():
        raise Refused(f'python missing: {plan["python"]}')
    if not Path(plan['db']).parent.is_dir():
        raise Refused(f'database folder missing: {Path(plan["db"]).parent}')
    ports = [row['port'] for row in plan['services']]
    if len(set(ports)) != len(ports) or not all(1 <= port <= 65535 for port in ports):
        raise Refused(f'ports must be distinct and valid: {ports}')
    busy = [port for port in ports if listeners(port) or port_open(port)]
    if busy:
        raise Refused(f'ports in use, nothing started: {busy}')


def spawn(row, log, env):
    with log.open('ab') as out:
        child = subprocess.Popen(row['command'], cwd=row['cwd'], env=env, stdin=subprocess.DEVNULL,
                                 stdout=out, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
    # Popen keeps its own handle open, so this PID is still this child while it is read.
    process = Process(child.pid)
    identity = process.identity()
    if identity['command_line'] != subprocess.list2cmdline(row['command']):
        process.terminate()
        process.close()
        raise Refused(f'{row["role"]}: started process does not show the command it was given')
    return child, process, identity


def wait_ready(record, row, child, process, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise Refused(f'{row["role"]} exited early with {child.returncode}; see {row["log"]}')
        server = server_of(process, row['port'])
        if server is not None and answers(record, row):
            # Listener and answer agree only if the answer came from our listener.
            if listeners(row['port']) == {server['pid']}:
                return server
        time.sleep(1)
    raise Refused(f'{row["role"]} not ready within {seconds}s; see {row["log"]}')


def start(record_path, plan, *, ready=READY_S):
    record_path = Path(record_path).resolve()
    preflight(record_path, plan)
    secret = secrets.token_urlsafe(32)
    record = {'schema': SCHEMA, 'state': 'starting', 'started_at': now(), 'secret': secret,
              'instance': instance_id(secret), 'app_root': plan['app_root'], 'python': plan['python'],
              'db': plan['db'], 'asset_root': plan.get('asset_root'), 'build': plan['build'],
              'workbench': None, 'services': []}
    # Exclusive create: two starts on one record cannot both proceed.
    with record_path.open('x', encoding='utf-8') as handle:
        handle.write(json.dumps(record, ensure_ascii=False, indent=2) + '\n')
    started = []
    try:
        for planned in plan['services']:
            row = {'role': planned['role'], 'alias': planned['alias'], 'port': planned['port'],
                   'log': str(record_path.with_name(f'{record_path.stem}-{planned["role"]}.log')),
                   'process': None, 'server': None}
            env = dict(os.environ)
            env.pop(SECRET_ENV, None)
            if row['role'] == 'workbench':
                env[SECRET_ENV] = secret
            child, process, row['process'] = spawn(planned, Path(row['log']), env)
            started.append((child, process))
            record['services'].append(row)
            save(record_path, record)
            row['server'] = wait_ready(record, row, child, process, ready[row['role']])
            if row['role'] == 'workbench':
                record['workbench'] = f'http://127.0.0.1:{row["port"]}'
            save(record_path, record)
        record['state'] = 'running'
        save(record_path, record)
        return record
    except BaseException as exc:
        # Only what this call started, through the handles it holds.
        for child, process in reversed(started):
            try:
                process.terminate()
                process.wait(EXIT_S)
            except OSError:
                pass
            process.close()
            if child.poll() is None:
                child.kill()
        record['state'] = 'failed'
        record['error'] = str(exc) or type(exc).__name__
        save(record_path, record)
        raise
    finally:
        for _, process in started:
            process.close()


# --- stop ------------------------------------------------------------------------------------

def stop_workbench(record, row, launched, server, deadline):
    """Ask our workbench to close after its running commands; True once its processes exited."""
    port = row['port']
    while True:
        if listeners(port) != {server.pid}:
            raise Refused(f'workbench port {port} is not held by its recorded process')
        session = workbench_session(port)
        if session is None or session.get('instance_id', session.get('instance')) != record['instance']:
            raise Refused('workbench does not answer with this instance id')
        code, body = http_json(f'http://127.0.0.1:{port}/api/instance/shutdown', data=b'', timeout=60,
                               headers={'X-Planning-Token': session.get('token', ''),
                                        'X-Instance-Secret': record['secret'], 'Content-Type': 'application/json'})
        if code == 200:
            break
        error = (body or {}).get('error', {}).get('code') if isinstance(body, dict) else None
        if code == 409 and error in {'INSTANCE_BUSY', 'INSTANCE_STOPPING'} and time.monotonic() < deadline:
            time.sleep(2)
            continue
        raise Refused(f'workbench did not accept the close request: {code} {error}')
    return server.wait(EXIT_S) and launched.wait(EXIT_S)


def stop(record_path, *, drain_s=600):
    record_path = Path(record_path).resolve()
    record = load(record_path)
    outcome = {}
    deadline = time.monotonic() + drain_s
    # The workbench first: once it is gone no command is still using the models.
    for row in sorted(record['services'], key=lambda r: r['role'] != 'workbench'):
        state, launched, server = open_service(row)
        if state != 'ours':
            outcome[row['role']] = state
            continue
        try:
            if server is None:
                raise Refused(f'{row["role"]} never reached its recorded listening process')
            if row['role'] == 'workbench':
                done = stop_workbench(record, row, launched, server, deadline)
            else:
                # A model server holds no task state: end the verified processes directly.
                for process in {id(p): p for p in (server, launched)}.values():
                    process.terminate()
                done = server.wait(EXIT_S) and launched.wait(EXIT_S)
            outcome[row['role']] = 'stopped' if done else 'still-running'
        except Refused as exc:
            outcome[row['role']] = f'refused: {exc}'
        finally:
            close(launched, server)
        if row['role'] == 'workbench' and outcome['workbench'] != 'stopped':
            # Never take the models away from a workbench that may still be running.
            for other in record['services']:
                outcome.setdefault(other['role'], 'left-running')
            break
    record['state'] = ('stopped' if all(v in {'stopped', 'exited', 'not-started'} for v in outcome.values())
                       else 'stop-incomplete')
    record['stop'] = {'at': now(), 'services': outcome}
    save(record_path, record)
    return record


# --- command line ----------------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description='只启动、核对、关闭本工具亲自启动的 CommPlan 实例')
    commands = parser.add_subparsers(dest='action', required=True)
    begin = commands.add_parser('start')
    begin.add_argument('--app-root', type=Path, required=True)
    begin.add_argument('--python', type=Path, required=True)
    begin.add_argument('--db', type=Path, required=True)
    begin.add_argument('--record', type=Path, required=True)
    begin.add_argument('--asset-root', type=Path)
    begin.add_argument('--port', type=int, default=DEFAULT_PORT)
    begin.add_argument('--chat-model')
    begin.add_argument('--cpu', action='store_true')
    begin.add_argument('--without-model', action='store_true')
    begin.add_argument('--without-embedding', action='store_true')
    for name in ('status', 'stop'):
        sub = commands.add_parser(name)
        sub.add_argument('--record', type=Path, required=True)
    commands.choices['stop'].add_argument('--drain-seconds', type=float, default=600)
    args = parser.parse_args(argv)
    if os.name != 'nt':
        print('owned_instance: Windows only', file=sys.stderr)
        return 2
    try:
        if args.action == 'start':
            record = start(args.record, plan_from_app(args))
            print(json.dumps({'state': record['state'], 'workbench': record['workbench'],
                              'services': {r['role']: r['server']['pid'] for r in record['services']}},
                             ensure_ascii=False))
            return 0
        if args.action == 'status':
            result = status(load(args.record))
            print(json.dumps(result, ensure_ascii=False))
            return {'running': 0, 'stopped': 3}.get(result['state'], 4)
        record = stop(args.record, drain_s=args.drain_seconds)
        print(json.dumps(record['stop'], ensure_ascii=False))
        return 0 if record['state'] == 'stopped' else 4
    except Refused as exc:
        print(f'owned_instance refused: {exc}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
