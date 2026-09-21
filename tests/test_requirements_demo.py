import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from test_requirements_contract import request

ROOT = Path(__file__).resolve().parents[1]


class DemoTests(unittest.TestCase):
    def run_cli(self, *args, input=None):
        return subprocess.run([sys.executable, '-B', '-X','utf8','-m','planning.demo',*args],
                              cwd=ROOT, input=input, capture_output=True, text=True, encoding='utf-8', timeout=25)

    def test_json_complete_and_chinese_summary(self):
        text = request()['raw_text']
        result = self.run_cli('--deterministic','--text',text,'--json')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['status'],'AWAITING_CONFIRMATION')
        result = self.run_cli('--deterministic','--text',text)
        self.assertIn('等待用户确认',result.stdout)
        self.assertIn('尚未进行正式计算',result.stdout)

    def test_request_file_and_invalid_json(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'request.json'; p.write_text(json.dumps(request()),encoding='utf-8')
            result=self.run_cli('--deterministic','--request',str(p),'--json')
            self.assertEqual(result.returncode,0,result.stderr)
            p.write_text('{"x":1,"x":2}',encoding='utf-8')
            result=self.run_cli('--deterministic','--request',str(p),'--json')
            self.assertEqual(result.returncode,2)
            self.assertEqual(json.loads(result.stdout)['status'],'FAILED')

    def test_interactive_and_missing_input(self):
        result=self.run_cli('--deterministic',input='按自由空间基准求路径损耗，频率2GHz\n')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('distance_km',result.stdout)

    def test_missing_catalog_visible(self):
        with tempfile.TemporaryDirectory() as temp:
            result=self.run_cli('--deterministic','--root',temp,'--text',request()['raw_text'],'--json')
        self.assertEqual(result.returncode,1)
        self.assertEqual(json.loads(result.stdout)['trace'][0]['reason_code'],'CATALOG_INVALID')
