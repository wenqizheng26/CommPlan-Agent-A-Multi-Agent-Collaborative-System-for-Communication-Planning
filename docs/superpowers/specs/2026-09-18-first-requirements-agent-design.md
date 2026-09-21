# 第一个需求与规划 Agent 设计

日期：2026-09-18。状态：设计已整理，供实施前审阅；不表示实现或验收完成。

## 1. 目标与决策依据

第一个 Agent 把用户的通信需求整理成可核对的参数、模型假设和计划建议。当前交付终点是“等待用户确认”，不是生成正式损耗数值。

主pipeline最新已接受的首月目标是：限定自由空间模型的单链路损耗闭环，成功结果可复核，未成功时状态、原因和处理路径可见。首个 Agent 是该闭环的前段；确认、计算、结果验证与结果失效管理由后续模块完成。链路预算、设备选型、方案优化、多链路和真实海面传播均不进入本次验收。

依据优先级：用户最新要求和主pipeline已接受的首月边界 → 本设计的首个 Agent 限定 → SINGLE_AGENT_PLAN.md 的切片接口 → CONTRACTS.md 的总体协议。旧周计划中的 ready_for_calculation 不适用于当前切片。

本轮“完成设计”仅恢复设计文档工作，不解除 NEXT_ACTION.md 对开发、测试、发布和自动恢复的停止要求。只新增本文件，不改共享契约、Backlog、实现或既有交接，不提交 Git。

### 已核实的工程事实

| 证据位置（仓库相对路径） | 事实及设计影响 |
|---|---|
| formula_rag/parsing.py：FIELDS、convert、extract_request | 已有规范字段、单位转换和文本解析。overrides 会覆盖参数并删除对应冲突，新增适配层不能把手工值直接传给这一覆盖路径。 |
| formula_rag/model.py：LocalSelector | 已有本机 Qwen 调用和受限选择 Schema，返回 raw_output、model、usage；仍须严格校验原始 JSON。 |
| formula_rag/interpretation.py：merge_interpretation | 已有原文片段、否定语境和传播条件复核，须在请求副本上调用。 |
| formula_rag/retrieval.py：Retriever.search | 支持既有检索，但零相关候选也可能被排名返回；排名本身不是证据充分的证明。 |
| formula_rag/pipeline.py：Engine.query、DEPENDENCIES | query 会进入计算，不能作为本 Agent 的入口；依赖表可用于未来计划扩展。 |
| knowledge/formulas.json：fspl_ghz | 卡内输入是 frequency_ghz、distance_km，输出声明为 path_loss_db/dB，要求 free_space；描述明确不覆盖海面反射等损耗。 |
| formula_rag/applicability.py：scope_issues | 已有明显近场异常检查；通过这项检查不等于证明真实远场条件满足。 |
| planning/requirements_contract.py | 有切片契约草稿代码，尚不能凭文件存在宣称完成；其部分语义检查仍须按本设计补齐后验收。 |
| tests/test_requirements_agent.py、test_requirements_contract.py | 已有行为测试草稿，代表待验证要求。本轮未运行测试。 |
| tests/test_workflow_dependencies.py | 是框架依赖与内存中断样例，不是业务图或跨进程恢复的交付证据。 |

本次核验未发现适用 AGENTS.md。主pipeline查询时处于 idle。历史 101 项测试结果只作基线，不作为当前 WIP 通过证明。

## 2. 方案与范围

采用“薄适配层 + 一个业务 Agent + 四节点图 + 独立 CLI”。复用现有 parser、单位、目录、检索器和 LocalSelector，在 planning 内补来源合并、计划建议、严格校验和失败说明。

另外两种方案不采用：直接包装 Engine.query 会过早计算；先实现完整多 Agent 和任务平台会扩大当前交付范围。

首月入口的业务能力白名单只有 fspl_ghz。共享请求和报告结构仍沿用 requirements-slice-v1，不删除旧 RAG 其他公式，不改变旧 API 的能力。白名单是可信程序配置，用户文本、模型和检索资料不能扩大它。其他公式最多作为“已识别但本入口不支持”的说明，不生成可确认计划。已有热噪声等通用测试可保留为将来的适配器扩展样例，不能要求首月入口开放这些业务。

