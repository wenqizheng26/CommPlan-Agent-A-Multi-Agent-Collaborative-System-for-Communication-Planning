# 受控计算、审查与主控增量交接

日期：2026-09-21。实现仓库 `.workareas/signal-formula-rag-h0-implementation`，HEAD `9957cc59160d751e6f9d3c30b827842ad1fd21e6`；本轮没有提交、推送或合并，原有大量未提交实现保持原位。

## 已实现

按用户批准的顺序推进：先验收持续补参与架构单视图，修复撤回后标题仍显示待澄清；再实现计算 Agent、结构化审查 Agent，最后实现受控主控策略。

| 部分 | 当前实现与界限 |
| --- | --- |
| 计算 Agent | 只读确认快照，给出当前许可的工具、步骤、版本与快照引用；可选 Qwen，不能生成参数或专业数值。当前仍只有单步 `fspl_ghz`。 |
| 审查 Agent | 独立角色先复核 8 项硬检查，再产生 pass / needs_input / not_applicable / recalculate 决策及事实引用。语义建议不能改数值、伪造引用或绕过硬校验；报告正文由程序生成。 |
| 主控 | `bounded_policy` 根据执行结果与审查意见继续校验、发布、退回、重算或停止。每版本最多两次计算；仅工具 TimeoutError / ConnectionError 可自动重试，硬错误直接失败。不是自主 LLM 任务拆解。 |
| 状态与恢复 | 保存每次工具结果、计算模式、审查结果和调度决定；重算结果使用不同 result_id。编辑/补参清空当前版本执行产物，保留历史；SQLite 主事务与幂等约束继续生效。旧确认检查点已实际恢复通过。 |
| 页面 | 显示计算与审查模式、审查退回原因、调度记录；只按真实调用高亮新增模型连接。历史记录缺少新字段时保持可读。 |

降级边界：本机模型不可用或建议结构/引用非法，最多一次结构修复后使用明确标记的确定性路径。审查降级只代表程序检查通过，不代表完成了模型语义审查。真实 Qwen 单次成功不能证明多 Agent 优于原始单 Agent。

## 验证与证据

- 全量 Python：189 tests，41.275 秒，OK；日志 `runtime/role-extension-python.log`。新增 12 项角色测试覆盖注入、身份、只读、离线、退回、重算上限、暂时故障恢复、硬失败和幂等。
- Node：8 passed，0 failed；包括审查等待状态与真实调用/降级显示。pip check 无依赖冲突。
- 最后 UI 文案与静态路由调整后，HTTP 5 项再验证通过。
- 可复现验收矩阵：运行 `.venv/Scripts/python.exe -B -X utf8 scripts/validate_role_slice.py`，12 个案例全部通过；证据 `evidence/role-acceptance-matrix-20260921.json`。工具故障和指定审查决策使用显式模拟，不冒充真实模型输出。
- 真实 Qwen：需求、计算与审查均为实际 llm 模式，审查 pass，2 GHz / 1 km 得到 98.42059991327963 dB。见 `evidence/role-extension-live-20260921.json`。
- 真实离线：停止本轮启动的模型进程后验证，计算与审查均为 deterministic_fallback，结果正常且 runtime_health=degraded。见 `evidence/role-extension-offline-20260921.json`。随后恢复本地模型服务供试用。
- 内置浏览器：新版真实 Qwen 闭环任务 `89fa3103-dafb-40ad-98b4-ef924d6c5d17`；页面显示 98.420600 dB、本机 Qwen 计算与审查通过，无浏览器 warning/error。见 `evidence/role-extension-browser-20260921.json`。旧检查点兼容证据为 `evidence/role-old-checkpoint-20260921.json`。
- 补参阶段证据 `evidence/supplement-acceptance-20260921.json` 包含增量前源码哈希与完整任务历史：缺参、补 1 km、确认、改 3 GHz、旧结果失效、歧义、不相关补参、撤回、只读历史与服务重启。手工输入 3000 MHz 与原文 3 GHz 同时保留并显示来源。

当前网页服务：`http://127.0.0.1:18082`，使用独立 `outputs/acceptance-20260921.sqlite` 验收数据库。原 `outputs/planning.sqlite` 未被这些验收案例写入。默认 `planning/run_planning.cmd` 仍使用原数据库；不要对同一端口重复启动。

## 本地审查与未完成事项

本地审查核对了模型只读输入、输出白名单、快照/结果绑定、硬校验前置、重算预算、发布门、事务/幂等、编辑失效、历史只读与观察事件边界。审查角色仅返回受控代码及事实 ID；事实正文由服务端产生。未引入新依赖，未修改公式库、物理表达式或数值常数。

**独立代码审查未完成**：请求的子代理因额度限制退出，没有审查报告。不能把上述本地自审、自动测试或产品内审查 Agent 视为独立代码审查通过。Chrome 自动化工具不可用，本轮页面验收使用 Codex 内置浏览器，不能称 Chrome 验收通过。

后续顺序：补独立代码审查和目标 Chrome 验收；选定下一种模型及适用条件、输入输出合同、来源与独立数值基准；再增加实际多步骤/多模型计划并做单/多 Agent 对照。现阶段没有海面/散射计算、完整链路预算、候选优化或自主总控，不宣称完整 CONTRACTS 与全 WBS 已完成。

## 源码入口

- `planning/agents/calculation.py`：工具调用建议与完整系统提示词。
- `planning/agents/review.py`：审查决策、事实引用、发布绑定与完整系统提示词。
- `planning/agents/role_model.py`：本地结构化调用、修复预算及降级记录。
- `planning/agents/orchestrator.py`：受控调度决策。
- `planning/workflow/planning_graph.py`、`task_service.py`：图路由、版本重建及恢复。
- `tests/test_planning_roles.py`、`scripts/validate_role_slice.py`：回归与验收矩阵。
