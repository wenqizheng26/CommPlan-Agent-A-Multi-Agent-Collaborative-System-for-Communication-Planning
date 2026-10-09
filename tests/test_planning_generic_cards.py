import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from formula_rag.catalog import load_catalog
from planning.agents.requirements import RequirementsAgent
from planning.requirements_contract import digest
from planning.services.card_units import convert_unit
from planning.services.generic_cards import quantities, validate_bindings
from planning.services.requirement_validation import check_report
from planning.services.calculation import validate_result
from planning.workflow.task_service import TaskService
from tests.test_planning_loop import command

ROOT=Path(__file__).resolve().parents[1]
CASES=[
    ('doppler_max','计算单程最大多普勒频移上界，载波频率2GHz，相对速度36km/h',
     '计算单程最大多普勒频移上界，载波频率2GHz','speed_kmh','36km/h',66.7128190396304),
    ('thermal_noise','计算热噪声功率，温度290K，带宽1MHz',
     '计算热噪声功率，温度290K','bandwidth_hz','1MHz',-113.97518719422808),
    ('noise_density','计算热噪声谱密度，温度290K',
     '计算热噪声谱密度','temperature_k','290K',-173.97518719422808),
    ('radio_horizon','计算无线电视距，第一端天线高度30m，第二端天线高度25m',
     '计算无线电视距，第一端天线高度30m','antenna2_m','25m',43.16616936921285),
]

class GenericCardTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        shutil.copytree(ROOT/'knowledge',self.root/'knowledge')
        shutil.copytree(ROOT/'config',self.root/'config')
        from tests.teacher_fixtures import copy_teacher_dependencies
        copy_teacher_dependencies(self.root)
        shutil.copy(ROOT/'runtime_config.json',self.root/'runtime_config.json')
        self.db=self.root/'tasks.sqlite'
        self.service=TaskService(self.root,self.db)

    def create(self,text,target=None,manual=None):
        c=command(text=text)
        c['input'].update(target=target,manual_parameters=manual or {})
        return self.service.apply(c)['state']

    def add_wavelength(self,title='自由空间波长',identifier='wavelength_free_space'):
        from planning.knowledge.drafts import DraftStore
        from tests.test_planning_formula_card_drafts import manual
        record=manual(identifier)
        record.update(title=title,expression='0.299792458/frequency_ghz',
            parameters=dict(frequency_ghz=dict(unit='GHz',description='载波频率',exclusive_min=0)),
            output=dict(name='wavelength_m',unit='m'))
        store=DraftStore(self.root)
        draft=store.create_manual('formula',record)
        store.review(draft['id'],'Reviewer',draft['content_hash'],'approve',source=dict(title='测试资料',locator='波长公式'),
            example=dict(inputs=dict(frequency_ghz=2),expected=.149896229,note='独立算例'))
        self.service.refresh_knowledge()

    def test_exact_new_card_title_precedes_old_keywords_and_retains_conflicts(self):
        for title in ['自由空间波长','路径损耗换算波长','接收电平示例波长']:
            with self.subTest(title=title):
                identifier='wavelength_'+str(len(load_catalog(self.root)))
                self.add_wavelength(title,identifier)
                s=self.create('计算'+title+'，载波频率2GHz。')
                self.assertEqual(s['status'],'AWAITING_CONFIRMATION',s.get('input_issues'))
                self.assertEqual(s['report']['targets'],[identifier])
                done=self.service.apply(command('confirm',s))['state']
                self.assertEqual(done['status'],'COMPLETED')
                self.assertAlmostEqual(done['result']['outputs'][0]['value'],.149896229)

    def test_independent_old_and_new_goals_are_not_silently_selected(self):
        self.add_wavelength()
        for text in ['计算自由空间波长和路径损耗，载波频率2GHz，距离1km',
                     '计算自由空间波长，载波频率2GHz；求路径损耗，距离1km']:
            s=self.create(text)
            self.assertEqual(s['status'],'AWAITING_INPUT')
            self.assertIn('INTENT_CONFLICT',[d['code'] for d in s['report']['diagnostics']])
            self.assertTrue(any(i['kind']=='conflict' for i in s['input_issues']))

    def test_manual_dedicated_goal_conflict_is_rechecked_at_confirmation(self):
        self.add_wavelength()
        s=self.create('按自由空间基准，计算自由空间波长，载波频率2GHz，距离1km',target='fspl_ghz')
        self.assertEqual(s['status'],'AWAITING_INPUT')
        self.assertIn('INTENT_CONFLICT',[d['code'] for d in s['report']['diagnostics']])
        good=self.create('按自由空间基准，计算路径损耗，载波频率2GHz，距离1km',target='fspl_ghz')
        self.assertEqual(good['status'],'AWAITING_CONFIRMATION')
        changed=copy.deepcopy(good['request'])
        changed['raw_text']+='；计算自由空间波长'
        with self.assertRaisesRegex(ValueError,'INTENT_CONFLICT'):
            check_report(good['report'],changed,load_catalog(self.root),self.root)

    def test_builtin_duplicate_title_keeps_dedicated_path_and_choice_is_unique(self):
        from planning.services.generic_cards import choices
        self.assertNotIn('fspl_mhz',{r['value'] for r in choices(self.root)})
        s=self.create('按自由空间基准，计算自由空间基本传输损耗，频率2GHz，距离1km')
        self.assertEqual(s['status'],'AWAITING_CONFIRMATION')
        self.assertNotIn('generic_card',s['report'])

    def test_generic_conclusion_and_answer_use_product_labels(self):
        s=self.create(CASES[1][2])
        issue=next(i for i in s['input_issues'] if i['field']==CASES[1][3])
        s=self.service.apply(command('answer',s,answers={issue['id']:CASES[1][4]},mode='deterministic'))['state']
        self.assertNotIn('bandwidth_hz=',s['request']['raw_text'])
        self.assertIn('噪声等效带宽',s['request']['raw_text'])
        done=self.service.apply(command('confirm',s))['state']
        self.assertIn('热噪声功率',done['final_report']['conclusion'])
        self.assertNotIn('thermal_noise_dbm',done['final_report']['conclusion'])

    def test_answered_parameter_labels_with_same_prefix_rebind_to_exact_field(self):
        from planning.knowledge.drafts import DraftStore
        from tests.test_planning_formula_card_drafts import manual
        record=manual('two_lengths')
        record.update(title='两端长度和',expression='a+b',
            parameters=dict(a=dict(unit='m',description='长度，第一端'),
                            b=dict(unit='m',description='长度，第二端')),
            output=dict(name='length_m',unit='m'))
        store=DraftStore(self.root)
        d=store.create_manual('formula',record)
        store.review(d['id'],'Reviewer',d['content_hash'],'approve',source=dict(title='核查资料',locator='式1'),
            example=dict(inputs=dict(a=1,b=2),expected=3,note='独立算例'))
        self.service.refresh_knowledge()
        s=self.create('计算两端长度和，a=1m，a=2m，b=3m')
        issue=next(i for i in s['input_issues'] if i['field']=='a')
        s=self.service.apply(command('answer',s,answers={issue['id']:'10m'},mode='deterministic'))['state']
        self.assertEqual(s['status'],'AWAITING_CONFIRMATION',s['input_issues'])
        self.assertIn('长度（参数 a） 10 m',s['request']['raw_text'])
        done=self.service.apply(command('confirm',s))['state']
        self.assertEqual(done['status'],'COMPLETED')
        self.assertEqual(done['result']['outputs'][0]['value'],13)

    def test_four_targets_only_execute_after_confirmation_and_recover(self):
        for ident,text,_,_,_,expected in CASES:
            with self.subTest(ident=ident):
                s=self.create(text)
                self.assertEqual(s['status'],'AWAITING_CONFIRMATION',s.get('failure'))
                self.assertIsNone(s['result'])
                self.service=TaskService(self.root,self.db)
                done=self.service.apply(command('confirm',s))['state']
                self.assertEqual(done['status'],'COMPLETED',done.get('failure'))
                result=done['result']
                self.assertEqual(result['calculation_mode'],'generic_card')
                self.assertEqual(result['card']['id'],ident)
                self.assertAlmostEqual(result['outputs'][0]['value'],expected,places=8)
                self.assertFalse(result['verification']['independent_model'])
                self.assertTrue(all(v['passed'] for v in done['validations']))
                self.assertNotIn('independent_magnitude',[v['validator_id'] for v in done['validations']])
                self.assertEqual(done['final_report']['calculation_mode'],'generic_card')
                self.assertIn('无独立复核模型',''.join(done['final_report']['limitations']))

    def test_four_missing_parameters_can_be_answered_then_confirmed(self):
        for ident,_,text,field,answer,_ in CASES:
            with self.subTest(ident=ident):
                s=self.create(text)
                self.assertEqual(s['status'],'AWAITING_INPUT')
                issue=next(i for i in s['input_issues'] if i['field']==field)
                s=self.service.apply(command('answer',s,answers={issue['id']:answer},mode='deterministic'))['state']
                self.assertEqual(s['status'],'AWAITING_CONFIRMATION',s.get('failure'))
                done=self.service.apply(command('confirm',s))['state']
                self.assertEqual(done['status'],'COMPLETED',done.get('failure'))

    def test_bounds_accept_zero_speed_but_reject_temperature_and_excessive_speed(self):
        good=self.create(CASES[0][1].replace('36km/h','0km/h'))
        self.assertEqual(good['status'],'AWAITING_CONFIRMATION')
        for text in [CASES[1][1].replace('290K','0K'),CASES[0][1].replace('36km/h','2000000km/h')]:
            s=self.create(text)
            self.assertEqual(s['status'],'AWAITING_INPUT')
            self.assertTrue(any(i['kind']=='PARAMETER_OUT_OF_RANGE' for i in s['input_issues']))

    def test_conflicting_originals_are_not_silently_overwritten(self):
        s=self.create(CASES[1][1]+'，温度300K')
        self.assertEqual(s['status'],'AWAITING_INPUT')
        issue=next(i for i in s['input_issues'] if i['field']=='temperature_k')
        s=self.service.apply(command('answer',s,answers={issue['id']:'310K'},mode='deterministic'))['state']
        self.assertEqual(s['status'],'AWAITING_CONFIRMATION')
        self.assertIn('thermal_noise',s['report']['targets'])
        self.assertNotIn('290K',s['request']['raw_text'])
        self.assertNotIn('300K',s['request']['raw_text'])

    def test_no_frequency_bandwidth_guess_and_unit_mismatch_is_question(self):
        s=self.create('计算热噪声功率，温度290K，载波频率1MHz')
        self.assertEqual(s['status'],'AWAITING_INPUT')
        self.assertIn('bandwidth_hz',s['report']['missing_parameters'])
        s=self.create('计算热噪声功率，温度290Hz，带宽1MHz')
        self.assertEqual(s['status'],'AWAITING_INPUT')
        self.assertIn('CARD_UNIT_MISMATCH',[d['code'] for d in s['report']['diagnostics']])

    def test_model_can_only_bind_existing_quantity_to_compatible_parameter(self):
        card=next(c for c in load_catalog(self.root) if c['id']=='thermal_noise')
        text='温度290K，带宽1MHz'
        qs=quantities(text)
        for bad in [{'bindings':[{'quantity_id':'q999','parameter':'temperature_k'}]},
                    {'bindings':[{'quantity_id':qs[1]['id'],'parameter':'temperature_k'}]},
                    {'bindings':[{'quantity_id':qs[0]['id'],'parameter':'temperature_k','value':300}]}]:
            with self.assertRaises(ValueError):
                validate_bindings(bad,text,card)

    def test_model_cannot_relabel_same_dimension_frequency_as_bandwidth(self):
        card=next(c for c in load_catalog(self.root) if c['id']=='thermal_noise')
        text='计算热噪声功率，温度290K，载波频率1MHz'
        with self.assertRaisesRegex(ValueError,'SOURCE_LABEL_MISMATCH'):
            validate_bindings({'bindings':[{'quantity_id':'q0','parameter':'temperature_k'},
                {'quantity_id':'q1','parameter':'bandwidth_hz'}]},text,card)

    def test_report_and_result_tampering_rejected_after_rehash(self):
        s=self.create(CASES[1][1])
        report=copy.deepcopy(s['report'])
        report['parameters_proposal'][0]['value']=300
        with self.assertRaises(ValueError):
            check_report(report,s['request'],load_catalog(self.root),self.root)
        done=self.service.apply(command('confirm',s))['state']
        result=copy.deepcopy(done['result'])
        result['outputs'][0]['value']+=1
        result['steps'][0]['output']['value']+=1
        result['result_hash']=digest({k:v for k,v in result.items() if k!='result_hash'})
        self.assertFalse(all(v['passed'] for v in validate_result(result,done['confirmed_snapshot'])))

    def test_registered_example_failure_prevents_publication(self):
        raw=json.loads((self.root/'knowledge/formulas.json').read_text(encoding='utf-8-sig'))
        card=next(c for c in raw if c['id']=='thermal_noise')
        card['examples'][0]['expected']+=20
        (self.root/'knowledge/formulas.json').write_text(json.dumps(raw),encoding='utf-8')
        s=self.create(CASES[1][1])
        done=self.service.apply(command('confirm',s))['state']
        self.assertEqual(done['status'],'FAILED')
        self.assertIsNone(done['final_report'])

    def test_disabled_target_and_changed_confirmation_blocked(self):
        from planning.knowledge.library import switch_card
        s=self.create(CASES[1][1])
        switch_card(self.root,'thermal_noise',False)
        with self.assertRaises(ValueError):
            self.service.apply(command('confirm',s))
        self.service.refresh_knowledge()
        s=self.create(CASES[1][1])
        self.assertEqual(s['status'],'NEEDS_MODEL')

    def test_generic_goal_choices_include_disabled_tools(self):
        s=self.create('频率2GHz')
        issue=next(i for i in s['input_issues'] if i['field']=='goal')
        rows={c['value']:c for c in issue['choices']}
        self.assertEqual(rows['thermal_noise']['group'],'generic')
        self.assertTrue(rows['slant_range_wgs84']['disabled'])
        s=self.service.apply(command('answer',s,answers={issue['id']:'thermal_noise'},mode='deterministic'))['state']
        self.assertEqual(s['status'],'AWAITING_INPUT')
        self.assertEqual(set(s['report']['missing_parameters']),{'temperature_k','bandwidth_hz'})

    def test_no_approximate_or_negated_value_silently_adopted(self):
        for text in ['计算热噪声功率，温度约290K，带宽1MHz',
                     '计算热噪声功率，温度不是290K，带宽1MHz',
                     '计算热噪声功率，温度290K或300K，带宽1MHz',
                     '计算热噪声功率，温度290K，带宽1MHz或2MHz',
                     '不计算热噪声功率，温度290K，带宽1MHz']:
            s=self.create(text)
            self.assertEqual(s['status'],'AWAITING_INPUT')

    def test_negative_chinese_temperature_is_not_read_as_positive(self):
        for token in ['负290K','−290K','-290K']:
            s=self.create('计算热噪声功率，温度'+token+'，带宽1MHz')
            self.assertEqual(s['status'],'AWAITING_INPUT')

    def test_postfix_bounds_require_exact_answer_and_recover(self):
        for suffix in ['以内','以下','以上','以外','不等','左右']:
            with self.subTest(suffix=suffix):
                s=self.create('计算热噪声功率，温度290K，带宽1MHz'+suffix)
                self.assertEqual(s['status'],'AWAITING_INPUT')
                issue=next(i for i in s['input_issues'] if i['field']=='bandwidth_hz')
                s=self.service.apply(command('answer',s,answers={issue['id']:'2MHz'},mode='deterministic'))['state']
                self.assertEqual(s['status'],'AWAITING_CONFIRMATION')

    def test_explicit_noise_target_conflicts_in_both_directions(self):
        for text,target in [('计算热噪声谱密度，温度290K，带宽1MHz','thermal_noise'),
                            ('计算热噪声功率，温度290K，带宽1MHz','noise_density')]:
            s=self.create(text,target=target)
            self.assertEqual(s['status'],'AWAITING_INPUT')
            self.assertIn('INTENT_CONFLICT',[d['code'] for d in s['report']['diagnostics']])

    def test_new_manual_card_and_multiple_conflicts_answered_without_offset_corruption(self):
        from planning.knowledge.drafts import DraftStore
        from tests.test_planning_formula_card_drafts import manual
        record=manual('sum_lengths')
        record.update(title='长度求和',expression='a+b',parameters={name:dict(unit='m',description=name) for name in ['a','b']},
                      output=dict(name='length_m',unit='m'))
        store=DraftStore(self.root)
        draft=store.create_manual('formula',record)
        store.review(draft['id'],'Reviewer',draft['content_hash'],'approve',source=dict(title='本机核查资料',locator='式1'),
            example=dict(inputs=dict(a=1,b=2),expected=3,note='独立核来算例'))
        self.service.refresh_knowledge()
        s=self.create('计算长度求和，a=1m，a=2m，b=3m，b=4m，保留正文')
        self.assertEqual(s['status'],'AWAITING_INPUT')
        answers={i['id']:('10m' if i['field']=='a' else '20m') for i in s['input_issues']}
        s=self.service.apply(command('answer',s,answers=answers,mode='deterministic'))['state']
        self.assertEqual(s['status'],'AWAITING_CONFIRMATION',s.get('failure'))
        self.assertIn('保留正文',s['request']['raw_text'])
        done=self.service.apply(command('confirm',s))['state']
        self.assertEqual(done['status'],'COMPLETED',done.get('failure'))
        self.assertEqual(done['result']['outputs'][0]['value'],30)
        self.assertEqual(done['report']['evidence_refs'][0]['source_id'],'card:sum_lengths#source:0')

    def test_rejected_quantities_can_be_replaced_once(self):
        for token in ['290K左右','290K或300K','290Hz','约290K','290K或300K或310K']:
            s=self.create('计算热噪声功率，温度'+token+'，带宽1MHz')
            issue=next(i for i in s['input_issues'] if i['field']=='temperature_k')
            s=self.service.apply(command('answer',s,answers={issue['id']:'320K'},mode='deterministic'))['state']
            self.assertEqual(s['status'],'AWAITING_CONFIRMATION',s.get('failure'))
            p=next(p for p in s['report']['parameters_proposal'] if p['canonical_name']=='temperature_k')
            self.assertEqual(p['value'],320)

    def test_dimensionless_unit_never_steals_last_digit(self):
        self.assertEqual(quantities('系数21'),[])
        self.assertEqual(quantities('系数2021'),[])
        self.assertEqual(quantities('系数2 1')[0]['value'],2)

    def test_dimensionless_answer_preserves_separator_through_confirm(self):
        from planning.knowledge.drafts import DraftStore
        from tests.test_planning_formula_card_drafts import manual
        record=manual('double_ratio')
        record.update(title='倍数',expression='ratio*2',parameters=dict(ratio=dict(unit='1',description='系数')),
                      output=dict(name='ratio_out',unit='1'))
        store=DraftStore(self.root)
        draft=store.create_manual('formula',record)
        store.review(draft['id'],'Reviewer',draft['content_hash'],'approve',source=dict(title='核查资料',locator='式1'),
            example=dict(inputs=dict(ratio=2),expected=4,note='独立算例'))
        self.service.refresh_knowledge()
        s=self.create('计算倍数')
        issue=next(i for i in s['input_issues'] if i['field']=='ratio')
        s=self.service.apply(command('answer',s,answers={issue['id']:'2 1'},mode='deterministic'))['state']
        self.assertEqual(s['status'],'AWAITING_CONFIRMATION')
        self.assertIn('系数 2 1',s['request']['raw_text'])
        done=self.service.apply(command('confirm',s))['state']
        self.assertEqual(done['status'],'COMPLETED',done.get('failure'))
        self.assertEqual(done['result']['outputs'][0]['value'],4)

    def test_h4_recognizes_all_registered_units_and_rejects_wrong_scale(self):
        from planning.services.card_units import UNITS
        from planning.services.number_check import known,unquoted,written
        for unit in UNITS:
            with self.subTest(unit=unit):
                parsed=written('结果为 2 '+unit)
                self.assertEqual(len(parsed),1)
                self.assertIsNotNone(parsed[0][3])
                self.assertEqual(unquoted('结果为 2 '+unit,known(dict(value=2,unit=unit))),[])
        self.assertTrue(unquoted('结果为 2 cm',known(dict(value=2,unit='m'))))
        self.assertTrue(unquoted('结果为 2 mm',known(dict(value=2,unit='m'))))
        self.assertTrue(unquoted('结果为 2 μs',known(dict(value=2,unit='s'))))
        self.assertTrue(unquoted('结果为 2 Mbps',known(dict(value=2,unit='bit/s'))))
        self.assertEqual(unquoted('结果为 200 cm',known(dict(value=2,unit='m'))),[])
        self.assertTrue(unquoted('结果为 2 MW',known(dict(value=2,unit='mW'))))
        for wrong,unit in [('mHz','MHz'),('Ms','ms'),('MM','mm'),('NS','ns'),('Khz','kHz')]:
            self.assertTrue(unquoted('结果为 2 '+wrong,known(dict(value=2,unit=unit))),(wrong,unit))

    def test_generic_known_unsupported_unit_can_be_answered(self):
        s=self.create('计算无线电视距，第一端天线高度20ft，第二端天线高度25m')
        issue=next(i for i in s['input_issues'] if i['field']=='antenna1_m')
        self.assertIn('暂不支持 ft',issue['detail'])
        s=self.service.apply(command('answer',s,answers={issue['id']:'6m'},mode='deterministic'))['state']
        self.assertEqual(s['status'],'AWAITING_CONFIRMATION')
        self.assertNotIn('20ft',s['request']['raw_text'])

    def test_receiver_threshold_preserves_existing_noise_reference_guard(self):
        text='计算 receiver_threshold，噪声谱密度-174dBm/Hz，比特速率1Gbit/s，解调门限15dB，噪声系数4dB，工程损失3dB'
        s=self.create(text,target='receiver_threshold')
        self.assertEqual(s['status'],'AWAITING_INPUT')
        s=self.create(text+'\n确认采用标准290K噪声路线',target='receiver_threshold')
        self.assertEqual(s['status'],'AWAITING_CONFIRMATION',s.get('failure'))
        done=self.service.apply(command('confirm',s))['state']
        self.assertEqual(done['status'],'COMPLETED',done.get('failure'))
        self.assertEqual(done['result']['outputs'][0]['value'],-62)

    def test_unit_conversions_are_same_dimension_and_finite(self):
        self.assertEqual(convert_unit(1,'MHz','Hz'),1e6)
        self.assertEqual(convert_unit(36,'km/h','m/s'),10)
        for source,target in [('Hz','K'),('dB','dBm'),('W','dBm'),('°C','K')]:
            with self.assertRaises(ValueError):
                convert_unit(1,source,target)

    def test_unsupported_units_show_conversion_without_typo_model_call(self):
        from planning.services.unit_typos import suggestions
        req=dict(raw_text='自由空间基准，频率2GHz，路径距离20海里，求路径损耗')
        with patch('planning.agents.role_model.suggest',side_effect=AssertionError('no typo guess')):
            self.assertEqual(suggestions(req,{'missing_parameters':['distance_km']},lambda *a:None),[])
        s=self.create(req['raw_text'])
        issue=next(i for i in s['input_issues'] if i['field']=='distance_km')
        self.assertIn('暂不支持 海里',issue['detail'])
        self.assertNotIn('suggestion',issue)

if __name__=='__main__':
    unittest.main()
