"""Named sites and the radio supply inputs from the fact store; unstated inputs take card assumptions (A3, H3)."""
import copy
import unittest
from pathlib import Path

from formula_rag.catalog import load_catalog
from planning.agents.requirements import RequirementsAgent
from planning.services.plans import LINE_OF_SIGHT
from planning.services.requirement_validation import check_report
from test_requirement_labels import ids, model
from test_requirements_contract import request

ROOT = Path(__file__).resolve().parents[1]
FREE = '按自由空间基准，'


def ask(end='B', extra=''):
    return FREE + f'A 站到 {end} 站用 XX-100 电台、2 GHz{extra}，要留 10 dB 余量，能通吗？不能的话发射功率至少要多大？'


def labeller(text, end='B', device='XX-100'):
    """What the model says about the demo question: the numbers, the goal, the two sites and the radio."""
    q = ids(text)
    clause = text[text.index('A 站'):text.index('，要留')]
    quantities = [dict(id=q['2 GHz'], field='frequency_ghz'), dict(id=q['10 dB'], field='required_margin_db')]
    if '40 dBm' in q:
        quantities.append(dict(id=q['40 dBm'], field='tx_power_dbm'))
    return model(targets=[dict(id='link_margin', evidence='能通吗')], quantities=quantities,
                 solve=[dict(unknown='tx_power_dbm', evidence='不能的话发射功率至少要多大')],
                 sites=[dict(mention='A站', evidence=clause), dict(mention=f'{end}站', evidence=clause)],
                 devices=[dict(mention=device, evidence=clause)])


def param(report, name):
    return next(p for p in report['parameters_proposal'] if p['canonical_name'] == name)


