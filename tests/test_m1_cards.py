"""C9 formula tools, source linkage, and assumption metadata."""
import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from formula_rag import catalog, core
from formula_rag.presentation import formula_view
from formula_rag.tools import geodetic_to_ecef
from planning.requirements_contract import digest
from planning.services.reference_models import agrees


ROOT = Path(__file__).resolve().parents[1]


class M1CardTests(unittest.TestCase):
    def setUp(self):
        self.cards = {c['id']: c for c in catalog.load_catalog(ROOT)}

    def test_public_wgs84_to_ecef_example(self):
        # EPSG Guidance Note 7 example, mirrored by GDAL, sections 2.2.1/2.3.2.
        lat = 53 + 48 / 60 + 33.82 / 3600
        lon = 2 + 7 / 60 + 46.38 / 3600
        actual = geodetic_to_ecef(lat, lon, 73)
        for got, published in zip(actual, (3771793.97, 140253.34, 5124304.35)):
            self.assertLessEqual(abs(got - published), 0.01)

    def test_examples_and_independent_recalculation(self):
        for name in ('slant_range_wgs84', 'radio_horizon'):
            card = self.cards[name]
            for example in card['examples']:
                with self.subTest(card=name, inputs=example['inputs']):
                    out = core.evaluate(card, example['inputs'])
                    self.assertEqual(out['status'], 'ok')
                    self.assertLessEqual(abs(out['value'] - example['expected']), example['tolerance'])
                    self.assertTrue(agrees(name, example['inputs'], out['value']))
        self.assertEqual(core.evaluate(self.cards['slant_range_wgs84'], {})['status'], 'missing_parameters')
        bad = dict(self.cards['slant_range_wgs84']['examples'][0]['inputs'], lat1_deg=91)
        self.assertEqual(core.evaluate(self.cards['slant_range_wgs84'], bad)['status'], 'invalid_parameters')

    def test_program_tool_is_whitelisted_and_has_no_expression_display(self):
        card = self.cards['slant_range_wgs84']
        view = formula_view(card)
        self.assertEqual(view['kind'], 'python_tool')
        self.assertIn('ECEF', view['algorithm'])
        self.assertTrue(view['sources'])
        self.assertNotIn('latex', view)
        self.assertNotIn('expression', card)
        forged = copy.deepcopy(card)
        forged['id'] = 'run_arbitrary_code'
        self.assertTrue(catalog.validate_card(forged))
        self.assertEqual(core.evaluate(forged, card['examples'][0]['inputs'])['status'], 'invalid_parameters')

    def test_defaults_validate_unit_and_domain_but_are_not_applied_implicitly(self):
        card = self.cards['received_power']
        self.assertEqual(card['parameters']['tx_loss_db']['default']['value'], 2)
        self.assertEqual(card['parameters']['rx_loss_db']['default']['value'], 2)
        self.assertEqual(card['parameters']['extra_loss_db']['default']['value'], 0)
        self.assertEqual(self.cards['link_margin']['parameters']['reserve_db']['default']['value'], 0)
        inputs = dict(card['examples'][0]['inputs'])
        inputs.pop('tx_loss_db')
        self.assertEqual(core.evaluate(card, inputs)['status'], 'missing_parameters')
        for mutation in (dict(value=-1, unit='dB', note='bad'),
                         dict(value=2, unit='dBm', note='bad'),
                         dict(value=2, unit='dB', note=''), None):
            bad = copy.deepcopy(card)
            bad['parameters']['tx_loss_db']['default'] = mutation
            self.assertTrue(catalog.validate_card(bad))

    def test_implementation_source_changes_card_and_snapshot_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'tools.py'
            source.write_bytes((ROOT / 'formula_rag/tools.py').read_bytes())
            with patch.object(catalog, '__file__', str(Path(tmp) / 'catalog.py')):
                before = catalog.load_catalog(ROOT)
                source.write_bytes(source.read_bytes() + b'\n# changed implementation source\n')
                after = catalog.load_catalog(ROOT)
        old = next(c for c in before if c['id'] == 'slant_range_wgs84')
        new = next(c for c in after if c['id'] == 'slant_range_wgs84')
        self.assertNotEqual(old['implementation_sha256'], new['implementation_sha256'])
        self.assertNotEqual(digest(old), digest(new))
        self.assertNotEqual(digest(before), digest(after))

    def test_existing_fspl_scalar_is_bit_identical(self):
        out = core.evaluate(self.cards['fspl_ghz'], {'frequency_ghz': 2, 'distance_km': 1})
        self.assertEqual(out['value'], 98.42059991327963)


if __name__ == '__main__':
    unittest.main()
