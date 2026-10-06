"""Source-package completeness, publication and tamper boundary checks."""
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import build_planning_release as builder
import validate_planning_release as validator


def archive_bytes(*, extra=None, tamper=None, missing=None, change=None, empty=False,
                  duplicate=None, attribute=None, remove_info=()):
    # Static consistency fixture; ActualSourcePackageTests uses real source bytes.
    files = {name: b'' if empty else b'reviewed source input\n' for name in builder.REQUIRED_FILES}
    info = dict(version=builder.VERSION, source_commit='a'*40, source_dirty=False,
                source_uncommitted_inputs=[], source_modified_inputs=[], build_fingerprint='b'*20,
                source_content_mode='worktree-bytes', workspace_build_fingerprint='b'*20,
                source_core_autocrlf=None,
                source_inputs_sha256=builder.inputs_digest(files),
                source_status_sha256=hashlib.sha256(b'').hexdigest(),
                built_at_utc='2026-10-03T00:00:00+00:00',
                intended_platform='Windows, Python 3.12',
                validation_record=builder.VALIDATION_RECORD,
                package_type=builder.PACKAGE_TYPE, acceptance_status='NOT_EVALUATED')
    info.update(change or {})
    for field in remove_info:
        info.pop(field)
    files.update({'VERSION': (builder.VERSION+'\n').encode(), 'BUILD_INFO.json': json.dumps(info).encode()})
    if missing:
        files.pop(missing)
    manifest = {'format': 1, 'files': {name: hashlib.sha256(data).hexdigest() for name,data in files.items()}}
    if tamper:
        files[tamper] += b'altered'
    files['MANIFEST.json'] = json.dumps(manifest).encode()
    files.update(extra or {})
    stream = io.BytesIO()
    with zipfile.ZipFile(stream,'w') as archive, warnings.catch_warnings():
        warnings.simplefilter('ignore',UserWarning)
        for name,data in files.items():
            if attribute and name == 'README.md':
                member = zipfile.ZipInfo(name)
                member.create_system = 3
                member.external_attr = attribute << 16
                archive.writestr(member,data)
            else:
                archive.writestr(name,data)
        if duplicate:
            archive.writestr(duplicate,b'duplicate')
    stream.seek(0)
    return stream


