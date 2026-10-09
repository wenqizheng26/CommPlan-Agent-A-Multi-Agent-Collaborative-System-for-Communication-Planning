"""Knowledge lifecycle, task invalidation and unit trust-boundary regressions."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch
from formula_rag.catalog import load_catalog
from planning.knowledge import library, sources, switches
from planning.knowledge.drafts import DraftStore, write_json
from planning.retrieval.documents import DocumentStore
from planning.services.requirement_evidence import snapshot_for
from planning.services.unit_typos import suggestions
from planning.web_server import create_server
from planning.workflow.task_service import TaskService
from tests.teacher_fixtures import copy_teacher_dependencies
from tests.test_planning_loop import ROOT, TEXT, command


class RootFixture:
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for folder in ('knowledge/documents','knowledge/facts','config'):
            shutil.copytree(ROOT / folder,self.root / folder)
        shutil.copy(ROOT / 'knowledge/formulas.json',self.root / 'knowledge/formulas.json')
        shutil.copy(ROOT / 'runtime_config.json',self.root / 'runtime_config.json')
        copy_teacher_dependencies(self.root)
        self.service = TaskService(self.root,self.root / 'tasks.sqlite')


class KnowledgeControlsTests(RootFixture, unittest.TestCase):

    def test_document_switch_preserves_catalog_and_refreshes_warm_service(self):
        retrieval=self.service.retrieval_for(None)
        catalog=load_catalog(self.root)
        before=snapshot_for(catalog,self.root)
        self.assertTrue(any(c['doc_id']=='sim-xx100' for c in retrieval.documents.chunks))
        sources.switch_document(self.root,'sim-xx100',False)
        self.service.refresh_knowledge()
        self.assertFalse(any(c['doc_id']=='sim-xx100' for c in retrieval.documents.chunks))
        self.assertEqual(load_catalog(self.root),catalog)
        self.assertNotEqual(snapshot_for(catalog,self.root),before)
        self.assertFalse(next(d for d in sources.describe(self.root)['documents'] if d['doc_id']=='sim-xx100')['enabled'])
        self.assertTrue(sources.sections(self.root,'sim-xx100'))
        sources.switch_document(self.root,'sim-xx100',True)
        self.assertEqual(snapshot_for(catalog,self.root),before)
        self.assertEqual(switches.read(self.root)['documents'],{})

    def test_old_confirmation_invalidated_by_document_or_card_switch(self):
        for kind,identifier in [('documents','sim-sites'),('cards','doppler_max')]:
            state=self.service.apply(command())['state']
            switches.set_enabled(self.root,kind,identifier,False)
            with self.assertRaisesRegex(ValueError,'KNOWLEDGE_CHANGED'):
                self.service.apply(command('confirm',state))
            self.assertEqual(self.service.get(state['task_id']),state)
            switches.set_enabled(self.root,kind,identifier,True)

    def test_disabled_cards_follow_missing_card_path(self):
        for card,text in [('fspl_ghz',TEXT),('fspl_ghz','按自由空间计算接收信号电平。'),
                          ('fspl_mhz','频率2GHz，距离1km，求链路余量。')]:
            with self.subTest(card=card):
                library.switch_card(self.root,card,False)
                state=self.service.apply(command(text=text))['state']
                self.assertEqual(state['status'],'AWAITING_INPUT',state)
                self.assertFalse(any(d['code']=='CARD_DISABLED' for d in state['report']['diagnostics']))
                self.assertNotIn('已停用',json.dumps(state['input_issues'],ensure_ascii=False))
                if text != TEXT:
                    self.assertIn('path_loss_db',state['report']['missing_parameters'])
                library.switch_card(self.root,card,True)

    def test_disabled_goal_choices_cannot_be_selected_by_api(self):
        library.switch_card(self.root,'fspl_ghz',False)
        state=self.service.apply(command(text='请帮我规划通信。'))['state']
        goal=state['input_issues'][0]
        choices={c['value']:c for c in goal['choices']}
        self.assertNotIn('fspl_ghz',choices)
        self.assertNotIn('disabled',choices['received_power'])
        with self.assertRaisesRegex(ValueError,'INVALID_ANSWER_CHOICE'):
            self.service.apply(command('answer',state,answers={goal['id']:'fspl_ghz'},mode='deterministic'))
        answered=self.service.apply(command('answer',state,answers={goal['id']:'received_power'},mode='deterministic'))['state']
        self.assertIn('path_loss_db',answered['report']['missing_parameters'])
        self.assertNotIn('fspl_ghz',[c['id'] for c in self.service.retrieval_for(None).cards])

    def test_absent_dependency_becomes_input_without_composite_recalculation(self):
        text='频率2GHz，距离1km，发射功率20dBm，两端天线增益18dBi，求链路余量，比较QPSK和16QAM。'
        library.switch_card(self.root,'fspl_ghz',False)
        state=self.service.apply(command(text=text))['state']
        self.assertEqual(state['status'],'AWAITING_CONFIRMATION',state)
        self.assertEqual(state['report']['calculation_plan_proposal']['selected_model'],
                         ['fspl_mhz','received_power','link_margin'])
        library.switch_card(self.root,'fspl_mhz',False)
        missing=self.service.apply(command(text=text.replace('和16QAM','')))['state']
        self.assertEqual(missing['status'],'AWAITING_INPUT',missing)
        self.assertIn('path_loss_db',missing['report']['missing_parameters'])
        issue=next(i for i in missing['input_issues'] if i['field']=='path_loss_db')
        supplied=self.service.apply(command('answer',missing,answers={issue['id']:'100dB'},mode='deterministic'))['state']
        self.assertEqual(supplied['status'],'AWAITING_CONFIRMATION',supplied)
        self.assertNotIn('tool',supplied['report']['calculation_plan_proposal'])
        self.assertEqual(supplied['report']['calculation_plan_proposal']['selected_model'],['received_power','link_margin'])
        done=self.service.apply(command('confirm',supplied))['state']
        self.assertEqual(done['status'],'COMPLETED',done)
        self.assertNotIn('tool_calls',done['result'])
        self.assertEqual(done['result']['steps'][0]['inputs']['path_loss_db'],100)
        library.switch_card(self.root,'fspl_mhz',True)
        supplied='按自由空间基准，路径损耗100dB，发射功率20dBm，发射天线增益18dBi，接收天线增益18dBi，求接收信号电平。'
        state=self.service.apply(command(text=supplied))['state']
        self.assertEqual(state['status'],'AWAITING_CONFIRMATION',state)
        self.assertEqual(state['report']['calculation_plan_proposal']['selected_model'],['received_power'])

    def test_switches_are_persistent_and_concurrent_updates_do_not_get_lost(self):
        with ThreadPoolExecutor(2) as pool:
            futures=[pool.submit(switches.set_enabled,self.root,kind,ident,False)
                     for kind,ident in [('cards','doppler_max'),('documents','sim-sites')]]
            for f in futures: f.result()
        self.assertEqual(switches.read(self.root),dict(schema_version=1,cards={'doppler_max':False},documents={'sim-sites':False}))
        reloaded=TaskService(self.root,self.root / 'restart.sqlite')
        self.assertNotIn('doppler_max',[c['id'] for c in reloaded.retrieval_for(None).cards])

    def test_disabled_and_deleted_cards_produce_same_tasks_and_restore(self):
        cases = [('fspl_ghz',TEXT),
            ('fspl_ghz','按自由空间基准，发射功率20dBm，发射天线增益18dBi，接收天线增益18dBi，接收门限-100dBm，求链路余量。'),
            ('fspl_mhz','频率2GHz，距离1km，发射功率20dBm，两端天线增益18dBi，求链路余量，调制QPSK。'),
            ('received_power','按自由空间基准，接收门限-100dBm，求链路余量。'),
            ('link_margin','按自由空间基准，求链路余量。'),
            ('thermal_noise','计算热噪声功率，温度290K，带宽1MHz'),
            ('thermal_noise','请规划通信。')]
        raw=load_catalog(self.root,include_disabled=True)
        def behavior(state):
            report=state['report'];plan=report['calculation_plan_proposal']
            return (state['status'], report['targets'], report['missing_parameters'],
                plan['selected_model'] if plan else None, [d['code'] for d in report['diagnostics']],
                [(i['field'],i['title'],i['choices']) for i in state['input_issues']])
        for card,text in cases:
            with self.subTest(card=card,text=text):
                library.switch_card(self.root,card,False)
                off=self.service.apply(command(text=text))['state']
                library.switch_card(self.root,card,True)
                write_json(self.root/'knowledge/formulas.json',[c for c in raw if c['id']!=card])
                absent=self.service.apply(command(text=text))['state']
                self.assertEqual(behavior(off),behavior(absent))
                write_json(self.root/'knowledge/formulas.json',raw)
        restored=self.service.apply(command(text=TEXT))['state']
        self.assertEqual(restored['status'],'AWAITING_CONFIRMATION')
        self.assertEqual(self.service.apply(command('confirm',restored))['state']['status'],'COMPLETED')

    def test_registry_missing_composite_member_preserves_active_card_tools(self):
        from formula_rag.registry import call_tool,load_tools
        for member in ('fspl_mhz','received_power','link_margin'):
            with self.subTest(member=member):
                library.switch_card(self.root,member,False)
                ids={t['id'] for t in load_tools(self.root)}
                self.assertNotIn(member,ids)
                self.assertNotIn('calc_link_margin',ids)
                self.assertEqual(call_tool(self.root,'fspl_ghz',dict(frequency_ghz=2,distance_km=1))['status'],'ok')
                self.assertEqual(call_tool(self.root,'calc_link_margin',{})['errors'],['UNREGISTERED_TOOL: calc_link_margin'])
                library.switch_card(self.root,member,True)
        self.assertIn('calc_link_margin',{t['id'] for t in load_tools(self.root)})

    def test_saved_goal_choices_follow_current_catalog_without_rewriting_history(self):
        create=command(text='请帮我规划通信。')
        state=self.service.apply(create)['state']
        original=self.service.store.get(state['task_id'])
        history=self.service.history(state['task_id'])
        issue=next(i for i in state['input_issues'] if i['field']=='goal')
        for card in ('fspl_ghz','thermal_noise'):
            library.switch_card(self.root,card,False)
        for response in (self.service.get(state['task_id']),self.service.apply(create)['state']):
            choices={c['value'] for i in response['input_issues'] for c in i['choices']}
            self.assertFalse({'fspl_ghz','thermal_noise'} & choices)
        for card in ('fspl_ghz','thermal_noise'):
            with self.assertRaisesRegex(ValueError,'INVALID_ANSWER_CHOICE'):
                self.service.apply(command('answer',state,answers={issue['id']:card},mode='deterministic'))
        self.assertEqual(self.service.store.get(state['task_id']),original)
        self.assertEqual(self.service.history(state['task_id']),history)
        library.switch_card(self.root,'fspl_ghz',True)
        self.assertIn('fspl_ghz',{c['value'] for i in self.service.get(state['task_id'])['input_issues'] for c in i['choices']})
        while_off=self.service.apply(command(text='请帮我规划通信。'))['state']
        library.switch_card(self.root,'thermal_noise',True)
        self.assertIn('thermal_noise',{c['value'] for i in self.service.get(while_off['task_id'])['input_issues'] for c in i['choices']})

    def test_old_report_goal_projection_filters_missing_cards(self):
        from planning.services.clarification import active_goal_issues,issues_for
        state=self.service.apply(command(text='请帮我规划通信。'))['state']
        state['report'].pop('available_goals')
        state['report']['disabled_goals']={'received_power':'旧停用依赖提示'}
        state.pop('input_issues')
        library.switch_card(self.root,'fspl_ghz',False)
        choices={c['value']:c for i in active_goal_issues(issues_for(state),load_catalog(self.root)) for c in i['choices']}
        self.assertNotIn('fspl_ghz',choices)
        self.assertNotIn('disabled',choices['received_power'])

    def test_full_modulation_chain_with_manual_threshold_requires_intent_resolution(self):
        state=self.service.apply(command(text='频率2GHz，距离1km，发射功率20dBm，两端天线增益18dBi，接收门限-100dBm，求链路余量，比较QPSK和16QAM。'))['state']
        self.assertEqual(state['status'],'AWAITING_INPUT')
        self.assertTrue(any(d['code']=='MODULATION_COUNT' for d in state['report']['diagnostics']))

    def test_shortened_modulation_chain_asks_single_choice_instead_of_losing_comparison(self):
        library.switch_card(self.root,'fspl_mhz',False)
        for threshold in ('','接收门限-100dBm，'):
            with self.subTest(threshold=threshold):
                state=self.service.apply(command(text='发射功率20dBm，两端天线增益18dBi，路径损耗100dB，'+threshold+'求链路余量，比较QPSK和16QAM。'))['state']
                self.assertEqual(state['status'],'AWAITING_INPUT')
                self.assertTrue(any(d['code']=='MODULATION_COUNT' for d in state['report']['diagnostics']))
                self.assertNotIn('variants',state['report']['calculation_plan_proposal'] or {})
                self.assertTrue(any('调制方式' in i['title'] for i in state['input_issues']))

    def test_library_exposes_all_cards_hashes_examples_and_source_kind(self):
        library.switch_card(self.root,'doppler_max',False)
        rows={c['id']:c for c in library.cards(self.root)}
        self.assertEqual(len(rows),14)
        self.assertFalse(rows['doppler_max']['enabled'])
        self.assertEqual(rows['fspl_ghz']['sources'][0]['doc_id'],'itu-p525-5')
        self.assertEqual(rows['sea_reflection_two_ray']['sources'][0]['doc_id'],'itu-p530-19')
        self.assertEqual(rows['doppler_max']['source_kind'],'builtin')
        self.assertEqual(rows['doppler_max']['calc'],'generic')
        self.assertEqual(rows['fspl_ghz']['calc'],'dedicated')
        for identifier in ('slant_range_wgs84','radio_horizon','fspl_mhz'):
            self.assertEqual(rows[identifier]['calc'],'dedicated')
        self.assertTrue(all(c['examples_passed'] for c in rows.values()),rows)
        self.assertTrue(all(len(c['content_hash'])==64 for c in rows.values()))

    def test_builtin_delete_forbidden_added_card_delete_leaves_history_intact(self):
        for operation,identifier in [(library.delete_card,'fspl_ghz'),(sources.delete_document,'sim-sites')]:
            with self.assertRaisesRegex(ValueError,'BUILTIN'): operation(self.root,identifier)
        state=self.service.apply(command())['state']
        history=copy.deepcopy(self.service.history(state['task_id']))
        raw=load_catalog(self.root,include_disabled=True)
        added=dict(raw[1],id='added_example',review={'draft_id':'example'})
        raw.append(added)
        write_json(self.root / 'knowledge/formulas.json',raw)
        library.switch_card(self.root,'added_example',False)
        library.delete_card(self.root,'added_example')
        self.assertNotIn('added_example',[c['id'] for c in library.cards(self.root)])
        self.assertNotIn('added_example',switches.read(self.root)['cards'])
        self.assertEqual(self.service.history(state['task_id']),history)

    def test_delete_added_document_removes_original_cache_and_blocks_pending_draft(self):
        record=sources.add_document(self.root,'sample.md',b'# Guide\n\nThe unit is GHz.')
        library_before=load_catalog(self.root)
        folder=self.root / 'knowledge/sources/converted';folder.mkdir(exist_ok=True)
        cache=folder / (record['doc_id']+'.abc.md');cache.write_text('cache')
        chunk=next(c for c in DocumentStore(self.root).chunks if c['doc_id']==record['doc_id'])
        draft=dict(id='a'*32,kind='formula',status='draft',record=copy.deepcopy(library_before[0]),
            evidence=[dict(field='parameters',chunk_id=chunk['id'],quote='The unit is GHz.')],doc_id=record['doc_id'],
            source_hashes={chunk['id']:record['sha256']},created_at='2026-10-09',origin={})
        draft['content_hash']=DraftStore.content_hash(draft)
        store=DraftStore(self.root);write_json(store.path(draft['id']),draft)
        sources.switch_document(self.root,record['doc_id'],False)
        sources.delete_document(self.root,record['doc_id'])
        self.assertFalse((self.root / record['local_path']).exists())
        self.assertFalse(cache.exists())
        self.assertNotIn(record['doc_id'],switches.read(self.root)['documents'])
        shown=store.views()[0]
        self.assertFalse(shown['approvable'])
        self.assertIn('来源文档已删除',shown['problems'])
        with self.assertRaisesRegex(ValueError,'DRAFT_NOT_APPROVABLE'):
            store.review(draft['id'],'Reviewer',draft['content_hash'],'approve')
        self.assertEqual(load_catalog(self.root),library_before)

    def test_typos_resolved_once_without_consuming_following_prose(self):
        for token,answer,field in [('1kn','1km','distance_km'),('10公理','10km','distance_km'),('2Ghzz','2GHz','frequency_ghz')]:
            for suffix in ['，求路径损耗。','求路径损耗。','，求路径损耗，需要保留正文。']:
                with self.subTest(token=token,suffix=suffix):
                    text=TEXT.replace('2GHz',token) if field=='frequency_ghz' else TEXT.replace('1km',token)
                    text=text.replace('，求路径损耗。',suffix)
                    state=self.service.apply(command(text=text))['state']
                    q=next(q for q in state['input_issues'] if q['field']==field)
                    out=self.service.apply(command('answer',state,answers={q['id']:answer},mode='deterministic'))['state']
                    self.assertEqual(out['status'],'AWAITING_CONFIRMATION',out)
                    self.assertNotIn(token,out['request']['raw_text'])
                    self.assertTrue(out['request']['raw_text'].endswith(suffix))
        normal=self.service.apply(command())['state']
        self.assertEqual(normal['status'],'AWAITING_CONFIRMATION')

    def test_unit_suggestions_require_model_legal_unit_and_unchanged_number(self):
        request={'raw_text':TEXT.replace('1km','1kn')}
        report={'missing_parameters':['distance_km']}
        def selector(value):
            return lambda *args: {'output':{'items':[dict(field='distance_km',value=value,reason='kn 可能是 km')]}}
        self.assertEqual(suggestions(request,report,False),[])
        valid=suggestions(request,report,selector('1km'))
        self.assertEqual(valid[0]['value'],'1km')
        self.assertEqual(valid[0]['note'],'单位猜测，需确认')
        for value in ['10km','1GHz','1kn']:
            self.assertEqual(suggestions(request,report,selector(value)),[])
        self.assertEqual(suggestions(request,report,lambda *args: (_ for _ in ()).throw(OSError())),[])

    def test_unit_replacement_preserves_adjacent_prose(self):
        from planning.services.clarification import replace_parameter
        from planning.services.unit_typos import problems
        for token,prose in [('1km','通信'),('10公里','通信'),('10公理','通信'),
                            ('1kn','实验'),('1kn','补充说明'),('1km','任意说明')]:
            with self.subTest(token=token,prose=prose):
                request=dict(raw_text='频率2GHz，距离'+token+prose+'，求路径损耗。',
                             manual_parameters={},condition=None,target=None)
                replace_parameter(request,None,'distance_km','10km')
                self.assertEqual(request['raw_text'],'频率2GHz，路径距离10km'+prose+'，求路径损耗。')
        self.assertEqual(problems('距离1km通信'),[])
        self.assertEqual(problems('距离1kn补充说明')[0]['unit'],'kn')
        request=dict(raw_text='频率2Ghzz实验，距离1km，求路径损耗。',manual_parameters={},condition=None,target=None)
        replace_parameter(request,None,'frequency_ghz','3GHz')
        self.assertEqual(request['raw_text'],'载波频率3GHz实验，距离1km，求路径损耗。')

    def test_unit_typo_does_not_get_offline_default_distance(self):
        state=self.service.apply(command(text='频率2GHz，距离1kn，求链路余量。'))['state']
        issue=next(q for q in state['input_issues'] if q['field']=='distance_km')
        self.assertNotIn('suggestion',issue)

    def test_model_unit_suggestion_is_saved_and_requires_explicit_answer(self):
        selector=lambda *args: {'output':{'items':[dict(field='distance_km',value='1km',reason='kn 可能是 km')]}}
        with patch('planning.workflow.planning_graph.role_selector',return_value=selector):
            state=self.service.apply(command(text=TEXT.replace('1km','1kn')))['state']
        issue=next(q for q in state['input_issues'] if q['field']=='distance_km')
        self.assertEqual(issue['suggestion']['note'],'单位猜测，需确认')
        self.assertIn('1kn',state['request']['raw_text'])
        self.assertEqual(self.service.get(state['task_id'])['input_issues'],state['input_issues'])
        answered=self.service.apply(command('answer',state,answers={issue['id']:'1km'},mode='deterministic'))['state']
        self.assertEqual(answered['status'],'AWAITING_CONFIRMATION')
        self.assertIn('单位修正已确认',answered['request']['raw_text'])

    def test_missing_geometry_member_asks_distance_without_skipping_horizon_check(self):
        from planning.agents.requirements import RequirementsAgent
        from planning.workflow.requirements_graph import run_requirements
        text='按自由空间基准计算，频率2GHz，A站到C站，求路径损耗。'
        output=dict(selected_ids=['fspl_ghz'],targets=[],conditions=[],sites=[
            dict(mention=name,evidence=name) for name in ['A站','C站']])
        request=dict(schema_version='1.0.0',task_id='geometry',request_id='geometry',revision=0,
                     **command(text=text)['input'])
        for member in ('radio_horizon','slant_range_wgs84'):
            with self.subTest(member=member):
                library.switch_card(self.root,member,False)
                agent=RequirementsAgent(self.root,selector=lambda *args:dict(raw_output=json.dumps(output)))
                state=run_requirements(request,agent)
                self.assertEqual(state['status'],'AWAITING_INPUT',state)
                self.assertIn('distance_km',state['report']['missing_parameters'])
                plan=state['report']['calculation_plan_proposal']
                self.assertEqual(plan['selected_model'],['fspl_ghz'])
                self.assertNotIn('checks',plan)
                library.switch_card(self.root,member,True)

    def test_document_query_is_recorded_in_report(self):
        state=self.service.apply(command(text='频率2GHz，距离1km，发射功率20dBm，两端天线增益18dBi，求链路余量，比较QPSK和16QAM。'))['state']
        self.assertEqual(state['status'],'AWAITING_CONFIRMATION',state)
        from planning.agents.review import document_query
        self.assertEqual(state['report']['document_retrieval']['query'],document_query(state['request'],state['report']))
        saved=self.service.get(state['task_id'])
        self.assertEqual(saved['report']['document_retrieval'],state['report']['document_retrieval'])


class KnowledgeAPITests(RootFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.server=create_server(self.root,self.root / 'http.sqlite',port=0)
        thread=threading.Thread(target=self.server.serve_forever,daemon=True);thread.start()
        def stop():
            self.server.shutdown();self.server.server_close();thread.join(5)
        self.addCleanup(stop)
        self.base=f'http://127.0.0.1:{self.server.server_port}'
        self.token=self.call('/api/session')[1]['token']

    def call(self,path,body=None,headers=None):
        h={'Content-Type':'application/json','X-Planning-Token':getattr(self,'token','')};h.update(headers or {})
        request=Request(self.base+path,data=json.dumps(body).encode() if body is not None else None,headers=h)
        try: response=urlopen(request,timeout=30)
        except HTTPError as e: response=e
        with response: return response.status,json.loads(response.read())

    def test_library_mutations_authentication_types_and_builtin_errors(self):
        routes=[('/api/documents/switch',{'doc_id':'sim-sites','enabled':False}),
                ('/api/formula-cards/switch',{'id':'doppler_max','enabled':False}),
                ('/api/documents/delete',{'doc_id':'sim-sites'}),('/api/formula-cards/delete',{'id':'fspl_ghz'})]
        for route,body in routes:
            for headers in [{'X-Planning-Token':'wrong'},{'Origin':'https://evil.test'}]:
                self.assertEqual(self.call(route,body,headers)[0],403)
        self.assertEqual(self.call(routes[0][0],routes[0][1])[0],200)
        self.assertEqual(self.call(routes[1][0],routes[1][1])[0],200)
        self.assertEqual(self.call(routes[2][0],routes[2][1]),(409,{'error':{'code':'DOCUMENT_BUILTIN','message':'内置文档不能删除，可以停用。'}}))
        self.assertEqual(self.call(routes[3][0],routes[3][1])[0],409)
        self.assertEqual(self.call('/api/documents/switch',{'doc_id':'sim-sites','enabled':'false'})[0],400)
        self.assertEqual(self.call('/api/formula-cards/delete',{'id':'missing'})[0],404)
        library=self.call('/api/formula-library')[1]
        self.assertFalse(next(c for c in library['cards'] if c['id']=='doppler_max')['enabled'])
        self.assertEqual(library['capabilities'],{'manual_drafts':True,'model_drafts':True,
                                                'generic_calculation':True})
        self.assertEqual(self.call('/api/formula-cards?ids=fspl_ghz')[1]['cards'][0]['sources'][0]['doc_id'],'itu-p525-5')

    def test_api_switch_invalidates_confirm_and_reports_folder_without_git(self):
        state=self.call('/api/commands',command())[1]['state']
        self.call('/api/documents/switch',{'doc_id':'sim-sites','enabled':False})
        status,data=self.call('/api/commands',command('confirm',state))
        self.assertEqual((status,data['error']['code']),(409,'KNOWLEDGE_CHANGED'))
        info=self.call('/api/session')[1]['instance']
        self.assertEqual(info,dict(folder=self.root.name,branch=None,commit=None,dirty=False))

    def test_knowledge_writes_wait_for_task_transaction(self):
        import sqlite3
        conn=sqlite3.connect(self.root / 'http.sqlite')
        conn.execute('BEGIN IMMEDIATE')
        done=threading.Event();results=[]
        worker=threading.Thread(target=lambda: (results.append(self.call('/api/documents/switch',
            {'doc_id':'sim-sites','enabled':False})),done.set()))
        worker.start()
        try:
            self.assertFalse(done.wait(.2))
            self.assertTrue(switches.enabled(self.root,'documents','sim-sites'))
        finally:
            conn.rollback();conn.close()
        worker.join(5)
        self.assertTrue(done.is_set())
        self.assertEqual(results[0][0],200)
        self.assertFalse(switches.enabled(self.root,'documents','sim-sites'))
