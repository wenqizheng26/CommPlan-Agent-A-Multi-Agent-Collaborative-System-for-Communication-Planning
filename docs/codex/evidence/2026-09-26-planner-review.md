# planner.py 审查修正（2026-09-26）

工作区：`CommPlan-Agent-M1-codex`；分支：`codex/m1-week3`。对照 Claude 2026-09-26 六项意见与 AGENT_LED §2a。

## 修正

1. `propose` 先合并 pending_questions；仅 AWAITING_CONFIRMATION 调用 PlanningAgent。追问保留无 origin、无 assessment 的程序预览。
2. compile_proposal 只验证计划；评估使用独立 accept_assessment / Rewrite，重写一次后只隐藏不合格条目（withheld: true、text: null）。没有合格条目时 assessment.mode 为 skipped。确认重放重新验证保留文字和隐藏条目的形状。重写时离线仍保留前次通过的计划。
3. origin_note 由计划失败码映射为中文原因，目标不符时用实际目标名称；确定性与离线不写该字段。
4. suggest caller 和 MAX_TOKENS 使用 compute_agent。
5. 删除 report.preflight 及其合同和重放字段；前端、审查角色直接读取 calculation_plan_proposal.assessment。条目隐藏时显示“该条未通过数字核对”，全部隐藏时显示“未做模型适用性评估”。
6. 保留原 PROMPT 文本；组装模型输入集中到 planning_view。没有调校真实 9B，也没有缩减原参数来源输入。

## 验证

- Node：`node --test tests/*.test.mjs`，48 项通过。
- Python：`python -m unittest discover -s tests`，374 项，OK（1 项跳过）；最终全量结果见同目录 `2026-09-26-planner-review-tests.log`。
- `pip check`：No broken requirements found。
- 本次涉及的已跟踪文件 `git diff --check` 无错误。全工作区检查另有此前未提交的 app.css 文件末尾空行，不在本次修正范围。
- 新增替身模型回归：评估重写成功、单条隐藏、全部隐藏、非法引用、重写离线、追问不调用模型、中文原因映射和隐藏条目确认重放。

## 交付边界

本工作区开始时已有大量未提交的 M1 实现，本次保持其他工作；修正仍留在工作区，未提交、未推送、未合并。真实 9B 与浏览器验收未运行；由 Claude 后续调校及验收。
