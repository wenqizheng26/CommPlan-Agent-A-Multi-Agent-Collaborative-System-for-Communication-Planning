# 项目进度与下一步核对

日期：2026-09-21。范围：本项目 skills 调整、当前实现只读核对及自动回归；没有修改业务源码或发布 Git。

## 当前结论

项目已超过“只有公式 RAG / 只有首个需求 Agent”的阶段。自由空间单链路的需求解析、人工确认、确定性计算、结果校验和工作台已有实现与历史端到端验收。其后的“持续补参 + 架构单视图”也已有代码，本轮全量回归通过，但尚缺与当前源码对应的最新浏览器、真实模型和独立审查验收记录。

| 层次 | 当前状态 | 证据与边界 |
| --- | --- | --- |
| 旧公式底座 | 已有 7 公式及解析、检索、确定性计算、适用性检查 | `formula_rag`、`knowledge`；本轮相对本工作区 HEAD 无 diff |
| 需求与规划 Agent | 已接入受规则约束的解析、检索、可选本机模型建议 | `planning/agents/requirements.py`；当前切片检索为词项路线 |
| 确认计算闭环 | 已实现，并有 9 月 18 日真实 Qwen / 离线 / 浏览器证据 | `CONFIRMED_LOOP_HANDOFF.md`；只正式支持声明假设下的自由空间路径损耗 |
| 持久化与历史 | SQLite、checkpoint、版本失效、幂等与恢复已有测试 | `task_service.py`、`task_store.py`、`test_planning_loop.py` |
| 工作台 | 已实现参数、公式、依据、时间线、历史与 JSON | `FLOW_WORKBENCH_HANDOFF.md` 是旧双视图阶段验收；当前已改为总体架构单视图 |
| 持续补参 | 已有受控合并、歧义追问、撤回、参数来源、旧结果失效 | `supplement.py`、`conversation.mjs`；8 项补参测试本轮通过，完整新阶段验收待补 |
| 多 Agent 完整研究系统 | 未完成 | 总控为固定路由，计算为确定性调度，验证解释主要为程序校验；不能称四个 LLM Agent 完成协作 |
| 新传播模型与研究评估 | 未完成 | 海面/散射模型、完整链路预算、候选优化、单/多 Agent 对照证据尚非本切片成果 |

## 本轮验证

- `.venv/Scripts/python.exe -X utf8 -m unittest discover -s tests -v`：177 tests，87.220 秒，OK，exit 0。
- `node --test tests/planning_flow.test.mjs tests/planning_web_text.test.mjs`：7 passed，0 failed，exit 0。
- `.venv/Scripts/python.exe -X utf8 -m pip check`：No broken requirements found，exit 0。
- 三项安装技能经系统 `quick_validate.py` 检查通过，fundamentals 的 Python/TypeScript 引用文件存在。
- 原始日志保留 `runtime/status-audit-20260921-python.log` 与 `runtime/status-audit-20260921-node.log`；结构化记录见 `evidence/status_review_20260921.json`。

未运行本轮可见浏览器验收、真实 Qwen、完整 dense RAG、现场传播验证或独立子智能体代码审查。历史记录不替代这些验证。

## 接管风险

当前实现目录：`E:/codex/项目/信号与AI/.workareas/signal-formula-rag-h0-implementation`，分支 `codex/h0-implementation-20260917`，HEAD `9957cc5`。大量实现与文档仍是未提交或未跟踪文件，不能只按 Git log 判断完成度；本轮未检查远端，也没有提交、合并或推送。

9 月 18 日工作台验收记录登记的 31 个源码文件中，11 个与当前 SHA256 不同。最新补参规格 `docs/superpowers/specs/2026-09-18-supplement-architecture-design.md` 明确取代双视图；旧 NEXT_ACTION 的“双视图已验收”与 WBS 的“LangGraph 未落地”均不足以描述当前状态。历史证据保留，当前恢复以本报告为先。

## 下一步顺序

1. **收尾现有补参与架构单视图。** 用可见 Chrome 验证“缺距离 → 补 1 km → 核对确认 → 正式结果 → 改为 3 GHz → 旧结果失效 → 再确认”；再验证歧义、撤回、手工来源、历史只读、刷新与服务重启，以及架构节点仅随真实调用变化。自动测试已通过，不必无变更反复全量运行。
2. **补齐当前源码的验收证据。** 可选真实 Qwen 与模型离线降级分别留证，检查补参结构化建议不能创造数值或清除未决问题；针对新增状态与前端竞态做审查。保留各层验证边界，形成 supplement/architecture 阶段交接。落实这些检查前不把本阶段标为全面完成。
3. **形成首月研究验收材料。** 汇总成功、缺参、冲突、模型不适用、执行/校验失败、编辑失效与恢复的案例、期望状态、实际输出和来源；明确工作流可靠性成果与传播精度结论的区别。核对 WBS 时逐项重映射，避免一次性把全部旧条目改成完成。
4. **再选择扩展研究方向。** 首月自由空间闭环收尾后，再确认优先增加传播模型还是 Agent 规划能力。新物理模型先明确适用条件、必要输入、可核验文献和独立数值基准；不能直接把自由空间用于实际海面/散射。多 Agent 收益需要对照实验支持。

项目级技能已调整，入口见 `AGENTS.md` 和 `SKILL_SELECTION_20260921.md`。本次交付为状态报告和技能安排，不把下一阶段计划计为已实施。