保留已识别的非关键参数，明确其不参与当前计划；不能因用户提供功率、增益而扩展成链路预算。不支持范围、候选频段、多个距离时要求用户明确单个工作点，不能擅自取中值或拆成多任务。

## 3. 输入契约

API 保持为 RequirementsAgent(root, selector=None, allow_fallback=True).run(request, expected_revision=...)。selector=None 使用既有 LocalSelector；selector=False 明确选择确定性模式；测试注入 callable 记为 stub，不自动记为真实 LLM。

请求字段必须完整且不得额外添加：

| 字段 | 约束 |
|---|---|
| schema_version | 固定 1.0.0 |
| task_id / request_id | 非空字符串；由调用方建立身份 |
| revision | 非负整数，拒绝 bool；有 expected_revision 时必须相等 |
| raw_text | 字符串，最多 12000 字符；空文本可配手工输入，仍需明确目标和模型条件 |
| manual_parameters | canonical_name → {value, unit}；字段来自 FIELDS；有限数字且单位匹配 |
| condition | null 或 free_space / free_space_reference / non_free_space |
| target | null 或显式目标标识；本入口只可为 fspl_ghz 生成计划 |

示例输入（设计样例，不是运行记录）：

```json
{
  "schema_version": "1.0.0",
  "task_id": "demo-001",
  "revision": 0,
  "request_id": "request-001",
  "raw_text": "按自由空间基准计算，频率2GHz，距离1km，求路径损耗。",
  "manual_parameters": {},
  "condition": null,
  "target": null
}
```

未知字段、未知参数、非有限数、非法类型、单位不匹配或旧 revision 在调用边界拒绝，不调用检索或模型。JSON 入口必须在解析时拒绝重复对象键，不能依赖转换成 dict 后的校验。错误使用稳定错误码和安全说明，不伪造合法 Agent Report。

## 4. 输出契约

顶层字段沿用 SINGLE_AGENT_PLAN.md：schema_version、profile、task_id、revision、request_id、parameters_proposal、conflicts、missing_parameters、candidate_models、calculation_plan_proposal、evidence_ids、evidence_refs、knowledge_snapshot、questions、assumptions、conditions、targets、execution_status、component_modes、runtime_health、diagnostics。

| 输出组 | 精确语义 |
|---|---|
| parameters_proposal | ParameterValue 列表，包含规范值、原值/单位、来源、revision；首版仅 user_provided / missing / conflicting，不输出 confirmed 或 derived。 |
| conflicts | 数值冲突引用至少两个 origin_id；resolution=null。条件和目标争议放 diagnostics/questions，不硬塞进数值冲突结构。 |
| missing_parameters | 当前目标需要且尚无值的字段；冲突与非法值另外说明，不混成“未输入”。 |
| candidate_models | 卡 ID、版本、登记状态和证据引用；仅表示候选，不等于适用性已确认。 |
| calculation_plan_proposal | null 或单步 fspl_ghz 计划；输入绑定 parameter_id，预期输出单位 dB，无结果值。 |
| evidence_refs / knowledge_snapshot | 真实卡片来源、定位、内容 hash、知识版本；不能伪造 source 或模型身份。 |
| questions / assumptions | 需要补充或消除的阻断问题，以及明确列出的模型限制；不把未确认假设自动写成事实。 |
| component_modes / runtime_health | 分别报告解释和检索方式，以及 ready / degraded / unavailable。 |
| diagnostics | 每项 {code, message, details}，记录步骤、原因、有效信息和下一步。 |

AWAITING_CONFIRMATION 只表示建议可供核对：计划非空、输入有效且无缺项/冲突/阻断问题、模型在白名单且登记合格、必要证据齐全、模型条件明确、确定性预检查通过。正式计算资格始终为零。

## 5. 参数来源与冲突处理

