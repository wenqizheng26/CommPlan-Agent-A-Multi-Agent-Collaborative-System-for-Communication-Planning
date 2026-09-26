"""Deterministic lookup of reviewed, locally sourced simulated facts."""
import hashlib
import json
import math
from pathlib import Path


def fact_manifest(root):
    root = Path(root)
    paths = sorted((*root.glob('knowledge/facts/*.json'),
                    *root.glob('knowledge/documents/simulated/*.md')))
    return [{'path': p.relative_to(root).as_posix(),
             'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _normal(name):
    value = ''.join(name.split())
    return value[:-1] if value.endswith('站') else value


class FactService:
    def __init__(self, root):
        self.root = Path(root)
        self._records = {}
        for kind, filename in (('site', 'sites.json'), ('device', 'devices.json')):
            path = self.root / 'knowledge' / 'facts' / filename
            records = json.loads(path.read_text(encoding='utf-8-sig'))
            if not isinstance(records, list):
                raise ValueError('FACT_CATALOG_INVALID')
            ids = set()
            for record in records:
                if not isinstance(record, dict) or record.get('type') != kind or not isinstance(record.get('id'), str) or record['id'] in ids:
                    raise ValueError('FACT_CATALOG_INVALID')
                ids.add(record['id'])
                if not isinstance(record.get('names'), list) or not record['names'] or any(not isinstance(n, str) or not n.strip() for n in record['names']):
                    raise ValueError('FACT_CATALOG_INVALID')
                source = record.get('source')
                if not isinstance(source, dict) or any(not isinstance(source.get(k), str) or not source[k].strip() for k in ('title', 'path', 'version', 'locator')):
                    raise ValueError('FACT_CATALOG_INVALID')
                source_path = self.root / source['path']
                if not source_path.resolve().is_relative_to(self.root.resolve()) or not source_path.is_file():
                    raise ValueError('FACT_SOURCE_INVALID')
                if source['locator'].startswith('表 1 行 ') and source['locator'].split()[-1] not in source_path.read_text(encoding='utf-8'):
                    raise ValueError('FACT_SOURCE_INVALID')
                if kind == 'site':
                    pos = record.get('position')
                    if (not isinstance(pos, dict) or pos.get('datum') != 'WGS84' or
                        any(not _finite(pos.get(k)) for k in ('lat', 'lon', 'ground_m')) or
                        not (-90 <= pos['lat'] <= 90 and -180 <= pos['lon'] <= 180) or
                        (pos.get('antenna_m') is not None and (not _finite(pos['antenna_m']) or pos['antenna_m'] < 0))):
                        raise ValueError('FACT_CATALOG_INVALID')
                else:
                    band = record.get('band_ghz')
                    if (not isinstance(record.get('model'), str) or
                        any(not _finite(record.get(k)) for k in ('tx_power_dbm', 'antenna_gain_dbi', 'rx_sensitivity_dbm')) or
                        not isinstance(band, list) or len(band) != 2 or not all(_finite(x) for x in band) or not 0 < band[0] < band[1]):
                        raise ValueError('FACT_CATALOG_INVALID')
            self._records[kind] = sorted((r for r in records if r.get('status') == 'verified'), key=lambda r: r['id'])

    def _find(self, kind, name):
        if not isinstance(name, str) or not name.strip() or len(name) > 50:
            raise ValueError('FACT_QUERY_INVALID')
        query = name.strip()
        normalized = _normal(query)
        tiers = (
            ('name_exact', lambda r: r['names'][0] == query),
            ('alias_exact', lambda r: query in r['names'][1:]),
            ('normalized_contains', lambda r: bool(normalized) and any(normalized in _normal(n) or _normal(n) in normalized for n in r['names'])),
        )
        for method, predicate in tiers:
            matches = [r for r in self._records[kind] if predicate(r)]
            if matches:
                return {'query': query, 'match_method': method,
                        'candidates': [{'record': r, 'source': r['source'], 'match_method': method} for r in matches]}
        return {'query': query, 'match_method': None, 'candidates': []}

    def find_site(self, name):
        return self._find('site', name)

    def find_device(self, name):
        return self._find('device', name)

    def public_records(self):
        """Read-only presentation data; no local paths or unreviewed records."""
        import copy
        rows=[]
        for kind, records in self._records.items():
            for record in records:
                fields=('position',) if kind=='site' else ('model','tx_power_dbm','antenna_gain_dbi','rx_sensitivity_dbm','band_ghz')
                rows.append(dict(id=record['id'],type=kind,names=list(record['names']),
                    simulated=record.get('simulated',False),
                    **({'environment':record.get('environment','未记录')} if kind=='site' else {}),
                    source={k:record['source'][k] for k in ('title','version','locator')},
                    **{k:copy.deepcopy(record[k]) for k in fields}))
        return dict(records=rows,version=self.describe()['version'])

    def describe(self):
        manifest = fact_manifest(self.root)
        payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        return {'version': hashlib.sha256(payload).hexdigest(),
                'site_count': len(self._records['site']), 'device_count': len(self._records['device']),
                'source_manifest': manifest}
