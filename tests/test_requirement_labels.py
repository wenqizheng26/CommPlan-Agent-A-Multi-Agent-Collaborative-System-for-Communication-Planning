"""The model labels quantities the program found; values always come from the text."""
import copy
import json
from pathlib import Path
import unittest
from unittest import mock

from formula_rag.catalog import load_catalog
from formula_rag.model import LocalSelector, evidence_spans
from formula_rag.model_transport import estimate_tokens
from planning.agents.requirements import RequirementsAgent
from planning.services.clarification import issues_for
from planning.services.requirement_policy import validate_target_semantics
from planning.services.requirement_quantities import find_quantities, LABEL_FIELDS, SOLVE_UNKNOWNS
from planning.services.requirement_validation import check_report
from test_requirements_contract import request

ROOT = Path(__file__).resolve().parents[1]
DEMO = 'A 站到 B 站用 XX-100 电台、2 GHz，要留 10 dB 余量，能通吗？不能的话发射功率至少要多大？'
CLAUSE = 'A 站到 B 站用 XX-100 电台、2 GHz'
REST = ('发射天线增益10dBi，接收天线增益10dBi，发射馈线损耗2dB，接收馈线损耗2dB，额外损耗0dB，'
        '接收灵敏度-100dBm')
MARGIN = f'按自由空间基准计算链路余量：频率2GHz，距离10km，发射端5W，{REST}，预留余量10dB。'


def ids(text):
    return {q['text']: q['id'] for q in find_quantities(text)}


def model(**output):
    """A stub model that answers with the given keys; missing keys are empty."""
    calls = []
    def fake(text, candidates):
        calls.append([c['id'] for c in candidates])
        body = dict(selected_ids=[c['id'] for c in candidates][:1], targets=[], conditions=[])
        body.update(output)
        return {'raw_output': json.dumps(body, ensure_ascii=False)}
    fake.calls = calls
    return fake


class QuantityTests(unittest.TestCase):
    def test_numbers_with_units_are_found_with_their_spans(self):
        found = find_quantities(DEMO)
        self.assertEqual([q['text'] for q in found], ['2 GHz', '10 dB'])
        for q in found:
            self.assertEqual(DEMO[slice(*q['span'])], q['text'])
        self.assertEqual((found[0]['value'], found[0]['unit']), (2.0, 'GHz'))

    def test_negated_ranged_and_alternative_values_are_not_offered(self):
        for text in ['频率不是2GHz，距离1km', '距离10至20km', '频率2GHz或3GHz', '如果发射功率30dBm']:
            with self.subTest(text=text):
                offered = [q['text'] for q in find_quantities(text)]
                self.assertFalse(any(t in {'2GHz', '20km', '3GHz', '30dBm'} for t in offered), offered)

    def test_a_measure_word_between_number_and_unit_is_read(self):
        [q] = find_quantities('余量得有10个dB')
        self.assertEqual((q['text'], q['value'], q['unit']), ('10个dB', 10.0, 'dB'))

    def test_bounds_are_marked(self):
        [q] = find_quantities('余量至少10dB')
        self.assertEqual(q['comparison'], '>=')
        [q] = find_quantities('功率不超过40dBm')
        self.assertEqual(q['comparison'], '<=')

    def test_questions_split_into_their_own_evidence(self):
        spans = evidence_spans(DEMO)
        self.assertIn('能通吗', spans)
        self.assertIn('不能的话发射功率至少要多大', spans)


