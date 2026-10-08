"""Negative modulation mentions cannot become calculation variants or completion defaults."""
from pathlib import Path
import tempfile
import unittest

from planning.workflow.task_service import TaskService
from tests.test_calculation_plans import command

ROOT = Path(__file__).resolve().parents[1]
BASE = ('计算链路余量：距离10公里，频率5.8GHz，发射功率20dBm，'
        '发射天线增益18dBi，接收天线增益18dBi，')


class ModulationExclusionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.database = Path(temporary.name) / 'tasks.sqlite'
        self.service = TaskService(ROOT, self.database)

    def create(self, ending):
        return self.service.apply(command(text=BASE + ending))['state']

    @staticmethod
    def diagnostics(state, code):
        return [d for d in state['report']['diagnostics'] if d['code'] == code]

    def assert_calculates(self, ending, expected, excluded=()):
        state = self.create(ending)
        self.assertEqual(state['status'], 'AWAITING_CONFIRMATION', (state['report'] or {}).get('questions', state.get('failure')))
        negatives = self.diagnostics(state, 'MODULATION_EXCLUDED')
        self.assertEqual([d['details']['mention'] for d in negatives], list(excluded))
        for d in negatives:
            start, end = d['details']['span']
            self.assertEqual(state['request']['raw_text'][start:end], d['details']['mention'])
        self.assertFalse(self.diagnostics(state, 'MODULATION_UNKNOWN'))
        self.assertFalse(self.diagnostics(state, 'MODULATION_NEEDED'))
        # Reconstruct the saved report before confirmation: exclusion diagnostics are information, not blockers.
        done = TaskService(ROOT, self.database).apply(command('confirm', state))['state']
        self.assertEqual(done['status'], 'COMPLETED', done.get('failure'))
        self.assertEqual([c['label'] for c in done['final_report']['tool_calls']], expected)
        return done

    def test_do_not_use_16qam_then_use_qpsk_calculates_only_qpsk(self):
        self.assert_calculates('不要16QAM，用QPSK。', ['QPSK'], ['16QAM'])

    def test_use_qpsk_then_do_not_use_16qam_calculates_only_qpsk(self):
        self.assert_calculates('用QPSK，不用16QAM。', ['QPSK'], ['16QAM'])

    def test_except_64qam_without_an_affirmative_choice_still_asks(self):
        state = self.create('除了64QAM都算。')
        self.assertEqual(state['status'], 'AWAITING_INPUT')
        self.assertIsNone(state['result'])
        [needed] = self.diagnostics(state, 'MODULATION_NEEDED')
        self.assertEqual(set(needed['details']['choices']), {'QPSK', '16QAM'})
        self.assertEqual([d['details']['mention'] for d in self.diagnostics(state, 'MODULATION_EXCLUDED')], ['64QAM'])
        self.assertFalse(self.diagnostics(state, 'MODULATION_UNKNOWN'))

    def test_positive_qpsk_and_16qam_still_calculate_both(self):
        self.assert_calculates('QPSK和16QAM分别算。', ['QPSK', '16QAM'])
        self.assert_calculates('分别用 QPSK 和 16QAM 算余量。', ['QPSK', '16QAM'])
        self.assert_calculates('非常想用QPSK。', ['QPSK'])

    def test_supported_negative_prefixes_and_suffix_do_not_leak_across_a_comma(self):
        for prefix in ('不要', '不用', '别用', '不采用', '排除', '除了', '非'):
            with self.subTest(prefix=prefix):
                self.assert_calculates(prefix + '16QAM，用QPSK。', ['QPSK'], ['16QAM'])
        self.assert_calculates('16QAM除外，用QPSK。', ['QPSK'], ['16QAM'])
        # "非" is inside the six-character lookback of the next name; the comma ends its scope.
        self.assert_calculates('非QPSK，16QAM。', ['16QAM'], ['QPSK'])

    def test_negative_unknown_is_excluded_instead_of_becoming_an_unknown_choice(self):
        self.assert_calculates('不用8PSK，用QPSK。', ['QPSK'], ['8PSK'])
        state = self.create('别用8PSK。')
        self.assertEqual(state['status'], 'AWAITING_INPUT')
        self.assertTrue(self.diagnostics(state, 'MODULATION_NEEDED'))
        self.assertFalse(self.diagnostics(state, 'MODULATION_UNKNOWN'))

    def test_completion_never_reintroduces_an_excluded_default_and_answer_keeps_it_excluded(self):
        draft = self.create('不要QPSK。')
        self.assertEqual(draft['status'], 'AWAITING_INPUT')
        [issue] = draft['input_issues']
        self.assertEqual(issue['field'], 'modulation')
        self.assertEqual({c['value'] for c in issue['choices']}, {'16QAM', '64QAM'})
        self.assertEqual(issue['suggestion']['value'], '16QAM')
        answered = self.service.apply(command('answer', draft, answers={issue['id']: issue['suggestion']['value']}))['state']
        self.assertEqual(answered['status'], 'AWAITING_CONFIRMATION', (answered['report'] or {}).get('questions', answered.get('failure')))
        done = self.service.apply(command('confirm', answered))['state']
        self.assertEqual(done['status'], 'COMPLETED', done.get('failure'))
        self.assertEqual([c['label'] for c in done['final_report']['tool_calls']], ['16QAM'])

    def test_excluding_every_registered_modulation_leaves_no_default(self):
        state = self.create('不用QPSK，不用16QAM，不用64QAM。')
        self.assertEqual(state['status'], 'AWAITING_INPUT')
        [needed] = self.diagnostics(state, 'MODULATION_NEEDED')
        self.assertEqual(needed['details']['choices'], [])
        self.assertFalse(any(item['field'] == 'modulation' for item in (state['report'].get('suggestions') or {}).get('items', [])))
        self.assertIsNone(state['result'])


if __name__ == '__main__':
    unittest.main()
