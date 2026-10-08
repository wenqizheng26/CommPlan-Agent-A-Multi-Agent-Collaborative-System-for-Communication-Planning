"""Discover and call registered deterministic tools with checked JSON boundaries."""
import copy
import json
from pathlib import Path

from . import core
from .catalog import load_catalog
from .schema import card_input_schema, card_output_schema, check_schema, validate
from planning.requirements_contract import digest
from planning.knowledge.parameter_ranges import load_ranges, expand_range_schema


COMPOSITE_ID = "calc_link_margin"
COMPOSITE_STEPS = ["fspl_mhz", "received_power", "link_margin"]


def _expand_schema(schema, names):
    """Resolve private enum declarations before checking or exposing a schema."""
    if type(schema) is list:
        return [_expand_schema(item, names) for item in schema]
    if type(schema) is not dict:
        return copy.deepcopy(schema)
    expanded = {key: _expand_schema(value, names) for key, value in schema.items() if key != "x-enum-from"}
    if "x-enum-from" in schema:
        if schema["x-enum-from"] != "modulations" or "enum" in schema:
            raise ValueError("TOOL_ENUM_SOURCE_INVALID")
        expanded["enum"] = list(names)
    return expanded


def _load(root):
    # Local import avoids a dependency cycle: FactService uses schema.validate
    # directly to check typical values and never imports this registry.
    from planning.knowledge.facts import FactService

    root = Path(root)
    ranges = load_ranges(root)
    cards = {card["id"]: card for card in load_catalog(root) if card["status"] == "verified"}
    facts = FactService(root)
    active_modulations = {
        row["id"] for row in facts.public_records()["records"] if row["type"] == "modulation"
    }
    modulation_catalog = json.loads(
        (root / "knowledge" / "facts" / "modulations.json").read_text(encoding="utf-8-sig")
    )
    # Keep the configured table order and include full table provenance in the
    # composite hash, rather than hashing only the expanded enum names.
    modulation_records = [record for record in modulation_catalog if record["id"] in active_modulations]
    names = [record["names"][0] for record in modulation_records]
    if not names or len(names) != len(set(names)):
        raise ValueError("TOOL_MODULATIONS_INVALID")
    tools = []
    for card in cards.values():
        tools.append({
            "id": card["id"], "kind": "card", "title": card["title"], "description": card["description"],
            "input_schema": card_input_schema(card), "output_schema": card_output_schema(card),
            "content_hash": digest(card),
        })
    raw_tools = json.loads((root / "knowledge" / "tools.json").read_text(encoding="utf-8-sig"))
    if type(raw_tools) is not list:
        raise ValueError("TOOL_CATALOG_INVALID")
    ids = set(cards)
    required = {"id", "title", "description", "steps", "assumptions", "input_schema", "output_schema"}
    for raw in raw_tools:
        if (type(raw) is not dict or set(raw) != required or type(raw.get("id")) is not str or raw["id"] in ids
                or raw.get("id") != COMPOSITE_ID
                or any(type(raw.get(field)) is not str or not raw[field].strip() for field in ("id", "title", "description"))
                or raw.get("steps") != COMPOSITE_STEPS
                or type(raw.get("assumptions")) is not list or not raw["assumptions"]
                or any(type(item) is not str or not item.strip() for item in raw["assumptions"])):
            raise ValueError("TOOL_CATALOG_INVALID")
        if any(card_id not in cards for card_id in raw["steps"]):
            raise ValueError("TOOL_DEPENDENCY_NOT_VERIFIED")
        tool = {**copy.deepcopy(raw), "kind": "composite"}
        for field in ("input_schema", "output_schema"):
            tool[field] = expand_range_schema(_expand_schema(tool[field], names), ranges)
            check_schema(tool[field])
        tool["content_hash"] = digest({
            "tool": tool,
            "cards": {card_id: digest(cards[card_id]) for card_id in tool["steps"]},
            "modulations": modulation_catalog,
            "parameter_ranges": ranges,
        })
        tools.append(tool)
        ids.add(tool["id"])
    return tools, cards, facts


