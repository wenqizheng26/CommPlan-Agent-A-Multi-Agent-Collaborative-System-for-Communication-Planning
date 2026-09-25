"""Confirmed plans with sites: the line-of-sight stop, the margin requirement and the solved power (A2, AGENT_LED Appendix A)."""
import copy
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from planning.agents.review import ReviewAgent
from planning.requirements_contract import digest
from planning.services.calculation import validate_result
from planning.workflow.task_service import TaskService
from test_requirement_facts import ask, labeller

ROOT = Path(__file__).resolve().parents[1]


def command(action='create', state=None, text=None):
    c = dict(action=action, task_id=state['task_id'] if state else str(uuid.uuid4()), event_id=str(uuid.uuid4()),
             expected_revision=state['revision'] if state else 0, expected_state_version=state['state_version'] if state else 0)
    if action == 'create':
        c.update(input=dict(raw_text=text, manual_parameters={}, condition=None, target=None), mode='llm')
    if action == 'confirm':
        c['review_hash'] = state['review']['review_hash']
    return c


class PlanGoalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.service = TaskService(ROOT, Path(self.tmp.name) / 'goal.sqlite')

    def run_link(self, end, reviewer=None):
        text = ask(end)
        with patch('planning.workflow.task_service.LocalSelector', return_value=labeller(text, end)):
            draft = self.service.apply(command(text=text))['state']
        self.assertEqual(draft['status'], 'AWAITING_CONFIRMATION', draft['report']['questions'])
        # The roles after confirmation never reach a real model here.
        with patch('planning.workflow.planning_graph.role_selector', return_value=False), \
             patch('planning.workflow.planning_graph.ReviewAgent', return_value=reviewer or ReviewAgent(False)):
            return self.service.apply(command('confirm', draft))['state']

    def test_an_unmet_requirement_is_solved_and_checked_against_the_rating(self):
        done = self.run_link('B')
        self.assertEqual(done['status'], 'COMPLETED')
        report = done['final_report']
        margin = report['outputs'][0]['value']
        self.assertAlmostEqual(margin, 5.933391, places=5)
        self.assertEqual({k: report['requirement'][k] for k in ('value', 'met')}, dict(value=10.0, met=False))
        solved = report['solve']
        # Margin grows dB for dB with transmit power, so the closed form is 37 + (10 - margin).
        self.assertLessEqual(abs(solved['value'] - (37 + 10 - margin)) / solved['value'], 1e-6)
        self.assertEqual((solved['direction'], solved['rated']['value'], solved['rated']['exceeded']), ('minimum', 37, True))
        self.assertEqual(report['conclusion'], '按已确认自由空间条件，链路余量 5.93 dB（扣除预留余量后高于门限），低于要求的 10 dB；'
                                               '发射功率至少需 41.07 dBm 才能满足，超过所选电台的额定发射功率 37 dBm。')
        self.assertTrue(all(v['passed'] for v in done['validations']))
        self.assertEqual([s['tool_id'] for s in report['steps']],
                         ['slant_range_wgs84', 'radio_horizon', 'fspl_ghz', 'received_power', 'link_margin'])

    def test_a_link_beyond_the_radio_horizon_stops_before_the_path_loss(self):
        done = self.run_link('C')
        self.assertEqual(done['status'], 'NEEDS_MODEL')
        self.assertIsNone(done['result'])
        failure = done['failure']
        self.assertEqual(failure['code'], 'BEYOND_LINE_OF_SIGHT')
        self.assertAlmostEqual(failure['details']['distance_km'], 85.065609, places=5)
        self.assertAlmostEqual(failure['details']['radio_horizon_km'], 40.991370, places=5)
        self.assertEqual([s['tool_id'] for s in failure['details']['steps']], ['slant_range_wgs84', 'radio_horizon'])
        self.assertIn('85.07 km', failure['message'])

    def test_a_met_requirement_is_not_solved(self):
        done = self.run_link('F')
        report = done['final_report']
        self.assertAlmostEqual(report['outputs'][0]['value'], 15.009069, places=5)
        self.assertTrue(report['requirement']['met'])
        self.assertNotIn('solve', report)
        self.assertTrue(report['conclusion'].endswith('满足不低于 10 dB 的要求。'))

    def test_a_changed_solution_fails_validation(self):
        done = self.run_link('B')
        result = copy.deepcopy(done['result'])
        result['solve']['value'] += 1
        result['result_hash'] = digest({k: v for k, v in result.items() if k != 'result_hash'})
        failed = [v['validator_id'] for v in validate_result(result, done['confirmed_snapshot']) if not v['passed']]
        self.assertEqual(failed, ['requirement_and_solve'])

    def test_the_reviewer_may_quote_the_worked_out_differences(self):
        seen = []
        def reviewer(role, prompt, view, schema):
            seen.append(view['facts'])
            return dict(output=dict(decision='caution', answer='不能满足：余量 5.93 dB，比要求低 4.07 dB；'
                                    '发射功率至少需 41.07 dBm，比 XX-100 额定的 37 dBm 高 4.07 dB。',
                                    opinions=[dict(kind='suggestion', text='可换用发射功率更高的电台，或提高天线增益。',
                                                   refs=['solve', 'goal'])], steps=[]))
        done = self.run_link('B', ReviewAgent(reviewer))
        self.assertEqual(done['final_report']['answer']['withheld'], False)
        facts = seen[0]
        self.assertEqual(facts['goal']['difference'], dict(value=4.06661, unit='dB', meaning='余量比要求低'))
        self.assertEqual(facts['solve']['rated']['difference']['value'], 4.06661)
        self.assertIn('两端电台均按 XX-100，参数取自XX-100 手册（模拟）。', [a['text'] for a in facts['assumptions']])


if __name__ == '__main__':
    unittest.main()
