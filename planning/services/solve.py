"""Pure one-variable inversion of a reviewed scalar calculation plan.

The plan envelope supplies registered cards, existing step bindings, known
canonical parameter values, parameter-id/name mapping, and confirmed conditions.
It does not read task state or publish a result.
"""
import math

from planning.requirements_contract import require
from planning.services.calculation import run_steps


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def solve(plan, unknown, condition, bracket=None) -> dict:
    require(type(plan) is dict and type(plan.get('steps')) is list and bool(plan['steps']) and
            type(plan.get('cards')) is list and type(plan.get('parameters')) is dict and
            type(plan.get('parameter_names')) is dict and type(plan.get('conditions')) is list,
            'SOLVE_PLAN')
    require(type(unknown) is str and bool(unknown), 'SOLVE_PLAN')
    require(type(condition) is dict and set(condition) == {'quantity', 'op', 'value'} and
            type(condition['quantity']) is str and condition['op'] in ('>=', '<=') and
            _finite(condition['value']), 'SOLVE_CONDITION')
    cards = plan['cards']
    by_id = {c['id']: c for c in cards}
    matches = []
    for step in plan['steps']:
        require(step['tool_id'] in by_id, 'SOLVE_PLAN')
        for name, binding in step['inputs'].items():
            if name == unknown and binding['kind'] == 'parameter':
                matches.append((by_id[step['tool_id']], binding))
    require(len(matches) == 1 and plan['parameter_names'].get(matches[0][1]['ref']) == unknown, 'SOLVE_PLAN')
    card = matches[0][0]
    require(card['status'] == 'verified', 'SOLVE_PLAN')
    spec = card['parameters'][unknown]
    bounds = spec.get('search_range')
    require(type(bounds) is list and len(bounds) == 2 and all(_finite(x) for x in bounds)
            and bounds[0] < bounds[1], 'SOLVE_BRACKET')
    if bracket is None:
        low, high = bounds
    else:
        require(type(bracket) in (list, tuple) and len(bracket) == 2 and all(_finite(x) for x in bracket)
                and bounds[0] <= bracket[0] < bracket[1] <= bounds[1], 'SOLVE_BRACKET')
        low, high = bracket
    require((('min' not in spec or low >= spec['min']) and
             ('exclusive_min' not in spec or low > spec['exclusive_min']) and
             ('max' not in spec or high <= spec['max'])), 'SOLVE_BRACKET')
    final = by_id[plan['steps'][-1]['tool_id']]
    require(final['output']['name'] == condition['quantity'], 'SOLVE_CONDITION')

    def evaluate_at(x):
        params = dict(plan['parameters'], **{unknown: x})
        steps = run_steps(plan, cards, params, plan['parameter_names'], plan['conditions'])
        value = steps[-1]['output']['value']
        return value, value - condition['value'], steps

    points = [low + (high - low) * i / 16 for i in range(17)]
    curve = [evaluate_at(x)[0] for x in points]
    samples = [y - condition['value'] for y in curve]
    slopes = [b - a for a, b in zip(samples, samples[1:])]
    increasing = all(s > 0 for s in slopes)
    decreasing = all(s < 0 for s in slopes)
    require(increasing or decreasing, 'SOLVE_NOT_MONOTONIC')
    require(samples[0] * samples[-1] < 0, 'SOLVE_NO_ROOT')
    original_bracket = [low, high]
    iterations = 0
    while high - low > 1e-9 * max(1, abs((low + high) / 2)):
        require(iterations < 256, 'SOLVE_NO_ROOT')
        mid = low + (high - low) / 2
        _, residual, _ = evaluate_at(mid)
        if (residual < 0) == increasing:
            low = mid
        else:
            high = mid
        iterations += 1
    value = low + (high - low) / 2
    quantity, residual, steps = evaluate_at(value)
    delta = 1e-6 * max(1, abs(value))
    require(original_bracket[0] < value - delta and value + delta < original_bracket[1], 'SOLVE_NO_ROOT')

    def side(x):
        output, _, _ = evaluate_at(x)
        passed = output >= condition['value'] if condition['op'] == '>=' else output <= condition['value']
        return {'unknown_value': x, 'condition_value': output, 'satisfies': passed}

    left, right = side(value - delta), side(value + delta)
    require(left['satisfies'] != right['satisfies'], 'SOLVE_NO_ROOT')
    direction = 'minimum' if right['satisfies'] else 'maximum'
    # The sampled curve is kept for display: the condition quantity at each of the 17 points.
    return {'unknown': unknown, 'value': value, 'unit': spec['unit'], 'direction': direction,
            'samples': [{'unknown_value': x, 'condition_value': y} for x, y in zip(points, curve)],
            'bracket': original_bracket, 'iterations': iterations, 'residual': residual,
            'condition': dict(condition), 'condition_value': quantity,
            'left': left, 'right': right, 'steps': steps}
