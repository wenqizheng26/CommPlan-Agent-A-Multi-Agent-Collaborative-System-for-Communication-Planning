"""Small independent FILE_PAYLOAD fixtures; no project/Git/model resources are captured."""
from __future__ import annotations

import copy
import ctypes
import hashlib
import json
import os
from pathlib import Path
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import archive_common as common
import project_archive as archive


class PathContractTests(unittest.TestCase):
    def test_windows_path_unicode_case_and_prefix_collisions_are_rejected(self):
        for name in ("../x", "/x", "C:/x", "//host/x", "a\\x", "a//x", "./a", "a/../x",
                     "NUL", "con.txt", "LPT¹.log", "a:stream", "a.", "a ", "a/", "a\0x", "a?x"):
            with self.subTest(name=name), self.assertRaises(common.ArchiveError):
                common.safe_member(name)
        for pairs in ([('A', False), ('a', False)], [('é', False), ('e\u0301', False)],
                      [('a', False), ('a/b', False)], [('a/', True), ('a', False)]):
            with self.subTest(pairs=pairs), self.assertRaises(common.ArchiveError):
                common.member_table(pairs)
        self.assertEqual(common.safe_member('project/中文 空格/.git/config'), 'project/中文 空格/.git/config')

    def test_json_duplicate_keys_nonfinite_and_unsafe_stream_names_fail(self):
        with tempfile.TemporaryDirectory(prefix='commplan-b3c-json-') as area:
            path = Path(area) / 'input.json'
            for text in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":Infinity}'):
                path.write_text(text, encoding='utf-8')
                with self.assertRaises(common.ArchiveError):
                    common.read_json(path)
        for name in (':../../escape:$DATA', ':a:b:$DATA', ':a:$INDEX_ALLOCATION', ':\0:$DATA', ':\\x:$DATA', ':$DATA'):
            with self.subTest(name=name), self.assertRaises(common.ArchiveError):
                common.stream_path('C:/fixture/file', name)


