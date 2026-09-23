import io
import json
import time
import unittest
from unittest.mock import Mock,patch
from urllib.error import HTTPError
from formula_rag.model_transport import chat,parse_output,ModelResponseError,operation_deadline
from planning.agents.requirements import RequirementsAgent
from test_requirements_contract import request
from test_planning_loop import ROOT

class TransportTests(unittest.TestCase):
    def test_http_400_context_is_not_connection_failure_and_not_retried(self):
        opener=Mock();opener.open.side_effect=HTTPError('http://127.0.0.1',400,'bad',{},io.BytesIO(b'context size exceeded'))
        with patch('urllib.request.build_opener',return_value=opener):
            report=RequirementsAgent(ROOT).run(request('按自由空间基准，频率2GHz，距离1km，求路径损耗'))
        opener.open.assert_called_once()
        self.assertIn('MODEL_CONTEXT_LIMIT',[d['code'] for d in report['diagnostics']])
        self.assertNotIn('MODEL_UNAVAILABLE',[d['code'] for d in report['diagnostics']])
        self.assertEqual(report['execution_status'],'AWAITING_CONFIRMATION')

    def test_empty_choices_and_invalid_json_preserve_raw_response(self):
        opener=Mock();opener.open.side_effect=lambda *a,**k:io.BytesIO(b'{"choices":[]}')
        with patch('urllib.request.build_opener',return_value=opener):
            with self.assertRaises(ModelResponseError) as caught:chat({'messages':[{'content':'test'}]})
        self.assertEqual(caught.exception.code,'MODEL_OUTPUT_INVALID')
        self.assertIn('choices',caught.exception.raw_output)
        for raw in ('bad json','{"a":1,"a":2}','{"a":NaN}'):
            with self.subTest(raw=raw),self.assertRaises(ModelResponseError) as caught:parse_output(raw)
            self.assertEqual(caught.exception.raw_output,raw)

    def test_deadline_and_context_budget_skip_network(self):
        token=operation_deadline.set(time.monotonic()-1)
        try:
            with self.assertRaises(ModelResponseError) as caught:chat({'messages':[]})
            self.assertEqual(caught.exception.code,'MODEL_TIME_BUDGET')
        finally:operation_deadline.reset(token)
        with patch('urllib.request.build_opener') as network:
            with self.assertRaises(ModelResponseError) as caught:chat({'messages':[{'content':'测试'*6000}]})
            self.assertEqual(caught.exception.code,'MODEL_CONTEXT_LIMIT')
            network.assert_not_called()
