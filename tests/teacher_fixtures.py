"""Local files required by the teacher fact tables in temporary test roots."""
from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]


def copy_teacher_dependencies(root):
    for relative in ('docs/design/TEACHER_CASES.md', 'knowledge/tools.json'):
        destination = Path(root) / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination)
