import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from formula_rag.catalog import load_catalog
from planning.agents.extraction import extract
from planning.knowledge.drafts import DraftStore
from planning.knowledge.facts import FactService, fact_manifest
from planning.retrieval.documents import DocumentStore
from tests.teacher_fixtures import copy_teacher_dependencies

ROOT = Path(__file__).resolve().parents[1]
TABLE = '| XX-300 | 40 | 6 | -97 | 1.0–3.0 |'


def model(output):
    """A stand-in for the local model that always gives this form."""
    return lambda role, prompt, view, schema: dict(output=copy.deepcopy(output), raw_output=json.dumps(output))


class DraftTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for folder in ('knowledge/documents', 'knowledge/facts'):
            shutil.copytree(ROOT / folder, self.root / folder)
        shutil.copy(ROOT / 'knowledge/formulas.json', self.root / 'knowledge/formulas.json')
        copy_teacher_dependencies(self.root)
        self.store = DraftStore(self.root)
        chunks = [c for c in DocumentStore(self.root).chunks if c['doc_id'] == 'sim-xx300']
        self.spec = next(c['id'] for c in chunks if TABLE in c['description'])
        self.eirp = next(c['id'] for c in chunks if 'EIRP = Pt' in c['description'])
        self.device = dict(found=True, names=['XX-300'], model='XX-300', tx_power_dbm=40, antenna_gain_dbi=6,
                           rx_sensitivity_dbm=-97, band_low_ghz=1.0, band_high_ghz=3.0,
                           evidence=[dict(field=f, chunk_id=self.spec, quote=TABLE) for f in
                                     ('names', 'model', 'tx_power_dbm', 'antenna_gain_dbi', 'rx_sensitivity_dbm', 'band_ghz')])
        quote = lambda field, text: dict(field=field, chunk_id=self.eirp, quote=text)
        self.formula = dict(found=True, id='eirp_dbm', title='等效全向辐射功率',
            description='发射机输出功率加发射天线增益、减去发射馈线损耗', expression='tx_power_dbm + tx_gain_dbi - tx_loss_db',
            output_name='eirp_dbm', output_unit='dBm',
            parameters=[dict(name='tx_power_dbm', unit='dBm', description='发射机输出功率'),
                        dict(name='tx_gain_dbi', unit='dBi', description='发射天线沿对端方向的增益'),
                        dict(name='tx_loss_db', unit='dB', description='发射馈线损耗')],
            notes=['三项必须属于同一发射端、同一频率。'],
            example_inputs=[dict(name='tx_power_dbm', value=40), dict(name='tx_gain_dbi', value=6), dict(name='tx_loss_db', value=2)],
            example_expected=44,
            evidence=[quote('title', '等效全向辐射功率'), quote('description', '发射机输出功率加发射天线增益、减去发射馈线损耗'),
                      quote('expression', 'EIRP = Pt + Gt − Lt'), quote('output.unit', '单位 dBm'),
                      quote('parameters', '其中 Pt 为发射机输出功率（dBm），Gt 为发射天线沿对端方向的增益（dBi），Lt 为发射馈线损耗（dB）'),
                      quote('examples.0.inputs', 'Pt = 40 dBm，Gt = 6 dBi，Lt = 2 dB'),
                      quote('examples.0.expected', 'EIRP = 40 + 6 − 2 = 44 dBm'),
                      quote('applicability.notes', '三项必须属于同一发射端、同一频率')])

    def test_device_draft_is_invisible_until_approved_then_supplies_the_library(self):
        result = extract(self.root, 'device', [self.spec], model(self.device))
        draft = result['draft']
        self.assertEqual((draft['status'], draft['approvable'], draft['problems']), ('draft', True, []))
        self.assertEqual({row['field']: row['status'] for row in draft['checks']}['band_ghz.1'], 'match')
        # Each field shows its quote once, under the table header that names the column.
        power = next(row for row in draft['checks'] if row['field'] == 'tx_power_dbm')
        self.assertEqual([(q['quote'], q['header']) for q in power['quotes']],
                         [(TABLE, '| 型号 | 额定发射功率 dBm | 天线增益 dBi | 接收灵敏度 dBm | 工作频段 GHz |')])
        self.assertEqual(FactService(self.root).find_device('XX-300')['candidates'], [])
        before = fact_manifest(self.root)
        with self.assertRaisesRegex(ValueError, 'DRAFT_STALE_REVIEW'):
            self.store.review(draft['id'], '审核人', 'wrong', 'approve')
        approved = self.store.review(draft['id'], '审核人', draft['content_hash'], 'approve')
        self.assertEqual(approved['status'], 'approved')
        self.assertEqual(approved, self.store.review(draft['id'], '审核人', draft['content_hash'], 'approve'))
        record = FactService(self.root).find_device('XX-300')['candidates'][0]['record']
        self.assertEqual((record['tx_power_dbm'], record['band_ghz'], record['simulated']), (40, [1.0, 3.0], True))
        self.assertEqual(record['source']['locator'], '§1 规格表')
        self.assertEqual(record['review']['reviewer'], '审核人')
        self.assertNotEqual(before, fact_manifest(self.root))
        # The other records keep their text: one compact line each.
        lines = (self.root / 'knowledge/facts/devices.json').read_text(encoding='utf-8').splitlines()
        self.assertEqual(len(lines), 5)
        self.assertIn('"id":"device:xx-300"', lines[3])
        again = extract(self.root, 'device', [self.spec], model(self.device))['draft']
        self.assertFalse(again['approvable'])
        self.assertIn('库里已有编号 device:xx-300', again['problems'])
        with self.assertRaisesRegex(ValueError, 'DRAFT_NOT_APPROVABLE'):
            self.store.review(again['id'], '审核人', again['content_hash'], 'approve')

    def test_rejection_keeps_the_reason_and_writes_nothing(self):
        draft = extract(self.root, 'device', [self.spec], model(self.device))['draft']
        with self.assertRaisesRegex(ValueError, 'DRAFT_REASON'):
            self.store.review(draft['id'], '审核人', draft['content_hash'], 'reject')
        rejected = self.store.review(draft['id'], '审核人', draft['content_hash'], 'reject', '频段需再核')
        self.assertEqual((rejected['status'], rejected['review']['reason']), ('rejected', '频段需再核'))
        self.assertEqual(FactService(self.root).find_device('XX-300')['candidates'], [])
        with self.assertRaisesRegex(ValueError, 'DRAFT_ALREADY_REVIEWED'):
            self.store.review(draft['id'], '审核人', draft['content_hash'], 'approve')

    def test_invented_numbers_and_quotes_retry_then_leave_no_draft(self):
        invented = dict(self.device, tx_power_dbm=45)
        result = extract(self.root, 'device', [self.spec], model(invented))
        self.assertIsNone(result['draft'])
        self.assertEqual((result['mode'], result['attempts']), ('deterministic_fallback', 2))
        self.assertIn('DRAFT_NUMBER_UNGROUNDED: tx_power_dbm', result['diagnostics'][0]['reason'])
        fake = copy.deepcopy(self.device)
        fake['evidence'][2]['quote'] = '额定发射功率 40 dBm'
        self.assertIn('DRAFT_QUOTE_NOT_FOUND', extract(self.root, 'device', [self.spec], model(fake))['diagnostics'][0]['reason'])
        self.assertEqual(self.store.list(), [])
        self.assertIn('没有生成草稿', extract(self.root, 'device', [self.spec], False)['message'])
        missing = extract(self.root, 'device', [self.spec], model(dict(self.device, found=False)))
        self.assertEqual((missing['draft'], missing['mode']), (None, 'stub'))

    def test_formula_draft_checks_its_example_at_the_documents_precision(self):
        draft = extract(self.root, 'formula', [self.eirp], model(self.formula))['draft']
        self.assertTrue(draft['approvable'])
        self.assertEqual((draft['example']['value'], draft['example']['passed'], draft['example']['tolerance']), (44, True, 0.5))
        statuses = {row['field']: row['status'] for row in draft['checks']}
        self.assertEqual((statuses['expression'], statuses['examples.0.expected']), ('manual', 'match'))
        wrong = dict(self.formula, expression='tx_power_dbm + tx_gain_dbi + tx_loss_db')
        failed = extract(self.root, 'formula', [self.eirp], model(wrong))
        self.assertIsNone(failed['draft'])
        self.assertIn('EXTRACTION_EXAMPLE_FAILED', failed['diagnostics'][-1]['reason'])
        # Every field without a quote is named at once, so one retry can supply them all.
        partial = dict(self.formula, evidence=[e for e in self.formula['evidence']
                                               if e['field'] not in ('description', 'output.unit', 'examples.0.expected')])
        unquoted = extract(self.root, 'formula', [self.eirp], model(partial))
        self.assertIsNone(unquoted['draft'])
        self.assertIn('DRAFT_EVIDENCE_MISSING: description、output.unit、examples.0.expected',
                      unquoted['diagnostics'][0]['reason'])
        self.store.review(draft['id'], '审核人', draft['content_hash'], 'approve')
        card = next(c for c in load_catalog(self.root) if c['id'] == 'eirp_dbm')
        self.assertEqual((card['status'], card['sources'][0]['locator'], card['examples'][0]['expected']),
                         ('verified', '§2 等效全向辐射功率', 44))

    def test_changed_document_blocks_review(self):
        draft = extract(self.root, 'device', [self.spec], model(self.device))['draft']
        path = self.root / 'knowledge/documents/simulated/XX-300 手册.md'
        path.write_bytes(path.read_bytes().replace('| 40 |'.encode(), '| 41 |'.encode()))
        manifest = self.root / 'knowledge/documents/manifest.json'
        data = json.loads(manifest.read_text(encoding='utf-8'))
        import hashlib
        next(d for d in data['documents'] if d['doc_id'] == 'sim-xx300')['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        shown = self.store.view(self.store.get(draft['id']))
        self.assertFalse(shown['approvable'])
        with self.assertRaisesRegex(ValueError, 'DRAFT_NOT_APPROVABLE'):
            self.store.review(draft['id'], '审核人', draft['content_hash'], 'approve')

    def test_records_from_documents_kept_only_on_another_machine_stay_usable(self):
        added = self.root / 'knowledge/sources/added/added-1.md'
        added.parent.mkdir(parents=True)
        added.write_bytes((self.root / 'knowledge/documents/simulated/XX-300 手册.md').read_bytes())
        import hashlib
        sha = hashlib.sha256(added.read_bytes()).hexdigest()
        manifest = self.root / 'knowledge/documents/manifest.json'
        data = json.loads(manifest.read_text(encoding='utf-8'))
        data['documents'] = [d for d in data['documents'] if d['doc_id'] != 'sim-xx300'] + [dict(
            doc_id='added-1', title='XX-300 手册（外来）', version='1', language='zh', source='本机添加：XX-300.md',
            local_path='knowledge/sources/added/added-1.md', sha256=sha, simulated=False, redistributable=False)]
        manifest.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        chunk = next(c['id'] for c in DocumentStore(self.root).chunks if c['doc_id'] == 'added-1' and TABLE in c['description'])
        output = dict(self.device, evidence=[dict(e, chunk_id=chunk) for e in self.device['evidence']])
        draft = extract(self.root, 'device', [chunk], model(output))['draft']
        self.store.review(draft['id'], '审核人', draft['content_hash'], 'approve')
        added.unlink()  # a fresh clone: the original is not on this machine
        self.assertEqual(len(FactService(self.root).find_device('XX-300')['candidates']), 1)
        added.write_bytes(b'changed')  # a different file under the same name is not the reviewed source
        service = FactService(self.root)
        self.assertEqual((service.find_device('XX-300')['candidates'], service.stale), ([], ['device:xx-300']))


if __name__ == '__main__':
    unittest.main()
