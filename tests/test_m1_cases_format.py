import collections
import json
from pathlib import Path
import unittest


class M1CasesFormatTests(unittest.TestCase):
    def test_independent_acceptance_inventory_is_complete(self):
        path=Path(__file__).parent/'eval/m1_cases.jsonl'
        rows=[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
        self.assertEqual(len({r['id'] for r in rows}),len(rows))
        self.assertEqual(collections.Counter(r['category'] for r in rows),
                         dict(main=12,variant=10,hard_rule=8,offline_equivalence=6))
        self.assertEqual(collections.Counter(r['rule'] for r in rows if r['category']=='hard_rule'),
                         dict(H1=2,H2=2,H3=2,H4=2))
        for row in rows:
            self.assertIsInstance(row['expected'],dict)
            if row['category']=='main':
                self.assertEqual(row['expected']['target'],'link_margin')
                self.assertEqual(row['expected']['requirement']['value'],10)
                self.assertEqual(row['expected']['solve'],'tx_power_dbm')
            if row['category']!='hard_rule':
                self.assertTrue(row['text'])


if __name__=='__main__':unittest.main()


class NaturalQuestionRegression(unittest.TestCase):
    def test_feasibility_question_does_not_negate_known_frequency(self):
        from formula_rag.parsing import extract_request
        from planning.services.requirement_quantities import find_quantities
        text='在 2 GHz 下的现有配置是否满足'
        self.assertFalse(extract_request(text)['issues'])
        self.assertEqual(find_quantities(text)[0]['value'],2)
        self.assertEqual(find_quantities('是否采用 2 GHz'),[])

    def test_margin_statement_is_a_grounded_goal_but_concept_is_not(self):
        from planning.services.requirement_policy import validate_target_semantics
        validate_target_semantics(dict(targets=[dict(id='link_margin',evidence='余量要求 10 dB')]))
        with self.assertRaises(ValueError):
            validate_target_semantics(dict(targets=[dict(id='link_margin',evidence='解释什么是余量')]))

    def test_device_model_digits_are_not_frequency_choices(self):
        from planning.services.input_domains import extract_domains
        from planning.services.requirement_quantities import find_quantities
        self.assertEqual(extract_domains('电台 XX-100、2 GHz 是否满足'),([],[]))
        self.assertEqual([q['value'] for q in find_quantities('电台 XX-100、2 GHz 是否满足')],[2.])
        from planning.services.requirement_parameters import collect_parameters
        from formula_rag.parsing import extract_request
        text='电台 XX-100、2 GHz 是否满足'
        request=dict(raw_text=text,manual_parameters={},revision=0,request_id='test')
        _,_,issues=collect_parameters(request,extract_request(text),[])
        self.assertFalse(any(i['code']=='INPUT_PARSE_ISSUE' for i in issues))
        self.assertEqual(extract_domains('频率 1、2 GHz')[0][0]['value']['values'],[1.,2.])
