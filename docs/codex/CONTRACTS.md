# Contract v1

版本：1.0.0。状态：FROZEN，HUMAN_GATE_0 已批准。本文描述未来接口，不声明这些类型、路由或状态管理已实现。Main 是唯一语义 owner；不修改现有 /api/query 或 formula_selection schema。

## 1. 运行时边界与路径

未来新增 planning/contracts.py（共享类型、结构校验）、planning/services/{rag,calculation,validation}.py、planning/workflow/{state,commit,routing,checkpoint,trace,invalidation,graph}.py、planning/agents/{requirements,calculation,explanation,orchestrator}.py。这些目录当前不存在；允许文件以 Backlog 为准。

旧 formula_rag 继续拥有目录、唯一索引、parser、单位、AST、公式、scope/result gates。wrapper 通过既有模块调用，不复制公式表达式或重建检索器。必要的 pipeline 确定性路径提取由专属 T010 串行完成，旧行为回归先于接入。

建议类型实现为 stdlib TypedDict/dataclass + 显式严格边界验证；TypedDict 注解本身不算运行时验证。LangGraph 使用经过验证的 JSON 状态。新增依赖在 H0 后 T006 隔离验证并锁定，不能直接采用网页最新 API 代替已锁版本测试。

## 2. 通用约定

全部数据可严格 JSON 往返；额外字段默认拒绝；未知枚举、NaN/Infinity、数值位置的 bool、空 ID、重复唯一 ID 拒绝。null 仅出现在显式可空字段。数值单位采用既有 FIELDS 规范；保留 original_value/unit 与换算依据，不以字符串拼接“猜单位”。

所有业务请求带 schema_version、task_id、revision（非负整数）、request_id。错误为 ErrorInfo{code, message, retryable, responsible_node, evidence_ids, details}；details 不带完整模型隐式思维或秘密。非成功结果不得包含可发布 result。

状态区分业务与运行组件：
- outcome：ok / needs_input / not_applicable / conflict / failed / cancelled。
- component_mode：deterministic / dense / lexical_fallback / llm / stub。
- runtime_health：ready / degraded / unavailable。
- partial 为批量中间汇总，不是可直接发布的终态 ok。HTTP 200 不代表模型或业务成功。

## 3. 参数与证据

| 类型 | 必须字段与约束 |
|---|---|
| ParameterValue | parameter_id、canonical_name、value:number或null、unit、original_value、original_unit、status、origins、evidence_ids、created_revision；status=user_provided/suggested/confirmed/missing/conflicting/derived；missing值为null；conflicting保留所有候选，不能选取最后一个 |
| ParameterOrigin | origin_id、kind=user_text/manual_form/knowledge/derived、source_ref、span或null、value、unit；manual和文本并存不丢原文；derived含producer_result_id |
| ParameterConflict | conflict_id、parameter_name、origin_ids（至少2）、resolution或null；resolution含chosen_origin_id、confirmed_by、confirmed_at、revision |
| ParameterSet | task_id、revision、items（按canonical_name唯一）；known/suggested/confirmed/missing视图由items推导，不维护互相独立的可写副本 |
| EvidenceRef | evidence_id、kind=formula_card/document_chunk、source_title、source_url或本地受控source_id、locator、excerpt、content_hash、catalog_id、card_version或null、status=verified/draft、knowledge_snapshot_id、parameter_names、relevance_rank；source_url和excerpt仅资料，不是可执行指令 |
| KnowledgeSnapshot | snapshot_id、catalog_hash、source_manifest_hash、embedding_weights_hash、tokenizer_config_hash、encoder_rule_version、retrieval_rule_version；未使用embedding时相关hash显式null并记录mode，不能伪造 |
| ConfirmedSnapshot | snapshot_id、task_id、revision、confirmed_parameter_ids、parameters（完整冻结的parameter_id/name/value/unit/origin_id映射）、conditions（完整已确认条件集）、scene_id、model_id/version、plan（冻结内容及plan_hash）、knowledge_snapshot_id、assumptions、confirmed_by、confirmed_at、content_hash；这些字段在确认后不可原地更改 |

