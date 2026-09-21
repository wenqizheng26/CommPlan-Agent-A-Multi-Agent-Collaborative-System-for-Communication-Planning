# 架构决策记录

HUMAN_GATE_0 已批准，记录见 evidence/h0_approval.json。以下决策为已批准目标，是否实现以 Task Backlog 与测试证据为准。

| ID | 状态 | 决策与依据 | 后果 / 对应任务 |
|---|---|---|---|
| ADR-01 | 既有约束 | formula_rag 是唯一检索与公式底座；保留当前 Engine/AST/目录/单位/适用性能力 | 新 planning 包只包装和编排，不保存第二套公式或索引；T008–T013 |
| ADR-02 | accepted | 先交付自由空间单链路损耗四路闭环，再交付预算/Pr/margin 与 WBS 其他范围 | VSDX Demo 外内容仍保留在 Backlog，不能删除 WBS 3.2/3.3；T002/T024 |
| ADR-03 | accepted | 保持 1+3 业务职责，不以功能框数量增加 Agent | Orchestrator 提建议，Router 作受控执行决定；规划负责计划，专业计算角色只受控调用；T002/T020–T023 |
| ADR-04 | accepted | 将旧“需求与知识”映射至“需求与规划”的需求/证据部分，将旧“计算规划”的计划职责迁入规划角色，其执行职责对应“专业计算” | 职责迁移已由 H0 批准；docs/requirements.md R2 保留迁移表，不改原图 |
| ADR-05 | accepted | 新增 planning/contracts.py 作为可执行公共类型与验证入口，docs/codex/CONTRACTS.md 作为语义事实源 | Main 单一 owner，类型实现和文档必须同版本；现有公式选择 schema 保留；T003/T005 |
| ADR-06 | accepted | LangGraph 仅承担 WBS4.0 要求的受控状态图、暂停恢复；不承担数值计算 | H0 后隔离环境验证并锁定兼容版本；首版 SQLite 本地持久检查点，无新增服务器；T006/T014–T019 |
| ADR-07 | accepted | 每任务串行可信提交，reducer 只合并已校验更新，不能把 reducer 当授权层 | 先校验执行身份/字段权限/revision，再 CAS 提交与检查点；T014/T015 |
| ADR-08 | accepted | 首版关键输入变化保守失效全部下游，只有依赖哈希证明相同才复用 | 单调 revision；拒绝旧确认和晚到结果；精细重算可后续优化；T018 |
| ADR-09 | accepted | CalculationService 组合准入、完整 scope、确定性计算、result checks；不可裸包装 core.evaluate | 保留算法，必要时只提取 pipeline 的确定性调用链，保持旧 query 语义；T010/T012 |
| ADR-10 | accepted | 新任务 API 使用 /api/tasks，旧 /api/query 与 /api/save-result 保持兼容 | 新 UI 必须计算前显式确认；旧界面明确旧模式边界；T025–T028 |
| ADR-11 | accepted | 开发 max_active_subagents=3，公共接口先冻结，互不重叠文件才能并行；单一 publisher | 审计/Astra low，机械任务/Luna；复杂状态语义失败后 Main 升级 medium/high；AGENT_ASSIGNMENTS |
| ADR-12 | accepted | 三种评测模式共用工具/知识/数据/预算，分别报告程序正确性、引用正确性、任务达成、成本和失败 | 不以 7 卡 top8 contains-target 或 mock 测试证明模型效果；T029–T032 |

## H0 决策包

批准对象为：首个 Demo 与 WBS 后续范围的阶段分配；ADR-03/04 的四角色职责映射；新契约/接口草案；LangGraph 最小持久运行时的隔离验证；已定义 Backlog 的普通任务自动推进规则。保留全部旧改动，由 T001 记录其归属/验收后再决定基线提交，不把本轮文档上传当成业务提交授权。

H0 后 Main 可冻结已批准的具体契约；重大 breaking change、改变研究范围/业务角色、改原图、替换 RAG、专业标准争议或无解释的大面积回归触发单独升级。普通局部修复按两次预算自动执行。

## T002 范围落实

R2 已记录四角色职责迁移、首个四路径 Demo 与 T024 预算边界、当前任务和历史研究目标的区别。原图未改。完整 WBS 状态仍以实际验收为准，H0 不构成业务完成证明。
