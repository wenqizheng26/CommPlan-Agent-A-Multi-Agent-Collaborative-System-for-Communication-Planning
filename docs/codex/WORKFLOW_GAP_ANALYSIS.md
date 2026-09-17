# 工作流差距与流程图一致性审计

AUD-01，2026-09-17。权威输入为桌面原始VSDX，ZIP/XML只读解析；不以仓库v1.4图替代。原图未修改。证据见evidence/diagram_nodes.json（页面、Shape ID、文本、Cells、Connect记录与SHA256）。XML可证明文本/连接引用；未在Visio视觉核验线重叠、颜色、箭头端方向或版式。

## 实现与设计边界

|能力|当前实现证据|设计缺口|
|---|---|---|
|Workflow|Engine.query单次函数 pipeline.py:25|无StateGraph编译/执行|
|GraphState|request/values/completed局部字典 pipeline.py:69|无持久共享状态/授权提交/reducer|
|Schema|catalog.py:17手工元数据校验；model.py:25 strict formula_selection JSON Schema|无任务/Agent/ToolResult强类型契约|
|Router|pipeline.py:86起确定性条件分支|无角色调度/版本门/有限retry协议|
|checkpoint|app.py:21内存results缓存|无跨重启恢复；JSON导出不等于checkpoint|
|confirmation|web/assets/app.js:16直接计算|无确认快照/interrupt/resume|
|revision/invalidation|每次query重新计算|无旧结果失效图/晚到结果拒绝|
|trace|pipeline.py:36 runtime信息|无task/revision/node/attempt因果事件链|
|Agent|model.py:8 LocalSelector|无1+3独立角色输入输出与权限|

## 流程图一致性审计：八问

1. 建议保留：1+3平级角色、共享RAG/LLM、确定性数值、先确认再计算再审查、模型缺口停止、程序提交共享状态。page1 Shape99/110与page2 Shape250清楚区分角色平级和数据依赖。

2. 已有节点/链路基础：page2 Shape92/97对应model.py:15/parsing.py:76的旧解析；104/109对应retrieval.py:89与卡source；155/166/181对应scope/core/result校验；211对应app.py:74导出。只能称能力复用，未证明在图示工作流节点中运行。

3. 完全缺失：总控角色调度、规划Agent协议、任务级确认门/快照、checkpoint恢复、reducer授权提交、review版本绑定、预算重试/失败分类、正式发布门、trace及参数变化的跨运行失效。

4. WBS映射：1.x负责图的业务/架构/角色/契约/验收；2.x支撑89/95与page2 104/109/192；3.x支撑66/155/166/181；4.x将所有调度、确认、状态与Agent组合为受控运行时；5.x对应35/59/71和page2 83/136/206/211。窄Demo完成不能代表3.2/3.3等总体任务验收。

5. 与RAG：复用现有Retriever卡索引，新增稳定Evidence返回字段和知识快照，不新建第二RAG。图page1 Shape96提及设备手册/规则/案例；仓库七卡未证明覆盖全部；Shape111“分块和索引”只有卡级document拼接实现。

6. LangGraph映射：四角色可以各作为Node承载Agent协议；决策由条件边执行；确认用interrupt/resume；校验/计算为确定性Node/Tool；state更新交授权reducer/commit层；检查点独立基础设施。本文不冻结依赖版本/API，交主AgentContract review。

7. 风险：page1计算Agent描述含校验和正式损耗输出，若全部交LLM会越权；page2各菱形应程序判定。page2 227有限重试仅文字，缺budget持久状态与耗尽出口详细协议；141否回补参需区分拒绝/取消/修改，避免用户不确认时自动回环。145提交确认与171提交结果需原子版本核验；202一致性审查不可单靠LLM自由覆盖数值。Connect原记录有成对连接（同组连接点不同），不得据线数推断重复业务调用；端方向需视觉复核。

8. 建议后续修改清单（本轮未改）：标注程序gate与Agent边界；给确认否分支增加取消/重新规划语义；标出retry耗尽/不可恢复终点；状态箭头注明只读/建议/程序提交权限；加入revision/晚到结果拒绝与恢复幂等说明；明确Demo外链路预算/候选比较所在阶段。核心业务图变更须H0/升级确认。

## 功能块工程分类

下面按原始文字Shape定位；相邻说明Shape归属同一功能块，标题、泳道、图例、是/否和页码为标注而非独立Agent。Connect全量保留在JSON。

