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
        r = self.agent().run(request('按自由空间基准，距离1km，求路径损耗'))
        self.assertEqual(r['execution_status'], 'AWAITING_INPUT')
        self.assertIn('frequency_ghz', r['missing_parameters'])
        p = next(p for p in r['parameters_proposal'] if p['canonical_name'] == 'frequency_ghz')
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
            return {'raw_output': json.dumps({'selected_ids': ['fspl_ghz'], 'targets': [{'id': 'fspl_ghz', 'evidence': '求路径损耗'}], 'conditions': []})}
        r = self.agent(fake).run(request('按自由空间基准，距离1km，求路径损耗'))
        self.assertEqual(r['component_modes']['interpretation'], 'stub')
        self.assertIn('frequency_ghz', r['missing_parameters'])

    def test_month_one_scope_and_conditions(self):
        cases = [('求热噪声功率，温度300K，带宽2MHz', 'NEEDS_MODEL'),
                 ('频率2GHz，距离1km，求路径损耗', 'AWAITING_INPUT'),
                 ('按自由空间基准，频率0GHz，距离1km，求路径损耗', 'AWAITING_INPUT'),
                 ('按自由空间基准，频率2GHz，距离1e-12km，求路径损耗', 'NEEDS_MODEL'),
                 ('真实海面传播损耗，频率2GHz，距离1km', 'NEEDS_MODEL'),
                 ('频率2GHz，距离1km', 'AWAITING_INPUT'),
                 ('按自由空间基准，频率2至3GHz，距离1km，求路径损耗', 'AWAITING_CONFIRMATION'),
                 ('按自由空间基准，频率不是2GHz，距离1km，求路径损耗', 'AWAITING_INPUT')]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(self.agent().run(request(text))['execution_status'], expected)

    def test_manual_intent_cannot_erase_contradiction(self):
        q = request('求接收功率，频率2GHz，距离1km')
        q.update(target='fspl_ghz', condition='free_space')
        r = self.agent().run(q)
        self.assertNotEqual(r['execution_status'], 'AWAITING_CONFIRMATION')
        self.assertIn('INTENT_CONFLICT', [x['code'] for x in r['diagnostics']])

    def test_input_not_mutated_and_stale_rejected_before_selector(self):
        q = request(); original = copy.deepcopy(q)
        self.agent().run(q)
        self.assertEqual(q, original)
        def forbidden(*args):
            self.fail('stale request called model')
        with self.assertRaisesRegex(ValueError, 'STALE_REVISION'):
            self.agent(forbidden).run(q, expected_revision=9)

    def test_model_cannot_use_duplicate_keys_or_fabricated_evidence(self):
        for raw in ['{"selected_ids":[],"selected_ids":["fspl_ghz"],"targets":[],"conditions":[]}',
                    json.dumps({'selected_ids':['fspl_ghz'], 'targets':[{'id':'fspl_ghz','evidence':'不存在的原文'}], 'conditions':[]})]:
            r = self.agent(lambda *a: {'raw_output':raw}).run(request('频率2GHz，距离1km'))
            self.assertNotEqual(r['execution_status'], 'AWAITING_CONFIRMATION')

    def test_source_original_units_and_normalized_values(self):
        r = self.agent().run(request('按自由空间基准，频率2000MHz，距离1000m，求路径损耗'))
        p = {x['canonical_name']:x for x in r['parameters_proposal']}
        self.assertEqual(p['frequency_ghz']['value'], 2)
        self.assertEqual(p['frequency_ghz']['origins'][0]['value'], 2000)
        self.assertEqual(p['distance_km']['value'], 1)
        self.assertEqual(p['distance_km']['origins'][0]['unit'], 'm')

    def test_alternatives_and_two_way_are_not_single_link_inputs(self):
        for text in ['按自由空间基准，频率2GHz，距离1km，求路径损耗，频率2GHz或者3GHz',
                     '按自由空间基准，频率2GHz，距离1km，求双程路径损耗']:
            with self.subTest(text=text):
                self.assertNotEqual(self.agent().run(request(text))['execution_status'],'AWAITING_CONFIRMATION')

    def test_explicit_baseline_with_disclaimer_is_supported(self):
        text='只按自由空间基准计算，不代表实际海面损耗，频率2GHz，距离1km，求路径损耗'
        self.assertEqual(self.agent().run(request(text))['execution_status'],'AWAITING_CONFIRMATION')

    def test_model_target_must_mean_path_loss(self):
        def fake(*args):
            return {'raw_output':json.dumps({'selected_ids':['fspl_ghz'],'targets':[{'id':'fspl_ghz','evidence':'求天线高度'}],'conditions':[]})}
        r = self.agent(fake).run(request('按自由空间基准，频率2GHz，距离1km，求天线高度'))
        self.assertNotEqual(r['execution_status'],'AWAITING_CONFIRMATION')

    def test_explicit_domains_are_preserved_for_confirmation(self):
        for values in ['2GHz或3GHz','2GHz、3GHz','2GHz至3GHz','2GHz或者3GHz']:
            r=self.agent().run(request('按自由空间基准，距离1km，求路径损耗，频率'+values))
            self.assertEqual(r['execution_status'],'AWAITING_CONFIRMATION')
            value=next(p['value'] for p in r['parameters_proposal'] if p['canonical_name']=='frequency_ghz')
            self.assertEqual(value['kind'],'interval' if '至' in values else 'choices')

    def test_zero_similarity_cannot_supply_evidence(self):
        a=self.agent()
        with patch.object(a.retriever,'search',return_value=[{'id':'fspl_ghz','rank':1,'lexical_similarity':0}]):
            self.assertEqual(a.run(request())['execution_status'],'NEEDS_MODEL')

    def test_direct_lookup_manual_units_and_missing_fields(self):
        q=request(''); q.update(target='fspl_ghz',condition='free_space_reference',manual_parameters={
            'frequency_ghz':{'value':2000,'unit':'MHz'},'distance_km':{'value':1000,'unit':'m'}})
        r=self.agent().run(q)
        self.assertEqual(r['execution_status'],'AWAITING_CONFIRMATION')
        self.assertEqual({p['canonical_name']:p['value'] for p in r['parameters_proposal']},{'frequency_ghz':2,'distance_km':1})

    def test_all_status_paths_never_call_numerical_tool(self):
        cases=[request(),request('按自由空间基准求路径损耗，频率2GHz'),request('求真实海面传播损耗，频率2GHz，距离1km'),
               request('按自由空间基准求路径损耗，频率2GHz，频率3GHz，距离1km')]
        with patch('formula_rag.core.evaluate',side_effect=AssertionError('compute forbidden')), patch('formula_rag.pipeline.Engine.query',side_effect=AssertionError('engine forbidden')):
            for q in cases:
                r=self.agent().run(q)
                self.assertNotIn('result',r)
                self.assertFalse(any(p['status']=='confirmed' for p in r['parameters_proposal']))
            def fail(*args): raise OSError('offline')
            self.assertEqual(self.agent(fail,allow_fallback=False).run(request())['execution_status'],'FAILED')

    def test_known_unsupported_scope_does_not_depend_on_model_service(self):
        def forbidden(*args): self.fail('unneeded model invocation')
        r=self.agent(forbidden,allow_fallback=False).run(request('求真实海面传播损耗，频率2GHz，距离1km'))
        self.assertEqual(r['execution_status'],'NEEDS_MODEL')

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
