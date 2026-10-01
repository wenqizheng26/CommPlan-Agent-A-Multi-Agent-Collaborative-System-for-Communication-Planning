"""The teacher's link-margin path (TEACHER_CASES): modulation table, calc_link_margin, comparison."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from planning.services import calculation
from planning.requirements_contract import digest
from planning.workflow.task_service import TaskService
from test_calculation_plans import ROOT, MARGIN, command

CASES = {c['id']: c for c in map(json.loads, (ROOT / 'tests/eval/teacher_cases.jsonl').read_text(encoding='utf-8').splitlines())}
# Without the model the rules bind a gain only when it is labelled as one.
TEXT3 = CASES['teacher_03']['text'].replace('天线 12dBi', '天线增益 12dBi')
ROW = ('rx_sensitivity_dbm', 'path_loss_db', 'rx_power_dbm', 'link_margin_db', 'meets')


def manual(text, target='link_margin'):
    return dict(input=dict(raw_text=text, manual_parameters={}, condition=None, target=target))


class TeacherPathTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.service = TaskService(ROOT, Path(tmp.name) / 'tasks.sqlite')

    def run_case(self, case_id, **changes):
        draft = self.service.apply(command(text=TEXT3 if case_id == 'teacher_03' else CASES[case_id]['text'], **changes))['state']
        self.assertEqual(draft['status'], CASES[case_id]['expected']['first_stop'], draft['report']['questions'])
        return draft, self.service.apply(command('confirm', draft))['state']

    def assert_rows(self, rows, expected):
        self.assertEqual([r['modulation'] if 'modulation' in r else r['label'] for r in rows], [r['modulation'] for r in expected])
        for got, want in zip(rows, expected):
            for key in ROW:
                if key == 'meets':
                    self.assertEqual(got[key], want[key])
                else:
                    self.assertAlmostEqual(got[key], want[key], delta=1e-9)

    def test_case_one_runs_as_calc_link_margin_with_the_qpsk_sensitivity(self):
        draft, done = self.run_case('teacher_01')
        report = draft['report']
        plan = report['calculation_plan_proposal']
        self.assertEqual((plan['selected_model'], plan['tool']), (['fspl_mhz', 'received_power', 'link_margin'], 'calc_link_margin'))
        self.assertEqual(report['conditions'], ['free_space'])
        params = {p['canonical_name']: p for p in report['parameters_proposal']}
        self.assertEqual([(o['kind'], o['source_ref']) for o in params['rx_threshold_dbm']['origins']],
                         [('modulation', 'modulation:qpsk#rx_sensitivity_dbm')])
        self.assertTrue(all(params[n]['value'] == 0 and params[n]['origins'][0]['source_ref'] == 'tool:calc_link_margin#' + n
                            for n in ('tx_loss_db', 'rx_loss_db', 'extra_loss_db', 'reserve_db')))
        self.assertEqual(done['status'], 'COMPLETED', done.get('failure'))
        [call] = done['final_report']['tool_calls']
        self.assertEqual((call['label'], call['status'], call['result']['sensitivity_source']), ('QPSK', 'ok', 'modulation_table'))
        self.assert_rows([dict(call['result'], label='QPSK')], CASES['teacher_01']['expected']['results'])
        self.assertEqual(done['result']['outputs'][0]['value'], call['result']['link_margin_db'])
        self.assertNotIn('comparison', done['final_report'])
        tools = [e['details'] for e in self.service.activity.events(done['task_id']) if e['node'] == 'tool']
        self.assertEqual([t['tool_id'] for t in tools], ['fspl_mhz', 'received_power', 'link_margin', 'calc_link_margin'])
        self.assertEqual([s['card'] for s in tools[-1]['steps']], ['fspl_mhz', 'received_power', 'link_margin'])
        self.assertEqual((tools[-1]['label'], tools[-1]['arguments']['frequency_mhz']), ('QPSK', 5800))

    def test_case_three_compares_the_modulations_and_recommends_the_largest_margin(self):
        expected = CASES['teacher_03']['expected']
        draft, done = self.run_case('teacher_03', **manual(TEXT3))
        plan = draft['report']['calculation_plan_proposal']
        self.assertEqual([v['label'] for v in plan['variants']], ['16QAM'])
        self.assertEqual(done['status'], 'COMPLETED', done.get('failure'))
        comparison = done['final_report']['comparison']
        self.assert_rows(comparison['rows'], expected['results'])
        self.assertAlmostEqual(comparison['margin_diff_db'], expected['margin_diff_db'], delta=1e-9)
        self.assertEqual(comparison['recommend'], expected['recommend'])
        self.assertEqual([c['label'] for c in done['final_report']['tool_calls']], ['QPSK', '16QAM'])
        self.assertIn('QPSK 余量最大', done['final_report']['conclusion'])

    def test_an_unknown_modulation_is_a_choice_that_replaces_it_in_the_text(self):
        text = '计算链路余量：距离10公里，频率5.8GHz，发射功率20dBm，发射天线增益18dBi，接收天线增益18dBi，使用8PSK。'
        draft = self.service.apply(command(text=text))['state']
        self.assertEqual(draft['status'], 'AWAITING_INPUT')
        [issue] = draft['input_issues']
        self.assertEqual((issue['field'], issue['kind'], issue['excerpt']), ('modulation', 'choice', '8PSK'))
        answered = self.service.apply(command('answer', draft, answers={issue['id']: '16QAM'}))['state']
        self.assertEqual(answered['status'], 'AWAITING_CONFIRMATION', answered['report']['questions'])
        self.assertIn('使用16QAM', answered['request']['raw_text'])
        done = self.service.apply(command('confirm', answered))['state']
        self.assertAlmostEqual(done['result']['outputs'][0]['value'], 23.291440128741257, delta=1e-9)

    def test_stated_losses_and_named_radios_keep_the_general_budget(self):
        draft = self.service.apply(command(text=MARGIN))['state']
        plan = draft['report']['calculation_plan_proposal']
        self.assertEqual(plan['selected_model'], ['fspl_ghz', 'received_power', 'link_margin'])
        self.assertNotIn('tool', plan)
        radio = self.service.apply(command(text='按自由空间基准计算链路余量：A站到B站用 XX-100，频率2GHz，距离10km。'))['state']
        plan = radio['report']['calculation_plan_proposal']
        self.assertEqual(plan['selected_model'][0], 'fspl_ghz')
        self.assertNotIn('tool', plan)

    def test_a_changed_tool_result_fails_validation(self):
        _, done = self.run_case('teacher_03', **manual(TEXT3))
        snapshot = done['confirmed_snapshot']
        for path in (('tool_calls', 1, 'result', 'link_margin_db'), ('comparison', 'recommend')):
            result = copy.deepcopy(done['result'])
            target = result
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = 99 if path[-1] != 'recommend' else '16QAM'
            result['result_hash'] = digest({k: v for k, v in result.items() if k != 'result_hash'})
            failed = [v['validator_id'] for v in calculation.validate_result(result, snapshot) if not v['passed']]
            self.assertEqual(failed, ['link_tool'], path)


if __name__ == '__main__':
    unittest.main()