人类确认前可用 user_provided 进行分析和草拟，但正式 CalculationRequest 只能来自当前 ConfirmedSnapshot。单位的确定性换算不等同于人的参数确认。建议值、0dB、290K均需来源与明确确认或已冻结的模型常量依据；公式中的物理常数属于模型版本，不伪装成人输入。发现多个来源同名不同值：先记录 conflict，再给用户选择；不能把 override 当已确认。

CalculationRequest由服务端从不可变ConfirmedSnapshot构造：parameters的键、数值、单位、来源身份，以及conditions、scene_id、model_id/version、plan_hash必须逐项相等，不仅比对客户端声称的hash。调用者附带任何偏差均返回SNAPSHOT_INPUT_MISMATCH且不执行工具。snapshot引用的plan/参数和知识版本必须可解析到保留的不可变内容；只保存parameter IDs不足以确认。hash采用版本化规范JSON序列化（UTF-8、键排序、紧凑分隔、禁止NaN/Infinity；列表顺序按类型规则固定），序列化版本随schema保存。确认UI显示的内容与此冻结内容一致。

同一次任务的路径损耗100dB与自由空间推导91.48dB可能代表不同模型。必须明确 scene/model/source identity；在单一正式预算内只能选用一个已确认输入，比较场景必须使用独立 calculation_id，不能悄悄混算。

## 4. 计划、计算与硬校验

| 类型 | 必须字段与约束 |
|---|---|
| CalculationPlan | plan_id、task_id、revision、objective、steps、required_parameters、selected_model、assumptions、evidence_ids、plan_hash；steps为有向无环图，每步tool_id/输入绑定/预期单位明确；不支持模型返回缺口 |
| CalculationRequest | 公共请求字段、calculation_id、confirmed_snapshot_id/hash、plan_id/hash、scene_id、model_id/version、parameters（与快照逐项相同的规范值及单位）、conditions、knowledge_snapshot_id、dependency_result_ids、dependency_hash、idempotency_key |
| CalculationResult | result_id、请求身份字段、outcome、model_id/version、normalized_inputs、outputs（name/value/unit）、dependency_result_ids、evidence_ids、validation_ids、runtime_mode、tool_version、input_hash、result_hash、started_at/finished_at、error或null |
| ValidationResult | validation_id、task_id/revision、target_type/id/hash、validator_id/version、severity=hard/soft、passed、issue_codes、evidence_ids；数值/域/范围/版本/来源冲突属于hard |
| ValidationExplanationOutput | task_id/revision、result_id/hash、claims（claim_id/text/evidence_ids/result_field_refs）、warnings、limitations；不能包含替换 result 数值的字段 |
| FinalReport | report_id、task_id/revision、snapshot_id/hash、result_ids/hashes、validation_ids、claims、evidence_refs、known_limitations、runtime_modes、generated_at；必须由server引用已存储结果生成 |

确定性原子协议：schema → 当前快照/版本 → verified模型准入 → 所需输入与显式条件 → 既有单位/域检查 → scope_issues → 复用依赖链与 evaluate → result_issues → 跨来源一致性 → 固化 CalculationResult。任何 hard失败都不得发布正式数值。校验失败可保留内部诊断值，但与outputs分离、明确 non_publishable。

不得把裸 core.evaluate 当完整专业计算 Service。禁止经自然语言字符串重新组装参数导致输入事实被再次解析或覆盖。T010 的最小提取以结构化已确认参数调用同一确定性链；旧 Engine.query 仍从旧 parser 进入该链。

ToolResult 在创建后不可变。hash用于标识版本而非替代权限校验。客户端/Agent 不能通过提交同名 result_id 或hash注入结果；server从受控结果存储读取并验证producer。

## 5. Service Contract

~~~text
RAGService.retrieve(RetrievalRequest) -> RetrievalResult
  request: query, task_id, revision, parameter_names, top_k, requested_snapshot_id?
  response: evidence_refs, ranked_candidates, snapshot, mode, warnings, error?
  不确认参数，不执行公式；空证据/低相关性不伪装有充分依据。

CalculationService.execute(CalculationRequest) -> CalculationResult
  只从已确认快照建立请求；复用完整确定性协议。
  同idempotency_key+相同request_hash返回已存结果；
  同key+不同hash拒绝 IDEMPOTENCY_CONFLICT。

