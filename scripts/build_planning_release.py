"""Build a source-only Planning Workbench release from an explicit allowlist."""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import zipfile


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.0-demo"
VALIDATION_RECORD = "docs/demo/VALIDATION.md"
ROOT_FILES = {
    "LICENSE", "README.md", "THIRD_PARTY.md", "requirements-planning.txt",
    "runtime_config.json", "setup_planning.cmd", "启动.cmd", "start.cmd",
    "start_commplan.py", "stop_commplan.py", "停止服务.cmd", "launch.py",
    "knowledge/formulas.json", "config/models.json", "planning/README.md", VALIDATION_RECORD,
    "docs/demo/RECORDING.md", "scripts/planning_smoke.py",
    "planning/run_planning.cmd",
}
SOURCE_FILES = set("""
formula_rag/__init__.py formula_rag/applicability.py formula_rag/catalog.py
formula_rag/core.py formula_rag/importing.py formula_rag/interpretation.py
formula_rag/model_transport.py formula_rag/model.py formula_rag/parsing.py
formula_rag/pipeline.py formula_rag/presentation.py formula_rag/retrieval.py
planning/__init__.py planning/agents/__init__.py planning/agents/calculation.py
planning/agents/orchestrator.py planning/agents/requirements.py planning/agents/review.py
planning/agents/role_model.py planning/build_info.py planning/demo.py
planning/examples/complete.json planning/examples/conflict.json planning/examples/missing.json
planning/providers/__init__.py planning/providers/registry.py planning/providers/settings.py
planning/retrieval/__init__.py planning/retrieval/service.py
planning/requirements_contract.py planning/services/__init__.py
planning/services/calculation.py planning/services/clarification.py
planning/services/confirmation.py planning/services/domain_calculation.py
planning/services/input_domains.py planning/services/model_status.py
planning/services/plans.py planning/services/reference_models.py
planning/services/requirement_evidence.py planning/services/requirement_parameters.py
planning/services/requirement_policy.py planning/services/requirement_validation.py
planning/services/supplement.py planning/web_server.py planning/web/app.css
planning/web/app.js planning/web/conversation.mjs planning/web/details.mjs
planning/web/drafts.mjs planning/web/flow.mjs planning/web/index.html
planning/web/model-status.mjs planning/web/progress.mjs planning/web/settings.mjs planning/web/timing.mjs planning/web/questions.mjs
planning/web/roles.mjs planning/web/text.mjs planning/web/values.mjs
planning/workflow/__init__.py planning/workflow/activity.py
planning/workflow/planning_graph.py planning/workflow/requirements_graph.py
planning/workflow/task_service.py planning/workflow/task_store.py
""".split())
SOURCE_SUFFIXES = {".py", ".js", ".mjs", ".html", ".css", ".json"}
GENERATED = {"VERSION", "BUILD_INFO.json", "MANIFEST.json"}
REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
REQUIRED_FILES = {
    "LICENSE", "README.md", "THIRD_PARTY.md", "requirements-planning.txt",
    "runtime_config.json", "setup_planning.cmd", "启动.cmd", "start.cmd",
    "start_commplan.py", "launch.py", "knowledge/formulas.json",
    "planning/README.md", "planning/run_planning.cmd", "docs/demo/RECORDING.md",
    VALIDATION_RECORD, "scripts/planning_smoke.py",
} | SOURCE_FILES


def permitted(name):
    """An explicit source allowlist; no broad worktree traversal or runtime assets."""
    path = PurePosixPath(name)
    if not name or "\\" in name or path.is_absolute() or ".." in path.parts:
        return False
    if any(part.startswith(".") or part in {"__pycache__", "models", "runtime", "outputs", "tests"}
           for part in path.parts):
        return False
    return name in ROOT_FILES or name in SOURCE_FILES or name in GENERATED


def regular_file(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        return False
    return not bool(getattr(info, "st_file_attributes", 0) & REPARSE_POINT)


def checked_file(root, name):
    if not permitted(name) or name in GENERATED:
        raise ValueError(f"release path is not allowed: {name}")
    path = root.joinpath(*PurePosixPath(name).parts)
    current = path
    while current != root:
        if current.is_symlink() or bool(getattr(current.lstat(), "st_file_attributes", 0) & REPARSE_POINT):
            raise ValueError(f"symlink or reparse point refused: {name}")
        current = current.parent
    if not regular_file(path) or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"not a regular in-tree file: {name}")
    return path


def source_files(root):
    names = {name for name in ROOT_FILES if (root / name).is_file()} | SOURCE_FILES
    unlisted = {
        path.relative_to(root).as_posix()
        for folder in ("planning", "formula_rag")
        for path in (root / folder).rglob("*")
        if path.is_file() and path.suffix in SOURCE_SUFFIXES
        and path.relative_to(root).as_posix() not in names
    }
    if unlisted:
        raise ValueError("new source needs explicit release review: " + ", ".join(sorted(unlisted)))
    missing = REQUIRED_FILES - names
    if missing:
        raise ValueError("missing release inputs: " + ", ".join(sorted(missing)))
    missing_on_disk = {name for name in names if not (root / name).is_file()}
    if missing_on_disk:
        raise ValueError("missing release inputs: " + ", ".join(sorted(missing_on_disk)))
    for name in names:
        checked_file(root, name)
    return sorted(names)


def git_value(root, *args):
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    if result.returncode:
        raise RuntimeError("Git metadata unavailable: " + result.stderr.strip())
    return result.stdout.strip()


def build(root=ROOT, output=None, version=VERSION, require_clean=False):
    root = Path(root).resolve()
    names = source_files(root)
    spec = importlib.util.spec_from_file_location("commplan_release_build_info", root / "planning/build_info.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # build_fingerprint reads this source tree; the archive carries the same immutable inputs.
    fingerprint = module.build_fingerprint(root)
    commit = git_value(root, "rev-parse", "HEAD")
    dirty = bool(git_value(root, "status", "--porcelain", "--untracked-files=all"))
    if require_clean and dirty:
        raise ValueError("formal release requires a clean source commit")
    info = {
        "version": version,
        "source_commit": commit,
        "source_dirty": dirty,
        "built_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "intended_platform": "Windows, Python 3.12",
        "build_fingerprint": fingerprint,
        "validation_record": VALIDATION_RECORD,
        "package_type": "source-demo-without-model-assets",
    }
    payloads = {name: checked_file(root, name).read_bytes() for name in names}
    payloads["VERSION"] = (version + "\n").encode("utf-8")
    payloads["BUILD_INFO.json"] = (json.dumps(info, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    manifest = {
        "format": 1,
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(payloads.items())},
    }
    payloads["MANIFEST.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    output = Path(output) if output else root / "outputs" / "releases" / f"commplan-agent-v{version}-source.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(payloads.items()):
            archive.writestr(name, data)
    return output.resolve()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--version", default=VERSION)
    parser.add_argument("--require-clean", action="store_true", help="require committed source for formal release")
    args = parser.parse_args(argv)
    print(build(args.root, args.output, args.version, args.require_clean))
    return 0


if __name__ == "__main__":
    sys.exit(main())
