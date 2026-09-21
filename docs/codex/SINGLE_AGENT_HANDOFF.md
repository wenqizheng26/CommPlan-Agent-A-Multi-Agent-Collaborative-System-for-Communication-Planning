# 首个需求与规划 Agent 运行交接

> 后续阶段更新：确认计算、持久化和网页已在用户继续授权下完成限定切片，当前状态见 [CONFIRMED_LOOP_HANDOFF.md](CONFIRMED_LOOP_HANDOFF.md)。以下为首个 Agent CLI 的阶段交接。

日期：2026-09-18。当前实现工作区：`E:/codex/项目/信号与AI/.workareas/signal-formula-rag-h0-implementation`。本轮用户目标“做到可初步运行成品”授权恢复第一个 Agent 的实施；完整工程、正式计算及 Git 发布未随之展开。

## 使用入口

双击 `planning/run_requirements.cmd`，输入一行需求即可查看中文报告。无模型服务时默认明确降级；如需不调用模型，使用：

```powershell
Set-Location 'E:/codex/项目/信号与AI/.workareas/signal-formula-rag-h0-implementation'
.\planning\run_requirements.cmd --deterministic --request planning/examples/complete.json
```

`planning/examples/missing.json` 演示缺距离，`planning/examples/conflict.json` 演示原文与手工值冲突。加 `--json` 可输出完整状态。详细命令、模型服务启动方法和退出码见 `planning/README.md`。

## 已实现范围与准确边界

- RequirementsAgent：复用原 parser、convert、Retriever、LocalSelector 和原文 grounding，输出候选参数、来源、证据、缺项、冲突与计划建议。
- StateGraph：receive_request → propose_requirements → check_requirements → finish；异常短路、四种终态、八步框架上限、安全 trace。
- 严格输入及输出检查：拒绝重复 JSON 键、非有限数、布尔数值、非法身份与版本；重核来源、目录、卡版本、快照 hash、计划绑定和适用条件。
- 业务入口仅支持单程自由空间单链路损耗基准的规划；参数齐全到 AWAITING_CONFIRMATION，不执行公式、不产生 confirmed 参数或正式损耗。
- LLM 只建议目标/条件；数值只取明确用户输入。首次加最多两次结构重试；网络失败立即降级或失败。无法支持的明确目标直接 NEEDS_MODEL，不依赖模型是否在线。
- RAG 使用同一目录的词项检索，模式 lexical_fallback；没有 dense embedding 成功声明，也没有独立重审原始科学文献。
- CLI 支持文本、完整请求文件、交互输入、中文摘要和完整 JSON，正常业务等待 exit 0、请求错误 exit 2、执行失败 exit 1。

接口保持 requirements-slice-v1 / schema 1.0.0；新增 `requirement_policy.py` 与 `requirement_validation.py` 是内部共享规则和出口检查，不改变既有顶层字段。模型请求不新增商业模型依赖。

## 验收证据与覆盖

最终测试计数、退出码、时间、文件哈希见 `evidence/sa_validation.json`；完整命令输出见 `evidence/sa-tests-20260918.log`。演示和真实模型调用见 `evidence/sa-demo-20260918.json`；独立复核见 `evidence/single_agent_review_20260918.json`。

