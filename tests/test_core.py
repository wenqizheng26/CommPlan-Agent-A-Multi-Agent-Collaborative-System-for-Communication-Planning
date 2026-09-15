"""Independent arithmetic anchors and calculator trust-boundary checks."""
import copy
import importlib
import json
import math
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CoreTests(unittest.TestCase):
    def setUp(self):
        try:
            self.core = importlib.import_module("formula_rag.core")
            self.catalog = importlib.import_module("formula_rag.catalog")
        except ModuleNotFoundError:
            self.fail("The formula core and catalog have not been implemented")
        self.cards = {c["id"]: c for c in self.catalog.load_catalog(ROOT)}

    def calculate(self, identifier, parameters):
        return self.core.evaluate(self.cards[identifier], parameters)

    def test_workbook_fspl_200_metres(self):
        out = self.calculate("fspl_ghz", {"frequency_ghz": 4.5, "distance_km": 0.2})
        self.assertEqual(out["status"], "ok")
        self.assertAlmostEqual(out["value"], 91.48485018878651, places=11)
        self.assertEqual(out["unit"], "dB")
        self.assertEqual(out["inputs"], {"frequency_ghz": 4.5, "distance_km": 0.2})

    def test_workbook_fspl_400_metres(self):
        self.assertAlmostEqual(self.calculate("fspl_ghz", {"frequency_ghz": 4.5, "distance_km": 0.4})["value"], 97.50545010206613, places=11)

    def test_doubling_distance_adds_six_db(self):
        first = self.calculate("fspl_ghz", {"frequency_ghz": 2.4, "distance_km": 1})["value"]
        second = self.calculate("fspl_ghz", {"frequency_ghz": 2.4, "distance_km": 2})["value"]
        self.assertAlmostEqual(second-first, 6.020599913279624, places=11)

    def test_missing_parameters_are_explicit(self):
        out = self.calculate("fspl_ghz", {})
        self.assertEqual(out["status"], "missing_parameters")
        self.assertCountEqual(out["missing"], ["frequency_ghz", "distance_km"])
        self.assertNotIn("value", out)

    def test_zero_and_negative_distance_rejected(self):
        for distance in [0, -1]:
            with self.subTest(distance=distance):
                out = self.calculate("fspl_ghz", {"frequency_ghz": 4.5, "distance_km": distance})
                self.assertEqual(out["status"], "invalid_parameters")
                self.assertTrue(out["errors"])

    def test_nonfinite_text_bool_and_null_not_used_as_numbers(self):
        for frequency in [math.nan, math.inf, -math.inf, "4.5", True, None]:
            with self.subTest(frequency=frequency):
                out = self.calculate("fspl_ghz", {"frequency_ghz": frequency, "distance_km": 1})
                self.assertEqual(out["status"], "invalid_parameters")
                self.assertNotIn("value", out)

    def test_unused_query_parameters_do_not_enter_calculation_inputs(self):
        out = self.calculate("fspl_ghz", {"frequency_ghz": 4.5, "distance_km": 0.2, "speed_kmh": 50})
        self.assertEqual(out["status"], "ok")
        self.assertNotIn("speed_kmh", out["inputs"])

    def test_draft_cannot_calculate(self):
        card = copy.deepcopy(self.cards["fspl_ghz"])
        card["status"] = "draft"
        self.assertEqual(self.core.evaluate(card, {"frequency_ghz": 4.5, "distance_km": 1})["status"], "unverified_formula")

    def test_ast_blocks_code_execution_and_undeclared_names(self):
        for expression in ["__import__('os').system('echo bad')", "frequency_ghz.__class__", "[x for x in (1,2)]", "unknown_name + 1", "log10(x=1)", "True", "(lambda: 1)()"]:
            with self.subTest(expression=expression):
                card = copy.deepcopy(self.cards["fspl_ghz"])
                card["expression"] = expression
                self.assertEqual(self.core.evaluate(card, {"frequency_ghz": 4.5, "distance_km": 1})["status"], "invalid_parameters")

    def test_ast_limits_work_and_rejects_overflow(self):
        for expression in ["9**(9**9)", "1e308 * 1e308", "+".join(["1"]*200), "sqrt(-1)", "1/0"]:
            with self.subTest(expression=expression):
                card = copy.deepcopy(self.cards["fspl_ghz"])
                card["expression"] = expression
                self.assertEqual(self.core.evaluate(card, {"frequency_ghz": 4.5, "distance_km": 1})["status"], "invalid_parameters")

    def test_one_way_maximum_doppler_uses_exact_speed_of_light(self):
        out = self.calculate("doppler_max", {"frequency_ghz": 4.5, "speed_kmh": 108})
        self.assertEqual(out["unit"], "Hz")
        self.assertAlmostEqual(out["value"], 450.3115285175053, places=10)
        self.assertEqual(self.calculate("doppler_max", {"frequency_ghz": 4.5, "speed_kmh": 0})["value"], 0)

    def test_doppler_is_flagged_as_upper_bound(self):
        card = self.cards["doppler_max"]
        self.assertIn("maximum_doppler", card["applicability"]["requires"])
        self.assertIn("上界", card["description"])

    def test_thermal_noise_has_no_implicit_temperature(self):
        out = self.calculate("thermal_noise", {"bandwidth_hz": 1e6})
        self.assertEqual(out["status"], "missing_parameters")
        self.assertIn("temperature_k", out["missing"])

    def test_thermal_noise_290_kelvin_one_megahertz(self):
        out = self.calculate("thermal_noise", {"temperature_k": 290, "bandwidth_hz": 1e6})
        self.assertEqual(out["unit"], "dBm")
        self.assertAlmostEqual(out["value"], -113.97518719422808, places=10)

    def test_received_power_gain_and_loss_signs(self):
        out = self.calculate("received_power", {"tx_power_dbm": 40, "tx_gain_dbi": 2, "rx_gain_dbi": 2, "tx_loss_db": 2, "rx_loss_db": 2, "path_loss_db": 91.48485018878651, "extra_loss_db": 0})
        self.assertAlmostEqual(out["value"], -51.48485018878651, places=11)
        self.assertEqual(out["unit"], "dBm")

    def test_negative_power_gain_and_margin_are_valid(self):
        out = self.calculate("link_margin", {"rx_power_dbm": -90, "rx_threshold_dbm": -80, "reserve_db": 3})
        self.assertEqual(out["value"], -13)
        self.assertEqual(out["unit"], "dB")

    def test_loss_and_reserve_cannot_be_negative(self):
        out = self.calculate("link_margin", {"rx_power_dbm": -70, "rx_threshold_dbm": -80, "reserve_db": -3})
        self.assertEqual(out["status"], "invalid_parameters")

    def test_catalog_has_sourced_formulas_and_all_examples_reproduce(self):
        self.assertEqual(set(self.cards), {"fspl_ghz", "doppler_max", "thermal_noise", "received_power", "link_margin", "noise_density", "receiver_threshold"})
        for card in self.cards.values():
            self.assertTrue(card["sources"])
            self.assertTrue(card["examples"])
            self.assertEqual(self.catalog.validate_card(card), [])
            for example in card["examples"]:
                self.assertAlmostEqual(self.core.evaluate(card, example["inputs"])["value"], example["expected"], delta=example.get("tolerance", 1e-9))

    def test_catalog_rejects_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)/"knowledge"
            directory.mkdir()
            card = self.cards["fspl_ghz"]
            (directory/"formulas.json").write_text(json.dumps([card, card]), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "duplicate"):
                self.catalog.load_catalog(Path(tmp))

    def test_schema_rejects_invalid_domain_and_missing_sources(self):
        card = copy.deepcopy(self.cards["fspl_ghz"])
        card["parameters"]["distance_km"]["max"] = -1
        self.assertTrue(self.catalog.validate_card(card))
        card = copy.deepcopy(self.cards["fspl_ghz"])
        card["sources"] = []
        self.assertTrue(self.catalog.validate_card(card))


class WorkbookAuditTests(unittest.TestCase):
    def setUp(self):
        try:
            self.audit = importlib.import_module("scripts.inspect_workbook")
        except ModuleNotFoundError:
            self.fail("The independent workbook auditor has not been implemented")

    def test_excel_formula_references_are_recomputed_without_cached_outputs(self):
        formulas = {"C5": "20.0*LOG10(C3)", "C6": "20.0*LOG10(C4)", "C7": "92.4+C5+C6"}
        cells = {"C3": 4.5, "C4": 0.2, "C5": 999, "C6": 999, "C7": 999}
        self.assertAlmostEqual(self.audit.recompute_cell("C7", formulas, cells), 91.48485018878651, places=11)

    def test_excel_auditor_blocks_unsupported_calls_and_cycles(self):
        for formulas in [{"C1": "__import__('os')"}, {"C1": "C2+1", "C2": "C1+1"}, {"C1": "'Sheet2'!C3"}]:
            with self.subTest(formulas=formulas):
                with self.assertRaises(ValueError):
                    self.audit.recompute_cell("C1", formulas, {})


if __name__ == "__main__":
    unittest.main()
