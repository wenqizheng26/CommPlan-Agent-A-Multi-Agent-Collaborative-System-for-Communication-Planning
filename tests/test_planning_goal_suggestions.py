"""Goal defaults are proposals adopted by the user, never parsed values or confirmation."""
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from planning.workflow.task_service import TaskService


ROOT = Path(__file__).resolve().parents[1]
ORIGINALS = (
    ('大概十公里出头，5.8个G，20个dBm，两边天线都18dBi，QPSK。', 'link_margin'),
    ('距离10000米，频率5800MHz，功率0.1W，增益18dBi。', 'link_margin'),
    ('信号好一点，距离没说，功率也没定。', 'link_margin'),
    ('今天天气不错，下午测试，距离10km，频率5.8G，其他你看着办。', 'fspl_ghz'),
)
COMPLETE = '距离10km，频率5.8GHz，发射功率20dBm，发射天线增益18dBi，接收天线增益18dBi，QPSK。'


def command(action='create', state=None, text=COMPLETE, manual=None, **changes):
    cmd = dict(action=action, task_id=state['task_id'] if state else str(uuid.uuid4()),
               event_id=str(uuid.uuid4()), expected_revision=state['revision'] if state else 0,
               expected_state_version=state['state_version'] if state else 0)
    if action in {'create', 'edit'}:
        cmd.update(input=dict(raw_text=text, manual_parameters=manual or {}, condition=None, target=None),
                   mode='deterministic')
    elif action == 'answer':
        cmd['mode'] = 'deterministic'
    elif action == 'confirm':
        cmd['review_hash'] = state['review']['review_hash']
    cmd.update(changes)
    return cmd


class GoalSuggestionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'tasks.sqlite'
        self.service = TaskService(ROOT, self.db)

    def create(self, text=COMPLETE, **changes):
        with patch('formula_rag.model_transport.chat', side_effect=AssertionError('no model call')), \
                patch('formula_rag.core.evaluate', side_effect=AssertionError('not confirmed')):
            state = self.service.apply(command(text=text, **changes))['state']
        self.assertEqual(state['status'], 'AWAITING_INPUT', state.get('failure'))
        self.assertIsNone(state['result'])
        self.assertIsNone(state['confirmed_snapshot'])
        return state

    def goal(self, state):
        return next(i for i in state['input_issues'] if i['field'] == 'goal')

    def adopt(self, state, value=None):
        issue = self.goal(state)
        value = value or issue['suggestion']['value']
        with patch('formula_rag.core.evaluate', side_effect=AssertionError('not confirmed')):
            return self.service.apply(command('answer', state, answers={issue['id']: value}))['state']

    def test_all_four_original_hidden_inputs_have_grounded_goal_suggestions(self):
        for text, expected in ORIGINALS:
            with self.subTest(text=text):
                state = self.create(text)
                issue = self.goal(state)
                self.assertEqual(issue['suggestion']['value'], expected)
                self.assertEqual(issue['suggestion']['note'], '默认补全，需确认')
                self.assertTrue(issue['suggestion']['reason'])
                self.assertIn(expected, [c['value'] for c in issue['choices']])
                self.assertEqual(state['request']['raw_text'], text)
                self.assertIsNone(state['request']['target'])
                self.assertEqual(state['report']['targets'], [])
                answered = self.adopt(state)
                self.assertEqual(answered['request']['target'], expected)
                self.assertIn(answered['status'], {'AWAITING_INPUT', 'AWAITING_CONFIRMATION'})
                self.assertNotIn('goal', [i['field'] for i in answered['input_issues']])

    def test_field_names_can_suggest_a_goal_without_inventing_parameter_values(self):
        state = self.create(ORIGINALS[2][0])
        self.assertEqual(state['report']['parameters_proposal'], [])
        self.assertEqual(self.goal(state)['suggestion']['value'], 'link_margin')
        answered = self.adopt(state)
        self.assertEqual(answered['request']['target'], 'link_margin')
        self.assertEqual(answered['status'], 'AWAITING_INPUT')
        self.assertNotIn('goal', [i['field'] for i in answered['input_issues']])
        self.assertEqual({i['field'] for i in answered['input_issues']},
                         {'frequency_ghz', 'distance_km', 'tx_power_dbm', 'tx_gain_dbi', 'rx_gain_dbi', 'modulation'})
        self.assertTrue(all(p['value'] is None for p in answered['report']['parameters_proposal']
                            if p['canonical_name'] in {'frequency_ghz', 'distance_km', 'tx_power_dbm', 'tx_gain_dbi', 'rx_gain_dbi'}))

    def test_no_parameter_information_gives_no_default(self):
        for text in ('', '今天天气不错，下午测试。', '信号好一点。'):
            with self.subTest(text=text):
                state = self.create(text)
                self.assertNotIn('suggestion', self.goal(state))
                self.assertIsNone(state['request']['target'])
                self.assertIsNone(state['report']['calculation_plan_proposal'])

    def test_distance_and_frequency_suggest_path_loss_then_ask_for_its_condition(self):
        state = self.create('距离1km，频率2000MHz。')
        self.assertEqual(self.goal(state)['suggestion']['value'], 'fspl_ghz')
        answered = self.adopt(state)
        self.assertEqual(answered['request']['target'], 'fspl_ghz')
        self.assertEqual(answered['status'], 'AWAITING_INPUT')
        self.assertEqual([i['field'] for i in answered['input_issues']], ['condition'])
        condition = answered['input_issues'][0]
        with patch('formula_rag.core.evaluate', side_effect=AssertionError('not confirmed')):
            ready = self.service.apply(command('answer', answered, answers={condition['id']: 'free_space_reference'}))['state']
        self.assertEqual(ready['status'], 'AWAITING_CONFIRMATION')
        self.assertIsNone(ready['result'])

    def test_geometry_with_another_parsed_field_does_not_default_to_path_loss(self):
        state = self.create('距离1km，频率2GHz，起点天线海面高度20m。')
        self.assertEqual({p['canonical_name'] for p in state['report']['parameters_proposal']},
                         {'distance_km', 'frequency_ghz', 'height1_above_sea_m'})
        self.assertNotIn('suggestion', self.goal(state))

    def test_parsed_manual_budget_inputs_take_priority_over_geometry(self):
        for field, value, unit in [('tx_power_dbm', 20, 'dBm'), ('tx_gain_dbi', 18, 'dBi'),
                                   ('rx_gain_dbi', 18, 'dBi'), ('rx_threshold_dbm', -100, 'dBm')]:
            with self.subTest(field=field):
                state = self.create('距离1km，频率2GHz。', manual={field: dict(value=value, unit=unit)})
                self.assertEqual(self.goal(state)['suggestion']['value'], 'link_margin')
                parameter = next(p for p in state['report']['parameters_proposal'] if p['canonical_name'] == field)
                self.assertEqual(parameter['origins'][0]['kind'], 'manual_form')
                self.assertEqual(parameter['value'], value)

    def test_adopted_goal_keeps_original_text_and_records_default_provenance(self):
        draft = self.create()
        answered = self.adopt(draft)
        self.assertEqual(answered['status'], 'AWAITING_CONFIRMATION', answered.get('failure'))
        self.assertEqual(answered['request']['raw_text'], COMPLETE)
        self.assertEqual(answered['conversation']['original_input']['raw_text'], COMPLETE)
        self.assertIsNone(answered['conversation']['original_input']['target'])
        turn = answered['conversation']['turns'][-1]
        self.assertEqual(turn['mode'], 'suggestion')
        self.assertTrue(turn['answers'][0]['suggested'])
        self.assertIsNone(turn['before']['target'])
        self.assertEqual(turn['after']['target'], 'link_margin')
        self.assertIn('默认补全', turn['answers'][0]['display'])
        self.assertTrue(any(d['code'] == 'USER_TARGET_SELECTION' for d in answered['report']['diagnostics']))
        self.assertEqual(TaskService(ROOT, self.db).get(answered['task_id']), answered)
        done = self.service.apply(command('confirm', answered))['state']
        self.assertEqual(done['status'], 'COMPLETED', done.get('failure'))

    def test_user_can_choose_a_different_goal(self):
        draft = self.create()
        self.assertEqual(self.goal(draft)['suggestion']['value'], 'link_margin')
        answered = self.adopt(draft, 'received_power')
        self.assertEqual(answered['request']['target'], 'received_power')
        self.assertNotIn('goal', [i['field'] for i in answered['input_issues']])
        self.assertEqual(answered['conversation']['turns'][-1]['mode'], 'user_answer')
        self.assertNotIn('suggested', answered['conversation']['turns'][-1]['answers'][0])

    def test_unknown_modulation_is_not_replaced_by_adopting_the_goal(self):
        text = COMPLETE.replace('QPSK', '8PSK')
        draft = self.create(text)
        self.assertEqual(self.goal(draft)['suggestion']['value'], 'link_margin')
        answered = self.adopt(draft)
        self.assertEqual(answered['status'], 'AWAITING_INPUT')
        self.assertIn('8PSK', answered['request']['raw_text'])
        issue = next(i for i in answered['input_issues'] if i['field'] == 'modulation')
        self.assertEqual(issue['excerpt'], '8PSK')
        self.assertNotIn('suggestion', issue)
        self.assertIsNone(answered['result'])
