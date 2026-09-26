"""Extract explicit quantities. No LLM-provided number is trusted here."""
import math
import re
import unicodedata


FIELDS = {
    'bit_rate_bps': ('比特速率', 'bit/s', ['比特速率', '数据比特率', '比特率']),
    'ebn0_db': ('解调门限 Eb/N0', 'dB', ['解调门限Eb/N0', '解调门限Eb/N0', 'Eb/N0', 'Eb/No', '解调门限']),
    'engineering_loss_db': ('工程损失', 'dB', ['工程损失', '实现损失']),
    'noise_figure_db': ('接收机噪声系数', 'dB', ['收信机噪声系数', '接收机噪声系数', '噪声系数']),
    'noise_density_dbm_hz': ('噪声谱密度', 'dBm/Hz', ['噪声功率谱密度', '噪声谱密度']),
    'drift_loss_db': ('平台漂移损耗', 'dB', ['空中平台漂移损耗', '平台漂移损耗']),
    'frequency_ghz': ('工作频率', 'GHz', ['工作频率', '载波频率', '频率', '载频']),
    'distance_km': ('通信距离', 'km', ['通信距离', '链路距离', '链路长度', '距离', '相距']),
    'speed_kmh': ('相对速度', 'km/h', ['相对速率', '相对速度', '径向速度', '速度']),
    'bandwidth_hz': ('噪声带宽', 'Hz', ['噪声带宽', '带宽']),
    'temperature_k': ('噪声温度', 'K', ['噪声温度', '温度']),
    'tx_power_dbm': ('发射功率', 'dBm', ['发射信号电平', '发射功率', '发射电平']),
    'tx_gain_dbi': ('发射天线增益', 'dBi', ['发射天线增益', '发天线增益', '发射增益']),
    'rx_gain_dbi': ('接收天线增益', 'dBi', ['接收天线增益', '收天线增益', '接收增益']),
    'tx_loss_db': ('发馈线损耗', 'dB', ['发射馈线损耗', '发馈线损耗', '发端馈损']),
    'rx_loss_db': ('收馈线损耗', 'dB', ['接收馈线损耗', '收馈线损耗', '收端馈损']),
    'path_loss_db': ('路径损耗', 'dB', ['总传输损耗', '传输损耗', '传播损耗', '路径损耗']),
    'extra_loss_db': ('额外损耗', 'dB', ['额外损耗', '其他损耗', '附加损耗']),
    'rx_power_dbm': ('接收信号电平', 'dBm', ['接收信号电平', '接收功率', '接收电平']),
    'rx_threshold_dbm': ('接收门限', 'dBm', ['接收灵敏度', '接收门限', '接收阈值']),
    'reserve_db': ('预留余量', 'dB', ['工程储备', '工程预留', '预留余量', '预留损耗', '储备余量']),
}
NUMBER = r'[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?'
UNITS = r'(?:dBm/Hz|Mbit/s|kbit/s|bit/s|Mb/s|kb/s|Mbps|kbps|bps|km/h|m/s|千米每小时|公里每小时|米每秒|GHz|MHz|kHz|Hz|吉赫兹|兆赫兹|千赫兹|赫兹|dBm|dBi|dBd|dB|mW|W|毫瓦|瓦|km|千米|公里|m|米|℃|°C|摄氏度|K|开尔文)'
QUANTITY = re.compile(rf'(?<![\w.])(?P<value>{NUMBER})\s*(?P<unit>{UNITS})(?![A-Za-z/\d])', re.I)
ALIAS_UNIT = {'吉赫兹': 'ghz', '兆赫兹': 'mhz', '千赫兹': 'khz', '赫兹': 'hz',
              '公里': 'km', '千米': 'km', '米': 'm', '千米每小时': 'km/h',
              '公里每小时': 'km/h', '米每秒': 'm/s', '毫瓦': 'mw', '瓦': 'w',
              '摄氏度': 'c', '℃': 'c', '°c': 'c', '开尔文': 'k'}


