import copy
import importlib
import unittest


def request(text='按自由空间基准计算，频率2GHz，距离1km，求路径损耗。'):
    return dict(schema_version='1.0.0', task_id='task-1', revision=0,
                request_id='request-1', raw_text=text, manual_parameters={}, condition=None, target=None)


class ContractTests(unittest.TestCase):
    def module(self):
        try:
            return importlib.import_module('planning.requirements_contract')
        except ModuleNotFoundError:
            self.fail('requirements slice contract has not been implemented')

    def test_request_roundtrip_and_copy(self):
        data = request()
        result = self.module().validate_request(data)
        self.assertEqual(data, result)
        self.assertIsNot(data, result)

    def test_request_rejects_bad_boundaries(self):
        c = self.module()
        for patch in [dict(extra=1), dict(revision=True), dict(revision=-1), dict(task_id=' '),
                      dict(schema_version='2'), dict(condition='maybe'), dict(raw_text='x'*12001),
                      dict(manual_parameters={'distance_km': {'value': True, 'unit': 'km'}}),
                      dict(manual_parameters={'distance_km': {'value': float('nan'), 'unit': 'km'}}),
                      dict(manual_parameters={'distance_km': {'value': 1, 'unit': 'W'}}),
                      dict(manual_parameters={'distance_km': {'value': 1, 'unit': 'km', 'extra': 2}})]:
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                c.validate_request({**request(), **patch})

    def test_stale_revision(self):
        with self.assertRaisesRegex(ValueError, 'STALE_REVISION'):
            self.module().validate_request(request(), expected_revision=1)
