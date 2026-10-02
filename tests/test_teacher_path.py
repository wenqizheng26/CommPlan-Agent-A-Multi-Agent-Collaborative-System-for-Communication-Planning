"""The teacher's link-margin path (TEACHER_CASES): modulation table, calc_link_margin, comparison."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from planning.services import calculation
from planning.requirements_contract import digest
from planning.workflow.task_service import TaskService
from test_calculation_plans import ROOT, MARGIN, command

CASES = {c['id']: c for c in map(json.loads, (ROOT / 'tests/eval/teacher_cases.jsonl').read_text(encoding='utf-8').splitlines())}
# Without the model the rules bind a gain only when it is labelled as one.
TEXT3 = CASES['teacher_03']['text'].replace('天线 12dBi', '天线增益 12dBi')
ROW = ('rx_sensitivity_dbm', 'path_loss_db', 'rx_power_dbm', 'link_margin_db', 'meets')


def manual(text, target='link_margin'):
    return dict(input=dict(raw_text=text, manual_parameters={}, condition=None, target=target))


class TeacherPathTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.service = TaskService(ROOT, Path(tmp.name) / 'tasks.sqlite')

    def run_case(self, case_id, **changes):
        draft = self.service.apply(command(text=TEXT3 if case_id == 'teacher_03' else CASES[case_id]['text'], **changes))['state']
        self.assertEqual(draft['status'], CASES[case_id]['expected']['first_stop'], draft['report']['questions'])
        return draft, self.service.apply(command('confirm', draft))['state']

    def assert_rows(self, rows, expected):
        self.assertEqual([r['modulation'] if 'modulation' in r else r['label'] for r in rows], [r['modulation'] for r in expected])
        for got, want in zip(rows, expected):
            for key in ROW:
                if key == 'meets':
                    self.assertEqual(got[key], want[key])
                else:
                    self.assertAlmostEqual(got[key], want[key], delta=1e-9)

    def test_case_one_runs_as_calc_link_margin_with_the_qpsk_sensitivity(self):
        draft, done = self.run_case('teacher_01')
        report = draft['report']
        plan = report['calculation_plan_proposal']
        self.assertEqual((plan['selected_model'], plan['tool']), (['fspl_mhz', 'received_power', 'link_margin'], 'calc_link_margin'))
        self.assertEqual(report['conditions'], ['free_space'])
        params = {p['canonical_name']: p for p in report['parameters_proposal']}
        self.assertEqual([(o['kind'], o['source_ref']) for o in params['rx_threshold_dbm']['origins']],
                         [('modulation', 'modulation:qpsk#rx_sensitivity_dbm')])
        self.assertTrue(all(params[n]['value'] == 0 and params[n]['origins'][0]['source_ref'] == 'tool:calc_link_margin#' + n
                            for n in ('tx_loss_db', 'rx_loss_db', 'extra_loss_db', 'reserve_db')))
        self.assertEqual(done['status'], 'COMPLETED', done.get('failure'))
        [call] = done['final_report']['tool_calls']
        self.assertEqual((call['label'], call['status'], call['result']['sensitivity_source']), ('QPSK', 'ok', 'modulation_table'))
        self.assert_rows([dict(call['result'], label='QPSK')], CASES['teacher_01']['expected']['results'])
        self.assertEqual(done['result']['outputs'][0]['value'], call['result']['link_margin_db'])
        self.assertNotIn('comparison', done['final_report'])
        tools = [e['details'] for e in self.service.activity.events(done['task_id']) if e['node'] == 'tool']
        self.assertEqual([t['tool_id'] for t in tools], ['fspl_mhz', 'received_power', 'link_margin', 'calc_link_margin'])
        self.assertEqual([s['card'] for s in tools[-1]['steps']], ['fspl_mhz', 'received_power', 'link_margin'])
        self.assertEqual((tools[-1]['label'], tools[-1]['arguments']['frequency_mhz']), ('QPSK', 5800))

    def test_case_three_compares_the_modulations_and_recommends_the_largest_margin(self):
        expected = CASES['teacher_03']['expected']
        draft, done = self.run_case('teacher_03', **manual(TEXT3))
        plan = draft['report']['calculation_plan_proposal']
        self.assertEqual([v['label'] for v in plan['variants']], ['16QAM'])
        self.assertEqual(done['status'], 'COMPLETED', done.get('failure'))
        comparison = done['final_report']['comparison']
        self.assert_rows(comparison['rows'], expected['results'])
        self.assertAlmostEqual(comparison['margin_diff_db'], expected['margin_diff_db'], delta=1e-9)
        self.assertEqual(comparison['recommend'], expected['recommend'])
        self.assertEqual([c['label'] for c in done['final_report']['tool_calls']], ['QPSK', '16QAM'])
        self.assertIn('QPSK 余量最大', done['final_report']['conclusion'])

    def test_an_unknown_modulation_is_a_choice_that_replaces_it_in_the_text(self):
        text = '计算链路余量：距离10公里，频率5.8GHz，发射功率20dBm，发射天线增益18dBi，接收天线增益18dBi，使用8PSK。'
        draft = self.service.apply(command(text=text))['state']
        self.assertEqual(draft['status'], 'AWAITING_INPUT')
        [issue] = draft['input_issues']
        self.assertEqual((issue['field'], issue['kind'], issue['excerpt']), ('modulation', 'choice', '8PSK'))
        answered = self.service.apply(command('answer', draft, answers={issue['id']: '16QAM'}))['state']
        self.assertEqual(answered['status'], 'AWAITING_CONFIRMATION', answered['report']['questions'])
        self.assertIn('使用16QAM', answered['request']['raw_text'])
        done = self.service.apply(command('confirm', answered))['state']
        self.assertAlmostEqual(done['result']['outputs'][0]['value'], 23.291440128741257, delta=1e-9)

    def test_stated_losses_and_named_radios_keep_the_general_budget(self):
        draft = self.service.apply(command(text=MARGIN))['state']
        plan = draft['report']['calculation_plan_proposal']
        self.assertEqual(plan['selected_model'], ['fspl_ghz', 'received_power', 'link_margin'])
        self.assertNotIn('tool', plan)
        radio = self.service.apply(command(text='按自由空间基准计算链路余量：A站到B站用 XX-100，频率2GHz，距离10km。'))['state']
        plan = radio['report']['calculation_plan_proposal']
        self.assertEqual(plan['selected_model'][0], 'fspl_ghz')
        self.assertNotIn('tool', plan)

    def test_a_changed_tool_result_fails_validation(self):
        _, done = self.run_case('teacher_03', **manual(TEXT3))
        snapshot = done['confirmed_snapshot']
        for path in (('tool_calls', 1, 'result', 'link_margin_db'), ('comparison', 'recommend')):
            result = copy.deepcopy(done['result'])
            target = result
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = 99 if path[-1] != 'recommend' else '16QAM'
            result['result_hash'] = digest({k: v for k, v in result.items() if k != 'result_hash'})
            failed = [v['validator_id'] for v in calculation.validate_result(result, snapshot) if not v['passed']]
            self.assertEqual(failed, ['link_tool'], path)

    def test_case_two_lists_the_gaps_with_table_suggestions_that_one_answer_adopts(self):
        text = CASES['teacher_02']['text']
        draft = self.service.apply(command(text=text, **manual(text)))['state']
        self.assertEqual(draft['status'], 'AWAITING_INPUT')
        found = draft['report']['suggestions']
        self.assertEqual(found['mode'], 'deterministic')
        self.assertEqual({x['field']: x['value'] for x in found['items']},
                         dict(distance_km=10, tx_power_dbm=20, tx_gain_dbi=18, rx_gain_dbi=18, modulation='QPSK'))
        issues = {i['field']: i for i in draft['input_issues']}
        self.assertEqual(set(issues), {'distance_km', 'tx_power_dbm', 'tx_gain_dbi', 'rx_gain_dbi', 'modulation'})
        self.assertEqual(issues['tx_power_dbm']['suggestion']['value'], '20dBm')
        self.assertEqual(issues['modulation']['suggestion']['note'], '默认补全，需确认')
        answers = {i['id']: i['suggestion']['value'] for i in issues.values()}
        state = self.service.apply(command('answer', draft, answers=answers))['state']
        self.assertEqual(state['status'], 'AWAITING_CONFIRMATION', state['report']['questions'])
        for line in ('路径距离10km（默认补全）', '发射功率20dBm（默认补全）', '调制方式 QPSK（默认补全）'):
            self.assertIn(line, state['request']['raw_text'])
        turn = state['conversation']['turns'][-1]
        self.assertEqual((turn['kind'], turn['mode']), ('answer', 'suggestion'))
        self.assertTrue(all(a['suggested'] for a in turn['answers']))
        self.assertNotIn('suggestions', state['report'])
        done = self.service.apply(command('confirm', state))['state']
        self.assert_rows([dict(done['final_report']['tool_calls'][0]['result'], label='QPSK')], CASES['teacher_02']['expected']['results'])

    def test_a_typed_value_is_not_marked_as_a_default(self):
        text = CASES['teacher_02']['text']
        draft = self.service.apply(command(text=text, **manual(text)))['state']
        issue = next(i for i in draft['input_issues'] if i['field'] == 'tx_power_dbm')
        state = self.service.apply(command('answer', draft, answers={issue['id']: '23dBm'}))['state']
        self.assertIn('发射功率23dBm', state['request']['raw_text'])
        self.assertNotIn('（默认补全）', state['request']['raw_text'])
        self.assertEqual(state['conversation']['turns'][-1]['mode'], 'user_answer')

    def test_one_gain_written_for_both_ends_is_each_ends_gain(self):
        # Without the model the rules read a distance only after a label such as "距离".
        for case_id, gain in (('variant_04', 18), ('variant_06', 12)):
            draft, done = self.run_case(case_id, **manual(CASES[case_id]['text'].replace('：10公里', '：距离10公里')))
            params = {p['canonical_name']: p for p in draft['report']['parameters_proposal']}
            tx, rx = params['tx_gain_dbi'], params['rx_gain_dbi']
            self.assertEqual((tx['value'], rx['value']), (gain, gain))
            self.assertEqual(tx['origins'][0]['span'], rx['origins'][0]['span'])
            self.assertEqual(done['status'], 'COMPLETED', done.get('failure'))
            self.assert_rows([dict(c['result'], label=c['label']) for c in done['final_report']['tool_calls']],
                             CASES[case_id]['expected']['results'])
        from planning.services.requirement_parameters import BOTH_GAINS
        self.assertFalse(BOTH_GAINS.search('发射天线增益18dBi，接收天线增益12dBi'))
        self.assertFalse(BOTH_GAINS.search('距离和两端天线增益都还不确定'))

    def test_a_bare_letter_is_a_label_and_leaves_the_distance_open(self):
        from formula_rag.catalog import load_catalog
        from planning.services.requirement_facts import sources_for
        text = CASES['missing_05']['text']
        request = dict(raw_text=text, manual_parameters={}, request_id='r')
        entities = [dict(kind='site', mention=m, span=[text.index(m), text.index(m) + 1]) for m in ('A', 'B')]
        facts = sources_for(request, entities, load_catalog(ROOT), 'link_margin', {'frequency_ghz', 'tx_power_dbm'}, ROOT)
        self.assertEqual((facts['tool'], facts['sites'], facts['labels']), ('calc_link_margin', [], ['A', 'B']))
        self.assertNotIn('slant_range_wgs84', facts['order'])
        self.assertIn('distance_km', facts['leaves'])
        self.assertFalse(any(o['kind'] == 'site' for origins in facts['sources'].values() for o in origins))
        named = [dict(e, mention=m) for e, m in zip(entities, ('A站', 'B岛站'))]
        written = sources_for(dict(request, raw_text='A站到B岛站，' + text), named, load_catalog(ROOT), 'link_margin',
                              {'frequency_ghz', 'tx_power_dbm'}, ROOT)
        self.assertEqual([s['id'] for s in written['sites']], ['site:sim-a', 'site:sim-b'])
        self.assertIn('slant_range_wgs84', written['order'])

    def test_stability_and_video_wording_is_evidence_for_the_link_margin(self):
        from formula_rag.interpretation import merge_interpretation
        text = CASES['teacher_02']['text']
        for evidence in ('要稳定', '传视频'):
            request = dict(text=text, conditions=[], targets=[])
            info = merge_interpretation(request, dict(targets=[dict(id='link_margin', evidence=evidence)]), {'link_margin'})
            self.assertEqual((request['targets'], info['target_origin']), (['link_margin'], 'model'))

    def test_the_suggestion_prompt_keeps_numeric_defaults_unless_the_text_asks_for_that_input(self):
        from planning.services.suggestions import PROMPT
        self.assertIn('距离、功率和天线增益取 default', PROMPT)
        self.assertIn('只用来选调制方式', PROMPT)

    def test_the_model_picks_a_candidate_with_a_reason_and_a_bad_pick_falls_back_to_the_table(self):
        from planning.agents.requirements import RequirementsAgent
        from planning.services.suggestions import suggestions_for
        text = CASES['teacher_02']['text']
        request = dict(schema_version='1.0.0', task_id='t', revision=0, request_id='r', raw_text=text,
                       manual_parameters={}, condition=None, target='link_margin')
        report = RequirementsAgent(ROOT, selector=False).run(request)

        def selector(picks):
            def call(role, prompt, view, schema):
                self.assertEqual(role, 'suggest')
                items = [dict(field=o['field'], value=picks.get(o['field'], o['default']), reason='要稳定，选抗干扰强的低阶调制'
                              if o['field'] == 'modulation' else '典型取值') for o in view['open']]
                return dict(output=dict(items=items), raw_output='', model='stub', usage={})
            return call
        found = suggestions_for(request, report, ROOT, selector({'tx_power_dbm': '23'}))
        self.assertEqual(found['mode'], 'stub')
        picked = {x['field']: x for x in found['items']}
        self.assertEqual((picked['tx_power_dbm']['value'], picked['modulation']['reason']), (23, '要稳定，选抗干扰强的低阶调制'))
        fallback = suggestions_for(request, report, ROOT, selector({'tx_power_dbm': '25'}))
        self.assertEqual(fallback['mode'], 'deterministic_fallback')
        self.assertEqual({x['field']: x['reason'] for x in fallback['items']}['tx_power_dbm'], '典型值表的默认值')

    def test_the_review_sees_the_comparison_and_may_explain_it_with_its_numbers(self):
        from planning.agents.review import ReviewAgent, facts_for
        _, done = self.run_case('teacher_03', **manual(TEXT3))
        facts = facts_for(done['result'], done['confirmed_snapshot'], done['validations'])
        c = facts['comparison']
        self.assertEqual([(r['modulation'], r['rx_sensitivity']['value'], r['link_margin']['value']) for r in c['rows']],
                         [('QPSK', -100, 22.894), ('16QAM', -95, 17.894)])
        self.assertEqual((c['difference']['value'], c['recommend']['modulation']), (5.0, 'QPSK'))
        threshold = next(i for i in facts['inputs'] if i['id'] == 'in:rx_threshold_dbm')
        self.assertEqual(threshold['source'], '调制表（模拟参数） QPSK')
        answer = ('推荐 QPSK：余量 22.89 dB，16QAM 为 17.89 dB，相差 5.00 dB。两者接收电平都是 -77.11 dBm，'
                  '16QAM 阶数更高、灵敏度 -95 dBm 高于 QPSK 的 -100 dBm，余量因此更小。')
        def selector(role, prompt, view, schema):
            self.assertIn('comparison', schema['properties']['opinions']['items']['properties']['refs']['items']['enum'])
            return dict(output=dict(decision='pass', answer=answer, opinions=[], steps=[]), raw_output='', model='stub', usage={})
        assessment = ReviewAgent(selector).run(done['result'], done['confirmed_snapshot'])
        self.assertEqual((assessment['role']['mode'], assessment['role']['proposal']['answer']), ('stub', answer))

    def test_the_review_prompt_speaks_of_a_higher_threshold_not_a_higher_sensitivity(self):
        from planning.agents.review import PROMPT
        self.assertIn('所需的接收门限越高', PROMPT)
        self.assertNotIn('接收灵敏度越高', PROMPT)


class ServiceLabelTests(unittest.TestCase):
    """Case two names a service ("传视频"): the report keeps it as a label from the text, never as an input."""

    def test_the_named_service_is_read_from_the_text_and_negations_are_not(self):
        from planning.services.requirement_policy import service_label
        text = CASES['teacher_02']['text']
        start = text.index('传视频')
        self.assertEqual(service_label(text), dict(kind='video', label='视频', mention='传视频', span=[start, start + 3]))
        for text, label in [('用于视频监控', '视频'), ('语音通话要稳定', '语音'), ('数据传输要稳定', '数据'),
                            ('transmit data over 10 km', '数据'), ('a 5.8 GHz video link', '视频'),
                            ('不需要传视频，只算余量', None), ('without HD video, compute the margin', None),
                            ('看下数据手册', None), ('The data shows 3 dB', None), ('now stream video over 8 km', '视频'), (CASES['teacher_01']['text'], None)]:
            self.assertEqual((service_label(text) or {}).get('label'), label, text)

    def test_negation_and_contrast_name_the_service_asked_for_and_mixed_requests_get_no_label(self):
        from planning.services.requirement_policy import service_label
        for text, label in [('不是视频业务，是语音通话', '语音'), ('不需要任何视频业务，只传数据', '数据'),
                            ('视频不用传，语音就行', '语音'), ('not video but voice traffic', '语音'),
                            ('视频就不用了，传数据', '数据'), ('video is not needed, voice only', '语音'),
                            ('不考虑视频', None), ('视频暂不需要', None), ('不卡顿地传视频', '视频'),
                            # Several services asked for at once: no single label is reliable.
                            ('传视频和语音', None), ('语音通话，也要传数据', None)]:
            self.assertEqual((service_label(text) or {}).get('label'), label, text)

    def test_the_contract_rejects_a_service_label_outside_the_list(self):
        from planning.requirements_contract import validate_report
        with tempfile.TemporaryDirectory() as tmp:
            draft = TaskService(ROOT, Path(tmp) / 'tasks.sqlite').apply(command(text=CASES['teacher_02']['text']))['state']
        validate_report(draft['report'], draft['request'])
        for kind, label in [('radar', '雷达'), (None, None), ([], '视频'), ('video', None)]:
            bad = copy.deepcopy(draft['report'])
            bad['service'].update(kind=kind, label=label)
            with self.assertRaisesRegex(ValueError, 'SERVICE_LABEL', msg=repr(kind)):
                validate_report(bad, draft['request'])

    def test_case_two_report_carries_the_label_and_the_check_replays_it(self):
        from formula_rag.catalog import load_catalog
        from planning.services.requirement_validation import check_report
        with tempfile.TemporaryDirectory() as tmp:
            draft = TaskService(ROOT, Path(tmp) / 'tasks.sqlite').apply(command(text=CASES['teacher_02']['text']))['state']
        report, request, cards = draft['report'], draft['request'], load_catalog(ROOT)
        self.assertEqual((report['service']['kind'], report['service']['mention']), ('video', '传视频'))
        self.assertNotIn('service', {p['canonical_name'] for p in report['parameters_proposal']})
        check_report(report, request, cards, ROOT)
        # A report saved before the label existed still checks; a changed label does not.
        check_report({k: v for k, v in report.items() if k != 'service'}, request, cards, ROOT)
        changed = copy.deepcopy(report)
        changed['service'].update(kind='voice', label='语音')
        with self.assertRaisesRegex(ValueError, 'SERVICE_LABEL_MISMATCH'):
            check_report(changed, request, cards, ROOT)
        changed['service'].update(kind='video', label='语音')
        with self.assertRaisesRegex(ValueError, 'SERVICE_LABEL'):
            check_report(changed, request, cards, ROOT)


if __name__ == '__main__':
    unittest.main()
