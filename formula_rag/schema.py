"""Small, explicit JSON Schema subset for deterministic tool boundaries.

Unsupported keywords are errors rather than silently ignored constraints.
This module depends only on the standard library, so facts can validate their
typical values without importing the tool registry.
"""
import math


KEYWORDS = {
    "type", "properties", "required", "additionalProperties", "enum",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum",
    "oneOf", "items", "title", "description",
}
TYPES = {"object", "number", "integer", "string", "boolean", "array"}
BOUNDS = {"minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"}


def _number(value):
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _json_value(value):
    if value is None or type(value) in (str, bool):
        return True
    if type(value) in (int, float):
        return _number(value)
    if type(value) is list:
        return all(_json_value(item) for item in value)
    if type(value) is dict:
        return all(type(key) is str and _json_value(item) for key, item in value.items())
    return False


def _equal(left, right):
    """JSON equality keeps booleans distinct from numbers, including in enums."""
    if type(left) in (int, float) and type(right) in (int, float):
        return _number(left) and _number(right) and left == right
    if type(left) is not type(right):
        return False
    if type(left) is list:
        return len(left) == len(right) and all(_equal(a, b) for a, b in zip(left, right))
    if type(left) is dict:
        return left.keys() == right.keys() and all(_equal(left[key], right[key]) for key in left)
    return left == right


def check_schema(schema):
    """Raise ValueError for an unsupported keyword or malformed declaration."""
    def check(value, path):
        if type(value) is not dict:
            raise ValueError(f"{path}: schema must be an object")
        unknown = set(value) - KEYWORDS
        if unknown:
            raise ValueError(f"{path}: unsupported schema keyword(s): " + ", ".join(sorted(map(str, unknown))))
        if "type" in value and (type(value["type"]) is not str or value["type"] not in TYPES):
            raise ValueError(f"{path}.type: unsupported type")
        for name in ("title", "description"):
            if name in value and type(value[name]) is not str:
                raise ValueError(f"{path}.{name}: must be a string")
        if "properties" in value:
            properties = value["properties"]
            if type(properties) is not dict or any(type(key) is not str for key in properties):
                raise ValueError(f"{path}.properties: must be an object with string keys")
            for name, subschema in properties.items():
                check(subschema, f"{path}.properties.{name}")
        if "required" in value:
            required = value["required"]
            if (type(required) is not list or any(type(name) is not str for name in required)
                    or len(required) != len(set(required))):
                raise ValueError(f"{path}.required: must be a list of unique strings")
        if "additionalProperties" in value and value["additionalProperties"] is not False:
            raise ValueError(f"{path}.additionalProperties: only false is supported")
        if "enum" in value:
            choices = value["enum"]
            if type(choices) is not list or not choices or not all(_json_value(item) for item in choices):
                raise ValueError(f"{path}.enum: must be a nonempty list of JSON values")
            if any(_equal(item, earlier) for index, item in enumerate(choices) for earlier in choices[:index]):
                raise ValueError(f"{path}.enum: duplicate values")
        for name in BOUNDS:
            if name in value and not _number(value[name]):
                raise ValueError(f"{path}.{name}: must be a finite number")
        if "oneOf" in value:
            branches = value["oneOf"]
            if type(branches) is not list or not branches:
                raise ValueError(f"{path}.oneOf: must be a nonempty list of schemas")
            for index, branch in enumerate(branches):
                check(branch, f"{path}.oneOf[{index}]")
        if "items" in value:
            check(value["items"], f"{path}.items")

    check(schema, "$")


def _has_type(value, name):
    if name == "number":
        return _number(value)
    if name == "integer":
        return _number(value) and (type(value) is int or value.is_integer())
    return type(value) is {
        "object": dict, "string": str, "boolean": bool, "array": list,
    }[name]


def _validate(instance, schema, path):
    errors = []
    if "type" in schema and not _has_type(instance, schema["type"]):
        errors.append(f"{path}: must be {schema['type']}")
    if "enum" in schema and not any(_equal(instance, choice) for choice in schema["enum"]):
        errors.append(f"{path}: value is not in enum")
    if type(instance) is dict:
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in instance:
                errors.append(f"{path}.{name}: required property is missing")
        if schema.get("additionalProperties") is False:
            for name in sorted(set(instance) - set(properties), key=str):
                errors.append(f"{path}.{name}: additional property is not allowed")
        for name, subschema in properties.items():
            if name in instance:
                errors.extend(_validate(instance[name], subschema, f"{path}.{name}"))
    if type(instance) is list and "items" in schema:
        for index, item in enumerate(instance):
            errors.extend(_validate(item, schema["items"], f"{path}[{index}]"))
    if type(instance) in (int, float) and any(name in schema for name in BOUNDS):
        if not _number(instance):
            errors.append(f"{path}: must be a finite number")
        else:
            comparisons = (
                ("minimum", lambda a, b: a >= b, ">="),
                ("maximum", lambda a, b: a <= b, "<="),
                ("exclusiveMinimum", lambda a, b: a > b, ">"),
                ("exclusiveMaximum", lambda a, b: a < b, "<"),
            )
            for name, accepts, symbol in comparisons:
                if name in schema and not accepts(instance, schema[name]):
                    errors.append(f"{path}: must be {symbol} {schema[name]}")
    if "oneOf" in schema:
        matches = sum(not _validate(instance, branch, path) for branch in schema["oneOf"])
        if matches != 1:
            errors.append(f"{path}: oneOf requires exactly one matching schema, got {matches}")
    return errors


def validate(instance, schema):
    """Return path-qualified errors; an empty list means the instance is valid."""
    check_schema(schema)
    return _validate(instance, schema, "$")


def card_input_schema(card):
    """Use canonical parameter units and the same numeric bounds as evaluate."""
    properties = {}
    for name, parameter in card["parameters"].items():
        spec = {
            "type": "number",
            "description": f"{parameter['description']}（单位：{parameter['unit']}）",
        }
        for old_name, new_name in (
            ("min", "minimum"), ("exclusive_min", "exclusiveMinimum"), ("max", "maximum"),
        ):
            if old_name in parameter:
                spec[new_name] = parameter[old_name]
        properties[name] = spec
    schema = {
        "type": "object", "properties": properties,
        "required": list(properties), "additionalProperties": False,
    }
    check_schema(schema)
    return schema


def card_output_schema(card):
    schema = {
        "type": "object",
        "properties": {"value": {"type": "number"}, "unit": {"type": "string", "enum": [card["output"]["unit"]]}},
        "required": ["value", "unit"], "additionalProperties": False,
    }
    check_schema(schema)
    return schema
