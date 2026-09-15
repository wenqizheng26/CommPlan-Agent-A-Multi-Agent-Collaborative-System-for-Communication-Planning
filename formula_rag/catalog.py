"""Read and validate a versioned, local formula catalog."""
import json
import math
from pathlib import Path
import re

from .core import validate_expression


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
    for key in ("id", "title", "description", "version", "expression"):
        if not isinstance(card.get(key), str) or not card[key].strip():
            errors.append(f"{key} must be a nonempty string")
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
    return cards
