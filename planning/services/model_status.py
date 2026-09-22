"""Read-only live service probe, separate from saved task outcomes."""
from datetime import datetime, timezone
import json
from urllib.error import HTTPError, URLError
from urllib.request import build_opener, ProxyHandler, HTTPRedirectHandler

MODEL_URL = 'http://127.0.0.1:18081'
MODEL_ALIAS = 'signal-formula-qwen3'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def read_status(path):
    opener = build_opener(ProxyHandler({}), NoRedirect())
    with opener.open(MODEL_URL + path, timeout=2) as response:
        return json.loads(response.read(65536))


def probe_model():
    status = 'unknown'
    try:
        health = read_status('/health')
        if isinstance(health, dict) and health.get('status') == 'ok':
            models = read_status('/v1/models')
            items = models.get('data', []) if isinstance(models, dict) else []
            status = 'ready' if isinstance(items, list) and any(
                isinstance(item, dict) and item.get('id') == MODEL_ALIAS for item in items
            ) else 'unexpected'
        elif isinstance(health, dict) and health.get('status') == 'loading model':
            status = 'loading'
    except HTTPError as exc:
        status = 'not_ready' if exc.code == 503 else 'unknown'
    except (URLError, OSError):
        status = 'unreachable'
    except (ValueError, TypeError):
        status = 'unknown'
    return {'status': status, 'model': MODEL_ALIAS, 'endpoint': MODEL_URL,
            'checked_at': datetime.now(timezone.utc).isoformat()}
