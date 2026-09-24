# CommPlan-Agent 当前交接（2026-09-24）

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
