import io
import json
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from formula_rag.model import LocalSelector
from planning.agents.requirements import RequirementsAgent
from test_requirements_contract import request

ROOT = Path(__file__).resolve().parents[1]


class RequirementSelectionTests(unittest.TestCase):
    def run_local(self, req, proposal):
        opener = Mock()
        opener.open.side_effect = lambda *a, **k: io.BytesIO(json.dumps({
            'choices': [{'message': {'content': json.dumps(proposal)}}], 'model': 'test-local'
        }).encode())
        with patch('formula_rag.model.urllib.request.build_opener', return_value=opener):
            report = RequirementsAgent(ROOT, selector=LocalSelector()).run(req)
        return report, json.loads(opener.open.call_args.args[0].data)

    def test_selected_target_is_context_not_fabricated_quote(self):
        req = request('按自由空间基准计算，频率5GHz，路径距离0.9-1.1km。')
        req['target'] = 'fspl_ghz'
        report, payload = self.run_local(req, {'selected_ids':['fspl_ghz'], 'targets':[],
            'conditions':[{'id':'free_space_reference','evidence':'按自由空间基准计算'}]})
        self.assertEqual(report['execution_status'], 'AWAITING_CONFIRMATION')
        self.assertEqual(report['component_modes']['interpretation'], 'llm')
        schema = payload['response_format']['json_schema']['schema']['properties']
        self.assertEqual(schema['targets']['maxItems'], 0)
        self.assertIn('"target": "fspl_ghz"', payload['messages'][-1]['content'])
        source = next(d for d in report['diagnostics'] if d['code']=='USER_TARGET_SELECTION')
        self.assertEqual(source['details']['source_ref'], 'request-1:target')
        self.assertNotIn('求路径损耗', req['raw_text'])

    def test_all_manual_selections_and_empty_text(self):
        req = request('')
        req.update(target='fspl_ghz',condition='free_space_reference',manual_parameters={
            'frequency_ghz':{'value':5,'unit':'GHz'},'distance_km':{'value':1,'unit':'km'}})
        report, payload = self.run_local(req, {'selected_ids':['fspl_ghz'],'targets':[],'conditions':[]})
        self.assertEqual(report['execution_status'], 'AWAITING_CONFIRMATION')
        self.assertEqual(payload['response_format']['json_schema']['schema']['properties']['conditions']['maxItems'],0)
        self.assertIn('USER_CONDITION_SELECTION', [d['code'] for d in report['diagnostics']])

    def test_unselected_target_still_requires_verbatim_evidence(self):
        report, payload = self.run_local(request('按自由空间基准计算，频率5GHz，距离1km。'),
            {'selected_ids':['fspl_ghz'],'targets':[{'id':'fspl_ghz','evidence':'求路径损耗'}],'conditions':[]})
        self.assertEqual(report['runtime_health'], 'degraded')
        failures=[d['details'] for d in report['diagnostics'] if d['code']=='MODEL_OUTPUT_INVALID']
        self.assertEqual(len(failures), 3)
        self.assertEqual(failures[0]['reason'], 'MODEL_UNGROUNDED')
        self.assertEqual(failures[0]['rejected'][0]['reason'], '目标或原文证据无效')
        self.assertEqual(json.loads(failures[0]['model_output'])['targets'][0]['evidence'], '求路径损耗')
        self.assertEqual(payload['response_format']['json_schema']['schema']['properties']['targets']['maxItems'],3)

    def test_manual_selection_cannot_hide_original_conflict(self):
        req = request('不要计算路径损耗，求接收功率，频率5GHz，距离1km。')
        req.update(target='fspl_ghz',condition='free_space_reference')
        report=RequirementsAgent(ROOT,selector=False).run(req)
        self.assertNotEqual(report['execution_status'], 'AWAITING_CONFIRMATION')

    def test_manual_target_cannot_accept_fabricated_evidence(self):
        req=request('按自由空间基准计算，频率5GHz，距离1km。');req['target']='fspl_ghz'
        report,_=self.run_local(req,{'selected_ids':['fspl_ghz'],'targets':[{'id':'fspl_ghz','evidence':'求路径损耗'}],'conditions':[]})
        self.assertEqual(report['runtime_health'],'degraded')
        self.assertTrue(any(d['code']=='MODEL_OUTPUT_INVALID' for d in report['diagnostics']))
