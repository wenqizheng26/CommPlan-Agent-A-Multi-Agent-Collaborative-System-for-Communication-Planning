"""Collect explicit observations without the legacy manual override semantics."""
import math
import re
import unicodedata
from formula_rag.parsing import FIELDS, NUMBER, UNITS, QUANTITY_NUMBER, QUANTITY_PATTERN, quantity_value, convert, extract_request
from planning.services.input_domains import extract_domains, convert_domain, same, APPROX, field_for
from planning.services.fact_fields import FACT_FIELDS, field_unit


def diagnostic(code, message, **details):
    return {'code': code, 'message': message, 'details': details}


def overlaps(text, excerpt, span):
    """Whether an occurrence of excerpt in text overlaps span."""
    start = text.find(excerpt) if excerpt else -1
    while start >= 0:
        if start < span[1] and span[0] < start + len(excerpt):
            return True
        start = text.find(excerpt, start + 1)
    return False


BOTH_GAINS = re.compile(rf'(?:收发两端|两端|两边|收发|发射(?:和|与|及|、)接收|transmit and receive|both)\s*(?:的)?\s*(?:天线|antennas?)?\s*(?:增益|gains?)?'
                        rf'\s*(?:都是|都为|均为|各为|各是|各|均|都|为|是|are|of|each|[:：=])?\s*(?:each\s*)?'
                        rf'(?P<value>{NUMBER})\s*(?P<unit>dBi)(?![A-Za-z/\d])', re.I)
NUMERIC_FRAGMENT = re.compile(rf'\d|[-+负]?[零〇一二两三四五六七八九十百千万亿]+(?:点[零一二三四五六七八九]+)?'
                              rf'(?=\s*(?:个\s*)?(?:{UNITS}|左右|上下|出头|$))', re.I)


