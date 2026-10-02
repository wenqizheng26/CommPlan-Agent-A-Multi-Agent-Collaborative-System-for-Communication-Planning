"""T2 catalog, schema, deterministic tools, API, and unchanged M1 planning checks."""
import copy
import json
import math
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.request import urlopen

from formula_rag.catalog import load_catalog
from formula_rag.core import evaluate
from formula_rag import registry
from formula_rag.schema import (
    card_input_schema, card_output_schema, check_schema, validate,
)
from planning.agents.requirements import RequirementsAgent
from planning.knowledge.facts import FactService
from planning.requirements_contract import digest
from planning.services import reference_models


ROOT = Path(__file__).resolve().parents[1]
SENSITIVITIES = {"QPSK": -100, "16QAM": -95, "64QAM": -90}
TEACHER_INPUTS = (
    dict(distance_km=10, frequency_mhz=5800, tx_power_dbm=20, tx_gain_dbi=18, rx_gain_dbi=18),
    dict(distance_km=8, frequency_mhz=2400, tx_power_dbm=17, tx_gain_dbi=12, rx_gain_dbi=12),
)


def copy_knowledge(root):
    """Copy all local source data, including the new modulation source document."""
    root = Path(root)
    shutil.copytree(ROOT / "knowledge", root / "knowledge")
    source = ROOT / "docs/design/TEACHER_CASES.md"
    destination = root / "docs/design/TEACHER_CASES.md"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return root


def teacher_regression_rows():
    """Evidence helper: remove only fspl_mhz, keeping all other inputs identical."""
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        raw = json.loads((ROOT / "knowledge/formulas.json").read_text(encoding="utf-8"))
        if sum(card["id"] == "fspl_mhz" for card in raw) != 1:
            raise AssertionError("the regression requires exactly one appended fspl_mhz card")
        folders = [copy_knowledge(Path(tmp) / name) for name in ("before", "after")]
        (folders[0] / "knowledge/formulas.json").write_text(
            json.dumps([card for card in raw if card["id"] != "fspl_mhz"], ensure_ascii=False),
            encoding="utf-8",
        )
        agents = [RequirementsAgent(folder, selector=False) for folder in folders]
        for line in (ROOT / "tests/eval/m1_cases.jsonl").read_text(encoding="utf-8").splitlines():
            case = json.loads(line)
            if "text" not in case:
                continue
            request = dict(
                schema_version="1.0.0", task_id="teacher-regression", revision=0,
                request_id="teacher-request", raw_text=case["text"],
                manual_parameters={}, condition=None, target=None,
            )
            reports = [agent.run(request) for agent in agents]

            def signature(report):
                plan = report["calculation_plan_proposal"]
                chain = [step["tool_id"] for step in plan["steps"]] if plan else []
                return dict(targets=report["targets"], final_target=chain[-1] if chain else None,
                            chain=chain, status=report["execution_status"])

            def candidates(agent):
                retrieved = agent.last_retrieval
                return [hit["id"] for hit in retrieved["hits"] if hit["id"] in retrieved["used"]]

            rows.append(dict(
                id=case["id"], before=signature(reports[0]), after=signature(reports[1]),
                candidates_before=candidates(agents[0]), candidates_after=candidates(agents[1]),
                models_before=[model["model_id"] for model in reports[0]["candidate_models"]],
                models_after=[model["model_id"] for model in reports[1]["candidate_models"]],
                eligible_before=agents[0].last_retrieval["candidate_used"],
                eligible_after=agents[1].last_retrieval["candidate_used"],
            ))
    return rows


class TeacherFactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = copy_knowledge(Path(self.temp.name) / "app")

    def assert_rejected_mutations(self, relative, mutations):
        path = self.root / relative
        original = path.read_bytes()
        records = json.loads(original)
        for name, mutate in mutations:
            with self.subTest(mutation=name):
                bad = copy.deepcopy(records)
                mutate(bad)
                path.write_text(json.dumps(bad, ensure_ascii=False), encoding="utf-8")
                try:
                    with self.assertRaises(ValueError):
                        FactService(self.root)
                finally:
                    path.write_bytes(original)

    def test_modulations_lookup_normalization_and_public_visibility(self):
        service = FactService(self.root)
        for name, sensitivity in {**SENSITIVITIES, "16 qam": -95, "16-QAM": -95,
                                  "16_qam": -95, "qpsk": -100}.items():
            with self.subTest(name=name):
                found = service.find_modulation(name)
                self.assertEqual(len(found["candidates"]), 1)
                record = found["candidates"][0]["record"]
                self.assertEqual(record["rx_sensitivity_dbm"], sensitivity)
                self.assertEqual(record["type"], "modulation")
                self.assertTrue(record["simulated"])
                self.assertEqual(record["status"], "verified")
                self.assertEqual(record["note"], "模拟参数，可配置")
                self.assertEqual(record["source"]["path"], "docs/design/TEACHER_CASES.md")
                self.assertEqual(record["source"]["locator"], "决定 · 调制灵敏度")
        self.assertEqual(service.find_modulation("8PSK")["candidates"], [])
        self.assertTrue(all(row["type"] != "modulation" for row in service.records()))
        public = [row for row in service.public_records()["records"] if row["type"] == "modulation"]
        self.assertEqual(len(public), 3)
        self.assertEqual(service.describe()["modulation_count"], 3)

    def test_bad_modulation_catalog_is_rejected(self):
        mutations = [
            ("duplicate id", lambda rows: rows.append(copy.deepcopy(rows[0]))),
            ("empty names", lambda rows: rows[0].update(names=[])),
            ("blank alias", lambda rows: rows[0].update(names=["QPSK", " "])),
            ("wrong type", lambda rows: rows[0].update(type="device")),
            ("missing source", lambda rows: rows[0]["source"].update(path="docs/missing.md")),
        ]
        for value in ("-100", True, None, math.nan, math.inf, -math.inf):
            mutations.append((f"invalid sensitivity {value!r}",
                              lambda rows, value=value: rows[0].update(rx_sensitivity_dbm=value)))
        self.assert_rejected_mutations("knowledge/facts/modulations.json", mutations)

    def test_typical_values_match_teacher_defaults_and_return_deep_copies(self):
        service = FactService(self.root)
        expected = {
            "distance_km": ("km", 10, [10]),
            "tx_power_dbm": ("dBm", 20, [17, 20, 23, 27, 30]),
            "tx_gain_dbi": ("dBi", 18, [12, 18, 24]),
            "rx_gain_dbi": ("dBi", 18, [12, 18, 24]),
            "modulation": ("—", "QPSK", ["QPSK", "16QAM", "64QAM"]),
        }
        rows = service.typical_values()
        self.assertEqual(len(rows), 5)
        self.assertEqual({row["field"] for row in rows}, set(expected))
        for row in rows:
            self.assertEqual((row["unit"], row["default"], row["candidates"]), expected[row["field"]])
            self.assertEqual(row["note"], "模拟参数，可配置；默认补全，需用户确认")
        original = copy.deepcopy(rows)
        rows[0]["candidates"].append("tampered")
        rows[0]["default"] = "tampered"
        self.assertEqual(service.typical_values(), original)

    def test_typical_values_enforce_membership_modulation_and_numeric_domains(self):
        def change_field(rows, field, **changes):
            next(row for row in rows if row["field"] == field).update(changes)

        mutations = [
            ("default outside candidates", lambda rows: change_field(rows, "tx_power_dbm", default=99)),
            ("unknown default modulation", lambda rows: change_field(rows, "modulation", default="8PSK", candidates=["8PSK"])),
            ("unknown candidate modulation", lambda rows: change_field(rows, "modulation", candidates=["QPSK", "8PSK"])),
        ]
        for field in ("distance_km", "tx_power_dbm", "tx_gain_dbi", "rx_gain_dbi"):
            for value in (True, "20", math.nan, math.inf):
                mutations.append((f"{field} nonnumeric {value!r}",
                                  lambda rows, field=field, value=value: change_field(rows, field, default=value, candidates=[value])))
        for value in (0, -1):
            mutations.append((f"distance domain {value}",
                              lambda rows, value=value: change_field(rows, "distance_km", default=value, candidates=[value])))
        mutations.append(("candidate violates domain", lambda rows: change_field(rows, "distance_km", candidates=[10, 0])))
        self.assert_rejected_mutations("knowledge/facts/typical_values.json", mutations)

    def test_typical_values_reject_invalid_structure_and_incomplete_fields(self):
        mutations = [
            ("missing required field", lambda rows: rows.pop()),
            ("duplicate field", lambda rows: rows.append(copy.deepcopy(rows[0]))),
            ("unknown field", lambda rows: rows[0].update(field="frequency_mhz")),
            ("nonobject record", lambda rows: rows.__setitem__(0, None)),
            ("empty unit", lambda rows: rows[0].update(unit="")),
            ("blank note", lambda rows: rows[0].update(note=" ")),
            ("empty candidates", lambda rows: rows[0].update(candidates=[])),
            ("nonarray candidates", lambda rows: rows[0].update(candidates="10")),
            ("missing default", lambda rows: rows[0].pop("default")),
        ]
        self.assert_rejected_mutations("knowledge/facts/typical_values.json", mutations)
        path = self.root / "knowledge/facts/typical_values.json"
        path.write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            FactService(self.root)


