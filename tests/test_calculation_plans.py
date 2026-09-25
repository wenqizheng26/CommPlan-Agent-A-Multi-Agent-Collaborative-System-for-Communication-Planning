import copy
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import uuid

from formula_rag.catalog import load_catalog
from formula_rag.model import evidence_spans
from formula_rag.model_transport import estimate_tokens
from planning.agents import role_model
from planning.agents.requirements import correction_hints
from planning.agents.review import ReviewAgent
from planning.services import calculation
from planning.services.plans import chain, final_target, bound_issues
from planning.workflow.task_service import TaskService, review_context

ROOT = Path(__file__).resolve().parents[1]
BUDGET = ('发射功率30dBm，发射天线增益10dBi，接收天线增益10dBi，发射馈线损耗2dB，'
          '接收馈线损耗2dB，额外损耗0dB')
MARGIN = f'按自由空间基准计算链路余量：频率2GHz，距离10km，{BUDGET}，接收灵敏度-100dBm，预留余量10dB。'
POWER = f'按自由空间基准计算接收功率：频率2GHz，距离10km，{BUDGET}。'
# 92.4 + 20log10(2) + 20log10(10), then the budget sums, by hand.
FSPL = 118.42059991327963
RX = 30 + 10 + 10 - 2 - 2 - FSPL - 0
MARGIN_DB = RX - (-100) - 10


