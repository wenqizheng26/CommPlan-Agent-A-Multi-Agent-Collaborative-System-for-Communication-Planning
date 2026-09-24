# CommPlan-Agent 当前交接（2026-09-24）

## M1 下一阶段（分支 `claude/calc-plans`，不影响正在审查的 v0.1.0 候选）

验收点见 [ACCEPTANCE_M1](../design/ACCEPTANCE_M1.md)，设计见 [CALCULATION_PLANS](../design/CALCULATION_PLANS.md)。第 1 周的通用计算链已提交在 9a69535。v0.1.0 发布之前，不要把该分支合入 `codex/model-eval-integration` 或 `main`。

### Codex 任务 C7：计算链的评测与真实模型回归

> **目标**：在真实 Qwen 下确认，扩展计算链之后，FSPL 的表现没有退化，链路预算请求也能走通。
> **范围**：在 `claude/calc-plans` 上新增评测用例、证据和测试；不改 `planning/` 业务代码。发现问题时记录原始输出，交给 Claude 判断，不要自行修改业务逻辑。
> **环境**：
> - 该分支已检出在工作区 `E:/codex/项目/信号与AI/CommPlan-Agent-M1`（与主工作区 `CommPlan-Agent` 并列；可用 `git worktree list` 核对），所有命令都在这个目录运行；不要在主工作区切换到这个分支。
> - Python 使用主工作区的 `CommPlan-Agent\.venv`。
> - 本工作区没有被 git 忽略的 `models/`，否则评测会把 Qwen 记为 `not_installed`。先在 cmd 中执行 `mklink /J models E:\codex\项目\信号与AI\CommPlan-Agent\models` 建立目录联接（该路径已被忽略，不会进入提交或源码包），完成后可以删除。
> - Qwen 服务仍从主工作区启动。
> - 不推送、不合并；完成后把提交号告诉 Claude。
> **步骤**：
> 1. 在 `tests/eval/requirements_cases.jsonl` 中增加 6 条用例，同步更新 `tests/test_eval_models.py` 中的条数断言：
>    - 完整链路余量；
>    - 完整接收功率；
>    - 缺少预算参数；
>    - 余量与热噪声同时请求（期望 NEEDS_MODEL）；
>    - 多步计划中出现区间（期望 PLAN_DOMAIN_UNSUPPORTED）；
>    - 馈线损耗为负。
>
>    期望值以 `tests/test_calculation_plans.py` 的行为为准。
> 2. 用 `scripts/eval_models.py` 跑确定性基线和两个 Qwen 档案，与 C6 的结果逐条对比。重点检查原有 FSPL 用例：纯 FSPL 请求送入模型的候选多了 `received_power` 卡，需要确认目标识别没有变化。
> 3. 在主工作区启动本机 Qwen，用本分支服务（模型模式）完成页面上的“链路预算”示例，记录任务 id、截图，以及每一步的数值。
> 4. 回归：Python、Node、`pip check` 全部通过。结果写入 `docs/codex/evidence/`，并在本节末尾补一行状态。
> **完成标准**：新增用例的确定性基线全部通过；FSPL 用例与 C6 相比，退化项逐条列出（没有退化也要写明）；真实模型场景有证据；未完成的项目如实标为待办。

讲解：计算链由程序按公式卡的输出名和输入名反向拼接，模型在这一步只参与目标识别。数值仍然只来自登记公式，每一步都有独立复算。单步 FSPL 的执行、结果形状和数值保持 v0.1.0 原样。

---

唯一实施规格：[V4](DEMO_HANDOFF_V4.md)。当前交付范围仍是 FSPL-stage Planning Workbench；后端确认、checkpoint、revision 与确定性数值合同保持冻结。验收证据见 [VALIDATION](../demo/VALIDATION.md) 和 [C5/C6 记录](evidence/2026-09-24-C5-C6.md)。

## 当前候选

- `codex/model-eval-integration` 将 `claude/model-retrieval` 的模型注册表、设置、检索和计时 UI，与已合并 GitHub `main` 的旧网页清理及 C5 评测合并。C5 提交 `41d18b0`；合并提交 `7771c2c`。旧应用 `app.py`、根目录 `web/`、对应脚本/测试已删除，工作台所依赖的 `formula_rag/` 保留。
- C5 的 30 条固定案例已运行确定性基线及两个本地 Qwen 档案。模型 27 次实际尝试中，两个档案各 25 次结构化成功、2 个案例降级；参数和状态 30/30 包含程序回退，不能说成模型独立 30/30。
- C6 合并后 Python 251 项 OK（1 项系统权限 skip）、Node 33 项 PASS、`pip check` PASS。真实 Qwen、快速失败审查档案、BGE 混合检索、离线降级已在独立数据库上验证；三个任务均完成并得到 98.42059991327963 dB。正常运行的审查角色曾因结构化失败降级；混合检索运行的 BGE 状态为 `ready`，三个模型角色均完成；离线运行三个模型角色均记录 `offline`，随后模型已重启并通过健康检查。
- C6 的干净源码 ZIP 已完成构建与解压 smoke；全新解压目录的 `setup_planning.cmd`、`pip check` 和 HTTP 创建/确认/重启恢复也通过。首次 GitHub CI 暴露了评测单测依赖本机模型文件的假设；`e301ecc` 已修复，此后 [最终代码 CI](https://github.com/wenqizheng26/CommPlan-Agent-A-Multi-Agent-Collaborative-System-for-Communication-Planning/actions/runs/35948954929) 和 [验收记录 CI](https://github.com/wenqizheng26/CommPlan-Agent-A-Multi-Agent-Collaborative-System-for-Communication-Planning/actions/runs/35949403530) 两个作业均 PASS。用户已确认新候选在目标 Chrome 的七项及附加检查通过。后续提交的状态以 [分支 CI 列表](https://github.com/wenqizheng26/CommPlan-Agent-A-Multi-Agent-Collaborative-System-for-Communication-Planning/actions?query=branch%3Acodex%2Fmodel-eval-integration) 为准；发布门禁尚缺实施团队外独立审查。

## 下一步

1. 请实施团队外的 Reviewer 独立审查最终候选，范围为 GitHub `main` 与 `codex/model-eval-integration` 的差异，重点核对模型评测口径、检索证据门禁、设置与状态快照、活动语义、启动身份和发布包排除项。此前实施者和子智能体的自审不计入。
2. 独立审查通过后，才继续 V4 Stage 5：PR、接受到 `main`、从被接受的 `main` 重建/验收 ZIP、tag。此前不声明 `CommPlan-Agent Demo Release Ready`。

项目内模型资源位于被忽略的 `models/signal-formula-qwen3/`；源码包默认不包含模型权重与 llama runtime，GitHub 不应包含它们。父目录 `.workareas` 和 `signal-formula-rag` 不是当前入口，也不在本次修改范围。
