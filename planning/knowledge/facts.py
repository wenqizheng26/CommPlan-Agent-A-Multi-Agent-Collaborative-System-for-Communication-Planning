"""Deterministic lookup of reviewed, locally sourced simulated facts."""
import hashlib
import json
import math
from pathlib import Path


def fact_manifest(root):
    root = Path(root)
    paths = sorted((*root.glob('knowledge/facts/*.json'),
                    *root.glob('knowledge/documents/simulated/*.md'),
                    *root.glob('knowledge/documents/manifest.json'),
                    *root.glob('knowledge/documents/glossary.json')))
    return [{'path': p.relative_to(root).as_posix(),
             'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths]


def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _normal(name):
    value = ''.join(name.split())
    return value[:-1] if value.endswith('站') else value


def _normal_modulation(name):
    return ''.join(name.upper().split()).replace('-', '').replace('_', '')


def registered(root, source):
    """The approved record's document is in the manifest with the same hash (the original may be
    kept only on the machine that added it: added originals are ignored by Git)."""
    path = Path(root) / 'knowledge/documents/manifest.json'
    if not source.get('sha256') or not path.is_file():
        return False
    documents = json.loads(path.read_text(encoding='utf-8')).get('documents', [])
    return any(d.get('local_path') == source['path'] and d.get('sha256') == source['sha256'] for d in documents)


class FactService:
    def __init__(self, root):
        self.root = Path(root)
        self._records = {}
        self._typical_values = []
        self.stale = []  # approved records whose source document has changed since review
        facts_path = self.root / 'knowledge' / 'facts'
        teacher_tables = [(facts_path / filename).is_file()
                          for filename in ('modulations.json', 'typical_values.json')]
        if any(teacher_tables) and not all(teacher_tables):
            raise ValueError('FACT_CATALOG_INVALID')
        for kind, filename in (('site', 'sites.json'), ('device', 'devices.json'),
                               ('modulation', 'modulations.json')):
            path = self.root / 'knowledge' / 'facts' / filename
            # Old knowledge roots without either teacher table remain usable.
            if kind == 'modulation' and not any(teacher_tables):
                self._records[kind] = []
                continue
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
                if not source_path.resolve().is_relative_to(self.root.resolve()):
                    raise ValueError('FACT_SOURCE_INVALID')
                if not source_path.is_file():
                    if kind == 'modulation' or not registered(self.root, source):
                        raise ValueError('FACT_SOURCE_INVALID')
                elif source.get('sha256') and hashlib.sha256(source_path.read_bytes()).hexdigest() != source['sha256']:
                    self.stale.append(record['id'])
                if (source_path.is_file() and source['locator'].startswith('表 1 行 ')
                        and source['locator'].split()[-1] not in source_path.read_text(encoding='utf-8')):
                    raise ValueError('FACT_SOURCE_INVALID')
                if kind == 'site':
                    pos = record.get('position')
                    if (not isinstance(pos, dict) or pos.get('datum') != 'WGS84' or
                        any(not _finite(pos.get(k)) for k in ('lat', 'lon', 'ground_m')) or
                        not (-90 <= pos['lat'] <= 90 and -180 <= pos['lon'] <= 180) or
                        (pos.get('antenna_m') is not None and (not _finite(pos['antenna_m']) or pos['antenna_m'] < 0))):
                        raise ValueError('FACT_CATALOG_INVALID')
                elif kind == 'device':
                    band = record.get('band_ghz')
                    if (not isinstance(record.get('model'), str) or
                        any(not _finite(record.get(k)) for k in ('tx_power_dbm', 'antenna_gain_dbi', 'rx_sensitivity_dbm')) or
                        not isinstance(band, list) or len(band) != 2 or not all(_finite(x) for x in band) or not 0 < band[0] < band[1]):
                        raise ValueError('FACT_CATALOG_INVALID')
                elif (not record['id'].strip() or not _finite(record.get('rx_sensitivity_dbm'))
                      or not isinstance(record.get('note'), str) or not record['note'].strip()
                      or not isinstance(record.get('simulated'), bool)):
                    raise ValueError('FACT_CATALOG_INVALID')
            self._records[kind] = sorted((r for r in records if r.get('status') == 'verified' and r['id'] not in self.stale),
                                         key=lambda r: r['id'])
        if all(teacher_tables):
            self._load_typical_values(facts_path / 'typical_values.json')

    def _load_typical_values(self, path):
        from formula_rag.schema import check_schema, validate

        records = json.loads(path.read_text(encoding='utf-8-sig'))
        tools = json.loads((self.root / 'knowledge' / 'tools.json').read_text(encoding='utf-8-sig'))
        if not isinstance(records, list) or not isinstance(tools, list):
            raise ValueError('FACT_TYPICAL_VALUES_INVALID')
        schemas = [tool.get('input_schema') for tool in tools
                   if isinstance(tool, dict) and tool.get('id') == 'calc_link_margin']
        if len(schemas) != 1 or not isinstance(schemas[0], dict):
            raise ValueError('FACT_TYPICAL_VALUES_INVALID')
        properties = schemas[0].get('properties')
        if not isinstance(properties, dict):
            raise ValueError('FACT_TYPICAL_VALUES_INVALID')
        fields = {'distance_km', 'tx_power_dbm', 'tx_gain_dbi', 'rx_gain_dbi', 'modulation'}
        seen = set()
        modulations = {record['names'][0] for record in self._records['modulation']}
        for record in records:
            if (not isinstance(record, dict) or record.get('field') not in fields
                    or record['field'] in seen
                    or any(not isinstance(record.get(k), str) or not record[k].strip()
                           for k in ('unit', 'note'))
                    or not isinstance(record.get('candidates'), list) or not record['candidates']
                    or 'default' not in record or record['default'] not in record['candidates']):
                raise ValueError('FACT_TYPICAL_VALUES_INVALID')
            field = record['field']
            seen.add(field)
            values = [record['default'], *record['candidates']]
            if field == 'modulation':
                if any(not isinstance(value, str) or value not in modulations for value in values):
                    raise ValueError('FACT_TYPICAL_VALUES_INVALID')
            else:
                schema = properties.get(field)
                if not isinstance(schema, dict):
                    raise ValueError('FACT_TYPICAL_VALUES_INVALID')
                check_schema(schema)
                if any(not _finite(value) or validate(value, schema) for value in values):
                    raise ValueError('FACT_TYPICAL_VALUES_INVALID')
        if seen != fields:
            raise ValueError('FACT_TYPICAL_VALUES_INVALID')
        self._typical_values = records

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

    def records(self):
        """Every reviewed site and device record, for matching names in a message."""
        import copy
        return copy.deepcopy(self._records['site'] + self._records['device'])

    def find_site(self, name):
        return self._find('site', name)

    def find_device(self, name):
        return self._find('device', name)

    def find_modulation(self, name):
        if not isinstance(name, str) or not name.strip() or len(name) > 50:
            raise ValueError('FACT_QUERY_INVALID')
        query = name.strip()
        normalized = _normal_modulation(query)
        tiers = (
            ('name_exact', lambda r: r['names'][0] == query),
            ('alias_exact', lambda r: query in r['names'][1:]),
            ('normalized_exact', lambda r: any(normalized == _normal_modulation(n) for n in r['names'])),
        )
        for method, predicate in tiers:
            matches = [record for record in self._records['modulation'] if predicate(record)]
            if matches:
                return {'query': query, 'match_method': method,
                        'candidates': [{'record': record, 'source': record['source'], 'match_method': method}
                                       for record in matches]}
        return {'query': query, 'match_method': None, 'candidates': []}

    def modulation_records(self):
        """The modulation table, most robust (lowest sensitivity) first."""
        import copy
        return copy.deepcopy(sorted(self._records['modulation'], key=lambda r: r['rx_sensitivity_dbm']))

    def typical_values(self):
        import copy
        return copy.deepcopy(self._typical_values)

    def public_records(self):
        """Read-only presentation data; no local paths or unreviewed records."""
        import copy
        rows=[]
        for kind, records in self._records.items():
            for record in records:
                fields = (('position',) if kind == 'site' else
                          ('rx_sensitivity_dbm', 'note') if kind == 'modulation' else
                          ('model', 'tx_power_dbm', 'antenna_gain_dbi', 'rx_sensitivity_dbm', 'band_ghz'))
                rows.append(dict(id=record['id'],type=kind,names=list(record['names']),
                    simulated=record.get('simulated',False),
                    **({'environment':record.get('environment','未记录')} if kind=='site' else {}),
                    source={k:record['source'][k] for k in ('title','version','locator')},
                    **{k:copy.deepcopy(record[k]) for k in fields}))
        return dict(records=rows, version=self.describe()['version'], typical_values=self.typical_values())

    def describe(self):
        manifest = fact_manifest(self.root)
        payload = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
        return {'version': hashlib.sha256(payload).hexdigest(),
                'site_count': len(self._records['site']), 'device_count': len(self._records['device']),
                'modulation_count': len(self._records['modulation']),
                'source_manifest': manifest}