1. 对输入进行防御复制，保留未改写原文；先调用旧 parser 解析原文，不传 overrides。
2. 从 parser 的参数、证据与 issues 收集候选。冲突项不能只读最终 parameters，否则会丢候选。对证据片段的细化仍复用原 parser/convert，保留整句否定和范围检查的结论，不把被拒绝片段重新当肯定事实。
3. 手工输入单独转换为规范单位，保留原值/单位和 manual_form 来源。
4. 在同一个字段内比较归一化候选；只容忍浮点换算误差，使用版本化规则 rel_tol=1e-12、abs_tol=0，不用工程容差把两个不同输入合并。
5. 等价值合并为一个 user_provided 参数，但保留所有来源；不同值为 conflicting，主 value=null，保留所有候选，要求用户修正。
6. 没有可用值的必要字段为 missing，value=null。负数或零频率/距离保留为用户输入并报告 INPUT_DOMAIN_INVALID，不能改成默认值或进入确认状态。

ParameterOrigin 保持既有字段：origin_id、kind、source_ref、span、value、unit。origin 的 value/unit 保留原始数值与单位；ParameterValue.value/unit 使用规范值。source_ref 引用 request_id 的原文或手工字段路径；span 只有可在原文准确定位时才填写。无法准确定位则 span=null，并在 diagnostics.details 的来源记录中保存原文片段；不能把规范化文本的位置冒充原文偏移。

手工 target 作为主意图，但若与原文明确目标不同，必须展示差异并追问；手工 condition 与原文互斥时同样阻断。用户明确“只按自由空间基准，不代表实际海面损耗”可以提出基准计划；同时要求实际海面损耗则不能靠手工选择无痕放行。

补充或修正由调用方提交完整新请求：同 task_id、新 request_id、revision+1。首版无会话记忆，不把一句“改成3GHz”暗自合并到未知旧请求。调用方须先更新表单或原文，避免旧值仍保留造成持续冲突。

## 6. RAG 与 LLM 的调用位置

Agent 内部顺序：确定性初解析 → 既有目录与检索 → LLM 意图建议（可禁用）→ 原文证据复核 → 来源合并与模型准入 → 生成计划和问题 → 严格报告校验。

RAG 默认使用 Retriever(dense=False)，模式为 lexical_fallback；复用已有知识目录，不建立第二个索引。检索只提供知识依据，不能产生用户的频率、距离或传播事实。

检索返回前列不代表足够相关。自由文本目标必须有 parser 的明确意图或经 merge_interpretation 核验的原文目标片段；只有 selected_ids 排名不能建立目标。显式 target 可直接解析同一目录中的指定卡，但须记录为显式卡查找，不能伪装成高相似度命中。目标卡缺失、证据为空、只有低相关排名且无目标依据时禁止生成可确认计划。无明确目标时先 AWAITING_INPUT；已明确目标却没有支持证据时 NEEDS_MODEL。

证据 content_hash 按规范 JSON 对实际卡内容计算；catalog_hash 对本次加载的完整目录计算；source_manifest_hash 对真实来源元数据计算。这些 hash 证明内容身份，不证明科学正确。card.status=verified 仅复述库内登记状态，本轮没有独立核实来源文献时必须在 limitations 诊断中说明。embedding_weights_hash、tokenizer_config_hash 为 null，不声称 dense 验证。

LLM 只接收原文与受控候选卡摘要，输出 selected_ids、targets、conditions。严格解析 raw_output：拒绝未知键、错误枚举、重复键、异常类型、越界数量及嵌套额外字段；再核验 ID 在候选集内和证据来自原文。忽略格式化后的宽松字典不能替代这一步。既有 LocalSelector 未返回可验证原始结果时不得以 llm 模式通过。

LLM 不能改参数值、确认输入、发起工具执行、写 Graph 状态或指定 goto。资料里的指令也是资料，不产生权限。日志只保存安全摘要、模型身份、usage、耗时、错误码和证据引用，不记录隐藏推理。

结构错误最多追加两次受限重试，即总调用最多三次；首版复用同一受限调用，不宣称具备尚未实现的带反馈修复提示。连接失败或超时不连续重试，立即按 allow_fallback 决定确定性降级或 FAILED。LocalSelector 当前单次 HTTP timeout 为 120 秒；图八步上限不是时间上限，三次结构失败请求的名义等待预算为约 360 秒加本地开销，不宣称严格墙钟超时。要获得更短硬期限需后续单独修改 transport，不在本设计中假装已有。