class TeacherSchemaTests(unittest.TestCase):
    def assert_validation(self, schema, passing, failing):
        check_schema(schema)
        for instance in passing:
            self.assertEqual(validate(instance, schema), [], (schema, instance))
        for instance in failing:
            self.assertTrue(validate(instance, schema), (schema, instance))

    def test_all_supported_types_and_number_safety(self):
        cases = (
            ("object", [{}], [[], None]), ("number", [0, -1.5], [True, "1", math.nan, math.inf, -math.inf]),
            ("integer", [1, -2], [1.5, True, "1"]), ("string", ["", "value"], [1, None]),
            ("boolean", [True, False], [0, "true"]), ("array", [[], [1]], [{}, "array"]),
        )
        for kind, passing, failing in cases:
            with self.subTest(type=kind):
                self.assert_validation({"type": kind}, passing, failing)

    def test_properties_required_additional_properties_and_items(self):
        self.assert_validation({"type": "object", "properties": {"value": {"type": "number"}}},
                               [{}, {"value": 2}], [{"value": "2"}])
        self.assert_validation({"type": "object", "required": ["value"]},
                               [{"value": None}], [{}])
        self.assert_validation({"type": "object", "properties": {"value": {"type": "number"}},
                                "additionalProperties": False}, [{}, {"value": 1}], [{"extra": 1}])
        self.assert_validation({"type": "array", "items": {"type": "number"}},
                               [[], [1, 2.5]], [[1, "bad"], [math.nan]])

    def test_enum_and_each_inclusive_and_exclusive_boundary(self):
        self.assert_validation({"type": "string", "enum": ["QPSK", "16QAM"]},
                               ["QPSK", "16QAM"], ["8PSK"])
        cases = (
            ("minimum", [2, 2.1], [1.9]), ("maximum", [2, 1.9], [2.1]),
            ("exclusiveMinimum", [2.1], [2, 1.9]), ("exclusiveMaximum", [1.9], [2, 2.1]),
        )
        for keyword, passing, failing in cases:
            with self.subTest(keyword=keyword):
                self.assert_validation({"type": "number", keyword: 2}, passing, failing)

    def test_one_of_requires_exactly_one_successful_branch(self):
        self.assert_validation(
            {"type": "object", "oneOf": [{"required": ["modulation"]}, {"required": ["rx_sensitivity_dbm"]}]},
            [{"modulation": "QPSK"}, {"rx_sensitivity_dbm": -100}],
            [{}, {"modulation": "QPSK", "rx_sensitivity_dbm": -100}],
        )

    def test_title_and_description_are_string_annotations(self):
        for keyword in ("title", "description"):
            with self.subTest(keyword=keyword):
                self.assert_validation({"type": "number", keyword: "annotation"}, [1], ["1"])
                with self.assertRaises(ValueError):
                    check_schema({"type": "number", keyword: 123})

    def test_unsupported_keywords_are_rejected_even_in_nested_schemas(self):
        for schema in ({"type": "number", "multipleOf": 2},
                       {"properties": {"nested": {"pattern": "x"}}},
                       {"items": {"x-enum-from": "modulations"}},
                       {"oneOf": [{"type": "number"}, {"allOf": []}]}):
            with self.subTest(schema=schema):
                with self.assertRaises(ValueError):
                    check_schema(schema)

    def test_all_verified_cards_match_evaluate_at_bounds_and_invalid_inputs(self):
        cards = [card for card in load_catalog(ROOT) if card["status"] == "verified"]
        for card in cards:
            schema = card_input_schema(card)
            check_schema(schema)
            check_schema(card_output_schema(card))
            self.assertEqual(set(schema["required"]), set(card["parameters"]))
            self.assertIs(schema["additionalProperties"], False)
            baseline = card["examples"][0]["inputs"]
            cases = [("valid example", baseline)]
            for name, spec in card["parameters"].items():
                self.assertIn(spec["unit"], schema["properties"][name]["description"])
                cases.append((f"missing {name}", {key: value for key, value in baseline.items() if key != name}))
                for value in (True, math.nan, math.inf):
                    cases.append((f"{name}={value!r}", baseline | {name: value}))
                for boundary in ("min", "exclusive_min", "max"):
                    if boundary in spec:
                        value = spec[boundary]
                        delta = max(abs(value) * 1e-9, 1e-9)
                        for offset in (-delta, 0, delta):
                            cases.append((f"{name} {boundary} offset {offset}", baseline | {name: value + offset}))
            for label, values in cases:
                with self.subTest(card=card["id"], case=label):
                    errors = validate(values, schema)
                    result = evaluate(card, values)
                    if errors:
                        self.assertNotEqual(result["status"], "ok")
                    elif result["status"] != "ok":
                        self.assertTrue(result.get("errors"))
                        self.assertTrue(all(error.startswith("calculation:") for error in result["errors"]), result)
                    else:
                        self.assertEqual(validate({"value": result["value"], "unit": result["unit"]},
                                                  card_output_schema(card)), [])
            # Authorized compatibility exception: evaluate keeps ignoring extra query inputs.
            # The new schema and registry must both reject them at their own boundary.
            extra = baseline | {"unexpected_parameter": 1}
            with self.subTest(card=card["id"], case="extra parameter"):
                self.assertTrue(validate(extra, schema))
                self.assertEqual(registry.call_tool(ROOT, card["id"], extra)["status"], "invalid_arguments")


