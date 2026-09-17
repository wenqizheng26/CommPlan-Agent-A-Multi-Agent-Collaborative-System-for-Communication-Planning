import copy
import json
import tempfile
import unittest
from pathlib import Path

try:
    from formula_rag.importing import import_card, approve_card
except ImportError:
    import_card = approve_card = None


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(import_card, '公式导入工具尚未实现')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'knowledge').mkdir()
        (self.root/'knowledge/formulas.json').write_text('[]')
        self.card = {'id': 'wavelength', 'title': '真空波长', 'description': '真空波长与频率的关系',
                     'version': '1.0', 'status': 'verified', 'expression': '299792458 / (frequency_ghz * 1000000000)',
                     'output': {'name': 'wavelength_m', 'unit': 'm'},
                     'parameters': {'frequency_ghz': {'description': '频率', 'unit': 'GHz', 'exclusive_min': 0}},
                     'applicability': {'requires': []}, 'sources': [{'title': 'NIST c', 'url': 'https://physics.nist.gov/cuu/Constants/Value/c.html'}],
                     'examples': [{'inputs': {'frequency_ghz': 1}, 'expected': .299792458, 'tolerance': 1e-12}]}

    def test_import_forces_draft_and_duplicate_is_rejected(self):
        result = import_card(self.root, self.card)
        self.assertEqual(result['status'], 'draft')
        with self.assertRaises(ValueError):
            import_card(self.root, self.card)

    def test_approval_checks_numeric_examples(self):
        self.card['examples'][0]['expected'] = 99
        import_card(self.root, self.card)
        with self.assertRaises(ValueError):
            approve_card(self.root, 'wavelength', 'local reviewer')

    def test_explicit_approval_records_reviewer(self):
        import_card(self.root, self.card)
        result = approve_card(self.root, 'wavelength', 'local reviewer')
        self.assertEqual(result['status'], 'verified')
        self.assertEqual(result['review']['reviewer'], 'local reviewer')

    def test_custom_parameters_are_usable_after_import(self):
        self.card.update(id='double_height', title='高度算术示例', description='仅扩展机制测试', expression='height_m*2')
        self.card['parameters'] = {'height_m': {'unit': 'm', 'description': '高度', 'exclusive_min': 0}}
        self.card['examples'] = [{'inputs': {'height_m': 10}, 'expected': 20, 'tolerance': 1e-12}]
        import_card(self.root, self.card)
        approve_card(self.root, 'double_height', 'test reviewer')
        from formula_rag.pipeline import Engine
        result = Engine(self.root, dense=False, llm=False).query('计算高度', target='double_height', parameters={'height_m': 10})
        self.assertEqual(result['status'], 'ok')
        self.assertEqual(result['calculations'][0]['value'], 20)

    def test_unknown_applicability_rules_rejected_at_import(self):
        self.card['applicability']['requires'] = ['far_field']
        with self.assertRaises(ValueError):
            import_card(self.root, self.card)


if __name__ == '__main__':
    unittest.main()
