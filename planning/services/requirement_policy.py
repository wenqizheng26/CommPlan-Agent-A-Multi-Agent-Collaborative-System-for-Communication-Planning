"""Shared scope policy for the single-link, one-way free-space entry point."""
import re
from formula_rag.parsing import extract_request
from planning.requirements_contract import require


def validate_target_semantics(model):
    for target in model.get('targets', []):
        parsed = extract_request(target['evidence'])
        require(target['id'] == 'fspl_ghz' and parsed['targets'] == ['fspl_ghz']
                and not parsed['unsupported_targets'], 'MODEL_TARGET_SEMANTICS')


def intent_conflict(request, parsed):
    target, condition = request['target'], request['condition']
    return bool((target and parsed['target_origin'] == 'explicit_text' and set(parsed['targets']) != {target})
                or (condition == 'non_free_space' and 'free_space' in parsed['conditions'])
                or (condition in {'free_space','free_space_reference'} and 'non_free_space' in parsed['conditions']))


def outside_scope(text, parsed, targets, conditions):
    if parsed['unsupported_targets'] or any(t != 'fspl_ghz' for t in targets):
        return True
    for clause in re.split(r'[，,。；;\n]', text):
        # Only a complete, unambiguous disclaimer is exempt. A negative word
        # inside a contrast or double negative cannot erase a positive request.
        if re.fullmatch(r'\s*(?:不代表|不要求|无需|不计算|不要计算|不求)(?:真实|实际)?(?:海面|海上|海域)(?:传播)?损耗\s*', clause):
            continue
        if re.search(r'(?:真实|实际).{0,8}(?:海面|海上|海域).{0,8}(?:损耗|传播)', clause):
            return True
        if re.search(r'双程|往返|雷达回波|双向雷达', clause):
            return True
    return 'non_free_space' in conditions and 'free_space_reference' not in conditions
