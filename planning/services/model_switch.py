"""Switch the chat model on its shared port: 8 GB of video memory holds one at a time.

The switch runs in the background and the page polls it. Commands that may call a model and a
switch exclude each other: a switch waits for no command, and commands are refused during it.
"""
from contextlib import contextmanager
import copy
from datetime import datetime, timezone
from pathlib import Path
import threading
import time

from planning.requirements_contract import require
from planning.services.model_status import probe_endpoint

START_TIMEOUT_S = 240


def name(model):
    return model['display_name'].replace(' · Q4_K_M', '')


class Gate:
    """Counts running model commands; a switch may start only when none runs."""

    def __init__(self):
        self._lock = threading.Lock()
        self.running = 0
        self.switching = False

    @contextmanager
    def command(self):
        with self._lock:
            require(not self.switching, 'MODEL_SWITCHING')
            self.running += 1
        try:
            yield
        finally:
            with self._lock:
                self.running -= 1

    def claim(self):
        with self._lock:
            require(not self.switching, 'MODEL_SWITCH_RUNNING')
            require(not self.running, 'MODEL_SWITCH_BUSY')
            self.switching = True

    def release(self):
        with self._lock:
            self.switching = False


class SwitchFailed(Exception):
    pass


class LocalRuntime:
    """Stops and starts llama-server with the launcher's own helpers (repository root modules)."""

    def __init__(self, root):
        self.root = Path(root)

    def assets(self, model):
        import start_commplan
        try:
            return start_commplan.asset_root(None, model)
        except RuntimeError:
            return None

    def served(self, model):
        return probe_endpoint(model['endpoint'].rstrip('/'))

    def stop(self, model):
        import stop_commplan
        port = int(model['endpoint'].rstrip('/').rsplit(':', 1)[1])
        aliases, _ = stop_commplan.service_ports(self.root)
        found = stop_commplan.listeners({port})
        if any(stop_commplan.commplan_role(item, aliases, set()) != 'model' for item in found):
            raise SwitchFailed(f'{port} 端口被其他程序占用，没有切换。')
        for item in found:
            stop_commplan.stop(item['pid'])
        if found and not stop_commplan.wait_closed(port):
            raise SwitchFailed('原模型未能停止，没有切换。')
        for item in found:
            stop_commplan.forget(item['pid'])

    def start(self, model):
        import start_commplan
        from launch import model_command
        root = self.assets(model)
        if root is None:
            raise SwitchFailed(f'本机没有 {name(model)} 的权重。')
        process = start_commplan.spawn(model_command(root, model_id=model['id'], registry_root=self.root),
                                       'commplan-model', root)
        try:
            start_commplan.wait_ready(lambda: start_commplan.model_ready(model), process,
                                      '模型', timeout=START_TIMEOUT_S)
        except RuntimeError as exc:
            raise SwitchFailed(str(exc)) from exc


class ModelSwitcher:
    def __init__(self, service, gate, runtime=None):
        self.service, self.gate = service, gate
        self.runtime = runtime or LocalRuntime(service.root)
        self._lock = threading.Lock()
        self._state = dict(state='idle')
        self._started = None

    def status(self):
        with self._lock:
            state = dict(self._state)
            if state['state'] == 'switching':
                state['elapsed_ms'] = round((time.monotonic() - self._started) * 1000)
        return state

    def start(self, model_id):
        registry = self.service.registry
        model = registry.models.get(model_id) if type(model_id) is str else None
        require(model is not None and model['kind'] == 'chat', 'SETTINGS_UNKNOWN_MODEL')
        require(registry.strict(model_id), 'SETTINGS_MODEL_NOT_STRUCTURED')
        require(self.runtime.assets(model) is not None, 'MODEL_NOT_INSTALLED')
        self.gate.claim()
        try:
            with self._lock:
                self._started = time.monotonic()
                self._state = dict(state='switching', model_id=model_id,
                                   started_at=datetime.now(timezone.utc).isoformat())
            threading.Thread(target=self._run, args=(model_id,), daemon=True).start()
        except BaseException:
            self.gate.release()
            raise
        return self.status()

    def _finish(self, **fields):
        with self._lock:
            elapsed = round((time.monotonic() - self._started) * 1000)
            self._state = dict(self._state, elapsed_ms=elapsed,
                               finished_at=datetime.now(timezone.utc).isoformat(), **fields)

    def _run(self, model_id):
        registry = self.service.registry
        target = registry.models[model_id]
        try:
            live, served = self.runtime.served(target)
            if not (live == 'ok' and target['alias'] in served):
                previous = next((m for m in registry.models.values()
                                 if m['kind'] == 'chat' and m['endpoint'] == target['endpoint'] and m['alias'] in served), None)
                self.runtime.stop(target)
                try:
                    self.runtime.start(target)
                except SwitchFailed as exc:
                    note = '，原模型未能恢复，请用“启动 CommPlan”重新启动。'
                    if previous is not None:
                        try:
                            self.runtime.start(previous)
                            note = f'。已恢复 {name(previous)}。'
                        except SwitchFailed:
                            pass
                    raise SwitchFailed(f'{name(target)} 未能启动：{exc}'.rstrip('。') + note) from exc
            cleared = self.adopt(model_id)
            self._finish(state='done', cleared_roles=cleared,
                         message=f'已切换到 {name(target)}。' +
                                 (f'{len(cleared)} 个角色原先指定的模型未加载，改为跟随默认。' if cleared else ''))
        except SwitchFailed as exc:
            self._finish(state='failed', message=str(exc))
        except Exception as exc:  # the page must learn the switch ended; details go to the server log
            print('model switch failed:', type(exc).__name__, exc, flush=True)
            self._finish(state='failed', message='切换未完成，请查看服务器终端。')
        finally:
            self.gate.release()

    def adopt(self, model_id):
        """Make the loaded model the default; roles bound to an unloaded model follow it."""
        registry = self.service.registry
        alias = registry.models[model_id]['alias']
        for _ in range(3):
            current = self.service.settings.get()
            settings = copy.deepcopy(current['settings'])
            settings['chat']['default'] = model_id
            roles = settings['chat']['roles']
            cleared = [r for r, m in roles.items() if m is not None and registry.models[m]['alias'] != alias]
            for role in cleared:
                roles[role] = None
            if settings == current['settings']:
                return cleared
            try:
                self.service.update_settings(settings, current['version'])
                return cleared
            except ValueError as exc:
                if str(exc) != 'STALE_SETTINGS':
                    raise
        raise ValueError('STALE_SETTINGS')
