"""English requests retain original provenance and the same numeric gates."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from formula_rag.parsing import extract_request
from planning.agents.requirements import RequirementsAgent
from planning.workflow.task_service import TaskService
from test_planning_loop import command

ROOT=Path(__file__).resolve().parents[1]
TEXT='Use the free-space reference; frequency 2GHz; distance 1km; calculate path loss.'
BUDGET='Use the free-space reference; frequency 2GHz; distance 10km; transmit power 30dBm; tx gain 5dBi; rx gain 5dBi; receiver threshold -100dBm; calculate link margin.'
CASES=[(TEXT,['fspl_ghz'],98.42059991327963),
       (BUDGET,['fspl_ghz','received_power','link_margin'],17.57940008672037),
       (BUDGET.replace('calculate link margin','calculate received power'),['fspl_ghz','received_power'],-82.42059991327963),
       ('Calculate first Fresnel zone radius; frequency 2GHz; d1=15km; d2=15km.',['fresnel_radius'],33.500746),
       ('Use a single knife-edge model; calculate knife-edge diffraction loss; frequency 2GHz; d1=15km; d2=15km; relative obstacle height 20m.',['knife_edge_nu','knife_edge_loss'],12.876),
       ('Use a smooth sea single specular reflection two-ray model; calculate additional sea-reflection loss; frequency 2GHz; distance 30km; tx height above sea 30m; rx height above sea 25m.',['sea_reflection_two_ray'],5.130)]

def request(text):
    return dict(schema_version='1.0.0',task_id='en',revision=0,request_id='en-request',raw_text=text,
                manual_parameters={},condition=None,target=None)

class EnglishTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.service=TaskService(ROOT,Path(self.tmp.name)/'tasks.sqlite')

    def test_complete_confirmed_chains(self):
        for text,chain,value in CASES:
            with self.subTest(text=text):
                draft=self.service.apply(command(text=text))['state']
                self.assertEqual(draft['status'],'AWAITING_CONFIRMATION',draft['report']['diagnostics'])
                self.assertEqual(draft['report']['calculation_plan_proposal']['selected_model'],chain)
                done=self.service.apply(command('confirm',draft))['state']
                self.assertEqual(done['status'],'COMPLETED',done.get('failure'))
                self.assertAlmostEqual(done['result']['outputs'][0]['value'],value,delta=.002)
                self.assertTrue(all(v['passed'] for v in done['validations']))

    def test_case_and_units(self):
        p=extract_request('CARRIER FREQUENCY is 2000MHz; LINK DISTANCE is 1000m; TRANSMIT POWER 1W; TX GAIN 1dBd; calculate path loss.')
        self.assertEqual(p['parameters'],dict(frequency_ghz=2,distance_km=1,tx_power_dbm=30,tx_gain_dbi=3.15))
        self.assertEqual(p['targets'],['fspl_ghz'])

    def test_missing_conflicting_and_negative_numeric_context(self):
        for text in [TEXT.replace('distance 1km; ',''),TEXT+' frequency 3GHz.',
                     TEXT.replace('frequency 2GHz','frequency unknown 2GHz'),
                     TEXT.replace('frequency 2GHz','frequency is not 2GHz'),
                     TEXT+' frequency 3', TEXT.replace('frequency 2GHz','frequency about 2GHz')]:
            draft=self.service.apply(command(text=text))['state']
            self.assertEqual(draft['status'],'AWAITING_INPUT')
            self.assertIsNone(draft['result'])

    def test_free_space_cannot_be_inferred_and_actual_sea_not_supported(self):
        for text,status in [(TEXT.replace('Use the free-space reference; ',''),'AWAITING_INPUT'),
                            ('Calculate actual sea propagation loss; frequency 2GHz; distance 30km.','NEEDS_MODEL'),
                            (TEXT+' two-way radar echo','NEEDS_MODEL'),
                            (TEXT.replace('Use the free-space reference','Do not use free space'),'AWAITING_INPUT')]:
            self.assertEqual(self.service.apply(command(text=text))['state']['status'],status)

    def test_english_provenance_uses_exact_original_span(self):
        report=RequirementsAgent(ROOT,selector=False).run(request('🙂 '+TEXT))
        for p in report['parameters_proposal']:
            for o in p['origins']:
                if o['kind']=='user_text':
                    a,b=o['span']; self.assertIsNotNone(o['span'])
                    self.assertIn(str(int(o['value'])),('🙂 '+TEXT)[a:b])

    def test_model_english_evidence_grounded_without_translating_it(self):
        output=dict(selected_ids=['fspl_ghz'],targets=[dict(id='fspl_ghz',evidence='calculate path loss')],
                    conditions=[dict(id='free_space_reference',evidence='Use the free-space reference')])
        selector=lambda *args:dict(raw_output=json.dumps(output),model='stub',usage={})
        report=RequirementsAgent(ROOT,selector=selector).run(request(TEXT))
        self.assertEqual(report['component_modes']['interpretation'],'stub',report['diagnostics'])
        self.assertEqual(report['execution_status'],'AWAITING_CONFIRMATION')
        output['targets'][0]['evidence']='计算路径损耗'
        report=RequirementsAgent(ROOT,selector=selector).run(request(TEXT))
        self.assertEqual(report['component_modes']['interpretation'],'deterministic')
        self.assertEqual(report['runtime_health'],'degraded')

    def test_english_supplement_starts_new_revision_and_keeps_old_result_invalid(self):
        draft=self.service.apply(command(text=TEXT))['state']
        done=self.service.apply(command('confirm',draft))['state']
        changed=self.service.apply(command('supplement',done,message='Change frequency to 3GHz',mode='deterministic'))['state']
        self.assertEqual(changed['revision'],1)
        self.assertIsNone(changed['result'])
        self.assertEqual(changed['status'],'AWAITING_CONFIRMATION',changed['report']['diagnostics'])
        final=self.service.apply(command('confirm',changed))['state']
        self.assertAlmostEqual(final['result']['outputs'][0]['value'],101.94242509439326)

    def test_bandwidth_and_height_never_become_frequency_or_distance(self):
        for text,field in [('Use free-space reference; bandwidth 2GHz; distance 1km; calculate path loss.','frequency_ghz'),
                           ('Use free-space reference; frequency 2GHz; antenna height 20m; calculate path loss.','distance_km')]:
            draft=self.service.apply(command(text=text))['state']
            self.assertEqual(draft['status'],'AWAITING_INPUT')
            self.assertIn(field,draft['report']['missing_parameters'])

    def test_local_selector_declares_new_conditions_and_labels_context(self):
        from formula_rag.model import LocalSelector
        from formula_rag.catalog import load_catalog
        from planning.services.requirement_quantities import find_quantities,LABEL_FIELDS
        text=CASES[4][0]
        with patch('formula_rag.model.chat',return_value=({},json.dumps(dict(selected_ids=[],targets=[],conditions=[])))) as call:
            LocalSelector()(text,load_catalog(ROOT),quantities=find_quantities(text),label_fields=LABEL_FIELDS)
        payload=call.call_args.args[0]
        enum=payload['response_format']['json_schema']['schema']['properties']['conditions']['items']['properties']['id']['enum']
        self.assertTrue({'single_knife_edge','smooth_sea'} <= set(enum))
        self.assertIn('d1=15km',payload['messages'][-1]['content'])
        self.assertIn('d1_km',payload['messages'][-1]['content'])
