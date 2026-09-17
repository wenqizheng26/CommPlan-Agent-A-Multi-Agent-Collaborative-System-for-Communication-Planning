"""Versioned, deterministic scope checks; neither LLM output nor RAG text is authority."""
import math
import re
import unicodedata

RULE_VERSION = 'p1-1.0.0'
STANDARD_NOISE_CLAUSE = '确认采用标准290K噪声路线'
NOISE_QUESTION = (
    '请确认噪声参考：输入温度/谱密度是否仅为接收机输入端的源噪声，尚未包含接收机噪声？'
    '噪声系数 NF 是否按 T0=290 K 定义？当前仅支持匹配源温度为 290 K 的标准路线。'
    '若确实满足，可另起一行输入“确认采用标准290K噪声路线”，并明确输入温度或谱密度；'
    '其他源温度或已含接收机噪声的系统总噪声路线待后续公式版本支持。'
)
FARFIELD_NOTE = '当前只检查了明显异常的距离/波长组合，未完整验证天线远场条件；结果仅用于所声明的自由空间基准。'


def noise_confirmation(text, explicit=None):
    """Accept a typed user confirmation or a whole affirmative clause, never model inference."""
    if explicit is not None:
        if (not isinstance(explicit, dict) or set(explicit) != {'mode', 'confirmed'}
                or explicit['mode'] != 'standard_290k' or type(explicit['confirmed']) is not bool):
            raise ValueError('noise_reference 必须包含 mode="standard_290k" 与布尔 confirmed；其他噪声路线暂未支持。')
        return {**explicit, 'origin': 'structured_input'}
    normalized = unicodedata.normalize('NFKC', text)
    clauses = [re.sub(r'\s+', '', c).casefold() for c in re.split(r'[,;。\n]', normalized)]
    confirmed = STANDARD_NOISE_CLAUSE.casefold() in clauses
    # Other mentions of this route (negation, quotation, questions) cannot be
    # silently overruled by an affirmative clause elsewhere in the same request.
    if any('标准290k噪声路线' in c and c != STANDARD_NOISE_CLAUSE.casefold() for c in clauses):
        confirmed = False
    return {'mode': 'standard_290k', 'confirmed': confirmed,
            'origin': 'explicit_text' if confirmed else 'unconfirmed'}


def _issue(code, message, fields=(), severity='needs_input'):
    return {'code': code, 'severity': severity, 'message': message, 'fields': list(fields),
            'rule_version': RULE_VERSION}


def model_coverage_issue():
    return _issue('model_coverage_gap',
        '当前传播模型库只覆盖自由空间基准，未覆盖实际海面反射、遮挡等传播机制。'
        '请明确此次是否只求自由空间基准；若求真实环境传播损耗，需补充经审核的环境模型及其条件，当前无法给出实际传播数值。')


def _finite(value, positive=False):
    try:
        return (not isinstance(value, bool) and isinstance(value, (float, int))
                and math.isfinite(value) and (not positive or value > 0))
    except OverflowError:
        return False


def scope_issues(formula_id, values, request):
    if formula_id == 'fspl_ghz':
        f, d = values.get('frequency_ghz'), values.get('distance_km')
        if _finite(f, positive=True) and _finite(d, positive=True):
            # log(4*pi*d*f/c), with km/GHz converted to m/Hz, avoids
            # multiplication overflow. This rejects an obvious near-field
            # failure only; it is NOT a sufficient far-field criterion.
            separation_log = math.log10(d) + math.log10(f) + 12 + math.log10(4 * math.pi / 299792458)
            if separation_log <= 0:
                return [_issue('free_space_nearfield',
                    '距离不大于 λ/(4π)，该自由空间远场关系不能作为有效传播损耗使用。'
                    '请核对距离与频率单位；若确为近场场景，需要另选适用模型，不能把负损耗截为零。',
                    ('frequency_ghz', 'distance_km'), 'not_applicable')]
    if formula_id == 'receiver_threshold':
        reference = request['noise_reference']
        if not reference['confirmed']:
            return [_issue('noise_reference_unconfirmed', NOISE_QUESTION,
                           ('temperature_k', 'noise_density_dbm_hz', 'noise_figure_db'))]
        temperature, density = values.get('temperature_k'), values.get('noise_density_dbm_hz')
        exact_density = 10 * math.log10(1.380649e-23 * 290 * 1000)
        # -174 is a declared engineering rounding of k*290, not a default.
        # Keep the supplied number unchanged, and disclose the approximation.
        mismatch = (_finite(temperature) and temperature != 290)
        if _finite(density):
            mismatch |= not any(math.isclose(density, ref, abs_tol=1e-8, rel_tol=0)
                                for ref in (exact_density, -174))
        if mismatch:
            return [_issue('noise_reference_mismatch',
                '已确认的标准 290 K 路线与输入温度或谱密度不一致。当前仅支持源温度 290 K、'
                '不含接收机噪声的 kT 谱密度（或明确输入其工程舍入值 −174 dBm/Hz）及标准 NF。'
                '请核对定义后重新输入；若源温度确为其他值，本版本暂不支持该门限路线，不能直接相加 NF。',
                ('temperature_k', 'noise_density_dbm_hz', 'noise_figure_db'), 'not_applicable')]
    return []


def result_issues(formula_id, value):
    # Until P2 removes the rounded FSPL constant, its narrow transition region
    # can still give negative arithmetic just above lambda/(4*pi).
    if formula_id == 'fspl_ghz' and value < 0:
        return [_issue('free_space_nearfield',
            '当前舍入形式给出负损耗，距离位于远场公式的明显异常边界附近；该值不能作为有效传播损耗，需核对单位并选择适用模型。',
            ('frequency_ghz', 'distance_km'), 'not_applicable')]
    return []


def describe_result(formula_id, value):
    if formula_id == 'link_margin':
        code = 'below_threshold' if value < 0 else 'above_threshold' if value > 0 else 'at_threshold'
        meaning = ('扣除预留余量后低于门限' if value < 0 else '扣除预留余量后高于门限' if value > 0 else '扣除预留余量后恰好等于门限')
        return {'code': code, 'difference_db': abs(value), 'rule_version': RULE_VERSION,
                'message': f'{meaning}，差额 {abs(value):.8f} dB。判断使用未舍入数值，仅表示所填预算条件下的门限关系，不保证现场可靠通信。'}
    if formula_id in ('received_power', 'receiver_threshold', 'thermal_noise'):
        return {'code': 'power_level', 'rule_version': RULE_VERSION,
                'message': 'dBm 是相对于 1 mW 的功率电平；负 dBm 表示低于 1 mW，不代表负功率或计算错误。'}
    return None
