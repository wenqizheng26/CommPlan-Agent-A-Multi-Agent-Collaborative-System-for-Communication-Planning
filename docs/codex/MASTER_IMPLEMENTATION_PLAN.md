# 总体施工计划

目标：保留现有 formula_rag 与旧接口，先证明单链路损耗工作流的确认、计算、校验和恢复闭环，再完成 WBS 后续预算、资料治理与评测。
状态：HUMAN_GATE_0 待批准；35 个后续工程任务全部阻塞，完整参数见 TASK_BACKLOG.yaml。当前只有审计与控制文件已产出，没有已运行的后台施工调度程序。
执行方式：用户已指定 Main/Subagent 组织；Main 按下列状态机派发，子 Agent 接 Task Packet。不再询问选择工作模式，不虚构当前未安装的技能。

## 建议保留、修改、新增

- 保留：formula_rag 内 AST/公式/参数单位/适用性/知识目录/混合检索/唯一索引；旧 query/save-result；现有101项测试；七公式及版本；原 VSDX/WBS。
- 最小修改：T010 提取 pipeline 结构化确定性路径；T011 完善索引身份；T029 评测预期与指标；T025 新增任务 API；T026–T028 新模式 UI。改变公式或旧语义必须单独审查，不能归入 wrapper 的附带修改。
- 新增：planning 包内共享 Contract、服务包装、授权提交、状态/检查点/确认/路由/trace/失效、四角色输入输出、独立测试、资料来源及评测协议。
- 首个 Demo 暂不实现：散射/复杂传播模型、海域面积覆盖和大规模候选优化。WBS 3.8 只预留注册/能力边界。更大研究设计保留记录，延期内容不能计入验收。

## 阶段、输入输出及验收

| Phase | Task | WBS | 输入/输出 | 阶段验收与后续 |
|---|---|---|---|---|
| P0 本轮 | AUD-01/02/03、PLN、REV、PUB、H0 | 全38项映射 | 原规范/WBS/VSDX/工作树→审计、Contract草案、控制文件 | 独立review、控制文件校验后停H0；上传失败单列 |
| P1 基线与合同 | T001–T004 | 1.0–1.5、4.7 | 审计→P1可复现基线、范围映射、冻结合同、失败矩阵 | 旧改动归属清晰、Contract独立审查；进P2 |
| P2 类型与资产治理 | T005–T008 | 1.4、2.0–2.2、2.7、3.0/3.4、4.0/4.7 | 合同→严格Schema、锁依赖、来源清单、参数字典 | JSON/非法值、依赖兼容、禁止隐式确认；进P3 |
| P3 现有服务包装 | T009–T013 | 2.3–2.5/2.7、3.1–3.6、4.2/4.4–4.6/4.8 | 旧parser/retriever/pipeline→带来源/版本服务 | scope全链、冲突拒绝、8样例/旧回归不丢；与P4基础可交错 |
| P4 工作流基础 | T014–T019 | 1.4、4.0/4.1/4.3/4.6–4.8、5.2 | Schema/服务→state/commit/checkpoint/确认/router/失效/stub图 | 正常/缺参/失败/修改失效四路、跨进程恢复、晚到/重复消息；进P5 |
| P5 角色接入 | T020–T023 | 4.1/4.2/4.4–4.6/4.8 | stub及协议→四角色调用边界/发布门 | LLM不产数值不越权；stub与真实模型验证分列；进P6 |
| P6 预算与UI | T024–T028 | 3.2/3.3/3.8、4.3/4.7、5.0–5.4 | 服务/任务API→预算、扩展注册、确认页面与证据链 | 无重复算式、旧API兼容、Chrome五路演练；进P7 |
| P7 独立评测 | T029–T032 | 1.5、2.1/2.4/2.6、3.1/3.6/3.7、4.0/4.5/4.8 | fixtures/真实本地模型→检索/科学验证/三模式对照 | 标准可追溯、真实RAG有证据、公平预算与失败指标；进P8 |
| P8 完整WBS收尾 | T033–T035 | 2.0/2.1/2.3/2.7、3.9、5.4、1.5/4.7 | 资产及评测→资料chunk增量接入、统一文档/逐项验收/恢复演练 | 每项按证据验收，缺资料/外部限制继续BLOCKED |

