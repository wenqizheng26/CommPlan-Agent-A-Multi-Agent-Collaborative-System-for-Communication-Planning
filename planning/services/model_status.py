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


def probe_endpoint(base):
    """('ok', served aliases) for an answering llama-server, else (status, empty set)."""
    try:
        health = read_status('/health', base)
        if isinstance(health, dict) and health.get('status') == 'ok':
            models = read_status('/v1/models', base)
            items = models.get('data', []) if isinstance(models, dict) else []
            return 'ok', {item.get('id') for item in items if isinstance(item, dict)} if isinstance(items, list) else set()
        if isinstance(health, dict) and health.get('status') == 'loading model':
            return 'loading', set()
    except HTTPError as exc:
        return ('not_ready' if exc.code == 503 else 'unknown'), set()
    except (URLError, OSError):
        return 'unreachable', set()
    except (ValueError, TypeError):
        pass
    return 'unknown', set()


def probe_model(base=None, alias=None):
    if base is None or alias is None:
        default_base, default_alias = default_endpoint_alias()
        base = default_base if base is None else base
        alias = default_alias if alias is None else alias
    live, served = probe_endpoint(base)
    status = ('ready' if alias in served else 'unexpected') if live == 'ok' else live
    return {'status': status, 'model': alias, 'endpoint': base,
            'checked_at': datetime.now(timezone.utc).isoformat()}


def probe_registry(registry):
    """Live status of every registered llama.cpp model; one probe per endpoint.
    'standby' means another registered model holds the shared port: switching loads this one.
    A reachable service wins: it may run from an external asset root."""
    seen, result = {}, {}
    for m in registry.models.values():
        if m['kind'] != 'chat' and m.get('runtime') != 'llama.cpp':
            continue
        base = m['endpoint'].rstrip('/')
        if base not in seen:
            seen[base] = probe_endpoint(base)
        live, served = seen[base]
        if live == 'ok':
            registered = {o['alias'] for o in registry.models.values() if o.get('endpoint', '').rstrip('/') == base}
            status = 'ready' if m['alias'] in served else 'standby' if served & registered else 'unexpected'
        else:
            status = live
        result[m['id']] = ('not_installed' if status in ('unreachable', 'standby') and not registry.installed(m['id'])
                           else status)
    return result