@unittest.skipUnless(os.name == 'nt', 'actual Windows file identity/streams/ACL fixture required')
class FilePayloadTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='commplan-b3c-fixture-')
        self.addCleanup(self.temporary.cleanup)
        self.area = Path(self.temporary.name)
        self.source = self.area / '源 空格'
        self.source.mkdir()
        (self.source / '中文 空目录').mkdir()
        (self.source / '.git').mkdir()
        (self.source / '.git/config').write_bytes(b'[raw]\r\npath = E:/old/source\r\n')
        (self.source / '.gitignore').write_bytes(b'ignored.bin\n')
        (self.source / 'ignored.bin').write_bytes(b'ignored-but-preserved\x00\xff')
        (self.source / '中文.txt').write_bytes('原字节\r\n'.encode('utf-8'))
        (self.source / 'small.gguf').write_bytes(bytes(range(256)) * 4)
        with zipfile.ZipFile(self.source / 'inner.zip', 'w') as inner:
            inner.writestr('../ordinary-inner-name', b'not extracted')
        (self.source / '.hidden-empty').mkdir()
        function = common.kernel.SetFileAttributesW
        function.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong]
        self.assertTrue(function(str(self.source / '.hidden-empty'), 0x12))
        self.plan_path = self.area / 'plan.json'
        self.window_path = self.area / 'window.json'
        self.destination = self.area / 'batch'

    def prepare(self, dependencies=None):
        value = archive.plan(self.source, dependencies or [], self.plan_path)
        common.write_exclusive(self.window_path, common.json_bytes({
            'scope': 'FILE_PAYLOAD', 'window_id': 'fixture-window-1', 'source_writers_stopped': True,
            'approved_root_paths': [r['path'] for r in value['roots']]}))
        return value

    def complete(self):
        self.prepare()
        return archive.capture(self.plan_path, self.window_path, self.destination)

    def failed_capture(self, hook):
        self.prepare()
        with self.assertRaises((common.ArchiveError, OSError)):
            archive.capture(self.plan_path, self.window_path, self.destination, hook=hook)
        self.assertFalse((self.destination / 'FILE_PAYLOAD_COMPLETE.json').exists())
        self.assertFalse((self.destination / 'COMPLETE.json').exists())
        self.assertEqual(common.read_json(self.destination / 'FAILURE.json')['status'], 'INCOMPLETE')

    def reseal_checksums(self):
        value = common.read_json(self.destination / 'CHECKSUMS.json')
        for name in value['files']:
            size, digest = common.sha256_file(self.destination / name)
            value['files'][name] = {'size': size, 'sha256': digest}
        (self.destination / 'CHECKSUMS.json').write_bytes(common.json_bytes(value))
        digest = common.sha256_file(self.destination / 'CHECKSUMS.json')[1]
        marker = common.read_json(self.destination / 'FILE_PAYLOAD_COMPLETE.json')
        marker['checksums_sha256'] = digest
        (self.destination / 'FILE_PAYLOAD_COMPLETE.json').write_bytes(common.json_bytes(marker))
        return digest

    def test_complete_payload_keeps_raw_ignored_nested_and_hidden_empty_entries(self):
        result = self.complete()
        self.assertEqual(archive.verify(self.destination, result['checksums_sha256'])['file_payload_integrity'], 'PASS')
        rows = archive._read_jsonl(self.destination / 'files.jsonl')
        with zipfile.ZipFile(self.destination / 'payload.zip') as package:
            self.assertIn('project/中文 空目录/', package.namelist())
            self.assertIn('project/.hidden-empty/', package.namelist())
            for relative in ('inner.zip', 'ignored.bin', '.git/config', '中文.txt'):
                self.assertEqual(package.read('project/' + relative), (self.source / relative).read_bytes())
            self.assertNotIn('../ordinary-inner-name', package.namelist())
        self.assertTrue(all(row['before'] == row['captured'] == row['after'] for row in rows))
        metadata = common.read_json(self.destination / 'ARCHIVE_INFO.json')
        self.assertEqual(metadata['acl_restoration'], 'RECORD_ONLY')
        self.assertTrue(all(row['observation']['security_metadata']['sacl'] == 'NOT_READ' for row in rows))
        self.assertFalse((self.destination / 'COMPLETE.json').exists())
        self.assertEqual(metadata['git_history_recovery'], 'NOT_RUN')
        # verify has no dependency on the original files or their active Git pointers.
        with patch.object(archive, 'snapshot', side_effect=AssertionError('verify accessed source')):
            self.assertEqual(archive.verify(self.destination, result['checksums_sha256'])['status'], 'FILE_PAYLOAD_COMPLETE')

    def test_real_default_file_ads_and_directory_ads_have_exact_separate_members(self):
        file = self.source / '中文.txt'
        directory = self.source / '中文 空目录'
        Path(str(file) + ':证据:$DATA').write_bytes(b'file-ads\x00\xff')
        Path(str(directory) + ':目录流:$DATA').write_bytes(b'directory-ads')
        result = self.complete()
        rows = archive._read_jsonl(self.destination / 'files.jsonl')
        named = [(row, stream) for row in rows for stream in row['streams'] if not stream['is_default']]
        self.assertEqual(len(named), 2)
        with zipfile.ZipFile(self.destination / 'payload.zip') as package:
            for row, stream in named:
                self.assertTrue(stream['archive_member'].startswith('streams/'))
                self.assertNotIn(':', stream['archive_member'])
                self.assertEqual(package.read(stream['archive_member']), Path(common.stream_path(self.source / row['relative_path'], stream['name'])).read_bytes())
        self.assertEqual(archive.verify(self.destination, result['checksums_sha256'])['streams_integrity'], 'PASS')

    def test_real_hardlinks_keep_each_path_member_and_record_outside_alias_boundary(self):
        original = self.source / 'ignored.bin'
        os.link(original, self.source / 'second.bin')
        os.link(original, self.area / 'outside-alias.bin')
        result = self.complete()
        groups = common.read_json(self.destination / 'dependencies.json')['hardlinks']
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]['link_count'], 3)
        self.assertEqual(groups[0]['in_scope_alias_count'], 2)
        self.assertEqual(groups[0]['outside_scope_aliases'], 1)
        with zipfile.ZipFile(self.destination / 'payload.zip') as package:
            self.assertEqual(package.read('project/ignored.bin'), package.read('project/second.bin'))
        self.assertEqual(archive.verify(self.destination, result['checksums_sha256'])['hardlink_topology_recovery'], 'NOT_RUN')

    def junction(self, path, target):
        run = subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(path), str(target)], capture_output=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)

    def short_path(self, path):
        function = common.kernel.GetShortPathNameW
        function.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_ulong]
        function.restype = ctypes.c_ulong
        buffer = ctypes.create_unicode_buffer(32768)
        size = function(str(path), buffer, len(buffer))
        self.assertTrue(0 < size < len(buffer), ctypes.get_last_error())
        result = Path(buffer.value)
        self.assertTrue(os.path.samefile(result, path))
        # This fixture requires real short aliases, like RUNNER~1 in Windows CI.
        self.assertNotEqual(str(result).casefold(), str(path).casefold())
        return result

    def test_short_root_alias_keeps_original_path_and_resolves_internal_junction(self):
        long_source = self.source.resolve(strict=True)
        self.junction(long_source / 'linked-dir', long_source / '中文 空目录')
        self.source = self.short_path(long_source)
        result = self.complete()
        planned = common.read_json(self.plan_path)
        self.assertEqual(planned['roots'][0]['path'], str(self.source))
        links = archive._read_jsonl(self.destination / 'links.jsonl')
        target_id = archive._entry_id('project', '中文 空目录')
        self.assertEqual(links[0]['target_entry_id'], target_id)
        self.assertEqual(links[0]['relation'], 'internal')
        self.assertEqual(archive.verify(self.destination, result['checksums_sha256'])['status'], 'FILE_PAYLOAD_COMPLETE')

    def test_short_alias_does_not_bypass_overlap_output_or_reparse_checks(self):
        long_source = self.source.resolve(strict=True)
        short_source = self.short_path(long_source)
        with self.assertRaisesRegex(common.ArchiveError, 'overlapping capture roots'):
            archive.roots_for(long_source, [{'dependency_id': 'alias', 'path': str(short_source)}])
        with self.assertRaisesRegex(common.ArchiveError, 'output overlaps'):
            archive.plan(short_source, [], long_source / 'self-plan.json')
        with self.assertRaisesRegex(common.ArchiveError, 'output overlaps'):
            archive.plan(long_source, [], short_source / 'self-plan.json')
        link = self.area.resolve(strict=True) / 'linked source ancestor'
        self.junction(link, long_source)
        alias = self.short_path(link)
        with self.assertRaisesRegex(common.ArchiveError, 'reparse path component'):
            archive.plan(alias / '中文 空目录', [], self.plan_path)

    def test_short_external_root_alias_still_requires_exact_registration(self):
        external = self.area.resolve(strict=True) / 'external long resource directory'
        external.mkdir()
        (external / 'resource.bin').write_bytes(b'outside data')
        self.junction(self.source / 'linked-resource', external)
        with self.assertRaisesRegex(common.ArchiveError, 'exact capture root'):
            archive.plan(self.source, [], self.plan_path)
        short_external = self.short_path(external)
        self.prepare([{'dependency_id': 'runtime', 'path': str(short_external)}])
        result = archive.capture(self.plan_path, self.window_path, self.destination)
        links = archive._read_jsonl(self.destination / 'links.jsonl')
        self.assertEqual(links[0]['relation'], 'registered_external')
        self.assertEqual(links[0]['target_entry_id'], archive._entry_id('runtime', ''))
        self.assertEqual(archive.verify(self.destination, result['checksums_sha256'])['status'], 'FILE_PAYLOAD_COMPLETE')

    def test_real_junction_records_target_without_recursing_or_duplicating_it(self):
        self.junction(self.source / 'linked-dir', self.source / '中文 空目录')
        result = self.complete()
        links = archive._read_jsonl(self.destination / 'links.jsonl')
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]['reparse_type'], 'junction')
        self.assertTrue(links[0]['target_captured'])
        with zipfile.ZipFile(self.destination / 'payload.zip') as package:
            self.assertFalse(any(name.startswith('project/linked-dir') for name in package.namelist()))
        self.assertEqual(archive.verify(self.destination, result['checksums_sha256'])['relations_recorded'], 'PASS')

    def test_unregistered_external_link_fails_and_exact_dependency_is_captured_once(self):
        external = self.area / 'external'
        external.mkdir()
        (external / 'resource.bin').write_bytes(b'precise external target')
        self.junction(self.source / 'linked-resource', external)
        with self.assertRaisesRegex(common.ArchiveError, 'exact capture root'):
            archive.plan(self.source, [], self.plan_path)
        self.assertFalse(self.plan_path.exists())
        self.prepare([{'dependency_id': 'runtime', 'path': str(external)}])
        result = archive.capture(self.plan_path, self.window_path, self.destination)
        with zipfile.ZipFile(self.destination / 'payload.zip') as package:
            self.assertEqual(package.read('dependencies/runtime/resource.bin'), b'precise external target')
            self.assertFalse(any('linked-resource/' in name for name in package.namelist()))
        self.assertEqual(archive.verify(self.destination, result['checksums_sha256'])['members'], result['members'])

    def test_output_inside_source_or_via_reparse_and_existing_outputs_are_refused(self):
        with self.assertRaises(common.ArchiveError):
            archive.plan(self.source, [], self.source / 'self-plan.json')
        self.junction(self.area / 'output-alias', self.source)
        with self.assertRaises(common.ArchiveError):
            archive.plan(self.source, [], self.area / 'output-alias/plan.json')
        self.prepare()
        prior = self.plan_path.read_bytes()
        with self.assertRaises(common.ArchiveError):
            archive.plan(self.source, [], self.plan_path)
        self.assertEqual(self.plan_path.read_bytes(), prior)
        self.destination.mkdir()
        (self.destination / 'keep').write_bytes(b'old batch')
        with self.assertRaises(common.ArchiveError):
            archive.capture(self.plan_path, self.window_path, self.destination)
        self.assertEqual((self.destination / 'keep').read_bytes(), b'old batch')

    def test_publish_race_keeps_placeholder_and_part(self):
        def occupy(stage, row):
            if stage == 'before_publish':
                (self.destination / 'payload.zip').write_bytes(b'other writer owns this file')
        self.failed_capture(occupy)
        self.assertEqual((self.destination / 'payload.zip').read_bytes(), b'other writer owns this file')
        self.assertTrue((self.destination / 'payload.zip.part').exists())

    def test_same_size_bytes_and_membership_changes_do_not_seal(self):
        def change(stage, row):
            if stage == 'before_after_scan':
                path = self.source / 'ignored.bin'
                old = path.stat()
                path.write_bytes(b'X' * old.st_size)
                os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns))
                (self.source / '.git/config').unlink()
                (self.source / 'new.txt').write_bytes(b'new')
        self.failed_capture(change)
        self.assertTrue((self.destination / 'SOURCE_DIFFERENCE.json').exists())

    def test_stream_same_size_change_addition_and_removal_do_not_seal(self):
        host = self.source / '中文.txt'
        Path(str(host) + ':change:$DATA').write_bytes(b'AAAA')
        Path(str(host) + ':remove:$DATA').write_bytes(b'remove')
        def change(stage, row):
            if stage == 'before_after_scan':
                Path(str(host) + ':change:$DATA').write_bytes(b'BBBB')
                Path(str(host) + ':remove:$DATA').unlink()
                Path(str(host) + ':new:$DATA').write_bytes(b'new')
        self.failed_capture(change)

    def test_hardlink_relation_only_change_does_not_seal(self):
        # Adding a scope-external alias leaves source file bytes and times untouched.
        def change(stage, row):
            if stage == 'before_after_scan':
                os.link(self.source / 'ignored.bin', self.area / 'new-outside-alias')
        self.failed_capture(change)

    def test_real_junction_retarget_does_not_seal(self):
        self.junction(self.source / 'linked-dir', self.source / '中文 空目录')
        def change(stage, row):
            if stage == 'before_after_scan':
                os.rmdir(self.source / 'linked-dir')
                self.junction(self.source / 'linked-dir', self.source / '.hidden-empty')
        self.failed_capture(change)

    def test_io_interruption_retains_parts_and_nonzero_cli_failures(self):
        def interrupt(stage, row):
            if stage == 'stream_block':
                raise OSError('fixture interrupted I/O')
        self.failed_capture(interrupt)
        self.assertTrue((self.destination / 'payload.zip.part').exists())
        for command in ('restore', 'verify-restored'):
            run = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(Path(archive.__file__)), command], capture_output=True, encoding='utf-8')
            self.assertEqual(run.returncode, 1)
            self.assertIn('NOT_IMPLEMENTED', run.stderr)

    def test_missing_window_and_changed_plan_source_fail(self):
        self.prepare()
        window = common.read_json(self.window_path)
        window['source_writers_stopped'] = False
        self.window_path.write_bytes(common.json_bytes(window))
        with self.assertRaises(common.ArchiveError):
            archive.capture(self.plan_path, self.window_path, self.destination)
        self.assertFalse(self.destination.exists())
        window['source_writers_stopped'] = True
        self.window_path.write_bytes(common.json_bytes(window))
        (self.source / '中文.txt').write_bytes(b'different after plan')
        with self.assertRaises(common.ArchiveError):
            archive.capture(self.plan_path, self.window_path, self.destination)
        self.assertEqual(common.read_json(self.destination / 'FAILURE.json')['stage'], 'before')

    def test_stream_api_or_unknown_reparse_gap_cannot_be_reported_complete(self):
        with patch.object(common, 'enumerate_streams', side_effect=common.ArchiveError('GAP: streams unsupported')):
            with self.assertRaisesRegex(common.ArchiveError, 'GAP'):
                archive.plan(self.source, [], self.plan_path)
        actual = (self.source / '中文.txt').lstat()
        class FakeStat:
            st_mode = actual.st_mode
            st_size = actual.st_size
            st_mtime_ns = actual.st_mtime_ns
            st_ctime_ns = actual.st_ctime_ns
            st_file_attributes = 0x400
            st_reparse_tag = 0x81234567
        with patch.object(common.Path, 'lstat', return_value=FakeStat()):
            with self.assertRaisesRegex(common.ArchiveError, 'unknown reparse'):
                common.observe(self.source / '中文.txt')

    def test_zip64_streaming_and_allowed_algorithms_are_real_small_fixture_paths(self):
        with patch.object(zipfile, 'ZIP64_LIMIT', 100), patch.object(zipfile, 'ZIP_FILECOUNT_LIMIT', 2):
            result = self.complete()
            self.assertEqual(archive.verify(self.destination, result['checksums_sha256'])['status'], 'FILE_PAYLOAD_COMPLETE')
            with zipfile.ZipFile(self.destination / 'payload.zip') as package:
                file = package.getinfo('project/small.gguf')
                self.assertEqual(file.extract_version, 45)
                self.assertEqual(file.compress_type, zipfile.ZIP_STORED)
                self.assertEqual(package.getinfo('project/中文.txt').compress_type, zipfile.ZIP_DEFLATED)
            self.assertIn(b'PK\x06\x06', (self.destination / 'payload.zip').read_bytes())

    def test_outer_checksums_crc_sha_truncation_and_extra_files_are_rejected(self):
        result = self.complete()
        with self.assertRaisesRegex(common.ArchiveError, 'external'):
            archive.verify(self.destination, '0' * 64)
        path = self.destination / 'payload.zip'
        original = path.read_bytes()
        with zipfile.ZipFile(path) as package:
            info = package.getinfo('project/small.gguf')
            offset = info.header_offset
        _, _, _, _, _, _, _, _, _, name_size, extra_size = struct.unpack('<IHHHHHIIIHH', original[offset:offset + 30])
        modified = bytearray(original)
        modified[offset + 30 + name_size + extra_size] ^= 1
        path.write_bytes(modified)
        digest = self.reseal_checksums()
        with self.assertRaises((common.ArchiveError, zipfile.BadZipFile)):
            archive.verify(self.destination, digest)
        path.write_bytes(original[:-12])
        digest = self.reseal_checksums()
        with self.assertRaises(zipfile.BadZipFile):
            archive.verify(self.destination, digest)
        path.write_bytes(original)
        digest = self.reseal_checksums()
        (self.destination / 'unlisted').write_bytes(b'extra')
        with self.assertRaises(common.ArchiveError):
            archive.verify(self.destination, digest)

    def test_invalid_zip_members_duplicate_algorithm_or_special_type_are_rejected(self):
        result = self.complete()
        rows = archive._read_jsonl(self.destination / 'files.jsonl')
        planned = common.read_json(self.plan_path)['snapshot']
        original = self.destination / 'payload.zip'
        with zipfile.ZipFile(original) as package:
            members = [(info, package.read(info)) for info in package.infolist()]
        for problem in ('duplicate', 'traversal', 'bzip2', 'symlink'):
            altered = self.area / (problem + '.zip')
            with zipfile.ZipFile(altered, 'w') as package:
                for info, data in members:
                    info = copy.copy(info)
                    if info.filename == 'project/small.gguf':
                        if problem == 'bzip2': info.compress_type = zipfile.ZIP_BZIP2
                        if problem == 'symlink': info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    package.writestr(info, data)
                if problem == 'duplicate': package.writestr(members[-1][0], members[-1][1])
                if problem == 'traversal': package.writestr('../escape', b'bad')
            with self.subTest(problem=problem), self.assertRaises(common.ArchiveError):
                archive._verify_payload(altered, rows, planned)


if __name__ == '__main__':
    unittest.main()
