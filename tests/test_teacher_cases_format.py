"""Frozen teacher acceptance fixtures; all numerical checks use only stdlib math."""

from collections import Counter
import json
import math
from pathlib import Path
import unittest


TEACHER_TEXTS = {
    "teacher_01": "算一下 A 楼顶到 B 楼顶的无线链路余量。距离 10 公里，频率 5.8GHz，发射功率 20dBm，发射天线增益 18dBi，接收天线增益 18dBi，调制方式 QPSK。",
    "teacher_02": "从石家庄山顶基站连到乡镇，想用 5.8G，传视频，要稳定，功率和天线还没定。",
    "teacher_03": "A 到 B 距离 8 公里，频率 2.4GHz，发射功率 17dBm，发射天线 12dBi，接收天线 12dBi，分别用 QPSK 和 16QAM 算余量，哪个更稳？",
}
PARSED_FIELDS = {
    "distance_km", "frequency_mhz", "tx_power_dbm", "tx_gain_dbi",
    "rx_gain_dbi", "modulations",
}
MISSING_ORDER = (
    "distance_km", "frequency_mhz", "tx_power_dbm", "tx_gain_dbi",
    "rx_gain_dbi", "modulation",
)
DEFAULTS = {
    "distance_km": 10, "tx_power_dbm": 20, "tx_gain_dbi": 18,
    "rx_gain_dbi": 18, "modulations": ["QPSK"],
}
SENSITIVITIES = {"QPSK": -100, "16QAM": -95, "64QAM": -90}
CASE_ONE_INPUT = {**DEFAULTS, "frequency_mhz": 5800}
CASE_THREE_INPUT = {
    "distance_km": 8, "frequency_mhz": 2400, "tx_power_dbm": 17,
    "tx_gain_dbi": 12, "rx_gain_dbi": 12, "modulations": ["QPSK", "16QAM"],
}


def read_cases():
    path = Path(__file__).parent / "eval" / "teacher_cases.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


class TeacherCasesFormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = read_cases()
        cls.by_id = {row["id"]: row for row in cls.rows}

    def assert_finite_number(self, value):
        self.assertIsInstance(value, (int, float))
        self.assertNotIsInstance(value, bool)
        self.assertTrue(math.isfinite(value))

    def assert_input_fields(self, values):
        self.assertIsInstance(values, dict)
        self.assertLessEqual(set(values), PARSED_FIELDS)
        for field, value in values.items():
            if field == "modulations":
                self.assertIsInstance(value, list)
                self.assertGreater(len(value), 0)
                self.assertEqual(len(value), len(set(value)))
                for modulation in value:
                    self.assertIsInstance(modulation, str)
                    self.assertTrue(modulation)
            else:
                self.assert_finite_number(value)
                if field in {"distance_km", "frequency_mhz"}:
                    self.assertGreater(value, 0)

    def test_inventory_has_unique_ids_and_exact_category_counts(self):
        self.assertEqual(len(self.rows), 20)
        self.assertEqual(len(self.by_id), len(self.rows))
        self.assertEqual(
            Counter(row["category"] for row in self.rows),
            {"teacher": 3, "variant": 8, "missing": 5, "clarify": 2, "english": 2},
        )
        for row in self.rows:
            self.assertEqual(set(row), {"id", "category", "text", "expected"})
            self.assertTrue(row["text"])
            self.assertRegex(row["id"], rf"^{row['category']}_\d{{2}}$")

    def test_teacher_texts_are_verbatim(self):
        self.assertEqual(
            {row["id"]: row["text"] for row in self.rows if row["category"] == "teacher"},
            TEACHER_TEXTS,
        )

    def test_field_names_and_category_contracts(self):
        allowed_expected = {
            "first_stop", "parsed", "nodes", "service", "missing", "ask",
            "after_defaults", "results", "margin_diff_db", "recommend", "tolerance",
        }
        for row in self.rows:
            with self.subTest(case=row["id"]):
                expected = row["expected"]
                self.assertIsInstance(expected, dict)
                self.assertLessEqual(set(expected), allowed_expected)
                self.assert_input_fields(expected["parsed"])
                self.assertEqual(expected["tolerance"], 1e-6)
                if "nodes" in expected:
                    self.assertEqual(len(expected["nodes"]), 2)
                    self.assertTrue(all(isinstance(node, str) and node for node in expected["nodes"]))
                if "service" in expected:
                    self.assertIsInstance(expected["service"], str)
                    self.assertTrue(expected["service"])
                if row["category"] == "missing":
                    self.assertIn("missing", expected)
                    self.assertIn("after_defaults", expected)
                    self.assert_input_fields(expected["after_defaults"])
                else:
                    self.assertNotIn("missing", expected)
                    self.assertNotIn("after_defaults", expected)
                if row["category"] == "clarify":
                    self.assertIn("ask", expected)
                    self.assertNotIn("results", expected)
                    self.assertNotIn("margin_diff_db", expected)
                    self.assertNotIn("recommend", expected)
                else:
                    self.assertNotIn("ask", expected)
                    self.assertGreater(len(expected["results"]), 0)

    def test_first_stops_and_teacher_two_explicit_fields(self):
        for row in self.rows:
            needs_input = row["category"] in {"missing", "clarify"} or row["id"] == "teacher_02"
            self.assertEqual(
                row["expected"]["first_stop"],
                "AWAITING_INPUT" if needs_input else "AWAITING_CONFIRMATION",
                row["id"],
            )
        expected = self.by_id["teacher_02"]["expected"]
        self.assertEqual(expected["parsed"], {"frequency_mhz": 5800})
        self.assertEqual(expected["nodes"], ["石家庄山顶基站", "乡镇"])
        self.assertEqual(expected["service"], "视频")
        self.assertEqual(self.by_id["clarify_01"]["expected"]["ask"], ["modulation"])
        self.assertEqual(self.by_id["clarify_02"]["expected"]["ask"], ["frequency_mhz"])
        self.assertNotIn("frequency_mhz", self.by_id["clarify_02"]["expected"]["parsed"])

    def test_missing_fields_are_ordered_and_defaults_preserve_explicit_input(self):
        for row in self.rows:
            if row["category"] != "missing":
                continue
            with self.subTest(case=row["id"]):
                expected = row["expected"]
                parsed = expected["parsed"]
                absent = [
                    field for field in MISSING_ORDER
                    if ("modulations" if field == "modulation" else field) not in parsed
                ]
                self.assertEqual(expected["missing"], absent)
                self.assertTrue(absent)
                self.assertEqual(set(expected["after_defaults"]), PARSED_FIELDS)
                self.assertEqual(expected["after_defaults"], {**DEFAULTS, **parsed})

    def test_all_results_match_independent_teacher_formula(self):
        result_fields = {
            "modulation", "rx_sensitivity_dbm", "path_loss_db", "rx_power_dbm",
            "link_margin_db", "meets",
        }
        for row in self.rows:
            if row["category"] == "clarify":
                continue
            with self.subTest(case=row["id"]):
                expected = row["expected"]
                if row["category"] == "missing":
                    inputs = expected["after_defaults"]
                elif row["id"] == "teacher_02":
                    # The teacher original is a teacher-category case with missing input.
                    # Restricted missing/after_defaults fields belong only to missing-category
                    # variants. Its results describe adoption of the teacher's stated defaults.
                    inputs = {**DEFAULTS, **expected["parsed"]}
                else:
                    inputs = expected["parsed"]
                self.assertEqual(set(inputs), PARSED_FIELDS)
                self.assertEqual(
                    [result["modulation"] for result in expected["results"]], inputs["modulations"],
                )
                path_loss = (
                    32.44 + 20 * math.log10(inputs["distance_km"])
                    + 20 * math.log10(inputs["frequency_mhz"])
                )
                rx_power = inputs["tx_power_dbm"] + inputs["tx_gain_dbi"] + inputs["rx_gain_dbi"] - path_loss
                margins = []
                for result in expected["results"]:
                    self.assertEqual(set(result), result_fields)
                    sensitivity = SENSITIVITIES[result["modulation"]]
                    margin = rx_power - sensitivity
                    margins.append(margin)
                    for field, value in {
                        "rx_sensitivity_dbm": sensitivity, "path_loss_db": path_loss,
                        "rx_power_dbm": rx_power, "link_margin_db": margin,
                    }.items():
                        self.assert_finite_number(result[field])
                        self.assertLessEqual(abs(result[field] - value), 1e-9, field)
                    self.assertIsInstance(result["meets"], bool)
                    self.assertEqual(result["meets"], margin >= 0)
                if len(margins) >= 2:
                    self.assert_finite_number(expected["margin_diff_db"])
                    self.assertLessEqual(abs(expected["margin_diff_db"] - (max(margins) - min(margins))), 1e-9)
                    self.assertEqual(expected["recommend"], inputs["modulations"][margins.index(max(margins))])
                else:
                    self.assertNotIn("margin_diff_db", expected)
                    self.assertNotIn("recommend", expected)

    def test_teacher_rounded_results_equal_supplied_values(self):
        for case_id in ("teacher_01", "teacher_02"):
            result = self.by_id[case_id]["expected"]["results"][0]
            self.assertEqual(
                [round(result[field], 2) for field in ("path_loss_db", "rx_power_dbm", "link_margin_db")],
                [127.71, -71.71, 28.29],
            )
        qpsk, qam16 = self.by_id["teacher_03"]["expected"]["results"]
        self.assertEqual(
            [round(qpsk["path_loss_db"], 2), round(qpsk["rx_power_dbm"], 2),
             round(qpsk["link_margin_db"], 2), round(qam16["link_margin_db"], 2)],
            [118.11, -77.11, 22.89, 17.89],
        )

    def test_variants_and_english_preserve_units_and_modulation_order(self):
        for case_id in ("teacher_01", "variant_01", "variant_02", "variant_03", "variant_04", "variant_08", "english_01"):
            self.assertEqual(self.by_id[case_id]["expected"]["parsed"], CASE_ONE_INPUT, case_id)
        for case_id in ("teacher_03", "variant_07", "english_02"):
            self.assertEqual(self.by_id[case_id]["expected"]["parsed"], CASE_THREE_INPUT, case_id)
        self.assertEqual(
            self.by_id["variant_05"]["expected"]["parsed"],
            {**CASE_THREE_INPUT, "modulations": ["16QAM", "QPSK"]},
        )
        self.assertEqual(
            self.by_id["variant_06"]["expected"]["parsed"],
            {**CASE_THREE_INPUT, "modulations": ["QPSK", "16QAM", "64QAM"]},
        )
        self.assertIn("10000米", self.by_id["variant_02"]["text"])
        self.assertIn("5800 MHz", self.by_id["variant_02"]["text"])
        self.assertIn("5.8G", self.by_id["variant_03"]["text"])
        self.assertIn("两端天线都是18dBi", self.by_id["variant_04"]["text"])
        self.assertIn("信道带宽20MHz", self.by_id["variant_08"]["text"])


if __name__ == "__main__":
    unittest.main()