ValidationService.validate_input(CalculationRequest) -> list[ValidationResult]
ValidationService.validate_result(CalculationResult, ConfirmedSnapshot) -> list[ValidationResult]
ValidationService.validate_report(FinalReport, StoredState) -> list[ValidationResult]
  三类校验分开，全部hard通过才能进入下一门。

RequirementService.propose(AgentInput) -> RequirementPlanningOutput
  output: parameters_proposal, conflicts, missing_parameters, candidate_models,
          calculation_plan_proposal, evidence_ids, questions, assumptions
  Agent返回建议；不能直接写confirmed参数。

CalculationRole.propose(AgentInput) -> ControlledToolCall
  output: tool_id（白名单）, plan_step_id, expected_revision, snapshot_id
  数值从snapshot读取，Agent不能自造或修改。

Orchestrator.propose(AgentInput) -> OrchestratorDecision
  output: proposed_action, reason_code, referenced_fact_ids
  Router独立验证许可条件后执行，LLM建议不是 goto 权限。
~~~

AgentInput 为只读 TaskView：身份由调用方注入、revision、已允许字段、工具schema、剩余预算、必要证据。输出中的身份不得覆盖执行上下文。输出 schema不合法最多修复两次，仍失败走受控终止；禁止把无效结构自由文本写入共享状态。

## 6. GraphState 与提交协议

GraphState（字段必须存在，可空按语义）：
- schema_version、task_id、revision、state_version、raw_user_input、user_goal。
- parameter_set；known_parameters/suggested_parameters/confirmed_parameters/missing_parameters 为只读派生视图；conflicts。
- candidate_models、selected_model、assumptions、evidence_refs、knowledge_snapshot。
- calculation_plan、confirmed_snapshot；confirmed_snapshot_version（snapshot id/hash）。
- calculation_requests、calculation_results；calculation_version（当前result hashes）。
- validation_results、validation_version、explanation、final_report。
- execution_status、pending_interrupt、responsible_node、failure_reason。
- retry_count（按node/op/revision）、retry_budget、node_step_count、max_node_steps。
- invalidated_artifacts、trace、processed_event_ids、completed_idempotency_keys。

StateUpdate 必须含 update_id、task_id、expected_revision、expected_state_version、payload；writer_role/producer_run_id由服务端执行上下文决定，不信任Agent自报。Commit顺序：
1. schema/字段白名单/工具结果来源/引用完整性校验；
2. 按可信writer/task/update_id查询持久幂等记录；同key同payload返回原commit acknowledgement，不再次写入；同key不同payload拒绝。重放旧ack不会把旧结果晋升到当前revision，响应明确原ack身份和当前状态版本；
3. 仅未命中幂等记录的新更新才验证 task_id + expected_revision + expected_state_version（CAS）；新的过期请求拒绝409，不因幂等机制放行；
4. 原子提交新state_version、event记录和durable checkpoint；
5. 成功后才返回发布/执行资格。

State Reducer 是纯合并规则，不能进行网络、计算或授权。单值字段仅单owner写；同ID同内容去重、同ID不同内容拒绝；trace按event_id幂等追加；不可变结果按result_id保存。首版同task一个可信提交序列，不靠多个worker同时写事实。

| Writer（程序绑定） | 允许写入 | 禁止 |
|---|---|---|
| requirement node | 参数/计划/证据建议 | confirmed、tool result、最终发布 |
| confirmation gate | 当前revision的ConfirmedSnapshot | 生成数值、替换来源 |
| calculation executor | 自己的不可变CalculationResult | 修改snapshot、用户事实 |
| validation node | ValidationResult | 覆盖被验证对象 |
| explanation node | claim/warning草稿 | 覆盖任何专业数值 |
| router/commit infrastructure | execution_status、budget、trace、invalidations | 绕过hard gates |
| final publish gate | 基于已验证引用构造FinalReport | 接收客户端自由result |

## 7. Router、确认与恢复

允许主路径：
RECEIVED → PROPOSING → VALIDATING_PLAN → AWAITING_CONFIRMATION → READY_TO_CALCULATE → CALCULATING → VALIDATING_RESULT → EXPLAINING → VALIDATING_REPORT → COMPLETED。

