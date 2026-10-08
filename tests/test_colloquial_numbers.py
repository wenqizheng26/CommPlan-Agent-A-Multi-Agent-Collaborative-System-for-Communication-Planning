"""Finite Chinese integer quantities keep source spans and explicit confirmation."""
from pathlib import Path
import tempfile
import unittest

from formula_rag.parsing import extract_request
from planning.services.number_check import known, unquoted
from planning.services.requirement_quantities import find_quantities
from planning.workflow.task_service import TaskService
from tests.test_planning_loop import ROOT, TEXT, command


class ColloquialParsingTests(unittest.TestCase):
    def test_chinese_integer_quantities_convert_only_with_explicit_units(self):
        cases = [('距离一公里', 1), ('距离两公里', 2), ('距离十公里', 10),
                 ('距离十一公里', 11), ('距离二十三公里', 23), ('距离一百米', .1),
                 ('距离两千米', 2), ('距离一千零五米', 1.005), ('距离一千二百三十四米', 1.234)]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(extract_request(text)['parameters']['distance_km'], expected)

    def test_f4_two_thousand_megahertz_is_now_two_gigahertz(self):
        text = '按自由空间基准，频率两千兆赫，距离一公里，求路径损耗。'
        parsed = extract_request(text)
        self.assertEqual(parsed['parameters'], {'frequency_ghz': 2, 'distance_km': 1})
        self.assertIn('两千兆赫', parsed['evidence']['frequency_ghz'][0])

    def test_spoken_decimal_g_preserves_network_generation_exclusion(self):
        for text in ['想用5.8个G，传视频', '频率5.8 个 G', '频率2.4G']:
            with self.subTest(text=text):
                expected = 2.4 if '2.4' in text else 5.8
                self.assertEqual(extract_request(text)['parameters']['frequency_ghz'], expected)
                self.assertEqual(find_quantities(text)[0]['value'], expected)
        self.assertEqual(find_quantities('5G网络，4个G基站，2.5Gbps'), [])

    def test_quantity_sources_keep_the_original_chinese_text_and_offsets(self):
        text = '大概十公里出头，想用5.8个G，频率两千兆赫。'
        quantities = find_quantities(text)
        self.assertEqual([(q['text'], q['value'], q['unit']) for q in quantities],
                         [('十公里', 10, '公里'), ('5.8个G', 5.8, 'G'), ('两千兆赫', 2000, '兆赫')])
        for q in quantities:
            self.assertEqual(text[slice(*q['span'])], q['text'])

    def test_unsupported_words_ordinals_and_shorthand_are_not_partial_quantities(self):
        for text in ['距离十', '一万公里', '一点五公里', '一百二公里', '二零二六年',
                     '单位是千米，公里', '第十公里站', '一到两公里', '十公里或二十公里']:
            with self.subTest(text=text):
                self.assertEqual(find_quantities(text), [])

    def test_number_guard_checks_supported_chinese_integers_against_facts(self):
        facts = known({'distance_km': 10, 'frequency_ghz': 2})
        self.assertEqual(unquoted('距离十公里，频率两千兆赫', facts), [])
        self.assertEqual(unquoted('距离十一公里', facts), ['十一公里'])
        self.assertTrue(unquoted('距离一万公里', facts))

    def test_chinese_number_guard_keeps_signs_dimensions_and_unsupported_forms(self):
        facts = known({'tx_power_dbm': -20, 'tx_gain_dbi': 20})
        self.assertEqual(unquoted('发射功率负二十dBm，增益二十dBi', facts), [])
        self.assertEqual(unquoted('发射功率二十dBm', facts), ['二十dBm'])
        self.assertEqual(unquoted('距离二十公里', facts), ['二十公里'])
        self.assertTrue(unquoted('发射功率一万DBM', facts))


class ColloquialConfirmationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.service = TaskService(ROOT, Path(tmp.name) / 'tasks.sqlite')

    def test_approximate_chinese_distance_stays_unconfirmed_and_answer_cleans_the_whole_phrase(self):
        for phrase in ['大概十公里出头', '十公里出头', '大概十公里左右']:
            with self.subTest(phrase=phrase):
                draft = self.service.apply(command(text=TEXT.replace('距离1km', phrase)))['state']
                self.assertEqual(draft['status'], 'AWAITING_INPUT')
                self.assertIsNone(draft['result'])
                self.assertTrue(any(d['code'] == 'PARAMETER_APPROXIMATE' for d in draft['report']['diagnostics']))
                parameter = next(p for p in draft['report']['parameters_proposal'] if p['canonical_name'] == 'distance_km')
                self.assertEqual(parameter['value'], 10)
                self.assertEqual(draft['request']['raw_text'][slice(*parameter['origins'][0]['span'])], '十公里')
                question = next(q for q in draft['input_issues'] if q['field'] == 'distance_km')
                with self.assertRaisesRegex(ValueError, 'NOT_CONFIRMABLE'):
                    self.service.apply(command('confirm', draft, review_hash='x'))
                answered = self.service.apply(command('answer', draft, answers={question['id']: '十公里'}, mode='deterministic'))['state']
                self.assertEqual(answered['status'], 'AWAITING_CONFIRMATION')
                self.assertEqual(answered['revision'], draft['revision'] + 1)
                self.assertEqual(answered['input_issues'], [])
                for hedge in ['大概', '出头', '左右']:
                    self.assertNotIn(hedge, answered['request']['raw_text'])
                self.assertEqual(next(p['value'] for p in answered['report']['parameters_proposal'] if p['canonical_name'] == 'distance_km'), 10)

    def test_exact_f4_and_spoken_g_are_confirmable_without_model_calls(self):
        for frequency in ['两千兆赫', '2.0个G']:
            draft = self.service.apply(command(text=TEXT.replace('2GHz', frequency).replace('1km', '一公里')))['state']
            self.assertEqual(draft['status'], 'AWAITING_CONFIRMATION')
            self.assertEqual(self.service.model_calls.calls(draft['task_id']), [])

    def test_unresolved_chinese_value_cannot_disappear_beside_a_valid_value(self):
        for phrase in ['距离一百二公里', '距离一万公里', '距离十']:
            with self.subTest(phrase=phrase):
                draft = self.service.apply(command(text=TEXT + '，' + phrase))['state']
                self.assertEqual(draft['status'], 'AWAITING_INPUT')
                self.assertTrue(any(d['code'] == 'INPUT_PARSE_ISSUE' for d in draft['report']['diagnostics']))
                self.assertIsNone(draft['confirmed_snapshot'])

    def test_chinese_budget_answer_and_megahertz_correction_replace_the_original_value(self):
        from tests.test_planning_modulation_exclusions import BASE
        draft = self.service.apply(command(text=BASE.replace('20dBm', '1000dBm') + 'QPSK。'))['state']
        question = next(q for q in draft['input_issues'] if q['field'] == 'tx_power_dbm')
        ready = self.service.apply(command('answer', draft, answers={question['id']: '二十个dBm'}, mode='deterministic'))['state']
        self.assertEqual(ready['status'], 'AWAITING_CONFIRMATION', ready.get('failure'))
        self.assertNotIn('1000', ready['request']['raw_text'])
        draft = self.service.apply(command(text=TEXT + '，频率3GHz'))['state']
        question = next(q for q in draft['input_issues'] if q['field'] == 'frequency_ghz')
        ready = self.service.apply(command('answer', draft, answers={question['id']: '两千兆赫'}, mode='deterministic'))['state']
        self.assertEqual(ready['status'], 'AWAITING_CONFIRMATION', ready.get('failure'))
        self.assertNotIn('3GHz', ready['request']['raw_text'])


if __name__ == '__main__':
    unittest.main()
