"""Start the planning workbench and optional local Qwen, without downloads."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

from launch import model_command
from planning.build_info import build_fingerprint

ROOT = Path(__file__).resolve().parent
MODEL_URL = 'http://127.0.0.1:18081'
MODEL_ALIAS = 'signal-formula-qwen3'


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


def model_ready():
    data = read_json(MODEL_URL + '/v1/models')
    health = read_json(MODEL_URL + '/health')
    return (isinstance(data, dict) and isinstance(health, dict)
            and health.get('status') == 'ok'
            and any(isinstance(item, dict) and item.get('id') == MODEL_ALIAS
                    for item in data.get('data', [])))


def asset_root(explicit=None):
    configured = explicit or os.environ.get('COMMPLAN_ASSET_ROOT')
    candidates = [Path(configured)] if configured else [
        ROOT / 'models' / 'signal-formula-qwen3', ROOT,
        ROOT.parent / 'signal-formula-rag',
        ROOT.parent.parent / 'signal-formula-rag',
    ]
    for root in candidates:
        config_path = root / 'runtime_config.json'
        if not config_path.is_file():
            continue
        config = json.loads(config_path.read_text(encoding='utf-8'))['generation']
        if config.get('port') != 18081 or config.get('alias') != MODEL_ALIAS:
            continue
        if all((root / config[key]).is_file() for key in ('path', 'executable')):
            return root.resolve()
    raise RuntimeError('未找到 Qwen 权重和 llama-server。请用 --asset-root 指向含 runtime_config.json 的资源目录，或使用 --without-model。')


def spawn(command, name, cwd):
    logs = ROOT / 'runtime'
    logs.mkdir(exist_ok=True)
    with (logs / (name + '.out.log')).open('ab') as out, (logs / (name + '.err.log')).open('ab') as err:
        process = subprocess.Popen(
            command, cwd=str(cwd), stdin=subprocess.DEVNULL, stdout=out, stderr=err,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0,
        )
    (logs / (name + '.pid')).write_text(str(process.pid), encoding='ascii')
    return process


def wait_ready(check, process, label, timeout=180):
    deadline = time.monotonic() + timeout
    next_update = time.monotonic() + 15
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f'{label}提前退出，请查看 runtime 中的 commplan-*.err.log。')
        if check():
            return
        if time.monotonic() >= next_update:
            print(f'仍在等待{label}就绪…', flush=True)
            next_update = time.monotonic() + 15
        time.sleep(1)
    # Only stop the child created by this launch, never an existing service.
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    raise RuntimeError(f'{label}启动超时，已停止本次启动的进程。请查看 runtime 中的日志。')


def ensure_model(args):
    if model_ready():
        print('复用已就绪的本机 Qwen：' + MODEL_URL, flush=True)
        return
    if listening(18081):
        raise RuntimeError('18081 端口已占用，但未确认目标 Qwen 就绪；未重复启动或关闭已有服务。')
    root = asset_root(args.asset_root)
    print(f'启动本机 Qwen，资源目录：{root}', flush=True)
    process = spawn(model_command(root, args.cpu), 'commplan-model', root)
    wait_ready(model_ready, process, '本机 Qwen')
    print('本机 Qwen 已就绪。', flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description='一键启动通信筹划工作台与本地模型（不下载资源）')
    parser.add_argument('--asset-root', type=Path, help='含 runtime_config.json、模型与运行时的目录')
    parser.add_argument('--without-model', action='store_true', help='只启动工作台')
    parser.add_argument('--cpu', action='store_true', help='本次新启动的模型使用 CPU')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, default=18082)
    parser.add_argument('--db', type=Path, help='仅在新启动工作台时生效；不会更换已有服务的数据库')
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535 or args.port == 18081:
        parser.error('工作台端口必须在 1–65535 之间，且不能占用模型端口 18081。')
    address = f'http://127.0.0.1:{args.port}'

    def workbench_ready():
        data = read_json(address + '/api/session')
        return isinstance(data, dict) and data.get('profile') == 'confirmed-fspl-loop-v1'

    existing = workbench_ready()
    if existing and read_json(address+'/api/session').get('build') != build_fingerprint(ROOT):
        raise RuntimeError('该端口运行的是旧版工作台。请停止旧工作台进程后重新启动，或用 --port 选择空闲端口；模型服务可继续复用。')
    if not existing and listening(args.port):
        raise RuntimeError(f'{args.port} 端口已被其他服务占用，请使用 --port 指定其他端口。')
    if existing and args.db is not None:
        raise RuntimeError('指定了 --db，但该端口已有工作台。请使用空闲的 --port 启动独立数据库。')
    if not args.without_model:
        try:
            ensure_model(args)
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            print(f'模型未就绪：{exc}\n将打开工作台，请使用“确定性”模式。', flush=True)
    else:
        print('仅启动工作台；不启动或关闭模型服务。', flush=True)
    if existing:
        print('复用已有工作台，沿用该服务的数据库。', flush=True)
    else:
        command = [sys.executable, '-B', '-X', 'utf8', '-m', 'planning.web_server', '--port', str(args.port)]
        if args.db is not None:
            command.extend(['--db', str(args.db.resolve())])
        print('启动通信筹划工作台…', flush=True)
        process = spawn(command, f'commplan-web-{args.port}', ROOT)
        wait_ready(workbench_ready, process, '工作台', timeout=60)
    print('工作台已就绪：' + address, flush=True)
    print('页面默认使用确定性模式；模型就绪后可选择“本机 Qwen”。后台服务在关闭本窗口后继续运行。', flush=True)
    if not args.no_browser and not webbrowser.open(address):
        print('未能自动打开浏览器，请手动打开上述地址。', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f'启动未完成：{exc}', file=sys.stderr)
        raise SystemExit(1)