阶段编号表达交付关系，实际依赖以 YAML 为准。P2 T006/T007 可与不依赖它们的工作交错；P4 T014 可在 P3 部分 wrapper 期间开工；P7 T029 无需等待全部 UI，而 T032 需要真实链路/UI/独立模型证据。

## 后续工程任务索引

- T001：固化当前P1工作树基线；依赖 H0；owner main_agent。
- T002：冻结范围与四角色职责映射；依赖 T001；owner main_agent。
- T003：独立审查并冻结Contract v1；依赖 T002；owner main_agent。
- T004：冻结验收案例与失败矩阵；依赖 T003；owner test_runner。
- T005：实现严格公共Schema与单位参数契约；依赖 T003、T004；owner main_agent。
- T006：隔离验证并锁定最小LangGraph依赖；依赖 T003、T001；owner main_agent。
- T007：整理知识分类与来源身份清单；依赖 T003；owner documentation_maintainer。
- T008：建立任务参数字典与典型值规则；依赖 T005、T007；owner calculation_service_specialist。
- T009：封装保留来源与冲突的参数解析；依赖 T005、T008；owner rag_service_specialist。
- T010：最小提取完整确定性计算路径；依赖 T005、T001；owner calculation_service_specialist。
- T011：包装唯一RAG与Evidence快照；依赖 T005、T007；owner rag_service_specialist。
- T012：实现受控CalculationService；依赖 T010、T009、T005；owner calculation_service_specialist。
- T013：实现输入/结果/发布三级硬Validator；依赖 T005、T009、T011；owner calculation_service_specialist。
- T014：实现GraphState与可信提交层；依赖 T005；owner workflow_implementer。
- T015：持久检查点与跨进程恢复；依赖 T006、T014；owner workflow_implementer。
- T016：计算前确认与interrupt-resume；依赖 T015、T009；owner workflow_implementer。
- T017：确定性Router与有限Retry及Trace；依赖 T014、T015、T013；owner workflow_implementer。
- T018：Revision失效与晚到结果拒绝；依赖 T014、T017；owner workflow_implementer。
- T019：图骨架四路径Stub端到端验收；依赖 T012、T013、T016、T017、T018、T004；owner workflow_implementer。
- T020：接入需求与规划角色；依赖 T019、T011；owner agent_logic_implementer。
- T021：接入专业计算角色的受控调用；依赖 T019、T012；owner agent_logic_implementer。
- T022：接入总控建议且保持确定性路由；依赖 T019；owner agent_logic_implementer。
- T023：验证解释与正式发布门；依赖 T019、T013、T011；owner agent_logic_implementer。
- T024：统一链路预算输出与复杂模型扩展契约；依赖 T012、T013、T019；owner calculation_service_specialist。
- T025：新增任务API并保持旧接口；依赖 T020、T021、T022、T023；owner main_agent。
- T026：定义兼容新旧模式的页面结构；依赖 T025；owner ui_integrator。
- T027：实现版本化确认与修改交互；依赖 T026；owner ui_integrator。
- T028：执行过程证据展示与真实浏览器验收；依赖 T027；owner ui_integrator。
- T029：修正检索评测与隔离输出；依赖 T011、T008；owner test_runner。
- T030：受控真实模型与完整RAG Smoke；依赖 T029、T020、T025；owner test_runner。
- T031：独立科学来源与计算边界验证；依赖 T007、T012、T024；owner scientific_reviewer。
- T032：三运行模式对照评测；依赖 T024、T028、T030、T031；owner test_runner。
- T033：完成受控资料分块接入唯一索引；依赖 T011、T007、T029；owner rag_service_specialist。
- T034：统一知识/模型/API说明与WBS验收；依赖 T032、T033；owner documentation_maintainer。
- T035：最终回归与项目恢复演练；依赖 T034；owner test_runner。

每项 YAML 有 Objective、Dependencies、Owner/Subagent Type、Allowed/Forbidden Files、Inputs、Outputs、Acceptance Criteria、Test Command、Status。新增文件和测试命令明确标为 planned；不能在文件未创建时宣称通过。

## 关键路径和可并行批次

关键路径：H0 → T001 → T002 → T003 → T004 → T005 → T014 → T015 → T016/T017 → T018 → T019 → T020–T023 → T025 → T026 → T027 → T028 → T032 → T034 → T035。
旁路：T006 是 checkpoint 前置；T007/08/09 与 T010/11/12/13 是服务门；T024 预算、T030 真实模型、T031 科学验证、T033 资料接入为总体验收前置。