def command(action='create', state=None, text=MARGIN, **changes):
    c = dict(action=action, task_id=state['task_id'] if state else str(uuid.uuid4()),
             event_id=str(uuid.uuid4()), expected_revision=state['revision'] if state else 0,
             expected_state_version=state['state_version'] if state else 0)
    if action in {'create', 'edit'}:
        c.update(input=dict(raw_text=text, manual_parameters={}, condition=None, target=None), mode='deterministic')
    if action == 'answer':
        c['mode'] = 'deterministic'
    if action == 'confirm':
        c['review_hash'] = state['review']['review_hash']
    c.update(changes)
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
        issues = {i['field']: i for i in state['input_issues']}
        self.assertEqual(set(issues), set(state['report']['missing_parameters']))
        self.assertEqual(issues['rx_threshold_dbm']['title'], '请补充接收门限（dBm）')
        self.assertIn('-100dBm', issues['rx_threshold_dbm']['detail'])

    def answer(self, state, values):
        ids = {i['field']: i['id'] for i in state['input_issues']}
        return self.service.apply(command('answer', state, answers={ids[k]: v for k, v in values.items()}))['state']

    def test_budget_questions_are_answered_one_field_at_a_time(self):
        state = self.service.apply(command(text='按自由空间基准计算链路余量，频率2GHz，距离10km，发射功率30dBm。'))['state']
        # Labelled and bare answers are both accepted; the question already names the field.
        state = self.answer(state, dict(tx_gain_dbi='发射天线增益10dBi', rx_gain_dbi='10dBi', tx_loss_db='2dB',
                                        rx_loss_db='2dB', extra_loss_db='0dB'))
        self.assertEqual(state['status'], 'AWAITING_INPUT')
        self.assertEqual({i['field'] for i in state['input_issues']}, {'rx_threshold_dbm', 'reserve_db'})
        state = self.answer(state, dict(rx_threshold_dbm='-100dBm', reserve_db='10dB'))
        self.assertEqual(state['status'], 'AWAITING_CONFIRMATION', state['report']['questions'])
        # Each answer becomes one readable "label value" line, whether or not it was labelled.
        text = state['request']['raw_text']
        self.assertEqual(text.count('发射天线增益'), 1)
        self.assertEqual(text.count('接收天线增益'), 1)
        self.assertIn('接收门限-100dBm', text)
        done = self.service.apply(command('confirm', state))['state']
        self.assertAlmostEqual(done['result']['outputs'][0]['value'], MARGIN_DB, places=9)

    def test_budget_values_can_be_supplied_in_one_supplement(self):
        state = self.service.apply(command(text='按自由空间基准计算链路余量，频率2GHz，距离10km。'))['state']
        message = BUDGET + '，接收灵敏度-100dBm，预留余量10dB'
        state = self.service.apply(command('supplement', state, message=message, mode='deterministic'))['state']
        self.assertEqual(state['status'], 'AWAITING_CONFIRMATION', state['report']['questions'])
        self.assertEqual(state['request']['raw_text'].count('预留余量'), 1)
        done = self.service.apply(command('confirm', state))['state']
        self.assertAlmostEqual(done['result']['outputs'][0]['value'], MARGIN_DB, places=9)

    def test_a_changed_budget_value_replaces_the_old_one(self):
        draft = self.service.apply(command(text=MARGIN))['state']
        state = self.service.apply(command('supplement', draft, message='发射功率改为33dBm', mode='deterministic'))['state']
        self.assertEqual(state['status'], 'AWAITING_CONFIRMATION')
        self.assertIn('发射功率33dBm', state['request']['raw_text'])
        self.assertNotIn('30dBm', state['request']['raw_text'])
        done = self.service.apply(command('confirm', state))['state']
        self.assertAlmostEqual(done['result']['outputs'][0]['value'], MARGIN_DB + 3, places=9)

    def test_review_input_fits_the_local_model_context_after_several_turns(self):
        state = self.service.apply(command(text='按自由空间基准计算链路余量，频率2GHz，距离10km，发射功率30dBm。'))['state']
        state = self.answer(state, dict(tx_gain_dbi='10dBi', rx_gain_dbi='10dBi', tx_loss_db='2dB', rx_loss_db='2dB', extra_loss_db='0dB'))
        state = self.service.apply(command('supplement', state, message='接收灵敏度-100dBm，预留余量10dB', mode='deterministic'))['state']
        state = self.service.apply(command('supplement', state, message='发射功率改为33dBm', mode='deterministic'))['state']
        done = self.service.apply(command('confirm', state))['state']
        sent = []
        def fake_chat(payload, *args, **kwargs):
            sent.append(payload)
            return {}, '{"decision":"pass","answer":"链路余量为 20.58 dB。","opinions":[],"steps":[]}'
        with mock.patch.object(role_model, 'chat', fake_chat):
            role = ReviewAgent(selector=None, context=review_context(done['conversation'])).run(
                done['result'], done['confirmed_snapshot'])['role']
        self.assertEqual(role['mode'], 'llm')
        # The demo model has at least 8K of context (AGENT_LED §0); the 4B profiles fall back when it does not fit.
        self.assertLessEqual(estimate_tokens(sent[0]), 8192)

    def test_a_budget_answer_must_be_one_value_for_that_field(self):
        state = self.service.apply(command(text='按自由空间基准计算链路余量，频率2GHz，距离10km。'))['state']
        for bad in ('30dBm或33dBm', '接收门限-100dBm', '大概30dBm', '30'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                self.answer(state, dict(tx_power_dbm=bad))

    def test_multi_step_plans_refuse_intervals(self):
        text = MARGIN.replace('距离10km', '距离10至20km')
        state = self.service.apply(command(text=text))['state']
        self.assertEqual(state['status'], 'AWAITING_INPUT')
        self.assertIn('PLAN_DOMAIN_UNSUPPORTED', [d['code'] for d in state['report']['diagnostics']])

    def test_negative_feed_loss_is_rejected_before_confirmation(self):
        state = self.service.apply(command(text=MARGIN.replace('发射馈线损耗2dB', '发射馈线损耗-2dB')))['state']
        self.assertEqual(state['status'], 'AWAITING_INPUT')
        self.assertTrue(any('tx_loss_db' in q for q in state['report']['questions']))
        issue = next(i for i in state['input_issues'] if i['field'] == 'tx_loss_db')
        self.assertEqual(issue['kind'], 'invalid')
        state = self.answer(state, dict(tx_loss_db='2dB'))
        self.assertEqual(state['status'], 'AWAITING_CONFIRMATION')
        self.assertNotIn('-2dB', state['request']['raw_text'])

    def test_tampered_intermediate_value_fails_validation(self):
        _, done = self.run_text(MARGIN)
        result = copy.deepcopy(done['result'])
        result['steps'][1]['output']['value'] += 1
        result['result_hash'] = calculation.digest({k: v for k, v in result.items() if k != 'result_hash'})
        checks = {v['validator_id']: v['passed'] for v in calculation.validate_result(result, done['confirmed_snapshot'])}
        self.assertFalse(checks['step_chain'])
        self.assertFalse(checks['independent_magnitude'])
        self.assertTrue(checks['result_integrity'])


class ModelEvidenceTests(unittest.TestCase):
    def test_evidence_choices_are_verbatim_clauses_and_their_parts(self):
        text = '按自由空间基准计算接收功率和链路余量，频率2GHz。'
        spans = evidence_spans(text)
        self.assertIn('按自由空间基准计算接收功率和链路余量', spans)
        self.assertIn('链路余量', spans)
        self.assertTrue(all(s in text for s in spans))
        self.assertEqual(evidence_spans(''), [])

    def test_a_retry_is_told_which_item_failed(self):
        text = '按自由空间基准计算链路余量，频率2GHz，距离1km。'
        copied = '{"selected_ids":["link_margin"],"targets":[{"id":"link_margin","evidence":"计算接收电平高于接收门限的余量"}],"conditions":[]}'
        [hint] = correction_hints(copied, text)
        self.assertIn('不是用户问题的原文片段', hint)
        wrong = '{"selected_ids":["fspl_ghz"],"targets":[{"id":"fspl_ghz","evidence":"计算链路余量"}],"conditions":[]}'
        self.assertIn("['link_margin']", correction_hints(wrong, text)[0])
        self.assertEqual(correction_hints('{"selected_ids":[],"targets":[{"id":"link_margin","evidence":"计算链路余量"}],"conditions":[]}', text), [])
        # A rejected guess is answered with "leave it empty", never with a suggested value.
        empty = '{"selected_ids":[],"targets":[],"conditions":[]}'
        [hint] = correction_hints(empty, text, [{'kind': 'condition', 'id': 'free_space', 'reason': '原文不足以确认该传播假设'}])
        self.assertIn('conditions 返回空数组', hint)
        [hint] = correction_hints(empty, text, [{'kind': 'target', 'reason': '证据未明确计算意图'}])
        self.assertIn('targets 返回空数组', hint)


if __name__ == '__main__':
    unittest.main()
