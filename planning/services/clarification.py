"""Task-level, source-grounded questions and versioned partial answers."""
import copy
import re
from planning.requirements_contract import digest, require
from planning.services.requirement_parameters import collect_parameters
from planning.services.input_domains import numbers, APPROX, format_value
from formula_rag.parsing import extract_request, FIELDS, UNITS, NUMBER
from planning.services.supplement import input_of, conversation_of

NAMES={'frequency_ghz':'载波频率','distance_km':'路径距离'}
# Link-budget inputs: one confirmed scalar each, any sign; card bounds are checked by planning.
BUDGET={'tx_power_dbm':'发射功率','tx_gain_dbi':'发射天线增益','rx_gain_dbi':'接收天线增益',
        'tx_loss_db':'发射馈线损耗','rx_loss_db':'接收馈线损耗','extra_loss_db':'额外损耗',
        'path_loss_db':'路径损耗','rx_power_dbm':'接收信号电平','rx_threshold_dbm':'接收门限',
        'reserve_db':'预留余量'}
LABELS=NAMES|BUDGET


def label_pattern(field):
    if field=='frequency_ghz':
        return r'载波频率|工作频率|频率|载频'
    if field=='distance_km':
        return r'路径距离|通信距离|链路距离|距离|相距'
    return '|'.join(re.escape(a) for a in sorted(FIELDS[field][2]+[BUDGET[field]],key=len,reverse=True))


EXAMPLES={'tx_power_dbm':'30dBm','rx_threshold_dbm':'-100dBm','rx_power_dbm':'-70dBm','path_loss_db':'120dB',
          'reserve_db':'10dB','extra_loss_db':'0dB'}


def example(field):
    return EXAMPLES.get(field,{'dBi':'10dBi','dB':'2dB'}.get(FIELDS[field][1],'1'+FIELDS[field][1]))


def issues_for(state):
    report=state.get('report') or {}
    if state['status'] not in {'AWAITING_INPUT','NEEDS_MODEL'}:
        return []
    issues=[]
    def add(kind,field,title,detail,excerpt='',choices=()):
        key='issue-'+digest([kind,field,excerpt])[:20]
        if any(i['id']==key for i in issues):
            return
        issues.append(dict(id=key,kind=kind,field=field,title=title,detail=detail,excerpt=excerpt,
                           choices=list(choices),status='open',blocking=True,source='requirements'))
    if state['status']=='NEEDS_MODEL':
        add('capability','task','需求明确，但当前模型不支持','当前支持自由空间条件下的路径损耗、接收信号电平与链路余量。可编辑任务重新定义目标；系统不会擅自替换你的需求。')
        return issues
    diagnostics=report.get('diagnostics',[])
    if any(d['code']=='INTENT_CONFLICT' for d in diagnostics):
        add('conflict','task','目标或模型条件存在冲突','请直接编辑当前任务，统一原文和手工模型条件。')
        return issues
    if not report.get('targets'):
        add('clarification','goal','你希望得到什么结果？','先明确目标，再判断能力与所需参数；选择不代表当前系统支持。',
            choices=[dict(value='fspl_ghz',label='路径损耗'),dict(value='received_power',label='接收信号电平'),dict(value='link_margin',label='链路余量'),
                     dict(value='link_feasibility',label='判断能否通信'),dict(value='scheme_comparison',label='比较方案')])
        return issues
    if any(d['code']=='MISSING_CONDITION' for d in diagnostics):
        add('clarification','condition','是否明确只做自由空间基准？','自由空间基准不代表实际海面或遮挡环境。',
            choices=[dict(value='free_space_reference',label='是，只计算自由空间基准'),dict(value='non_free_space',label='否，需要实际环境传播评估')])
    params={p['canonical_name']:p for p in report.get('parameters_proposal',[])}
    approx={d['details'].get('field'):d['details'] for d in diagnostics if d['code']=='PARAMETER_APPROXIMATE'}
    for field,p in params.items():
        if field not in NAMES:
            continue
        if p['status']=='conflicting':
            add('conflict',field,NAMES[field]+'有多个冲突来源','输入最终采用的单值、区间或离散候选（含单位）。',
                excerpt=' / '.join(format_value(o['value'])+' '+o['unit'] for o in p['origins']))
        elif field in approx:
            add('clarification',field,NAMES[field]+'的近似范围是什么？','填写明确范围（例如 2±0.1GHz），或明确按单值计算（例如 2GHz）。',excerpt=approx[field]['excerpt'])
        elif p['status']=='missing':
            add('missing',field,'请补充'+NAMES[field],'可输入单值、区间或离散候选，必须包含单位。')
        elif min(numbers(p['value']))<=0:
            add('invalid',field,NAMES[field]+'必须大于零','区间的所有端点与候选都必须大于零。')
    # Link-budget inputs are answered one field at a time, like frequency and distance.
    unit=lambda f: FIELDS[f][1]
    for field in BUDGET:  # link order, transmitter first
        p=params.get(field)
        if not p:
            continue
        if p['status']=='conflicting':
            add('conflict',field,BUDGET[field]+'有多个冲突来源',f'输入最终采用的单个数值（含单位，例如 {example(field)}）。',
                excerpt=' / '.join(format_value(o['value'])+' '+o['unit'] for o in p['origins']))
        elif p['status']=='missing':
            add('missing',field,f'请补充{BUDGET[field]}（{unit(field)}）',f'输入单个数值和单位，例如 {example(field)}。')
    for d in diagnostics:
        if d['code']=='INPUT_DOMAIN_INVALID':
            for field in d['details'].get('fields') or []:
                if field in BUDGET:
                    add('invalid',field,BUDGET[field]+'超出公式定义域','按登记公式，该量不能取当前值；请重新输入（含单位）。',
                        excerpt=format_value(params[field]['value'])+' '+params[field]['unit'] if field in params else '')
    for d in diagnostics:
        if d['code'] in {'PLAN_DOMAIN_UNSUPPORTED','PLAN_TARGETS_SPLIT'}:
            add('clarification','task','计算计划需要调整',d['message'])
    for d in diagnostics:
        if d['code'] in {'SOURCE_AMBIGUOUS','INPUT_PARSE_ISSUE'}:
            field=d['details'].get('field')
            if not any(i['field']==field for i in issues):
                add('clarification',field if field in LABELS else 'task','有一项数值表达需要澄清',d['message'],excerpt=str(d['details'].get('excerpt','')))
    for pending in (state.get('conversation') or {}).get('pending',[]):
        # Same-field questions share one answer; unrelated text remains separate.
        field=pending.get('field')
        if field and any(i['field']==field for i in issues):
            continue
        add('pending',field or ('pending:'+pending['turn_id']),'有一条补充尚未明确',pending['question'],
            excerpt=pending['turn_id'],choices=[dict(value='withdraw',label='撤回这条补充')])
    if state.get('review_assessment',{}):
        decision=state['review_assessment']['role']['proposal']['decision']
        if decision=='needs_input':
            add('review','task','审查要求重新核对模型假设','请编辑需求或补充明确的模型条件，再重新确认。')
    if not issues:
        for question in report.get('questions',[]):
            add('clarification','task','请澄清当前描述',question,excerpt=question)
    return issues


