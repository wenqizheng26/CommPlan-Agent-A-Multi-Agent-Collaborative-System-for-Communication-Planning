"""Wordings the rules used to misread: a model name next to a number, "是否满足", a stated margin requirement."""
import unittest

from formula_rag.parsing import extract_request
from planning.services.input_domains import extract_domains
from planning.services.requirement_policy import validate_target_semantics
from planning.services.requirement_quantities import RANGE, UNCERTAIN


class WordingTests(unittest.TestCase):
    def test_a_model_name_before_a_number_is_not_a_list_of_candidates(self):
        found, issues = extract_domains('XX-100、2 GHz，距离 30 km')
        self.assertEqual((found, issues), ([], []))
        self.assertIsNone(RANGE.search('XX-100、2 GHz'))
        # Real alternatives are still refused.
        found, _ = extract_domains('用 2 GHz 或 3 GHz')
        self.assertEqual(found[0]['value'], dict(kind='choices', values=[2.0, 3.0]))
        self.assertIsNotNone(RANGE.search('2 GHz、3 GHz'))

    def test_asking_whether_a_requirement_is_met_does_not_hide_the_numbers(self):
        parsed = extract_request('频率 2 GHz，链路余量是否满足 10 dB？')
        self.assertEqual(parsed['parameters'].get('frequency_ghz'), 2.0)
        self.assertEqual(parsed['issues'], [])
        self.assertIsNone(UNCERTAIN.search('是否满足'))
        # Uncertainty about the value itself still blocks it.
        parsed = extract_request('是否用 2 GHz 还不确定')
        self.assertNotIn('frequency_ghz', parsed['parameters'])
        self.assertTrue(parsed['issues'])

    def test_a_stated_margin_requirement_is_a_margin_target_and_a_concept_question_is_not(self):
        validate_target_semantics(dict(targets=[dict(id='link_margin', evidence='链路余量要不低于 10 dB')]))
        with self.assertRaisesRegex(ValueError, 'MODEL_TARGET_CONCEPT'):
            validate_target_semantics(dict(targets=[dict(id='link_margin', evidence='解释什么是链路余量')]))


if __name__ == '__main__':
    unittest.main()
