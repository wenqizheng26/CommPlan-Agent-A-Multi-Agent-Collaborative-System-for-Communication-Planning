import unittest
from pathlib import Path
from formula_rag.catalog import load_catalog


class PresentationTests(unittest.TestCase):
    def test_latex_is_derived_from_actual_expression(self):
        from formula_rag.presentation import formula_view
        card = load_catalog(Path(__file__).resolve().parents[1])[0]
        view = formula_view(card)
        self.assertIn(r'\log_{10}', view['latex'])
        self.assertIn('92.4', view['latex'])
        self.assertNotIn('frequency_ghz', view['latex'])
        self.assertEqual(view['symbols'][0]['field'], 'frequency_ghz')
        self.assertEqual(view['symbols'][0]['unit'], 'GHz')
        changed = {**card, 'expression': '93.4 + 20*log10(frequency_ghz)'}
        self.assertIn('93.4', formula_view(changed)['latex'])

    def test_subtraction_and_division_keep_grouping(self):
        from formula_rag.presentation import expression_latex
        self.assertIn(r'\left(', expression_latex('a-(b+c)'))
        self.assertIn(r'\frac', expression_latex('a/(b+c)'))
        self.assertIn(r'\left(', expression_latex('(a+b)*c'))


if __name__ == '__main__':
    unittest.main()
