"""Build a source-only Planning Workbench release from an explicit allowlist."""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.2.0-dev"
PACKAGE_TYPE = "source-workbench-without-model-assets"
VALIDATION_RECORD = "docs/codex/M1_ACCEPTANCE_STATUS.md"
ROOT_FILES = {
    "LICENSE", "README.md", "THIRD_PARTY.md", "requirements-planning.txt", "requirements-docs.txt",
    "runtime_config.json", "setup_planning.cmd", "启动.cmd", "start.cmd",
    "start_commplan.py", "stop_commplan.py", "停止服务.cmd", "launch.py",
    "knowledge/formulas.json", "config/models.json", "planning/README.md", VALIDATION_RECORD,
    "scripts/planning_smoke.py", "scripts/build_planning_release.py",
    "scripts/validate_planning_release.py", "scripts/eval_teacher.py",
    "planning/run_planning.cmd",
    "knowledge/tools.json", "knowledge/facts/sites.json", "knowledge/facts/devices.json",
    "knowledge/facts/modulations.json", "knowledge/facts/typical_values.json",
    "knowledge/facts/parameter_ranges.json",
    "knowledge/documents/manifest.json", "knowledge/documents/glossary.json",
    "knowledge/documents/simulated/站址表.md", "knowledge/documents/simulated/XX-100 手册.md",
    "knowledge/documents/simulated/XX-200 手册.md", "knowledge/documents/simulated/XX-300 手册.md",
    "knowledge/documents/simulated/调制方式与接收灵敏度.md",
}
DOCUMENT_FILES = set("""
docs/README.md docs/delivery/SOURCE_PACKAGE.md
docs/codex/NEXT_ACTION.md docs/codex/NEXT_ACTION.history-2026-10-02.md
docs/codex/M1_ACCEPTANCE_STATUS.md docs/codex/M1_COMPLETION.md
docs/codex/TEACHER_TASKS.md docs/codex/DEMO_HANDOFF_V4.md docs/design/WORKBENCH_UI.md
docs/demo/VALIDATION.md docs/demo/RECORDING.md docs/requirements.md
docs/design/TEACHER_CASES.md docs/design/ACCEPTANCE_M1.md docs/design/AGENT_LED.md
docs/design/CALCULATION_PLANS.md docs/design/KNOWLEDGE_FACTS.md
docs/design/MODEL_RETRIEVAL.md docs/design/M1_WEEK4.md
docs/design/FORMULA_SURVEY.md docs/design/ORCHESTRATOR_LLM.md
""".split())
# A reproducible deterministic precheck subset, not the final M1 acceptance matrix.
VALIDATION_FILES = set("""
scripts/inspect_workbook.py
tests/test_planning_release.py tests/test_core.py tests/test_teacher_tools.py
tests/test_teacher_cases_format.py tests/test_teacher_path.py tests/test_calculation_plans.py
tests/eval/m1_cases.jsonl tests/eval/teacher_cases.jsonl
tests/planning_m1.test.mjs tests/planning_report.test.mjs
tests/fixtures/teacher_report/margin.json tests/fixtures/teacher_report/comparison.json
tests/fixtures/teacher_report/defaults.json tests/fixtures/teacher_report/fspl_legacy.json
""".split())
SOURCE_FILES = set("""
formula_rag/__init__.py formula_rag/applicability.py formula_rag/catalog.py
formula_rag/core.py formula_rag/importing.py formula_rag/interpretation.py
formula_rag/tools.py
formula_rag/registry.py formula_rag/schema.py
formula_rag/model_transport.py formula_rag/model.py formula_rag/parsing.py
formula_rag/pipeline.py formula_rag/presentation.py formula_rag/retrieval.py
planning/__init__.py planning/agents/__init__.py planning/agents/calculation.py
planning/agents/orchestrator.py planning/agents/requirements.py planning/agents/review.py
planning/agents/role_model.py planning/build_info.py planning/demo.py
planning/instance_info.py planning/knowledge/library.py planning/knowledge/switches.py
planning/services/unit_typos.py
planning/agents/planner.py
planning/knowledge/__init__.py planning/knowledge/facts.py planning/knowledge/parameter_ranges.py
planning/retrieval/convert.py planning/retrieval/documents.py planning/retrieval/http_encoder.py
planning/services/fact_fields.py planning/services/number_check.py
planning/services/requirement_facts.py planning/services/requirement_quantities.py planning/services/solve.py
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
planning/web/m1.mjs
planning/web/drafts.mjs planning/web/flow.mjs planning/web/index.html
planning/web/model-status.mjs planning/web/progress.mjs planning/web/settings.mjs planning/web/timing.mjs planning/web/questions.mjs
planning/web/roles.mjs planning/web/text.mjs planning/web/values.mjs planning/web/marquee.mjs
planning/web/library.mjs planning/web/compare.mjs
planning/agents/extraction.py planning/knowledge/drafts.py planning/knowledge/sources.py
planning/services/entity_followup.py
planning/services/coastal.py planning/services/model_switch.py planning/services/suggestions.py
planning/web/i18n-en.mjs planning/web/i18n.mjs planning/web/lang.js
planning/web/records.mjs planning/web/report.mjs planning/workflow/model_log.py
planning/workflow/__init__.py planning/workflow/activity.py
planning/workflow/planning_graph.py planning/workflow/requirements_graph.py
planning/workflow/task_service.py planning/workflow/task_store.py
""".split())
SOURCE_SUFFIXES = {".py", ".js", ".mjs", ".html", ".css", ".json"}
GENERATED = {"VERSION", "BUILD_INFO.json", "MANIFEST.json"}
REPARSE_POINT = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
REQUIRED_FILES = ROOT_FILES | SOURCE_FILES | DOCUMENT_FILES | VALIDATION_FILES
VERSION_PATTERN = re.compile(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?\Z")


def permitted(name):
    """An explicit source allowlist; no broad worktree traversal or runtime assets."""
    if not isinstance(name, str):
        return False
    path = PurePosixPath(name)
    if (not name or "\\" in name or path.is_absolute() or ".." in path.parts
            or path.as_posix() != name):
        return False
    if any(part.startswith(".") or part in {"__pycache__", "models", "runtime", "outputs"}
           for part in path.parts):
        return False
    return name in REQUIRED_FILES or name in GENERATED


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
    names = REQUIRED_FILES
    unlisted = set()
    for folder in ("planning", "formula_rag"):
        base = root / folder
        if base.is_symlink() or (base.exists() and bool(
                getattr(base.lstat(), "st_file_attributes", 0) & REPARSE_POINT)):
            raise ValueError(f"symlink or reparse point refused: {folder}")
        for directory, folders, files in os.walk(base, followlinks=False):
            for part in folders + files:
                path = Path(directory) / part
                if path.is_symlink() or bool(getattr(path.lstat(), "st_file_attributes", 0) & REPARSE_POINT):
                    raise ValueError(f"symlink or reparse point refused: {path.relative_to(root)}")
            for part in files:
                path = Path(directory) / part
                if path.suffix in SOURCE_SUFFIXES and path.relative_to(root).as_posix() not in names:
                    unlisted.add(path.relative_to(root).as_posix())
    if unlisted:
        raise ValueError("new source needs explicit release review: " + ", ".join(sorted(unlisted)))
    # These are all additional immutable inputs used by the existing fingerprint ABI.
    immutable = {p.relative_to(root).as_posix()
                 for pattern in ("knowledge/facts/*.json", "knowledge/documents/*.json",
                                 "knowledge/documents/simulated/*.md") for p in root.glob(pattern)}
    if immutable - names:
        raise ValueError("new data needs explicit release review: " + ", ".join(sorted(immutable - names)))
    missing_on_disk = {name for name in names if not (root / name).is_file()}
    if missing_on_disk:
        raise ValueError("missing release inputs: " + ", ".join(sorted(missing_on_disk)))
    for name in names:
        checked_file(root, name)
    return sorted(names)


def git_value(root, *args, input_text=None):
    result = subprocess.run(["git", "--no-optional-locks", *args], cwd=root,
                            input=input_text, capture_output=True, text=True, encoding="utf-8", check=False)
    if result.returncode:
        raise RuntimeError("Git metadata unavailable: " + result.stderr.strip())
    return result.stdout.strip()


def source_identity(root):
    if Path(git_value(root, "rev-parse", "--show-toplevel")).resolve() != root.resolve():
        raise ValueError("release root must be its Git worktree top-level")
    commit = git_value(root, "rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("invalid source commit")
    committed = {}
    for entry in git_value(root, "ls-tree", "-r", "-z", "HEAD").split("\0"):
        if entry:
            metadata, name = entry.split("\t", 1)
            mode, kind, blob = metadata.split()
            if kind == "blob" and mode in {"100644", "100755"}:
                committed[name] = blob
    names = sorted(REQUIRED_FILES)
    # Read paths directly through Git's clean filters. Index flags such as
    # assume-unchanged cannot conceal changed source, while CRLF conversion stays valid.
    blobs = git_value(root, "hash-object", "--stdin-paths",
                      input_text="\n".join(names) + "\n").splitlines()
    if len(blobs) != len(names):
        raise ValueError("Git source blob identity incomplete")
    modified = [name for name, blob in zip(names, blobs)
                if name in committed and committed[name] != blob]
    return (commit, git_value(root, "symbolic-ref", "--quiet", "--short", "HEAD")
            if git_value(root, "rev-parse", "--abbrev-ref", "HEAD") != "HEAD" else "HEAD",
            git_value(root, "status", "--porcelain", "--untracked-files=all"),
            sorted(REQUIRED_FILES - committed.keys()), modified)


def inputs_digest(payloads):
    """Identity of exactly the packaged source bytes; independent of Git newline conversion."""
    digests = {name: hashlib.sha256(data).hexdigest() for name, data in sorted(payloads.items())}
    return hashlib.sha256(json.dumps(digests, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def source_payloads(root, names):
    payloads = {name: checked_file(root, name).read_bytes() for name in names}
    for name, data in payloads.items():
        if not data.strip() and not name.endswith("/__init__.py"):
            raise ValueError(f"empty release input: {name}")
    return payloads


def git_blob_payloads(root, names, commit):
    """Read exact reviewed HEAD bytes, without checkout or text-mode decoding."""
    entries = {}
    for entry in git_value(root, "ls-tree", "-r", "-z", commit).split("\0"):
        if entry:
            metadata, name = entry.split("\t", 1)
            mode, kind, object_id = metadata.split()
            entries[name] = (mode, kind, object_id)
    object_ids = []
    for name in names:
        mode, kind, object_id = entries.get(name, (None, None, None))
        if (mode not in {"100644", "100755"} or kind != "blob"
                or not re.fullmatch(r"[0-9a-f]{40}", object_id or "")):
            raise ValueError(f"reviewed Git blob unavailable: {name}")
        object_ids.append(object_id)
    run = subprocess.run(["git", "--no-optional-locks", "cat-file", "--batch"], cwd=root,
                         input=("\n".join(object_ids) + "\n").encode("ascii"),
                         capture_output=True, timeout=60, check=False)
    if run.returncode:
        raise RuntimeError("Git blob read failed: " + run.stderr.decode("utf-8", errors="replace").strip())
    payloads, offset = {}, 0
    for name, expected in zip(names, object_ids):
        end = run.stdout.find(b"\n", offset)
        if end < 0:
            raise ValueError("incomplete Git batch header")
        header = run.stdout[offset:end].split(b" ")
        if (len(header) != 3 or header[0] != expected.encode("ascii") or header[1] != b"blob"
                or not re.fullmatch(rb"(?:0|[1-9][0-9]*)", header[2])):
            raise ValueError("Git batch object identity/type/length mismatch")
        size = int(header[2])
        if size > 20 * 1024 * 1024:
            raise ValueError("Git blob exceeds source-package member limit")
        start, stop = end + 1, end + 1 + size
        if stop >= len(run.stdout) or run.stdout[stop:stop + 1] != b"\n":
            raise ValueError("incomplete Git batch payload")
        data = run.stdout[start:stop]
        actual = hashlib.sha1(b"blob " + str(size).encode("ascii") + b"\0" + data).hexdigest()
        if actual != expected:
            raise ValueError("Git batch blob content hash mismatch")
        if not data.strip() and not name.endswith("/__init__.py"):
            raise ValueError(f"empty release input: {name}")
        payloads[name], offset = data, stop + 1
    if offset != len(run.stdout):
        raise ValueError("unexpected trailing Git batch data")
    return payloads


def core_autocrlf(root):
    run = subprocess.run(["git", "--no-optional-locks", "config", "--get", "core.autocrlf"],
                         cwd=root, capture_output=True, text=True, encoding="utf-8", check=False)
    if run.returncode not in {0, 1}:
        raise RuntimeError("Git core.autocrlf query failed: " + run.stderr.strip())
    return run.stdout.strip() if run.returncode == 0 else None


def fingerprint_function(root):
    spec = importlib.util.spec_from_file_location("commplan_release_build_info", root / "planning/build_info.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.build_fingerprint


def payload_fingerprint(root, payloads):
    """Run the reviewed fingerprint function over the actual member bytes."""
    fingerprint = fingerprint_function(root)
    with tempfile.TemporaryDirectory(prefix="commplan-source-bytes-") as temporary:
        tree = Path(temporary)
        for name, data in payloads.items():
            path = tree.joinpath(*PurePosixPath(name).parts)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return fingerprint(tree)


def check_output(root, output):
    """Keep generated output out of source identity and refuse linked destinations/overwrites."""
    if output.exists() or output.is_symlink():
        raise ValueError("release output already exists: " + str(output))
    current = output.parent
    while current != current.parent:
        if current.is_symlink() or (current.exists() and bool(
                getattr(current.lstat(), "st_file_attributes", 0) & REPARSE_POINT)):
            raise ValueError("symlink or reparse output directory refused")
        current = current.parent
    if output.is_relative_to(root):
        check = subprocess.run(["git", "--no-optional-locks", "check-ignore", "--quiet", "--",
                                output.relative_to(root).as_posix()], cwd=root, check=False)
        if check.returncode != 0:
            raise ValueError("release output must be Git-ignored or outside source tree")


def build(root=ROOT, output=None, version=VERSION, require_clean=False):
    if not isinstance(version, str) or not VERSION_PATTERN.fullmatch(version):
        raise ValueError("invalid release version")
    source_root = Path(root).absolute()
    for current in (source_root, *source_root.parents):
        if current.is_symlink() or bool(getattr(current.lstat(), "st_file_attributes", 0) & REPARSE_POINT):
            raise ValueError("symlink or reparse source root refused")
    root = Path(root).resolve()
    output = (Path(output).absolute() if output else
              root / "outputs" / "releases" / f"commplan-agent-v{version}-source.zip")
    check_output(root, output)
    names = source_files(root)
    identity = source_identity(root)
    workspace_payloads = source_payloads(root, names)
    workspace_fingerprint = fingerprint_function(root)(root)
    autocrlf = core_autocrlf(root)

    commit, _, status, uncommitted_inputs, modified_inputs = identity
    dirty = bool(status or uncommitted_inputs or modified_inputs)
    if require_clean and dirty:
        raise ValueError("formal release requires a clean source commit")
    payloads = git_blob_payloads(root, names, commit) if require_clean else dict(workspace_payloads)
    fingerprint = payload_fingerprint(root, payloads)
    info = {
        "version": version,
        "source_commit": commit,
        "source_dirty": dirty,
        "source_inputs_sha256": inputs_digest(payloads),
        "source_status_sha256": hashlib.sha256(status.encode()).hexdigest(),
        "source_uncommitted_inputs": uncommitted_inputs,
        "source_modified_inputs": modified_inputs,
        "source_content_mode": "git-blobs" if require_clean else "worktree-bytes",
        "workspace_build_fingerprint": workspace_fingerprint,
        "source_core_autocrlf": autocrlf,
        "built_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "intended_platform": "Windows, Python 3.12",
        "build_fingerprint": fingerprint,
        "validation_record": VALIDATION_RECORD,
        "package_type": PACKAGE_TYPE,
        "acceptance_status": "NOT_EVALUATED",
    }
    payloads["VERSION"] = (version + "\n").encode("utf-8")
    payloads["BUILD_INFO.json"] = (json.dumps(info, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    manifest = {
        "format": 1,
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(payloads.items())},
    }
    payloads["MANIFEST.json"] = (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=".commplan-building-", suffix=".zip", dir=output.parent)
    os.close(handle)
    temporary = Path(temporary)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for name, data in sorted(payloads.items()):
                archive.writestr(name, data)
        if (source_identity(root) != identity or source_files(root) != names
                or source_payloads(root, names) != workspace_payloads
                or fingerprint_function(root)(root) != workspace_fingerprint
                or core_autocrlf(root) != autocrlf):
            raise ValueError("source changed during release build; no archive published")
        check_output(root, output)
        # Same-directory hard links publish atomically on the supported NTFS destination.
        # An unsupported filesystem fails without overwriting or leaving a partial archive.
        os.link(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
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
