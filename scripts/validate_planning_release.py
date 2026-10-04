"""Check source-package integrity and optional deterministic prechecks, not M1 acceptance."""

import argparse
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
import zipfile

from build_planning_release import (PACKAGE_TYPE, REQUIRED_FILES, ROOT, VALIDATION_RECORD,
                                    VERSION_PATTERN, fingerprint_function, inputs_digest, permitted)


MAX_FILE = 20 * 1024 * 1024
MAX_TOTAL = 80 * 1024 * 1024
PYTHON_SUITES = ("test_core", "test_teacher_tools", "test_teacher_cases_format",
                 "test_calculation_plans", "test_teacher_path")
NODE_SUITES = ("tests/planning_m1.test.mjs", "tests/planning_report.test.mjs")
LIMITATIONS = [
    "Source precheck uses the selected executable and its installed dependencies; no independent installation is proved.",
    "Selected deterministic Python/Node suites and isolated HTTP smoke are only subsets of the final offline matrix.",
    "Real models, target browser/printing, final teacher acceptance, CI, release and cleanroom installation are not evaluated.",
    "Member hashes prove consistency, not publisher authenticity; verify the externally supplied archive SHA256.",
]


def read_json(archive, name):
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError(f"duplicate JSON key: {name}/{key}")
            out[key] = value
        return out
    def invalid_constant(value):
        raise ValueError(f"invalid JSON number: {name}/{value}")
    return json.loads(archive.read(name), object_pairs_hook=unique, parse_constant=invalid_constant)


def inspect_archive(archive):
    infos = archive.infolist()
    names = [item.filename for item in infos]
    if len(names) != len(set(names)) or len(names) != len({name.casefold() for name in names}):
        raise ValueError("duplicate ZIP member names")
    if "MANIFEST.json" not in names or "BUILD_INFO.json" not in names or "VERSION" not in names:
        raise ValueError("release metadata missing")
    if not REQUIRED_FILES.issubset(names):
        raise ValueError("required release input missing")
    total = 0
    for item in infos:
        name = item.filename
        path = PurePosixPath(name)
        mode = (item.external_attr >> 16) & 0xFFFF
        if (not permitted(name) or path.as_posix() != name or item.is_dir()
                or item.flag_bits & 1 or (mode and stat.S_IFMT(mode) not in {0, stat.S_IFREG})
                or item.file_size > MAX_FILE):
            raise ValueError(f"unsafe ZIP member: {name}")
        total += item.file_size
    if total > MAX_TOTAL:
        raise ValueError("ZIP uncompressed size exceeds release limit")
    manifest = read_json(archive, "MANIFEST.json")
    if not isinstance(manifest, dict):
        raise ValueError("invalid manifest")
    digests = manifest.get("files")
    if type(manifest.get("format")) is not int or manifest["format"] != 1 or not isinstance(digests, dict):
        raise ValueError("invalid manifest")
    if set(digests) != set(names) - {"MANIFEST.json"}:
        raise ValueError("manifest membership mismatch")
    for name in names:
        if name == "MANIFEST.json":
            continue
        data = archive.read(name)
        actual = hashlib.sha256(data).hexdigest()
        if not isinstance(digests[name], str) or not re.fullmatch(r"[0-9a-f]{64}", digests[name]) or digests[name] != actual:
            raise ValueError(f"SHA256 mismatch: {name}")
        if name in REQUIRED_FILES and not data.strip() and not name.endswith("/__init__.py"):
            raise ValueError(f"empty release input: {name}")
    info = read_json(archive, "BUILD_INFO.json")
    if (not isinstance(info, dict) or info.get("package_type") != PACKAGE_TYPE
            or info.get("validation_record") != VALIDATION_RECORD
            or info.get("acceptance_status") != "NOT_EVALUATED"
            or not isinstance(info.get("version"), str) or not VERSION_PATTERN.fullmatch(info["version"])
            or not isinstance(info.get("source_commit"), str) or not re.fullmatch(r"[0-9a-f]{40}", info["source_commit"])
            or type(info.get("source_dirty")) is not bool
            or not isinstance(info.get("source_uncommitted_inputs"), list)
            or any(not isinstance(name, str) or name not in REQUIRED_FILES
                   for name in info["source_uncommitted_inputs"])
            or info["source_uncommitted_inputs"] != sorted(set(info["source_uncommitted_inputs"]))
            or (info["source_uncommitted_inputs"] and not info["source_dirty"])
            or not isinstance(info.get("source_modified_inputs"), list)
            or any(not isinstance(name, str) or name not in REQUIRED_FILES
                   for name in info["source_modified_inputs"])
            or info["source_modified_inputs"] != sorted(set(info["source_modified_inputs"]))
            or (info["source_modified_inputs"] and not info["source_dirty"])
            or not isinstance(info.get("build_fingerprint"), str) or not re.fullmatch(r"[0-9a-f]{20}", info["build_fingerprint"])
            or any(not isinstance(info.get(k), str) or not re.fullmatch(r"[0-9a-f]{64}", info[k])
                   for k in ("source_inputs_sha256", "source_status_sha256"))
            or info.get("intended_platform") != "Windows, Python 3.12"):
        raise ValueError("build metadata contract mismatch")
    try:
        timestamp = datetime.fromisoformat(info["built_at_utc"])
        if timestamp.utcoffset() != timedelta(0):
            raise ValueError("timestamp must identify UTC")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("invalid build timestamp") from exc
    if archive.read("VERSION") != (info["version"] + "\n").encode():
        raise ValueError("VERSION mismatch")
    if VALIDATION_RECORD not in names:
        raise ValueError("validation record missing")
    packaged = {name: archive.read(name) for name in names if name in REQUIRED_FILES}
    if info["source_inputs_sha256"] != inputs_digest(packaged):
        raise ValueError("source input identity mismatch")
    content_fields = {"source_content_mode", "workspace_build_fingerprint", "source_core_autocrlf"}
    present = content_fields.intersection(info)
    if present and present != content_fields:
        raise ValueError("partial source content metadata")
    if present:
        if (not isinstance(info["source_content_mode"], str)
                or info["source_content_mode"] not in {"git-blobs", "worktree-bytes"}
                or not isinstance(info["workspace_build_fingerprint"], str)
                or not re.fullmatch(r"[0-9a-f]{20}", info["workspace_build_fingerprint"])
                or (info["source_core_autocrlf"] is not None and (
                    not isinstance(info["source_core_autocrlf"], str)
                    or not re.fullmatch(r"[A-Za-z0-9]{1,32}", info["source_core_autocrlf"])))):
            raise ValueError("source content metadata contract mismatch")
        if info["source_content_mode"] == "git-blobs" and (
                info["source_dirty"] or info["source_uncommitted_inputs"] or info["source_modified_inputs"]):
            raise ValueError("Git blob mode requires clean source metadata")
        if info["source_content_mode"] == "worktree-bytes" and (
                info["workspace_build_fingerprint"] != info["build_fingerprint"]):
            raise ValueError("worktree fingerprint metadata mismatch")
    return info


