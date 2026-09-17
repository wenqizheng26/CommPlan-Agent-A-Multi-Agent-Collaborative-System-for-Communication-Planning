# WBS 逐项状态审计

AUD-01，2026-09-17。只读证据；停在 HUMAN_GATE_0。状态不等于老师验收。无条目标 ACCEPTED；IMPLEMENTED 仅指旧功能代码存在。

来源：`C:/Users/nntm/Desktop/天大信号/WBS分解-智能体.xlsx`，Sheet1，B4:I45。38项：6+8+10+9+5；另有第1行说明和第3行表头，共40非空行。任务名称与交付物原文保留于下表，所有非空单元格（含负责人备注/工日）见 evidence/wbs_rows.json。原始数字ID有二进制浮点尾数，raw_id保留，映射ID按一位小数；原表1/2/3/4/5作为1.0等具体任务，不误作仅标题。

| ID / 原行 | 二级任务原文 | 主要成果原文 | 状态 | 完成判断 | 代码/设计证据 | 缺口/重复/风险 |
|---|---|---|---|---|---|---|
| 1.0 / 4 | 首月研究目标与实现边界定义 | 首月目标、功能边界、实现范围 | DESIGNED | 部分 | docs/requirements.md:23; VSDX page1 Shape99/109 | 总体候选比较与窄损耗Demo边界待H0明确 |
| 1.1 / 5 | 通信链路筹划业务流程梳理 | 通信筹划业务流程图 | DESIGNED | 部分 | docs/system-flow.md:3; VSDX page2 | 业务图存在；未实现确认/恢复/审查闭环 |
| 1.2 / 6 | 系统总体技术架构设计 | 系统总体架构图 | DESIGNED | 部分 | docs/requirements.md:86; VSDX page1 Shape2 | 架构设计存在；LangGraph未落地 |
| 1.3 / 7 | 多智能体角色及协同关系设计 | Agent角色与协同关系说明 | DESIGNED | 部分 | VSDX page1 Shape39/44/49/54 | 保留1+3；图内校验/计算/状态拆程序组件 |
| 1.4 / 8 | 数据结构及模块接口设计 | 参数字段、接口及数据结构定义 | DESIGNED | 部分 | docs/requirements.md:186; app.py:18 | 已有字典API；无任务级Schema/提交权限 |
| 1.5 / 9 | 测试指标及阶段验收目标定义 | 测试指标及验收标准 | DESIGNED | 部分 | docs/requirements.md:238; tests/; scripts/evaluate.py | 有测试与验收案例；WBS验收口径未冻结 |
| 2.0 / 11 | 通信链路筹划知识体系梳理 | 通信筹划知识体系及分类 | IN_PROGRESS | 部分 | knowledge/formulas.json; formula_rag/catalog.py:75 | 7公式非完整通信筹划知识体系 |
| 2.1 / 12 | 专业资料与知识条目整理 | 知识文档及知识条目 | IN_PROGRESS | 部分 | formula_rag/catalog.py:56; knowledge/formulas.json | 公式来源已有；设备手册/规则覆盖未证明 |
| 2.2 / 13 | 通信筹划参数字典与规则整理 | 参数字典、参数说明及规则库 | IN_PROGRESS | 部分 | formula_rag/parsing.py:39; docs/requirements.md:186 | 单公式字典已有；任务来源/确认/冲突状态缺失 |
| 2.3 / 14 | 文档分块、向量化与索引构建 | RAG向量知识库 | IN_PROGRESS | 部分 | formula_rag/retrieval.py:15,34,70 | 卡级元数据索引已实现；通用资料分块未实现，不另建第二RAG |
| 2.4 / 15 | RAG检索流程实现 | 知识检索接口 | IMPLEMENTED | 已实现待验收 | formula_rag/retrieval.py:89 | 混合检索存在；独立Service契约/场景验收待补 |
| 2.5 / 16 | 检索结果与任务参数关联 | RAG与Agent接口 | IN_PROGRESS | 部分 | formula_rag/pipeline.py:80,192 | calc有version/sources；candidate无version，无EvidenceRef参数图 |
| 2.6 / 17 | RAG基础测试与优化 | 检索测试结果 | IN_PROGRESS | 部分 | scripts/evaluate.py; tests/test_pipeline.py | 历史评测不等于WBS引用/失败模式/真实运行验收 |
| 2.7 / 18 | 知识库及接口整理 | 知识库说明及接口文档 | IN_PROGRESS | 部分 | README.md; formula_rag/catalog.py:17 | 已有说明与元数据校验；统一接口/快照需补 |
| 3.0 / 20 | 单链路计算输入参数定义 | 计算输入参数表 | IN_PROGRESS | 部分 | formula_rag/parsing.py:76; formula_rag/pipeline.py:25 | 无版本化CalculationRequest |
| 3.1 / 21 | 自由空间传播损耗模型实现 | 传播损耗计算模块 | IMPLEMENTED | 已实现待验收 | formula_rag/core.py:94; formula_rag/applicability.py:54 | 仅自由空间；异常近场筛查不是完整远场证明；科学版本仍待审核 |
| 3.2 / 22 | 链路预算模型实现 | 链路预算模型 | IN_PROGRESS | 部分/重叠风险 | formula_rag/pipeline.py:14,100 | 递归依赖非统一预算契约；显式与派生值不对账；复用3.3 |
| 3.3 / 23 | 接收电平与链路余量计算 | 接收功率及链路余量计算模块 | IMPLEMENTED | 已实现待验收 | knowledge/formulas.json; formula_rag/pipeline.py:100 | 接收电平/余量存在；作为3.2输出，勿另建算法 |
| 3.4 / 24 | 附加损耗与典型参数处理 | 附加损耗及缺省参数处理规则 | IN_PROGRESS | 部分/风险 | formula_rag/parsing.py:76; formula_rag/pipeline.py:58 | 损耗字段已有；典型/缺省不应静默变确认值 |
| 3.5 / 25 | 专业计算函数接口封装 | Agent可调用计算接口 | IN_PROGRESS | 部分 | formula_rag/core.py:94; formula_rag/pipeline.py:25 | core函数不是完整CalculationService；必须含scope/result gates |
| 3.6 / 26 | 参数单位及合法性检查 | 参数检查模块 | IN_PROGRESS | 部分/风险 | formula_rag/parsing.py:39,168; formula_rag/core.py:94 | 单位检查存在；直接core绕过scope，覆盖文本无冲突历史 |
| 3.7 / 27 | 专业计算模型独立验证 | 模型测试案例及结果 | IN_PROGRESS | 部分 | tests/test_core.py; tests/test_scientific_scope.py | 卡样例与程序测试存在；独立科学验证/边界未完全证明 |
| 3.8 / 28 | 复杂传播模型扩展接口预留 | 模型扩展接口 | DESIGNED | 未完成 | VSDX page1 Shape109; formula_rag/importing.py:20 | 公式导入不等于复杂传播插件接口；首期只设计扩展边界 |
| 3.9 / 29 | 专业模型说明及接口整理 | 专业模型说明文档 | IN_PROGRESS | 部分 | formula_rag/presentation.py:72; README.md | 模型展示/说明已有；受控接口文档需统一 |
| 4.0 / 31 | 多智能体工作流框架搭建 | LangGraph工作流骨架 | NOT_STARTED | 未完成 | requirements.lock.txt; formula_rag/pipeline.py:18 | 无LangGraph依赖/StateGraph调用 |
| 4.1 / 32 | 总控智能体实现 | 任务识别、分解及调度能力 | DESIGNED | 未完成 | VSDX page1 Shape39; formula_rag/model.py:8 | LocalSelector不是Orchestrator |
| 4.2 / 33 | 需求解析与参数提取实现 | 自然语言参数提取能力 | IN_PROGRESS | 部分 | formula_rag/parsing.py:76; formula_rag/interpretation.py:12 | 提取/依据核验已有；Planning Agent/状态提交未做 |
| 4.3 / 34 | 缺失参数识别与用户确认 | 缺参判断及参数补充流程 | IN_PROGRESS | 部分 | formula_rag/pipeline.py:110; web/assets/app.js:16 | 缺项追问已有；计算前确认快照/interrupt-resume缺失 |
| 4.4 / 35 | 专业计算智能体实现 | 专业计算Agent | DESIGNED | 未完成 | VSDX page1 Shape49; formula_rag/core.py:94 | 确定性内核可复用；受控计算Agent尚无 |
| 4.5 / 36 | RAG知识检索能力接入 | RAG工具调用能力 | IN_PROGRESS | 部分 | formula_rag/pipeline.py:34; formula_rag/model.py:15 | 旧引擎已接RAG；新工作流wrapper与EvidenceRef缺失 |
| 4.6 / 37 | 专业工具调用与受控路由 | 工具路由及调用机制 | IN_PROGRESS | 部分 | formula_rag/core.py:28; formula_rag/pipeline.py:86 | 白名单与确定性分支已有；Workflow router/budget未做 |
| 4.7 / 38 | 任务状态管理机制 | 任务共享状态 | NOT_STARTED | 未完成 | app.py:21,97; docs/requirements.md:203 | 内存64结果缓存非GraphState/checkpoint/revision |
| 4.8 / 39 | 结果校验与解释机制 | 结果验证与解释输出 | IN_PROGRESS | 部分 | formula_rag/applicability.py:89; formula_rag/pipeline.py:142 | 硬校验基础；验证解释Agent/发布门/一致性审查缺失 |
| 5.0 / 41 | 原型系统界面总体设计 | 原型界面设计 | IN_PROGRESS | 部分 | web/index.html; docs/mockups/2026-09-14-parse-review-layout.html | 已有旧UI与mockup；不能把mockup当运行UI |
| 5.1 / 42 | 用户任务输入界面实现 | 任务输入界面 | IMPLEMENTED | 已实现待验收 | web/assets/app.js:16; app.py:93 | 自然语言输入已接/api/query；新任务协议未接 |
| 5.2 / 43 | 参数识别与用户确认界面 | 参数确认界面 | IN_PROGRESS | 部分 | web/assets/app.js:16,17 | 手填纠错与事后识别展示；没有计算前独立确认 |
| 5.3 / 44 | 多智能体执行过程展示 | Agent执行流程展示 | NOT_STARTED | 未完成 | web/assets/app.js:17 | 只展示耗时/检索模式；无Agent事件流 |
| 5.4 / 45 | RAG检索结果展示 | 知识检索展示界面 | IN_PROGRESS | 部分 | web/assets/app.js:6,11,17 | 候选/公式来源版本可查看；无EvidenceRef及参数证据联动 |

