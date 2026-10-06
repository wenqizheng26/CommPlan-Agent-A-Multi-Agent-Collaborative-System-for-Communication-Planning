"""Windows pwsh resource-boundary fixtures; no network or acquired EXE execution."""
import base64
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile
import tempfile
import unittest
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts' / 'prepare_delivery_assets.ps1'


def zip_bytes(entries):
    output = io.BytesIO()
    with warnings.catch_warnings():
        # A duplicate is an intentional attack fixture.
        warnings.simplefilter('ignore', UserWarning)
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, data, mode in entries:
                info = zipfile.ZipInfo(name)
                info.create_system = 3
                info.external_attr = mode << 16
                archive.writestr(info, data)
    return output.getvalue()


def tar_bytes(entries, *, gz=False):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w', format=tarfile.PAX_FORMAT) as archive:
        for name, data, kind in entries:
            info = tarfile.TarInfo(name)
            info.type = kind
            if kind in (tarfile.SYMTYPE, tarfile.LNKTYPE):
                info.linkname = '../outside.txt'
            if kind == tarfile.REGTYPE:
                info.size = len(data)
            archive.addfile(info, io.BytesIO(data) if kind == tarfile.REGTYPE else None)
    payload = output.getvalue()
    return gzip.compress(payload) if gz else payload


GOOD_ZIP = [('asset/', b'', stat.S_IFDIR | 0o755),
            ('asset/LICENSE.txt', b'fixture license\n', stat.S_IFREG | 0o644),
            ('asset/sub/empty.txt', b'', stat.S_IFREG | 0o644)]
GOOD_TAR = [('asset/', b'', tarfile.DIRTYPE),
            ('asset/LICENSE.txt', b'fixture license\n', tarfile.REGTYPE),
            ('asset/sub/empty.txt', b'', tarfile.REGTYPE)]


class PlanningDeliveryAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.name != 'nt':
            raise RuntimeError('These security fixtures require Windows; never skip them in Windows CI.')
        cls.pwsh = shutil.which('pwsh')
        if cls.pwsh is None:
            raise RuntimeError('pwsh 7.4+ is required; CI must fail instead of skip.')
        cls.temp = tempfile.TemporaryDirectory(prefix='commplan-assets-')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.base = Path(cls.temp.name)
        cls.outside = cls.base / 'outside'
        cls.outside.mkdir()
        (cls.outside / 'sentinel.txt').write_bytes(b'never change this\n')
        cls.cases = []

        def case(name, payload, *, fmt='Zip', changes=None, preexisting=None):
            run = cls.base / name
            run.mkdir()
            archive = run / 'input.archive'
            archive.write_bytes(payload)
            opts = dict(Mode='Extract', RunRoot=str(run), Archive=str(archive), Format=fmt,
                        ExpectedSize=len(payload), ExpectedSha256=hashlib.sha256(payload).hexdigest(),
                        Destination=str(run / 'output'), ManifestOut=str(run / 'evidence' / 'result.json'),
                        AllowedTopLevel=['asset'])
            opts.update(changes or {})
            if preexisting == 'destination':
                Path(opts['Destination']).mkdir()
                (Path(opts['Destination']) / 'old.txt').write_bytes(b'old destination')
            elif preexisting == 'manifest':
                Path(opts['ManifestOut']).parent.mkdir()
                Path(opts['ManifestOut']).write_bytes(b'old manifest')
            cls.cases.append(dict(id=name, options=opts))
            return run, opts

        good_zip = zip_bytes(GOOD_ZIP)
        cls.good_zip = good_zip
        case('zip_ok', good_zip)
        case('tar_ok', tar_bytes(GOOD_TAR), fmt='Tar')
        case('gzip_ok', tar_bytes(GOOD_TAR, gz=True), fmt='TarGzip')
        long_name = 'asset/' + 'deep/' * 30 + 'long.txt'
        case('pax_ok', tar_bytes([(long_name, b'long fixture', tarfile.REGTYPE)]), fmt='Tar')
        case('sha_bad', good_zip, changes={'ExpectedSha256': '0' * 64})
        case('size_bad', good_zip, changes={'ExpectedSize': len(good_zip) + 1})
        case('existing_output', good_zip, preexisting='destination')
        case('existing_manifest', good_zip, preexisting='manifest')
        run, opts = case('overlap', good_zip)
        opts['ManifestOut'] = str(run / 'output' / 'inside.json')
        # opts must remain the actual case object when changed after insertion.
        cls.cases[-1]['options'] = opts
        run, opts = case('input_overlap', good_zip)
        opts['Destination'] = str(run / 'input.archive' / 'output')
        cls.cases[-1]['options'] = opts
        run, opts = case('outside_destination', good_zip)
        opts['Destination'] = str(cls.outside / 'escape')
        cls.cases[-1]['options'] = opts
        run, opts = case('junction_parent', good_zip)
        junction = run / 'jump'
        subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(junction), str(cls.outside)],
                       check=True, capture_output=True, text=True, timeout=15)
        opts['Destination'] = str(junction / 'escape')
        cls.cases[-1]['options'] = opts

        attacks = ['../outside.txt', '/absolute.txt', '//server/share', 'C:/drive.txt',
                   'asset\\backslash.txt', 'asset/file.txt:stream', 'asset/./dot.txt',
                   'asset//empty.txt', 'asset/NUL.txt', 'asset/COM¹.txt',
                   'asset/trailing.', 'asset/trailing ', 'asset/control\x01.txt',
                   'asset/a?.txt', 'other/file.txt']
        cls.path_ids = []
        for number, name in enumerate(attacks):
            identity = 'path_%02d' % number
            cls.path_ids.append(identity)
            payload = zip_bytes([(name, b'attack', stat.S_IFREG | 0o644)])
            if '\\' in name:
                # Windows ZipInfo normalizes separators while creating the fixture.
                # Restore both header names, preserving their original byte lengths.
                payload = payload.replace(name.replace('\\', '/').encode(), name.encode())
            case(identity, payload)
        case('duplicate', zip_bytes([('asset/a', b'a', stat.S_IFREG)] * 2))
        case('case_duplicate', zip_bytes([('asset/A', b'a', stat.S_IFREG), ('asset/a', b'b', stat.S_IFREG)]))
        case('parent_file', zip_bytes([('asset/sub', b'a', stat.S_IFREG), ('asset/sub/file', b'b', stat.S_IFREG)]))
        case('type_collision', zip_bytes([('asset/sub/', b'', stat.S_IFDIR), ('asset/sub', b'b', stat.S_IFREG)]))
        case('zip_symlink', zip_bytes([('asset/link', b'../outside', stat.S_IFLNK | 0o777)]))
        case('zip_device', zip_bytes([('asset/device', b'', stat.S_IFCHR | 0o600)]))
        dos_reparse = io.BytesIO()
        with zipfile.ZipFile(dos_reparse, 'w') as archive:
            info = zipfile.ZipInfo('asset/link'); info.external_attr = 0x400
            archive.writestr(info, b'../outside')
        case('zip_reparse', dos_reparse.getvalue())
        for identity, kind in [('tar_symlink', tarfile.SYMTYPE), ('tar_hardlink', tarfile.LNKTYPE),
                               ('tar_device', tarfile.CHRTYPE), ('tar_fifo', tarfile.FIFOTYPE),
                               ('tar_sparse', tarfile.GNUTYPE_SPARSE)]:
            case(identity, tar_bytes([('asset/link', b'', kind)]), fmt='Tar')
        case('tar_traversal', tar_bytes([('../outside.txt', b'attack', tarfile.REGTYPE)]), fmt='Tar')
        case('count_limit', good_zip, changes={'MaxMembers': 2})
        case('member_limit', good_zip, changes={'MaxMemberBytes': 2})
        case('total_limit', zip_bytes([('asset/a', b'aaa', stat.S_IFREG), ('asset/b', b'bbb', stat.S_IFREG)]),
             changes={'MaxTotalBytes': 5})
        case('zero_limit', good_zip, changes={'MaxMembers': 0})
        case('overflow_limit', good_zip, changes={'MaxTotalBytes': 9223372036854775807})
        case('missing_allowlist', good_zip, changes={'AllowedTopLevel': []})
        case('wildcard_allowlist', good_zip, changes={'AllowedTopLevel': ['*']})
        case('zip_truncated', good_zip[:-8])
        corrupt_zip = bytearray(zip_bytes([('asset/a', b'payload', stat.S_IFREG)]))
        central = corrupt_zip.index(b'PK\x01\x02')
        corrupt_zip[central + 16] ^= 1
        case('zip_crc', bytes(corrupt_zip))
        tar = tar_bytes(GOOD_TAR)
        case('tar_truncated', tar[:1536], fmt='Tar')
        corrupt_tar = bytearray(tar); corrupt_tar[0] ^= 1
        case('tar_checksum', bytes(corrupt_tar), fmt='Tar')
        case('tar_trailing', tar + b'evil', fmt='Tar')
        corrupt_gzip = bytearray(gzip.compress(tar)); corrupt_gzip[-8] ^= 1
        case('gzip_crc', bytes(corrupt_gzip), fmt='TarGzip')
        case('gzip_bomb', gzip.compress(tar + b'\0' * 100000), fmt='TarGzip',
             changes={'MaxMembers': 10, 'MaxTotalBytes': 100})
        # Malformed extension claims a giant body. It must be rejected before allocation/read.
        header = bytearray(tarfile.TarInfo('pax').tobuf(format=tarfile.USTAR_FORMAT))
        header[156] = ord('x'); header[124:136] = b'77777777777\0'
        header[148:156] = b'        '
        header[148:156] = ('%06o\0 ' % sum(header)).encode('ascii')
        case('giant_pax', bytes(header), fmt='Tar')
        for identity, payload, size, digest in [
                ('download_ok', b'fixture download\n', 17, None),
                ('download_short', b'abc', 4, None),
                ('download_long', b'abcd', 3, hashlib.sha256(b'abc').hexdigest()),
                ('download_sha', b'abc', 3, '0' * 64)]:
            run = cls.base / identity; run.mkdir()
            opts = dict(Mode='Download', RunRoot=str(run), Uri='https://nodejs.org/dist/v22.23.3/fixture.bin',
                        ExpectedSize=size, ExpectedSha256=digest or hashlib.sha256(payload).hexdigest(),
                        Destination=str(run / 'resource.bin'), ManifestOut=str(run / 'result.json'))
            cls.cases.append(dict(id=identity, options=opts, fixture=base64.b64encode(payload).decode()))
        for identity, uri in [('http_rejected', 'http://nodejs.org/asset'),
                              ('latest_rejected', 'https://github.com/a/releases/latest/asset'),
                              ('credentials_rejected', 'https://user:password@example.test/asset')]:
            run = cls.base / identity; run.mkdir()
            cls.cases.append(dict(id=identity, fixture='', options=dict(Mode='Download', RunRoot=str(run),
                Uri=uri, ExpectedSize=1, ExpectedSha256='0' * 64,
                Destination=str(run / 'resource.bin'), ManifestOut=str(run / 'result.json'))))

        cases_file = cls.base / 'cases.json'
        cases_file.write_text(json.dumps(cls.cases), encoding='utf-8')
        worker = cls.base / 'worker.ps1'
        worker.write_text(r'''
param([string]$Script, [string]$Cases, [string]$Result)
$ErrorActionPreference = 'Stop'
. $Script -LibraryOnly
$results = @()
foreach ($case in (Get-Content -LiteralPath $Cases -Raw | ConvertFrom-Json)) {
    $options = [CommPlan.AssetOptions]::new()
    foreach ($property in $case.options.PSObject.Properties) { $options.($property.Name) = $property.Value }
    try {
        if ($null -ne $case.PSObject.Properties['fixture']) {
            $stream = [IO.MemoryStream]::new([Convert]::FromBase64String($case.fixture))
            try { $manifest = [CommPlan.DeliveryAssets]::FromFixtureStream($options, $stream) } finally { $stream.Dispose() }
        } else { $manifest = [CommPlan.DeliveryAssets]::Run($options) }
        $results += [pscustomobject]@{ id=$case.id; success=$true; error=$null }
    } catch { $results += [pscustomobject]@{ id=$case.id; success=$false; error=$_.Exception.Message } }
}
[pscustomobject]@{ pwsh=$PSVersionTable.PSVersion.ToString(); dotnet=[Environment]::Version.ToString(); cases=$results } |
    ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Result -Encoding utf8
''', encoding='utf-8')
        result_file = cls.base / 'result.json'
        process = subprocess.run([cls.pwsh, '-NoProfile', '-NonInteractive', '-File', str(worker),
                                  '-Script', str(SCRIPT), '-Cases', str(cases_file), '-Result', str(result_file)],
                                 cwd=ROOT, capture_output=True, text=True, timeout=90)
        if process.returncode:
            raise AssertionError('pwsh fixture worker failed:\n' + process.stdout + process.stderr)
        cls.evidence = json.loads(result_file.read_text(encoding='utf-8-sig'))
        cls.results = {row['id']: row for row in cls.evidence['cases']}
        cls.options = {case['id']: case['options'] for case in cls.cases}
        if len(cls.results) != len(cls.cases):
            raise AssertionError('fixture worker omitted cases')

    def successful(self, identity):
        self.assertTrue(self.results[identity]['success'], self.results[identity]['error'])
        opts = self.options[identity]
        manifest = json.loads(Path(opts['ManifestOut']).read_text(encoding='utf-8'))
        self.assertEqual(manifest['status'], 'PASSED')
        self.assertEqual(manifest['actualSha256'], opts['ExpectedSha256'])
        self.assertEqual(manifest['actualSize'], opts['ExpectedSize'])
        return manifest

    def rejected(self, *identities):
        for identity in identities:
            with self.subTest(fixture=identity):
                result = self.results[identity]
                self.assertFalse(result['success'], identity)
                self.assertTrue(result['error'])
                opts = self.options[identity]
                if identity != 'existing_output':
                    self.assertFalse(Path(opts['Destination']).exists(), identity)
                if Path(opts['ManifestOut']).is_file() and identity != 'existing_manifest':
                    manifest = json.loads(Path(opts['ManifestOut']).read_text(encoding='utf-8'))
                    self.assertEqual(manifest['status'], 'FAILED')

    def test_zip_plain_files_and_member_manifest(self):
        manifest = self.successful('zip_ok')
        self.assertEqual(manifest['memberCount'], 3)
        self.assertEqual(manifest['totalBytes'], len(b'fixture license\n'))
        members = {m['path']: m for m in manifest['members']}
        self.assertEqual(members['asset/sub/empty.txt']['sha256'], hashlib.sha256(b'').hexdigest())
        self.assertEqual((Path(self.options['zip_ok']['Destination']) / 'asset/LICENSE.txt').read_bytes(), b'fixture license\n')

    def test_plain_tar_and_gzip(self):
        for identity in ['tar_ok', 'gzip_ok']:
            with self.subTest(fixture=identity):
                self.successful(identity)
                self.assertEqual((Path(self.options[identity]['Destination']) / 'asset/LICENSE.txt').read_bytes(), b'fixture license\n')

    def test_pax_long_path_is_audited_and_preserved(self):
        manifest = self.successful('pax_ok')
        self.assertEqual(manifest['memberCount'], 2)
        self.assertEqual(manifest['members'][0]['path'], 'asset/' + 'deep/' * 30 + 'long.txt')

    def test_input_sha_and_size_gate(self): self.rejected('sha_bad', 'size_bad')
    def test_paths_rejected_before_output(self): self.rejected(*self.path_ids)
    def test_duplicate_and_type_conflicts(self): self.rejected('duplicate', 'case_duplicate', 'parent_file', 'type_collision')
    def test_zip_links_devices_and_reparse_markers(self): self.rejected('zip_symlink', 'zip_device', 'zip_reparse')
    def test_tar_links_and_special_types(self): self.rejected('tar_symlink', 'tar_hardlink', 'tar_device', 'tar_fifo', 'tar_sparse', 'tar_traversal')
    def test_limits_and_overflow(self): self.rejected('count_limit', 'member_limit', 'total_limit', 'zero_limit', 'overflow_limit')
    def test_allowlist_required_and_literal(self): self.rejected('missing_allowlist', 'wildcard_allowlist')
    def test_corrupt_and_truncated_archives(self): self.rejected('zip_truncated', 'zip_crc', 'tar_truncated', 'tar_checksum', 'tar_trailing', 'gzip_crc')
    def test_metadata_and_gzip_bombs_are_bounded(self): self.rejected('giant_pax', 'gzip_bomb')
    def test_parent_junction_and_outside_destinations(self): self.rejected('junction_parent', 'outside_destination')
    def test_input_evidence_and_output_overlap(self): self.rejected('overlap', 'input_overlap')

    def test_preexisting_outputs_are_preserved(self):
        self.rejected('existing_output', 'existing_manifest')
        self.assertEqual((Path(self.options['existing_output']['Destination']) / 'old.txt').read_bytes(), b'old destination')
        self.assertEqual(Path(self.options['existing_manifest']['ManifestOut']).read_bytes(), b'old manifest')

    def test_download_fixture_publication_and_evidence_kind(self):
        manifest = self.successful('download_ok')
        self.assertEqual(manifest['evidenceKind'], 'TRANSPORT_FIXTURE')
        self.assertEqual(Path(self.options['download_ok']['Destination']).read_bytes(), b'fixture download\n')

    def test_download_fixture_length_and_hash_failure(self): self.rejected('download_short', 'download_long', 'download_sha')
    def test_http_latest_and_credentials_rejected_before_transport(self): self.rejected('http_rejected', 'latest_rejected', 'credentials_rejected')

    def test_outside_sentinel_and_directory_are_untouched(self):
        self.assertEqual(sorted(p.name for p in self.outside.iterdir()), ['sentinel.txt'])
        self.assertEqual((self.outside / 'sentinel.txt').read_bytes(), b'never change this\n')

    def test_required_windows_host_is_recorded(self):
        self.assertGreaterEqual(tuple(map(int, self.evidence['pwsh'].split('.')[:2])), (7, 4))
        self.assertGreaterEqual(int(self.evidence['dotnet'].split('.')[0]), 8)

    def test_real_cli_success_and_failure_exit_codes(self):
        for succeeds in (True, False):
            with self.subTest(succeeds=succeeds):
                run = self.base / ('cli_ok' if succeeds else 'cli_bad'); run.mkdir()
                archive = run / 'input.zip'; archive.write_bytes(self.good_zip)
                process = subprocess.run([self.pwsh, '-NoProfile', '-NonInteractive', '-File', str(SCRIPT),
                    '-Mode', 'Extract', '-RunRoot', str(run), '-Archive', str(archive), '-Format', 'Zip',
                    '-Destination', str(run / 'output'), '-ManifestOut', str(run / 'manifest.json'),
                    '-ExpectedSize', str(len(self.good_zip)), '-ExpectedSha256',
                    hashlib.sha256(self.good_zip).hexdigest() if succeeds else '0' * 64,
                    '-AllowedTopLevel', 'asset'], cwd=ROOT, capture_output=True, text=True, timeout=30)
                self.assertEqual(process.returncode == 0, succeeds, process.stdout + process.stderr)


if __name__ == '__main__':
    unittest.main()
