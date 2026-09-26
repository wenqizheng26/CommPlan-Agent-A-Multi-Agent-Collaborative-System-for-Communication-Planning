"""Build an offline llama.cpp command from the default chat registry entry."""
from pathlib import Path
from urllib.parse import urlparse

from planning.providers.registry import Registry


RUNTIME = Path('runtime/llama.cpp-b10950/llama-server.exe')


def model_paths(asset_root, model):
    """Resolve the registry weight inside a local asset package or project root."""
    asset_root = Path(asset_root)
    weight = Path(model['weights'])
    marker = ('models', 'signal-formula-qwen3')
    package_weight = Path(*weight.parts[2:]) if weight.parts[:2] == marker else weight
    candidates = (
        (asset_root / RUNTIME, asset_root / package_weight),
        (asset_root / 'models' / 'signal-formula-qwen3' / RUNTIME, asset_root / weight),
    )
    for executable, weights in candidates:
        if executable.is_file() and weights.is_file():
            return executable, weights
    return None


def model_command(asset_root, cpu=False, *, registry_root=None):
    project_root = Path(registry_root) if registry_root else Path(__file__).resolve().parent
    registry = Registry(project_root)
    model = registry.models[registry.defaults['chat']]
    paths = model_paths(asset_root, model)
    if paths is None:
        raise FileNotFoundError(f"默认模型 {model['id']} 的权重或 llama-server 不在资源目录中")
    executable, weights = paths
    endpoint = urlparse(model['endpoint'])
    if endpoint.hostname != '127.0.0.1' or endpoint.port is None:
        raise ValueError('模型启动器需要 127.0.0.1 上的固定端口')
    runtime = model.get('runtime_options', {})
    command = [str(executable), '-m', str(weights),
               '--alias', model['alias'], '--host', endpoint.hostname, '--port', str(endpoint.port),
               '-c', str(model['context']), '-np', '1',
               '-ngl', '0' if cpu else str(runtime.get('gpu_layers', 99)),
               '--offline', '--reasoning', 'off', '--no-webui', '-t', '6',
               '--cors-origins', 'http://127.0.0.1:18080', '--no-cors-credentials']
    if not cpu and runtime.get('device', 'Vulkan1'):
        command.extend(['--device', runtime.get('device', 'Vulkan1')])
    return command


def embedding_command(asset_root, *, registry_root=None):
    registry = Registry(Path(registry_root) if registry_root else Path(__file__).resolve().parent)
    model = registry.models[registry.defaults['embedding']]
    paths = model_paths(asset_root, model)
    if paths is None:
        raise FileNotFoundError('向量模型权重或 llama-server 不在资源目录中')
    endpoint = urlparse(model['endpoint'])
    if endpoint.hostname != '127.0.0.1' or endpoint.port is None:
        raise ValueError('模型启动器需要 127.0.0.1 上的固定端口')
    executable, weights = paths
    return [str(executable), '-m', str(weights), '--alias', model['alias'],
            '--host', endpoint.hostname, '--port', str(endpoint.port), '--embedding', '--pooling', 'last',
            '-c', str(model['context']), '-b', str(model['context']), '-ub', str(model['context']),
            '-np', '1', '-ngl', '0', '-t', '6', '--offline', '--no-webui',
            '--cors-origins', 'http://127.0.0.1:18080', '--no-cors-credentials']
