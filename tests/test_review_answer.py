"""The model answers and reviews a checked result; every number it writes must quote the task (H4)."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from planning.agents.review import ReviewAgent, validate_assessment
from planning.requirements_contract import digest
from planning.services.number_check import known, unquoted
from planning.workflow.task_service import TaskService
from tests.test_calculation_plans import MARGIN, MARGIN_DB, command

ROOT = Path(__file__).resolve().parents[1]
GOOD = dict(
    decision='pass',
    answer='按自由空间基准，链路余量约 17.58 dB；接收信号电平 -72.42 dBm，高于接收门限 -100 dBm。',
    opinions=[dict(kind='assumption', text='已按 10 dB 扣除预留余量；实际馈线损耗若大于 2 dB，余量相应减少。',
                   refs=['in:reserve_db', 'in:tx_loss_db'])],
    steps=[dict(id='step:fspl-step', note='按 ITU-R P.525-5 自由空间公式，路径损耗 118.42 dB。'),
           dict(id='step:link_margin-step', note='接收电平减门限与预留余量，得余量 17.58 dB。')])


def model(*outputs):
    """A stub reviewer that answers in turn and records what it was shown."""
    seen = []
    def fake(role, prompt, view, schema):
        seen.append(view)
        return dict(output=copy.deepcopy(outputs[min(len(seen), len(outputs)) - 1]))
    fake.seen = seen
    return fake


class NumberCheckTests(unittest.TestCase):
    values = known(dict(inputs=[dict(value=2.0, unit='GHz'), dict(value=34.064, unit='km'), dict(value=-92.0, unit='dBm')],
                        result=dict(outputs=[dict(value=5.928, unit='dB')]),
                        notes=['k = 4/3，按 ITU-R P.525-5（11/2024）式(6)']))

    def test_a_number_quotes_a_value_at_the_precision_it_is_written_with(self):
        for text in ['余量 5.93 dB', '余量约 5.9 dB', '余量约 6 dB', '距离 34.06 公里，即 34064 米', '频率 2000 MHz',
                     '门限 −92 dBm', '门限 -92dBm', 'k=4/3']:
            with self.subTest(text=text):
                self.assertEqual(unquoted(text, self.values), [])
        for text, bad in [('余量 5.94 dB', ['5.94 dB']), ('门限 92 dBm', ['92 dBm']), ('余量 5.93 dBm', ['5.93 dBm']),
                          ('高出 4.07 dB', ['4.07 dB']), ('余量为十分贝', ['十分贝'])]:
            with self.subTest(text=text):
                self.assertEqual(unquoted(text, self.values), bad)

    def test_names_standards_dates_and_ordinals_are_not_quantities(self):
        text = '第1步按 ITU-R P.525-5（11/2024）第 2.3 节式(6)计算；XX-100、WGS84。\n1. 路径损耗\n2. 余量'
        self.assertEqual(unquoted(text, self.values), [])

    def test_a_range_hyphen_is_not_a_minus_sign(self):
        self.assertEqual(unquoted('1.4-2.7 GHz', known(dict(a=dict(value=1.4, unit='GHz'), b=dict(value=2.7, unit='GHz')))), [])


class ReviewAnswerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.service = TaskService(ROOT, Path(self.tmp.name) / 'review.sqlite')
        self.draft = self.service.apply(command())['state']
        self.assertEqual(self.draft['status'], 'AWAITING_CONFIRMATION')

    def confirm(self, reviewer):
        with patch('planning.workflow.planning_graph.ReviewAgent', return_value=reviewer):
            return self.service.apply(command('confirm', self.draft))['state']

    def test_the_answer_opinions_and_step_notes_are_published_beside_the_program_values(self):
        fake = model(GOOD)
        done = self.confirm(ReviewAgent(fake))
        self.assertEqual(done['status'], 'COMPLETED')
        report = done['final_report']
        self.assertEqual(report['answer'], dict(text=GOOD['answer'], mode='stub', withheld=False))
        self.assertEqual(report['review']['opinions'], GOOD['opinions'])
        self.assertEqual(report['explanation'], GOOD['steps'])
        self.assertAlmostEqual(report['outputs'][0]['value'], MARGIN_DB, places=9)
        self.assertIn('17.58 dB', report['conclusion'])
        facts = fake.seen[0]['facts']
        self.assertEqual([s['id'] for s in facts['steps']], ['step:fspl-step', 'step:received_power-step', 'step:link_margin-step'])
        self.assertIn('step:fspl-step', facts['steps'][1]['uses'])

    def test_a_number_the_model_worked_out_itself_is_sent_back_once(self):
        bad = dict(GOOD, answer='链路余量 17.58 dB，接收电平比门限高 27.58 dB。')
        fake = model(bad, GOOD)
        done = self.confirm(ReviewAgent(fake))
        role = done['review_assessment']['role']
        self.assertEqual((role['mode'], role['attempts']), ('stub', 2))
        self.assertEqual(role['diagnostics'][0]['code'], 'REVIEW_NUMBERS')
        self.assertIn('27.58 dB', fake.seen[1]['correction'])
        self.assertEqual(done['final_report']['answer']['text'], GOOD['answer'])

    def test_text_that_fails_twice_is_withheld_and_the_rest_is_kept(self):
        bad = dict(GOOD, answer='链路余量 18.58 dB。', steps=[dict(id='step:fspl-step', note='路径损耗 118.42 dBm。')])
        done = self.confirm(ReviewAgent(model(bad)))
        self.assertEqual(done['status'], 'COMPLETED')
        report = done['final_report']
        self.assertEqual(report['answer'], dict(text=None, mode='stub', withheld=True))
        self.assertEqual(report['review']['withheld'], ['answer', 'steps.0'])
        self.assertEqual(report['review']['opinions'], GOOD['opinions'])
        self.assertIsNone(report['explanation'][0]['note'])
        self.assertAlmostEqual(report['outputs'][0]['value'], MARGIN_DB, places=9)

    def test_a_stored_answer_is_checked_again_before_publication(self):
        done = self.confirm(ReviewAgent(model(GOOD)))
        tampered = copy.deepcopy(done['review_assessment'])
        tampered['role']['proposal']['answer'] = '链路余量 18.58 dB。'
        tampered['assessment_hash'] = digest({k: v for k, v in tampered.items() if k != 'assessment_hash'})
        with self.assertRaisesRegex(ValueError, 'REVIEW_NUMBERS'):
            validate_assessment(tampered, done['result'], done['confirmed_snapshot'])
        tampered = copy.deepcopy(done['review_assessment'])
        tampered['facts']['result']['outputs'][0]['value'] = 18.58
        tampered['assessment_hash'] = digest({k: v for k, v in tampered.items() if k != 'assessment_hash'})
        with self.assertRaisesRegex(ValueError, 'REVIEW_FACT_CHANGED'):
            validate_assessment(tampered, done['result'], done['confirmed_snapshot'])

    def test_a_caution_needs_a_reason_and_references_must_exist(self):
        for output in [dict(GOOD, decision='caution', opinions=[]),
                       dict(GOOD, opinions=[dict(kind='risk', text='需要核对。', refs=['in:antenna_m'])]),
                       dict(GOOD, steps=list(reversed(GOOD['steps'])))]:
            with self.subTest(output=output):
                done = self.confirm(ReviewAgent(model(output)))
                self.assertEqual(done['review_assessment']['role']['mode'], 'deterministic_fallback')
                self.assertEqual(done['final_report']['answer']['text'], None)
                self.assertEqual(done['final_report']['runtime_health'], 'degraded')
                self.draft = self.service.apply(command())['state']

    def test_without_the_model_the_program_publishes_and_no_text_is_written(self):
        with patch('planning.agents.role_model.LocalRoleSelector.__call__', side_effect=ConnectionError):
            offline = self.confirm(ReviewAgent(None))
        self.assertEqual(offline['review_assessment']['role']['mode'], 'deterministic_fallback')
        self.assertEqual(offline['final_report']['answer'], dict(text=None, mode='deterministic_fallback', withheld=False))
        self.draft = self.service.apply(command())['state']
        rules = self.service.apply(command('confirm', self.draft))['state']
        self.assertEqual(rules['final_report']['answer'], dict(text=None, mode='deterministic', withheld=False))
        self.assertEqual(rules['final_report']['review']['decision'], 'pass')
        self.assertEqual(offline['final_report']['outputs'], rules['final_report']['outputs'])


if __name__ == '__main__':
    unittest.main()
