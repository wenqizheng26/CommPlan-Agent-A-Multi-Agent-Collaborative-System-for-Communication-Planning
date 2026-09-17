# 架构与工程风险清单

本轮未修业务实现。等级表示影响和阻塞关系，不代表已发生线上事故。主证据：RAG_CALCULATION_AUDIT / WORKFLOW_GAP_ANALYSIS / TEST_BASELINE。

| 风险 | 等级 | 真实证据与影响 | 拟处理/Owner | 解除条件 |
|---|---|---|---|---|
| R01 未提交基线 | HIGH | 15项旧改动含applicability模块未在HEAD；本地101测试不能证明GitHub检出同样通过 | T001/Main | 精确manifest、接受基线commit、对应回归 |
| R02 角色职责漂移 | HIGH | requirements需求与知识/计算规划，与VSDX/v3需求与规划/专业计算职责不同 | T002/Main/H0 | 明确映射批准，保持1+3且原图不改 |
| R03 Demo冒充总体范围 | HIGH | VSDX把预算列Demo外；WBS3.2/3.3仍要求预算 | T002/T024 | 阶段与38项逐个验收区分 |
| R04 手工覆盖丢来源 | HIGH | RC-01 parsing.py:168-174；200m→手填1km直接覆盖 | T009/参数owner | 两个来源都保留，冲突需resolution+revision |
| R05 显式/派生混用 | HIGH | RC-02 同请求FSPL91.48而Pr用显式100；无场景来源身份 | T012/T013/T024 | 同场景明确选择或拒绝；比较分calculation_id |
| R06 裸计算器被误包装 | HIGH | RC-03 core.evaluate缺pipeline范围/result gate | T010/T012 | wrapper全链测试，近场/散射/缺参不放行 |
| R07 先算后确认 | HIGH | app.js:16提交即query；无snapshot/interrupt | T016/T025/T027 | 确认前无正式计算；stale确认拒绝 |
| R08 状态越权与旧结果复用 | HIGH（设计风险） | GraphState/commit/revision/checkpoint尚无业务实现 | T014–T019 | 身份权限、CAS、幂等、跨重启、晚到与预算测试 |
| R09 缺省值误当已确认 | HIGH（设计风险） | WBS3.4成果“附加损耗及缺省参数处理规则”与禁止静默默认需解释 | T008/T009 | 参数来源/状态清晰；建议不能自动confirmed |
| R10 评测目标陈旧 | MEDIUM | RC-04 290K确认case与新gate不一致 | T029 | 修fixture，真实评测不通过时如实失败 |
| R11 检索指标无区分度 | MEDIUM | RC-05 7卡top8 contains-target近乎恒真 | T029/T032 | top1/top3/rank/拒识/引用分别测 |
| R12 引用和可信标签 | MEDIUM | candidates缺版本；UI对draft硬编码已核对；verified不证明标准来源真 | T007/T011/T028/T031 | Evidence快照、真实status展示、独立来源复核 |
| R13 embedding缓存身份不全 | MEDIUM | RC-09只hash权重未含tokenizer/config规则 | T011 | snapshot变更触发明确失效且旧接口兼容 |
| R14 真模型未运行 | MEDIUM/验收阻塞 | Qwen18081未监听；101单测主测deterministic/mock | T030 | 实际dense/LLM请求、模型hash与输出日志 |
| R15 LangGraph重入副作用 | HIGH（设计风险） | 新框架尚未锁定；resume可能重新执行节点前部 | T006/T015/T016 | 锁版、持久预算、幂等任务/确认/发布 |
| R16 XML审计非视觉审查 | LOW/限制 | VSDX文本/Connect全量提取但未视觉核对箭头 | T002 review | 对存在争议的连线人工核对；不伪造已验收 |
| R17 通用资料覆盖缺口 | MEDIUM | 7卡索引不是设备/规则/资料通用分块 | T007/T033 | 明确输入格式与来源manifest；唯一索引增量 |
| R18 GitHub目标与通道 | 外部阻塞 | 旧origin超时/connector404；用户要求新建目标；创建/发布结果见GITHUB_PUBLICATION | Luna publisher | 新目标真实存在、private可验证、上传SHA核验 |
| R19 过度多Agent | MEDIUM（设计风险） | WBS功能不能一项一Agent，图内大量校验/计算为确定性工作 | T002/T020–23 | 保留1+3；Service/Validator/Router独立边界 |
| R20 调度状态假完成 | HIGH（流程风险） | 文档/代码存在不等于运行或验收；上下文切换易丢基线 | 控制校验器/T035/Main | H0状态不可绕过，证据齐全后才ACCEPTED |

复核发现的报告本身错误在 REVIEW_REPORT 记录并先修文档；不把修报告等同于修生产风险。GitHub阻塞不会允许绕过H0，也不应取消本地已可完成的审计计划。
