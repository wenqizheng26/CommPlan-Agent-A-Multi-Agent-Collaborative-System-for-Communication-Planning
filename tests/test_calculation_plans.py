import copy
from pathlib import Path
import tempfile
import unittest
import uuid

from formula_rag.catalog import load_catalog
from planning.services import calculation
from planning.services.plans import chain, final_target, bound_issues
from planning.workflow.task_service import TaskService

ROOT = Path(__file__).resolve().parents[1]
BUDGET = ('发射功率30dBm，发射天线增益10dBi，接收天线增益10dBi，发射馈线损耗2dB，'
          '接收馈线损耗2dB，额外损耗0dB')
MARGIN = f'按自由空间基准计算链路余量：频率2GHz，距离10km，{BUDGET}，接收灵敏度-100dBm，预留余量10dB。'
POWER = f'按自由空间基准计算接收功率：频率2GHz，距离10km，{BUDGET}。'
# 92.4 + 20log10(2) + 20log10(10), then the budget sums, by hand.
FSPL = 118.42059991327963
RX = 30 + 10 + 10 - 2 - 2 - FSPL - 0
MARGIN_DB = RX - (-100) - 10


def command(action='create', state=None, text=MARGIN):
    c = dict(action=action, task_id=state['task_id'] if state else str(uuid.uuid4()),
             event_id=str(uuid.uuid4()), expected_revision=state['revision'] if state else 0,
             expected_state_version=state['state_version'] if state else 0)
    if action in {'create', 'edit'}:
        c.update(input=dict(raw_text=text, manual_parameters={}, condition=None, target=None), mode='deterministic')
    if action == 'confirm':
        c['review_hash'] = state['review']['review_hash']
    return c


class PlannerTests(unittest.TestCase):
    cards = load_catalog(ROOT)

    def test_chain_follows_output_names_in_execution_order(self):
        order, leaves = chain('link_margin', self.cards, set())
        self.assertEqual(order, ['fspl_ghz', 'received_power', 'link_margin'])
        self.assertIn('frequency_ghz', leaves)
        self.assertIn('rx_threshold_dbm', leaves)
        self.assertNotIn('path_loss_db', leaves)
        self.assertNotIn('rx_power_dbm', leaves)

    def test_a_given_intermediate_value_replaces_its_upstream_step(self):
        order, leaves = chain('link_margin', self.cards, {'path_loss_db'})
        self.assertEqual(order, ['received_power', 'link_margin'])
        self.assertIn('path_loss_db', leaves)
        self.assertNotIn('frequency_ghz', leaves)

    def test_final_target_must_cover_every_requested_quantity(self):
        self.assertEqual(final_target(['received_power', 'link_margin'], self.cards), 'link_margin')
        self.assertEqual(final_target(['fspl_ghz'], self.cards), 'fspl_ghz')
        self.assertIsNone(final_target(['link_margin', 'thermal_noise'], self.cards))
        self.assertIsNone(final_target([], self.cards))

    def test_declared_card_domains_are_checked_before_confirmation(self):
        order, _ = chain('received_power', self.cards, set())
        self.assertEqual(bound_issues(order, self.cards, {'tx_loss_db': -1, 'rx_loss_db': 0}), ['tx_loss_db'])


class PlanLoopTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.service = TaskService(ROOT, Path(tmp.name) / 'tasks.sqlite')

    def run_text(self, text):
        draft = self.service.apply(command(text=text))['state']
        self.assertEqual(draft['status'], 'AWAITING_CONFIRMATION', draft['report']['questions'])
        return draft, self.service.apply(command('confirm', draft))['state']

    def test_link_margin_runs_three_confirmed_steps_and_matches_hand_calculation(self):
        draft, done = self.run_text(MARGIN)
        plan = draft['report']['calculation_plan_proposal']
        self.assertEqual([s['tool_id'] for s in plan['steps']], ['fspl_ghz', 'received_power', 'link_margin'])
        self.assertEqual(done['status'], 'COMPLETED')
        steps = done['result']['steps']
        self.assertAlmostEqual(steps[0]['output']['value'], FSPL, places=9)
        self.assertAlmostEqual(steps[1]['output']['value'], RX, places=9)
        self.assertAlmostEqual(done['result']['outputs'][0]['value'], MARGIN_DB, places=9)
        self.assertEqual(steps[1]['inputs']['path_loss_db'], steps[0]['output']['value'])
        self.assertEqual(done['result']['tool_version'].split('/')[0], 'confirmed-plan-v1')
        ids = {v['validator_id'] for v in done['validations'] if v['passed']}
        self.assertTrue({'step_chain', 'independent_magnitude', 'input_consistency'} <= ids)
        self.assertIn('链路余量 17.58 dB', done['final_report']['conclusion'])
        self.assertIn('高于门限', done['final_report']['conclusion'])

    def test_received_power_is_a_two_step_plan(self):
        _, done = self.run_text(POWER)
        self.assertEqual(done['status'], 'COMPLETED')
        self.assertEqual([s['tool_id'] for s in done['result']['steps']], ['fspl_ghz', 'received_power'])
        self.assertAlmostEqual(done['result']['outputs'][0]['value'], RX, places=9)

    def test_single_step_fspl_keeps_the_v010_result_shape(self):
        _, done = self.run_text('按自由空间基准计算，频率2GHz，距离1km，求路径损耗。')
        self.assertNotIn('steps', done['result'])
        self.assertEqual(done['result']['outputs'][0]['value'], 98.42059991327963)
        self.assertTrue(done['result']['tool_version'].startswith('confirmed-fspl-v1/'))

    def test_missing_budget_inputs_are_asked_not_guessed(self):
        state = self.service.apply(command(text='按自由空间基准计算链路余量，频率2GHz，距离1km。'))['state']
        self.assertEqual(state['status'], 'AWAITING_INPUT')
        self.assertIn('tx_power_dbm', state['report']['missing_parameters'])
        # The plan is shown with its open inputs, but it cannot be confirmed.
        self.assertEqual(len(state['report']['calculation_plan_proposal']['steps']), 3)
        self.assertTrue(state['report']['questions'])
        detail = next(i['detail'] for i in state['input_issues'] if i['title'] == '请补充计算所需参数')
        self.assertIn('接收门限（dBm）', detail)
        self.assertNotIn('rx_threshold_dbm', detail)

    def test_multi_step_plans_refuse_intervals(self):
        text = MARGIN.replace('距离10km', '距离10至20km')
        state = self.service.apply(command(text=text))['state']
        self.assertEqual(state['status'], 'AWAITING_INPUT')
        self.assertIn('PLAN_DOMAIN_UNSUPPORTED', [d['code'] for d in state['report']['diagnostics']])

    def test_negative_feed_loss_is_rejected_before_confirmation(self):
        state = self.service.apply(command(text=MARGIN.replace('发射馈线损耗2dB', '发射馈线损耗-2dB')))['state']
        self.assertEqual(state['status'], 'AWAITING_INPUT')
        self.assertTrue(any('tx_loss_db' in q for q in state['report']['questions']))

    def test_tampered_intermediate_value_fails_validation(self):
        _, done = self.run_text(MARGIN)
        result = copy.deepcopy(done['result'])
        result['steps'][1]['output']['value'] += 1
        result['result_hash'] = calculation.digest({k: v for k, v in result.items() if k != 'result_hash'})
        checks = {v['validator_id']: v['passed'] for v in calculation.validate_result(result, done['confirmed_snapshot'])}
        self.assertFalse(checks['step_chain'])
        self.assertFalse(checks['independent_magnitude'])
        self.assertTrue(checks['result_integrity'])


if __name__ == '__main__':
    unittest.main()
