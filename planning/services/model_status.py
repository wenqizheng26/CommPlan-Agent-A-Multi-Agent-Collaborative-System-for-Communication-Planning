"""Read-only live service probe, separate from saved task outcomes."""
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, ProxyHandler, HTTPRedirectHandler
from planning.providers.registry import Registry

def default_endpoint_alias():
    registry = Registry(Path(__file__).resolve().parents[2])
    model = registry.models[registry.defaults['chat']]
    return model['endpoint'].rstrip('/'), model['alias']


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def read_status(path, base):
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(base + path, timeout=2) as response:
        return json.loads(response.read(65536))


def probe_model(base=None, alias=None):
    if base is None or alias is None:
        default_base, default_alias = default_endpoint_alias()
        base = default_base if base is None else base
        alias = default_alias if alias is None else alias
    status = 'unknown'
    try:
        health = read_status('/health', base)
        if isinstance(health, dict) and health.get('status') == 'ok':
            models = read_status('/v1/models', base)
            items = models.get('data', []) if isinstance(models, dict) else []
            status = 'ready' if isinstance(items, list) and any(
                isinstance(item, dict) and item.get('id') == alias for item in items
            ) else 'unexpected'
        elif isinstance(health, dict) and health.get('status') == 'loading model':
            status = 'loading'
    except HTTPError as exc:
        status = 'not_ready' if exc.code == 503 else 'unknown'
    except (URLError, OSError):
        status = 'unreachable'
    except (ValueError, TypeError):
        status = 'unknown'
    return {'status': status, 'model': alias, 'endpoint': base,
            'checked_at': datetime.now(timezone.utc).isoformat()}


def probe_registry(registry):
    """Live status of every registered chat model; one probe per endpoint and alias.
    A reachable service wins: it may run from an external asset root."""
    seen, result = {}, {}
    for m in registry.models.values():
        if m['kind'] != 'chat' and m.get('runtime') != 'llama.cpp':
            continue
        key = (m['endpoint'].rstrip('/'), m['alias'])
        if key not in seen:
            seen[key] = probe_model(*key)['status']
        live = seen[key]
        result[m['id']] = 'not_installed' if live == 'unreachable' and not registry.installed(m['id']) else live
    return result
