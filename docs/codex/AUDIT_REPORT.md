# 项目接管审计与H0交付总报告

日期：2026-09-17。审计执行：Astra low 两个专业子 Agent；独立测试：Luna medium；Main 整合与合同设计；非原作者 Astra reviewer；GitHub 由 Luna low 单独负责。

结论：这是已有可复用RAG与确定性计算底座的项目，尚未完成任务级确认、持久状态和1+3业务工作流。本轮保留业务代码及15项既有变更，交付审计和施工计划，停 HUMAN_GATE_0。

## A. Repository Baseline

详见 REPOSITORY_BASELINE.md。当前 HEAD 7342866450b08dafca10278bf98812f9f0fac137、分支codex/p1-applicability；123 Git tracked项，完整元数据库存27230项（包含依赖/模型/git，捕获时快照）。真实入口 launch.py / app.py → Engine.query；旧UI和API存在。P1适用性能力部分位于旧未提交工作树，不能归为本轮实现，也不能假设远端拥有它。

## B. WBS → Code Mapping

详见 WBS_STATUS.md / evidence/wbs_rows.json：38项逐ID代码与文档映射，已保留源行、任务和成果。Sheet1 B4:I45；不把1.0等编号误认为纯标题。没有任何条目因本次审计而直接标ACCEPTED。
已实现待新验收：检索流程、FSPL、接收电平/余量、旧输入UI；大量WBS部分完成；LangGraph任务状态等未开始。重复风险：3.2预算与3.3输出、2.4检索与4.5接入应复用。每项后续工程任务映射见WBS_TASK_MAPPING.md。

## C. RAG / Calculation Audit

详见 RAG_CALCULATION_AUDIT.md。实际7卡、8数值例符合声明容差；现有检索是词项+BGE+RRF，卡级metadata索引，非任意文档分块。parser/单位、AST白名单、依赖计算、适用性、引用和本地API均有可复用实现。
优先风险：手工值覆盖文本丢原来源、同任务显式与派生损耗未对账、裸core wrapper会漏适用性门。当前散射/缺损耗拒绝证据存在，不能泛化为“所有错误均成功”或“算术全错”。

## D. Multi-Agent / Workflow Gap

详见 WORKFLOW_GAP_ANALYSIS.md：VSDX两页所有Shape/Connect证据已保存、43块已分类，八项一致性问题有答复。无真正运行的LangGraph、GraphState、确认快照、checkpoint、revision/失效/trace；已有单公式selector JSON Schema。
1+3数量可保留；原requirements与VSDX/v3的两个专业角色职责分配不同，需H0映射。确定性计算/Validator/Router/reducer/检查点不是新增业务Agent。GitHub/审计等Codex Subagent不属于项目业务角色。

## E. Architecture Risks

RISK_REGISTER.md 列20项风险、证据、owner/任务及解除条件。最高优先为可复现基线、职责/范围、确认与版本、权限提交、适用性全链，先于提示词扩展和UI美化。

## F. 保留 / 修改 / 新增

MASTER_IMPLEMENTATION_PLAN.md 说明最小增量范围：保留formula_rag与唯一索引；提取确定性调用路径、完善追溯、增量wrapper；新增planning状态/工作流/确认及角色协议；不重写RAG，不改原图，不新增业务Agent。

## G. Contract v1

CONTRACTS.md 为1.0.0-draft.1，尚未冻结。包含GraphState、Parameter/ConfirmedSnapshot、Evidence/KnowledgeSnapshot、计划/计算请求结果、校验/解释/报告、Orchestrator建议、Service、提交权限、revision失效、retry、持久恢复、trace、API v1兼容草案。
类型注解不能替代运行时验证；reducer不能替代授权；hash不能替代可信来源；core.evaluate不能替代完整科学适用性门。

## H–J. Backlog / 编排 / Ownership

TASK_BACKLOG.yaml 含44条任务：9条本轮控制任务/门、35条后续工程任务。后续任务完整覆盖38个WBS编号；全部BLOCKED_HUMAN_GATE_0，有具体路径、输入输出、验收、测试和依赖。
AGENT_ASSIGNMENTS.md 规定Main公共Contract权限、各角色模型强度、Task Packet/Handoff、最多3个活跃Subagent、互斥锁和单一publisher。高风险状态逻辑串行，服务及角色在依赖和文件不冲突时并行。Reviewer不得审自己实现的功能。

## K. Test / Review / Retry / Escalation

TEST_BASELINE.md及原日志：101/101 unittest，30 Python与33 JSON静态解析、JS语法、BGE probe通过。Qwen端口未监听；真实LLM/完整RAG/浏览器/独立专业来源未验证；旧reports不是本轮结果。
MASTER_IMPLEMENTATION_PLAN规定实现两轮局部修复、分层升级；运行时retry另有持久预算。Reviewer和Tester独立检查、Main验收后才能更新ACCEPTED。

## L. 后续自动施工顺序

H0批准 → 接纳可复现基线与范围/职责 → Contract冻结 → 类型/资产/依赖 → 现有服务wrapper → state/checkpoint/确认/router/失效 → 四路stub → 业务角色 → API/UI/预算 → 真模型与科学验证/公平评测 → 文档分块增量及38项收尾。
普通批准任务可连续执行，只有明确重大升级条件停人；当前没有建立常驻后台scheduler。

## M. 持久工程控制

PROJECT_CONTEXT、ARCHITECTURE_DECISIONS、WBS_STATUS、TASK_BACKLOG、CONTRACTS、AGENT_ASSIGNMENTS、IMPLEMENTATION_LOG、TEST_BASELINE、NEXT_ACTION，以及总计划、风险表、独立review、原证据、只读控制校验器均在docs/codex。
控制校验器验证YAML字段、ID/依赖DAG、H0阻塞、38项覆盖、路径ownership和文档引用。它验证控制结构，不替代业务测试或科学审查。

## N. 立即下一步

本轮停止HUMAN_GATE_0。事实review为附带限制的PARTIAL，文字P2已复核修正；合同五项问题已改，Reviewer二轮消息确认主要修正，仅剩T007文字同步且Main已修。但Reviewer和publisher因账户额度中止，最终review尚未写回、GitHub未创建/上传、本地发布目录未建立。恢复后先按REVIEW_RESOLUTION.md完成有界最终复核，再由用户批准H0；不开始T001以后实现。

## 证据等级

代码/运行验证：本地入口、7卡、定向probe、101测试与静态/BGE检查。
文档/设计判断：原图角色、Demo边界、所有新Contract与35任务设计。
仍需确认或未来验证：H0范围与职责映射、真实模型链路、科学标准、原图视觉争议、新目标创建/上传及后续实现验收。
