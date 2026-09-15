import unittest
from pathlib import Path
from formula_rag.pipeline import Engine


class InterpretationTests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine(Path(__file__).resolve().parents[1], dense=False, llm=False)

    def test_model_can_supply_unmatched_target_with_real_evidence(self):
        self.engine.selector = lambda *_: {'selected_ids': ['thermal_noise'],
            'targets': [{'id': 'thermal_noise', 'evidence': '温度引起的底噪有多强'}], 'conditions': []}
        result = self.engine.query('温度290K，带宽1MHz，温度引起的底噪有多强')
        self.assertEqual(result['status'], 'ok')
        self.assertAlmostEqual(result['calculations'][0]['value'], -113.97518719422808)
        self.assertEqual(result['interpretation']['target_origin'], 'model')

    def test_fabricated_target_evidence_is_rejected(self):
        self.engine.selector = lambda *_: {'selected_ids': ['thermal_noise'],
            'targets': [{'id': 'thermal_noise', 'evidence': '文本中不存在的内容'}], 'conditions': []}
        result = self.engine.query('温度290K，带宽1MHz，这些参数是什么意思')
        self.assertEqual(result['status'], 'needs_input')
        self.assertFalse(result['calculations'])
        self.assertTrue(result['interpretation']['rejected'])

    def test_model_cannot_infer_free_space_from_sea(self):
        self.engine.selector = lambda *_: {'selected_ids': ['fspl_ghz'], 'targets': [],
            'conditions': [{'id': 'free_space', 'evidence': '岸站到海上平台'}]}
        result = self.engine.query('岸站到海上平台，频率4.5GHz，距离30公里，计算传输损耗')
        self.assertEqual(result['status'], 'needs_input')
        self.assertNotIn('free_space', result['request']['conditions'])
        self.assertTrue(result['interpretation']['rejected'])

    def test_model_condition_evidence_must_include_negation_context(self):
        self.engine.selector = lambda *_: {'selected_ids': ['fspl_ghz'], 'targets': [],
            'conditions': [{'id': 'free_space', 'evidence': '自由空间'}]}
        result = self.engine.query('无法确定是否为自由空间，4.5GHz，200米，求路径损耗')
        self.assertEqual(result['status'], 'needs_input')
        self.assertNotIn('free_space', result['request']['conditions'])

    def test_explicit_manual_target_wins_over_model(self):
        self.engine.selector = lambda *_: {'selected_ids': ['fspl_ghz'],
            'targets': [{'id': 'fspl_ghz', 'evidence': '自由空间'}], 'conditions': []}
        result = self.engine.query('自由空间，温度290K，带宽1MHz', target='thermal_noise')
        self.assertEqual(result['request']['targets'], ['thermal_noise'])
        self.assertEqual(result['interpretation']['target_origin'], 'manual')

    def test_grounded_model_can_classify_explicit_ideal_baseline(self):
        self.engine.selector = lambda *_: {'selected_ids': ['fspl_ghz'], 'targets': [],
            'conditions': [{'id': 'free_space_reference', 'evidence': '只计算理想无反射传播基准'}]}
        result = self.engine.query('只计算理想无反射传播基准，频率4.5GHz，距离200米，求路径损耗')
        self.assertEqual(result['status'], 'ok')
        self.assertIn('free_space_reference', result['request']['conditions'])
        self.assertAlmostEqual(result['calculations'][0]['value'], 91.48485018878651)

    def test_model_must_not_replace_explicit_unsupported_quantity(self):
        self.engine.selector = lambda *_: {'selected_ids': ['doppler_max'],
            'targets': [{'id': 'doppler_max', 'evidence': '求多普勒效应损耗'}],
            'conditions': [{'id': 'maximum_doppler', 'evidence': '求多普勒效应损耗'}]}
        result = self.engine.query('频率4.5GHz，速度0km/h，求多普勒效应损耗')
        self.assertNotIn('doppler_max', result['request']['targets'])
        self.assertEqual(result['status'], 'needs_input')

    def test_trimmed_negative_intent_is_not_accepted(self):
        self.engine.selector = lambda *_: {'selected_ids': ['thermal_noise'],
            'targets': [{'id': 'thermal_noise', 'evidence': '底噪有多强'}], 'conditions': []}
        result = self.engine.query('温度290K，带宽1MHz，我不是问底噪有多强，而是问这些单位是什么意思')
        self.assertFalse(result['calculations'])


if __name__ == '__main__':
    unittest.main()
