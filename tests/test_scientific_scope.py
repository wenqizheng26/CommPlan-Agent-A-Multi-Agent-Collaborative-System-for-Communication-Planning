import math
import unittest
from unittest.mock import patch
from pathlib import Path
from formula_rag.pipeline import Engine

STANDARD = {'mode': 'standard_290k', 'confirmed': True}
NOISE = '噪声谱密度-174dBm/Hz，比特率1000000bit/s，Eb/N0 10dB，噪声系数3dB，工程损失0dB，求接收门限'


class ScientificScopeTests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine(Path(__file__).resolve().parents[1], dense=False, llm=False)

    def node(self, result, identifier):
        return next(c for c in result['calculations'] if c['id'] == identifier)

    def test_sea_case_explains_coverage_without_reasking_known_numbers(self):
        r = self.engine.query('岸站到海上平台，频率4.5GHz，距离30公里，求传输损耗')
        self.assertEqual(r['request']['parameters']['distance_km'], 30)
        c = self.node(r, 'fspl_ghz')
        self.assertNotIn('value', c)
        self.assertIn('model_coverage_gap', [i['code'] for i in c['scope_issues']])
        q = ' '.join(r['questions'])
        self.assertIn('当前', q)
        self.assertIn('模型', q)
        self.assertIn('自由空间基准', q)
        self.assertNotIn('请补充频率', q)
        self.assertNotIn('请补充距离', q)

    def test_nearfield_rejected_at_same_ratio_for_different_frequencies(self):
        for f in (0.1, 1, 100):
            with self.subTest(frequency=f):
                d = 299792458 / (f * 1e9) / (8 * math.pi) / 1000
                r = self.engine.query('按自由空间基准，求传输损耗', parameters={'frequency_ghz': f, 'distance_km': d})
                c = self.node(r, 'fspl_ghz')
                self.assertEqual(c['status'], 'not_applicable')
                self.assertNotIn('value', c)
                self.assertIn('free_space_nearfield', [i['code'] for i in c['scope_issues']])

    def test_rejected_fspl_blocks_dependents_but_not_independent_noise(self):
        r = self.engine.query('按自由空间基准，频率1GHz，距离0.000001km，温度290K，带宽1MHz，计算链路余量和热噪声功率',
            parameters={'tx_power_dbm': 40, 'tx_gain_dbi': 2,
            'rx_gain_dbi': 2, 'tx_loss_db': 2, 'rx_loss_db': 2, 'extra_loss_db': 0,
            'rx_threshold_dbm': -62, 'reserve_db': 0})
        for identifier in ('fspl_ghz', 'received_power', 'link_margin'):
            self.assertNotIn('value', self.node(r, identifier))
        self.assertEqual(self.node(r, 'thermal_noise')['status'], 'ok')
        self.assertEqual(r['status'], 'partial')

    def test_zero_and_negative_distance_are_invalid(self):
        for d in (0, -1):
            r = self.engine.query('按自由空间基准，求传输损耗', parameters={'frequency_ghz': 1, 'distance_km': d})
            self.assertNotIn('value', self.node(r, 'fspl_ghz'))
            self.assertEqual(r['status'], 'invalid_input')

    def test_positive_fspl_is_not_proof_of_farfield(self):
        r = self.engine.query('按自由空间基准，频率4.5GHz，距离30公里，求传输损耗')
        self.assertEqual(self.node(r, 'fspl_ghz')['status'], 'ok')
        self.assertTrue(any('远场' in w and '未' in w for w in r['warnings']))

    def test_negative_dbm_is_valid_and_explained(self):
        r = self.engine.query('温度290K，带宽1MHz，求热噪声功率')
        c = self.node(r, 'thermal_noise')
        self.assertAlmostEqual(c['value'], -113.97518719422808, places=8)
        self.assertIn('1 mW', c['assessment']['message'])

    def test_margin_classification_uses_unrounded_number(self):
        for margin, code in ((-8, 'below_threshold'), (-.004, 'below_threshold'), (0, 'at_threshold'), (.004, 'above_threshold')):
            with self.subTest(margin=margin):
                r = self.engine.query('求链路余量', parameters={'rx_power_dbm': -62 + margin, 'rx_threshold_dbm': -62, 'reserve_db': 0})
                c = self.node(r, 'link_margin')
                self.assertEqual(c['assessment']['code'], code)
                self.assertAlmostEqual(c['value'], margin)
                self.assertTrue(any('预算' in w for w in r['warnings']))

    def test_noise_reference_needs_explicit_confirmation_even_for_minus174(self):
        for text in (NOISE, NOISE.replace('噪声谱密度-174dBm/Hz', '温度100K')):
            c = self.node(self.engine.query(text), 'receiver_threshold')
            self.assertNotIn('value', c)
            self.assertIn('noise_reference_unconfirmed', [i['code'] for i in c['scope_issues']])

    def test_structured_reference_confirms_standard_route_only(self):
        r = self.engine.query(NOISE, noise_reference=STANDARD)
        self.assertEqual(self.node(r, 'receiver_threshold')['value'], -101)
        self.assertEqual(r['request']['noise_reference']['origin'], 'structured_input')
        for replacement in ('温度100K', '噪声谱密度-180dBm/Hz'):
            r = self.engine.query(NOISE.replace('噪声谱密度-174dBm/Hz', replacement), noise_reference=STANDARD)
            c = self.node(r, 'receiver_threshold')
            self.assertNotIn('value', c)
            self.assertIn('noise_reference_mismatch', [i['code'] for i in c['scope_issues']])

    def test_standard_confirmation_does_not_supply_missing_temperature(self):
        r = self.engine.query(NOISE.replace('噪声谱密度-174dBm/Hz，', ''), noise_reference=STANDARD)
        self.assertNotIn('value', self.node(r, 'receiver_threshold'))
        self.assertNotIn('temperature_k', r['request']['parameters'])
        self.assertTrue(any('或参考噪声温度' in q for q in r['questions']))

    def test_explicit_reference_clause_and_negated_or_quoted_clause(self):
        r = self.engine.query(NOISE + '\n确认采用标准290K噪声路线')
        self.assertEqual(self.node(r, 'receiver_threshold')['value'], -101)
        for clause in ('不确认采用标准290K噪声路线', '是否确认采用标准290K噪声路线？',
                       '“确认采用标准290K噪声路线”', '如果确认采用标准290K噪声路线'):
            self.assertNotIn('value', self.node(self.engine.query(NOISE + '\n' + clause), 'receiver_threshold'))

    def test_structured_unconfirmed_overrides_text_confirmation(self):
        r = self.engine.query(NOISE + '\n确认采用标准290K噪声路线', noise_reference={'mode':'standard_290k', 'confirmed':False})
        self.assertNotIn('value', self.node(r, 'receiver_threshold'))

    def test_llm_cannot_confirm_noise_reference(self):
        self.engine.selector = lambda *_: {'selected_ids': ['receiver_threshold'], 'noise_reference': STANDARD}
        self.assertNotIn('value', self.node(self.engine.query(NOISE), 'receiver_threshold'))

    def test_invalid_confirmation_schema_is_rejected(self):
        for invalid in (True, {'mode':'standard_290k','confirmed':'true'}, {'mode':'system_total','confirmed':True}):
            with self.assertRaises(ValueError):
                self.engine.query(NOISE, noise_reference=invalid)

    def test_scope_rejection_prevents_expression_execution(self):
        with patch('formula_rag.core._calculate', side_effect=AssertionError('must not execute')):
            for text, identifier in ((NOISE, 'receiver_threshold'),
                ('按自由空间基准，频率1GHz，距离0.000001km，求传输损耗', 'fspl_ghz')):
                self.assertNotIn('value', self.node(self.engine.query(text), identifier))

    def test_standard_source_temperature_is_computed_without_rounding(self):
        r = self.engine.query(NOISE.replace('噪声谱密度-174dBm/Hz', '温度290K'), noise_reference=STANDARD)
        c = self.node(r, 'receiver_threshold')
        self.assertEqual(c['dependencies'], ['noise_density'])
        self.assertAlmostEqual(c['value'], -100.97518719422808, places=8)

    def test_rounded_constant_transition_does_not_publish_negative_loss(self):
        d = 299792458 / 1e9 / (4 * math.pi) / 1000 * 1.001
        r = self.engine.query('按自由空间基准，求传输损耗', parameters={'frequency_ghz':1, 'distance_km':d})
        self.assertEqual(self.node(r, 'fspl_ghz')['status'], 'not_applicable')
        self.assertNotIn('value', self.node(r, 'fspl_ghz'))


if __name__ == '__main__':
    unittest.main()