|页面/Shape|原文功能块|建议工程实体|
|---|---|---|
| visio/pages/page1.xml / 2 | LangGraph · 流程编排与状态管理 | Workflow Infrastructure |
| visio/pages/page1.xml / 35 | 用户输入通信需求 | UI / LangGraph Node |
| visio/pages/page1.xml / 39 | 总控 Agent | Agent（总控建议）+ Router（程序决定边） |
| visio/pages/page1.xml / 44 | 需求与规划 Agent | Agent |
| visio/pages/page1.xml / 49 | 专业计算 Agent | Agent（受控调用） |
| visio/pages/page1.xml / 54 | 验证与解释 Agent | Agent（解释）+ Validator（程序） |
| visio/pages/page1.xml / 59 | 参数核对与确认 | Human-in-the-loop Gate |
| visio/pages/page1.xml / 66 | 链路损耗计算模型 | Tool / Service / Deterministic Function |
| visio/pages/page1.xml / 71 | 结果与证据报告 | LangGraph Node + 发布Validator |
| visio/pages/page1.xml / 77 | 共享状态 / 本地检查点 | State Reducer + Checkpoint / State Infrastructure |
| visio/pages/page1.xml / 82 | 共享大模型 LLM | Service |
| visio/pages/page1.xml / 89 | RAG 检索服务 | Service / Tool |
| visio/pages/page1.xml / 95 | 专业知识库 | Service（只读知识资产） |
| visio/pages/page2.xml / 83 | 用户输入链路计算需求 | UI / LangGraph Node |
| visio/pages/page2.xml / 87 | 总控调度需求与规划 Agent | Router / Conditional Edge |
| visio/pages/page2.xml / 92 | 调用 LLM 解析任务 | Service调用Node |
| visio/pages/page2.xml / 97 | 生成结构化参数草稿 | Schema Validator / Node |
| visio/pages/page2.xml / 104 | 调用 RAG 检索专业依据 | Tool / Service |
| visio/pages/page2.xml / 109 | 获取带来源的知识片段 | Evidence Validator / Node |
| visio/pages/page2.xml / 114 | 检索依据可用？ | Router / Conditional Edge |
| visio/pages/page2.xml / 118 | 组织知识增强上下文 | Deterministic Function |
| visio/pages/page2.xml / 123 | 调用 LLM 制定计算计划 | Agent（需求与规划） |
| visio/pages/page2.xml / 128 | 已登记模型支持？ | Validator + Conditional Edge |
| visio/pages/page2.xml / 132 | 必要信息齐全？ | Validator + Conditional Edge |
| visio/pages/page2.xml / 136 | 用户核对与确认 | Human-in-the-loop Gate |
| visio/pages/page2.xml / 141 | 当前方案已确认？ | Validator + Conditional Edge |
| visio/pages/page2.xml / 145 | 提交已确认的任务快照 | State Reducer + Checkpoint |
| visio/pages/page2.xml / 150 | 总控调度专业计算 Agent | Router / Conditional Edge |
| visio/pages/page2.xml / 155 | 校核参数与模型适用条件 | Validator / Deterministic Function |
| visio/pages/page2.xml / 160 | 输入校核通过？ | Router / Conditional Edge |
| visio/pages/page2.xml / 166 | 调用传输链路损耗模型 | Tool / Deterministic Function |
| visio/pages/page2.xml / 171 | 接收并提交结构化计算结果 | State Reducer + Result Validator |
| visio/pages/page2.xml / 176 | 总控调度验证与解释 Agent | Router / Conditional Edge |
| visio/pages/page2.xml / 181 | 程序执行数值合理性校验 | Validator |
| visio/pages/page2.xml / 186 | 数值校验通过？ | Router / Conditional Edge |
| visio/pages/page2.xml / 192 | RAG 检索解释与验证依据 | Tool / Service |
| visio/pages/page2.xml / 197 | 调用 LLM 生成解释与建议 | Agent（验证与解释） |
| visio/pages/page2.xml / 202 | 一致性审查通过？ | Validator + Conditional Edge |
| visio/pages/page2.xml / 206 | 发布结果与证据报告 | 发布Gate / LangGraph Node |
| visio/pages/page2.xml / 211 | 用户查看 / 保存 JSON | UI / Export Service |
| visio/pages/page2.xml / 215 | 向用户补问或修正参数 | Human-in-the-loop Gate + revision Node |
| visio/pages/page2.xml / 220 | 总控报告模型或专业依据缺口 | Failure Node |
| visio/pages/page2.xml / 227 | 总控分类处理异常 | Router + budget Validator |

## 可执行计划候选

先冻结Scope/Contract/验收，再包装现有RAG/Calculation/Validation，后实现state/router/checkpoint单一ownership；用stub先覆盖正常、缺参、工具失败、参数改变四路，再接真实四角色和UI。旧API保持兼容，新确认路径独立测试。候选任务与验收见evidence/aud01_tasks.json。所有候选状态为DRAFT，须主Agent映射正式Task ID；本轮停H0。

## 角色命名和职责冲突

当前docs/requirements.md:88-95以“需求与知识 Agent / 计算规划 Agent”为两个专业角色，并规定非Agent抽取Worker和确定性执行子图；VSDX page1 Shape44/49与v3使用“需求与规划 Agent / 专业计算 Agent”。双方都是1+3，但规划职责在不同角色，不能只作同义替换。H0需冻结角色到功能/输入输出/工具权限的映射，并将旧名称列别名或明确弃用；未获确认不修改需求文档/原图。

LocalSelector已有strict JSON输出约束（model.py:25），但它只约束公式选择/目标/条件，不能视作任务级GraphState或四角色Contract已实现。
