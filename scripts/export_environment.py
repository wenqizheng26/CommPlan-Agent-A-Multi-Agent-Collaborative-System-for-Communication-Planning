"""Record installed dependency versions and copy their installed license notices."""
import importlib.metadata as metadata
import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
rows = []
license_dir = ROOT/'runtime/licenses/python'
license_dir.mkdir(parents=True, exist_ok=True)
for dist in sorted(metadata.distributions(), key=lambda d: d.metadata['Name'].lower()):
    name = dist.metadata['Name']
    notices = []
    for file in dist.files or []:
        if 'dist-info' in str(file) and any(t in file.name.lower() for t in ('license', 'copying', 'notice')):
            source = dist.locate_file(file)
            if source.is_file():
                destination = license_dir/(name+'-'+file.name)
                destination.write_bytes(source.read_bytes())
                notices.append(str(destination.relative_to(ROOT)))
    rows.append({'name': name, 'version': dist.version,
                 'license_metadata': dist.metadata.get('License-Expression') or dist.metadata.get('License'),
                 'license_classifiers': [c for c in dist.metadata.get_all('Classifier', []) if c.startswith('License')],
                 'license_files': notices})
(ROOT/'requirements.lock.txt').write_text('\n'.join(r['name']+'=='+r['version'] for r in rows)+'\n', encoding='utf-8')
(ROOT/'reports/environment.json').write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps([{'name': r['name'], 'version': r['version'], 'notices': len(r['license_files'])} for r in rows], indent=2))