## 范围冲突与后续映射

WBS 3.2/3.3包含链路预算、接收功率与余量。VSDX page1 Shape99限定单链路损耗Demo，Shape109将链路预算列为Demo外扩展；这应解释为阶段划分，不能删除WBS任务。docs/requirements.md:23,49要求同任务有限候选比较，属于比窄Demo更大的已有设计范围，需在H0登记阶段归属。WBS未写候选位置或成本指标，不从历史描述补造已冻结范围。

3.2与3.3复用同一计算链；2.4与4.5分别是检索能力与接入工作流，不重复建设索引；1.3与1.4迭代冻结，4.7是基础设施而非Agent。3.4成果原文“附加损耗及缺省参数处理规则”与禁止静默默认原则存在解释风险：默认只能建议，正式执行需确认或登记常量依据。

本表逐ID已穷尽。每个ID对应的正式施工Task ID见[WBS_TASK_MAPPING.md](WBS_TASK_MAPPING.md)，由主Agent在TASK_BACKLOG.yaml统一维护；evidence/aud01_tasks.json仅为早期审计候选，不另建任务；不能把本地旧改动归为本轮施工成果。

## 独立审计汇合

AUD-03当前工作树基线：101项unittest全通过（0失败/跳过），30个Python与33个JSON静态解析通过，JS语法通过；BGE只读向量probe通过。Qwen端口未监听，完整真实RAG/LLM未验证。具体命令及日志见TEST_BASELINE.md。该结果支持现有程序回归基线，不把上述38项升级为ACCEPTED。AUD-02的8个公式样例符合卡声明容差；详细科学与检索限制见RAG_CALCULATION_AUDIT.md。
