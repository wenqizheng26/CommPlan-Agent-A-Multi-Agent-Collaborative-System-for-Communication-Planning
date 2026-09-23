# Demo delivery 当前入口（2026-09-23）

唯一实施规格：[V4](DEMO_HANDOFF_V4.md)。当前仅交付 FSPL-stage Planning Workbench；后端主体、确定性数值与确认/恢复合同维持冻结。权威验收状态见 [VALIDATION](../demo/VALIDATION.md)。

## 已完成：C3 历史归档

- 历史受跟踪文件先复制并逐文件验哈希，再从仓库移除；旧解压目录和闲置验收数据库移到仓库外 `_archive/2026-09-23-commplan/`。保留 4 份当前文档引用的证据、运行中的数据库和 `outputs/releases/`。
- 仓库外 `MANIFEST.md` 记录 139 个条目的原路径、大小与来源提交；保留 Markdown 的相对链接检查为 0 个失效链接。原本就不存在的 2 个历史报告链接已标明失效。
- 单独提交 `03c985f8757651ef3f6fb3ca54d947ead18c9585`；归档后 Python 233 OK（1 symlink 权限 skip）、Node 27 PASS，工作树干净。旧版 Formula RAG、CI legacy-full、父目录 `.workareas` 与 `signal-formula-rag` 不属本次归档范围。

## C2：视觉改版后的 Stage 4 候选

- 基于干净提交 `03c985f` 运行 Python 233 OK（1 skip）、Node 27 PASS、`pip check` PASS。`--require-clean` source ZIP 的 SHA-256 为 `64CA21C1DAE6FF21B51CF7A05333D878CBC76AEFD7D1F97DC6D89CF3AE66942C`；验证器解压、指纹和 HTTP 创建/确认/重启恢复 smoke PASS。
- 独立数据库上的在线 Qwen 与真实离线降级均完成完整 FSPL 示例，确定性原值均为 98.42059991327963 dB。模型从项目内资源重启，`/health` 与 `/v1/models` 正常。内置浏览器所见流程高亮与结果一致；离线 LLM 明示“调用已降级”。
- 1430×804 CSS 视口（对应当前 2560×1440 Windows 显示）浅色三栏同屏，无整页或流程内滚动，控制台无 warning/error。系统深色实测尚未完成；内置浏览器不能代替目标 Chrome 验收。
- `commplan/codex/demo-delivery-final` 已推送到 `ce685d4`；[CI run 35830153906](https://github.com/wenqizheng26/CommPlan-Agent-A-Multi-Agent-Collaborative-System-for-Communication-Planning/actions/runs/35830153906) 的 `planning-minimal` 与 `legacy-full` 均 PASS。系统深色实测仍待完成，C2 未据此宣称全部 PASS。

## Stage 4 外部门禁与 Stage 5

- 目标 Chrome 七项流程按 V4 §29，由用户在最新候选 `http://127.0.0.1:18088` 手动验收；不能以 Node 或内置浏览器替代。
- 实施团队外的独立 Reviewer 审查 `9ee7939..HEAD`，重点见 VALIDATION；本代理自审、测试和运行时 Review Agent 不计入。
- 上述门禁通过并更新统一验收记录后，才进入 Stage 5：PR、合并 `main`、从已接受的 `main` 重建/验收 ZIP、打 tag。此时之前不执行 C4 旧应用与旧工作区清理，不声明 `CommPlan-Agent Demo Release Ready`。
