"""Build an offline llama.cpp command from the default chat registry entry."""
from pathlib import Path
import re
import subprocess
from urllib.parse import urlparse

from planning.providers.registry import Registry


RUNTIME = Path('runtime/llama.cpp-b10950/llama-server.exe')
# llama.cpp numbers Vulkan devices in enumeration order, which can change across reboots: on the
# development laptop Vulkan1 was the RTX 4060 until a reboot made it the Radeon 610M iGPU.
DISCRETE = re.compile(r'NVIDIA|GeForce|Quadro|Radeon RX|Radeon Pro|Arc A', re.I)


def vulkan_devices(executable):
    """[(VulkanN, name)] as this llama-server numbers them now; empty when it cannot be listed."""
    try:
        result = subprocess.run([str(executable), '--list-devices'], capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=60)
    except (OSError, subprocess.SubprocessError):
        return []
    return re.findall(r'^\s*(Vulkan\d+):\s*(.+?)\s*\(\d+ MiB', result.stdout + result.stderr, re.M)


def resolve_device(executable, wanted):
    """'auto': a discrete GPU by name, else the first Vulkan device, else none (CPU). A name fragment
    such as 'NVIDIA' must match a device. An explicit VulkanN or none is used as written."""
    if re.fullmatch(r'Vulkan\d+|none', wanted):
        return wanted
    devices = vulkan_devices(executable)
    if wanted == 'auto':
        return next((d for d, name in devices if DISCRETE.search(name)), devices[0][0] if devices else 'none')
    match = next((d for d, name in devices if wanted.lower() in name.lower()), None)
    if match is None:
        raise RuntimeError(f'没有名称含 {wanted} 的 GPU：' + ('；'.join(f'{d} {n}' for d, n in devices) or '未列出设备'))
    return match


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


def model_command(asset_root, cpu=False, *, registry_root=None, model_id=None):
    project_root = Path(registry_root) if registry_root else Path(__file__).resolve().parent
    registry = Registry(project_root)
    model = registry.models[model_id or registry.defaults['chat']]
    paths = model_paths(asset_root, model)
    if paths is None:
        raise FileNotFoundError(f"模型 {model['id']} 的权重或 llama-server 不在资源目录中")
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
    if not cpu:
        command.extend(['--device', resolve_device(executable, runtime.get('device', 'auto'))])
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
    # CPU only. With -ngl 0 alone llama.cpp still offloads large batches to the GPU, and its buffers
    # push the chat model's weights out of an 8 GB card: the 9B then generates about 4x slower.
    return [str(executable), '-m', str(weights), '--alias', model['alias'],
            '--host', endpoint.hostname, '--port', str(endpoint.port), '--embedding', '--pooling', 'last',
            '-c', str(model['context']), '-b', str(model['context']), '-ub', str(model['context']),
            '-np', '1', '-ngl', '0', '--device', 'none', '-t', '6', '--offline', '--no-webui',
            '--cors-origins', 'http://127.0.0.1:18080', '--no-cors-credentials']