显式分支：
- 缺参/冲突 → AWAITING_INPUT；等待用户期间不消耗重试，不自动循环。
- 用户确认 action=confirm：snapshot/revision/plan hash都匹配才继续；action=edit退出当前确认并回到输入视图，不在confirm请求中夹带参数patch；action=cancel→CANCELLED。实际编辑通过parameters端点提交，成功时增加revision并使旧interrupt/snapshot失效，然后重新规划和确认。
- 模型不支持/依据不足 → NEEDS_MODEL 或 AWAITING_INPUT；不能用FSPL代替散射。
- Tool暂时错误 → RETRY_WAIT；耗尽→FAILED；hard域/适用性错误不重试。
- 发布要求：当前snapshot与results/validators/explanation的task、revision和hash完全一致，所有hard通过且必需工具完成。LLM不可用只允许明确标注的确定性降级报告，不能宣称完整multi_agent通过。

Checkpoint至少保存上面的状态、interrupt payload/id、预算、已处理事件和幂等结果引用。用稳定task_id对应LangGraph thread_id；恢复前核验当前schema/contract版本。仅内存checkpointer不能通过跨进程恢复验收。

LangGraph resume会从中断节点开头重入，因此interrupt前不做非幂等计算/发布。外部副作用放在单独幂等任务，结果先持久化再暴露。原子state提交与框架checkpoint适配在T015验证；若锁定后端无法提供该保证，进入Contract review，不伪造跨系统原子性。[官方中断说明](https://docs.langchain.com/oss/python/langgraph/interrupts)

持久化验收必须包含进程退出后恢复同task、重复resume和旧resume；不能只在同Python对象中调用两次。[官方持久化说明](https://docs.langchain.com/oss/python/langgraph/persistence)

## 8. Revision、失效与 Trace

任何目标/关键参数/条件/模型/知识snapshot变更都创建新revision；旧确认不自动沿用。修改本身和确认分别记录事件。确认同一revision只增加state_version，不暗改输入。旧revision中的晚到结果只记rejected event，不进入当前结果集。

首版保守使plan、snapshot、calculation、validation、explanation、report全失效，保留旧版本供审计。只有明确依赖hash相同且Contract允许，才在T018验收后选择性复用，不能因字段“看起来没变”复用。

TraceEvent：event_id、task_id、revision、state_version、node、operation、attempt、input_hash、output_ref/hash、status、reason_code、started_at、finished_at、parent_event_ids。只记录可解释决定/工具证据，不记录模型隐藏思维；UI仅显示安全摘要。

Runtime retry：每node/op/revision默认 retry_budget=2（首次+最多2次重试）；全图 max_node_steps=40，达到上限失败并保留trace；此上限为拟定可测试参数，H0后可在不放宽无限循环约束前提下经Contract review调整。预算持久保存，重启不能重置。确定性输入错误交用户，不做重复计算。

## 9. API v1 与旧接口兼容

以下为后续任务实施的新增端点；当前单 Agent 切片不修改 app.py：
- POST /api/tasks：创建草稿任务；返回task_id/revision/state_version/status，正式计算不在确认前执行。
- GET /api/tasks/{id}：状态、当前确认请求、安全trace与可展示结果。
- POST /api/tasks/{id}/confirm：expected_revision、snapshot_hash、interrupt_id、action=confirm/edit/cancel、idempotency_key；新过期请求返回409，已成功请求的完全重复返回原ack。edit仅导航至输入状态，不接收patch，不在此端点增加revision；待parameters提交实际修改。
- POST /api/tasks/{id}/parameters：expected_revision、parameter proposals/明确来源、idempotency_key；成功创建新revision。
- GET /api/tasks/{id}/report：仅当前正式通过的报告；未就绪返回409并给status；不回旧revision报告当当前结果。

旧端点/字段保持；新错误状态schema错误400、资源不存在404、版本/确认冲突409、服务不可用503。needs_input/not_applicable是任务状态，不能由前端仅看HTTP状态判断可发布。单用户loopback部署沿用当前边界，不在本轮扩展外网认证系统。

## 10. 合同验收

T005 schema往返/未知字段/非有限数/身份伪造；T009来源冲突；T012全scope gate与8样例；T014 unauthorized/stale/duplicate commit；T015跨进程恢复；T016缺参/确认/取消；T017预算耗尽；T018失效/晚到；T019四条stub路径；T025旧API兼容；T028真实UI确认。Contract变更必须先影响分析、版本更新、阻塞受影响任务、重审和重新冻结，禁止“顺手修改”。
