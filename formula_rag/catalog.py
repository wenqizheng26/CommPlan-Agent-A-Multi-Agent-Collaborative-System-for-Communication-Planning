"""Read and validate a versioned, local formula catalog."""
import json
import hashlib
import math
from pathlib import Path
import re

from .core import validate_expression
from .tools import TOOLS


def _number(value):
    try:
        return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)
    except OverflowError:
        return False


def validate_card(card: dict) -> list[str]:
    """Validate declaration only; numeric examples can be checked with evaluate."""
    if not isinstance(card, dict):
        return ["formula must be an object"]
    errors = []
    kind = card.get('kind', 'expression')
    if kind not in ('expression', 'python_tool'):
        errors.append('kind must be expression or python_tool')
    for key in ("id", "title", "description", "version"):
        if not isinstance(card.get(key), str) or not card[key].strip():
            errors.append(f"{key} must be a nonempty string")
    if kind == 'expression' and (not isinstance(card.get('expression'), str) or not card['expression'].strip()):
        errors.append('expression must be a nonempty string')
    if kind == 'python_tool' and card.get('id') not in TOOLS:
        errors.append('python_tool id is not whitelisted')
    if kind == 'python_tool' and ('expression' in card or
                                  not isinstance(card.get('algorithm'), str) or not card['algorithm'].strip()):
        errors.append('python_tool requires algorithm and must not declare expression')
    if isinstance(card.get("id"), str) and not re.fullmatch(r"[a-z][a-z0-9_]*", card["id"]):
        errors.append("id must use lowercase letters, digits and underscores")
    if card.get("status") not in ("verified", "draft"):
        errors.append("status must be verified or draft")
    output = card.get("output")
    if not isinstance(output, dict) or any(not isinstance(output.get(k), str) or not output[k] for k in ("name", "unit")):
        errors.append("output must declare name and unit")
    parameters = card.get("parameters")
    if not isinstance(parameters, dict):
        errors.append("parameters must be an object")
    else:
        for name, spec in parameters.items():
            if not isinstance(spec, dict):
                errors.append(f"{name}: parameter definition must be an object")
                continue
            if any(not isinstance(spec.get(k), str) or not spec[k] for k in ("unit", "description")):
                errors.append(f"{name}: unit and description are required")
            valid_bounds = True
            for key in ("min", "exclusive_min", "max"):
                if key in spec and not _number(spec[key]):
                    errors.append(f"{name}.{key}: finite numeric bound required")
                    valid_bounds = False
            if valid_bounds and "max" in spec:
                if "min" in spec and spec["min"] > spec["max"]:
                    errors.append(f"{name}: min exceeds max")
                if "exclusive_min" in spec and spec["exclusive_min"] >= spec["max"]:
                    errors.append(f"{name}: empty numeric domain")
            if 'default' in spec:
                default = spec['default']
                if (not isinstance(default, dict) or set(default) != {'value', 'unit', 'note'}
                        or not _number(default.get('value')) or default.get('unit') != spec.get('unit')
                        or not isinstance(default.get('note'), str) or not default['note'].strip()):
                    errors.append(f'{name}.default: value, matching unit and note required')
                elif valid_bounds and (('min' in spec and default['value'] < spec['min'])
                      or ('exclusive_min' in spec and default['value'] <= spec['exclusive_min'])
                      or ('max' in spec and default['value'] > spec['max'])):
                    errors.append(f'{name}.default: value outside parameter domain')
        if kind == 'expression':
            errors.extend(validate_expression(card.get("expression"), parameters))
    applicability = card.get("applicability")
    if not isinstance(applicability, dict) or not isinstance(applicability.get("requires"), list) or any(not isinstance(x, str) or not x for x in applicability["requires"]):
        errors.append("applicability.requires must be a string list")
    sources = card.get("sources")
    if not isinstance(sources, list) or any(not isinstance(source, dict) for source in sources):
        errors.append("sources must be an object list")
    elif card.get("status") == "verified" and (not sources or any(not source.get("title") or not (source.get("url") or source.get("path")) for source in sources)):
        errors.append("verified formulas require titled, locatable sources")
    examples = card.get("examples")
    if not isinstance(examples, list):
        errors.append("examples must be a list")
    else:
        if card.get("status") == "verified" and not examples:
            errors.append("verified formulas require a numeric example")
        for index, example in enumerate(examples):
            if not isinstance(example, dict) or not isinstance(example.get("inputs"), dict) or not _number(example.get("expected")):
                errors.append(f"examples[{index}]: inputs and finite expected value required")
            elif "tolerance" in example and (not _number(example["tolerance"]) or example["tolerance"] < 0):
                errors.append(f"examples[{index}]: nonnegative finite tolerance required")
    return errors


def load_catalog(root: Path) -> list[dict]:
    path = Path(root)/"knowledge"/"formulas.json"
    cards = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(cards, list):
        raise ValueError("formula catalog must be a list")
    seen = set()
    for index, card in enumerate(cards):
        errors = validate_card(card)
        if errors:
            raise ValueError(f"formula {index}: " + "; ".join(errors))
        if card["id"] in seen:
            raise ValueError(f"duplicate formula id: {card['id']}")
        seen.add(card["id"])
        if card.get('kind') == 'python_tool':
            # The loaded card, evidence hash and knowledge snapshot all include
            # the executable implementation, including helper functions.
            card['implementation_sha256'] = hashlib.sha256((Path(__file__).parent / 'tools.py').read_bytes()).hexdigest()
    return cards