def attach_issues(state,previous=None):
    new=issues_for(state)
    previous=previous or {}
    old=(previous.get('input_issues') or issues_for(previous)) if previous else []
    history=copy.deepcopy(previous.get('resolved_input_issues',[]))
    for issue in old:
        if not any(i['id']==issue['id'] for i in new):
            history.append(dict(issue,status='resolved',resolved_revision=state['revision']))
    state['input_issues']=new
    state['resolved_input_issues']=history
    kinds={i['kind'] for i in new}
    state['waiting_reason']=('模型能力不足' if 'capability' in kinds else '需求待澄清' if kinds & {'clarification','pending','review'}
                             else '待消解冲突' if 'conflict' in kinds else '待补充或修正参数' if new else None)
    return state


def replace_parameter(request, report, field, answer):
    probe=dict(schema_version='1.0.0',task_id='answer',revision=0,request_id='answer',raw_text=answer,
               manual_parameters={},condition=None,target=None)
    require(field in LABELS,'ANSWER_REQUIRES_EDIT')
    labels=label_pattern(field)
    parameters,conflicts,diagnostics=collect_parameters(probe,extract_request(answer),[])
    # A bare budget value such as "30dBm" carries no field; the question names it.
    if not parameters and field in BUDGET:
        answer=BUDGET[field]+answer
        probe['raw_text']=answer
        parameters,conflicts,diagnostics=collect_parameters(probe,extract_request(answer),[])
    require(len(parameters)==1 and parameters[0]['canonical_name']==field and not conflicts
            and parameters[0]['value'] is not None, 'ANSWER_PARAMETER_REQUIRED')
    # Frequency and distance may be domains but must be positive; budget inputs are one scalar.
    value=parameters[0]['value']
    require(min(numbers(value))>0 if field in NAMES else type(value) is not dict, 'ANSWER_PARAMETER_REQUIRED')
    require(not any(d['code'] in {'INPUT_PARSE_ISSUE','SOURCE_AMBIGUOUS','PARAMETER_APPROXIMATE'} for d in diagnostics), 'ANSWER_STILL_AMBIGUOUS')
    # Only accept a numeric expression and optional field label, no silently ignored prose.
    param=parameters[0]
    spans=[o['span'] for o in param['origins'] if o['span']]
    require(len(spans)==1,'ANSWER_STILL_AMBIGUOUS')
    residual=answer[:spans[0][0]]+answer[spans[0][1]:]
    residual=re.sub(rf'{labels}|采用|确定为|按|单值|计算|为|[\s=：:，,。;；]', '',residual)
    require(not residual,'ANSWER_STILL_AMBIGUOUS')
    # Re-collect against the current text: earlier answers may have shifted offsets.
    current_probe=dict(probe, **request)
    old_parameters, _, current_diagnostics=collect_parameters(current_probe,extract_request(request['raw_text']),[])
    old=next((p for p in old_parameters if p['canonical_name']==field),None)
    remove=[o['span'] for o in old['origins'] if o['kind']=='user_text' and o['span']] if old else []
    text=request['raw_text']
    units=r'GHz|MHz|kHz|Hz|吉赫兹|兆赫兹|千赫兹|赫兹|km|千米|公里|m|米' if field in NAMES else UNITS
    # Consume the whole old numeric expression, including approximation/negation
    # and incomplete units. Never rewrite unrelated prose in that clause.
    fragment=re.compile(rf'(?:{labels})(?:\s|为|是|不是|不为|不确定|未知|大约|大概|约|近似|差不多|改为|采用|[:：=])*'
                        rf'[-+0-9.eE\s±/~～–—至到或、]*(?:{units})?'
                        rf'(?:\s*(?:或者|或|、)\s*[-+0-9.eE]+\s*(?:{units})?)*'
                        r'(?:左右|上下)?',re.I)
    for m in fragment.finditer(text):
        if re.search(r'\d',m.group()):
            remove.append(list(m.span()))
    for d in current_diagnostics:
        if d['code']=='PARAMETER_APPROXIMATE' and d['details'].get('field')==field:
            remove.append(d['details']['span'])
    merged=[]
    for start,end in sorted(remove):
        if merged and start <= merged[-1][1]:
            merged[-1][1]=max(end,merged[-1][1])
        else:
            merged.append([start,end])
    numeric=answer[slice(*spans[0])].strip()
    if field in BUDGET:  # the span may include the label; keep only the value and unit
        numeric=re.search(rf'{NUMBER}\s*(?:{UNITS})(?![A-Za-z/\d])',numeric,re.I).group()
    replacement=LABELS[field]+numeric
    if merged:
        for i,(start,end) in reversed(list(enumerate(merged))):
            text=text[:start]+(replacement if i==0 else '')+text[end:]
    else:
        text=text.rstrip()+'\n'+replacement+'。'
    request['raw_text']=text
    if field in request['manual_parameters'] and type(param['value']) is not dict:
        request['manual_parameters'][field]={'value':param['value'],'unit':param['unit']}
    else:
        request['manual_parameters'].pop(field,None)
    # The replacement must survive parsing with exactly the user's chosen value.
    check, conflicts, _=collect_parameters(dict(probe,**request),extract_request(text),[])
    actual=next((p for p in check if p['canonical_name']==field),None)
    require(actual is not None and actual['value']==param['value'] and not any(c['parameter_name']==field for c in conflicts),
            'ANSWER_REPLACEMENT_CONFLICT')