def convert(field, value, unit):
    if unit in ('MW', 'mHz'):
        raise ValueError('暂不支持此大小写敏感的SI单位；请明确换算为W或Hz')
    unit = ALIAS_UNIT.get(unit.lower(), unit.lower())
    frequency = {'hz': 1, 'khz': 1e3, 'mhz': 1e6, 'ghz': 1e9}
    rates = {'bit/s': 1, 'bps': 1, 'kb/s': 1e3, 'kbit/s': 1e3, 'kbps': 1e3, 'mb/s': 1e6, 'mbit/s': 1e6, 'mbps': 1e6}
    if field == 'bit_rate_bps' and unit in rates:
        return value * rates[unit]
    if field == 'noise_density_dbm_hz' and unit == 'dbm/hz':
        return value
    if field == 'frequency_ghz' and unit in frequency:
        return value * frequency[unit] / 1e9
    if field == 'bandwidth_hz' and unit in frequency:
        return value * frequency[unit]
    if field == 'distance_km' and unit in ('m', 'km'):
        return value / 1000 if unit == 'm' else value
    if field == 'speed_kmh' and unit in ('km/h', 'm/s'):
        return value * 3.6 if unit == 'm/s' else value
    if field == 'temperature_k' and unit in ('k', 'c'):
        return value + 273.15 if unit == 'c' else value
    if field.endswith('_dbm') and unit in ('dbm', 'w', 'mw'):
        if unit == 'dbm':
            return value
        if value <= 0:
            raise ValueError('线性功率必须大于零')
        return 10 * math.log10(value) + (30 if unit == 'w' else 0)
    if field.endswith('_dbi') and unit == 'dbi':
        return value
    if field.endswith('_dbi') and unit == 'dbd':
        return value + 2.15
    if field.endswith('_dbi') and unit == 'db':
        raise ValueError('天线增益的dB参考不明确，请重新输入dBi或dBd')
    if field.endswith('_db') and unit == 'db':
        return value
    raise ValueError('单位与参数不匹配')


