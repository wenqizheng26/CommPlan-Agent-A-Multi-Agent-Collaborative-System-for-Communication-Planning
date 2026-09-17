# 首个需求与规划 Agent 实施计划

用户最新范围：先完成一个 Agent，子 Agent 继续阶段提交 GitHub。Main 依据既有 H0 和本次明确实现指令收敛为本切片；完整35任务保留，不自动扩展到其他业务角色。

## 目标与验收

输入自然语言和显式手工参数，复用 formula_rag 的 parser、单位、interpretation、LocalSelector、Retriever，输出可审查参数/来源、冲突、缺参、能力缺口、证据和计划建议。LangGraph 只驱动接收、提出建议、检查及结束。所有路径禁止计算或确认：齐全仅 AWAITING_CONFIRMATION；缺参/冲突 AWAITING_INPUT；未知传播模型 NEEDS_MODEL；故障 FAILED 或标明 deterministic/degraded 的降级建议。

使用独立 RequirementSliceState，不声称完整 GraphState、持久checkpoint、用户确认resume或其他三个Agent已交付。既有未跟踪周计划保留为参考，其中 ready_for_calculation 不作为本切片执行资格。

方案选择：采用薄适配器和独立CLI演示，可逐步接回完整图；直接包装Engine.query会提前计算，不能采用；先完成整35任务才实现一个Agent超出当前范围，暂不推进。

## 已冻结切片公共接口（Main语义owner）

模块 planning/requirements_contract.py，与完整目标 planning/contracts.py 区分。schema_version=1.0.0；profile=requirements-slice-v1。

Request字段精确为 schema_version, task_id, revision, request_id, raw_text, manual_parameters, condition, target。manual_parameters为canonical_name→{value:number,unit:str}；condition/target可null；其他字段拒绝。身份非空，revision非负整数且非bool，有限数，文本长度依旧parser。单位由既有convert/FIELDS转换，保留手工原值与单位。

Report字段：schema_version, profile, task_id, revision, request_id, parameters_proposal, conflicts, missing_parameters, candidate_models, calculation_plan_proposal, evidence_ids, evidence_refs, knowledge_snapshot, questions, assumptions, conditions, targets, execution_status, component_modes, runtime_health, diagnostics。proposal使用Contract ParameterValue/Origin形状；冲突保留所有来源且value=null。缺项不能用0、290K补齐。原文规范化可能改变span时允许span=null并保留准确source_ref和原文片段；不能伪造偏移。

Evidence与snapshot使用既有Contract语义，真实card source/version/status/hash。本阶段默认lexical_fallback且embedding/tokenizer hash=null；仅真实使用并计算身份后才称dense。未独立核实来源文档必须保留审核限制。不得引入第二个索引。

计划只绑定已登记formula_id/required_parameters/依赖步骤/单位/条件，不执行。优先显式target；LLM selected_ids只用于受控意图选择，targets/conditions必须由merge_interpretation按原文证据重新验证；无目标/低相关/不支持不能默认FSPL。复用旧DEPENDENCIES但不调用Engine.query或evaluate。

模型输出严格检查JSON原始结果未知字段、枚举、格式，不能仅信任LocalSelector解包后丢弃未知键的字典。模型数值不能成为参数。有限结构修复最多2次；请求总图步数上限8。组件分别记录interpretation=llm/deterministic/stub、retrieval=lexical_fallback/dense/stub，health=ready/degraded/unavailable。真实调用需日志、模型身份和usage证据，stub不冒充llm。

Agent API RequirementsAgent(root, selector=None, allow_fallback=True).run(request, *, expected_revision=None) -> Report；selector默认为既有LocalSelector，显式deterministic CLI选项可禁用。每次输入防御复制；expected_revision不等拒绝STALE_REVISION。无全局共享任务缓存；新文本/手工修改必须由调用方新revision，此切片不提供编辑API。输出与输入身份一致、未知字段/布尔数值/非有限数均拒绝。

Graph API build_requirements_graph(agent) 与run_requirements(request, agent, expected_revision=None)。状态只含request/report/trace/status；合法终态不含COMPLETED正式发布或READY_TO_CALCULATE。trace记录节点/状态/revision/时间/模式而不输出模型隐藏推理。CLI python -m planning.demo --text ... [--deterministic]。

## 工作分解与所有权

SA-ENV：隔离.venv、requirements.lock.txt、tests/test_workflow_dependencies.py、DEPENDENCY_DECISION.md、evidence/sa_env.json。Astra环境worker。
SA-CORE：planning/__init__.py、planning/requirements_contract.py、planning/agents/__init__.py、planning/agents/requirements.py、planning/services/__init__.py、planning/services/requirement_parameters.py、planning/services/requirement_evidence.py、tests/test_requirements_contract.py、tests/test_requirements_agent.py、evidence/sa_core.json。单一Astra实现者，Main授权切片字段实现，不可自行改本契约。
SA-GRAPH：planning/workflow/__init__.py、planning/workflow/requirements_graph.py、planning/demo.py、tests/test_requirements_graph.py、tests/test_requirements_demo.py。SA-CORE同一owner在ENV和CORE通过后串行实现。
SA-REVIEW：非实现者Astra只读代码并写evidence/single_agent_review.json；检查权限、冲突、单位、计划依赖、模型降级、证据hash和旧API。
SA-RUN：独立全量回归、三类CLI与一次有界真实本地模型验证，evidence/sa_validation.json及日志；模型未就绪则先查既有启动方式和资源，在授权本地资源内启动。无法真实运行必须明确剩余限制。
SA-HANDOFF：Main写SINGLE_AGENT_HANDOFF.md、IMPLEMENTATION_LOG、NEXT_ACTION、PROJECT_CONTEXT、Backlog状态。
SA-PUBLISH：github_luna唯一Git操作者，精确已审核文件allowlist提交；账号wenqizheng26，新private仓库；远端SHA一致才标上传。

任何worker不修改formula_rag、旧app.py、web、知识公式、原图、原始表格、sourcevenv。只允许上述路径；.git只publisher可经Git工具操作，最多Main+3子Agent。单项修复最多2轮后升级Main，不自动增加业务Agent。

每项代码先写行为测试看RED再最小实现看GREEN。完整输入/缺参/文本多值冲突/手工冲突/等价单位/未支持模型/否定/伪造参数/LLM错误/无证据/旧revision必须覆盖；全部既有101项回归应保留。ENV独立先行；CORE与ENV可并行；GRAPH串接；REVIEW和独立RUN并行；通过后PUBLISH。

完整35任务中T005/T009/T011/T019/T020仅部分覆盖，后续合并完整协议时继续原验收，不因本切片通过而标完成。

运行验收可复用原本地 Qwen 权重与 llama.cpp 可执行文件（均只读），新进程日志与身份仅落本切片 evidence/sa-model.* 和 sa_model_process.json；启动限回环、offline、hidden，新进程本次验证结束后按记录PID精确停止，不影响已有服务。模型进程日志不随GitHub快照上传。
