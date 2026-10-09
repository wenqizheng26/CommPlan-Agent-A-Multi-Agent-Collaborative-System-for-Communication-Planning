import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from formula_rag.catalog import load_catalog
from planning.knowledge.drafts import DraftStore, write_json
from planning.knowledge.switches import set_enabled

ROOT = Path(__file__).resolve().parents[1]


def manual(identifier='manual_power'):
    return dict(id=identifier, title='加倍功率', description='输入功率乘二', version='1.0.0', status='draft',
                expression='power_w * 2', output=dict(name='power_w', unit='W'),
                parameters=dict(power_w=dict(unit='W', description='输入功率', min=0, max=100)),
                applicability=dict(requires=[], notes=[]), sources=[], examples=[])


def proposal(identifier='model_power'):
    return dict(id=identifier, title='加倍功率', description='输入功率乘二', expression='power_w * 2',
                output_name='power_w', output_unit='W', parameters=[dict(name='power_w', unit='W', description='输入功率')],
                notes=['仅用于测试算例'], example_inputs=[dict(name='power_w', value=3)], example_expected=6)


def selector(output):
    return lambda role, prompt, view, schema: dict(output=copy.deepcopy(output), raw_output=json.dumps(output))


class FormulaDraftTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / 'knowledge').mkdir()
        shutil.copy(ROOT / 'knowledge/formulas.json', self.root / 'knowledge/formulas.json')
        self.store = DraftStore(self.root)
        self.source = dict(title='审核人核查的资料', locator='第 2 页，式 1')
        self.example = dict(inputs=dict(power_w=7), expected=14, note='按原文算例独立核查')

    def approve(self, draft, **kwargs):
        return self.store.review(draft['id'], '审核人', draft['content_hash'], 'approve', **kwargs)

    def test_manual_without_example_is_reviewable_without_documents(self):
        draft = self.store.create_manual('formula', manual())
        self.assertEqual((draft['source_kind'], draft['origin'], draft['evidence'], draft['checks']),
                         ('manual', {}, [], []))
        self.assertTrue(draft['needs_source'])
        self.assertTrue(draft['approvable'])
        self.assertNotIn('doc_id', draft)
        self.assertNotIn('example', draft)
        self.assertEqual(len(self.store.views()), 1)
        self.assertFalse(any(c['id'] == 'manual_power' for c in load_catalog(self.root)))

    def test_manual_approval_requires_source_and_independent_example(self):
        draft = self.store.create_manual('formula', manual())
        for kwargs in ({}, dict(source=self.source), dict(example=self.example)):
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, 'DRAFT_SOURCE_REQUIRED'):
                self.approve(draft, **kwargs)
        self.assertEqual(self.store.get(draft['id'])['status'], 'draft')

    def test_published_source_and_example_are_the_reviewers_and_repeat_is_noop(self):
        draft = self.store.create_manual('formula', manual())
        approved = self.approve(draft, source=self.source, example=self.example)
        card = next(c for c in load_catalog(self.root) if c['id'] == 'manual_power')
        self.assertEqual(card['sources'], [self.source])
        self.assertNotIn('path', card['sources'][0])
        self.assertEqual(card['examples'][0]['inputs'], self.example['inputs'])
        self.assertEqual(card['source_kind'], 'manual')
        self.assertEqual(approved['review']['source'], self.source)
        self.assertEqual(approved, self.approve(draft))
        self.assertEqual(sum(c['id'] == 'manual_power' for c in load_catalog(self.root)), 1)

    def test_review_example_rejects_bad_extra_missing_and_nonfinite_inputs(self):
        draft = self.store.create_manual('formula', manual())
        examples = [dict(self.example, expected=15), dict(self.example, expected=float('nan')),
                    dict(self.example, inputs=dict(power_w=True)), dict(self.example, inputs=dict(power_w=101)),
                    dict(self.example, inputs={}), dict(self.example, inputs=dict(power_w=7, extra=1)),
                    dict(self.example, inputs=dict(power_w=float('inf')))]
        for example in examples:
            with self.subTest(example=example), self.assertRaisesRegex(ValueError, 'DRAFT_EXAMPLE_FAILED'):
                self.approve(draft, source=self.source, example=example)
        self.assertEqual(self.store.get(draft['id'])['status'], 'draft')

    def test_source_and_example_shape_are_bounded(self):
        draft = self.store.create_manual('formula', manual())
        for source in (dict(title='', locator='p2'), dict(self.source, url='javascript:alert(1)'),
                       dict(self.source, path='arbitrary'), dict(self.source, url=None)):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'DRAFT_SOURCE_REQUIRED'):
                self.approve(draft, source=source, example=self.example)
        with self.assertRaisesRegex(ValueError, 'DRAFT_SOURCE_REQUIRED'):
            self.approve(draft, source=self.source, example=dict(self.example, tolerance=100))

    def test_expression_unit_and_declaration_checks_precede_persistence(self):
        for change in (dict(expression='__import__("os")'), dict(expression='power_w.__class__'),
                       dict(expression='other * 2'), dict(kind='python_tool'), dict(id='../bad'),
                       dict(id='x' * 65), dict(output=dict(name='x', unit='madeup')),
                       dict(parameters=dict(power_w=dict(unit='bogus', description='输入')))):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.store.create_manual('formula', dict(manual(), **change))
        self.assertEqual(self.store.list(), [])

    def test_manual_supplied_examples_are_checked_without_trusting_tolerance(self):
        record = manual()
        record['examples'] = [dict(inputs=dict(power_w=3), expected=999, tolerance=10000)]
        with self.assertRaisesRegex(ValueError, 'DRAFT_EXAMPLE_FAILED'):
            self.store.create_manual('formula', record)

    def test_disabled_existing_id_is_never_overwritten(self):
        set_enabled(self.root, 'cards', 'doppler_max', False)
        with self.assertRaisesRegex(ValueError, 'DRAFT_DUPLICATE_ID'):
            self.store.create_manual('formula', manual('doppler_max'))

    def test_publish_race_checks_duplicate_again_and_preserves_first(self):
        first = self.store.create_manual('formula', manual())
        second = self.store.create_manual('formula', manual())
        self.approve(first, source=self.source, example=self.example)
        self.assertFalse(self.store.view(self.store.get(second['id']))['approvable'])
        with self.assertRaisesRegex(ValueError, 'DRAFT_NOT_APPROVABLE'):
            self.approve(second, source=self.source, example=self.example)

    def test_model_example_is_self_check_and_independent_review_replaces_it(self):
        result = self.store.create_model('formula', '加倍功率', selector(proposal()))
        draft = result['draft']
        self.assertEqual((result['mode'], result['attempts']), ('stub', 1))
        self.assertEqual(draft['source_kind'], 'model_knowledge')
        self.assertTrue(draft['example']['self_check'])
        self.assertEqual(draft['example']['value'], 6)
        self.assertEqual(draft['origin']['topic'], '加倍功率')
        self.assertIn('出处未核', result['message'])
        self.approve(draft, source=self.source, example=self.example)
        card = next(c for c in load_catalog(self.root) if c['id'] == 'model_power')
        self.assertEqual(card['source_kind'], 'model_knowledge')
        self.assertEqual(card['examples'][0]['expected'], 14)
        self.assertEqual(self.store.view(self.store.get(draft['id']))['example']['expected'], 6)

    def test_bad_model_examples_retry_and_leave_no_draft(self):
        for output in (dict(proposal(), example_expected=999),
                       dict(proposal(), example_inputs=[dict(name='power_w', value=3), dict(name='power_w', value=3)]),
                       dict(proposal(), expression='1 / 0'), dict(proposal(), output_unit='bogus')):
            with self.subTest(output=output):
                result = self.store.create_model('formula', '加倍功率', selector(output))
                self.assertIsNone(result['draft'])
                self.assertEqual(result['attempts'], 2)
        self.assertEqual(self.store.list(), [])

    def test_model_offline_does_not_fabricate_proposal(self):
        result = self.store.create_model('formula', '加倍功率')
        self.assertEqual((result['draft'], result['attempts'], result['mode']), (None, 0, 'deterministic'))
        self.assertEqual(self.store.list(), [])

    def test_topic_and_kind_validation(self):
        for topic in ('', 'x' * 101, None):
            with self.subTest(topic=topic), self.assertRaisesRegex(ValueError, 'DRAFT_TOPIC'):
                self.store.create_model('formula', topic)
        with self.assertRaisesRegex(ValueError, 'DRAFT_KIND'):
            self.store.create_manual('device', manual())

    def test_non_document_hash_covers_source_kind_and_origin(self):
        draft = self.store.create_manual('formula', manual())
        raw = self.store.get(draft['id'])
        raw['source_kind'] = 'document'
        write_json(self.store.path(draft['id']), raw)
        with self.assertRaisesRegex(ValueError, 'DRAFT_CHANGED'):
            self.store.get(draft['id'])

    def test_reject_needs_no_source_and_keeps_model_origin(self):
        draft = self.store.create_model('formula', '加倍功率', selector(proposal()))['draft']
        rejected = self.store.review(draft['id'], '审核人', draft['content_hash'], 'reject', '出处未找到')
        self.assertEqual(rejected['status'], 'rejected')
        self.assertEqual(rejected['origin'], draft['origin'])
        self.assertFalse(any(c['id'] == 'model_power' for c in load_catalog(self.root)))

    def test_user_provenance_is_not_promoted_to_reviewed_source(self):
        record = manual()
        record.update(review=dict(reviewer='伪造'), source_kind='document', sources=[dict(title='伪造', url='https://example.com')])
        draft = self.store.create_manual('formula', record)
        self.assertEqual(draft['source_kind'], 'manual')
        self.assertEqual(draft['record']['sources'], [])
        self.assertNotIn('review', draft['record'])

    def test_interrupted_publish_recovers_review_inputs_from_published_card(self):
        from unittest.mock import patch
        draft = self.store.create_manual('formula', manual())
        original_write = write_json

        def fail_draft_write(path, value):
            if Path(path) == self.store.path(draft['id']):
                raise OSError('interrupted after publish')
            return original_write(path, value)

        with patch('planning.knowledge.drafts.write_json', side_effect=fail_draft_write):
            with self.assertRaisesRegex(OSError, 'interrupted'):
                self.approve(draft, source=self.source, example=self.example)
        self.assertEqual(self.store.get(draft['id'])['status'], 'draft')
        recovered = self.approve(draft)
        self.assertEqual(recovered['status'], 'approved')
        self.assertEqual(recovered['review']['source'], self.source)
        self.assertEqual(sum(c['id'] == 'manual_power' for c in load_catalog(self.root)), 1)

    def test_numeric_first_id_matches_declared_contract(self):
        draft = self.store.create_manual('formula', manual('9_power'))
        self.assertTrue(draft['approvable'])


if __name__ == '__main__':
    unittest.main()