def apply_answers(current,answers,event_id):
    issues={i['id']:i for i in issues_for(current)}
    require(type(answers) is dict and 0<len(answers)<=20,'INVALID_ANSWERS')
    require(set(answers)<=set(issues),'STALE_QUESTION')
    request=input_of(current);before=copy.deepcopy(request);conversation=conversation_of(current)
    answered=[]
    for key,value in answers.items():
        require(type(value) is str and 0<len(value.strip())<=500,'INVALID_ANSWER')
        issue=issues[key];field=issue['field'];value=value.strip()
        if issue['kind']=='pending' and value=='withdraw':
            conversation['pending']=[p for p in conversation['pending'] if p['turn_id']!=issue['excerpt']]
        elif field=='goal':
            require(value in {c['value'] for c in issue['choices']},'INVALID_ANSWER_CHOICE')
            request['target']=value
        elif field=='condition':
            require(value in {c['value'] for c in issue['choices']},'INVALID_ANSWER_CHOICE')
            request['condition']=value
        elif field in LABELS:
            replace_parameter(request,current['report'],field,value)
            conversation['pending']=[p for p in conversation['pending'] if p.get('field')!=field]
        else:
            raise ValueError('ANSWER_REQUIRES_EDIT')
        display=next((c['label'] for c in issue['choices'] if c['value']==value),value)
        answered.append(dict(issue_id=key,title=issue['title'],answer=value,display=display))
    request['raw_text']=re.sub(r'(?:载波频率|频率|路径距离|距离)\s*(?=[，,。；;\n]|$)', '',request['raw_text'])
    require(len(request['raw_text'])<=12000,'MERGED_TEXT_TOO_LONG')
    conversation['turns'].append(dict(turn_id=event_id,number=len(conversation['turns'])+1,kind='answer',
        message='；'.join(x['title']+'：'+x['display'] for x in answered),before=before,after=copy.deepcopy(request),
        changes=[dict(field='task',before=before['raw_text'],after=request['raw_text'])],questions=[],mode='user_answer',
        applied=True,answers=answered))
    return request,conversation