class PlanningReleaseTests(unittest.TestCase):
    def inspect(self,**kwargs):
        with zipfile.ZipFile(archive_bytes(**kwargs)) as archive:
            return validator.inspect_archive(archive)

    def test_explicit_allowlist_includes_runtime_data_and_selected_validation(self):
        for name in ('formula_rag/registry.py','formula_rag/schema.py','planning/services/coastal.py',
                     'planning/services/model_switch.py','planning/services/suggestions.py',
                     'planning/workflow/model_log.py','planning/web/i18n-en.mjs','planning/web/i18n.mjs',
                     'planning/web/lang.js','planning/web/records.mjs','planning/web/report.mjs',
                     'knowledge/tools.json','knowledge/facts/modulations.json','knowledge/facts/typical_values.json',
                     'scripts/eval_teacher.py','tests/test_core.py','tests/eval/teacher_cases.jsonl'):
            with self.subTest(name=name):
                self.assertTrue(builder.permitted(name))
        for name in ('models/model.gguf','runtime/server.exe','.venv/x.py','outputs/tasks.sqlite',
                     'tests/test_model_settings.py','.git/config','planning/__pycache__/x.pyc',
                     '../escape.txt','./VERSION','planning//web/app.js','planning\\web\\app.js',
                     'planning/unlisted_helper.py','C:/VERSION'):
            with self.subTest(name=name):
                self.assertFalse(builder.permitted(name))

    def test_hashes_and_missing_runtime_inputs_are_checked(self):
        self.assertEqual(self.inspect()['version'],'0.2.0-dev')
        with self.assertRaisesRegex(ValueError,'SHA256 mismatch'):
            self.inspect(tamper='VERSION')
        for name in ('knowledge/tools.json','knowledge/facts/modulations.json','planning/web/report.mjs'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError,'required release input missing'):
                self.inspect(missing=name)

    def test_fake_all_empty_source_cannot_pass_consistent_manifest(self):
        with self.assertRaisesRegex(ValueError,'empty release input'):
            self.inspect(empty=True)

    def test_paths_duplicates_special_files_and_sizes_are_rejected(self):
        for name in ('../escape.txt','models/model.gguf','./VERSION','planning//web/app.js'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError,'unsafe ZIP member'):
                self.inspect(extra={name:b'bad'})
        for name in ('VERSION','version'):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError,'duplicate ZIP member'):
                self.inspect(duplicate=name)
        for mode in (stat.S_IFLNK|0o777, stat.S_IFCHR|0o644):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError,'unsafe ZIP member'):
                self.inspect(attribute=mode)
        with patch.object(validator,'MAX_FILE',16), self.assertRaisesRegex(ValueError,'unsafe ZIP member'):
            self.inspect()
        with patch.object(validator,'MAX_TOTAL',16), self.assertRaisesRegex(ValueError,'size exceeds'):
            self.inspect()

    def test_metadata_does_not_assert_acceptance_or_false_clean_source(self):
        changes = [('version','../0.2.0'),('source_commit','unknown'),('source_dirty',1),
                   ('source_uncommitted_inputs',['README.md']),('source_uncommitted_inputs',['invalid']),
                   ('source_modified_inputs',['README.md']),
                   ('source_inputs_sha256','0'),('source_status_sha256',None),('build_fingerprint','unknown'),
                   ('package_type','source-demo-without-model-assets'),('acceptance_status','PASS'),
                   ('validation_record','docs/demo/VALIDATION.md')]
        for key,value in changes:
            with self.subTest(key=key,value=value), self.assertRaisesRegex(ValueError,'metadata contract'):
                self.inspect(change={key:value})
        for value in (None,'today','2026-10-03T00:00:00','2026-10-03T00:00:00+01:00'):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError,'invalid build timestamp'):
                self.inspect(change={'built_at_utc':value})
        with self.assertRaisesRegex(ValueError,'source input identity mismatch'):
            self.inspect(change={'source_inputs_sha256':'0'*64})

    def test_duplicate_json_keys_and_nonfinite_numbers_are_rejected(self):
        for content in (b'{"format":1,"format":1,"files":{}}',b'{"format":NaN,"files":{}}'):
            with zipfile.ZipFile(archive_bytes(extra={'MANIFEST.json':content})) as archive:
                with self.assertRaisesRegex(ValueError,'duplicate JSON key|invalid JSON number'):
                    validator.inspect_archive(archive)
        with zipfile.ZipFile(archive_bytes(extra={'MANIFEST.json':b'{"format":true,"files":{}}'})) as archive:
            with self.assertRaisesRegex(ValueError,'invalid manifest'):
                validator.inspect_archive(archive)

    def test_new_content_contract_and_legacy_packages_are_distinguished(self):
        fields=('source_content_mode','workspace_build_fingerprint','source_core_autocrlf')
        self.assertNotIn('source_content_mode',self.inspect(remove_info=fields))
        with self.assertRaisesRegex(ValueError,'partial source content metadata'):
            self.inspect(remove_info=('source_core_autocrlf',))
        for change in ({'source_content_mode':None},{'source_content_mode':[]},
                       {'source_content_mode':'canonical'}, {'workspace_build_fingerprint':'bad'},
                       {'source_core_autocrlf':'true\n'}, {'source_core_autocrlf':False}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError,'source content metadata contract'):
                self.inspect(change=change)
        with self.assertRaisesRegex(ValueError,'Git blob mode requires clean'):
            self.inspect(change={'source_content_mode':'git-blobs','source_dirty':True})
        with self.assertRaisesRegex(ValueError,'worktree fingerprint metadata mismatch'):
            self.inspect(change={'workspace_build_fingerprint':'c'*20})
        self.assertEqual(self.inspect(change={'source_content_mode':'git-blobs',
                          'workspace_build_fingerprint':'c'*20})['source_content_mode'],'git-blobs')

    def test_git_batch_rejects_wrong_type_order_size_truncation_and_hash(self):
        data=b'byte\x00payload\r\n'
        object_id=hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
        entries='100644 blob '+object_id+'\t中文.md\0'
        valid=object_id.encode()+b' blob '+str(len(data)).encode()+b'\n'+data+b'\n'
        replies=(valid.replace(b' blob ',b' tree '),
                 valid.replace(object_id.encode(),b'0'*40,1),
                 valid.replace(str(len(data)).encode()+b'\n',b'-1\n',1),
                 valid[:-1], valid.replace(data,b'wrong payload!'),valid+b'extra',
                 object_id.encode()+b' missing\n',
                 object_id.encode()+b' blob 20971521\n')
        for reply in replies:
            with self.subTest(reply=reply), patch.object(builder,'git_value',return_value=entries), \
                    patch.object(builder.subprocess,'run',return_value=subprocess.CompletedProcess([],0,reply,b'')):
                with self.assertRaisesRegex(ValueError,'Git batch|Git blob'):
                    builder.git_blob_payloads(ROOT,['中文.md'],'a'*40)
        with patch.object(builder,'git_value',return_value=entries.replace('100644','120000')):
            with self.assertRaisesRegex(ValueError,'reviewed Git blob unavailable'):
                builder.git_blob_payloads(ROOT,['中文.md'],'a'*40)

    def test_unlisted_source_and_empty_builder_inputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaisesRegex(ValueError,'missing release inputs'):
                builder.source_files(root)
            for name in builder.REQUIRED_FILES:
                path = root/name
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(b'')
            with self.assertRaisesRegex(ValueError,'empty release input'):
                builder.source_payloads(root,builder.source_files(root))
            (root/'planning/unreviewed.py').write_text('x=1\n')
            with self.assertRaisesRegex(ValueError,'new source needs explicit release review'):
                builder.source_files(root)

    def test_source_symlink_is_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'planning/web').mkdir(parents=True)
            target = root/'source.py'
            target.write_text('x=1')
            link = root/'planning/web/app.js'
            try:
                link.symlink_to(target)
            except (OSError,NotImplementedError):
                self.skipTest('symlink creation unavailable')
            with self.assertRaisesRegex(ValueError,'symlink or reparse'):
                builder.checked_file(root,'planning/web/app.js')

    def test_python_import_paths_are_removed_from_precheck_environment(self):
        with patch.dict(os.environ,{'PYTHONPATH':'unexpected-source','PYTHONHOME':'unexpected-runtime'}):
            environment = validator.isolated_environment()
        self.assertNotIn('PYTHONPATH',environment)
        self.assertNotIn('PYTHONHOME',environment)


class ActualSourcePackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # These temporary Git operations never use the source worktree's shared Git.
        # Real copied bytes make this test usable from an unpacked source without .git.
        cls.temporary = tempfile.TemporaryDirectory(prefix='commplan-package-test-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.container = Path(cls.temporary.name)
        cls.source = cls.container/'source'
        cls.source.mkdir()
        for name in builder.REQUIRED_FILES:
            destination = cls.source/name
            destination.parent.mkdir(parents=True,exist_ok=True)
            destination.write_bytes(builder.checked_file(ROOT,name).read_bytes())
        cls.git('init','--quiet')
        (cls.source/'.git/info').mkdir(parents=True,exist_ok=True)
        cls.git('-c','user.name=Release Boundary Test','-c','user.email=release-test@example.invalid',
                'commit','--quiet','--allow-empty','-m','Disposable test identity')

    @classmethod
    def git(cls,*args):
        return subprocess.run(['git',*args],cwd=cls.source,check=True,capture_output=True,text=True)

    def test_actual_tree_build_manifest_and_unpacked_fingerprint(self):
        output = self.container/'actual.zip'
        builder.build(self.source,output)
        with zipfile.ZipFile(output) as archive:
            info = validator.inspect_archive(archive)
            self.assertEqual(set(archive.namelist()),builder.REQUIRED_FILES|builder.GENERATED)
            for name in builder.REQUIRED_FILES:
                self.assertEqual(archive.read(name),(self.source/name).read_bytes(),name)
            self.assertEqual(info['build_fingerprint'],builder.fingerprint_function(ROOT)(ROOT))
            self.assertTrue(info['source_dirty'])
            self.assertEqual(set(info['source_uncommitted_inputs']),builder.REQUIRED_FILES)
            self.assertEqual(info['acceptance_status'],'NOT_EVALUATED')
        result = validator.validate(output,smoke=False)
        self.assertEqual(result['checks']['extracted_fingerprint'],'PASS')
        self.assertEqual(result['checks']['deterministic_http_smoke'],'NOT_RUN')
        self.assertEqual(result['m1_acceptance'],'NOT_EVALUATED')

    def test_existing_package_cannot_be_overwritten(self):
        output = self.container/'preserved.zip'
        output.write_bytes(b'original archive')
        with self.assertRaisesRegex(ValueError,'output already exists'):
            builder.build(self.source,output)
        self.assertEqual(output.read_bytes(),b'original archive')

    def test_invalid_version_and_dirty_formal_inputs_fail_before_publication(self):
        for index,version in enumerate(('../0.2.0','0.2.0/dev','01.2.0','0.2','')):
            output = self.container/f'invalid-{index}.zip'
            with self.subTest(version=version), self.assertRaisesRegex(ValueError,'invalid release version'):
                builder.build(self.source,output,version=version)
            self.assertFalse(output.exists())
        output = self.container/'require-clean.zip'
        with self.assertRaisesRegex(ValueError,'clean source commit'):
            builder.build(self.source,output,require_clean=True)
        self.assertFalse(output.exists())

    def test_nested_copy_cannot_borrow_outer_repository_identity(self):
        nested = self.source/'ignored-copy'
        nested.mkdir()
        (self.source/'.git/info/exclude').write_text('ignored-copy/\n')
        with self.assertRaisesRegex(ValueError,'Git worktree top-level'):
            builder.source_identity(nested)

    def test_ignored_required_member_still_marks_source_dirty(self):
        # An empty HEAD and locally ignored inputs otherwise give an empty Git status.
        with tempfile.TemporaryDirectory(prefix='commplan-ignored-test-') as temporary:
            root = Path(temporary)
            subprocess.run(['git','init','--quiet',str(root)],check=True,capture_output=True)
            (root/'.git/info').mkdir(parents=True,exist_ok=True)
            subprocess.run(['git','-c','user.name=Test','-c','user.email=test@example.invalid',
                            'commit','--quiet','--allow-empty','-m','Test identity'],cwd=root,check=True,capture_output=True)
            (root/'.git/info/exclude').write_text('*\n')
            for name in builder.REQUIRED_FILES:
                destination=root/name
                destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_bytes(builder.checked_file(ROOT,name).read_bytes())
            identity = builder.source_identity(root)
            self.assertEqual(identity[2],'')
            self.assertIn('README.md',identity[3])
            output=root.parent/(root.name+'-ignored.zip')
            with self.assertRaisesRegex(ValueError,'clean source commit'):
                builder.build(root,output,require_clean=True)
            self.assertFalse(output.exists())

    def test_git_crlf_filters_allow_clean_source_but_index_flags_cannot_hide_changes(self):
        with tempfile.TemporaryDirectory(prefix='commplan-flags-test-') as temporary:
            root=Path(temporary)/'source'
            root.mkdir()
            for name in builder.REQUIRED_FILES:
                destination=root/name
                destination.parent.mkdir(parents=True,exist_ok=True)
                destination.write_bytes(builder.checked_file(ROOT,name).read_bytes())
            def git(*args):
                return subprocess.run(['git',*args],cwd=root,check=True,capture_output=True,text=True).stdout.strip()
            git('init','--quiet')
            git('config','core.autocrlf','true')
            (root/'.gitattributes').write_text('planning/web/app.js text\n')
            git('add','--all')
            git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','--quiet','-m','Real test inputs')
            path=root/'planning/web/app.js'
            original=path.read_bytes().replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
            path.write_bytes(original)
            git('add','--','planning/web/app.js')
            self.assertEqual(git('diff','--cached','--raw'),'')
            self.assertEqual(builder.source_identity(root)[2:5],('',[],[]))
            builder.build(root,Path(temporary)/'clean-crlf.zip',require_clean=True)
            for flag in ('assume-unchanged','skip-worktree'):
                with self.subTest(flag=flag):
                    git('update-index','--'+flag,'planning/web/app.js')
                    try:
                        path.write_bytes(original+b'// concealed change\r\n')
                        identity=builder.source_identity(root)
                        self.assertEqual(identity[2],'')
                        self.assertEqual(identity[4],['planning/web/app.js'])
                        output=Path(temporary)/(flag+'.zip')
                        with self.assertRaisesRegex(ValueError,'clean source commit'):
                            builder.build(root,output,require_clean=True)
                        self.assertFalse(output.exists())
                    finally:
                        path.write_bytes(original)
                        git('update-index','--no-'+flag,'planning/web/app.js')

    def test_source_bytes_changing_during_build_do_not_publish(self):
        original = builder.source_payloads
        calls = []
        def changing(root,names):
            payloads = original(root,names)
            calls.append(True)
            if len(calls) == 2:
                payloads['README.md'] += b'source changed\n'
            return payloads
        output = self.container/'changed.zip'
        with patch.object(builder,'source_payloads',side_effect=changing):
            with self.assertRaisesRegex(ValueError,'source changed during release build'):
                builder.build(self.source,output)
        self.assertFalse(output.exists())
        self.assertFalse(list(self.container.glob('.commplan-building-*')))

    def test_unpacked_fingerprint_mismatch_is_not_a_pass(self):
        output = self.container/'bad-fingerprint.zip'
        builder.build(self.source,output)
        with patch.object(validator,'fingerprint_function',return_value=lambda root:'0'*20):
            with self.assertRaisesRegex(ValueError,'unpacked build fingerprint mismatch'):
                validator.validate(output,smoke=False)


class GitSourceBytesTests(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='commplan-git-bytes-test-')
        self.addCleanup(self.temporary.cleanup)
        self.container=Path(self.temporary.name)
        self.source=self.container/'source'
        self.source.mkdir()
        for name in builder.REQUIRED_FILES:
            destination=self.source/name
            destination.parent.mkdir(parents=True,exist_ok=True)
            data=builder.checked_file(ROOT,name).read_bytes()
            if name.endswith('.cmd'):
                # Prepare a known CRLF blob even when the tested formal package carries LF.
                data=data.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
            destination.write_bytes(data)
        self.git('init','--quiet')
        self.git('config','core.autocrlf','false')
        # This is fixture-local policy only; production blobs remain byte-exact.
        (self.source/'.gitattributes').write_text('* text=auto\nplanning/web/app.js text\n*.cmd -text\n')
        self.git('add','--all')
        self.git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','--quiet','-m','Byte source fixture')

    def git(self,*args):
        return subprocess.run(['git',*args],cwd=self.source,check=True,capture_output=True).stdout

    def package(self,name,require_clean):
        output=self.container/(name+'.zip')
        builder.build(self.source,output,require_clean=require_clean)
        with zipfile.ZipFile(output) as archive:
            info=validator.inspect_archive(archive)
            payloads={name:archive.read(name) for name in builder.REQUIRED_FILES}
        result=validator.validate(output,smoke=False)
        self.assertEqual(result['checks']['extracted_fingerprint'],'PASS')
        return info,payloads

    def test_simulated_manifest_matches_lf_worktree_and_git_blobs(self):
        records=json.loads((self.source/'knowledge/documents/manifest.json').read_bytes())['documents']
        simulated=[record for record in records if record['simulated']]
        self.assertEqual({record['doc_id'] for record in simulated},
                         {'sim-sites','sim-xx100','sim-xx200','sim-xx300'})
        for record in simulated:
            name=record['local_path']
            with self.subTest(document=record['doc_id']):
                actual=(self.source/name).read_bytes()
                blob=self.git('cat-file','blob','HEAD:'+name)
                self.assertNotIn(b'\r',actual)
                self.assertEqual(actual,blob)
                self.assertEqual(hashlib.sha256(actual).hexdigest(),record['sha256'])

    def test_formal_package_simulated_documents_ready_and_byte_tampering_changed(self):
        from planning.retrieval.documents import DocumentStore
        info,_=self.package('simulated-documents',True)
        self.assertEqual(info['source_content_mode'],'git-blobs')
        unpacked=self.container/'unpacked-simulated-documents'
        with zipfile.ZipFile(self.container/'simulated-documents.zip') as archive:
            archive.extractall(unpacked)
        self.assertFalse((unpacked/'.git').exists())
        records=json.loads((unpacked/'knowledge/documents/manifest.json').read_bytes())['documents']
        simulated=[record for record in records if record['simulated']]
        expected={record['doc_id']:'ready' for record in simulated}
        store=DocumentStore(unpacked)
        self.assertEqual({item['doc_id']:item['status'] for item in store.status
                          if item['doc_id'] in expected},expected)
        self.assertTrue(all(item['chunks']>0 for item in store.status if item['doc_id'] in expected))
        for record in simulated:
            with self.subTest(document=record['doc_id']):
                path=unpacked/record['local_path']
                original=path.read_bytes()
                # Same decoded text, different bytes: integrity checking must reject CRLF too.
                changed=original.replace(b'\n',b'\r\n')
                self.assertNotEqual(original,changed)
                path.write_bytes(changed)
                try:
                    altered=DocumentStore(unpacked)
                    self.assertEqual({item['doc_id']:item['status'] for item in altered.status
                                      if item['doc_id'] in expected},
                                     expected|{record['doc_id']:'changed'})
                    self.assertFalse(any(chunk['doc_id']==record['doc_id'] for chunk in altered.chunks))
                finally:
                    path.write_bytes(original)

    def test_formal_same_head_bytes_digest_and_fingerprint_ignore_checkout_newlines(self):
        name='planning/web/app.js'
        path=self.source/name
        original=path.read_bytes().replace(b'\r\n',b'\n')
        lines=original.splitlines(keepends=True)
        mixed=b''.join(line.replace(b'\n',b'\r\n') if index%2 else line for index,line in enumerate(lines))
        previous=None
        workspace=[]
        commit=self.git('rev-parse','HEAD')
        for label,content,autocrlf in (('lf',original,'false'),
                                        ('crlf',original.replace(b'\n',b'\r\n'),'true'),
                                        ('mixed',mixed,'input')):
            self.git('config','core.autocrlf',autocrlf)
            path.write_bytes(content)
            identity=builder.source_identity(self.source)
            self.assertEqual(identity[3:5],([],[]))
            if identity[2]:
                # Matching clean-filter content never exempts a Git-dirty worktree.
                with self.assertRaisesRegex(ValueError,'clean source commit'):
                    builder.build(self.source,self.container/('dirty-'+label+'.zip'),require_clean=True)
            # Fixture-only index stat refresh; the source blob and HEAD remain identical.
            self.git('add','--',name)
            self.assertEqual(self.git('rev-parse','HEAD'),commit)
            self.assertEqual(self.git('diff','--cached','--raw'),b'')
            self.assertEqual(builder.source_identity(self.source)[2:5],('',[],[]))
            info,payloads=self.package('formal-'+label,True)
            self.assertEqual(info['source_content_mode'],'git-blobs')
            self.assertFalse(info['source_dirty'])
            self.assertEqual(info['source_core_autocrlf'],autocrlf)
            self.assertEqual(payloads[name],self.git('cat-file','blob','HEAD:'+name))
            comparable=(payloads,info['source_inputs_sha256'],info['build_fingerprint'])
            if previous is not None:
                self.assertEqual(previous,comparable)
            previous=comparable
            workspace.append(info['workspace_build_fingerprint'])
            dev,actual=self.package('development-'+label,False)
            self.assertEqual(dev['source_content_mode'],'worktree-bytes')
            self.assertEqual(actual[name],content)
            self.assertEqual(dev['workspace_build_fingerprint'],dev['build_fingerprint'])
        self.assertEqual(len(set(workspace)),3)

    def test_binary_chinese_paths_repeated_objects_and_crlf_blobs_are_preserved(self):
        names=['knowledge/documents/simulated/站址表.md','README.md']
        binary=b'\x00\xff\x80\r\n'+ '中文文件'.encode('utf-8')+b'\nend\x00'
        for name in names:
            (self.source/name).write_bytes(binary)
        self.git('add','--all')
        self.git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','--quiet','-m','Binary source fixture')
        commit=self.git('rev-parse','HEAD').decode().strip()
        self.assertEqual(builder.git_blob_payloads(self.source,names,commit),{name:binary for name in names})
        info,payloads=self.package('binary-and-cmd',True)
        self.assertEqual(payloads[names[0]],binary)
        for name in ('start.cmd','setup_planning.cmd','planning/run_planning.cmd'):
            # CRLF fixture blobs must not be text-decoded or normalized by cat-file.
            self.assertEqual(payloads[name],self.git('cat-file','blob','HEAD:'+name))
            self.assertIn(b'\r\n',payloads[name])
            self.assertNotIn(b'\n',payloads[name].replace(b'\r\n',b''))

    def test_formal_missing_or_modified_workspace_still_fails_before_blob_collection(self):
        path=self.source/'README.md'
        original=path.read_bytes()
        path.write_bytes(original+b'actual change\n')
        with self.assertRaisesRegex(ValueError,'clean source commit'):
            builder.build(self.source,self.container/'modified.zip',require_clean=True)
        path.unlink()
        with self.assertRaisesRegex(ValueError,'missing release inputs'):
            builder.build(self.source,self.container/'missing.zip',require_clean=True)
        self.assertFalse((self.container/'modified.zip').exists())
        self.assertFalse((self.container/'missing.zip').exists())

    def test_formal_publish_rechecks_workspace_even_when_canonical_bytes_are_unchanged(self):
        original=builder.git_blob_payloads
        path=self.source/'README.md'
        def changing(root,names,commit):
            payloads=original(root,names,commit)
            path.write_bytes(path.read_bytes()+b'changed during build\n')
            return payloads
        output=self.container/'formal-changed.zip'
        with patch.object(builder,'git_blob_payloads',side_effect=changing):
            with self.assertRaisesRegex(ValueError,'source changed during release build'):
                builder.build(self.source,output,require_clean=True)
        self.assertFalse(output.exists())
        self.assertFalse(list(self.container.glob('.commplan-building-*')))

    def test_formal_publish_rechecks_git_autocrlf_observation(self):
        original=builder.git_blob_payloads
        def changing(root,names,commit):
            payloads=original(root,names,commit)
            self.git('config','core.autocrlf','true')
            return payloads
        output=self.container/'config-changed.zip'
        with patch.object(builder,'git_blob_payloads',side_effect=changing):
            with self.assertRaisesRegex(ValueError,'source changed during release build'):
                builder.build(self.source,output,require_clean=True)
        self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
