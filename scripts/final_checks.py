"""Record current tests, source fingerprints and JavaScript syntax verification."""
import argparse
import datetime
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('--node', default='node')
args = parser.parse_args()
run = subprocess.run([sys.executable, '-X', 'utf8', '-m', 'unittest', 'discover', '-s', 'tests', '-v'], cwd=ROOT, capture_output=True, text=True, encoding='utf-8')
test_output = run.stdout + run.stderr
html = (ROOT/'web/index.html').read_text(encoding='utf-8')
scripts = re.findall(r'<script>(.*?)</script>', html, re.S)
scripts.extend(p.read_text(encoding='utf-8') for p in (ROOT/'web/assets').glob('app.js'))
syntax = subprocess.run([args.node, '--check'], input='\n'.join(scripts), capture_output=True, text=True, encoding='utf-8')
paths = sorted([*ROOT.glob('formula_rag/*.py'), *ROOT.glob('tests/*.py'), *ROOT.glob('scripts/*.py'),
                *ROOT.glob('web/assets/app.*'), ROOT/'web/assets/katex/manifest.json',
                ROOT/'app.py', ROOT/'launch.py', ROOT/'web/index.html', ROOT/'knowledge/formulas.json', ROOT/'runtime_config.json'])
sources = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
aggregate = hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()
visual_path = ROOT/'reports/browser_qa.json'
visual = json.loads(visual_path.read_text(encoding='utf-8')) if visual_path.exists() else {}
web_sources = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
               for p in [ROOT/'web/index.html', ROOT/'web/assets/app.js', ROOT/'web/assets/app.css',
                         ROOT/'formula_rag/presentation.py', ROOT/'knowledge/formulas.json']}
visual_qa = {'verified': visual.get('main_flow_passed', False) and visual.get('web_sources') == web_sources,
             'evidence': 'reports/browser_qa.json',
             'scope': 'Observed in-app browser layout, formula navigation, missing-input flow and local JSON save; see browser evidence for scope.'}
report = {'timestamp_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'unit_tests': {'exit_code': run.returncode, 'output': test_output},
          'javascript_syntax': {'exit_code': syntax.returncode, 'output': syntax.stdout + syntax.stderr},
          'visual_qa': visual_qa,
          'source_sha256': sources, 'aggregate_sha256': aggregate,
          'passed': run.returncode == 0 and syntax.returncode == 0}
(ROOT/'reports/final_checks.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({'passed': report['passed'], 'unit_summary': test_output.splitlines()[-4:], 'js_syntax_exit': syntax.returncode,
                  'source_hash': aggregate, 'visual_qa': report['visual_qa']}, ensure_ascii=False, indent=2))
raise SystemExit(0 if report['passed'] else 1)
