"""C10 fact catalog, sources, snapshots, and Appendix A calculations."""
import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from formula_rag.catalog import load_catalog
from formula_rag.core import evaluate
from planning.knowledge.facts import FactService
from planning.services.requirement_evidence import snapshot_for


ROOT = Path(__file__).resolve().parents[1]


class M1FactTests(unittest.TestCase):
    def setUp(self):
        self.service = FactService(ROOT)
        self.cards = {c['id']: c for c in load_catalog(ROOT)}

    def test_matching_and_verified_provenance(self):
        for name, method in [('A站', 'name_exact'), ('A岸站', 'alias_exact')]:
            result = self.service.find_site(name)
            self.assertEqual(result['match_method'], method)
            self.assertEqual([c['record']['id'] for c in result['candidates']], ['site:sim-a'])
        self.assertEqual([c['record']['id'] for c in self.service.find_site('港口站')['candidates']],
                         ['site:sim-east', 'site:sim-west'])
        self.assertIsNone(self.service.find_site('D站')['candidates'][0]['record']['position']['antenna_m'])
        self.assertEqual(self.service.find_site('未知站')['candidates'], [])
        self.assertEqual(self.service.find_device('XX-100')['candidates'][0]['record']['tx_power_dbm'], 37)
        for query in ('', ' ', 'x' * 51):
            with self.assertRaisesRegex(ValueError, 'FACT_QUERY_INVALID'):
                self.service.find_site(query)
        for kind in ('site', 'device'):
            for record in self.service._records[kind]:
                self.assertEqual(record['status'], 'verified')
                self.assertTrue(record['source']['locator'])
                self.assertTrue((ROOT / record['source']['path']).is_file())

    def test_documents_match_structured_values(self):
        site_text = (ROOT / 'knowledge/documents/simulated/站址表.md').read_text(encoding='utf-8')
        self.assertTrue(site_text.startswith('模拟数据，仅供演示'))
        table = {}
        for line in site_text.splitlines():
            if line.startswith('| site:'):
                cells = [c.strip() for c in line.strip('|').split('|')]
                table[cells[0]] = cells
        self.assertEqual(len(table), 7)
        for site in self.service._records['site']:
            cells = table[site['id']]
            self.assertEqual(cells[1:3], [site['names'][0], site['names'][1] if len(site['names']) > 1 else '—'])
            pos = site['position']
            self.assertEqual([float(cells[3]), float(cells[4]), float(cells[5])],
                             [pos['lat'], pos['lon'], pos['ground_m']])
            self.assertEqual(None if cells[6] == '未知' else float(cells[6]), pos['antenna_m'])
        for device in self.service._records['device']:
            text = (ROOT / device['source']['path']).read_text(encoding='utf-8')
            self.assertTrue(text.startswith('模拟数据，仅供演示'))
            cells = [c.strip() for c in next(l for l in text.splitlines() if l.startswith('| ' + device['model'] + ' |')).strip('|').split('|')]
            self.assertEqual(cells[0], device['model'])
            self.assertEqual([float(c) for c in cells[1:4]],
                             [device['tx_power_dbm'], device['antenna_gain_dbi'], device['rx_sensitivity_dbm']])
            self.assertEqual([float(x) for x in cells[4].split('–')], device['band_ghz'])

    def test_snapshot_changes_for_facts_and_documents(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / 'knowledge', root / 'knowledge')
            before = snapshot_for(load_catalog(root), root)
            for relative in ('knowledge/facts/sites.json', 'knowledge/documents/simulated/站址表.md'):
                target = root / relative
                original = target.read_bytes()
                target.write_bytes(original + b'\n')
                self.assertNotEqual(snapshot_for(load_catalog(root), root), before)
                target.write_bytes(original)

    def test_unreviewed_record_hidden_and_no_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / 'knowledge', root / 'knowledge')
            path = root / 'knowledge/facts/sites.json'
            records = json.loads(path.read_text(encoding='utf-8'))
            draft = copy.deepcopy(records[0])
            draft.update(id='site:unreviewed', names=['未审核站'], status='draft')
            records.append(draft)
            path.write_text(json.dumps(records, ensure_ascii=False), encoding='utf-8')
            with patch('socket.socket', side_effect=AssertionError('network access')):
                service = FactService(root)
                self.assertEqual(service.find_site('未审核站')['candidates'], [])
                self.assertEqual(service.describe()['site_count'], 7)

    def test_appendix_a_distance_horizon_and_margin(self):
        sites = {r['id']: r for r in self.service._records['site']}
        base = sites['site:sim-a']['position']
        device = self.service.find_device('XX-100')['candidates'][0]['record']
        expected = [('site:sim-b', 34.06437891885911, 43.16616936921285, 5.93),
                    ('site:sim-c', 85.06560867773132, 40.991369503811114, None),
                    ('site:sim-f', 11.981648366331887, 38.5228607555874, 15.01),
                    ('site:sim-east', 25.977276854481172, 40.991369503811114, 8.29),
                    ('site:sim-west', 22.013016287350297, 40.991369503811114, 9.73)]
        for site_id, distance, horizon, margin in expected:
            with self.subTest(site=site_id):
                other = sites[site_id]['position']
                inputs = {'lat1_deg': base['lat'], 'lon1_deg': base['lon'], 'ground1_m': base['ground_m'], 'antenna1_m': base['antenna_m'],
                          'lat2_deg': other['lat'], 'lon2_deg': other['lon'], 'ground2_m': other['ground_m'], 'antenna2_m': other['antenna_m']}
                got_distance = evaluate(self.cards['slant_range_wgs84'], inputs)['value']
                got_horizon = evaluate(self.cards['radio_horizon'], {'antenna1_m': base['antenna_m'], 'antenna2_m': other['antenna_m']})['value']
                self.assertAlmostEqual(got_distance, distance, delta=.001)
                self.assertAlmostEqual(got_horizon, horizon, delta=.001)
                if margin is not None:
                    fspl = evaluate(self.cards['fspl_ghz'], {'frequency_ghz': 2, 'distance_km': got_distance})['value']
                    rx = evaluate(self.cards['received_power'], {'tx_power_dbm': device['tx_power_dbm'], 'tx_gain_dbi': device['antenna_gain_dbi'],
                        'rx_gain_dbi': device['antenna_gain_dbi'], 'tx_loss_db': 2, 'rx_loss_db': 2, 'path_loss_db': fspl, 'extra_loss_db': 0})['value']
                    actual = evaluate(self.cards['link_margin'], {'rx_power_dbm': rx, 'rx_threshold_dbm': device['rx_sensitivity_dbm'], 'reserve_db': 0})['value']
                    self.assertAlmostEqual(actual, margin, delta=.01)


if __name__ == '__main__':
    unittest.main()
