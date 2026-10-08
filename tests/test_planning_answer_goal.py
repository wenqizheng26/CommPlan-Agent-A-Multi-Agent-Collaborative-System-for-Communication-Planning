"""A parameter answer keeps the already established unique calculation goal."""
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from planning.workflow.task_service import TaskService


ROOT = Path(__file__).resolve().parents[1]
TEXT = '从山顶基站连到乡镇，用5.8G，传视频，功率和天线没定。'


def command(action='create', state=None, text=TEXT, mode='deterministic', **changes):
    cmd = dict(action=action, task_id=state['task_id'] if state else str(uuid.uuid4()), event_id=str(uuid.uuid4()),
               expected_revision=state['revision'] if state else 0,
               expected_state_version=state['state_version'] if state else 0)
    if action in {'create', 'edit'}:
        cmd.update(input=dict(raw_text=text, manual_parameters={}, condition=None, target=None), mode=mode)
    elif action == 'answer':
        cmd['mode'] = mode
    elif action == 'confirm':
        cmd['review_hash'] = state['review']['review_hash']
    cmd.update(changes)
    return cmd


def selector(with_goal):
    def model(text, candidates):
        return dict(raw_output=json.dumps(dict(selected_ids=['link_margin'], conditions=[],
            targets=[dict(id='link_margin', evidence='连到乡镇')] if with_goal else []), ensure_ascii=False))
    return model


class AnswerGoalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db = Path(self.temp.name) / 'tasks.sqlite'
        self.service = TaskService(ROOT, self.db)
        self.roles = patch('planning.workflow.planning_graph.LocalRoleSelector', return_value=False)
        self.roles.start()
        self.addCleanup(self.roles.stop)

    def draft(self):
        with patch('planning.workflow.task_service.LocalSelector', return_value=selector(True)):
            draft = self.service.apply(command(mode='llm'))['state']
        self.assertEqual(draft['status'], 'AWAITING_INPUT', draft.get('failure'))
        self.assertIsNone(draft['request']['target'])
        self.assertEqual(draft['report']['targets'], ['link_margin'])
        self.assertEqual({i['field'] for i in draft['input_issues']},
                         {'distance_km', 'tx_power_dbm', 'tx_gain_dbi', 'rx_gain_dbi', 'modulation'})
        return draft

    def adopt(self, draft):
        answers = {i['id']: i['suggestion']['value'] for i in draft['input_issues']}
        with patch('planning.workflow.task_service.LocalSelector', return_value=selector(False)):
            return self.service.apply(command('answer', draft, mode='llm', answers=answers))['state']

    def test_adopting_all_defaults_preserves_the_model_goal_without_reasking(self):
        draft = self.draft()
        with patch('formula_rag.core.evaluate', side_effect=AssertionError('before confirmation')):
            answered = self.adopt(draft)
        self.assertEqual(answered['request']['target'], 'link_margin')
        self.assertEqual(answered['revision'], draft['revision'] + 1)
        self.assertEqual(answered['status'], 'AWAITING_CONFIRMATION', answered.get('failure') or answered['report']['questions'])
        self.assertEqual(answered['input_issues'], [])
        self.assertIsNone(answered['result'])
        self.assertEqual(answered['conversation']['original_input']['target'], None)
        self.assertTrue(all(a['suggested'] for a in answered['conversation']['turns'][-1]['answers']))
        self.assertEqual(TaskService(ROOT, self.db).get(answered['task_id'])['request']['target'], 'link_margin')
        with patch('planning.workflow.task_service.LocalSelector', return_value=selector(False)):
            done = self.service.apply(command('confirm', answered))['state']
        self.assertEqual(done['status'], 'COMPLETED', done.get('failure'))
        self.assertAlmostEqual(done['result']['outputs'][0]['value'], 28.291440128741257)

    def test_partial_answer_also_preserves_the_goal(self):
        draft = self.draft()
        issue = next(i for i in draft['input_issues'] if i['field'] == 'distance_km')
        with patch('planning.workflow.task_service.LocalSelector', return_value=selector(False)):
            answered = self.service.apply(command('answer', draft, mode='llm', answers={issue['id']: '10km'}))['state']
        self.assertEqual(answered['request']['target'], 'link_margin')
        self.assertEqual(answered['status'], 'AWAITING_INPUT')
        self.assertNotIn('goal', [i['field'] for i in answered['input_issues']])
        self.assertEqual({i['field'] for i in answered['input_issues']},
                         {'tx_power_dbm', 'tx_gain_dbi', 'rx_gain_dbi', 'modulation'})

    def test_an_explicit_goal_answer_has_priority(self):
        state = self.service.apply(command(text='按自由空间基准，频率2GHz，距离1km。'))['state']
        self.assertEqual(state['report']['targets'], [])
        [issue] = state['input_issues']
        self.assertEqual(issue['field'], 'goal')
        answered = self.service.apply(command('answer', state, answers={issue['id']: 'fspl_ghz'}))['state']
        self.assertEqual(answered['request']['target'], 'fspl_ghz')
        self.assertEqual(answered['status'], 'AWAITING_CONFIRMATION')

    def test_multiple_report_targets_are_not_inherited(self):
        text = ('按自由空间基准计算路径损耗和链路余量，频率2GHz，发射功率20dBm，'
                '发射天线增益18dBi，接收天线增益18dBi，QPSK。')
        draft = self.service.apply(command(text=text))['state']
        self.assertEqual(set(draft['report']['targets']), {'fspl_ghz', 'link_margin'})
        issue = next(i for i in draft['input_issues'] if i['field'] == 'distance_km')
        answered = self.service.apply(command('answer', draft, answers={issue['id']: '10km'}))['state']
        self.assertIsNone(answered['request']['target'])
        self.assertEqual(set(answered['report']['targets']), {'fspl_ghz', 'link_margin'})

    def test_edit_reidentifies_the_goal_instead_of_inheriting_it(self):
        answered = self.adopt(self.draft())
        with patch('planning.workflow.task_service.LocalSelector', return_value=selector(False)):
            edited = self.service.apply(command('edit', answered, mode='llm'))['state']
        self.assertIsNone(edited['request']['target'])
        self.assertEqual(edited['status'], 'AWAITING_INPUT')
        self.assertEqual(edited['report']['targets'], [])
        self.assertEqual([i['field'] for i in edited['input_issues']], ['goal'])

    def test_existing_request_target_is_preserved(self):
        text = '按自由空间基准计算，频率2GHz，发射功率20dBm，发射天线增益18dBi，接收天线增益18dBi。'
        draft = self.service.apply(command(text=text, input=dict(raw_text=text, manual_parameters={},
                                      condition=None, target='received_power')))['state']
        issue = next(i for i in draft['input_issues'] if i['field'] == 'distance_km')
        answered = self.service.apply(command('answer', draft, answers={issue['id']: '10km'}))['state']
        self.assertEqual(answered['request']['target'], 'received_power')
        self.assertEqual(answered['report']['targets'], ['received_power'])