def load_tools(root):
    """Return public metadata for every verified card and registered composite."""
    tools, _, _ = _load(root)
    return tools


def _calculate_card(card, inputs, steps):
    computed = core.evaluate(card, inputs)
    if type(computed) is not dict:
        raise ValueError(f"{card['id']}: calculator result must be an object")
    if computed.get("status") != "ok":
        details = computed.get("errors") or computed.get("missing") or [computed.get("status", "unknown calculation failure")]
        raise ValueError(f"{card['id']}: " + "; ".join(map(str, details)))
    result = {"value": computed.get("value"), "unit": computed.get("unit")}
    errors = validate(result, card_output_schema(card))
    if errors:
        raise ValueError(f"{card['id']} output schema: " + "; ".join(errors))
    steps.append({
        "card": card["id"], "inputs": copy.deepcopy(inputs), "value": result["value"],
        "unit": result["unit"], "content_hash": digest(card),
    })
    return result


def _link_margin(arguments, cards, facts, steps):
    if "modulation" in arguments:
        matches = facts.find_modulation(arguments["modulation"])["candidates"]
        if len(matches) != 1:
            raise ValueError("MODULATION_LOOKUP_NOT_UNIQUE")
        modulation = matches[0]["record"]
        sensitivity = modulation["rx_sensitivity_dbm"]
        source = "modulation_table"
    else:
        modulation = None
        sensitivity = arguments["rx_sensitivity_dbm"]
        source = "argument"
    path_loss = _calculate_card(cards["fspl_mhz"], {
        "distance_km": arguments["distance_km"], "frequency_mhz": arguments["frequency_mhz"],
    }, steps)["value"]
    rx_power = _calculate_card(cards["received_power"], {
        "tx_power_dbm": arguments["tx_power_dbm"], "tx_gain_dbi": arguments["tx_gain_dbi"],
        "rx_gain_dbi": arguments["rx_gain_dbi"], "tx_loss_db": 0, "rx_loss_db": 0,
        "extra_loss_db": 0, "path_loss_db": path_loss,
    }, steps)["value"]
    margin = _calculate_card(cards["link_margin"], {
        "rx_power_dbm": rx_power, "rx_threshold_dbm": sensitivity, "reserve_db": 0,
    }, steps)["value"]
    required = arguments.get("required_margin_db", 0)
    result = {
        "path_loss_db": path_loss, "rx_power_dbm": rx_power, "rx_sensitivity_dbm": sensitivity,
        "sensitivity_source": source, "link_margin_db": margin,
        "required_margin_db": required, "meets": margin >= required,
    }
    if modulation is not None:
        result.update(modulation=modulation["names"][0], simulated=True)
    return result


def call_tool(root, tool_id, arguments):
    """Call only a registered id, preserving deterministic calculation evidence."""
    response = {
        "tool": tool_id, "arguments": copy.deepcopy(arguments), "status": "failed",
        "errors": [], "result": None, "steps": [],
    }
    try:
        tools, cards, facts = _load(root)
        tool = next((item for item in tools if item["id"] == tool_id), None)
        if tool is None:
            raise ValueError(f"UNREGISTERED_TOOL: {tool_id}")
        errors = validate(arguments, tool["input_schema"])
        if errors:
            response.update(status="invalid_arguments", errors=errors)
            return response
        if tool["kind"] == "card":
            result = _calculate_card(cards[tool_id], arguments, response["steps"])
        elif tool_id == COMPOSITE_ID:
            result = _link_margin(arguments, cards, facts, response["steps"])
        else:
            raise ValueError(f"UNSUPPORTED_TOOL: {tool_id}")
        errors = validate(result, tool["output_schema"])
        if errors:
            response["errors"] = ["output schema: " + error for error in errors]
            return response
        response.update(status="ok", result=result)
    except (OSError, KeyError, TypeError, ValueError, ArithmeticError) as exc:
        response["errors"] = [str(exc)]
    return response
