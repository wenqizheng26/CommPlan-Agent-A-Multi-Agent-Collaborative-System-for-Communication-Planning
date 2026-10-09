"""Public knowledge views and reviewed-card lifecycle operations."""
import json
import math
from pathlib import Path
from formula_rag.catalog import load_catalog
from formula_rag.core import evaluate
from planning.requirements_contract import digest, require
from planning.knowledge import switches
from planning.knowledge.drafts import write_json


def cards(root):
    from planning.services.plans import TARGETS
    off = switches.read(root)['cards']
    rows = []
    for card in load_catalog(root, include_disabled=True):
        kind = card.get('kind', 'expression')
        passed = bool(card['examples'])
        for example in card['examples']:
            result = evaluate(card, example['inputs'])
            value = result.get('value')
            passed = passed and result.get('status') == 'ok' and type(value) in (int, float) and math.isfinite(value)
            passed = passed and abs(value - example['expected']) <= example.get('tolerance', 1e-6)
        added = bool(card.get('review'))
        rows.append(dict(card, kind=kind, expression=card.get('expression'), examples_passed=bool(passed),
            enabled=card['id'] not in off, added=added,
            source_kind=card.get('source_kind', 'document' if added else 'builtin'),
            calc='dedicated' if card['id'] in TARGETS else 'needs_tool' if kind == 'python_tool' else 'generic',
            content_hash=digest(card)))
    return rows


def switch_card(root, identifier, value):
    require(type(identifier) is str, 'CARD_ID')
    require(any(c['id'] == identifier for c in load_catalog(root, include_disabled=True)), 'CARD_NOT_FOUND')
    switches.set_enabled(root, 'cards', identifier, value)


def delete_card(root, identifier):
    require(type(identifier) is str, 'CARD_ID')
    with switches.mutation(root):
        all_cards = load_catalog(root, include_disabled=True)
        card = next((c for c in all_cards if c['id'] == identifier), None)
        require(card is not None, 'CARD_NOT_FOUND')
        require(bool(card.get('review')), 'CARD_BUILTIN')
        path = Path(root) / 'knowledge/formulas.json'
        raw = json.loads(path.read_text(encoding='utf-8-sig'))
        write_json(path, [c for c in raw if c['id'] != identifier])
        data = switches.read(root)
        data['cards'].pop(identifier, None)
        switches.save(root, data)
