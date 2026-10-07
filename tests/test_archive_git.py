"""Git history rebuild from an original restore; small temporary repositories only."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import archive_common as common
import archive_git
import project_archive as archive


def remove_tree(path):
    def writable(function, target, _):
        os.chmod(target, stat.S_IWRITE)
        function(target)
    shutil.rmtree(path, onexc=writable)


@unittest.skipUnless(os.name == "nt" and shutil.which("git"), "Windows fixture with git")
class GitReconstructTests(unittest.TestCase):
    def setUp(self):
        self.area = Path(tempfile.mkdtemp(prefix="commplan-b3c-git-"))
        self.addCleanup(remove_tree, self.area)
        self.config = self.area / "fixture.gitconfig"
        self.config.write_text("[user]\n\tname = Fixture\n\temail = fixture@example.invalid\n"
                               "[core]\n\tautocrlf = false\n[init]\n\tdefaultBranch = main\n", encoding="utf-8")
        self.env = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
        self.env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=str(self.config))
        self.source = self.area / "project root"
        self.source.mkdir()
        self.app = self.source / "app"
        self.git("init", "-q", str(self.app))
        for index in range(3):
            (self.app / "notes.txt").write_bytes(f"line {index}\n".encode())
            self.git("-C", self.app, "add", "notes.txt")
            self.git("-C", self.app, "commit", "-q", "-m", f"commit {index}")
            if index == 0:
                self.first = self.rev(self.app, "HEAD")
                self.git("-C", self.app, "tag", "-a", "v0", "-m", "annotated")
        self.git("-C", self.app, "branch", "feature", self.first)
        self.git("-C", self.app, "tag", "light", "HEAD~1")
        self.git("-C", self.app, "pack-refs", "--all")
        self.git("-C", self.app, "tag", "-a", "v-loose", "-m", "loose annotated", "HEAD")
        # A commit that only the reflog reaches: dangling for the bundle, kept in the raw objects.
        (self.app / "notes.txt").write_bytes(b"dropped\n")
        self.git("-C", self.app, "commit", "-q", "-am", "dropped")
        self.dropped = self.rev(self.app, "HEAD")
        self.git("-C", self.app, "reset", "-q", "--hard", "HEAD~1")
        self.git("-C", self.app, "worktree", "add", "-q", "--detach", str(self.source / "app-wt"), "HEAD~1")
        self.git("-C", self.app, "worktree", "add", "-q", str(self.source / "app-feat"), "feature")
        (self.app / "notes.txt").write_bytes(b"dirty working copy\n")
        (self.app / "untracked.txt").write_bytes(b"untracked\n")
        self.other = self.source / "other"
        self.git("init", "-q", str(self.other))
        (self.other / "a.txt").write_bytes(b"other\n")
        self.git("-C", self.other, "add", "a.txt")
        self.git("-C", self.other, "commit", "-q", "-m", "other")
        self.git("init", "-q", str(self.source / "empty"))
        self.git("init", "-q", str(self.source / "pub"))
        (self.source / "pub/.git/.git").mkdir()
        (self.source / "pub/.git/.git/HEAD").write_bytes(b"ref: refs/heads/main\n")
        self.expected = {name: self.refs(path) for name, path in (("app", self.app), ("other", self.other))}

    def git(self, *args):
        return subprocess.run(["git", *map(str, args)], env=self.env, check=True, capture_output=True,
                              text=True).stdout

    def rev(self, repository, name):
        return self.git("-C", repository, "rev-parse", name).strip()

    def refs(self, repository):
        rows = self.git("-C", repository, "for-each-ref", "--format=%(refname) %(objectname)").splitlines()
        return dict(line.split(" ") for line in rows)

    def captured(self):
        # Plan through the 8.3 alias when the volume has one (as on CI runners): git wrote the
        # long names into the worktree pointers, so they must not be matched by root text.
        import ctypes
        buffer = ctypes.create_unicode_buffer(1024)
        ctypes.windll.kernel32.GetShortPathNameW(str(self.source), buffer, 1024)
        root = Path(buffer.value) if buffer.value else self.source
        value = archive.plan(root, [], self.area / "plan.json")
        common.write_exclusive(self.area / "window.json", common.json_bytes({
            "scope": "FILE_PAYLOAD", "window_id": "git-window-1", "source_writers_stopped": True,
            "approved_root_paths": [r["path"] for r in value["roots"]]}))
        result = archive.capture(self.area / "plan.json", self.area / "window.json", self.area / "batch")
        archive.restore(self.area / "batch", self.area / "restore", result["checksums_sha256"])
        return result["checksums_sha256"]

    def repository(self, report, suffix):
        return next(r for r in report["repositories"] if r["restored_git_dir"].endswith(suffix))

    def test_history_refs_worktree_heads_and_raw_objects_are_rebuilt_without_touching_originals(self):
        digest = self.captured()
        report = archive_git.reconstruct(self.area / "batch", self.area / "restore", self.area / "git", digest)
        self.assertEqual((report["status"], report["git_history_recovery"]), ("GIT_HISTORY_RECOVERED", "PASS"))
        self.assertEqual(report["original_area"], "UNCHANGED_RESCANNED")
        app = self.repository(report, "project/app/.git")
        self.assertEqual(app["refs"], self.expected["app"])
        self.assertEqual(app["peeled"], {"refs/tags/v0": self.first,
                                         "refs/tags/v-loose": self.rev(self.app, "HEAD")})
        heads = {"refs/archive/b3c/HEAD": self.rev(self.app, "HEAD"),
                 "refs/archive/b3c/worktrees/app-wt": self.rev(self.app, "HEAD~1"),
                 "refs/archive/b3c/worktrees/app-feat": self.first}
        self.assertEqual(app["archive_refs"], heads)
        self.assertGreaterEqual(app["raw_only_objects"], 1)
        self.assertTrue(app["reflogs_original_only"] and app["index_original_only"])
        self.assertIn("ORIG_HEAD", app["pseudo_refs_original_only"])
        self.assertEqual(self.repository(report, "project/other/.git")["refs"], self.expected["other"])
        for suffix in ("project/empty/.git", "project/pub/.git"):
            self.assertEqual(self.repository(report, suffix)["reason"], "NO_COMMIT_HISTORY")
        self.assertEqual([a["kind"] for a in report["anomalies"]], ["nested_git"])
        self.assertEqual(report["unmatched_worktree_pointers"], [])

        # The bundle alone rebuilds every ref, including the detached worktree HEAD.
        bundle = self.area / "git" / app["bundle"]
        listed = dict(reversed(line.split(" ")) for line in self.git("bundle", "list-heads", bundle).splitlines())
        self.assertEqual({k: v for k, v in listed.items() if k != "HEAD"}, dict(self.expected["app"], **heads))
        clone = self.area / "independent"
        self.git("clone", "-q", "--mirror", bundle, clone)
        self.assertEqual(self.refs(clone), dict(self.expected["app"], **heads))
        # The reflog-only commit is not in the bundle, but stays in the derived bare copy of the raw objects.
        missing = subprocess.run(["git", "-C", str(clone), "cat-file", "-e", self.dropped], env=self.env)
        self.assertNotEqual(missing.returncode, 0)
        self.assertEqual(self.git("-C", self.area / "git" / app["derived_bare"], "cat-file", "-t", self.dropped).strip(),
                         "commit")

        trees = {t["admin_name"] or "main": t for t in app["worktrees"]}
        self.assertEqual(set(trees), {"main", "app-wt", "app-feat"})
        for name, tree in trees.items():
            self.assertEqual(tree["status"], "REBUILT")
            self.assertTrue(tree["captured"])
            path = self.area / "git" / tree["rebuilt_path"]
            self.assertEqual(self.rev(path, "HEAD"), tree["head_object"])
            if name != "main":
                self.assertEqual(tree["rebuilt_admin_name"], name)
        self.assertEqual(self.git("-C", self.area / "git" / trees["app-feat"]["rebuilt_path"],
                                  "symbolic-ref", "HEAD").strip(), "refs/heads/feature")
        # Working copies are clean HEAD checkouts; the dirty bytes stay in the original area.
        self.assertEqual((self.area / "git" / trees["main"]["rebuilt_path"] / "notes.txt").read_bytes(), b"line 2\n")
        self.assertEqual((self.area / "restore/original/project/app/notes.txt").read_bytes(), b"dirty working copy\n")
        self.assertFalse((self.area / "git" / trees["main"]["rebuilt_path"] / "untracked.txt").exists())

        result = archive_git.verify_reconstructed(self.area / "batch", self.area / "restore", self.area / "git", digest)
        self.assertEqual(result["verification"], "CURRENT_REFS_AND_BUNDLES_RECHECKED")
        rebuilt = self.area / "git" / app["reconstructed"]
        self.git("-C", rebuilt, "update-ref", "refs/heads/feature", self.rev(self.app, "HEAD"))
        with self.assertRaisesRegex(common.ArchiveError, "reconstructed refs changed"):
            archive_git.verify_reconstructed(self.area / "batch", self.area / "restore", self.area / "git", digest)

    def test_missing_object_alternates_and_bad_destinations_fail_with_record(self):
        loose = next(p for p in (self.other / ".git/objects").rglob("*") if p.is_file() and len(p.parent.name) == 2)
        os.chmod(loose, stat.S_IWRITE)
        loose.unlink()
        digest = self.captured()
        with self.assertRaisesRegex(common.ArchiveError, "incomplete or corrupt"):
            archive_git.reconstruct(self.area / "batch", self.area / "restore", self.area / "git-1", digest)
        self.assertEqual(common.read_json(self.area / "git-1" / archive_git.FAILURE)["status"], "FAIL")
        self.assertFalse((self.area / "git-1" / archive_git.MARKER).exists())
        import ctypes
        buffer = ctypes.create_unicode_buffer(1024)
        ctypes.windll.kernel32.GetShortPathNameW(str(self.area / "restore"), buffer, 1024)
        aliases = [Path(buffer.value) / "inside"] if buffer.value and Path(buffer.value) != self.area / "restore" else []
        for target in (self.area / "git-1", self.area / "restore/inside", self.area / "batch/inside",
                       self.source / "inside", *aliases):
            with self.assertRaisesRegex(common.ArchiveError, "already exists|overlaps"):
                archive_git.reconstruct(self.area / "batch", self.area / "restore", target, digest)

    def test_alternates_are_refused_and_cli_exit_codes(self):
        (self.app / ".git/objects/info/alternates").write_bytes(b"E:/elsewhere/objects\n")
        digest = self.captured()
        cli = [sys.executable, "-B", "-X", "utf8", str(Path(archive.__file__))]
        common_args = ["--archive-dir", self.area / "batch", "--restore-dir", self.area / "restore",
                       "--expected-checksums-sha256", digest]
        failed = subprocess.run(cli + ["reconstruct-git", "--destination", self.area / "git"] + common_args,
                                capture_output=True, encoding="utf-8")
        self.assertEqual(failed.returncode, 1)
        self.assertIn("objects/info/alternates", failed.stderr)
        os.chmod(self.app / ".git/objects/info/alternates", stat.S_IWRITE)
        (self.app / ".git/objects/info/alternates").unlink()
        remove_tree(self.area / "batch")
        remove_tree(self.area / "restore")
        (self.area / "plan.json").unlink()
        (self.area / "window.json").unlink()
        digest = self.captured()
        common_args[-1] = digest
        done = subprocess.run(cli + ["reconstruct-git", "--destination", self.area / "git-ok"] + common_args,
                              capture_output=True, encoding="utf-8")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)["git_history_recovery"], "PASS")
        checked = subprocess.run(cli + ["verify-reconstructed-git", "--destination", self.area / "git-ok"] + common_args,
                                 capture_output=True, encoding="utf-8")
        self.assertEqual(checked.returncode, 0, checked.stderr)


if __name__ == "__main__":
    unittest.main()
