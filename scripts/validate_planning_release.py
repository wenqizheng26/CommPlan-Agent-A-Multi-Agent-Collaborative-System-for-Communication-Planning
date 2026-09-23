"""Reject unsafe/tampered ZIPs before extraction, then smoke the unpacked Demo."""

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import stat
import subprocess
import sys
import tempfile
import zipfile

from build_planning_release import REQUIRED_FILES, VALIDATION_RECORD, permitted


MAX_FILE = 20 * 1024 * 1024
MAX_TOTAL = 80 * 1024 * 1024


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
    manifest = json.loads(archive.read("MANIFEST.json"))
    digests = manifest.get("files")
    if manifest.get("format") != 1 or not isinstance(digests, dict):
        raise ValueError("invalid manifest")
    if set(digests) != set(names) - {"MANIFEST.json"}:
        raise ValueError("manifest membership mismatch")
    for name in names:
        if name == "MANIFEST.json":
            continue
        actual = hashlib.sha256(archive.read(name)).hexdigest()
        if digests[name] != actual:
            raise ValueError(f"SHA256 mismatch: {name}")
    info = json.loads(archive.read("BUILD_INFO.json"))
    if (info.get("package_type") != "source-demo-without-model-assets"
            or info.get("validation_record") != VALIDATION_RECORD
            or "version" not in info or "source_commit" not in info
            or "build_fingerprint" not in info):
        raise ValueError("build metadata contract mismatch")
    if archive.read("VERSION").decode("utf-8").strip() != info["version"]:
        raise ValueError("VERSION mismatch")
    if VALIDATION_RECORD not in names:
        raise ValueError("validation record missing")
    return info


def validate(path, smoke=True):
    path = Path(path).resolve()
    with zipfile.ZipFile(path) as archive:
        info = inspect_archive(archive)
        with tempfile.TemporaryDirectory(prefix="commplan-release-") as temporary:
            root = Path(temporary)
            for item in archive.infolist():
                target = root.joinpath(*PurePosixPath(item.filename).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(item))
            fingerprint = subprocess.run(
                [sys.executable, "-B", "-X", "utf8", "-c",
                 "from planning.build_info import build_fingerprint; import pathlib; print(build_fingerprint(pathlib.Path.cwd()))"],
                cwd=root, capture_output=True, text=True, timeout=20, check=False)
            if fingerprint.returncode:
                raise RuntimeError("unpacked fingerprint failed: " + fingerprint.stderr[-2000:])
            actual = fingerprint.stdout.strip()
            if actual != info["build_fingerprint"]:
                raise ValueError("unpacked build fingerprint mismatch")
            result = {"status": "PASS", "archive": str(path),
                      "source_commit": info["source_commit"], "source_dirty": info["source_dirty"],
                      "files": len(archive.namelist()), "build_fingerprint": actual}
            if smoke:
                run = subprocess.run(
                    [sys.executable, "-B", "-X", "utf8", str(root / "scripts/planning_smoke.py"),
                     "--root", str(root)], cwd=root, capture_output=True, text=True,
                    timeout=120, check=False)
                if run.returncode:
                    raise RuntimeError("unpacked HTTP smoke failed: " + (run.stderr or run.stdout)[-3000:])
                result["smoke"] = json.loads(run.stdout)
                if result["smoke"].get("status") != "PASS":
                    raise RuntimeError("unpacked HTTP smoke did not pass")
            return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--no-smoke", action="store_true", help="inspect only; cannot satisfy release smoke gate")
    args = parser.parse_args(argv)
    print(json.dumps(validate(args.archive, smoke=not args.no_smoke), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
