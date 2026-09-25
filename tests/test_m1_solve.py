"""C11 inversion against the same registered multi-step calculation chain."""
import copy
import math
from pathlib import Path
import unittest

from formula_rag.catalog import load_catalog, validate_card
from planning.services.plans import chain, plan_for
from planning.services.solve import solve


ROOT = Path(__file__).resolve().parents[1]
DISTANCE = 34.06437891885911


def margin_plan():
    cards = load_catalog(ROOT)
    order, leaves = chain('link_margin', cards, set())
    records = [{'canonical_name': name, 'parameter_id': f'param:{name}'} for name in leaves]
    base = plan_for({'request_id': 'solve-test', 'task_id': 'solve-test', 'revision': 0}, order, cards, records, [])
    values = {'frequency_ghz': 2, 'distance_km': DISTANCE, 'tx_power_dbm': 37,
              'tx_gain_dbi': 5, 'rx_gain_dbi': 5, 'tx_loss_db': 2,
              'rx_loss_db': 2, 'extra_loss_db': 0, 'rx_threshold_dbm': -92, 'reserve_db': 0}
    return dict(base, cards=cards, parameters=values,
                parameter_names={r['parameter_id']: r['canonical_name'] for r in records},
                conditions=['free_space'])


class M1SolveTests(unittest.TestCase):
    def test_minimum_transmit_power_and_three_repeat_determinism(self):
        plan = margin_plan()
        condition = {'quantity': 'link_margin_db', 'op': '>=', 'value': 10}
        results = [solve(plan, 'tx_power_dbm', condition) for _ in range(3)]
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[1], results[2])
        result = results[0]
        current_margin = 37 + 5 + 5 - 2 - 2 - (92.4 + 20 * math.log10(2) + 20 * math.log10(DISTANCE)) + 92
        closed = 37 + 10 - current_margin
        self.assertLessEqual(abs(result['value'] - closed) / abs(closed), 1e-6)
        self.assertEqual(result['unit'], 'dBm')
        self.assertEqual(result['direction'], 'minimum')
        self.assertEqual(result['bracket'], [-30, 70])
        self.assertFalse(result['left']['satisfies'])
        self.assertTrue(result['right']['satisfies'])
        self.assertLess(abs(result['residual']), 1e-7)
        self.assertEqual([s['tool_id'] for s in result['steps']], ['fspl_ghz', 'received_power', 'link_margin'])

    def test_farthest_distance_matches_closed_form(self):
        plan = margin_plan()
        result = solve(plan, 'distance_km', {'quantity': 'link_margin_db', 'op': '>=', 'value': 10})
        current_margin = 37 + 5 + 5 - 2 - 2 - (92.4 + 20 * math.log10(2) + 20 * math.log10(DISTANCE)) + 92
        closed = DISTANCE * 10 ** ((current_margin - 10) / 20)
        self.assertLessEqual(abs(result['value'] - closed) / closed, 1e-6)
        self.assertEqual(result['direction'], 'maximum')
        self.assertTrue(result['left']['satisfies'])
        self.assertFalse(result['right']['satisfies'])

    def test_no_root_non_monotonic_and_missing_bracket(self):
        plan = margin_plan()
        with self.assertRaisesRegex(ValueError, '^SOLVE_NO_ROOT$'):
            solve(plan, 'tx_power_dbm', {'quantity': 'link_margin_db', 'op': '>=', 'value': 1000})
        missing = copy.deepcopy(plan)
        next(c for c in missing['cards'] if c['id'] == 'received_power')['parameters']['tx_power_dbm'].pop('search_range')
        with self.assertRaisesRegex(ValueError, '^SOLVE_BRACKET$'):
            solve(missing, 'tx_power_dbm', {'quantity': 'link_margin_db', 'op': '>=', 'value': 10})
        curved_card = {'id': 'curved', 'title': 'test', 'description': 'test', 'version': '1',
                       'status': 'verified', 'expression': '(x-5)**2',
                       'output': {'name': 'y', 'unit': 'dB'},
                       'parameters': {'x': {'unit': 'dB', 'description': 'test', 'search_range': [0, 10]}},
                       'applicability': {'requires': []}, 'sources': [{'title': 'test', 'path': 'test'}],
                       'examples': [{'inputs': {'x': 1}, 'expected': 16}]}
        self.assertEqual(validate_card(curved_card), [])
        curved = {'cards': [curved_card], 'steps': [{'step_id': 's1', 'tool_id': 'curved',
                   'inputs': {'x': {'kind': 'parameter', 'ref': 'x-id', 'unit': 'dB'}},
                   'expected_unit': 'dB', 'required_conditions': []}],
                  'parameters': {}, 'parameter_names': {'x-id': 'x'}, 'conditions': []}
        with self.assertRaisesRegex(ValueError, '^SOLVE_NOT_MONOTONIC$'):
            solve(curved, 'x', {'quantity': 'y', 'op': '>=', 'value': 10})

    def test_search_range_validation(self):
        card = next(c for c in load_catalog(ROOT) if c['id'] == 'fspl_ghz')
        for interval in ([0, 1], [1, 1], [1, float('inf')], [1], [-1, 1]):
            bad = copy.deepcopy(card)
            bad['parameters']['distance_km']['search_range'] = interval
            self.assertTrue(validate_card(bad), interval)


if __name__ == '__main__':
    unittest.main()