class TeacherToolTests(unittest.TestCase):
    def test_teacher_groups_and_all_modulations_use_independent_arithmetic(self):
        rounded = ((127.71, -71.71, (28.29, 23.29, 18.29)),
                   (118.11, -77.11, (22.89, 17.89, 12.89)))
        for group, expected_rounded in zip(TEACHER_INPUTS, rounded):
            margins = []
            for index, (modulation, sensitivity) in enumerate(SENSITIVITIES.items()):
                arguments = group | {"modulation": modulation}
                original = copy.deepcopy(arguments)
                response = registry.call_tool(ROOT, "calc_link_margin", arguments)
                with self.subTest(group=group, modulation=modulation):
                    self.assertEqual(response["status"], "ok", response)
                    self.assertEqual(response["tool"], "calc_link_margin")
                    self.assertEqual(response["arguments"], original)
                    self.assertEqual(arguments, original)
                    self.assertEqual(response["errors"], [])
                    result = response["result"]
                    loss = 32.44 + 20 * math.log10(group["distance_km"]) + 20 * math.log10(group["frequency_mhz"])
                    power = group["tx_power_dbm"] + group["tx_gain_dbi"] + group["rx_gain_dbi"] - loss
                    margin = power - sensitivity
                    for field, value in (("path_loss_db", loss), ("rx_power_dbm", power),
                                         ("rx_sensitivity_dbm", sensitivity), ("link_margin_db", margin)):
                        self.assertAlmostEqual(result[field], value, delta=1e-9)
                    self.assertEqual(result["modulation"], modulation)
                    self.assertEqual(result["sensitivity_source"], "modulation_table")
                    self.assertTrue(result["simulated"])
                    self.assertEqual(result["required_margin_db"], 0)
                    self.assertEqual(result["meets"], margin >= 0)
                    self.assertEqual([round(result[key], 2) for key in ("path_loss_db", "rx_power_dbm")],
                                     list(expected_rounded[:2]))
                    self.assertEqual(round(result["link_margin_db"], 2), expected_rounded[2][index])
                    self.assertEqual([step["card"] for step in response["steps"]],
                                     ["fspl_mhz", "received_power", "link_margin"])
                    receive_inputs = response["steps"][1]["inputs"]
                    self.assertEqual([receive_inputs[name] for name in ("tx_loss_db", "rx_loss_db", "extra_loss_db")], [0, 0, 0])
                    self.assertEqual(response["steps"][2]["inputs"]["reserve_db"], 0)
                    self.assertEqual(registry.call_tool(ROOT, "calc_link_margin", arguments), response)
                    margins.append(result["link_margin_db"])
            self.assertAlmostEqual(margins[0] - margins[1], 5, delta=1e-9)
            self.assertAlmostEqual(margins[0] - margins[2], 10, delta=1e-9)

    def test_argument_sensitivity_and_required_margin_change_meets(self):
        arguments = TEACHER_INPUTS[0] | {"rx_sensitivity_dbm": -100}
        result = registry.call_tool(ROOT, "calc_link_margin", arguments)["result"]
        self.assertEqual(result["sensitivity_source"], "argument")
        self.assertNotIn("modulation", result)
        self.assertNotIn("simulated", result)
        margin = result["link_margin_db"]
        for required, meets in ((0, True), (margin, True), (margin + 1e-6, False)):
            with self.subTest(required=required):
                response = registry.call_tool(ROOT, "calc_link_margin", arguments | {"required_margin_db": required})
                self.assertEqual(response["status"], "ok", response)
                self.assertEqual(response["result"]["required_margin_db"], required)
                self.assertEqual(response["result"]["meets"], meets)

    def test_invalid_composite_arguments_are_rejected_before_calculation(self):
        base = TEACHER_INPUTS[0]
        invalid = [base, base | {"modulation": "QPSK", "rx_sensitivity_dbm": -100},
                   base | {"modulation": "8PSK"}, base | {"modulation": "QPSK", "distance_km": 0},
                   base | {"modulation": "QPSK", "extra": 1},
                   base | {"modulation": "QPSK", "required_margin_db": -1}]
        for name in (*base, "rx_sensitivity_dbm", "required_margin_db"):
            for value in (True, math.nan, math.inf):
                invalid.append(base | {"rx_sensitivity_dbm": -100, name: value})
        for arguments in invalid:
            with self.subTest(arguments=arguments), patch.object(registry.core, "evaluate", side_effect=AssertionError("invalid arguments reached calculator")):
                response = registry.call_tool(ROOT, "calc_link_margin", arguments)
                self.assertEqual(response["status"], "invalid_arguments")
                self.assertTrue(response["errors"])
                self.assertIsNone(response["result"])
                self.assertEqual(response["steps"], [])

    def test_card_tool_result_and_unregistered_id(self):
        for card in load_catalog(ROOT):
            if card["status"] != "verified":
                continue
            inputs = card["examples"][0]["inputs"]
            calculated = evaluate(card, inputs)
            response = registry.call_tool(ROOT, card["id"], inputs)
            self.assertEqual(response["status"], "ok", card["id"])
            self.assertEqual(response["result"], {"value": calculated["value"], "unit": calculated["unit"]})
        self.assertNotEqual(registry.call_tool(ROOT, "unregistered_tool", {})["status"], "ok")

    def test_card_output_schema_failures_return_failed(self):
        with patch.object(registry.core, "evaluate", return_value={"status": "ok", "value": "bad", "unit": "dB"}):
            response = registry.call_tool(ROOT, "fspl_mhz", {"distance_km": 10, "frequency_mhz": 5800})
        self.assertEqual(response["status"], "failed")
        self.assertTrue(response["errors"])
        self.assertIsNone(response["result"])

    def test_composite_final_output_schema_failure_returns_failed(self):
        def reject_output(instance, schema):
            if "link_margin_db" in schema.get("properties", {}):
                return ["synthetic output failure"]
            return validate(instance, schema)

        with patch.object(registry, "validate", side_effect=reject_output):
            response = registry.call_tool(ROOT, "calc_link_margin", TEACHER_INPUTS[0] | {"modulation": "QPSK"})
        self.assertEqual(response["status"], "failed")
        self.assertTrue(response["errors"])
        self.assertIsNone(response["result"])

    def test_new_fspl_reference_model_is_independent_and_old_card_unchanged(self):
        cards = {card["id"]: card for card in load_catalog(ROOT)}
        self.assertEqual(cards["fspl_ghz"]["expression"], "92.4 + 20*log10(frequency_ghz) + 20*log10(distance_km)")
        for inputs in TEACHER_INPUTS:
            parameters = {name: inputs[name] for name in ("distance_km", "frequency_mhz")}
            value = evaluate(cards["fspl_mhz"], parameters)["value"]
            # The independent physical formula uses exact c and 4*pi. The
            # registered teacher card intentionally rounds its constant to 32.44.
            self.assertAlmostEqual(reference_models.fspl_mhz(parameters), value, delta=0.01)
            self.assertTrue(reference_models.agrees("fspl_mhz", parameters, value))
            old = evaluate(cards["fspl_ghz"], {"distance_km": inputs["distance_km"], "frequency_ghz": inputs["frequency_mhz"] / 1000})["value"]
            self.assertAlmostEqual(value - old, 0.04, delta=1e-9)

    def test_m1_targets_chains_and_states_are_unchanged(self):
        rows = teacher_regression_rows()
        self.assertEqual(len(rows), 28)
        for row in rows:
            with self.subTest(case=row["id"]):
                self.assertEqual(row["before"], row["after"])


class TeacherToolsApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from planning.web_server import create_server
        cls.temp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temp.cleanup)
        cls.root = copy_knowledge(Path(cls.temp.name) / "app")
        shutil.copytree(ROOT / "config", cls.root / "config")
        cls.server = create_server(cls.root, Path(cls.temp.name) / "web.sqlite", port=0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.addClassCleanup(cls.stop)
        cls.base = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def stop(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def get(self, path):
        with urlopen(self.base + path, timeout=15) as response:
            self.assertEqual(response.status, 200)
            return json.loads(response.read().decode("utf-8"))

    def test_api_tools_is_complete_and_schemas_have_only_standard_keywords(self):
        tools = self.get("/api/tools")["tools"]
        cards = [card for card in load_catalog(self.root) if card["status"] == "verified"]
        self.assertEqual({tool["id"] for tool in tools}, {card["id"] for card in cards} | {"calc_link_margin"})
        self.assertEqual(len(tools), len(cards) + 1)
        self.assertEqual(tools, registry.load_tools(self.root))

        def no_extensions(value):
            if isinstance(value, dict):
                for key, nested in value.items():
                    self.assertFalse(key.startswith("x-"), key)
                    no_extensions(nested)
            elif isinstance(value, list):
                for nested in value:
                    no_extensions(nested)

        for tool in tools:
            with self.subTest(tool=tool["id"]):
                self.assertEqual(len(tool["content_hash"]), 64)
                for field in ("input_schema", "output_schema"):
                    check_schema(tool[field])
                    no_extensions(tool[field])
        composite = next(tool for tool in tools if tool["id"] == "calc_link_margin")
        self.assertEqual(composite["steps"], ["fspl_mhz", "received_power", "link_margin"])
        self.assertEqual(composite["input_schema"]["properties"]["modulation"]["enum"], list(SENSITIVITIES))
        self.assertTrue(composite["assumptions"])

    def test_step_and_card_tool_hashes_equal_formula_cards_api(self):
        tools = {tool["id"]: tool for tool in self.get("/api/tools")["tools"]}
        ids = [card["id"] for card in load_catalog(self.root) if card["status"] == "verified"]
        response = self.get("/api/formula-cards?ids=" + ",".join(ids))
        self.assertEqual(response["missing"], [])
        cards = {card["id"]: card for card in response["cards"]}
        for ident, card in cards.items():
            content_hash = card.pop("content_hash")
            self.assertEqual(content_hash, digest(card))
            self.assertEqual(tools[ident]["content_hash"], content_hash)
        calculated = registry.call_tool(self.root, "calc_link_margin", TEACHER_INPUTS[0] | {"modulation": "QPSK"})
        self.assertEqual(calculated["status"], "ok", calculated)
        for step in calculated["steps"]:
            self.assertEqual(step["content_hash"], tools[step["card"]]["content_hash"])
            reproduced = evaluate(cards[step["card"]], step["inputs"])
            self.assertEqual(step["value"], reproduced["value"])
            self.assertEqual(step["unit"], reproduced["unit"])

    def test_facts_api_includes_typical_values_and_modulations(self):
        response = self.get("/api/facts")
        self.assertEqual(response["typical_values"], FactService(self.root).typical_values())
        self.assertEqual(len([row for row in response["records"] if row["type"] == "modulation"]), 3)


if __name__ == "__main__":
    unittest.main()
