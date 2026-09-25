"""Answering what the fact store left open: a missing antenna height, a shared site name, a text-versus-record conflict."""
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from planning.workflow.task_service import TaskService
from test_requirement_facts import ask, labeller

ROOT = Path(__file__).resolve().parents[1]


def understand(text, candidates):
    """The stub model reads whichever second site the current text names."""
    end = next((name for name in ('东港', '西港', '港口', 'D', 'B') if f'{name} 站' in text or f'{name}站' in text), 'B')
    return labeller(text, end)(text, candidates)


class FactAnswerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.service = TaskService(ROOT, Path(self.tmp.name) / 'answers.sqlite')

    def apply(self, action, state=None, **extra):
        c = dict(action=action, task_id=state['task_id'] if state else str(uuid.uuid4()), event_id=str(uuid.uuid4()),
                 expected_revision=state['revision'] if state else 0, expected_state_version=state['state_version'] if state else 0,
                 **extra)
        with patch('planning.workflow.task_service.LocalSelector', return_value=understand):
            return self.service.apply(c)['state']

    def create(self, text):
        return self.apply('create', input=dict(raw_text=text, manual_parameters={}, condition=None, target=None), mode='llm')

    def answer(self, state, field, value):
        [issue] = [i for i in state['input_issues'] if i['field'] == field]
        return self.apply('answer', state, answers={issue['id']: value}, mode='llm')

    def test_a_missing_antenna_height_is_answered_in_the_panel(self):
        state = self.create(ask('D'))
        issue = next(i for i in state['input_issues'] if i['field'] == 'antenna2_m')
        self.assertEqual(issue['title'], '请补充接收端天线离地高度（m）')
        state = self.answer(state, 'antenna2_m', '20米')
        self.assertEqual(state['status'], 'AWAITING_CONFIRMATION', state['report']['questions'])
        self.assertEqual(state['request']['manual_parameters']['antenna2_m'], {'value': 20.0, 'unit': 'm'})

    def test_a_shared_site_name_is_chosen_and_the_text_names_that_site(self):
        state = self.create(ask('港口'))
        issue = next(i for i in state['input_issues'] if i['field'] == 'entity')
        self.assertEqual([c['value'] for c in issue['choices']], ['东港站', '西港站'])
        state = self.answer(state, 'entity', '东港站')
        self.assertIn('A 站到 东港站用 XX-100', state['request']['raw_text'])
        self.assertEqual(state['status'], 'AWAITING_CONFIRMATION', state['report']['questions'])
        lat = next(p for p in state['report']['parameters_proposal'] if p['canonical_name'] == 'lat2_deg')
        self.assertEqual(lat['origins'][0]['source_ref'], 'site:sim-east#position.lat')

    def test_the_chosen_value_settles_a_text_versus_record_conflict(self):
        for choice, expected in [('40dBm', 40.0), ('37dBm', 37.0)]:
            with self.subTest(choice=choice):
                state = self.create(ask(extra='、发射功率 40 dBm'))
                issue = next(i for i in state['input_issues'] if i['field'] == 'tx_power_dbm')
                self.assertEqual(issue['kind'], 'conflict')
                state = self.answer(state, 'tx_power_dbm', choice)
                self.assertEqual(state['status'], 'AWAITING_CONFIRMATION', state['report']['questions'])
                power = next(p for p in state['report']['parameters_proposal'] if p['canonical_name'] == 'tx_power_dbm')
                self.assertEqual(power['value'], expected)
                self.assertEqual(sorted(o['kind'] for o in power['origins']), ['manual_form', 'user_text'])


if __name__ == '__main__':
    unittest.main()