class FactSourceTests(unittest.TestCase):
    cards = load_catalog(ROOT)

    def run_agent(self, text, end='B', manual=None, device='XX-100'):
        q = request(text)
        q['manual_parameters'] = manual or {}
        r = RequirementsAgent(ROOT, selector=labeller(text, end, device)).run(q)
        self.assertEqual(check_report(r, q, self.cards, ROOT), r)
        return q, r

    def test_the_demo_question_takes_sites_radio_and_assumptions_into_one_plan(self):
        _, r = self.run_agent(ask())
        self.assertEqual(r['execution_status'], 'AWAITING_CONFIRMATION', r['questions'])
        plan = r['calculation_plan_proposal']
        self.assertEqual(plan['selected_model'], ['slant_range_wgs84', 'radio_horizon', 'fspl_ghz', 'received_power', 'link_margin'])
        self.assertEqual(plan['checks'], [LINE_OF_SIGHT])
        self.assertEqual(plan['requirement'], dict(quantity='link_margin_db', op='>=', value=10.0, unit='dB'))
        self.assertEqual(plan['solve_if_unmet'], 'tx_power_dbm')
        self.assertEqual(plan['steps'][2]['inputs']['distance_km'], dict(kind='step', ref='slant_range_wgs84-step', unit='km'))
        for name, value, kind, ref in [('lat1_deg', 30.05, 'site', 'site:sim-a#position.lat'),
                                       ('antenna2_m', 25, 'site', 'site:sim-b#position.antenna_m'),
                                       ('tx_power_dbm', 37, 'device', 'device:sim-xx100#tx_power_dbm'),
                                       ('rx_gain_dbi', 5, 'device', 'device:sim-xx100#antenna_gain_dbi'),
                                       ('rx_threshold_dbm', -92, 'device', 'device:sim-xx100#rx_sensitivity_dbm'),
                                       ('tx_loss_db', 2, 'default', 'card:received_power#tx_loss_db'),
                                       ('reserve_db', 0, 'default', 'card:link_margin#reserve_db')]:
            with self.subTest(name=name):
                p = param(r, name)
                self.assertEqual((p['value'], [(o['kind'], o['source_ref']) for o in p['origins']]), (value, [(kind, ref)]))
        self.assertEqual(r['assumptions'][:2], ['两端站点 A站、B站 的坐标与天线高度取自站址表（模拟）。',
                                                '两端电台均按 XX-100，参数取自XX-100 手册（模拟）。'])
        self.assertIn('预留余量按假设取 0 dB：要求余量单独比较，不预先扣除。', r['assumptions'])

    def test_a_site_without_antenna_height_is_asked_and_a_typed_value_is_used(self):
        _, r = self.run_agent(ask('D'), 'D')
        self.assertEqual(r['execution_status'], 'AWAITING_INPUT')
        self.assertEqual(r['missing_parameters'], ['antenna2_m'])
        self.assertEqual(param(r, 'lat2_deg')['value'], 29.881)
        _, r = self.run_agent(ask('D'), 'D', manual={'antenna2_m': {'value': 20, 'unit': 'm'}})
        self.assertEqual(r['execution_status'], 'AWAITING_CONFIRMATION', r['questions'])
        self.assertEqual([o['kind'] for o in param(r, 'antenna2_m')['origins']], ['manual_form'])

    def test_a_shared_name_is_a_choice_not_a_guess(self):
        text = ask('港口')
        _, r = self.run_agent(text, '港口')
        self.assertEqual(r['execution_status'], 'AWAITING_INPUT')
        [issue] = [d for d in r['diagnostics'] if d['code'] == 'ENTITY_AMBIGUOUS']
        self.assertEqual(issue['details']['choices'], ['东港站', '西港站'])
        self.assertIn('“港口 站”对应2个站点，请选定一个。可选：东港站、西港站。', r['questions'])
        self.assertNotIn('slant_range_wgs84', r['calculation_plan_proposal']['selected_model'])

    def test_a_text_value_that_differs_from_the_record_is_a_conflict(self):
        _, r = self.run_agent(ask(extra='、发射功率 40 dBm'))
        power = param(r, 'tx_power_dbm')
        self.assertEqual(power['status'], 'conflicting')
        self.assertEqual(sorted(o['kind'] for o in power['origins']), ['device', 'user_text'])
        self.assertEqual(r['execution_status'], 'AWAITING_INPUT')

    def test_unknown_names_and_an_out_of_band_radio_are_asked(self):
        _, r = self.run_agent(ask('Z'), 'Z')
        self.assertIn('ENTITY_UNKNOWN', [d['code'] for d in r['diagnostics']])
        self.assertEqual(r['execution_status'], 'AWAITING_INPUT')
        text = ask().replace('2 GHz', '5 GHz')
        q = request(text)
        fake = labeller(text.replace('5 GHz', '2 GHz'))  # same labels; the ids stay in place
        r = RequirementsAgent(ROOT, selector=fake).run(q)
        self.assertIn('频率 5 GHz 不在 XX-100 的工作频段 1.4–2.7 GHz 内。请核对频率或设备。', r['questions'])
        self.assertEqual(r['execution_status'], 'AWAITING_INPUT')

    def test_a_distance_in_the_text_needs_no_coordinates(self):
        text = '按自由空间基准计算链路余量：XX-100 电台，频率2GHz，距离10km。'
        q = request(text)
        clause = 'XX-100 电台'
        r = RequirementsAgent(ROOT, selector=model(devices=[dict(mention='XX-100', evidence=clause)])).run(q)
        self.assertEqual(r['execution_status'], 'AWAITING_CONFIRMATION', r['questions'])
        self.assertEqual(r['calculation_plan_proposal']['selected_model'], ['fspl_ghz', 'received_power', 'link_margin'])
        self.assertNotIn('checks', r['calculation_plan_proposal'])
        self.assertEqual(check_report(r, q, self.cards, ROOT), r)

    def test_a_changed_record_value_fails_the_replay(self):
        q, r = self.run_agent(ask())
        bad = copy.deepcopy(r)
        param(bad, 'lat1_deg')['origins'][0]['value'] = 31.0
        param(bad, 'lat1_deg')['value'] = 31.0
        with self.assertRaisesRegex(ValueError, 'PARAMETER_SOURCE_MISMATCH'):
            check_report(bad, q, self.cards, ROOT)


if __name__ == '__main__':
    unittest.main()