def collect_parameters(request, parsed, required, labeled=(), sources=None):
    """Rule observations plus model labels. A label only names a quantity the text already contains;
    where the rules bound the same quantity to another field, the label is left out and a question is raised.
    sources adds values from the fact store and card assumptions (requirement_facts.sources_for);
    where they differ from the text, the parameter is a conflict for the user to settle."""
    observations, diagnostics = {}, []
    # A margin requirement such as "余量至少10dB" is a comparison the rules refuse as a value.
    required_spans = [item['span'] for item in labeled if item['field'] == 'required_margin_db']
    domains, domain_issues = extract_domains(request['raw_text'])
    diagnostics.extend(domain_issues)
    masked = list(request['raw_text'])
    for issue in domain_issues:
        start, end = issue['details']['span']
        masked[start:end] = ' ' * (end-start)
    for domain in domains:
        start, end = domain['span']
        masked[start:end] = ' ' * (end-start)
        field = domain['field']
        observations.setdefault(field, []).append(dict(kind='user_text', source_ref=request['request_id'] + ':raw_text',
            span=domain['span'], value=domain['value'], unit=domain['unit']))
        prefix=re.split(r'[，,。；;\n？?！!]',request['raw_text'][:start])[-1]
        suffix=request['raw_text'][end:end+2]
        if re.search(r'不要|不是|并非|不采用|如果|假如|可能|也可以|大约|大概|约|近似|差不多',prefix) or suffix in {'左右','上下'}:
            diagnostics.append(diagnostic('SOURCE_AMBIGUOUS','区间或候选尚未明确采用，请重新说明。',field=field,excerpt=domain['excerpt'],span=domain['span']))
        diagnostics.append(diagnostic('EXPLICIT_NUMERIC_DOMAIN', '保留明确区间或离散候选；确认后逐端点或逐候选计算。',
            field=field, excerpt=domain['excerpt']))
    parsed = extract_request(''.join(masked)) if domains or domain_issues else parsed
    for match in APPROX.finditer(''.join(masked)):
        diagnostics.append(diagnostic('PARAMETER_APPROXIMATE', '近似表达没有明确误差范围，请指定区间或明确采用单值。',
            field=field_for(match.group()), excerpt=match.group(), span=list(match.span())))
    normalized_text = unicodedata.normalize('NFKC', ''.join(masked))
    alternatives = rf'(?<![A-Za-z0-9_.+-]){QUANTITY_NUMBER}\s*(?:{UNITS})?\s*(?:或者|或|、|至|到|~|～|±)\s*{QUANTITY_NUMBER}\s*{UNITS}'
    for match in re.finditer(alternatives, normalized_text, re.I):
        diagnostics.append(diagnostic('INPUT_PARSE_ISSUE', '发现范围或多个候选值，不能自动选取其中一个。',
                                      excerpt=match.group(), next_action='请明确本次采用的单个频率和距离。'))
    snippets = {k: list(v) for k, v in parsed['evidence'].items()}
    for issue in parsed['issues']:
        if issue['message'] == '发现不同数值，请明确采用哪一个':
            snippets.setdefault(issue['field'], []).extend(issue['evidence'])
        elif any(overlaps(request['raw_text'], issue.get('evidence'), s) for s in required_spans
                 if isinstance(issue.get('evidence'), str)):
            continue
        else:
            diagnostics.append(diagnostic('INPUT_PARSE_ISSUE', issue['message'],
                                          field=issue.get('field'), excerpt=issue.get('evidence'),
                                          next_action='请明确输入单个数值和匹配单位。'))
    occurrence = {}
    for field, excerpts in snippets.items():
        for excerpt in excerpts:
            normalized = unicodedata.normalize('NFKC', excerpt).replace('−', '-')
            matches = list(re.finditer(QUANTITY_PATTERN, normalized, re.I))
            if not matches:
                matches = list(re.finditer(rf'\(\s*(?P<unit>{UNITS})\s*\)\s*(?P<value>{NUMBER})', normalized, re.I))
            found = []
            for match in matches:
                try:
                    original, unit = quantity_value(match['value'], match['unit']), match['unit']
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
    # One gain written for both ends ("两端天线都是18dBi", "发射和接收天线增益各12dBi") is each end's gain;
    # a model label names one field per number, so the rule supplies both (TEACHER_CASES).
    for match in BOTH_GAINS.finditer(request['raw_text']):
        span = [match.start('value'), match.end('unit')]
        for field in ('tx_gain_dbi', 'rx_gain_dbi'):
            if any(o['span'] and o['span'][0] < span[1] and span[0] < o['span'][1] for o in observations.get(field, [])):
                continue
            observations.setdefault(field, []).append(dict(kind='user_text', source_ref=request['request_id'] + ':raw_text',
                span=span, value=float(match['value']), unit=match['unit']))
            diagnostics.append(diagnostic('SOURCE_EXCERPT', '用户原文来源（两端同值）', field=field,
                                          excerpt=match.group(), span=span))
    for item in labeled:
        field, (a, b) = item['field'], item['span']
        bound = {f for f, origins in observations.items() for o in origins
                 if o['span'] and o['span'][0] < b and a < o['span'][1]}
        if field in bound or (field == 'required_margin_db' and not bound):
            continue
        if bound:
            diagnostics.append(diagnostic('LABEL_CONFLICT', '原文数值的含义，规则与模型判断不一致。', field=field,
                                          rule_fields=sorted(bound), excerpt=request['raw_text'][a:b], span=[a, b]))
            continue
        observations.setdefault(field, []).append(dict(kind='user_text', source_ref=request['request_id'] + ':raw_text',
            span=[a, b], value=item['value'], unit=item['unit']))
        diagnostics.append(diagnostic('SOURCE_EXCERPT', '用户原文来源（模型标注）', field=field,
                                      excerpt=request['raw_text'][a:b], span=[a, b]))
    # Every explicitly labelled numeric fragment must be accounted for. A second
    # unitless/negative expression cannot silently disappear behind a valid value.
    labels = r'载波频率|工作频率|频率|载频|路径距离|通信距离|链路距离|距离|相距'
    for match in re.finditer(rf'(?:{labels})(?:(?!(?:{labels})|[，,。；;\n？?！!]).)*', request['raw_text']):
        fragment = match.group()
        if not NUMERIC_FRAGMENT.search(fragment):
            continue
        field = 'frequency_ghz' if re.match(r'载波频率|工作频率|频率|载频', fragment) else 'distance_km'
        local = [o for o in observations.get(field, []) if o['span'] and
                 match.start() <= o['span'][0] < match.end()]
        residue = list(fragment)
        for origin in local:
            a, b = origin['span']
            residue[max(0,a-match.start()):min(len(fragment),b-match.start())] = ' ' * (min(match.end(),b)-max(match.start(),a))
        # A later labelled parameter in the same clause is handled independently.
        remainder = re.split(r'(?:载波频率|工作频率|频率|载频|路径距离|通信距离|链路距离|距离|相距)', ''.join(residue), maxsplit=2)
        unexplained = remainder[1] if len(remainder)>1 else ''.join(residue)
        if NUMERIC_FRAGMENT.search(unexplained):
            diagnostics.append(diagnostic('INPUT_PARSE_ISSUE', '该参数包含尚未明确采用或缺少单位的数值，请重新填写完整表达。',
                                          field=field, excerpt=fragment, span=list(match.span())))
    for field, item in request['manual_parameters'].items():
        observations.setdefault(field, []).append(dict(kind='manual_form', source_ref=request['request_id'] + ':manual_parameters/' + field,
            span=None, value=item['value'], unit=item['unit']))
    # A second English labelled value without a unit cannot disappear behind a
    # valid first value. Check the original text, keeping all provenance offsets.
    from formula_rag.parsing import EN_FIELDS
    for field in ('frequency_ghz', 'distance_km'):
        labels = '|'.join(re.escape(a) for a in sorted(EN_FIELDS[field], key=len, reverse=True))
        pattern = rf'(?<![A-Za-z_])(?:{labels})(?![A-Za-z_]| from| to)\s*(?:is|of|at|[:=])?\s*(?P<value>{NUMBER})\s*(?P<unit>{UNITS})?(?![A-Za-z/\d])'
        for match in re.finditer(pattern, request['raw_text'], re.I):
            if not match['unit']:
                diagnostics.append(diagnostic('INPUT_PARSE_ISSUE', '该参数缺少单位，请重新填写完整表达。',
                                              field=field, excerpt=match.group(), span=list(match.span())))
    for field, origins in (sources or {}).items():
        observations.setdefault(field, []).extend(dict(o) for o in origins)
    parameters, conflicts = [], []
    for field in sorted(set(required) | set(observations)):
        origins = observations.get(field, [])
        for i, origin in enumerate(origins):
            origin['origin_id'] = f"{request['request_id']}:{field}:origin:{i}"
        # Fact-store geometry already comes in its card's unit.
        values = [o['value'] if field in FACT_FIELDS else convert_domain(field, o['value'], o['unit']) for o in origins]
        conflict = bool(values) and any(not same(v, values[0]) for v in values)
        status = 'conflicting' if conflict else ('user_provided' if values else 'missing')
        p = dict(parameter_id=f"{request['request_id']}:{field}", canonical_name=field,
                 value=values[0] if values and not conflict else None, unit=field_unit(field),
                 original_value=origins[0]['value'] if len(origins) == 1 else None,
                 original_unit=origins[0]['unit'] if len(origins) == 1 else None,
                 status=status, origins=origins, evidence_ids=[], created_revision=request['revision'])
        parameters.append(p)
        if conflict:
            conflicts.append(dict(conflict_id=p['parameter_id'] + ':conflict', parameter_name=field,
                                  origin_ids=[o['origin_id'] for o in origins], resolution=None))
    return parameters, conflicts, diagnostics