class LabelTests(unittest.TestCase):
    cards = load_catalog(ROOT)

    def agent(self, selector):
        return RequirementsAgent(ROOT, selector=selector)

    def demo_model(self):
        q = ids(DEMO)
        return model(targets=[dict(id='link_margin', evidence='能通吗')],
                     quantities=[dict(id=q['2 GHz'], field='frequency_ghz'), dict(id=q['10 dB'], field='required_margin_db')],
                     solve=[dict(unknown='tx_power_dbm', evidence='不能的话发射功率至少要多大')],
                     sites=[dict(mention='A站', evidence=CLAUSE), dict(mention='B站', evidence=CLAUSE)],
                     devices=[dict(mention='XX-100', evidence=CLAUSE)])

    def test_demo_question_is_understood_without_new_numbers(self):
        fake = self.demo_model()
        q = request(DEMO)
        r = self.agent(fake).run(q)
        self.assertIn('link_margin', fake.calls[0])
        self.assertEqual(r['component_modes']['interpretation'], 'stub')
        self.assertEqual(r['targets'], ['link_margin'])
        self.assertEqual(r['requirement'], dict(quantity='link_margin_db', op='>=', value=10.0, unit='dB',
                                                span=[DEMO.index('10 dB'), DEMO.index('10 dB') + 5]))
        self.assertEqual(r['solve']['unknown'], 'tx_power_dbm')
        self.assertEqual([(e['kind'], e['mention']) for e in r['entities']],
                         [('site', 'A 站'), ('site', 'B 站'), ('device', 'XX-100')])
        frequency = next(p for p in r['parameters_proposal'] if p['canonical_name'] == 'frequency_ghz')
        self.assertEqual((frequency['value'], len(frequency['origins'])), (2.0, 1))
        self.assertIn('SOLVE_REQUESTED', [d['code'] for d in r['diagnostics']])
        self.assertEqual(check_report(r, q, self.cards), r)

    def test_a_quantity_the_rules_cannot_bind_is_taken_from_the_model_label(self):
        q = request(MARGIN)
        deterministic = self.agent(False).run(q)
        self.assertIn('tx_power_dbm', deterministic['missing_parameters'])
        fake = model(quantities=[dict(id=ids(MARGIN)['5W'], field='tx_power_dbm')])
        r = self.agent(fake).run(q)
        self.assertEqual(r['execution_status'], 'AWAITING_CONFIRMATION')
        power = next(p for p in r['parameters_proposal'] if p['canonical_name'] == 'tx_power_dbm')
        self.assertAlmostEqual(power['value'], 36.98970004336019)
        self.assertEqual(power['origins'][0]['span'], [MARGIN.index('5W'), MARGIN.index('5W') + 2])
        self.assertEqual(check_report(r, q, self.cards), r)

    def test_tampered_labels_or_summaries_fail_the_replay(self):
        q = request(MARGIN)
        r = self.agent(model(quantities=[dict(id=ids(MARGIN)['5W'], field='tx_power_dbm')])).run(q)
        def label_of(report):
            return next(a for d in report['diagnostics'] if d['code'] == 'MODEL_CALL'
                        for a in d['details']['accepted'] if a['kind'] == 'quantity')
        for change, code in [(dict(value=50.0), 'LABEL_NOT_GROUNDED'),
                             (dict(field='rx_power_dbm'), 'PARAMETER_SOURCE_MISMATCH')]:
            with self.subTest(code=code):
                bad = copy.deepcopy(r)
                label_of(bad).update(change)
                with self.assertRaisesRegex(ValueError, code):
                    check_report(bad, q, self.cards)
        bad = copy.deepcopy(r)
        bad['requirement'] = dict(quantity='link_margin_db', op='>=', value=10.0, unit='dB', span=[0, 1])
        with self.assertRaisesRegex(ValueError, 'LABEL_SUMMARY_MISMATCH'):
            check_report(bad, q, self.cards)

    def test_disagreeing_labels_become_a_question(self):
        text = f'按自由空间基准计算链路余量：频率2GHz，距离10km，发射功率30dBm，{REST}，预留余量10dB。'
        q = request(text)
        r = self.agent(model(quantities=[dict(id=ids(text)['30dBm'], field='rx_threshold_dbm')])).run(q)
        self.assertEqual(r['execution_status'], 'AWAITING_INPUT')
        self.assertIn('LABEL_CONFLICT', [d['code'] for d in r['diagnostics']])
        issues = issues_for(dict(status=r['execution_status'], report=r))
        conflict = next(i for i in issues if i['title'] == '原文数值的含义不一致')
        self.assertIn('规则判断为发射功率', conflict['detail'])
        self.assertEqual(check_report(r, q, self.cards), r)

    def test_a_margin_bound_is_a_requirement_only_when_labelled(self):
        text = f'按自由空间基准计算链路余量：频率2GHz，距离10km，发射功率30dBm，{REST}，预留余量0dB，余量至少10dB。'
        q = request(text)
        deterministic = self.agent(False).run(q)
        self.assertIn('INPUT_PARSE_ISSUE', [d['code'] for d in deterministic['diagnostics']])
        self.assertNotEqual(deterministic['execution_status'], 'AWAITING_CONFIRMATION')
        bound = [x for x in find_quantities(text) if x['comparison']][0]['id']
        r = self.agent(model(quantities=[dict(id=bound, field='required_margin_db')])).run(q)
        self.assertEqual(r['execution_status'], 'AWAITING_CONFIRMATION')
        self.assertEqual(r['requirement']['value'], 10.0)
        self.assertEqual(check_report(r, q, self.cards), r)
        # A bound can never become a parameter value.
        r = self.agent(model(quantities=[dict(id=bound, field='reserve_db')])).run(q)
        self.assertEqual(r['component_modes']['interpretation'], 'deterministic')
        self.assertEqual(r['runtime_health'], 'degraded')

    def test_unknown_quantity_ids_are_retried_then_dropped(self):
        fake = model(quantities=[dict(id='q99', field='frequency_ghz')])
        r = self.agent(fake).run(request(DEMO))
        self.assertEqual(len(fake.calls), 3)
        self.assertEqual(r['component_modes']['interpretation'], 'deterministic')
        self.assertEqual((r['requirement'], r['solve'], r['entities']), (None, None, []))

    def test_a_mention_must_be_in_the_text(self):
        fake = model(sites=[dict(mention='C站', evidence=CLAUSE), dict(mention='A站', evidence=CLAUSE)])
        r = self.agent(fake).run(request(DEMO))
        # An invented name is dropped and recorded; the rest of the answer stands.
        self.assertEqual(r['component_modes']['interpretation'], 'stub')
        self.assertEqual([e['mention'] for e in r['entities']], ['A 站'])
        dropped = next(d for d in r['diagnostics'] if d['code'] == 'MODEL_LABEL_DROPPED')
        self.assertEqual(dropped['details']['items'][0]['mention'], 'C站')
        # A wrong clause is only a pointer; the mention itself is found where it is.
        text = '从A站打到B站，XX-100，2GHz，余量得有10个dB，够不够？'
        r = self.agent(model(devices=[dict(mention='XX-100', evidence='从A站打到B站')])).run(request(text))
        self.assertEqual(r['entities'], [dict(kind='device', mention='XX-100', span=[text.index('XX-100'), text.index('XX-100') + 6])])
        # "A到B两个站" names the sites without the word 站 after each letter.
        text = 'A到B两个站，XX-100电台，2GHz频点，余量不低于10dB，够用吗？'
        r = self.agent(model(sites=[dict(mention='A站', evidence='A到B两个站'), dict(mention='B站', evidence='A到B两个站')])).run(request(text))
        self.assertEqual([e['mention'] for e in r['entities']], ['A', 'B'])

    def test_a_solve_request_is_found_in_the_quoted_sentence(self):
        text = '想用XX-100把A站和B站连起来，2GHz，余量要10dB，能通吗？如果不能，发射功率至少多大？'
        r = self.agent(model(solve=[dict(unknown='tx_power_dbm', evidence='如果不能')])).run(request(text))
        a, b = r['solve']['span']
        self.assertEqual(text[a:b], '发射功率至少多大')
        # Without any power question in that sentence, the request is dropped, not guessed.
        r = self.agent(model(solve=[dict(unknown='tx_power_dbm', evidence='能通吗')])).run(request(text))
        self.assertIsNone(r['solve'])

    def test_an_a_not_a_question_is_not_a_negation(self):
        text = 'B站和A站之间用XX-100通信，工作频率2GHz，要求链路余量不低于10dB，能不能通？'
        r = self.agent(model(targets=[dict(id='link_margin', evidence='能不能通')])).run(request(text))
        self.assertEqual(r['component_modes']['interpretation'], 'stub')
        self.assertEqual(r['targets'], ['link_margin'])

    def test_a_requirement_label_on_a_reserve_is_a_conflict(self):
        text = f'按自由空间基准计算链路余量：频率2GHz，距离10km，发射功率30dBm，{REST}，预留余量10dB。'
        q = request(text)
        reserve = [x for x in find_quantities(text) if x['text'] == '10dB'][-1]['id']
        r = self.agent(model(quantities=[dict(id=reserve, field='required_margin_db')])).run(q)
        self.assertEqual(r['execution_status'], 'AWAITING_INPUT')
        conflict = next(d for d in r['diagnostics'] if d['code'] == 'LABEL_CONFLICT')
        self.assertEqual(conflict['details']['rule_fields'], ['reserve_db'])
        issue = next(i for i in issues_for(dict(status=r['execution_status'], report=r)) if i['kind'] == 'conflict')
        self.assertIn('模型判断为余量要求', issue['detail'])
        self.assertEqual(check_report(r, q, self.cards), r)

    def test_feasibility_questions_mean_link_margin_only(self):
        validate_target_semantics(dict(targets=[dict(id='link_margin', evidence='能通吗')]))
        with self.assertRaisesRegex(ValueError, 'MODEL_TARGET_SEMANTICS'):
            validate_target_semantics(dict(targets=[dict(id='fspl_ghz', evidence='能通吗')]))


