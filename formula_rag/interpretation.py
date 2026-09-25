"""Ground model intent in input text; physical assumptions still require explicit evidence."""
import re
from .parsing import extract_request

CONDITION_LABELS = {
    'free_space': '理想自由空间模型', 'free_space_reference': '自由空间基准',
    'non_free_space': '存在其他传播机制', 'maximum_doppler': '最大多普勒上界',
    'two_way': '双程传播',
}


def merge_interpretation(request, model, candidate_ids, manual_target=None, manual_condition=None):
    info = {'target_origin': 'manual' if manual_target else request.get('target_origin', 'text'),
            'targets': [], 'conditions': [], 'accepted': [], 'rejected': []}
    text = request['text']
    clauses = [m.group() for m in re.finditer(r'[^，,。；;\n？?！!]+', text)]

    def proposals(key):
        value = model.get(key, [])
        if not isinstance(value, list) or len(value) > 8:
            info['rejected'].append({'kind': key, 'reason': '模型结构不正确'})
            return []
        return value

    def grounded(item):
        return (isinstance(item, dict) and isinstance(item.get('id'), str)
                and isinstance(item.get('evidence'), str) and 2 <= len(item['evidence']) <= 300
                and item['evidence'] in text)

    targets = []
    for item in proposals('targets'):
        if not grounded(item) or item['id'] not in candidate_ids:
            info['rejected'].append({'kind': 'target', 'reason': '目标或原文证据无效'})
            continue
        enclosing = [c for c in clauses if item['evidence'] in c]
        # "能不能通""够不够" ask a question; they are not negations.
        if any(re.search(r'不(?:是|要|用|必|想|需)|不能|并非|无需', re.sub(r'(.)不\1', '', c)) for c in enclosing):
            info['rejected'].append({'kind': 'target', 'reason': '目标证据处于否定语境'})
            continue
        if request.get('unsupported_targets'):
            info['rejected'].append({'kind': 'target', 'reason': '不能用相似公式替代未支持的待求量'})
            continue
        if not re.search(r'计算|求|算|多大|多少|多强|够不够|够用|能否|能通|通不通|行不行|可行|满足|还剩|还有|上界|损耗|余量|功率|频移|底噪', item['evidence']):
            info['rejected'].append({'kind': 'target', 'reason': '证据未明确计算意图'})
            continue
        targets.append(item)
    if not manual_target and request.get('target_origin') != 'explicit_text' and targets:
        request['targets'] = list(dict.fromkeys(t['id'] for t in targets))
        info['target_origin'] = 'model'
        info['accepted'].extend({'kind': 'target', **t} for t in targets)

    conditions = set(request['conditions'])
    for item in proposals('conditions'):
        if not grounded(item) or item['id'] not in CONDITION_LABELS:
            info['rejected'].append({'kind': 'condition', 'reason': '条件或原文证据无效'})
            continue
        # Recheck whole clauses, never only a model-trimmed affirmative substring.
        enclosing = [c for c in clauses if item['evidence'] in c]
        supported = set()
        for clause in enclosing:
            supported.update(extract_request(clause)['conditions'])
            # An explicitly requested ideal baseline is a modelling instruction,
            # not an inference from a real environment such as sea or line of sight.
            if (re.search(r'(?:只|仅|按|采用|假设).*理想.*无反射.*(?:基准|参考)', clause)
                    and not re.search(r'不|是否|无法|未知|未确认|可能|如果', clause)):
                supported.update(('free_space', 'free_space_reference'))
        if item['id'] not in supported:
            info['rejected'].append({'kind': 'condition', 'id': item['id'], 'reason': '原文不足以确认该传播假设'})
            continue
        if manual_condition:
            continue
        conditions.add(item['id'])
        if item['id'] == 'free_space_reference':
            conditions.add('free_space')
        info['accepted'].append({'kind': 'condition', **item})
    request['conditions'] = sorted(conditions)
    info['targets'] = request['targets'][:]
    info['conditions'] = [{'id': c, 'label': CONDITION_LABELS.get(c, c)} for c in request['conditions']]
    info['condition_origin'] = 'manual' if manual_condition else ('model_checked' if any(a['kind'] == 'condition' for a in info['accepted']) else 'text')
    return info
