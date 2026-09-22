"""Bounded endpoint evaluation for monotone positive-frequency FSPL only."""
import math
from formula_rag import core
from formula_rag.applicability import scope_issues, result_issues
from planning.requirements_contract import require
from planning.services.input_domains import numbers, scenarios, format_value


def groups(parameters):
    fixed = {k:v for k,v in parameters.items() if not (type(v) is dict and v['kind']=='interval')}
    intervals = {k:v for k,v in parameters.items() if type(v) is dict and v['kind']=='interval'}
    return [dict(case, **intervals) for case in scenarios(fixed)]


def evaluate_domains(card, parameters, conditions):
    require(card['id']=='fspl_ghz', 'DOMAIN_MODEL_NOT_SUPPORTED')
    # Cartesian bounds make no correlation assumption. Every corner is checked.
    require(all(min(numbers(v)) > 0 for v in parameters.values()), 'INPUT_DOMAIN_INVALID')
    scenarios(parameters)  # enforce total evaluation budget before calling a tool
    outputs=[]
    for group in groups(parameters):
        values=[]
        for case in scenarios(group):
            require(not scope_issues(card['id'], case, {'conditions':conditions}), 'MODEL_NOT_APPLICABLE')
            result=core.evaluate(card,case)
            require(result['status']=='ok' and result['unit']=='dB' and result['inputs']==case, 'CALCULATION_DOMAIN_ERROR')
            val=result.get('value')
            require(type(val) in (int,float) and math.isfinite(val) and not result_issues(card['id'],val), 'NONFINITE_RESULT')
            values.append(val)
        ranged=any(type(v) is dict for v in group.values())
        value=dict(kind='interval',lower=min(values),upper=max(values)) if ranged else values[0]
        outputs.append(dict(name=card['output']['name'],value=value,unit='dB',inputs=group))
    return outputs


def validate_domains(outputs, parameters, model):
    expected=groups(parameters)
    if type(outputs) is not list or len(outputs)!=len(expected):
        return False,False
    domain_ok, magnitude_ok=True,True
    for output, group in zip(outputs,expected):
        reference=[20*(math.log10(c['frequency_ghz'])+math.log10(c['distance_km'])+12+math.log10(4*math.pi/299792458)) for c in scenarios(group)]
        bounds=[min(reference),max(reference)] if any(type(v) is dict for v in group.values()) else [reference[0]]
        try:
            vals=numbers(output['value'])
            interval=type(output['value']) is dict and output['value'].get('kind')=='interval'
            domain_ok &= (set(output)=={'name','value','unit','inputs'} and output['inputs']==group
                          and output['unit']=='dB' and output['name']==model['output']['name']
                          and interval==(len(bounds)==2) and min(vals)>=0)
            magnitude_ok &= len(vals)==len(bounds) and all(abs(a-b)<=0.05 for a,b in zip(vals,bounds))
        except (ValueError,KeyError,TypeError):
            return False,False
    return bool(domain_ok),bool(magnitude_ok)


def conclusion(outputs):
    parts=[]
    for index, output in enumerate(outputs,1):
        v=output['value']
        text=(f"{v['lower']:.2f}–{v['upper']:.2f} dB（输入范围对应的计算范围，非置信区间）" if type(v) is dict
              else f'{v:.2f} dB')
        prefix=(f"候选 {index}：" if len(outputs)>1 else '')
        parts.append(prefix+text)
    return '按已确认自由空间条件，'+'；'.join(parts)+'。'
