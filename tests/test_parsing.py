import math
import unittest

try:
    from formula_rag.parsing import extract_request
except ImportError:
    extract_request = None


class ParsingTests(unittest.TestCase):
    def parse(self, text, **kwargs):
        self.assertIsNotNone(extract_request, '自由文本解析器尚未实现')
        return extract_request(text, **kwargs)

    def test_equivalent_units(self):
        a = self.parse('自由空间，频率4.5 GHz，距离0.2 km，求传输损耗')
        b = self.parse('按自由空间计算衰减，载频4500 MHz，相距200米')
        self.assertEqual(a['parameters'], b['parameters'])
        self.assertEqual(a['parameters']['distance_km'], .2)
        self.assertIn('free_space', b['conditions'])

    def test_missing_unit_is_not_invented(self):
        result = self.parse('频率4.5，距离200，计算传输损耗')
        self.assertNotIn('frequency_ghz', result['parameters'])
        self.assertNotIn('distance_km', result['parameters'])

    def test_conflicting_values_block_field(self):
        result = self.parse('频率4.5 GHz，频率5 GHz，距离200米')
        self.assertNotIn('frequency_ghz', result['parameters'])
        self.assertTrue(result['issues'])

    def test_bandwidth_is_not_carrier(self):
        result = self.parse('温度290 K，带宽1 MHz，求热噪声功率')
        self.assertEqual(result['parameters']['bandwidth_hz'], 1e6)
        self.assertNotIn('frequency_ghz', result['parameters'])

    def test_power_and_signed_gain(self):
        result = self.parse('发射功率10 W，发射天线增益-2 dBi，接收天线增益3 dBi')
        self.assertEqual(result['parameters']['tx_power_dbm'], 40)
        self.assertEqual(result['parameters']['tx_gain_dbi'], -2)
        self.assertEqual(result['parameters']['rx_gain_dbi'], 3)

    def test_obstruction_does_not_imply_free_space(self):
        result = self.parse('山区非视距，不能按自由空间，频率4.5GHz，距离30公里，计算路径损耗')
        self.assertNotIn('free_space', result['conditions'])
        self.assertIn('non_free_space', result['conditions'])

    def test_free_space_reference_remains_labelled(self):
        result = self.parse('实际有遮挡，仅算自由空间基准，4.5 GHz，200米')
        self.assertIn('free_space_reference', result['conditions'])

    def test_celsius_and_velocity_conversion(self):
        result = self.parse('温度20℃，相对速度10 m/s，求最大多普勒频移，频率1GHz')
        self.assertAlmostEqual(result['parameters']['temperature_k'], 293.15)
        self.assertEqual(result['parameters']['speed_kmh'], 36)
        self.assertIn('maximum_doppler', result['conditions'])

    def test_manual_correction_is_explicit(self):
        result = self.parse('频率4.5GHz，频率5GHz', overrides={'frequency_ghz': 6})
        self.assertEqual(result['parameters']['frequency_ghz'], 6)
        self.assertEqual(result['evidence']['frequency_ghz'], ['手动输入（规范单位）'])

    def test_manual_nonfinite_and_unknown_fields_rejected(self):
        result = self.parse('计算损耗', overrides={'frequency_ghz': math.nan, 'result': 999})
        self.assertNotIn('frequency_ghz', result['parameters'])
        self.assertNotIn('result', result['parameters'])
        self.assertEqual(len(result['issues']), 2)

    def test_unicode_negative_is_preserved(self):
        result = self.parse('自由空间，频率4.5GHz，距离−200米，求路径损耗')
        self.assertEqual(result['parameters']['distance_km'], -.2)

    def test_range_and_complex_exponent_are_not_truncated(self):
        for text in ('频率4～5GHz', '距离100至200米', '距离2×10^2米'):
            with self.subTest(text=text):
                result = self.parse(text)
                self.assertFalse(result['parameters'])
                self.assertTrue(result['issues'])

    def test_negated_quantity_is_not_bound(self):
        result = self.parse('频率不是4.5GHz，距离200米')
        self.assertNotIn('frequency_ghz', result['parameters'])
        self.assertTrue(result['issues'])

    def test_si_case_never_changes_scale(self):
        for text in ('发射功率1MW', '频率1mHz'):
            with self.subTest(text=text):
                result = self.parse(text)
                self.assertFalse(result['parameters'])
                self.assertTrue(result['issues'])

    def test_unknown_or_negated_free_space_is_not_confirmation(self):
        for text in ('无法确定是否为自由空间', '自由空间不适用', '不知道是不是自由空间'):
            self.assertNotIn('free_space', self.parse(text)['conditions'])

    def test_explicit_target_takes_priority_over_known_inputs(self):
        result = self.parse('已知接收功率-50dBm，噪声温度290K，带宽1MHz，求热噪声功率')
        self.assertEqual(result['targets'], ['thermal_noise'])

    def test_negated_doppler_maximum_is_not_confirmed(self):
        result = self.parse('不用计算最大多普勒频移，只求实际多普勒频移，频率1GHz，速度36km/h')
        self.assertNotIn('maximum_doppler', result['conditions'])

    def test_multiple_explicit_targets_are_preserved(self):
        self.assertEqual(set(self.parse('求路径损耗和热噪声功率')['targets']), {'fspl_ghz', 'thermal_noise'})

    def test_unsupported_quantity_forms_are_blocked(self):
        for text in ('距离1,200米', '距离1/2km', '距离大于200米', '距离2×10²米', '距离>=200米', '距离200±10米'):
            with self.subTest(text=text):
                result = self.parse(text)
                self.assertNotIn('distance_km', result['parameters'])
                self.assertTrue(result['issues'])

    def test_area_is_not_distance(self):
        self.assertNotIn('distance_km', self.parse('面积200m²')['parameters'])

    def test_range_issue_binds_nearest_field_and_can_be_corrected(self):
        result = self.parse('频率4.5GHz，距离100至200米')
        self.assertEqual(result['issues'][0]['field'], 'distance_km')
        corrected = self.parse('频率4.5GHz，距离100至200米', overrides={'distance_km': .15})
        self.assertFalse(corrected['issues'])

    def test_unknown_label_does_not_become_distance(self):
        result = self.parse('自由空间，频率4.5GHz，天线高度200米，求路径损耗')
        self.assertNotIn('distance_km', result['parameters'])

    def test_loose_bandwidth_keeps_label_binding(self):
        result = self.parse('温度290K，带宽设置成1MHz，求热噪声功率')
        self.assertEqual(result['parameters']['bandwidth_hz'], 1000000)
        self.assertNotIn('frequency_ghz', result['parameters'])


if __name__ == '__main__':
    unittest.main()
