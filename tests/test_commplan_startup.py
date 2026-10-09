"""Launcher regressions that do not require a real local model."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import start_commplan


def make_assets(root):
    """Create the launcher contract with small placeholder files."""
    root.mkdir(parents=True, exist_ok=True)
    model = root / "models" / "Qwen3-4B-GGUF" / "Qwen3-4B-Q4_K_M.gguf"
    executable = root / "runtime" / "llama.cpp-b10950" / "llama-server.exe"
    model.parent.mkdir(parents=True, exist_ok=True)
    executable.parent.mkdir(parents=True, exist_ok=True)
    model.write_bytes(b"model placeholder")
    executable.write_bytes(b"runtime placeholder")
    return root


class AssetRootTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "project"
        self.project.mkdir()
        (self.project / 'config').mkdir()
        (self.project / 'config' / 'models.json').write_text(json.dumps({
            'schema_version': 1,
            'defaults': {'chat': 'test-chat'},
            'models': [{'id': 'test-chat', 'kind': 'chat', 'display_name': 'Test',
                        'endpoint': 'http://127.0.0.1:18081', 'alias': 'signal-formula-qwen3',
                        'context': 4096,
                        'weights': 'models/signal-formula-qwen3/models/Qwen3-4B-GGUF/Qwen3-4B-Q4_K_M.gguf'}]
        }), encoding='utf-8')
        self.local = make_assets(self.project / "models" / "signal-formula-qwen3")
        self.root = make_assets(self.project)
        self.legacy = make_assets(self.project.parent / "signal-formula-rag")
        root_patch = mock.patch.object(start_commplan, "ROOT", self.project)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        env_patch = mock.patch.dict(os.environ, {"COMMPLAN_ASSET_ROOT": ""})
        env_patch.start()
        self.addCleanup(env_patch.stop)

    def test_project_model_assets_win_over_root_and_legacy(self):
        self.assertEqual(start_commplan.asset_root(), self.local.resolve())

    def test_root_and_legacy_remain_fallbacks(self):
        (self.local / "models/Qwen3-4B-GGUF/Qwen3-4B-Q4_K_M.gguf").unlink()
        self.assertEqual(start_commplan.asset_root(), self.root.resolve())
        (self.root / "models/Qwen3-4B-GGUF/Qwen3-4B-Q4_K_M.gguf").unlink()
        self.assertEqual(start_commplan.asset_root(), self.legacy.resolve())

    def test_explicit_path_overrides_environment_and_project(self):
        explicit = make_assets(Path(self.temp.name) / "explicit")
        with mock.patch.dict(os.environ, {"COMMPLAN_ASSET_ROOT": str(self.legacy)}):
            self.assertEqual(start_commplan.asset_root(explicit), explicit.resolve())

    def test_environment_overrides_project(self):
        with mock.patch.dict(os.environ, {"COMMPLAN_ASSET_ROOT": str(self.legacy)}):
            self.assertEqual(start_commplan.asset_root(), self.legacy.resolve())

    def test_invalid_explicit_path_does_not_silently_fall_back(self):
        with self.assertRaises(RuntimeError):
            start_commplan.asset_root(Path(self.temp.name) / "missing")


class SavedModelTests(unittest.TestCase):
    def test_launcher_starts_the_model_the_settings_chose(self):
        from planning.providers.registry import Registry
        from planning.providers.settings import SettingsStore
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / 'planning.sqlite'
            self.assertEqual(start_commplan.saved_model(db)['id'], 'qwen35-9b-q4')  # no database yet
            self.assertFalse(db.exists())  # reading never creates it
            store = SettingsStore(db, Registry(start_commplan.ROOT))
            settings = store.get()['settings']
            settings['chat']['default'] = 'qwen3-4b-q4'
            store.put(settings, 0)
            self.assertEqual(start_commplan.saved_model(db)['id'], 'qwen3-4b-q4')


class WithoutModelTests(unittest.TestCase):
    def test_starts_workbench_without_touching_model_assets_or_service(self):
        ready = {"profile": "confirmed-fspl-loop-v1"}
        process = mock.Mock()

        def wait_for_workbench(check, child, label, timeout=180):
            self.assertIs(child, process)
            self.assertEqual(label, "工作台")
            self.assertEqual(timeout, 60)
            self.assertTrue(check())

        with (mock.patch.object(start_commplan, "read_json", side_effect=[None, ready]),
              mock.patch.object(start_commplan, "listening", return_value=False),
              mock.patch.object(start_commplan, "spawn", return_value=process) as spawn,
              mock.patch.object(start_commplan, "wait_ready", side_effect=wait_for_workbench),
              mock.patch.object(start_commplan, "ensure_model") as ensure_model,
              mock.patch.object(start_commplan, "asset_root") as asset_root,
              mock.patch.object(start_commplan.webbrowser, "open") as open_browser,
              mock.patch.dict(os.environ, {"COMMPLAN_ASSET_ROOT": "missing-assets"})):
            result = start_commplan.main(["--without-model", "--no-browser", "--port", "18083"])

        self.assertEqual(result, 0)
        ensure_model.assert_not_called()
        asset_root.assert_not_called()
        open_browser.assert_not_called()
        self.assertEqual(spawn.call_count, 1)
        command, name, cwd = spawn.call_args.args
        self.assertEqual(command[-2:], ["--port", "18083"])
        self.assertEqual(name, "commplan-web-18083")
        self.assertEqual(cwd, start_commplan.ROOT)


class ReplaceWorkbenchTests(unittest.TestCase):
    def launch(self, session, stopped):
        ready = {"profile": "confirmed-fspl-loop-v1"}
        with (mock.patch.object(start_commplan, "read_json", side_effect=[session, ready]),
              mock.patch.object(start_commplan, "build_fingerprint", return_value="new"),
              mock.patch.object(start_commplan, "listening", return_value=True),
              mock.patch.object(start_commplan, "stop_workbench", return_value=stopped) as stop,
              mock.patch.object(start_commplan, "spawn", return_value=mock.Mock()) as spawn,
              mock.patch.object(start_commplan, "wait_ready")):
            try:
                return start_commplan.main(["--without-model", "--no-browser"]), stop, spawn
            except RuntimeError as exc:
                return exc, stop, spawn

    def test_older_build_is_replaced(self):
        result, stop, spawn = self.launch({"profile": "confirmed-fspl-loop-v1", "build": "old"}, True)
        self.assertEqual(result, 0)
        stop.assert_called_once_with(18082)
        self.assertEqual(spawn.call_count, 1)

    def test_current_build_is_reused(self):
        result, stop, spawn = self.launch({"profile": "confirmed-fspl-loop-v1", "build": "new"}, True)
        self.assertEqual(result, 0)
        stop.assert_not_called()
        spawn.assert_not_called()

    def test_same_build_from_another_folder_is_replaced(self):
        info=dict(folder='other-worktree',branch='other',commit='abcdef12',dirty=False)
        result,stop,spawn=self.launch({'profile':'confirmed-fspl-loop-v1','build':'new','instance':info},True)
        self.assertEqual(result,0)
        stop.assert_called_once_with(18082)
        self.assertEqual(spawn.call_count,1)

    def test_other_program_on_the_port_is_left_alone(self):
        result, stop, spawn = self.launch(None, False)
        self.assertIsInstance(result, RuntimeError)
        stop.assert_called_once_with(18082)
        spawn.assert_not_called()


class BrowserTests(unittest.TestCase):
    def test_chrome_is_preferred_over_the_default_browser(self):
        with (mock.patch.object(start_commplan, "chrome", return_value=Path("C:/chrome.exe")),
              mock.patch.object(start_commplan.subprocess, "Popen") as popen,
              mock.patch.object(start_commplan.webbrowser, "open") as default):
            self.assertTrue(start_commplan.open_browser("http://127.0.0.1:18082"))
        self.assertEqual(popen.call_args.args[0], [str(Path("C:/chrome.exe")), "http://127.0.0.1:18082"])
        default.assert_not_called()

    def test_default_browser_without_chrome(self):
        with (mock.patch.object(start_commplan, "chrome", return_value=None),
              mock.patch.object(start_commplan.webbrowser, "open", return_value=True) as default):
            self.assertTrue(start_commplan.open_browser("http://127.0.0.1:18082"))
        default.assert_called_once_with("http://127.0.0.1:18082")


if __name__ == "__main__":
    unittest.main()
