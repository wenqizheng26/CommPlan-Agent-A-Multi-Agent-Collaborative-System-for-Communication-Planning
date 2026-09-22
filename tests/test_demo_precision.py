import copy
import unittest
from planning.services.domain_calculation import conclusion

class DemoPrecisionTests(unittest.TestCase):
    def test_human_precision_does_not_mutate_raw_outputs(self):
        outputs=[{'value':98.42059991327963}, {'value':101.94242509439325}]
        before=copy.deepcopy(outputs)
        self.assertEqual(conclusion(outputs),'按已确认自由空间条件，候选 1：98.42 dB；候选 2：101.94 dB。')
        self.assertEqual(outputs,before)
        self.assertEqual(conclusion(outputs[:1]),'按已确认自由空间条件，98.42 dB。')

    def test_interval_presentation_retains_nonprobabilistic_boundary(self):
        outputs=[{'value':{'kind':'interval','lower':97.975072,'upper':98.844386}}]
        before=copy.deepcopy(outputs)
        self.assertIn('97.98–98.84 dB（输入范围对应的计算范围，非置信区间）',conclusion(outputs))
        self.assertEqual(outputs,before)
