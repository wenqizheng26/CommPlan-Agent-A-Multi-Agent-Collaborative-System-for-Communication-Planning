"""Model evaluation must not turn offline or skipped calls into passing scores."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from eval_models import DEFAULT_CASES, evaluate, load_cases, percentile, score, summarize  # noqa: E402
from planning.providers.registry import Registry  # noqa: E402


class EvaluationTests(unittest.TestCase):
    def test_shipped_cases_cover_all_required_categories_and_baseline_reproduces(self):
        cases = load_cases(DEFAULT_CASES)
        self.assertEqual(len(cases), 30)
        result = evaluate(ROOT, cases, 'deterministic', Registry(ROOT))
        self.assertEqual(result['availability'], 'ready')
        self.assertTrue(all(row['passed'] for row in result['cases']))
        self.assertEqual(result['summary']['structured'], {'passed': 0, 'attempted': 0})
        self.assertEqual(result['summary']['accuracy']['status'], {'passed': 30, 'total': 30})

    def test_explicit_expectations_detect_wrong_domain_and_missing_question(self):
        report = dict(parameters_proposal=[dict(canonical_name='frequency_ghz', value={
            'kind': 'interval', 'lower': 1.9, 'upper': 2.1}, unit='GHz')],
            targets=['fspl_ghz'], conditions=['free_space'], execution_status='AWAITING_INPUT',
            diagnostics=[dict(code='MISSING_INPUT')], questions=[])
        expected = dict(parameters={'frequency_ghz': {'value': {'kind': 'interval', 'lower': 1.9,
            'upper': 2.1}, 'unit': 'GHz'}}, targets=['fspl_ghz'], conditions=['free_space'],
            status='AWAITING_INPUT', diagnostic_codes=['MISSING_INPUT'], questions_required=True)
        checks = score(report, expected)
        self.assertTrue(all(value for key, value in checks.items() if key != 'questions'))
        self.assertFalse(checks['questions'])
        report['parameters_proposal'][0]['value']['upper'] = 2.2
        self.assertFalse(score(report, expected)['parameters'])

    def test_denominators_and_nearest_rank_percentiles(self):
        rows = [dict(elapsed_ms=10 + 10 * i, checks={key: True for key in
                    ('parameters', 'targets', 'conditions', 'status', 'diagnostics', 'questions')},
                    model_attempted=i < 2, structured_success=i == 0 if i < 2 else None,
                    runtime_health='degraded' if i == 1 else 'ready',
                    degradation_reasons=['MODEL_OUTPUT_INVALID'] if i == 1 else [],
                    usage={'prompt_tokens': 10}) for i in range(5)]
        summary = summarize(rows)
        self.assertEqual(summary['structured'], {'passed': 1, 'attempted': 2})
        self.assertEqual(summary['latency_ms'], {'p50': 30, 'p95': 50})
        self.assertEqual(summary['degradation_reasons'], {'MODEL_OUTPUT_INVALID': 1})
        self.assertEqual(summary['tokens'], {'prompt_tokens': 50})
        self.assertIsNone(percentile([], 95))

    def test_offline_model_is_unscored(self):
        with patch.object(Registry, 'installed', return_value=True), \
             patch('eval_models.model_available', return_value=False):
            result = evaluate(ROOT, load_cases(DEFAULT_CASES)[:2], 'qwen3-4b-q4', Registry(ROOT))
        self.assertEqual(result['availability'], 'offline')
        self.assertEqual(result['summary']['scored'], 0)
        self.assertEqual(result['summary']['structured'], {'passed': 0, 'attempted': 0})
        self.assertTrue(all(row['checks'] is None for row in result['cases']))

    def test_uninstalled_model_is_unscored(self):
        with patch.object(Registry, 'installed', return_value=False), \
             patch('eval_models.model_available') as probe:
            result = evaluate(ROOT, load_cases(DEFAULT_CASES)[:2], 'qwen3-4b-q4', Registry(ROOT))
        self.assertEqual(result['availability'], 'not_installed')
        self.assertEqual(result['summary']['scored'], 0)
        self.assertTrue(all(row['checks'] is None for row in result['cases']))
        probe.assert_not_called()

    def test_duplicate_case_id_rejected(self):
        line = DEFAULT_CASES.read_text(encoding='utf-8').splitlines()[0]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'duplicate.jsonl'
            path.write_text(line + '\n' + line + '\n', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'duplicate'):
                load_cases(path)


if __name__ == '__main__':
    unittest.main()
