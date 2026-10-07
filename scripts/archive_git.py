"""Rebuild Git history from a verified original restore, in a separate reconstructed area.

The original area keeps the captured bytes; Git never runs there. For each repository with
history this builds a fresh bare copy from the raw objects and refs only (no captured config,
hooks, alternates or index), adds batch refs for every worktree HEAD so detached HEADs are in
the bundle, checks the objects, writes and verifies a full bundle, clones the bundle again and
compares every ref, peeled tag and HEAD with the raw files. Worktrees are checked out again at
new paths under their original admin names. Zero-history and nested `.git` copies are listed
and stay in the original area only.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from archive_common import (ArchiveError, file_identity, json_bytes, plain_absolute, plain_resolved, read_json,
                            sha256_file, within, write_exclusive)

SCHEMA = "commplan-history-git-reconstruct-v1"
ARCHIVE_REFS = "refs/archive/b3c"
REPORT = "GIT_RECONSTRUCT.json"
MARKER = "GIT_RECONSTRUCT_COMPLETE.json"
FAILURE = "GIT_RECONSTRUCT_FAILURE.json"
OBJECT_ID = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")
PSEUDO_REFS = ("ORIG_HEAD", "FETCH_HEAD", "MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "REBASE_HEAD")
ADMIN_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}\Z")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


# --- Git with no inherited configuration ------------------------------------------------------

class Git:
    """Runs git with no system/global config, no hooks, no prompts and no GIT_* overrides."""

    def __init__(self, work):
        self.empty = work / "empty"
        self.empty.mkdir()
        self.config = work / "empty.gitconfig"
        self.config.write_bytes(b"")
        self.env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
        self.env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=str(self.config), GIT_TERMINAL_PROMPT="0",
                        GIT_OPTIONAL_LOCKS="0", GIT_ATTR_NOSYSTEM="1")
        self.version = self("--version").strip()

    def __call__(self, *args, cwd=None, check=True):
        command = ["git", "-c", f"core.hooksPath={self.empty}", "-c", "core.autocrlf=false",
                   "-c", "core.fsmonitor=false", "-c", "core.longpaths=true", *args]
        result = subprocess.run(command, cwd=cwd, env=self.env, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        if check and result.returncode:
            raise ArchiveError(f"git {' '.join(args[:3])} failed: {result.stderr.strip()[:300]}")
        return result.stdout if check else result


# --- reading raw Git files ---------------------------------------------------------------------

def _walk(top):
    """Directories and files under top, never entering a symlink or junction."""
    stack = [top]
    while stack:
        current = stack.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                if entry.is_symlink() or entry.is_junction():
                    continue
                yield entry
                if entry.is_dir(follow_symlinks=False):
                    stack.append(entry.path)


def _text(path):
    return Path(path).read_bytes().decode("utf-8").strip()


def raw_refs(gitdir):
    """Refs, peeled tag values and symbolic refs exactly as the raw files state them."""
    refs, peeled, symbolic = {}, {}, {}
    packed = gitdir / "packed-refs"
    if packed.is_file():
        last = None
        for line in packed.read_bytes().decode("utf-8").splitlines():
            if not line or line.startswith("#"):
                continue
            if line.startswith("^"):
                if last is None or not OBJECT_ID.match(line[1:]):
                    raise ArchiveError("malformed packed-refs peel line")
                peeled[last] = line[1:]
                continue
            object_id, _, name = line.partition(" ")
            if not OBJECT_ID.match(object_id) or not name.startswith("refs/"):
                raise ArchiveError("malformed packed-refs line")
            refs[name], last = object_id, name
    loose = gitdir / "refs"
    if loose.is_dir():
        for entry in _walk(loose):
            if not entry.is_file(follow_symlinks=False):
                continue
            name = "refs/" + Path(entry.path).relative_to(loose).as_posix()
            if name.endswith(".lock"):
                raise ArchiveError(f"ref update was in progress at capture: {name}")
            value = _text(entry.path)
            if value.startswith("ref: "):
                symbolic[name] = value[5:]
            elif OBJECT_ID.match(value):
                refs[name] = value
                peeled.pop(name, None)  # A loose ref replaces the packed one and its peel line.
            else:
                raise ArchiveError(f"malformed loose ref {name}")
    return refs, peeled, symbolic


def _head(path):
    value = _text(path)
    if value.startswith("ref: "):
        return {"symbolic": value[5:]}
    if OBJECT_ID.match(value):
        return {"detached": value}
    raise ArchiveError(f"malformed HEAD {path}")


def _config_features(gitdir):
    """Repository features this rebuild cannot carry; any one makes the recovery incomplete."""
    found = []
    config = gitdir / "config"
    text = config.read_bytes().decode("utf-8", "replace").lower() if config.is_file() else ""
    section = ""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("["):
            section = line.strip("[]").split()[0]
            continue
        key = line.split("=", 1)[0].strip()
        if section == "extensions" and key in {"refstorage", "partialclone"}:
            found.append(f"extensions.{key}")
        if section == "extensions" and key == "objectformat" and line.split("=", 1)[-1].strip() != "sha1":
            found.append("extensions.objectformat")
        if section.startswith("remote") and key == "promisor":
            found.append("remote.promisor")
    for name in ("shallow", "objects/info/alternates", "objects/info/http-alternates"):
        path = gitdir / name
        if path.is_file() and path.stat().st_size:
            found.append(name)
    for name in ("modules", "lfs"):
        if (gitdir / name).is_dir():
            found.append(name)
    return found


def discover(original):
    """Git directories, linked-worktree pointers and anomalies in the restored original area."""
    original = Path(original)
    gitdirs, pointers, anomalies = [], [], []
    for entry in _walk(original):
        if entry.name.lower() != ".git":
            continue
        path = Path(entry.path)
        relative = path.relative_to(original).as_posix()
        if any(part.lower() == ".git" for part in path.relative_to(original).parts[:-1]):
            anomalies.append({"path": relative, "kind": "nested_git", "use": "ORIGINAL_ONLY"})
        elif entry.is_dir(follow_symlinks=False):
            if (path / "HEAD").is_file() and (path / "objects").is_dir():
                gitdirs.append(path)
            else:
                anomalies.append({"path": relative, "kind": "incomplete_git_directory", "use": "ORIGINAL_ONLY"})
        else:
            value = _text(path)
            if not value.startswith("gitdir: "):
                anomalies.append({"path": relative, "kind": "unrecognized_git_file", "use": "ORIGINAL_ONLY"})
            else:
                pointers.append({"path": path, "relative": relative, "target_text": value[8:]})
    return sorted(gitdirs), pointers, anomalies


def _mapper(value, destination):
    """Old absolute path text -> restored path, through the captured root list (text only)."""
    roots = [(os.path.normcase(os.path.abspath(root["path"])), destination / "original" / root["prefix"])
             for root in value["roots"] if root["kind"] == "directory"]

    def mapped(text):
        old = os.path.normcase(os.path.abspath(text.replace("/", "\\")))
        for prefix, restored in sorted(roots, key=lambda item: -len(item[0])):
            if old == prefix or old.startswith(prefix.rstrip("\\") + "\\"):
                return restored / old[len(prefix):].lstrip("\\") if old != prefix else restored
        return None
    return mapped


# --- one repository ----------------------------------------------------------------------------

def _repo_id(relative):
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", relative.removeprefix("original/").removesuffix("/.git")).strip("-.")
    return f"{slug[:60] or 'repo'}-{hashlib.sha256(relative.encode('utf-8')).hexdigest()[:8]}"


def _copy_raw(gitdir, derived):
    """Objects and refs only: never config, hooks, info, index or logs from the capture."""
    for name in ("objects", "refs"):
        source = gitdir / name
        if not source.is_dir():
            continue
        for entry in _walk(source):
            relative = Path(entry.path).relative_to(gitdir)
            if relative.as_posix() in {"objects/info/alternates", "objects/info/http-alternates"}:
                continue
            target = derived / relative
            if entry.is_dir(follow_symlinks=False):
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(entry.path, target)
    if (gitdir / "packed-refs").is_file():
        shutil.copyfile(gitdir / "packed-refs", derived / "packed-refs")


def _for_each_ref(git, repository):
    refs, peeled = {}, {}
    for line in git("-C", str(repository), "for-each-ref", "--format=%(refname) %(objectname) %(*objectname)").splitlines():
        name, object_id, peel = (line.split(" ") + [""])[:3]
        refs[name] = object_id
        if peel:
            peeled[name] = peel
    return refs, peeled


def _peeled(git, repository, refs):
    found = {}
    for name, object_id in refs.items():
        if git("-C", str(repository), "cat-file", "-t", object_id).strip() == "tag":
            found[name] = git("-C", str(repository), "rev-parse", f"{object_id}^{{}}").strip()
    return found


def _worktrees(gitdir, mapped, pointers):
    """The main worktree and every linked worktree recorded in this repository."""
    rows = [{"admin_name": None, "head": _head(gitdir / "HEAD"),
             "original_path": gitdir.parent, "captured": True, "main": True}]
    admin = gitdir / "worktrees"
    if admin.is_dir():
        for entry in sorted(admin.iterdir()):
            if not (entry / "HEAD").is_file():
                continue
            if not ADMIN_NAME.match(entry.name):
                raise ArchiveError(f"unsupported worktree admin name {entry.name!r}")
            pointer_text = _text(entry / "gitdir") if (entry / "gitdir").is_file() else ""
            restored_pointer = mapped(pointer_text) if pointer_text else None
            linked = next((p for p in pointers if restored_pointer is not None
                           and os.path.normcase(str(p["path"])) == os.path.normcase(str(restored_pointer))), None)
            back = mapped(linked["target_text"]) if linked else None
            rows.append({"admin_name": entry.name, "head": _head(entry / "HEAD"),
                         "original_pointer_text": pointer_text,
                         "original_path": restored_pointer.parent if restored_pointer else None,
                         "captured": linked is not None and back is not None
                         and os.path.normcase(str(back)) == os.path.normcase(str(entry)),
                         "main": False})
    return rows


def rebuild(git, gitdir, original, work, mapped, pointers):
    relative = gitdir.relative_to(original.parent).as_posix()
    repo_id = _repo_id(relative)
    refs, peeled, symbolic = raw_refs(gitdir)
    head = _head(gitdir / "HEAD")
    row = {"repo_id": repo_id, "restored_git_dir": relative, "head": head, "raw_ref_count": len(refs),
           "symbolic_refs": symbolic, "unsupported": _config_features(gitdir),
           "pseudo_refs_original_only": sorted(name for name in PSEUDO_REFS if (gitdir / name).is_file()),
           "reflogs_original_only": (gitdir / "logs").is_dir(), "index_original_only": (gitdir / "index").is_file()}
    if not refs and "detached" not in head:
        row.update(status="NOT_APPLICABLE", reason="NO_COMMIT_HISTORY", use="ORIGINAL_ONLY")
        return row
    if row["unsupported"]:
        raise ArchiveError(f"{relative}: unsupported repository features {row['unsupported']}")
    if any(name.startswith(ARCHIVE_REFS + "/") for name in refs):
        raise ArchiveError(f"{relative}: captured refs already use {ARCHIVE_REFS}")
    derived = work / "derived" / f"{repo_id}.git"
    git("init", "--bare", "--quiet", f"--template={git.empty}", str(derived))
    _copy_raw(gitdir, derived)
    (derived / "HEAD").write_bytes((gitdir / "HEAD").read_bytes())
    fsck = git("-C", str(derived), "fsck", "--full", "--no-progress", "--no-reflogs", check=False)
    lines = (fsck.stdout + fsck.stderr).splitlines()
    dangling = [line for line in lines if line.startswith("dangling ")]
    problems = [line for line in lines if line and not line.startswith(("dangling ", "notice:", "Checking"))]
    if fsck.returncode or problems:
        raise ArchiveError(f"{relative}: raw objects incomplete or corrupt: {problems[:5]}")
    worktrees = _worktrees(gitdir, mapped, pointers)
    for tree in worktrees:
        target = tree["head"].get("detached") or refs.get(tree["head"].get("symbolic", ""))
        tree["head_object"] = target
        tree["archive_ref"] = f"{ARCHIVE_REFS}/{'HEAD' if tree['main'] else 'worktrees/' + tree['admin_name']}"
        if not target:
            continue
        if git("-C", str(derived), "cat-file", "-e", f"{target}^{{commit}}", check=False).returncode:
            raise ArchiveError(f"{relative}: raw objects incomplete or corrupt: HEAD {target} missing")
        git("-C", str(derived), "update-ref", tree["archive_ref"], target)
    # With every worktree HEAD now named by a ref, its whole history must be present too.
    git("-C", str(derived), "rev-list", "--objects", "--all", "--quiet")
    derived_refs, derived_peeled = _for_each_ref(git, derived)
    original_view = {k: v for k, v in derived_refs.items() if not k.startswith(ARCHIVE_REFS + "/")}
    if original_view != refs:
        raise ArchiveError(f"{relative}: derived refs differ from the raw ref files")
    expected_peeled = _peeled(git, derived, refs)
    if any(peeled.get(name, expected_peeled[name]) != expected_peeled[name] for name in expected_peeled) \
            or set(peeled) - set(expected_peeled):
        raise ArchiveError(f"{relative}: packed-refs peel lines disagree with the tag objects")

    bundle = work / "bundles" / f"{repo_id}.bundle"
    bundle.parent.mkdir(exist_ok=True)
    git("-C", str(derived), "bundle", "create", "--quiet", str(bundle), "--all")
    git("-C", str(derived), "bundle", "verify", "--quiet", str(bundle))
    rebuilt = work / "reconstructed" / f"{repo_id}.git"
    git("clone", "--mirror", "--quiet", "--no-hardlinks", f"--template={git.empty}", str(bundle), str(rebuilt))
    rebuilt_refs, rebuilt_peeled = _for_each_ref(git, rebuilt)
    if rebuilt_refs != derived_refs or rebuilt_peeled != derived_peeled:
        raise ArchiveError(f"{relative}: refs rebuilt from the bundle differ")
    if "symbolic" in head and head["symbolic"] in rebuilt_refs:
        git("-C", str(rebuilt), "symbolic-ref", "HEAD", head["symbolic"])
    git("-C", str(rebuilt), "fsck", "--full", "--no-progress", "--no-dangling")
    git("-C", str(rebuilt), "rev-list", "--objects", "--all", "--quiet")
    raw_objects = len(git("-C", str(derived), "cat-file", "--batch-all-objects", "--batch-check=%(objectname)").split())
    bundle_objects = len(git("-C", str(rebuilt), "cat-file", "--batch-all-objects", "--batch-check=%(objectname)").split())

    for tree in worktrees:
        tree["original_path"] = (tree["original_path"].relative_to(original.parent).as_posix()
                                 if tree["original_path"] is not None else None)
        if not tree["head_object"]:
            tree.update(status="NOT_APPLICABLE", reason="UNBORN_HEAD")
            continue
        name = "main-worktree" if tree["main"] else tree["admin_name"]
        path = work / "worktrees" / repo_id / name
        path.parent.mkdir(parents=True, exist_ok=True)
        branch = tree["head"].get("symbolic", "")
        if branch.startswith("refs/heads/") and branch in rebuilt_refs:
            git("-C", str(rebuilt), "worktree", "add", "--quiet", str(path), branch[len("refs/heads/"):])
        else:
            git("-C", str(rebuilt), "worktree", "add", "--quiet", "--detach", str(path), tree["head_object"])
        if git("-C", str(path), "rev-parse", "HEAD").strip() != tree["head_object"]:
            raise ArchiveError(f"{relative}: rebuilt worktree {name} has another HEAD")
        if git("-C", str(path), "status", "--porcelain", "--untracked-files=all").strip():
            raise ArchiveError(f"{relative}: rebuilt worktree {name} is not a clean checkout")
        admin = Path(git("-C", str(path), "rev-parse", "--absolute-git-dir").strip())
        tree.update(status="REBUILT", rebuilt_path=path.relative_to(work).as_posix(),
                    rebuilt_admin_name=admin.name if not tree["main"] else None,
                    working_changes="ORIGINAL_AREA_ONLY")
        if not tree["main"] and admin.name != tree["admin_name"]:
            raise ArchiveError(f"{relative}: rebuilt worktree admin name {admin.name} != {tree['admin_name']}")
        tree["head"] = dict(tree["head"])
    row.update(status="PASS", refs=refs, peeled=expected_peeled, archive_refs={
                   t["archive_ref"]: t["head_object"] for t in worktrees if t["head_object"]},
               worktrees=worktrees, dangling_in_raw=len(dangling), raw_object_count=raw_objects,
               bundle_object_count=bundle_objects, raw_only_objects=raw_objects - bundle_objects,
               raw_only_objects_kept="ORIGINAL_AND_DERIVED_BARE",
               derived_bare=derived.relative_to(work).as_posix(), bundle=bundle.relative_to(work).as_posix(),
               bundle_size=bundle.stat().st_size, bundle_sha256=sha256_file(bundle)[1],
               reconstructed=rebuilt.relative_to(work).as_posix())
    return row


# --- whole restore -----------------------------------------------------------------------------

def reconstruct(archive, restore_dir, destination, expected_hash):
    from project_archive import _restore_contract, _restore_location, verify_restored
    verify_restored(archive, restore_dir, expected_hash)
    restore_dir = plain_resolved(Path(restore_dir))
    archive = plain_absolute(Path(archive))
    value = read_json(archive / "PLAN.json")
    # Same alias-safe checks as the original restore (archive, saved root text and identities),
    # plus the restore directory itself, by path and by identity.
    destination = _restore_location(destination, archive, value, _restore_contract(value), must_exist=False)
    key = lambda path: (lambda i: (i["volume_serial"], i["file_id"]))(file_identity(plain_absolute(path)))
    restored = key(restore_dir)
    if (within(destination, restore_dir) or within(restore_dir, destination)
            or any(key(ancestor) == restored for ancestor in destination.parents)):
        raise ArchiveError("reconstruct destination overlaps the original restore")
    destination.mkdir(parents=False)
    original = restore_dir / "original"
    try:
        git = Git(destination)
        gitdirs, pointers, anomalies = discover(original)
        mapped = _mapper(value, restore_dir)
        repositories = [rebuild(git, gitdir, original, destination, mapped, pointers) for gitdir in gitdirs]
        claimed = {os.path.normcase(str(original.parent / t["original_path"]))
                   for r in repositories for t in r.get("worktrees", []) if t.get("original_path")}
        stray = [p["relative"] for p in pointers if os.path.normcase(str(p["path"].parent)) not in claimed]
        # The rebuild only reads the original area; prove it is still byte-identical.
        verify_restored(archive, restore_dir, expected_hash)
        history = [r for r in repositories if r["status"] == "PASS"]
        report = {"schema": SCHEMA, "status": "GIT_HISTORY_RECOVERED" if history else "NO_GIT_HISTORY",
                  "checksums_sha256": expected_hash, "git_version": git.version,
                  "git_history_recovery": "PASS" if history else "NOT_APPLICABLE",
                  "repositories": repositories, "unmatched_worktree_pointers": stray, "anomalies": anomalies,
                  "original_area": "UNCHANGED_RESCANNED", "dependency_recovery": "NOT_RUN",
                  "retained_version_independence": "NOT_RUN"}
        write_exclusive(destination / REPORT, json_bytes(report))
        files = {REPORT: sha256_file(destination / REPORT)[1]}
        files.update({r["bundle"]: r["bundle_sha256"] for r in history})
        write_exclusive(destination / MARKER, json_bytes({"schema": SCHEMA, "status": report["status"],
                                                          "checksums_sha256": expected_hash, "files": files}))
        return report
    except Exception as error:
        write_exclusive(destination / FAILURE, json_bytes({"schema": SCHEMA, "status": "FAIL",
                                                           "error_type": type(error).__name__, "error": str(error)}))
        raise


def verify_reconstructed(archive, restore_dir, destination, expected_hash):
    """Read-only re-check: original area, marker and bundle hashes, bundle verify, refs and worktree HEADs."""
    from project_archive import verify_restored
    verify_restored(archive, restore_dir, expected_hash)
    destination = plain_absolute(Path(destination))
    marker = read_json(destination / MARKER)
    if marker.get("schema") != SCHEMA or marker.get("checksums_sha256") != expected_hash:
        raise ArchiveError("invalid reconstruct marker")
    for name, digest in marker["files"].items():
        if sha256_file(destination / name)[1] != digest:
            raise ArchiveError(f"reconstruct file changed: {name}")
    report = read_json(destination / REPORT)
    work = Path(tempfile.mkdtemp(prefix="git-verify-"))
    git = Git(work)
    try:
        for row in report["repositories"]:
            if row["status"] != "PASS":
                continue
            git("-C", str(destination / row["reconstructed"]), "bundle", "verify", "--quiet", str(destination / row["bundle"]))
            refs, _ = _for_each_ref(git, destination / row["reconstructed"])
            if {k: v for k, v in refs.items() if not k.startswith(ARCHIVE_REFS + "/")} != row["refs"] \
                    or {k: v for k, v in refs.items() if k.startswith(ARCHIVE_REFS + "/")} != row["archive_refs"]:
                raise ArchiveError(f"{row['repo_id']}: reconstructed refs changed")
            for tree in row["worktrees"]:
                if tree.get("status") == "REBUILT" and git("-C", str(destination / tree["rebuilt_path"]),
                                                           "rev-parse", "HEAD").strip() != tree["head_object"]:
                    raise ArchiveError(f"{row['repo_id']}: worktree HEAD changed")
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return dict(report, verification="CURRENT_REFS_AND_BUNDLES_RECHECKED")
