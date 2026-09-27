"""Stop this machine's CommPlan workbench and local models; other programs are left alone."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import time
import urllib.error
import urllib.request

from planning.providers.registry import Registry

ROOT = Path(__file__).resolve().parent
PROFILE = 'confirmed-fspl-loop-v1'
DEFAULT_WORKBENCH_PORT = 18082
NO_WINDOW = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def read_json(url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=2) as response:
            return json.load(response)
    except (urllib.error.URLError, OSError, ValueError):
        return None


def listening(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=1):
            return True
    except OSError:
        return False


def run(command):
    return subprocess.run(command, capture_output=True, text=True, errors='replace', timeout=60,
                          creationflags=NO_WINDOW).stdout


def service_ports(root=None):
    """Model aliases by port from the registry, and every workbench port this folder has started."""
    root = root or ROOT
    registry = Registry(root)
    aliases = {}
    for model in registry.models.values():
        if model.get('runtime') == 'llama.cpp' and model.get('endpoint'):
            aliases.setdefault(int(model['endpoint'].rsplit(':', 1)[1]), set()).add(model['alias'])
    workbenches = {DEFAULT_WORKBENCH_PORT}
    for pid_file in (root / 'runtime').glob('commplan-web-*.pid'):
        port = pid_file.stem.rsplit('-', 1)[-1]
        if port.isdigit():
            workbenches.add(int(port))
    return aliases, workbenches


def listeners(ports):
    """Processes listening on these local TCP ports, from netstat (fast; no process-table scan)."""
    if not ports:
        return []
    found = set()
    for line in run(['netstat', '-ano', '-p', 'TCP']).splitlines():
        parts = line.split()
        if len(parts) != 5 or not parts[4].isdigit() or parts[2] not in {'0.0.0.0:0', '[::]:0'}:
            continue
        port = parts[1].rpartition(':')[2]
        if port.isdigit() and int(port) in ports:
            found.add((int(port), int(parts[4])))
    return [{'port': port, 'pid': pid} for port, pid in sorted(found)]


def command_line(pid):
    """Slow (PowerShell); only for a server that cannot answer HTTP yet, such as a loading model."""
    script = ('[Console]::OutputEncoding=[Text.Encoding]::UTF8;'
              f'(Get-CimInstance Win32_Process -Filter "ProcessId={int(pid)}").CommandLine')
    return run(['powershell', '-NoProfile', '-NonInteractive', '-Command', script])


def commplan_role(listener, aliases, workbenches):
    """'model' or 'workbench' when the listener is one of ours; None for any other program."""
    port = listener['port']
    if port in aliases:
        served = read_json(f'http://127.0.0.1:{port}/v1/models')
        if isinstance(served, dict) and any(isinstance(m, dict) and m.get('id') in aliases[port]
                                            for m in served.get('data', [])):
            return 'model'
    if port in workbenches:
        session = read_json(f'http://127.0.0.1:{port}/api/session')
        if isinstance(session, dict) and session.get('profile') == PROFILE:
            return 'workbench'
    if port in aliases or port in workbenches:
        # A model that is still loading answers no HTTP request; its command line says what it is.
        command = command_line(listener['pid'])
        if port in aliases and 'llama-server' in command and any(f'--alias {a}' in command for a in aliases[port]):
            return 'model'
        if port in workbenches and '-m planning.web_server' in command:
            return 'workbench'
    return None


def stop(pid):
    run(['taskkill', '/PID', str(pid), '/T', '/F'])


def wait_closed(port, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not listening(port):
            return True
        time.sleep(0.5)
    return False


def stop_workbench(port):
    """Stop the CommPlan workbench on this port. False if the port holds anything else."""
    found = listeners({port})
    if not found or any(commplan_role(item, {}, {port}) != 'workbench' for item in found):
        return False
    for item in found:
        stop(item['pid'])
    return wait_closed(port)


def forget(pid):
    """Drop PID files that point at a process we have just stopped."""
    for pid_file in (ROOT / 'runtime').glob('commplan-*.pid'):
        try:
            if pid_file.read_text(encoding='ascii').strip() == str(pid):
                pid_file.unlink()
        except OSError:
            pass


def main(argv=None):
    argparse.ArgumentParser(description='关闭本机的通信筹划工作台与本地模型（不影响其他程序）').parse_args(argv)
    aliases, workbenches = service_ports()
    found = listeners(set(aliases) | workbenches)
    failed = False
    for item in found:
        label = f"端口 {item['port']}（PID {item['pid']}）"
        role = commplan_role(item, aliases, workbenches)
        if role is None:
            print(f'{label}不是 CommPlan 服务，未处理。', flush=True)
            continue
        stop(item['pid'])
        if wait_closed(item['port']):
            forget(item['pid'])
            print(f"已关闭{'工作台' if role == 'workbench' else '本地模型'}：{label}", flush=True)
        else:
            failed = True
            print(f'{label}未能关闭，请在任务管理器中结束该进程。', flush=True)
    if not found:
        print('没有正在运行的 CommPlan 服务。', flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f'关闭未完成：{exc}')
        raise SystemExit(1)