## 7. 计划建议与确定性检查

首月计划只有一个 fspl_ghz 步骤：绑定 frequency_ghz、distance_km 的 parameter_id，required_conditions 引用卡的 free_space，expected_unit=dB，dependencies=[]。缺参时可保留含 missing 参数引用的草案，但不能进入确认状态。模型不支持或目标不明确时 plan=null。

计划和每个参数都绑定 task_id/revision；plan_hash 对除自身以外的规范 JSON 计算。校验程序从真实目录核对 tool_id、所需输入键、单位、模型版本、条件和证据，不能仅凭报告自己给出的 candidate_models 白名单自证合法。禁止任意工具名、表达式和模型生成代码。

检查 frequency_ghz>0、distance_km>0，并复用已有 scope_issues 的输入适用性检查。只能做单位换算、输入域及适用性预检查，不调用 evaluate 或 Engine.query，不提前产生 path_loss_db。已过明显近场检查也仍须提示“未证明实际场景满足远场自由空间假设”。卡中舍入常数及版本保持不变。

未来多步骤规划可以复用 DEPENDENCIES，检查 DAG、输入绑定、单位与循环；本次不启用依赖推导，不把派生值填入参数候选。

## 8. LangGraph State、节点与路由

RequirementSliceState 只有四个顶层字段：request（只读输入）、report（合法 Report 或 null）、trace（节点事件列表）、status（处理中状态或四种终态）。State 是内部状态，不是完整 GraphState。程序必须显式验证数据，TypedDict 注解不能替代校验。

| 节点 | 职责和可写字段 |
|---|---|
| receive_request | 校验并复制输入；写 request、status、trace；无网络调用。 |
| propose_requirements | 调用唯一 Agent；写 report、status、trace；LLM 和 RAG 仅在此节点内。 |
| check_requirements | 从可信请求、目录和报告重新检查身份、来源、计划和准入；写最终 status、必要诊断及 trace；不再次调用 LLM。 |
| finish | 固定输出本次 State 和可展示摘要；追加结束 trace；无计算、确认、发布副作用。 |

正常路径为 START → receive_request → propose_requirements → check_requirements → finish → END。receive/propose 有不可恢复错误时通过条件边直接到 finish，不执行后续处理。check 决定业务终态后到 finish；四种业务状态是任务结果，不必为每种状态增加一个 Agent 或空节点。

trace 事件至少包含 node、task_id/revision（可取得时）、开始/结束时间、status、reason_code、attempt、组件模式。失败事件的 details 记录安全错误和下一步。节点采用单写者顺序执行；trace 更新采用返回完整新列表的方式，不同时混用追加 reducer，避免重复事件。request 不被后续节点原地改写。

全图最多执行八个节点，模型重试在 propose 内独立计数；没有自动回到开头的循环。等待用户也是本次调用结束，补充后重新提交请求，不冒充 interrupt/resume。图和 CLI 的应用封装捕获框架异常并输出失败；进程被强制终止或断电的恢复留给后续持久化阶段。

请求本身不合法时 Agent API 抛带稳定代码的边界异常；图封装保留 report=null、status=FAILED 和安全 trace。目录损坏或证据快照根本无法建立时，也采用这一失败形态，禁止为凑 Report 填伪造 hash。CLI 必须展示 trace 中的错误，不能只打印 null。非空 Report 必须完全满足契约；输出校验失败不得把不可信草稿作为正常报告呈现。

状态和条件边的框架语义参考 [LangGraph Graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)；具体实现只使用已锁版本在本地验证的 API，不采用网页中新 API 作为已安装能力证明。

## 9. 阻断、失败和降级必须可见

所有未就绪输出回答四件事：停在哪一步、为什么、哪些输入仍可用、下一步怎么做。用户显示名称由 status 与 diagnostics 联合确定，不只显示一个 FAILED。

