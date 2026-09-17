import copy
import importlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from test_requirements_contract import request

ROOT = Path(__file__).resolve().parents[1]


class RequirementsTests(unittest.TestCase):
    def agent(self, selector=False, **kwargs):
        try:
            module = importlib.import_module('planning.agents.requirements')
        except ModuleNotFoundError:
            self.fail('requirements agent has not been implemented')
        return module.RequirementsAgent(ROOT, selector=selector, **kwargs)

    def test_complete_never_computes(self):
        with patch('formula_rag.core.evaluate', side_effect=AssertionError('compute forbidden')), patch('formula_rag.pipeline.Engine.query', side_effect=AssertionError('engine forbidden')):
            r = self.agent().run(request())
        self.assertEqual(r['execution_status'], 'AWAITING_CONFIRMATION')
        self.assertEqual(r['component_modes']['retrieval'], 'lexical_fallback')
        self.assertIsNone(r['knowledge_snapshot']['embedding_weights_hash'])
        self.assertTrue(r['evidence_refs'])
        self.assertEqual(r['calculation_plan_proposal']['steps'][0]['tool_id'], 'fspl_ghz')

    def test_missing_has_no_default(self):
        r = self.agent().run(request('求热噪声功率，带宽2MHz'))
        self.assertEqual(r['execution_status'], 'AWAITING_INPUT')
        self.assertIn('temperature_k', r['missing_parameters'])
        p = next(p for p in r['parameters_proposal'] if p['canonical_name'] == 'temperature_k')
        self.assertIsNone(p['value'])

    def test_conflicts_and_equivalent_units(self):
        for text, manual, conflict in [('频率2GHz，频率3GHz', {}, True), ('频率2GHz', {'frequency_ghz': {'value': 3, 'unit': 'GHz'}}, True), ('频率2GHz，频率2000MHz', {}, False)]:
            q = request('按自由空间基准计算，距离1km，求路径损耗。' + text)
            q['manual_parameters'] = manual
            r = self.agent().run(q)
            p = next(p for p in r['parameters_proposal'] if p['canonical_name'] == 'frequency_ghz')
            self.assertEqual(len(p['origins']), 2)
            self.assertEqual(bool(r['conflicts']), conflict)
            self.assertEqual(p['value'], None if conflict else 2)

    def test_unsupported_and_negation(self):
        for text in ['散射环境，频率2GHz，距离1km，求路径损耗', '速度30km/h，求多普勒损耗']:
            self.assertEqual(self.agent().run(request(text))['execution_status'], 'NEEDS_MODEL')
        self.assertNotEqual(self.agent().run(request('不要计算路径损耗，频率2GHz，距离1km'))['execution_status'], 'AWAITING_CONFIRMATION')

    def test_model_raw_output_rejected_and_bounded(self):
        calls = []
        def fake(*args):
            calls.append(1)
            return {'selected_ids': ['fspl_ghz'], 'raw_output': json.dumps({'selected_ids': ['fspl_ghz'], 'targets': [], 'conditions': [], 'parameters': {'distance_km': 999}})}
        r = self.agent(fake).run(request())
        self.assertEqual(len(calls), 3)
        self.assertEqual(r['runtime_health'], 'degraded')
        self.assertEqual(r['component_modes']['interpretation'], 'deterministic')
        self.assertNotIn('999', json.dumps(r['parameters_proposal']))

    def test_stub_grounding_and_no_numeric_invention(self):
        def fake(*args):
            return {'raw_output': json.dumps({'selected_ids': ['thermal_noise'], 'targets': [{'id': 'thermal_noise', 'evidence': '求热噪声功率'}], 'conditions': []})}
        r = self.agent(fake).run(request('求热噪声功率，带宽2MHz'))
        self.assertEqual(r['component_modes']['interpretation'], 'stub')
        self.assertIn('temperature_k', r['missing_parameters'])

    def test_network_failure_and_fail_closed(self):
        def fail(*args):
            raise OSError('offline')
        self.assertEqual(self.agent(fail).run(request())['runtime_health'], 'degraded')
        self.assertEqual(self.agent(fail, allow_fallback=False).run(request())['execution_status'], 'FAILED')

    def test_empty_evidence_and_unknown_target(self):
        a = self.agent()
        with patch.object(a.retriever, 'search', return_value=[]):
            self.assertEqual(a.run(request())['execution_status'], 'NEEDS_MODEL')
        q = request(); q['target'] = 'unknown_model'
        self.assertEqual(a.run(q)['execution_status'], 'NEEDS_MODEL')

    def test_report_strict_identity_and_nested_schema(self):
        a = self.agent(); q = request(); r = a.run(q)
        c = importlib.import_module('planning.requirements_contract')
        self.assertEqual(c.validate_report(r, q), r)
        for mutate in [lambda x: x.update(revision=1), lambda x: x.update(extra=1), lambda x: x['parameters_proposal'][0].update(extra=1), lambda x: x['parameters_proposal'][0].update(value=True), lambda x: x['parameters_proposal'][0].update(created_revision=1)]:
            bad = copy.deepcopy(r); mutate(bad)
            with self.assertRaises(ValueError):
                c.validate_report(bad, q)
