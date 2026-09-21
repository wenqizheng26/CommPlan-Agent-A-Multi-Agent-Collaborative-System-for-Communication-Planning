# 第一个 Agent 可运行版本实施计划

> 执行：当前任务使用 executing-plans 串行实施；独立复核与主任务的交接整理可并行。用户目标“做到可初步运行成品”授权恢复本切片开发与测试，不恢复完整 35 项工程或自动发布。

**目标：** 完成设计文档所述需求与规划 Agent、四节点 LangGraph、可直接使用的 CLI，提供可复现验收和真实模型状态证据。

**架构：** planning 适配旧 parser、Retriever 和 LocalSelector。首个业务入口只准入 fspl_ghz；所有路径止于建议和等待确认，绝不计算。程序独立核对报告和证据。

**技术栈：** 现有隔离 Python 3.12、LangGraph 1.2.11、stdlib、unittest；不改旧 formula_rag / app / web。

## 文件职责

- planning/requirements_contract.py：严格请求/报告校验，重复 JSON 键拒绝。
- planning/services/requirement_parameters.py：原文和手工来源、冲突、规范单位。
- planning/services/requirement_evidence.py：目录证据、知识快照与计划身份。
- planning/agents/requirements.py：受控 LLM 调用、规划、缺项与失败分类。
- planning/workflow/requirements_graph.py：状态、节点、路由、可信报告复核。
- planning/demo.py：文本/请求文件/交互输入、中文展示、JSON 输出及退出码。
- tests/test_requirements_*.py：设计 A01–A18 验收；旧热噪声 Agent 样例改为首月范围外，旧 formula_rag 热噪声测试不变。
- docs/codex/SINGLE_AGENT_HANDOFF.md、evidence/sa_validation.json、日志：运行方法、结果及限制。

## 任务 1：确认 RED 与首月测试边界

- [x] 运行现有全量测试，记录旧基线和缺失实现失败。
- [x] 增加设计矩阵中条件缺失、非正/近场、目标冲突、范围/否定、伪造/重复 JSON、非法报告证据测试。
- [x] 明确基本断言：`run(request)['execution_status'] == 'AWAITING_CONFIRMATION'`，`report['calculation_plan_proposal']['steps'][0]['tool_id'] == 'fspl_ghz'`，禁止存在正式结果。
- [x] 运行 `.venv/Scripts/python.exe -B -X utf8 -m unittest discover -s tests -p test_requirements_agent.py -v`，预期实现缺失失败。

## 任务 2：参数、证据、Agent

- [x] 原文调用 `extract_request(raw_text)`，不传 overrides；证据逐项恢复原值/单位，保留原文定位或 null，和手工值经 convert 后比较。
- [x] 生成实际目录与卡片 hash；无证据不生成确认计划。
- [x] 严格 JSON 解码与原文 grounding，首次加最多两次结构重试；网络错误立即降级或失败。
- [x] 生成白名单单步计划；检查域/适用性；覆盖所有四终态；新增语义检查拒绝不一致报告。
- [x] 执行任务 1 命令直至通过；契约测试使用 `-p test_requirements_contract.py`。

## 任务 3：图和入口

- [x] 先写图测试：正常 trace 恰为四节点；早期非法请求不调用 Agent；证据/报告篡改进 FAILED；目录失败有 trace。
- [x] 先写 CLI 子进程测试：文本、文件、交互输入和 JSON 往返；exit 0/1/2 区分业务等待/故障/非法请求。
- [x] 运行两组测试看到缺失模块失败。
- [x] 用 StateGraph 添加 receive_request/propose_requirements/check_requirements/finish，错误条件边短路，recursion_limit=8。
- [x] CLI 支持 `--text`、`--request`、`--deterministic`、`--json`，无参数时交互输入；中文逐项展示参数和来源、问题、计划、模式、失败。
- [x] 跑图和 CLI 测试至 GREEN。

## 任务 4：验收与交付

- [x] 全量回归命令：`.venv/Scripts/python.exe -B -X utf8 -m unittest discover -s tests -v`。
- [x] 完整/缺参/冲突/模型缺口/失败 CLI 实例保存证据，失败不得留下正式数值。
- [x] 探测现有本机模型服务；仅在允许的现有本地启动方式下验证真实调用，不能规避历史策略拒绝。未运行明确记为未验证，不算 stub 通过。
- [x] 独立代码复核、修复及必要回归；交接文档列 A01–A18 的实测覆盖与未验证边界。
- [x] 更新 NEXT_ACTION/PROJECT_CONTEXT/切片状态。原 Git publisher 唯一写入规则保留，本任务不提交或上传。

## 设计一致性

执行依据为 2026-09-18-first-requirements-agent-design.md。较旧计划新增首月白名单、非法报告 null 出口和严格复核；公共请求/报告字段不变。确定性可运行版本与真实 LLM 验证分开报告；“初步运行”不代表完整通信筹划闭环完成。

## 运行验收记录

2026-09-18：143 项测试 / 57.113 秒 / exit 0；9 个 CLI/真实模型/离线实例，独立有界审查问题已关闭。实现新增共享 policy 和 validation 两个内部模块；public schema 未改。完整证据见 docs/codex/evidence/sa_validation.json。
