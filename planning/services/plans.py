"""Program-built calculation plans: chain registered cards by output/input name.

This is the deterministic planner (and later the fallback for model-written plans).
It never supplies a value; it only decides which verified cards run, in which order,
and which inputs the user still has to provide.
"""
import math
from planning.requirements_contract import digest, require
from planning.services.input_domains import numbers

# What a user can ask for. Others stay retrievable only.
TARGETS = ('fspl_ghz', 'received_power', 'link_margin')
# Geometry from site records: the straight-line distance, and the radio horizon it must stay within.
GEOMETRY = ('slant_range_wgs84', 'radio_horizon')
# Cards that may appear in a plan in this version.
SUPPORTED = TARGETS + GEOMETRY
OBJECTIVES = {'fspl_ghz': '自由空间单链路损耗基准',
              'received_power': '接收信号电平（链路预算）',
              'link_margin': '链路余量（链路预算）'}
MAX_STEPS = 8
LINE_OF_SIGHT = dict(check_id='line-of-sight', kind='line_of_sight',
                     distance='slant_range_wgs84-step', horizon='radio_horizon-step')


def producers(cards, exclude=()):
    out = {}
    for card in cards:
        if card['id'] in SUPPORTED and card['id'] not in exclude and card['status'] == 'verified':
            out.setdefault(card['output']['name'], []).append(card['id'])
    return out


def chain(target, cards, known, exclude=GEOMETRY):
    """Backward-chain from target. Known names stay inputs; others come from the unique producer.

    Cards in exclude never produce an input. By default that is the geometry: the distance comes
    from coordinates only when both sites were found in the fact store. Returns (order, leaves):
    card ids in execution order, and input names the user or the fact store provides.
    """
    by_id = {c['id']: c for c in cards}
    made = producers(cards, exclude)
    order, leaves, visiting = [], [], set()

    def visit(card_id):
        if card_id in order:
            return
        require(card_id in by_id and card_id in SUPPORTED, 'PLAN_CARD')
        require(card_id not in visiting, 'PLAN_CYCLE')
        visiting.add(card_id)
        for name in by_id[card_id]['parameters']:
            options = made.get(name, [])
            if name in known or not options:
                if name not in leaves:
                    leaves.append(name)
                continue
            require(len(options) == 1, 'PLAN_AMBIGUOUS_PRODUCER')
            visit(options[0])
        visiting.remove(card_id)
        order.append(card_id)

    visit(target)
    require(len(order) <= MAX_STEPS, 'PLAN_TOO_LONG')
    return order, leaves


def final_target(targets, cards):
    """The one requested quantity whose chain covers every other requested one, else None."""
    if not targets or any(t not in TARGETS for t in targets):
        return None
    for target in targets:
        order, _ = chain(target, cards, set())
        if set(targets) <= set(order):
            return target
    return None


def with_line_of_sight(order):
    """A distance taken from coordinates is used only within the radio horizon (H2), so the horizon runs next."""
    if 'slant_range_wgs84' not in order:
        return list(order)
    i = order.index('slant_range_wgs84') + 1
    return list(order[:i]) + ['radio_horizon'] + list(order[i:])


def plan_for(request, order, cards, parameters, evidence_ids, requirement=None, solve_if_unmet=None, notes=()):
    """notes are this task's own assumptions (values the user did not state); they come before card notes."""
    by_id = {c['id']: c for c in cards}
    by_name = {p['canonical_name']: p for p in parameters}
    step_ids = {card_id: ('fspl-step' if card_id == 'fspl_ghz' else card_id + '-step') for card_id in order}
    output_of = {by_id[card_id]['output']['name']: card_id for card_id in order}
    steps, required, assumptions = [], [], list(dict.fromkeys(notes))
    for card_id in order:
        card = by_id[card_id]
        inputs, dependencies = {}, []
        for name, spec in card['parameters'].items():
            source = output_of.get(name)
            if source is not None and source != card_id and name not in by_name:
                inputs[name] = dict(kind='step', ref=step_ids[source], unit=spec['unit'])
                dependencies.append(step_ids[source])
            else:
                inputs[name] = dict(kind='parameter', ref=by_name[name]['parameter_id'], unit=spec['unit'])
                if name not in required:
                    required.append(name)
        steps.append(dict(step_id=step_ids[card_id], tool_id=card_id, inputs=inputs, expected_unit=card['output']['unit'],
                          dependencies=dependencies, required_conditions=list(card['applicability']['requires'])))
        assumptions.extend(n for n in card['applicability'].get('notes', []) if n not in assumptions)
    plan = dict(plan_id=request['request_id'] + ':plan', task_id=request['task_id'], revision=request['revision'],
                objective=OBJECTIVES[order[-1]], selected_model=list(order),
                required_parameters=required, assumptions=assumptions,
                evidence_ids=evidence_ids, steps=steps)
    # Only plans that need them carry these keys, so earlier plans keep their shape and hash.
    if 'slant_range_wgs84' in order and 'radio_horizon' in order:
        plan['checks'] = [dict(LINE_OF_SIGHT)]
    if notes:
        plan['assumed'] = list(dict.fromkeys(notes))  # the task's own assumptions, also first in assumptions
    if requirement:
        plan['requirement'] = dict(requirement)
    if solve_if_unmet:
        plan['solve_if_unmet'] = solve_if_unmet
    plan['plan_hash'] = digest(plan)
    return plan


def requires_free_space(order, cards):
    by_id = {c['id']: c for c in cards}
    return any('free_space' in by_id[i]['applicability']['requires'] for i in order)


def bound_issues(order, cards, values):
    """Declared card domains for user-provided inputs, checked before confirmation."""
    by_id = {c['id']: c for c in cards}
    bad = []
    for card_id in order:
        for name, spec in by_id[card_id]['parameters'].items():
            if name not in values or name in bad:
                continue
            for x in numbers(values[name]):
                if (('min' in spec and x < spec['min']) or ('exclusive_min' in spec and x <= spec['exclusive_min'])
                        or ('max' in spec and x > spec['max']) or not math.isfinite(x)):
                    bad.append(name)
                    break
    return bad