def isolated_environment():
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    return environment


def offline_prechecks(root, node="node"):
    """Only deterministic test modules; no production model evaluation runners."""
    code = f"""import json,pathlib,platform,sys,unittest
root=pathlib.Path.cwd()
sys.path[:0]=[str(root/'tests'),str(root)]
rows=[]
for name in {list(PYTHON_SUITES)!r}:
    suite=unittest.TestLoader().loadTestsFromName(name)
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    rows.append(dict(suite=name,tests=result.testsRun,failures=len(result.failures),
                     errors=len(result.errors),skipped=len(result.skipped)))
print('PRECHECK_RESULT '+json.dumps(dict(python_version=platform.python_version(),suites=rows)))
sys.exit(any(not row['tests'] or row['failures'] or row['errors'] for row in rows))
"""
    commands = [[sys.executable, "-I", "-B", "-X", "utf8", "-c", code],
                [node, "--test", "--test-reporter=tap", *NODE_SUITES]]
    results = []
    environment = isolated_environment()
    node_version = subprocess.run([node, "--version"], cwd=root, env=environment,
                                  capture_output=True, text=True, encoding="utf-8", timeout=20, check=True).stdout.strip()
    for command in commands:
        run = subprocess.run(command, cwd=root, env=environment, capture_output=True, text=True,
                             encoding="utf-8", timeout=180, check=False)
        if run.returncode:
            raise RuntimeError("unpacked deterministic precheck failed: " + (run.stderr + run.stdout)[-5000:])
        python = command[0] == sys.executable
        if python:
            markers = [line.removeprefix("PRECHECK_RESULT ") for line in run.stdout.splitlines()
                       if line.startswith("PRECHECK_RESULT ")]
            if len(markers) != 1:
                raise RuntimeError("Python precheck counts missing or ambiguous")
            summary = json.loads(markers[0])
            version = summary.pop("python_version")
        else:
            counts = {key: int(value) for key, value in re.findall(
                r"^# (tests|pass|fail|cancelled|skipped|todo) (\d+)\s*$", run.stdout, re.MULTILINE)}
            if not counts.get("tests") or counts.get("fail", -1) != 0 or counts.get("cancelled", -1) != 0:
                raise RuntimeError("Node precheck counts missing or unsuccessful")
            summary, version = {"counts": counts}, node_version
        results.append({"suite": list(PYTHON_SUITES) if python else list(NODE_SUITES),
                        "command": command, "status": "PASS", "exit_code": run.returncode,
                        "runtime_version": version, "summary": summary,
                        "stdout": run.stdout, "stderr": run.stderr})
    return results


