"""Release boundary checks target leakage and archive integrity risks."""

import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_planning_release import REQUIRED_FILES, checked_file, permitted  # noqa: E402
from validate_planning_release import inspect_archive  # noqa: E402


def archive_bytes(extra=None, tamper=None):
    info = {
        "version": "0.1.0-demo", "source_commit": "a" * 40,
        "source_dirty": False, "build_fingerprint": "b" * 20,
        "validation_record": "docs/demo/VALIDATION.md",
        "package_type": "source-demo-without-model-assets",
    }
    files = {name: b"" for name in REQUIRED_FILES}
    files.update({
        "VERSION": b"0.1.0-demo\n",
        "BUILD_INFO.json": json.dumps(info).encode(),
        "docs/demo/VALIDATION.md": b"Validation record\n",
    })
    manifest = {"format": 1, "files": {
        name: hashlib.sha256(data).hexdigest() for name, data in files.items()}}
    if tamper:
        files[tamper] += b"altered"
    files["MANIFEST.json"] = json.dumps(manifest).encode()
    files.update(extra or {})
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    stream.seek(0)
    return stream


class PlanningReleaseTests(unittest.TestCase):
    def test_source_allowlist_excludes_model_and_developer_state(self):
        for name in ("models/model.gguf", "runtime/server.exe", ".venv/x.py",
                     "outputs/tasks.sqlite", "tests/test_core.py", ".git/config",
                     "planning/__pycache__/x.pyc", "../escape.txt"):
            with self.subTest(name=name):
                self.assertFalse(permitted(name))
        self.assertTrue(permitted("planning/web/app.js"))
        self.assertTrue(permitted("knowledge/formulas.json"))
        self.assertFalse(permitted("planning/unlisted_helper.py"))

    def test_archive_integrity_and_path_traversal(self):
        with zipfile.ZipFile(archive_bytes()) as archive:
            self.assertEqual(inspect_archive(archive)["version"], "0.1.0-demo")
        with zipfile.ZipFile(archive_bytes(tamper="VERSION")) as archive:
            with self.assertRaisesRegex(ValueError, "SHA256 mismatch"):
                inspect_archive(archive)
        with zipfile.ZipFile(archive_bytes(extra={"../escape.txt": b"bad"})) as archive:
            with self.assertRaisesRegex(ValueError, "unsafe ZIP member"):
                inspect_archive(archive)
        with zipfile.ZipFile(archive_bytes(extra={"models/model.gguf": b"bad"})) as archive:
            with self.assertRaisesRegex(ValueError, "unsafe ZIP member"):
                inspect_archive(archive)
        with zipfile.ZipFile(archive_bytes(extra={"./VERSION": b"bad"})) as archive:
            with self.assertRaisesRegex(ValueError, "unsafe ZIP member"):
                inspect_archive(archive)

    def test_source_symlink_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "planning" / "web").mkdir(parents=True)
            target = root / "source.py"
            target.write_text("x=1")
            link = root / "planning" / "web" / "app.js"
            try:
                link.symlink_to(target)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation unavailable")
            with self.assertRaisesRegex(ValueError, "symlink or reparse"):
                checked_file(root, "planning/web/app.js")


if __name__ == "__main__":
    unittest.main()
