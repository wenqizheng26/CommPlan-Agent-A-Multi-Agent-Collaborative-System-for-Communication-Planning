import argparse
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from formula_rag.importing import import_card, approve_card

parser = argparse.ArgumentParser(description='导入后为待审核，明确审核后才能计算；不会自动联网。')
sub = parser.add_subparsers(dest='command', required=True)
add = sub.add_parser('add')
add.add_argument('file')
review = sub.add_parser('approve')
review.add_argument('id')
review.add_argument('--reviewer', required=True)
args = parser.parse_args()
if args.command == 'add':
    result = import_card(ROOT, json.loads(Path(args.file).read_text(encoding='utf-8-sig')))
else:
    result = approve_card(ROOT, args.id, args.reviewer)
print(json.dumps({'id': result['id'], 'status': result['status']}, ensure_ascii=False))