class PromptTests(unittest.TestCase):
    def test_demo_prompt_fits_the_4b_context_and_offers_the_quantities(self):
        cards = [c for c in load_catalog(ROOT) if c['id'] in {'fspl_ghz', 'received_power', 'link_margin'}]
        seen = {}
        def fake_chat(payload, *args, **kwargs):
            seen['payload'] = payload
            return {'model': 'stub'}, json.dumps(dict(selected_ids=[], targets=[], conditions=[], quantities=[],
                                                       solve=[], sites=[], devices=[]))
        with mock.patch('formula_rag.model.chat', fake_chat):
            LocalSelector()(DEMO, cards, quantities=find_quantities(DEMO), label_fields=LABEL_FIELDS,
                            solve_unknowns=SOLVE_UNKNOWNS)
        payload = seen['payload']
        self.assertLessEqual(estimate_tokens(payload), 4096)
        self.assertIn('数量表：q1=2 GHz；q2=10 dB', payload['messages'][-1]['content'])
        schema = payload['response_format']['json_schema']['schema']['properties']
        self.assertEqual(schema['quantities']['items']['properties']['id']['enum'], ['q1', 'q2'])
        self.assertIn('不能的话发射功率至少要多大', schema['solve']['items']['properties']['evidence']['enum'])


if __name__ == '__main__':
    unittest.main()
