"""Build the command for an existing local llama.cpp model; never download assets."""
import json
from pathlib import Path


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