def validate(path, smoke=True, offline_tests=False, node="node"):
    path = Path(path).resolve()
    with zipfile.ZipFile(path) as archive:
        info = inspect_archive(archive)
        with tempfile.TemporaryDirectory(prefix="commplan-release-") as temporary:
            root = Path(temporary)
            for item in archive.infolist():
                target = root.joinpath(*PurePosixPath(item.filename).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(item))
            # Run the reviewer's existing fingerprint function over extracted bytes, not archive code.
            actual = fingerprint_function(ROOT)(root)
            if actual != info["build_fingerprint"]:
                raise ValueError("unpacked build fingerprint mismatch")
            result = {"status": "PASS", "archive": str(path),
                      "validation_scope": "source-precheck", "m1_acceptance": "NOT_EVALUATED",
                      "package_type": info["package_type"], "version": info["version"],
                      "source_commit": info["source_commit"], "source_dirty": info["source_dirty"],
                      "source_uncommitted_inputs": info["source_uncommitted_inputs"],
                      "source_modified_inputs": info["source_modified_inputs"],
                      "source_content_mode": info.get("source_content_mode", "legacy-worktree-bytes"),
                      "workspace_build_fingerprint": info.get("workspace_build_fingerprint"),
                      "source_core_autocrlf": info.get("source_core_autocrlf"),
                      "source_inputs_sha256": info["source_inputs_sha256"],
                      "files": len(archive.namelist()), "build_fingerprint": actual,
                      "checks": {"member_integrity": "PASS", "extracted_fingerprint": "PASS",
                                 "deterministic_http_smoke": "NOT_RUN", "offline_subset": "NOT_RUN"},
                      "limitations": list(LIMITATIONS)}
            if smoke:
                # -I prevents inherited import paths; the wrapper adds only extracted source.
                code = ("import pathlib,runpy,sys; root=pathlib.Path.cwd(); "
                        "sys.path.insert(0,str(root)); "
                        "sys.argv=['scripts/planning_smoke.py','--root',str(root)]; "
                        "runpy.run_path(str(root/'scripts/planning_smoke.py'),run_name='__main__')")
                command = [sys.executable, "-I", "-B", "-X", "utf8", "-c", code]
                run = subprocess.run(
                    command, cwd=root, env=isolated_environment(), capture_output=True,
                    text=True, encoding="utf-8", timeout=120, check=False)
                if run.returncode:
                    raise RuntimeError("unpacked HTTP smoke failed: " + (run.stderr or run.stdout)[-3000:])
                result["smoke"] = json.loads(run.stdout)
                if result["smoke"].get("status") != "PASS":
                    raise RuntimeError("unpacked HTTP smoke did not pass")
                result["smoke_command"] = command
                result["smoke_runtime_version"] = sys.version.split()[0]
                result["checks"]["deterministic_http_smoke"] = "PASS"
            if offline_tests:
                result["offline_subset"] = offline_prechecks(root, node)
                result["checks"]["offline_subset"] = "PASS"
            return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--no-smoke", action="store_true", help="inspect only; cannot satisfy release smoke gate")
    parser.add_argument("--offline-tests", action="store_true", help="run the named deterministic Python/Node precheck subset")
    parser.add_argument("--node", default="node", help="Node executable for optional prechecks")
    args = parser.parse_args(argv)
    print(json.dumps(validate(args.archive, smoke=not args.no_smoke, offline_tests=args.offline_tests,
                              node=args.node), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
