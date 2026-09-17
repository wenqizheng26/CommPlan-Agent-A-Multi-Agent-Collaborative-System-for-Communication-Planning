# 通信筹划项目持续接管上下文

日期：2026-09-17。阶段：H0已由用户“执行”批准，进入P1基线与合同冻结；Contract仍DRAFT直到T003验收。

## 范围和事实来源

- 当前唯一实施工作树：E:/codex/项目/信号与AI/.workareas/signal-formula-rag-h0-implementation；源工作树E:/codex/项目/信号与AI/signal-formula-rag保留原用户修改。
- 主规范：用户指定的 通信筹划项目_Codex完整交接与自动化编排_v3.md。
- 范围基准：WBS分解-智能体.xlsx，Sheet1 B4:I45，38 项。
- 设计意图基准：桌面原始 通信筹划多智能体协同流程.vsdx 的两页；不修改原图。
- 工程事实：当前工作树、可定位代码、原始测试日志。README/HANDOVER 中的完成声明不是运行证明。
- 历史研究涉及岸海单链路与候选比较；仅作为历史背景。当前总体范围以 WBS 和仓库需求文件为准，首个可演示闭环建议限于明确自由空间条件下的单链路损耗。不能用该 Demo 宣称完成链路预算或海上传播模型。

## 当前真实边界

HEAD 7342866450b08dafca10278bf98812f9f0fac137；原分支 codex/p1-applicability。开始时有 15 项既有业务变更，审计针对包含这些变更的本地工作树；GitHub HEAD 不包含全部被审计代码。不得覆盖、撤销、自动打包这些旧修改。

现有 formula_rag 实现 7 条公式、混合检索、参数/单位解析、AST 白名单计算、适用性/结果校验、旧 API/Web。101 项 unittest 通过；8 个公式样例符合卡声明容差。真实 Qwen/完整 dense RAG、科学来源复核、浏览器验收尚未完成。没有已运行的 LangGraph/GraphState/任务级确认或持久恢复；已存在公式选择 JSON Schema，不能声称“没有任何 Schema”。

## 不变规则

复用 formula_rag，不另起第二套 RAG；不整体重写；不静默改变旧 API；专业数值仅由确定性工具产生；Agent 不能覆盖 ToolResult；典型值只能 suggested；关键输入变更必须更新 revision 并使结果失效；有限重试；旧/晚到结果拒绝；证据、参数、公式、模型及执行版本可追溯。

开发 Subagent 与业务 Agent 是两个维度。Astra/Luna 是本次 Codex 工程人员的模型分工，不是项目本地 Qwen 业务角色，也不是给运行时增加商业模型依赖。

## 权限与恢复

用户最新指示覆盖 v3 中推荐的审计推理强度：代码/架构审计使用 Astra low，测试执行 Luna medium，发布 Luna low。Main 保留架构、公共 Contract 与集成责任。

本轮只生成审计/计划/工程控制文件并阶段性发布 GitHub。H0 未批准时，不实现后续业务功能。恢复顺序：PROJECT_CONTEXT → AUDIT_REPORT → ARCHITECTURE_DECISIONS → CONTRACTS → MASTER_IMPLEMENTATION_PLAN → TASK_BACKLOG → AGENT_ASSIGNMENTS → TEST_BASELINE → IMPLEMENTATION_LOG → NEXT_ACTION；然后核对工作树、未完成任务和发布 SHA。源事实变化时修正记录，不凭聊天记忆继续。

详细事实分别只有一个主文档：仓库入口 REPOSITORY_BASELINE；WBS 逐项状态 WBS_STATUS；RAG/计算 RAG_CALCULATION_AUDIT；流程图 WORKFLOW_GAP_ANALYSIS；测试 TEST_BASELINE。总报告只索引和归纳，避免维护多个相互漂移的副本。


## 2026-09-17 H0批准后的当前状态

用户在完整交付后明确“执行”，已记录evidence/h0_approval.json；REV-02最终复核已闭合。上文“本轮只审计/停H0”为首轮历史边界，现由批准施工范围替代。普通任务按依赖自动推进，原图不改/旧RAG复用/角色数量/重大升级边界继续有效。
