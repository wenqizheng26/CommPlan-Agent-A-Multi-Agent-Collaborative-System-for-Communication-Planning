"""Deterministic scalar calculator. Expressions are parsed, never executed as code.

Inputs must already use the canonical units declared by the card. Physical
applicability belongs to the pipeline; this module enforces numeric domains and
formula review status. Knowledge text is never interpreted as instructions.
"""
import ast
import math
import operator
from .tools import TOOLS

_FUNCTIONS = {"log10": math.log10, "ln": math.log, "sqrt": math.sqrt,
              "sin": math.sin, "cos": math.cos, "abs": abs}
_CONSTANTS = {"pi": math.pi}
_BINARY = {ast.Add: operator.add, ast.Sub: operator.sub,
           ast.Mult: operator.mul, ast.Div: operator.truediv}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("must be a finite number, not text, boolean or null")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("must be a finite number")
    return result


def _parse(expression, parameter_names):
    if not isinstance(expression, str) or not expression or len(expression) > 4096:
        raise ValueError("expression must contain 1 to 4096 characters")
    names = set(parameter_names)
    if any(not isinstance(name, str) or not name.isidentifier() or name.startswith("_")
           or name in _FUNCTIONS or name in _CONSTANTS for name in names):
        raise ValueError("invalid or reserved parameter name")
    tree = ast.parse(expression, mode="eval")
    if sum(1 for _ in ast.walk(tree)) > 128:
        raise ValueError("expression exceeds the node limit")

    def check(node, depth=0):
        if depth > 32:
            raise ValueError("expression exceeds the depth limit")
        if isinstance(node, ast.Constant):
            _finite_number(node.value)
        elif isinstance(node, ast.Name):
            if node.id not in names and node.id not in _CONSTANTS:
                raise ValueError(f"undeclared parameter: {node.id}")
        elif isinstance(node, ast.BinOp) and (type(node.op) in _BINARY or isinstance(node.op, ast.Pow)):
            check(node.left, depth+1)
            check(node.right, depth+1)
        elif isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY:
            check(node.operand, depth+1)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id not in _FUNCTIONS or len(node.args) != 1 or node.keywords:
                raise ValueError("only declared one-argument math functions are allowed")
            check(node.args[0], depth+1)
        else:
            raise ValueError(f"expression construct is not allowed: {type(node).__name__}")

    check(tree.body)
    return tree.body


def validate_expression(expression, parameter_names):
    """Return structural errors without executing any expression."""
    try:
        _parse(expression, parameter_names)
        return []
    except (TypeError, ValueError, SyntaxError, RecursionError, OverflowError) as exc:
        return [str(exc)]


def _calculate(node, values):
    if isinstance(node, ast.Constant):
        value = float(node.value)
    elif isinstance(node, ast.Name):
        value = values[node.id] if node.id in values else _CONSTANTS[node.id]
    elif isinstance(node, ast.UnaryOp):
        value = _UNARY[type(node.op)](_calculate(node.operand, values))
    elif isinstance(node, ast.BinOp):
        left, right = _calculate(node.left, values), _calculate(node.right, values)
        if isinstance(node.op, ast.Pow):
            if abs(right) > 1024:
                raise ValueError("exponent exceeds the calculation limit")
            value = math.pow(left, right)
        else:
            value = _BINARY[type(node.op)](left, right)
    elif isinstance(node, ast.Call):
        value = _FUNCTIONS[node.func.id](_calculate(node.args[0], values))
    else:  # Only validated trees can reach this routine.
        raise ValueError("unvalidated expression")
    return _finite_number(value)


def evaluate(card: dict, parameters: dict[str, float]) -> dict:
    """Calculate a reviewed card using only its declared canonical inputs."""
    if not isinstance(card, dict) or card.get("status") != "verified":
        return {"status": "unverified_formula", "errors": ["formula is not verified"]}
    if not isinstance(parameters, dict):
        return {"status": "invalid_parameters", "errors": ["parameters must be an object"]}
    specs = card.get("parameters")
    if not isinstance(specs, dict):
        return {"status": "invalid_parameters", "errors": ["formula parameters must be an object"]}
    errors, values = [], {}
    missing = [name for name in specs if name not in parameters]
    for name, spec in specs.items():
        if name not in parameters:
            continue
        try:
            value = _finite_number(parameters[name])
            if not isinstance(spec, dict):
                raise ValueError("invalid parameter specification")
            if "min" in spec and value < _finite_number(spec["min"]):
                raise ValueError(f"must be >= {spec['min']}")
            if "exclusive_min" in spec and value <= _finite_number(spec["exclusive_min"]):
                raise ValueError(f"must be > {spec['exclusive_min']}")
            if "max" in spec and value > _finite_number(spec["max"]):
                raise ValueError(f"must be <= {spec['max']}")
            values[name] = value
        except (TypeError, ValueError, OverflowError) as exc:
            errors.append(f"{name}: {exc}")
    if errors:
        out = {"status": "invalid_parameters", "errors": errors}
        if missing:
            out["missing"] = missing
        return out
    if missing:
        return {"status": "missing_parameters", "missing": missing}
    try:
        if card.get('kind') == 'python_tool':
            if card.get('id') not in TOOLS:
                raise ValueError('python_tool is not whitelisted')
            value = _finite_number(TOOLS[card['id']](values))
        else:
            tree = _parse(card.get("expression"), specs)
            value = _calculate(tree, values)
        unit = card["output"]["unit"]
        if not isinstance(unit, str) or not unit:
            raise ValueError("output unit is missing")
    except (KeyError, TypeError, ValueError, SyntaxError, ArithmeticError, RecursionError) as exc:
        return {"status": "invalid_parameters", "errors": [f"calculation: {exc}"]}
    return {"status": "ok", "value": value, "unit": unit, "inputs": values}
