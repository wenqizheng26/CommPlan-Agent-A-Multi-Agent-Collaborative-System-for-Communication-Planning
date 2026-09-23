"""Start existing local assets. This launcher never downloads or changes firewall rules."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parent


def model_command(root, cpu=False):
    root = Path(root)
    config = json.loads((root/'runtime_config.json').read_text(encoding='utf-8'))['generation']
    command = [str(root/config['executable']), '-m', str(root/config['path']),
               '--alias', config['alias'], '--host', '127.0.0.1', '--port', str(config['port']),
               '-c', str(config['context_size']), '-np', '1', '-ngl', '0' if cpu else str(config.get('gpu_layers',99)),
               '--offline', '--reasoning', 'off', '--no-webui', '-t', '6',
               '--cors-origins', 'http://127.0.0.1:18080', '--no-cors-credentials']
    if not cpu and config.get('device'):
        command.extend(['--device', config['device']])
    return command


def get_json(url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=3) as response:
            return json.load(response)
    except (urllib.error.URLError, OSError):
        return None


def spawn(command, name):
    (ROOT/'runtime').mkdir(exist_ok=True)
    with (ROOT/f'runtime/{name}.out.log').open('ab') as out, (ROOT/f'runtime/{name}.err.log').open('ab') as err:
        process = subprocess.Popen(command, cwd=str(ROOT), stdout=out, stderr=err,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    (ROOT/f'runtime/{name}.pid').write_text(str(process.pid))
    return process


def await_service(url, process, timeout=180):
    deadline = time.monotonic()+timeout
    while time.monotonic()<deadline:
        data = get_json(url)
        if data is not None:
            return data
        if process.poll() is not None:
            raise RuntimeError('服务提前退出，请查看 runtime 中对应的 err.log')
        time.sleep(1)
    raise RuntimeError('服务启动超时，请查看 runtime 中的日志')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cpu', action='store_true', help='Use CPU instead of the configured NVIDIA Vulkan device')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--model-only', action='store_true')
    args = parser.parse_args()
    config = json.loads((ROOT/'runtime_config.json').read_text(encoding='utf-8'))
    for value in (config['python'], config['generation']['executable'], config['generation']['path'], 'models/bge-small-zh-v1.5/model.safetensors'):
        if not (ROOT/value).is_file():
            raise RuntimeError(f'缺少本地资源：{value}。启动不会联网下载，请按README准备依赖。')
    model_url = f"http://127.0.0.1:{config['generation']['port']}"
    current = get_json(model_url+'/v1/models')
    if current is None:
        print('启动本地 Qwen 模型…', flush=True)
        process = spawn(model_command(ROOT, args.cpu), 'model')
        current = await_service(model_url+'/v1/models', process)
    if config['generation']['alias'] not in [x.get('id') for x in current.get('data', [])]:
        raise RuntimeError('模型端口由另一个服务占用，未复用该服务')
    print('本地模型已就绪。', flush=True)
    if args.model_only:
        return
    address = 'http://127.0.0.1:18080'
    status = get_json(address+'/api/status')
    if status is None:
        print('加载中文检索模型并启动应用…', flush=True)
        process = spawn([str(ROOT/config['python']), '-X', 'utf8', str(ROOT/'app.py')], 'app')
        status = await_service(address+'/api/status', process)
    if status.get('application') != 'signal-formula-rag' or not status.get('dense_enabled') or not status.get('llm_enabled'):
        raise RuntimeError('应用端口不是完整RAG服务，请先核对已有进程')
    print('已启动：'+address, flush=True)
    if not args.no_browser:
        webbrowser.open(address)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'启动未完成：{exc}', file=sys.stderr)
        raise SystemExit(1)