| 情况 | 终态 / 错误码 | 呈现与下一步 |
|---|---|---|
| 目标、距离、频率或必要条件缺失 | AWAITING_INPUT / MISSING_INPUT 或 MISSING_CONDITION | 列出具体字段和已知信息，请补充；不编造条件。 |
| 数值来源冲突 | AWAITING_INPUT / PARAMETER_CONFLICT | 并列原文与手工值、单位和来源，请修正。 |
| 目标/条件争议 | AWAITING_INPUT / INTENT_CONFLICT | 展示两种解释，请明确所需目标或基准。 |
| 非正频率或距离 | AWAITING_INPUT / INPUT_DOMAIN_INVALID | 展示原值和规则，请修改；保留有效的其他字段。 |
| 散射、真实海面损耗或首月范围外目标 | NEEDS_MODEL / UNSUPPORTED_SCOPE | 说明边界；可以建议用户另行选择自由空间基准，不能替用户选择。 |
| 明显近场异常 | NEEDS_MODEL / MODEL_NOT_APPLICABLE | 展示检查原因，要求核对单位或选择其他模型。 |
| 已明确目标却无支持卡/充分证据 | NEEDS_MODEL / EVIDENCE_UNAVAILABLE | 不提供可确认计划，提示补充知识依据。 |
| LLM 出错但确定性路径可用 | 由确定性结果决定，health=degraded | 展示 MODEL_UNAVAILABLE 或 MODEL_OUTPUT_INVALID、失败次数、实际采用模式。 |
| 禁止降级且 LLM 失败 | FAILED / MODEL_UNAVAILABLE 或 MODEL_OUTPUT_INVALID | 展示失败节点和重试记录，提示服务恢复后重新提交。 |
| 目录、程序、报告校验、预算错误 | FAILED / CATALOG_INVALID、REPORT_INVALID、STEP_LIMIT 等 | 没有正式结果；保留可信输入摘要，不返回无效草稿。 |
| 旧版本请求 | FAILED / STALE_REVISION | 不调用 Agent 依赖，提示载入当前版本重新提交。 |

多个阻断原因全部保留，主状态按不可恢复失败 → 明确模型/能力缺口 → 输入问题 → 等待确认的顺序选择。成功降级不是不可恢复失败；必须标明降级后是否仍有输入或模型问题。首版不计算部分目标，也不把其他目标的局部成功掩盖整个请求的能力缺口。

确定性模式是用户主动选择时，健康的词项检索与解析可记 ready；自动从模型失败切换才记 degraded。stub 仅为测试，不算真实模型通过。业务等待状态与 CLI 进程成功退出分开：正常生成等待报告 exit 0，边界请求错误 exit 2，不可恢复执行失败 exit 1。

界面示例（设计文案）：

> 当前状态：等待消除冲突。频率在原文中为 2 GHz，手工输入为 3 GHz；距离 1 km 已识别。请统一频率后重新提交。本次尚未生成正式计算结果。

> 当前状态：超出模型能力范围。已识别频率 4.5 GHz、距离 30 km；当前入口只能规划自由空间基准，不能给出真实海面传播损耗。如需基准比较，请明确改为自由空间基准。

## 10. 最小验收矩阵

以下均为待执行验收要求，不是本轮测试结果。