def extract_request(text, overrides=None, condition=None, target=None, field_specs=None):
    if not isinstance(text, str) or len(text) > 12000:
        raise ValueError('请输入不超过12000字的文本')
    original_text = text
    text = re.sub(r'(?<=\d)[⁰¹²³⁴⁵⁶⁷⁸⁹]+', lambda m: '^'+unicodedata.normalize('NFKC', m.group()), text)
    text = unicodedata.normalize('NFKC', text).replace('−', '-')
    # Accept labelled rows such as "发射功率 (dBm) 40" without supplying a unit
    # from a reference workbook. Only units present in the row are moved.
    row_sources = {}
    rows = []
    for row in text.splitlines():
        match = re.fullmatch(rf'\s*(.+?)\s*\(\s*({UNITS})\s*\)\s*[:=]?\s*({NUMBER})\s*', row, re.I)
        converted = f'{match[1].strip()} {match[3]}{match[2]}' if match else row
        row_sources[converted] = row
        rows.append(converted)
    text = '\n'.join(rows)
    def source_span(match):
        start = text.rfind('\n', 0, match.start()) + 1
        end = text.find('\n', match.end())
        line = text[start:end if end >= 0 else len(text)]
        return row_sources.get(line, match.group()) if line in row_sources and row_sources[line] != line else match.group()
    parameters, evidence, issues, values = {}, {}, [], {}
    known_fields = set(FIELDS) | set(field_specs or {})
    blocked = []
    def nearest_field(fragment):
        positions = [(fragment.rfind(alias), key) for key, (_, _, aliases) in FIELDS.items() for alias in aliases if alias in fragment]
        return max(positions)[1] if positions else None
    complicated = re.compile(rf'{NUMBER}\s*(?:~|～|至|到|—|–|-|/|±)\s*{NUMBER}\s*{UNITS}|(?:{NUMBER}\s*[×*x]\s*)?10\s*\^\s*{NUMBER}\s*{UNITS}|\d+(?:,\d{{3}})+\s*{UNITS}|(?:>=|<=|>|<|大于|小于|至少|至多|不少于|不超过)\s*{NUMBER}\s*{UNITS}', re.I)
    for match in complicated.finditer(text):
        blocked.append(match.span())
        prefix = text[max(0, match.start()-12):match.start()]
        field = nearest_field(prefix)
        issues.append({'field': field, 'message': '范围或复合数字不能自动选值，请输入单个数值与单位；科学计数可写2e2', 'evidence': match.group()})
    for clause in re.finditer(r'[^，,。；;\n？?！!]+', text):
        if re.search(r'不是|不为|不用|不要用|不能用|未知|不确定|不知道|是否(?!满足|达标|达成|够用|可行|能通)|例如|假如|如果', clause.group()) and re.search(rf'{NUMBER}\s*{UNITS}', clause.group(), re.I):
            blocked.append(clause.span())
            field = next((k for k, (_, _, aliases) in FIELDS.items() if any(a in clause.group() for a in aliases)), None)
            issues.append({'field': field, 'message': '数值处于否定、未知或举例语境，请明确采用值', 'evidence': clause.group()})
    numeric_text = ''.join(' ' if any(a <= i < b for a,b in blocked) else ch for i,ch in enumerate(text))
    consumed = []
    # Longer aliases win within their own field; anchored label binding prevents
    # a bandwidth from being interpreted as a carrier, or gain as feed loss.
    for field, (_, _, aliases) in FIELDS.items():
        prefix = '|'.join(re.escape(a) for a in sorted(aliases, key=len, reverse=True))
        pattern = re.compile(rf'(?:{prefix})\s*(?:为|是|约为|约|等于|[:：=])?\s*(?P<value>{NUMBER})\s*(?P<unit>{UNITS})(?![A-Za-z/\d])', re.I)
        for match in pattern.finditer(numeric_text):
            consumed.append(match.span())
            try:
                value = convert(field, float(match['value']), match['unit'])
                if not math.isfinite(value):
                    raise ValueError('数值不是有限数')
                values.setdefault(field, []).append((value, source_span(match)))
            except ValueError as exc:
                issues.append({'field': field, 'message': str(exc), 'evidence': match.group()})
    # Unlabelled frequency/distance/speed/temperature can be bound by unique units.
    # Do not guess which dB loss/gain a standalone number belongs to.
    loose = re.compile(rf'(?P<value>{NUMBER})\s*(?P<unit>{UNITS})(?![A-Za-z/\d])', re.I)
    for match in loose.finditer(numeric_text):
        if any(a <= match.start() < b for a, b in consumed):
            continue
        unit = ALIAS_UNIT.get(match['unit'].lower(), match['unit'].lower())
        field = ('frequency_ghz' if unit in ('ghz', 'mhz', 'khz', 'hz') else
                 'distance_km' if unit in ('km', 'm') else
                 'speed_kmh' if unit in ('km/h', 'm/s') else
                 'temperature_k' if unit in ('c', 'k') else None)
        # Unit alone is insufficient when a label is present: antenna height is
        # not path distance, and a loosely phrased bandwidth is not a carrier.
        clause_start = max([0] + [m.end() for m in re.finditer(r'[，,。；;\n]', numeric_text[:match.start()])]
                           + [b for a, b in consumed if b <= match.start()])
        prefix_text = numeric_text[clause_start:match.start()].strip()
        labelled = nearest_field(prefix_text)
        if labelled:
            field = labelled
        elif prefix_text and not re.fullmatch(r'(?:和|与|及|约|大约|为|是|[-:：=\s])*', prefix_text):
            field = None
        if field:
            try:
                value = convert(field, float(match['value']), match['unit'])
                if not math.isfinite(value):
                    raise ValueError('数值不是有限数')
                values.setdefault(field, []).append((value, match.group()))
            except ValueError as exc:
                issues.append({'field': field, 'message': str(exc), 'evidence': match.group()})
    for field, observations in values.items():
        unique = {v for v, _ in observations}
        if len(unique) == 1:
            parameters[field] = observations[0][0]
            evidence[field] = [span for _, span in observations]
        else:
            issues.append({'field': field, 'message': '发现不同数值，请明确采用哪一个', 'evidence': [s for _, s in observations]})
    if overrides is not None and not isinstance(overrides, dict):
        raise ValueError('补充参数格式不正确')
    for field, value in (overrides or {}).items():
        if field not in known_fields or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            issues.append({'field': field, 'message': '未知参数或非有限数值'})
            continue
        parameters[field] = float(value)
        evidence[field] = ['手动输入（规范单位）']
        issues = [i for i in issues if i.get('field') != field]
    conditions = set()
    clauses = re.split(r'[，,。；;\n]', text)
    uncertain = r'不|非|未知|是否|无法|未确认|未验证|尚未|假如|如果|可能'
    for clause in clauses:
        if '自由空间' in clause and not re.search(uncertain, clause):
            conditions.add('free_space')
            if re.search(r'自由空间(?:基准|参考)', clause):
                conditions.add('free_space_reference')
        if (re.search(r'计算\s*总传输损耗\s*L\s*=\s*92\.4\s*\+\s*Lf\s*\+\s*Ld', clause, re.I)
                and not re.search(uncertain, clause)):
            conditions.update(('free_space', 'free_space_reference'))
    if re.search(r'非视距|有遮挡|有山体|穿墙|山区|散射|绕射|超视距', text):
        conditions.add('non_free_space')
    if re.search(r'双程|双向雷达|雷达回波', text):
        conditions.add('two_way')
    for clause in clauses:
        if re.search(r'最大.{0,3}多普勒|多普勒.{0,3}(?:最大|上界)', clause) and not re.search(uncertain, clause):
            conditions.add('maximum_doppler')
    if condition:
        if condition not in ('free_space', 'free_space_reference', 'non_free_space'):
            raise ValueError('未知传播条件')
        conditions.discard('free_space')
        conditions.discard('free_space_reference')
        conditions.add(condition)
        if condition == 'free_space_reference':
            conditions.add('free_space')
    intents = []
    for clause in clauses:
        match = re.search(r'(?:计算|求出|求|想知道|算一下)(.+)', clause)
        if match and not re.search(r'不|不要|不用|不能', clause[:match.start()]):
            intents.append(match[1])
    # Blank output rows after a calculation instruction are additional requested
    # quantities, not known inputs with an invented value.
    if intents:
        for row in rows:
            if re.fullmatch(r'\s*(?:多普勒效应损耗|接收门限|接收信号电平|电平余量F?)\s*(?:\([^)]*\))?\s*', row):
                intents.append(row)
    explicit = '；'.join(intents)
    goal_text = explicit or text
    targets = []
    for identifier, pattern in [('link_margin', r'余量|裕量'), ('received_power', r'接收(?:信号)?电平|接收功率|链路预算'),
                                ('receiver_threshold', r'接收门限|接收灵敏度'),
                                ('thermal_noise', r'热噪声|噪声功率'), ('doppler_max', r'多普勒'),
                                ('fspl_ghz', r'传输损耗|传播损耗|路径损耗|衰减|自由空间|(?:^|；)损耗')]:
        if re.search(pattern, goal_text):
            targets.append(identifier)
    unsupported = []
    if re.search(r'多普勒(?:效应)?损耗', goal_text):
        targets = [t for t in targets if t != 'doppler_max']
        unsupported.append('doppler_loss')
    if not explicit and len(targets) > 1:
        targets = []
    if target:
        targets = [target]
    return {'text': original_text, 'parameters': parameters, 'evidence': evidence,
            'conditions': sorted(conditions), 'issues': issues, 'targets': targets,
            'unsupported_targets': unsupported,
            'target_origin': 'manual' if target else ('explicit_text' if explicit and targets else ('keyword' if targets else 'unknown'))}
