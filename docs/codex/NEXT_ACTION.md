# CommPlan-Agent 当前交接（2026-09-24）

唯一实施规格：[V4](DEMO_HANDOFF_V4.md)。当前交付范围仍是 FSPL-stage Planning Workbench；后端确认、checkpoint、revision 与确定性数值合同保持冻结。验收证据见 [VALIDATION](../demo/VALIDATION.md) 和 [C5/C6 记录](evidence/2026-09-24-C5-C6.md)。

## 当前候选

- `codex/model-eval-integration` 将 `claude/model-retrieval` 的模型注册表、设置、检索和计时 UI，与已合并 GitHub `main` 的旧网页清理及 C5 评测合并。C5 提交 `41d18b0`；合并提交 `7771c2c`。旧应用 `app.py`、根目录 `web/`、对应脚本/测试已删除，工作台所依赖的 `formula_rag/` 保留。
- C5 的 30 条固定案例已运行确定性基线及两个本地 Qwen 档案。模型 27 次实际尝试中，两个档案各 25 次结构化成功、2 个案例降级；参数和状态 30/30 包含程序回退，不能说成模型独立 30/30。
- C6 合并后 Python 251 项 OK（1 项系统权限 skip）、Node 33 项 PASS、`pip check` PASS。真实 Qwen、快速失败审查档案、BGE 混合检索、离线降级已在独立数据库上验证；三个任务均完成并得到 98.42059991327963 dB。正常运行的审查角色曾因结构化失败降级；混合检索运行的 BGE 状态为 `ready`，三个模型角色均完成；离线运行三个模型角色均记录 `offline`，随后模型已重启并通过健康检查。
- C6 的干净源码 ZIP 已完成构建与解压 smoke；全新解压目录的 `setup_planning.cmd`、`pip check` 和 HTTP 创建/确认/重启恢复也通过。首次 GitHub CI 暴露了评测单测依赖本机模型文件的假设；`e301ecc` 已修复，随后一次 [CI](https://github.com/wenqizheng26/CommPlan-Agent-A-Multi-Agent-Collaborative-System-for-Communication-Planning/actions/runs/35948390923) 两个作业均 PASS。最终文档提交的 CI 仍须确认。

## 下一步

1. 推送此文档提交并确认最终 HEAD 的 GitHub CI；从干净 HEAD 再构建一次 ZIP，记录最终 SHA-256。
2. 请用户在目标 Chrome 对**这一候选**复验 V4 §29 七项流程。旧版本上的七项通过不能自动继承；内置浏览器可做预览，但不是目标 Chrome 门禁。
3. 请实施团队外的 Reviewer 独立审查最终候选。此前实施者和子智能体的自审不计入。两项外部门禁都通过后，才继续 V4 Stage 5 的接受、从 `main` 重建 ZIP、合并和 tag；此前不声明 `CommPlan-Agent Demo Release Ready`。

项目内模型资源位于被忽略的 `models/signal-formula-qwen3/`；源码包默认不包含模型权重与 llama runtime，GitHub 不应包含它们。父目录 `.workareas` 和 `signal-formula-rag` 不是当前入口，也不在本次修改范围。