| 设计验收项 | 当前验证位置 |
|---|---|
| A01 完整输入无计算 | test_complete_never_computes、test_normal_trace_and_no_calculation；complete CLI/Qwen 实跑 |
| A02 缺参无默认值 | test_missing_has_no_default；missing CLI/Qwen 实跑 |
| A03 条件不得推断 | test_month_one_scope_and_conditions |
| A04 来源冲突 | test_conflicts_and_equivalent_units；conflict CLI/Qwen 实跑 |
| A05 等价单位/原值 | test_conflicts_and_equivalent_units、test_source_original_units_and_normalized_values |
| A06 否定/举例/范围/科学计数 | 原有 parser 回归；首个 Agent 的范围、否定、候选表达、转折/双重否定回归及手动探针 |
| A07 模型缺口 | test_unsupported_and_negation、test_known_unsupported_scope_does_not_depend_on_model_service；unsupported 实跑 |
| A08 空/低相关证据 | test_empty_evidence_and_unknown_target、test_zero_similarity_cannot_supply_evidence |
| A09 域/近场 | test_month_one_scope_and_conditions；复用原 scope_issues |
| A10 模型不可信输出 | test_model_raw_output_rejected_and_bounded、test_model_target_must_mean_path_loss、test_model_cannot_use_duplicate_keys_or_fabricated_evidence |
| A11 故障与降级 | test_network_failure_and_fail_closed；服务关闭后的 CLI 实测单列证据 |
| A12 身份/版本/数值类型 | test_requirements_contract；test_input_not_mutated_and_stale_rejected_before_selector；跨任务独立性测试 |
| A13 计划/来源篡改 | test_tampered_reports_fail_closed、test_rehashed_bad_plan_rejected_against_catalog |
| A14 无合法报告出口 | test_failure_has_visible_trace_and_no_report、test_missing_catalog_visible |
| A15 路由/步数 | 正常四节点、早期短路；STEP_LIMIT 通过模拟框架抛预算异常检查失败出口，固定无环图本身正常执行四步 |
| A16 CLI | test_requirements_demo；三类请求文件及一键启动器实跑 |
| A17 禁止数值工具 | test_all_status_paths_never_call_numerical_tool；planning Python 源码未引用 evaluate 或 Engine |
| A18 回归/真实模型 | 原有 101 项回归 + 环境 2 项 + 当前切片测试；真实服务调用有模型身份和非零 usage |

首轮新功能 RED：115 项测试中 9 项因 Agent 文件缺失失败，既有 101 项和环境/契约已存在部分通过；随后补充首月边界测试并实现。独立审查发现的多候选漏读、LLM 错误目标、报告复核遗漏、否定误判均先增加失败回归再修复。审查的最终结论单独保存，不把作者自查当成独立验收。

## 模型验证与本机资产

本轮使用原有 Qwen3-4B Q4_K_M GGUF 和 llama.cpp Vulkan 程序，无下载、无权重改动，服务限 `127.0.0.1:18081`、offline。进程身份与生命周期记录在 `evidence/sa_model_20260918.json`。历史 2026-09-17 的策略拒绝记录保留；2026-09-18 新授权下原启动方式成功，不覆盖或伪装历史状态。

实际调用记录中，complete/missing/conflict 使用 interpretation=llm，保留模型别名 signal-formula-qwen3、usage 与耗时。超出范围的请求由确定性规则直接阻断；不把这条路径写成调用了 LLM。运行日志 `sa-model-20260918.*.log` 是本地验证日志，不属于 GitHub 发布允许清单。

## 尚未交付及后续连接

当前是命令行可运行版本；没有修改旧网页/API，也没有实现任务级用户确认、ConfirmedSnapshot、专业计算 Agent、解释 Agent、Orchestrator、持久 checkpoint、编辑 API 或跨进程恢复。

后续接入《通信筹划多智能体协同流程》时，由总控读取当前 task/revision 调用本 Agent，程序验证后提交建议，再交确认节点。finish 只结束本次规划；用户确认后建立不可变快照，计算服务再执行。当前 expected_revision 仅检查调用参数，不是持久任务数据库中的 CAS。

适用性通过仅排除了已编码的明显错误，不能证明现实海域符合自由空间或远场。复杂自然语言超出已编码规则时需用户核对；本轮小规模 Qwen 场景验证不是自由文本准确率评测。

## 文件与发布

只改 planning、对应测试和本切片控制/交接文档。旧 formula_rag、app.py、web、knowledge、原图和原始材料没有本轮修改。源工作树的已有用户变更保留；当前工作树仍含此前尚未提交变更，不能把所有 git diff 归为本轮。

不提交、不推送、不合并、不删除工作树。Git 发布仍由独立 publisher 按明确允许清单处理；当前可运行性不以远端发布作为前提。
