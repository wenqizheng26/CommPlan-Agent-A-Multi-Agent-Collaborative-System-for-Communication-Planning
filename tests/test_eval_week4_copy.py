import sys
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


class Week4CopyTests(unittest.TestCase):
    def test_temporary_app_copy_keeps_every_cited_fact_source(self):
        import eval_week4
        from planning.knowledge.facts import FactService
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / 'app'
            eval_week4.copy_app(root)
            self.assertTrue((root / 'docs/design/TEACHER_CASES.md').is_file())
            # Raised FACT_SOURCE_INVALID before the cited files were copied.
            self.assertEqual(FactService(root).records(), FactService(ROOT).records())


if __name__ == '__main__':
    unittest.main()
