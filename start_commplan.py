"""Start the planning workbench and optional local Qwen, without downloads."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
import webbrowser

from launch import model_command, model_paths, embedding_command
from planning.build_info import build_fingerprint
from planning.providers.registry import Registry
from stop_commplan import PROFILE, listening, read_json, stop_workbench

ROOT = Path(__file__).resolve().parent


def default_model():
    registry = Registry(ROOT)
    return registry.models[registry.defaults['chat']]


def chrome():
    """Chrome is the target browser; the system default is only a fallback."""
    for base in (os.environ.get('ProgramFiles'), os.environ.get('ProgramFiles(x86)'), os.environ.get('LOCALAPPDATA')):
        if base and (Path(base) / 'Google/Chrome/Application/chrome.exe').is_file():
            return Path(base) / 'Google/Chrome/Application/chrome.exe'
    return None


def open_browser(address):
    path = chrome()
    if path is not None:
        try:
            subprocess.Popen([str(path), address], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except OSError:
            pass
    return webbrowser.open(address)


def model_ready():
    model = default_model()
    base = model['endpoint'].rstrip('/')
    data = read_json(base + '/v1/models')
    health = read_json(base + '/health')
    return (isinstance(data, dict) and isinstance(health, dict)
            and health.get('status') == 'ok'
            and any(isinstance(item, dict) and item.get('id') == model['alias']
                    for item in data.get('data', [])))


def asset_root(explicit=None):
    model = default_model()
    configured = explicit or os.environ.get('COMMPLAN_ASSET_ROOT')
    candidates = [Path(configured)] if configured else [
        ROOT / 'models' / 'signal-formula-qwen3', ROOT,
        ROOT.parent / 'signal-formula-rag',
        ROOT.parent.parent / 'signal-formula-rag',
    ]
    for root in candidates:
        if model_paths(root, model):
            return root.resolve()
    raise RuntimeError('未找到默认模型权重和 llama-server。请用 --asset-root 指向资源目录，或使用 --without-model。')


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
    model = default_model()
    base = model['endpoint'].rstrip('/')
    port = int(base.rsplit(':', 1)[1])
    if model_ready():
        print('复用已就绪的本机 Qwen：' + base, flush=True)
        return
    if listening(port):
        raise RuntimeError(f'{port} 端口已占用，但未确认目标 Qwen 就绪；未重复启动或关闭已有服务。')
    root = asset_root(args.asset_root)
    print(f'启动本机 Qwen，资源目录：{root}', flush=True)
    process = spawn(model_command(root, args.cpu), 'commplan-model', root)
    wait_ready(model_ready, process, '本机 Qwen')
    print('本机 Qwen 已就绪。', flush=True)


def ensure_embedding(args):
    registry = Registry(ROOT)
    model = registry.models.get(registry.defaults.get('embedding'), {})
    if model.get('runtime') != 'llama.cpp':
        return
    from planning.services.model_status import probe_model
    base = model['endpoint'].rstrip('/')
    ready = lambda: probe_model(base, model['alias'])['status'] == 'ready'
    if ready():
        print('复用已就绪的本机向量模型：' + base, flush=True)
        return
    if listening(int(base.rsplit(':', 1)[1])):
        raise RuntimeError('向量端口已占用，但未确认目标模型；保留现有服务。')
    asset_root=args.asset_root or os.environ.get('COMMPLAN_ASSET_ROOT')
    roots = [Path(asset_root)] if asset_root else [ROOT, ROOT/'models/signal-formula-qwen3']
    for root in roots:
        if model_paths(root, model):
            process = spawn(embedding_command(root, registry_root=ROOT), 'commplan-embedding', root)
            wait_ready(ready, process, '向量模型')
            return
    print('向量模型未安装，文档检索将使用词项。', flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description='一键启动通信筹划工作台与本地模型（不下载资源）')
    parser.add_argument('--asset-root', type=Path, help='含模型与运行时的目录')
    parser.add_argument('--without-model', action='store_true', help='只启动工作台')
    parser.add_argument('--cpu', action='store_true', help='本次新启动的模型使用 CPU')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--port', type=int, default=18082)
    parser.add_argument('--db', type=Path, help='仅在新启动工作台时生效；不会更换已有服务的数据库')
    args = parser.parse_args(argv)
    model_port = int(default_model()['endpoint'].rsplit(':', 1)[1])
    embedding = Registry(ROOT)
    embedding = embedding.models.get(embedding.defaults.get('embedding'), {})
    embedding_port = int(embedding['endpoint'].rsplit(':',1)[1]) if embedding.get('endpoint') else None
    if not 1 <= args.port <= 65535 or args.port in (model_port, embedding_port):
        parser.error(f'工作台端口必须在 1–65535 之间，且不能占用模型端口 {model_port}。')
    address = f'http://127.0.0.1:{args.port}'

    def workbench_ready():
        data = read_json(address + '/api/session')
        return isinstance(data, dict) and data.get('profile') == PROFILE

    session = read_json(address + '/api/session')
    existing = isinstance(session, dict) and session.get('profile') == PROFILE
    if existing and session.get('build') != build_fingerprint(ROOT) or not existing and listening(args.port):
        # An older CommPlan build holds the port: replace it. Anything else there is left alone.
        if not stop_workbench(args.port):
            raise RuntimeError(f'{args.port} 端口已被其他程序占用，请使用 --port 指定其他端口。')
        print('已停止旧版工作台，启动当前版本。', flush=True)
        existing = False
    if existing and args.db is not None:
        raise RuntimeError('指定了 --db，但该端口已有工作台。请使用空闲的 --port 启动独立数据库。')
    if not args.without_model:
        try:
            ensure_model(args)
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            print(f'模型未就绪：{exc}\n将打开工作台，请使用“确定性”模式。', flush=True)
        try:
            ensure_embedding(args)
        except (OSError, ValueError, KeyError, RuntimeError) as exc:
            print(f'向量模型未就绪：{exc}\n检索将降为词项。', flush=True)
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
    print('页面默认使用确定性模式；模型就绪后可选择“本机 Qwen”。关闭本窗口后服务仍在后台运行，用“停止服务”关闭。', flush=True)
    if not args.no_browser and not open_browser(address):
        print('未能自动打开浏览器，请手动打开上述地址。', flush=True)
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f'启动未完成：{exc}', file=sys.stderr)
        raise SystemExit(1)
