"""Shared scope policy for single-link, one-way plans over the supported cards."""
import re
from formula_rag.parsing import extract_request
from planning.requirements_contract import require
from planning.services.plans import SUPPORTED


# A feasibility question is the model's reading of "link margin"; the rules have no keyword for it.
FEASIBILITY = r'能(?:不能)?通|能否(?:打)?通|通不通|够不够|够用|行不行|可行吗|能否满足|能不能满足|是否满足|满不满足|能满足吗'


def validate_target_semantics(model):
    for target in model.get('targets', []):
        parsed = extract_request(target['evidence'])
        feasible = target['id'] == 'link_margin' and re.search(FEASIBILITY, target['evidence'])
        require(target['id'] in SUPPORTED and (parsed['targets'] == [target['id']] or bool(feasible))
                and not parsed['unsupported_targets'], 'MODEL_TARGET_SEMANTICS')


def intent_conflict(request, parsed):
    target, condition = request['target'], request['condition']
    for clause in re.split(r'[，,。；;\n]', request['raw_text']):
        if re.search(r'(?:不要|不用|不必|无需|不)(?:再|进行)?(?:计算|求出|求|算)(?:.*?)(?:路径损耗|传播损耗|传输损耗)', clause):
            # An explicitly excluded task cannot be reinstated by a dropdown or
            # an affirmative clause elsewhere in the same request.
            return True
        if re.search(r'(?:不采用|不用|不要用|不使用|不按|非|不是)(?:.*?自由空间)', clause):
            return True
    return bool((target and parsed['target_origin'] == 'explicit_text' and set(parsed['targets']) != {target})
                or (condition == 'non_free_space' and 'free_space' in parsed['conditions'])
                or (condition in {'free_space','free_space_reference'} and 'non_free_space' in parsed['conditions']))


def outside_scope(text, parsed, targets, conditions):
    if parsed['unsupported_targets'] or any(t not in SUPPORTED for t in targets):
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
