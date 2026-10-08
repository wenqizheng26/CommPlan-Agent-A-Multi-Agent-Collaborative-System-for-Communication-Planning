"""Engineering limits share one fact table across requirements, confirmation and tools."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
import uuid
from unittest.mock import patch

from formula_rag.catalog import load_catalog
from formula_rag.registry import call_tool, load_tools
from planning.agents.requirements import RequirementsAgent
from planning.knowledge.facts import FactService
from planning.workflow.task_service import TaskService


ROOT = Path(__file__).resolve().parents[1]
TEXT = '频率2000MHz，距离1km，发射功率20dBm，发射增益18dBi，接收增益18dBi，QPSK'
INPUTS = dict(distance_km=1, frequency_mhz=2000, tx_power_dbm=20,
              tx_gain_dbi=18, rx_gain_dbi=18, modulation='QPSK')


def command(action='create', state=None, text=TEXT, **changes):
    cmd = dict(action=action, task_id=state['task_id'] if state else str(uuid.uuid4()),
               event_id=str(uuid.uuid4()), expected_revision=state['revision'] if state else 0,
               expected_state_version=state['state_version'] if state else 0)
    if action in {'create', 'edit'}:
        cmd.update(input=dict(raw_text=text, manual_parameters={}, condition=None, target='link_margin'),
                   mode='deterministic')
    if action == 'confirm':
        cmd['review_hash'] = state['review']['review_hash']
    if action in {'answer', 'supplement'}:
        cmd['mode'] = 'deterministic'
    cmd.update(changes)
    return cmd


class PlanningParameterRangeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.service = TaskService(ROOT, Path(self.temp.name) / 'tasks.sqlite')

    def test_invalid_values_stop_before_plan_and_tools(self):
        examples = [('距离1km', '距离0km', 'distance_km'),
                    ('频率2000MHz', '频率0MHz', 'frequency_ghz'),
                    ('发射功率20dBm', '发射功率1000dBm', 'tx_power_dbm'),
                    ('发射功率20dBm', '发射功率-40dBm', 'tx_power_dbm'),
                    ('发射增益18dBi', '发射增益61dBi', 'tx_gain_dbi'),
                    ('接收增益18dBi', '接收增益-11dBi', 'rx_gain_dbi'),
                    ('距离1km', '距离1001km', 'distance_km'),
                    ('频率2000MHz', '频率301000MHz', 'frequency_ghz')]
        for before, after, field in examples:
            with self.subTest(value=after), patch('formula_rag.core.evaluate', side_effect=AssertionError('too early')):
                state = self.service.apply(command(text=TEXT.replace(before, after)))['state']
                self.assertEqual(state['status'], 'AWAITING_INPUT')
                self.assertIsNone(state['report']['calculation_plan_proposal'])
                self.assertIsNone(state['result'])
                self.assertIsNone(state['confirmed_snapshot'])
                issues = [i for i in state['input_issues'] if i['kind'] == 'PARAMETER_OUT_OF_RANGE']
                self.assertTrue(any(i['field'] == field for i in issues), state['input_issues'])
                with self.assertRaisesRegex(ValueError, 'NOT_CONFIRMABLE'):
                    self.service.apply(command('confirm', state, review_hash='none'))

    def test_legal_power_boundaries_pass_and_compute(self):
        for power in (-30, 60):
            with self.subTest(power=power):
                draft = self.service.apply(command(text=TEXT.replace('20dBm', f'{power}dBm')))['state']
                self.assertEqual(draft['status'], 'AWAITING_CONFIRMATION', draft['report']['questions'])
                done = self.service.apply(command('confirm', draft))['state']
                self.assertEqual(done['status'], 'COMPLETED', done.get('failure'))

    def test_fixing_a_range_question_creates_revision_and_invalidates_old_result(self):
        draft = self.service.apply(command())['state']
        done = self.service.apply(command('confirm', draft))['state']
        stale = command('confirm', draft)
        invalid = self.service.apply(command('supplement', done, message='发射功率改为1000dBm', mode='deterministic'))['state']
        self.assertEqual(invalid['status'], 'AWAITING_INPUT')
        self.assertEqual(invalid['revision'], done['revision'] + 1)
        self.assertIsNone(invalid['confirmed_snapshot'])
        self.assertIsNone(invalid['result'])
        self.assertIsNone(invalid['final_report'])
        issue = next(i for i in invalid['input_issues'] if i['kind'] == 'PARAMETER_OUT_OF_RANGE')
        self.assertEqual(issue['detail'], '发射功率 1000 dBm 超出工程范围（−30～60 dBm），请核对')
        fixed = self.service.apply(command('answer', invalid, answers={issue['id']: '30dBm'}))['state']
        self.assertEqual(fixed['revision'], invalid['revision'] + 1)
        self.assertEqual(fixed['status'], 'AWAITING_CONFIRMATION', fixed['report']['questions'])
        self.assertIsNone(fixed['result'])
        self.assertIsNone(fixed['confirmed_snapshot'])
        with self.assertRaisesRegex(ValueError, 'STALE_REVISION'):
            self.service.apply(stale)
        restored = TaskService(ROOT, Path(self.temp.name) / 'tasks.sqlite')
        self.assertEqual(restored.get(fixed['task_id']), fixed)
        self.assertEqual(restored.apply(command('confirm', fixed))['state']['status'], 'COMPLETED')

    def test_frequency_unit_conversion_and_domains_check_every_value(self):
        agent = RequirementsAgent(ROOT, selector=False)
        examples = [('频率301GHz，距离1km', 'frequency_ghz'),
                    ('频率2000MHz，距离0至1km', 'distance_km'),
                    ('频率2GHz或301GHz，距离1km', 'frequency_ghz'),
                    ('频率2000MHz，距离1km或1001km', 'distance_km'),
                    ('频率2至301GHz，距离1km', 'frequency_ghz')]
        for text, field in examples:
            with self.subTest(text=text):
                request = dict(schema_version='1.0.0', task_id='range', request_id='range-input', revision=0,
                               raw_text='按自由空间基准计算路径损耗，' + text, manual_parameters={}, condition=None, target='fspl_ghz')
                report = agent.run(request)
                self.assertEqual(report['execution_status'], 'AWAITING_INPUT')
                self.assertIsNone(report['calculation_plan_proposal'])
                self.assertTrue(any(d['code'] == 'PARAMETER_OUT_OF_RANGE' and d['details']['field'] == field
                                    for d in report['diagnostics']), report['diagnostics'])

    def test_direct_tool_rejects_bad_values_before_evaluation(self):
        for field, value in [('distance_km', 0), ('distance_km', 1001), ('frequency_mhz', 0),
                             ('frequency_mhz', 300001), ('tx_power_dbm', 1000), ('tx_power_dbm', -40),
                             ('tx_gain_dbi', 61), ('rx_gain_dbi', -11)]:
            with self.subTest(field=field, value=value), patch('formula_rag.core.evaluate', side_effect=AssertionError('blocked')):
                result = call_tool(ROOT, 'calc_link_margin', dict(INPUTS, **{field: value}))
                self.assertEqual(result['status'], 'invalid_arguments', result)
                self.assertIsNone(result['result'])
                self.assertEqual(result['steps'], [])

    def test_confirmation_rechecks_range_table_after_report_creation(self):
        draft = self.service.apply(command(text=TEXT.replace('20dBm', '60dBm')))['state']
        from planning.services import requirement_validation
        ranges = json.loads((ROOT / 'knowledge/facts/parameter_ranges.json').read_text(encoding='utf-8'))
        ranges['tx_power_dbm']['maximum'] = 40
        with patch('planning.knowledge.parameter_ranges.load_ranges', return_value=ranges):
            with self.assertRaisesRegex(ValueError, 'PARAMETER_OUT_OF_RANGE'):
                requirement_validation.check_report(draft['report'], draft['request'], load_catalog(ROOT), ROOT)


class ParameterRangeCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / 'knowledge', self.root / 'knowledge')
        destination = self.root / 'docs/design/TEACHER_CASES.md'
        destination.parent.mkdir(parents=True)
        shutil.copy2(ROOT / 'docs/design/TEACHER_CASES.md', destination)

    def test_schema_and_typical_values_use_the_fact_table(self):
        table = json.loads((self.root / 'knowledge/facts/parameter_ranges.json').read_text(encoding='utf-8'))
        tool = next(t for t in load_tools(self.root) if t['id'] == 'calc_link_margin')
        for field, limits in table.items():
            for key in ('minimum', 'maximum', 'exclusiveMinimum'):
                if key in limits:
                    self.assertEqual(tool['input_schema']['properties'][field][key], limits[key])
        raw = json.loads((self.root / 'knowledge/tools.json').read_text(encoding='utf-8'))[0]['input_schema']['properties']
        for field in table:
            self.assertFalse(set(raw[field]) & {'minimum', 'maximum', 'exclusiveMinimum', 'exclusiveMaximum'})
        from formula_rag.schema import validate
        for row in FactService(self.root).typical_values():
            if row['field'] in table:
                for value in [row['default'], *row['candidates']]:
                    self.assertEqual(validate(value, tool['input_schema']['properties'][row['field']]), [])

    def test_invalid_typical_defaults_and_candidates_are_rejected(self):
        path = self.root / 'knowledge/facts/typical_values.json'
        original = path.read_bytes()
        for field, value in [('distance_km', 1001), ('tx_power_dbm', 1000), ('tx_gain_dbi', -11), ('rx_gain_dbi', 61)]:
            for default in (False, True):
                with self.subTest(field=field, default=default):
                    rows = json.loads(original)
                    row = next(r for r in rows if r['field'] == field)
                    row['candidates'].append(value)
                    if default:
                        row['default'] = value
                    path.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
                    with self.assertRaisesRegex(ValueError, 'FACT_TYPICAL_VALUES_INVALID'):
                        FactService(self.root)
                    path.write_bytes(original)

    def test_changed_range_updates_schema_hash_and_requirement_guard(self):
        before = next(t for t in load_tools(self.root) if t['id'] == 'calc_link_margin')
        path = self.root / 'knowledge/facts/parameter_ranges.json'
        rows = json.loads(path.read_text(encoding='utf-8'))
        rows['tx_power_dbm']['maximum'] = 40
        path.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
        after = next(t for t in load_tools(self.root) if t['id'] == 'calc_link_margin')
        self.assertNotEqual(before['content_hash'], after['content_hash'])
        self.assertEqual(after['input_schema']['properties']['tx_power_dbm']['maximum'], 40)
        self.assertEqual(call_tool(self.root, 'calc_link_margin', dict(INPUTS, tx_power_dbm=41))['status'], 'invalid_arguments')
        request = dict(schema_version='1.0.0', task_id='range', request_id='range-input', revision=0,
                       raw_text=TEXT.replace('20dBm', '41dBm'), manual_parameters={}, condition=None, target='link_margin')
        report = RequirementsAgent(self.root, selector=False).run(request)
        self.assertEqual(report['execution_status'], 'AWAITING_INPUT')
        self.assertTrue(any(d['code'] == 'PARAMETER_OUT_OF_RANGE' for d in report['diagnostics']))
