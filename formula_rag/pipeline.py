"""Deterministic gates remain independent of model retrieval decisions."""
import time
from pathlib import Path
from .parsing import extract_request, FIELDS
from .retrieval import Retriever
from .model import LocalSelector
from .interpretation import merge_interpretation
from .presentation import formula_view
from .applicability import (RULE_VERSION, FARFIELD_NOTE, noise_confirmation, model_coverage_issue,
                            scope_issues, result_issues, describe_result)

CONDITIONS = {'free_space': '明确采用理想自由空间模型；现实环境只能按明确说明的自由空间基准计算',
              'maximum_doppler': '确认需要最大多普勒频移上界；仅有速度大小不能求带符号的实际频移'}
DEPENDENCIES = {'path_loss_db': 'fspl_ghz', 'rx_power_dbm': 'received_power',
                'rx_threshold_dbm': 'receiver_threshold', 'noise_density_dbm_hz': 'noise_density'}


class Engine:
    def __init__(self, root, dense=True, llm=True):
        from .catalog import load_catalog
        self.root = Path(root)
        self.cards = load_catalog(self.root)
        self.retriever = Retriever(self.root, self.cards, dense=dense)
        self.selector = LocalSelector() if llm else None

    def query(self, text, parameters=None, condition=None, target=None, noise_reference=None):
        from .catalog import load_catalog
        from .core import evaluate
        started = time.perf_counter()
        self.cards = load_catalog(self.root)
        self.retriever.update(self.cards)
        by_id = {c['id']: c for c in self.cards}
        field_specs = {k: s for c in self.cards for k, s in c['parameters'].items()}
        request = extract_request(text, overrides=parameters, condition=condition, target=target, field_specs=field_specs)
        request['noise_reference'] = noise_confirmation(text, noise_reference)
        matches = self.retriever.search(text)
        candidate_ids = {m['id'] for m in matches}
        runtime = {'dense_used': self.retriever.dense, 'llm_used': False, 'model_output_rejected': False,
                   'catalog_hash': self.retriever.hash, 'network': 'local_only', 'scope_rule_version': RULE_VERSION}
        selected_ids, model_error, selected = [], None, {}
        if self.selector:
            try:
                selected = self.selector(text, [by_id[m['id']] for m in matches])
                proposed = selected.get('selected_ids', [])
                if not isinstance(proposed, list) or any(not isinstance(i, str) or i not in candidate_ids for i in proposed):
                    runtime['model_output_rejected'] = True
                else:
                    selected_ids = list(dict.fromkeys(proposed))
                runtime.update({'llm_used': True, 'model': selected.get('model', 'local_selector'),
                                'model_selection': selected_ids, 'model_usage': selected.get('usage', {}),
                                'model_interpretation': {k: selected.get(k, []) for k in ('targets', 'conditions')}})
            except Exception as exc:
                model_error = f'{type(exc).__name__}: {exc}'
                runtime['model_error'] = model_error
        interpretation = merge_interpretation(request, selected, candidate_ids, target, condition)
        questions, calculations, warnings = [], [], []
        if 'doppler_loss' in request.get('unsupported_targets', []):
            if 'speed_kmh' not in request['parameters']:
                questions.append('请补充相对速度（km/h）。')
            questions.append('多普勒损耗需要波形、频偏补偿方式及有依据的损耗模型；当前知识库只有频移上界公式，不能把Hz结果当作dB损耗。')
        for issue in request['issues']:
            if issue.get('field') in ('tx_gain_dbi', 'rx_gain_dbi'):
                questions.append('请明确发射/接收天线增益的参考单位，重新输入dBi或dBd。')
        if 'drift_loss_db' in request['parameters']:
            questions.append('平台漂移损耗尚未自动计入：请明确它是否已包含在其他损耗中；若作为独立工程预留，请填写预留余量（dB）。')
        if model_error:
            warnings.append('本地模型调用未完成，当前仅提供程序检索/计算结果；本次不算完整RAG运行。')
        if 'free_space_reference' in request['conditions']:
            warnings.append('以下自由空间结果仅是理想基准，未估计实际遮挡、海面反射或额外传播损耗。')
        values = dict(request['parameters'])
        completed, visiting = {}, set()

        def calculate(identifier):
            if identifier in completed:
                return completed[identifier]
            card = by_id.get(identifier)
            if not card or identifier in visiting:
                return {'id': identifier, 'status': 'unknown_formula'}
            visiting.add(identifier)
            base = {'id': identifier, 'title': card['title'], 'version': card['version'],
                    'expression': card['expression'], 'sources': card.get('sources', []),
                    'description': card.get('description', ''), 'value_origin': 'deterministic_calculator',
                    'display': formula_view(card),
                    'declared_conditions': request['conditions'], 'applicability': card.get('applicability', {})}
            requires = card.get('applicability', {}).get('requires', [])
            absent = [c for c in requires if c not in request['conditions']]
            if identifier == 'doppler_max' and 'two_way' in request['conditions']:
                result = {**base, 'status': 'not_applicable', 'errors': ['该公式只支持单程多普勒上界，双程雷达需要单独的模型。']}
            elif 'free_space' in requires and 'non_free_space' in request['conditions'] and 'free_space_reference' not in request['conditions']:
                issue = model_coverage_issue()
                questions.append(issue['message'])
                result = {**base, 'status': 'not_applicable', 'scope_issues': [issue], 'errors': [issue['message']]}
            elif absent:
                issues = [model_coverage_issue()] if 'free_space' in absent else []
                questions.extend(i['message'] for i in issues)
                questions.extend(CONDITIONS.get(c, '请明确条件：' + c) for c in absent if c != 'free_space')
                result = {**base, 'status': 'missing_conditions', 'missing_conditions': absent,
                          'scope_issues': issues, 'errors': [i['message'] for i in issues]}
            else:
                dependencies = []
                for parameter in card['parameters']:
                    if parameter not in values and parameter in DEPENDENCIES and DEPENDENCIES[parameter] in by_id:
                        if parameter == 'noise_density_dbm_hz' and 'temperature_k' not in values:
                            continue
                        dependency = calculate(DEPENDENCIES[parameter])
                        dependencies.append(dependency['id'])
                        if dependency['status'] == 'ok':
                            values[parameter] = dependency['value']
                issues = scope_issues(identifier, values, request)
                missing = [p for p in card['parameters'] if p not in values]
                blocked = [d for d in dependencies if completed[d]['status'] != 'ok']
                if issues:
                    questions.extend(i['message'] for i in issues)
                    result = {**base, 'status': 'not_applicable' if any(i['severity'] == 'not_applicable' for i in issues) else 'missing_conditions',
                              'scope_issues': issues, 'errors': [i['message'] for i in issues],
                              'missing': missing, 'dependencies': dependencies}
                elif blocked:
                    result = {**base, 'status': 'missing_parameters', 'missing': missing,
                              'dependencies': dependencies, 'blocked_by': blocked,
                              'errors': ['上游计算尚未满足条件，本项暂不输出数值：' + '、'.join(by_id[d]['title'] for d in blocked)]}
                else:
                    result = {**base, **evaluate(card, values), 'dependencies': dependencies}
                if result.get('missing'):
                    for field in result.get('missing', []):
                        if field in ('path_loss_db', 'rx_power_dbm', 'rx_threshold_dbm') and DEPENDENCIES.get(field) in by_id:
                            continue
                        if field == 'noise_density_dbm_hz':
                            questions.append('请补充参考噪声谱密度（dBm/Hz），或参考噪声温度（K）；两者选填一个。')
                            continue
                        if field in {i.get('field') for i in request['issues']}:
                            continue
                        info = card['parameters'].get(field, {})
                        label = FIELDS.get(field, (info.get('description', field), info.get('unit', ''), []))
                        questions.append(f'请补充{label[0]}（{label[1]}）')
                if result.get('status') == 'ok':
                    issues = result_issues(identifier, result['value'])
                    if issues:
                        result.pop('value')
                        result.update(status='not_applicable', scope_issues=issues, errors=[i['message'] for i in issues])
                    else:
                        result['display_value'] = format(result['value'], '.8f').rstrip('0').rstrip('.')
            visiting.remove(identifier)
            completed[identifier] = result
            calculations.append(result)
            return result

        wanted = request['targets']
        if not wanted:
            suggestions = '、'.join(by_id[i]['title'] for i in selected_ids)
            questions.append('请明确要计算的量，或在“计算目标”中选择。' + ('检索建议：' + suggestions if suggestions else ''))
        elif any(i not in by_id for i in wanted):
            questions.append('所选公式不在当前知识库中，请选择已登记公式。')
        else:
            for identifier in wanted:
                calculate(identifier)
        # Block only calculations that use an invalid field, plus their dependents.
        invalid_fields = {i.get('field') for i in request['issues']}
        blocked_ids = set()
        for item in calculations:
            card = by_id[item['id']]
            affected = (None in invalid_fields or bool(invalid_fields.intersection(card['parameters']))
                        or bool(blocked_ids.intersection(item.get('dependencies', []))))
            if affected:
                blocked_ids.add(item['id'])
                if item['status'] == 'ok':
                    item.pop('value', None)
                    item.pop('display_value', None)
                    item['status'] = 'blocked_by_input_issue'
        for item in calculations:
            if item['status'] != 'ok':
                continue
            assessment = describe_result(item['id'], item['value'])
            if assessment:
                item['assessment'] = assessment
                warnings.append(assessment['message'])
            if item['id'] == 'fspl_ghz':
                warnings.append(FARFIELD_NOTE)
            if item['id'] == 'receiver_threshold' and item['inputs']['noise_density_dbm_hz'] == -174:
                warnings.append('本次采用用户输入的 −174 dBm/Hz 工程舍入值；精确 k×290 K 对应约 −173.97518719 dBm/Hz，未替换输入值。')
        statuses = [c['status'] for c in calculations]
        if request['issues'] or 'invalid_parameters' in statuses:
            status = 'invalid_input'
        elif 'not_applicable' in statuses:
            status = 'not_applicable'
        elif not calculations or any(s != 'ok' for s in statuses) or questions:
            status = 'needs_input'
        else:
            status = 'ok'
        if 'ok' in statuses and status != 'ok':
            status = 'partial'
        runtime['elapsed_seconds'] = round(time.perf_counter() - started, 3)
        return {'status': status, 'request': request, 'interpretation': interpretation,
                'candidates': [{**m, 'title': by_id[m['id']]['title'], 'review_status': by_id[m['id']]['status'],
                                'sources': by_id[m['id']].get('sources', [])} for m in matches],
                'calculations': calculations, 'questions': list(dict.fromkeys(questions)),
                'warnings': list(dict.fromkeys(warnings)), 'runtime': runtime}
