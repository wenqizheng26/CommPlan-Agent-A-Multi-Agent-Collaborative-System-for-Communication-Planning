"""Run: python -m planning.demo --deterministic --text '通信需求'."""
import argparse
import json
from pathlib import Path
import sys
import uuid
from planning.requirements_contract import strict_json, validate_request

LABELS = {'AWAITING_CONFIRMATION':'等待用户确认','AWAITING_INPUT':'等待补充或修正',
          'NEEDS_MODEL':'当前模型或依据不足','FAILED':'处理失败'}


def render(state):
    lines = ['需求与规划 Agent', '当前状态：'+LABELS.get(state['status'],state['status']),
             '尚未进行正式计算；本报告仅为参数与计划建议。']
    report = state['report']
    if report:
        lines.append(f"运行模式：解释={report['component_modes']['interpretation']}；检索={report['component_modes']['retrieval']}；健康={report['runtime_health']}")
        for p in report['parameters_proposal']:
            lines.append(f"参数 {p['canonical_name']}：{p['value'] if p['value'] is not None else '未确定'} {p['unit']} [{p['status']}]")
            for o in p['origins']:
                lines.append(f"  来源 {o['kind']}：{o['value']} {o['unit']}（{o['source_ref']}）")
        plan = report['calculation_plan_proposal']
        if plan:
            lines.append('计划建议：'+' → '.join(s['tool_id'] for s in plan['steps'])+'；待确认后由后续模块执行。')
        for q in report['questions']:
            lines.append('需要处理：'+q)
        for d in report['diagnostics']:
            if d['code'] in {'SOURCE_EXCERPT','EXPLICIT_CARD_LOOKUP','MODEL_CALL'}:
                continue
            lines.append(f"说明 [{d['code']}]：{d['message']}" + (' 下一步：'+d['details']['next_action'] if 'next_action' in d['details'] else ''))
        for e in report['evidence_refs']:
            lines.append(f"依据：{e['source_title']}；{e['locator']}；{e['source_url'] or e['source_id']}")
        for assumption in report['assumptions']:
            lines.append('适用限制：'+assumption)
        if state['status']=='AWAITING_CONFIRMATION':
            lines.append('下一步：核对原文、参数、模型和假设。本切片尚无确认执行功能。')
    for t in state['trace']:
        if t['reason_code']:
            lines.append(f"步骤 {t['node']} [{t['reason_code']}]：{t['message']}")
    lines.append('执行轨迹：'+' → '.join(t['node'] for t in state['trace']))
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description='自由空间单链路需求与规划演示；不执行公式计算。')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--text')
    source.add_argument('--request',type=Path,help='完整请求 JSON 文件，支持手工参数和 revision')
    parser.add_argument('--deterministic',action='store_true',help='不调用 LLM，使用确定性解析')
    parser.add_argument('--no-fallback',action='store_true',help='模型失败时直接失败')
    parser.add_argument('--json',action='store_true',help='输出完整状态 JSON')
    parser.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--expected-revision',type=int)
    args = parser.parse_args(argv)
    from planning.workflow.requirements_graph import run_requirements, failure_state
    request = None
    try:
        if args.request:
            request = strict_json(args.request.read_text(encoding='utf-8-sig'))
        else:
            text = args.text
            if text is None:
                print('请输入需求（例：按自由空间基准计算，频率2GHz，距离1km，求路径损耗）：',file=sys.stderr)
                text = input()
            request = dict(schema_version='1.0.0',task_id=str(uuid.uuid4()),revision=0,request_id=str(uuid.uuid4()),
                           raw_text=text,manual_parameters={},condition=None,target=None)
        request = validate_request(request,expected_revision=args.expected_revision)
    except (ValueError,TypeError,KeyError,OSError,EOFError):
        state = failure_state(None,'INVALID_REQUEST','请求文件、格式、单位或版本无效，请修正后重新提交。')
        code = 2
    else:
        try:
            from planning.agents.requirements import RequirementsAgent
            agent = RequirementsAgent(args.root,selector=False if args.deterministic else None,allow_fallback=not args.no_fallback)
        except (ValueError,TypeError,KeyError,OSError):
            state = failure_state(request,'CATALOG_INVALID','知识目录无法加载或不合法，请检查 --root 对应的 knowledge/formulas.json。','load_catalog')
        else:
            state = run_requirements(request,agent,expected_revision=args.expected_revision)
        code = 1 if state['status']=='FAILED' else 0
    print(json.dumps(state,ensure_ascii=False,indent=2,allow_nan=False) if args.json else render(state))
    return code


if __name__=='__main__':
    raise SystemExit(main())
