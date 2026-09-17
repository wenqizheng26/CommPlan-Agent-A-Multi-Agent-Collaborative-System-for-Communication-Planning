"""Explicit local formula registration and numerical review; never auto-approve uploads."""
import copy
import datetime
import json
import os
import tempfile
from pathlib import Path
from .catalog import load_catalog, validate_card
from .core import evaluate


def save_catalog(root, cards):
    path = Path(root)/'knowledge/formulas.json'
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent, delete=False, suffix='.tmp') as f:
        json.dump(cards, f, ensure_ascii=False, indent=2, allow_nan=False)
        name = f.name
    os.replace(name, path)


def import_card(root, card):
    card = copy.deepcopy(card)
    if not isinstance(card, dict):
        raise ValueError('公式文件必须包含一个JSON对象')
    card['status'] = 'draft'
    card.pop('review', None)
    errors = validate_card(card)
    if any(c not in ('free_space', 'maximum_doppler') for c in card.get('applicability', {}).get('requires', [])):
        errors.append('公式包含程序尚未支持的条件规则，请先实现并测试对应条件入口')
    if errors:
        raise ValueError('; '.join(errors))
    cards = load_catalog(root)
    if any(c['id'] == card['id'] for c in cards):
        raise ValueError('公式ID已存在，请使用新ID并登记新的版本，原条目保留')
    canonical = {k: s['unit'] for c in cards for k, s in c['parameters'].items()}
    if any(k in canonical and canonical[k] != s['unit'] for k, s in card['parameters'].items()):
        raise ValueError('参数名已被不同规范单位使用，请换用明确的新参数名')
    cards.append(card)
    save_catalog(root, cards)
    return card


def approve_card(root, identifier, reviewer):
    if not isinstance(reviewer, str) or not reviewer.strip():
        raise ValueError('审核人不能为空；执行本命令代表已核对物理适用条件和来源')
    cards = load_catalog(root)
    card = next((c for c in cards if c['id'] == identifier), None)
    if card is None:
        raise ValueError('未找到公式')
    card['status'] = 'verified'
    errors = validate_card(card)
    for example in card.get('examples', []):
        result = evaluate(card, example['inputs'])
        if result['status'] != 'ok' or abs(result['value'] - example['expected']) > example.get('tolerance', 1e-9):
            errors.append('数值样例未通过：' + json.dumps(example, ensure_ascii=False))
    if errors:
        raise ValueError('; '.join(errors))
    card['review'] = {'reviewer': reviewer.strip(), 'timestamp_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      'scope': '来源和物理适用条件由审核人确认；程序仅检查结构和数值样例'}
    save_catalog(root, cards)
    return card
