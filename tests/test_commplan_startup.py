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
    (root / "runtime_config.json").write_text(
        json.dumps({"generation": {
            "path": "models/Qwen3-4B-GGUF/Qwen3-4B-Q4_K_M.gguf",
            "executable": "runtime/llama.cpp-b10950/llama-server.exe",
            "alias": "signal-formula-qwen3", "port": 18081,
        }}),
        encoding="utf-8",
    )
    return root


class AssetRootTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name) / "project"
        self.project.mkdir()
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
        (self.local / "runtime_config.json").unlink()
        self.assertEqual(start_commplan.asset_root(), self.root.resolve())
        (self.root / "runtime_config.json").unlink()
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


if __name__ == "__main__":
    unittest.main()
