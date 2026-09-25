import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from planning.services.model_status import probe_model, default_endpoint_alias


class ModelServiceStatusTests(unittest.TestCase):
    def test_ready_requires_health_and_expected_model(self):
        alias = default_endpoint_alias()[1]
        with patch('planning.services.model_status.read_status', side_effect=[
            {'status': 'ok'}, {'data': [{'id': alias}]}
        ]) as read:
            result = probe_model()
        self.assertEqual(result['status'], 'ready')
        self.assertTrue(result['checked_at'])
        self.assertEqual([call.args[0] for call in read.call_args_list], ['/health', '/v1/models'])
        with patch('planning.services.model_status.read_status', side_effect=[
            {'status': 'ok'}, {'data': [{'id': 'other-model'}]}
        ]):
            self.assertEqual(probe_model()['status'], 'unexpected')

    def test_failure_does_not_claim_process_stopped(self):
        for error, expected in [(URLError('connection refused'), 'unreachable'),
                                (TimeoutError(), 'unreachable'),
                                (HTTPError('local', 503, 'loading', {}, None), 'not_ready'),
                                (ValueError('bad JSON'), 'unknown')]:
            with self.subTest(expected=expected), patch('planning.services.model_status.read_status', side_effect=error):
                self.assertEqual(probe_model()['status'], expected)

    def test_loading_and_malformed_payload(self):
        for payload, expected in [({'status': 'loading model'}, 'loading'), ([], 'unknown')]:
            with patch('planning.services.model_status.read_status', return_value=payload):
                self.assertEqual(probe_model()['status'], expected)
