# Codex 开发 Agent 编排与文件所有权

这是开发组织，不是项目运行时业务 Agent。模型选择是本轮操作策略，未做 Astra low 与 Sol high 的受控成本/质量基准比较。

## 本轮实际分工

| 开发角色 | 模型 / 推理 | 任务 | Ownership | 状态 |
|---|---|---|---|---|
| Main Tech Lead / Architect / Integrator | 当前主 Agent；关键架构推理 HIGH 级责任 | PLN-01，H0 汇总 | 本文件、PROJECT_CONTEXT、AUDIT_REPORT、ARCHITECTURE_DECISIONS、CONTRACTS、MASTER_IMPLEMENTATION_PLAN、TASK_BACKLOG、RISK_REGISTER、IMPLEMENTATION_LOG、NEXT_ACTION、REVIEW_RESOLUTION、控制文件校验器 | 文档落盘；H0停止 |
| repo_wbs_astra | gpt-6-astra / low | AUD-01 | REPOSITORY_BASELINE、WBS_STATUS、WORKFLOW_GAP_ANALYSIS；wbs_rows/repository_inventory/diagram_nodes/aud01_tasks JSON | 已交付 |
| rag_calc_astra | gpt-6-astra / low | AUD-02 | RAG_CALCULATION_AUDIT；rag_calculation_assets/aud02_tasks JSON | 已交付 |
| baseline_luna | gpt-5.6-luna / medium | AUD-03 | TEST_BASELINE；test_baseline JSON、test-*.log | 已交付 |
| independent_review_astra | gpt-6-astra / low；复杂问题升级 medium/high | REV-01 / 事实子包 | REVIEW_REPORT、review_checks JSON；只读其他文件 | PARTIAL范围审查已交付，P2修正已复核 |
| contract_review_astra | gpt-6-astra / low | REV-02 | CONTRACT_PLAN_REVIEW、contract_plan_review JSON；只读被审计划 | 最终记录被usage limit中止 |
| github_luna | gpt-5.6-luna / low | PUB-01 / PUB-02 | GITHUB_PUBLICATION、publication JSON；拟独立文档仓库的已批准 docs allowlist | 创建/上传受阻；usage limit中止 |
| repo_wbs_auditor | Sol / high（被用户指示替换） | 无最终产物 | 无 | 已中断，不再调度 |

最大同时运行：Main + 3 个 Subagent。上表为角色池，不意味着全部同时活跃。当前停止的 Agent 不占用实现任务 ownership。只有 github_luna 可以 git commit/push；不允许实现者私自发布。

最终交接例外：publisher与Contract reviewer因额度停止后，Main仅在PLN-01新列明的路径记录修正结果/发布事实，不改写独立Reviewer原始结论，不代替publisher进行Git操作。当前没有仍在后台运行的施工任务。

Astra 本次可调用最低档为 low，不存在 minimal 档；也通过 [OpenAI 官方模型页](https://developers.openai.com/api/docs/models/gpt-6-astra) 核实。OpenAI Docs 仅用于模型设置核验，不改变项目本地业务模型。

## H0 后动态调度

| 工作 | 默认模型/推理 | 升级条件 | 串并行与文件规则 |
|---|---|---|---|
| 仓库定位、明确边界的 adapter 实现 | Astra low | 两次局部失败或跨模块冲突→Main诊断后medium/high | Contract冻结且allowed_files不交叉才能并行 |
| 状态提交、失效、checkpoint、路由 | Astra medium；复杂一致性 high | 晚到结果/重复恢复无法闭合 | 公共契约先由Main处理；图与路由串行 |
| 科学公式适用性/独立数值验证 | Astra high | 标准证据冲突→人工升级 | 不授予直接改公式常数的权限 |
| UI明确接口接入 | Astra low | 接口语义冲突→Contract review | API冻结后；app.js同一owner串行 |
| 确定命令测试/日志/文档状态同步 | Luna medium / 文档low | 环境诊断超出一次纠正→Main | 全套集成测试一个runner；隔离临时输出 |
| 独立Review | Astra low；状态/科学风险 medium/high | 新发现改变共享语义 | 不审自己实现的任务 |
| GitHub提交与push核验 | Luna low | 冲突、错误远端、权限失败→Main | 全局单writer，精确allowlist，禁止force |

## 公共 Contract 权限

Main 独占 planning/contracts.py、planning/workflow/state.py、planning/workflow/commit.py 的语义及 CONTRACTS.md；具体实现可授予单个任务的 worker，但不能自行改变字段、状态含义或权限。planning/workflow/routing.py 与 graph.py 在冻结图边界后由同一 workflow owner 串行完成。依赖锁和 app.py 属于 Main 审批的集成文件，任务明确持有时才能修改。所有其余 ownership 以 TASK_BACKLOG.yaml 的 exact allowed_files 为准，默认拒绝未列出的路径。

互斥锁：shared_contract、workflow_core、legacy_pipeline、public_api、web_ui、knowledge_catalog、dependency_lock、integration_runtime、git_publish。即使使用独立 worktree，同一锁也不并行；worktree 不替代逻辑 ownership。Agent 从已接受的基线建工作区，不私自切换含用户修改的主工作树。

## Task Packet（Main 派发时逐项填充）

~~~yaml
TASK_ID: 从TASK_BACKLOG选取
TITLE: 当前任务标题
OBJECTIVE: 唯一可验收目标
WBS_REF: 逐项ID
CONTEXT: 当前证据和批准范围
DEPENDENCIES: 必须全部ACCEPTED
CONTRACT_VERSION: 精确版本与hash
BASELINE_COMMIT: 精确commit及额外工作树manifest
ALLOWED_FILES: 精确清单
FORBIDDEN_FILES: 禁区及默认拒绝未列出文件
INPUTS: 已存在输入
EXPECTED_OUTPUTS: 输出文件和行为
ACCEPTANCE_CRITERIA: 可观察断言
TEST_COMMANDS: 精确命令与预期
KNOWN_RISKS: 风险编号
LOCKS: 已获得的互斥锁
RETRY_BUDGET: 2
DO_NOT: 不改原图/角色数/RAG底座/冻结接口
~~~

## Handoff（Agent 必须返回）

~~~text
TASK_ID / STATUS: PASS|PARTIAL|BLOCKED|FAILED
BASELINE_COMMIT / CONTRACT_VERSION
FILES_CREATED / FILES_CHANGED / FILES_DELETED
IMPLEMENTATION_SUMMARY
CONTRACTS_USED / CONTRACT_CHANGE_REQUESTS
TESTS_ADDED / TEST_COMMANDS_RUN / TEST_RESULTS（exit code、时间、日志）
ACCEPTANCE_CRITERIA_RESULTS
KNOWN_LIMITATIONS / RISKS_FOUND / FOLLOW_UP_RECOMMENDATION
失败时：FAILURE_CLASS / ROOT_CAUSE_HYPOTHESIS / ATTEMPTS_USED
WHAT_WAS_NOT_TRIED / RECOMMENDED_NEXT_OWNER
~~~

Agent 的 PASS 只是提交审查，不自动等于任务 ACCEPTED。非实现者 Reviewer 核验 diff、验收和失败路径；Tester 在合并后的同一基线上跑集成；Main 决定 Accept，更新 Backlog/WBS/log 后释放锁。禁止多个 Agent 争写状态文件。