最多 3 子 Agent，Main 自己的文件工作也计入冲突检查：
1. T001–T003 串行；T004 的验收设计由非作者审查。
2. T005、T006、T007 文件独立，依赖满足可并行；T008 等 T005/T007。
3. T009 参数来源、T010 计算路径、T011 RAG 包装可并行，前提各自依赖均已接受。
4. T012 计算、T013 校验、T014 状态可并行；state/commit 公共字段只有 Main 批准的单 owner。
5. T015 → T016 → T017 → T018 → T019 在 workflow_core 锁下串行，不为并发拆散状态语义。
6. T020/21/22 先并行，T023 占释放名额；Reviewer/Tester 同样占槽位，不能再额外叠加。
7. T024 预算可与 T025 API 并行；T026→T027→T028 因 web_ui 单锁串行。
8. T029 评测和 T031 科学审核可先进行；T030/T032 持有 integration_runtime，真实服务测试串行。
9. T033 资料接入后 T034→T035 收尾；每阶段通过后更新控制文件并阶段发布。

## Main 驱动的调度状态机

~~~text
AUDIT -> PLAN -> CONTRACT_DRAFT -> CONTRACT_REVIEW -> HUMAN_GATE_0
 -> CONTRACT_FREEZE -> TASK_SCHEDULING -> IMPLEMENT -> UNIT_TEST
 -> INDEPENDENT_REVIEW -> INTEGRATION_TEST -> ACCEPT
 -> UPDATE_BACKLOG/WBS/LOG -> NEXT_READY_TASK
测试/Review失败 -> FIX -> RETEST -> 超预算则ESCALATE/REPLAN
~~~

H0 前只运行审计/计划/文档发布。H0 后 Main 每轮：
- 验证批准记录、基线、任务状态与锁；T001–T003属于冻结前置，仅核对H0批准草案及其hash，requires_frozen_contract=false；T004及以后必须验证已冻结Contract版本/hash；
- 选依赖全 ACCEPTED 的任务，从 BLOCKED 转 READY；未展示完 H0 方案前的“继续”仅继续本轮准备；
- 发完整 packet，记录 assigned_agent/model/reasoning/start 和 baseline；
- 实现者 scoped unit pass 后交接；非实现者 Reviewer 审查；Tester 在集成基线上跑必要回归；
- Main 验收后更新 task/WBS/log，释放锁并自动选下一任务。

仅 Main 修改 Backlog 状态。Agent PASS 不等于 ACCEPTED；任何 READY 任务缺输入、测试定义或 ownership，退回 PLAN。

## Review、Test、Retry、Escalation

测试分层：严格Contract→参数/单位→单工具/范围→Service→状态/权限→四路Workflow→重启/重试/失效→旧回归→真实模型/RAG→浏览器→公平对照。记录 base commit、contract hash、命令、exit code、日志；mock 不能替代真实，样例不能替代标准复核。

实现重试预算2次（初次失败后最多2轮 fix/retest），与运行时节点 retry 是不同预算。同根因重复失败先分类：
- Level0 局部实现/测试：原 owner 预算内修复。
- Level1 跨模块：Main 判断责任边界并重排。
- Level2 Contract：停受影响任务，CONTRACT_CHANGE_REQUEST→影响分析/版本更新/独立review/重新冻结。
- Level3 范围/业务角色/原图/RAG替换/重大依赖/广泛breaking/标准冲突/无法解释大回归：列 Trigger、Evidence、Impact、Options、推荐下一步及仍可继续部分，向用户升级。

Phase gate 通过后默认继续，不逐文件问人。GitHub 失败标 BLOCKED_EXTERNAL 并保留本地 reviewed commits。禁止 force、静默改 remote、误提交旧业务修改。用户本轮已改为要求新建仓库，不能再发布旧 origin。

## 完成条件与自动化边界

本轮交付持久控制规范与只读校验器，Main 可据此连续调度。没有安装常驻程序、周期 automation 或后台运行服务。H0 后在活跃 Codex 任务中推进，定时唤醒需另行授权。

首阶段完成至少需要：可重建基线、冻结 Contract、服务 wrapper、严格 Schema、参数状态分离、确认恢复、有限 retry、revision 失效、trace、四路 stub；业务 LLM 接入在此之后。

项目验收仍需 WBS 逐项证据、真实运行、独立 review 与文档同步；当前101测试通过不替代未来验收。
