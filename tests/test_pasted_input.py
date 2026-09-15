import unittest
from pathlib import Path
from formula_rag.pipeline import Engine
from formula_rag.parsing import extract_request

PASTE = '''工作频率 4.5Ghz
通信距离 0.2km
比特速率（kb/s）1000000
解调门限Eb/N0（误码-6）15
工程损失（dB）3
收信机噪声系数（dB）4
发射信号电平（dBm）40
发馈线损耗（dB）2
收馈线损耗（dB）2
发天线增益（dB）2
收天线增益（dB）2
空中平台漂移损耗（dB）0
其他损耗（dB）0
计算 总传输损耗L = 92.4+Lf+Ld
多普勒效应损耗（dB）
接收门限（dBm）
接收信号电平（dBm）
电平余量F（dB）'''


class PastedInputTests(unittest.TestCase):
    def setUp(self):
        self.engine = Engine(Path(__file__).resolve().parents[1], dense=False, llm=False)

    def test_unit_before_value_and_all_requested_outputs(self):
        parsed = extract_request(PASTE)
        self.assertEqual(parsed['parameters']['bit_rate_bps'], 1e9)
        self.assertEqual(parsed['parameters']['tx_power_dbm'], 40)
        self.assertEqual(parsed['parameters']['engineering_loss_db'], 3)
        self.assertIn('receiver_threshold', parsed['targets'])
        self.assertIn('received_power', parsed['targets'])
        self.assertIn('link_margin', parsed['targets'])
        self.assertIn('free_space_reference', parsed['conditions'])
        self.assertNotIn('speed_kmh', parsed['parameters'])
        self.assertNotIn('temperature_k', parsed['parameters'])
        self.assertNotIn('noise_density_dbm_hz', parsed['parameters'])
        self.assertNotIn('tx_gain_dbi', parsed['parameters'])
        self.assertNotIn('ebn0_db', parsed['parameters'])

    def test_reference_input_is_partial_not_silently_completed(self):
        result = self.engine.query(PASTE)
        fspl = next(c for c in result['calculations'] if c['id'] == 'fspl_ghz')
        self.assertAlmostEqual(fspl['value'], 91.48485018878651)
        self.assertNotEqual(result['status'], 'ok')
        questions = ' '.join(result['questions'])
        self.assertIn('噪声', questions)
        self.assertIn('相对速度', questions)
        self.assertIn('dBi', questions)
        self.assertIn('模型', questions)
        self.assertNotIn('请补充接收信号电平', questions)
        self.assertNotIn('请补充接收门限', questions)
        self.assertIn('或参考噪声温度', questions)

    def test_explicit_completed_budget_matches_reference_numbers(self):
        text = '''按自由空间基准计算
工作频率（GHz）4.5
通信距离（km）0.2
比特速率（kb/s）1000000
噪声谱密度（dBm/Hz）-174
解调门限Eb/N0（dB）15
工程损失（dB）3
收信机噪声系数（dB）4
发射信号电平（dBm）40
发馈线损耗（dB）2
收馈线损耗（dB）2
发天线增益（dBi）2
收天线增益（dBi）2
额外损耗（dB）0
预留余量（dB）0
计算 传输损耗
接收门限（dBm）
接收信号电平（dBm）
电平余量F（dB）'''
        result = self.engine.query(text)
        self.assertEqual(result['status'], 'ok', result['questions'])
        values = {c['id']: c.get('value') for c in result['calculations']}
        self.assertAlmostEqual(values['fspl_ghz'], 91.48485018878651)
        self.assertAlmostEqual(values['receiver_threshold'], -62)
        self.assertAlmostEqual(values['received_power'], -51.48485018878651)
        self.assertAlmostEqual(values['link_margin'], 10.51514981121349)


if __name__ == '__main__':
    unittest.main()