| 编号 | 场景 | 必须验证 |
|---|---|---|
| A01 | 明确自由空间基准、2 GHz、1 km、求损耗 | AWAITING_CONFIRMATION；单步计划、真实卡版本与来源；无损耗值。 |
| A02 | 缺频率或距离 | AWAITING_INPUT；缺项为 null，无默认值。 |
| A03 | 只有频率和距离、未指定自由空间条件 | AWAITING_INPUT；不能从视距或岸海推断 free_space。 |
| A04 | 原文 2 GHz 与手工 3 GHz | conflicting/null；双方来源保留，不能覆盖。 |
| A05 | 2 GHz 与 2000 MHz | 等价合并，保留两来源。 |
| A06 | 否定、举例、范围、科学计数 | 不采纳被否定/范围候选；明确合法的科学计数按旧 parser 支持范围处理。 |
| A07 | 请求真实海面、散射损耗或链路余量 | NEEDS_MODEL；不偷换 FSPL，不扩展首月目标。 |
| A08 | 缺目标/零相关返回/空检索证据 | 无目标先追问；已明确目标无证据时阻断；排名不能制造目标。 |
| A09 | 非正输入和明显近场 | 输入或适用性阻断，原因可见，不提前调用损耗公式。 |
| A10 | 模型捏造参数、未知键、重复键、错误类型、假证据、否定片段 | 拒绝模型输出，原始数值不被改变；结构重试总计不超过三次。 |
| A11 | 模型超时/服务异常 | 一次失败后降级或 FAILED；明确模式和次数，不伪报 llm。 |
| A12 | 身份不符、旧 revision、非法嵌套字段、NaN/Infinity/bool 数值 | 调用前或报告出口拒绝；不污染其他请求。 |
| A13 | 伪造卡/单位/计划绑定/来源 hash | 校验从可信目录和请求发现不一致，不能报告可确认。 |
| A14 | 目录加载失败、Agent 异常、无合法 Report | FAILED、report=null、安全 trace 和可读原因，无虚构 snapshot。 |
| A15 | 正常四节点、早期失败短路、步数上限 | trace 顺序正确，失败不继续提建议，不存在无限循环。 |
| A16 | CLI 完整/缺参/冲突/不支持/失败演示 | 业务状态、失败原因、下一步和退出码匹配。 |
| A17 | 每一条路径 | Engine.query 与 core.evaluate 的执行均为零；无 confirmed 参数或正式 result。 |
| A18 | 旧功能与真实模型 | 既有 101 项基线及新增测试独立回归；真实 Qwen 单列验证，记录调用身份、usage、日志与模式。 |

验收需同时检查“应当放行到确认的请求能放行”和“应当阻断的请求被正确阻断”。A17 除 mock 行为断言外须检查实际调用入口，避免预先绑定的函数别名绕过 mock。真实模型不可用时可以分别报告确定性路径验收结果和 LLM 未验证，不能宣称完整本地 LLM Agent 已通过。

## 11. 实施文件与后续接入

未来实施限定为 planning/requirements_contract.py、planning/agents/requirements.py、planning/services/requirement_parameters.py、planning/services/requirement_evidence.py、planning/workflow/requirements_graph.py、planning/demo.py 及对应测试。状态定义可放在 requirements_graph.py，首版不额外建设完整状态平台。

实施顺序：核对停止状态已解除与唯一 owner → 补齐契约语义和失败出口 → 参数来源与证据适配 → Agent → 四节点图和 CLI → 独立验收 → 交接。依赖已有隔离环境；没有新需求不重新安装或升级。formula_rag、app.py、web、知识公式、原始 WBS/VSDX、模型文件及源 venv 保持原有所有权。

本设计新增的首月白名单、报告无效时的失败出口和严格语义验收，是实施前需同步到 SINGLE_AGENT_PLAN/Backlog 的设计细化。本轮不改冻结版本；未来实施者须先记录差异、复核契约兼容性，不能按旧通用样例默默开放全部公式。

完整 pipeline 接入时，将 report 的候选参数、冲突、证据和计划映射到 RequirementPlanningOutput；仍不映射为 confirmed。后续确认门展示本次输入/模型/假设/计划并建立不可变 ConfirmedSnapshot，计算服务只从该快照生成请求，复用完整确定性检查链。首个 Agent 无权生成或替换 CalculationResult。

关键输入、目标、模型或知识版本变化时，由完整任务层创建新 revision，使旧计划、确认及结果失效。首个 Agent 只处理指定 revision 并保留身份，expected_revision 相等检查不等于持久 CAS，也不能防止调用方复用旧 revision。跨进程 checkpoint、重复确认、结果失效 UI 和失败恢复均属于后续闭环验收。

## 12. 设计自检与交付说明

设计覆盖：目标/替代方案、输入输出、State/节点/路由、LLM/RAG 调用位置、确定性边界、来源与冲突、缺参/未知模型/故障降级、失败展示、验收与完整 pipeline 接口。

无实现代码、依赖、共享控制文件或 Git 变更。本文件不代表 Agent 已运行，不代表已完成首月单链路损耗闭环；待用户审阅设计后，再由明确授权的实施任务接管。
