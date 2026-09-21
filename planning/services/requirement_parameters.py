"""Collect explicit observations without the legacy manual override semantics."""
import math
import re
import unicodedata
from formula_rag.parsing import FIELDS, NUMBER, UNITS, convert, extract_request


def diagnostic(code, message, **details):
    return {'code': code, 'message': message, 'details': details}


def collect_parameters(request, parsed, required):
    observations, diagnostics = {}, []
    normalized_text = unicodedata.normalize('NFKC', request['raw_text'])
    alternatives = rf'{NUMBER}\s*(?:{UNITS})?\s*(?:或者|或|、|至|到|~|～|±)\s*{NUMBER}\s*{UNITS}'
    for match in re.finditer(alternatives, normalized_text, re.I):
        diagnostics.append(diagnostic('INPUT_PARSE_ISSUE', '发现范围或多个候选值，不能自动选取其中一个。',
                                      excerpt=match.group(), next_action='请明确本次采用的单个频率和距离。'))
    snippets = {k: list(v) for k, v in parsed['evidence'].items()}
    for issue in parsed['issues']:
        if issue['message'] == '发现不同数值，请明确采用哪一个':
            snippets.setdefault(issue['field'], []).extend(issue['evidence'])
        else:
            diagnostics.append(diagnostic('INPUT_PARSE_ISSUE', issue['message'],
                                          field=issue.get('field'), excerpt=issue.get('evidence'),
                                          next_action='请明确输入单个数值和匹配单位。'))
    occurrence = {}
    for field, excerpts in snippets.items():
        for excerpt in excerpts:
            normalized = unicodedata.normalize('NFKC', excerpt).replace('−', '-')
            matches = list(re.finditer(rf'(?P<value>{NUMBER})\s*(?P<unit>{UNITS})(?![A-Za-z/\d])', normalized, re.I))
            if not matches:
                matches = list(re.finditer(rf'\(\s*(?P<unit>{UNITS})\s*\)\s*(?P<value>{NUMBER})', normalized, re.I))
            found = []
            for match in matches:
                try:
                    original, unit = float(match['value']), match['unit']
                    value = convert(field, original, unit)
                    if math.isfinite(value):
                        found.append((original, unit))
                except ValueError:
                    pass
            # Refuse ambiguous source reconstruction rather than invent provenance.
            if len(found) != 1:
                diagnostics.append(diagnostic('SOURCE_AMBIGUOUS', '原始数值来源无法唯一定位，请分行明确参数。', field=field, excerpt=excerpt))
                continue
            start = request['raw_text'].find(excerpt, occurrence.get(excerpt, 0))
            span = [start, start + len(excerpt)] if start >= 0 else None
            if span:
                occurrence[excerpt] = span[1]
            original, unit = found[0]
            observations.setdefault(field, []).append(dict(kind='user_text', source_ref=request['request_id'] + ':raw_text',
                span=span, value=original, unit=unit))
            diagnostics.append(diagnostic('SOURCE_EXCERPT', '用户原文来源', field=field, excerpt=excerpt, span=span))
    for field, item in request['manual_parameters'].items():
        observations.setdefault(field, []).append(dict(kind='manual_form', source_ref=request['request_id'] + ':manual_parameters/' + field,
            span=None, value=item['value'], unit=item['unit']))
    parameters, conflicts = [], []
    for field in sorted(set(required) | set(observations)):
        origins = observations.get(field, [])
        for i, origin in enumerate(origins):
            origin['origin_id'] = f"{request['request_id']}:{field}:origin:{i}"
        values = [convert(field, o['value'], o['unit']) for o in origins]
        conflict = bool(values) and any(not math.isclose(v, values[0], rel_tol=1e-12, abs_tol=0) for v in values)
        status = 'conflicting' if conflict else ('user_provided' if values else 'missing')
        p = dict(parameter_id=f"{request['request_id']}:{field}", canonical_name=field,
                 value=values[0] if values and not conflict else None, unit=FIELDS[field][1],
                 original_value=origins[0]['value'] if len(origins) == 1 else None,
                 original_unit=origins[0]['unit'] if len(origins) == 1 else None,
                 status=status, origins=origins, evidence_ids=[], created_revision=request['revision'])
        parameters.append(p)
        if conflict:
            conflicts.append(dict(conflict_id=p['parameter_id'] + ':conflict', parameter_name=field,
                                  origin_ids=[o['origin_id'] for o in origins], resolution=None))
    return parameters, conflicts, diagnostics
