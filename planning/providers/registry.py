"""Local model registry: which models exist, where they listen, what they can do.

The registry is product configuration (tracked, part of the build fingerprint).
Weights stay in ignored ``models/``; a missing file only marks a model uninstalled.
"""
from dataclasses import dataclass
import ipaddress
import json
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from planning.requirements_contract import require

KINDS = {'chat', 'embedding'}
# Every current model role validates a strict JSON-schema answer.
ROLES = ('requirements', 'supplement', 'compute_agent', 'validator_agent')


def loopback(url):
    parsed = urlparse(url)
    if parsed.scheme != 'http' or not parsed.hostname:
        return False
    if parsed.hostname == 'localhost':
        return True
    try:
        return ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        return False


def relative(path):
    return (type(path) is str and path and not PurePosixPath(path).is_absolute()
            and '\\' not in path and ':' not in path and '..' not in PurePosixPath(path).parts)


@dataclass(frozen=True)
class ChatBinding:
    """What one role call needs; recorded verbatim as provenance."""
    role: str
    model_id: str
    alias: str
    url: str
    context: int
    temperature: float
    timeout_s: float

    def record(self):
        return dict(role=self.role, model_id=self.model_id, alias=self.alias,
                    temperature=self.temperature, timeout_s=self.timeout_s)


class Registry:
    def __init__(self, root, path=None):
        self.root = Path(root)
        self.path = Path(path) if path else self.root / 'config/models.json'
        data = json.loads(self.path.read_text(encoding='utf-8'))
        require(type(data) is dict and data.get('schema_version') == 1, 'REGISTRY_SCHEMA')
        models = data.get('models')
        require(type(models) is list and models, 'REGISTRY_MODELS')
        self.models = {}
        for m in models:
            require(type(m) is dict and type(m.get('id')) is str and m['id'] not in self.models, 'REGISTRY_ID')
            require(m.get('kind') in KINDS, 'REGISTRY_KIND')
            require(type(m.get('display_name')) is str, 'REGISTRY_NAME')
            if m['kind'] == 'chat' or m.get('runtime') == 'llama.cpp':
                require(type(m.get('endpoint')) is str and loopback(m['endpoint']), 'REGISTRY_NOT_LOOPBACK')
                require(type(m.get('alias')) is str and m['alias'], 'REGISTRY_ALIAS')
                require(type(m.get('context')) is int and 512 <= m['context'] <= 131072, 'REGISTRY_CONTEXT')
                d = m.get('defaults', {})
                require(0 <= d.get('temperature', 0) <= 1 and 1 <= d.get('timeout_s', 30) <= 120, 'REGISTRY_DEFAULTS')
            if m['kind'] == 'embedding' and m.get('runtime') == 'llama.cpp':
                require(type(m.get('dimension')) is int and 1 <= m['dimension'] <= 4096, 'REGISTRY_DIMENSION')
            for key in ('weights', 'path'):
                if key in m:
                    require(relative(m[key]), 'REGISTRY_PATH')
            self.models[m['id']] = m
        self.defaults = data.get('defaults', {})
        require(self.kind(self.defaults.get('chat')) == 'chat', 'REGISTRY_DEFAULT_CHAT')
        require(self.defaults.get('embedding') is None or self.kind(self.defaults['embedding']) == 'embedding',
                'REGISTRY_DEFAULT_EMBEDDING')

    def kind(self, model_id):
        return self.models.get(model_id, {}).get('kind')

    def installed(self, model_id):
        m = self.models[model_id]
        target = m.get('weights') or m.get('path')
        return target is None or (self.root / target).exists()

    def strict(self, model_id):
        return bool(self.models[model_id].get('capabilities', {}).get('json_schema_strict'))

    def binding(self, role, model_id, params):
        m = self.models[model_id]
        d = m.get('defaults', {})
        timeout = params.get('timeout_s') or d.get('timeout_s', 30)
        temperature = params.get('temperature')
        return ChatBinding(role=role, model_id=model_id, alias=m['alias'],
                           url=m['endpoint'].rstrip('/') + '/v1/chat/completions', context=m['context'],
                           temperature=d.get('temperature', 0) if temperature is None else temperature,
                           timeout_s=float(timeout))

    def describe(self):
        """Public listing for the page; never exposes filesystem paths."""
        rows = []
        for m in self.models.values():
            row = dict(id=m['id'], kind=m['kind'], display_name=m['display_name'], runtime=m.get('runtime'),
                       installed=self.installed(m['id']), revision=m.get('revision'))
            if m['kind'] == 'chat':
                row.update(context=m['context'], strict=self.strict(m['id']), defaults=m.get('defaults', {}),
                           endpoint=m['endpoint'])
            else:
                row.update(dimension=m.get('dimension'))
            rows.append(row)
        return dict(defaults=self.defaults, models=rows)
