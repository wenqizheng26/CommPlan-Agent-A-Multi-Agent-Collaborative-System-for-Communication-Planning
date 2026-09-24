# Demo delivery 当前入口（2026-09-23）

## 范围变更：模型与检索纳入 v0.1.0-demo（用户 2026-09-23 决定）

- 设计规格：[MODEL_RETRIEVAL](../design/MODEL_RETRIEVAL.md)。仅本机模型；设置为全局默认并逐次记录；检索只定义接口与合同测试，向量/混合/重排实现由其他 RAG 负责人完成。
- 模型与检索实施尚未开始；后续实施完成后按 V4 重跑 Stage 2–4，并加跑规格第 11 节新增门禁。本轮用户另行授权了下述旧网页清理，不等于授权模型与检索实施。
- 因此下方 `ce685d4` 候选的目标 Chrome 验收与独立审查**暂缓**，待新候选再进行，避免重复验收；下方记录保持为该候选的真实状态。
- 分工见规格第 10 节：判断与核心由 Claude，迁移、计时、评测运行、记录、重跑与推送由 Codex，RAG 实现由其他人。

## 旧网页提前清理（用户 2026-09-23 新授权）

- 用户同意先清理 GitHub 当前树中明显退役的旧应用文件，覆盖下方“Stage 5 前不执行 C4”的旧安排；本次只涉及 `app.py`、`web/`、专用测试、旧评测脚本与示例，以及相应的启动器和文档。父目录 `.workareas`、`signal-formula-rag` 和其他 C4 候选未动。
- 清理前确认 Planning Workbench 仍依赖 `formula_rag/`、`launch.py` 中的 `model_command()` 和 `runtime_config.json`，这些均保留。旧页面被移除后，`launch.py` 不再提供指向已删除 `app.py` 的命令行入口。
- 清理分支 `codex/github-prune` 的首个代码提交为 `8d7b70b`，PR #3 已合并至 `main`（`1d97f6d`）。本机全量 Python 223 OK（1 symlink 权限 skip）、Node 27 PASS、`pip check` PASS；干净提交构建的 76 文件源码 ZIP，经完整性、HTTP 创建、确认和重启恢复校验 PASS。模型/检索新范围尚未实施；这次清理不构成 Demo 独立审查或最终发布验收。

唯一实施规格：[V4](DEMO_HANDOFF_V4.md)。当前仅交付 FSPL-stage Planning Workbench；后端主体、确定性数值与确认/恢复合同维持冻结。权威验收状态见 [VALIDATION](../demo/VALIDATION.md)。

## 已完成：C3 历史归档

- 历史受跟踪文件先复制并逐文件验哈希，再从仓库移除；旧解压目录和闲置验收数据库移到仓库外 `_archive/2026-09-23-commplan/`。保留 4 份当前文档引用的证据、运行中的数据库和 `outputs/releases/`。
- 仓库外 `MANIFEST.md` 记录 139 个条目的原路径、大小与来源提交；保留 Markdown 的相对链接检查为 0 个失效链接。原本就不存在的 2 个历史报告链接已标明失效。
- 单独提交 `03c985f8757651ef3f6fb3ca54d947ead18c9585`；归档后 Python 233 OK（1 symlink 权限 skip）、Node 27 PASS，工作树干净。旧版 Formula RAG、CI legacy-full、父目录 `.workareas` 与 `signal-formula-rag` 不属本次归档范围。

## C2：视觉改版后的 Stage 4 候选

- 基于干净提交 `03c985f` 运行 Python 233 OK（1 skip）、Node 27 PASS、`pip check` PASS。`--require-clean` source ZIP 的 SHA-256 为 `64CA21C1DAE6FF21B51CF7A05333D878CBC76AEFD7D1F97DC6D89CF3AE66942C`；验证器解压、指纹和 HTTP 创建/确认/重启恢复 smoke PASS。另在新目录解压该 ZIP，以已验证的 Python 3.12 设置 `COMMPLAN_PYTHON` 后执行 `setup_planning.cmd`、`pip check` 和解压目录自带 venv 的 HTTP smoke，均 PASS。
- 独立数据库上的在线 Qwen 与真实离线降级均完成完整 FSPL 示例，确定性原值均为 98.42059991327963 dB。模型从项目内资源重启，`/health` 与 `/v1/models` 正常。内置浏览器所见流程高亮与结果一致；离线 LLM 明示“调用已降级”。
- 1430×804 CSS 视口（对应当前 2560×1440 Windows 显示）浅色三栏同屏，无整页或流程内滚动，控制台无 warning/error。系统深色实测尚未完成；内置浏览器不能代替目标 Chrome 验收。
- `commplan/codex/demo-delivery-final` 已推送到 `ce685d4`；[CI run 35830153906](https://github.com/wenqizheng26/CommPlan-Agent-A-Multi-Agent-Collaborative-System-for-Communication-Planning/actions/runs/35830153906) 的 `planning-minimal` 与 `legacy-full` 均 PASS。系统深色实测仍待完成，C2 未据此宣称全部 PASS。

## Stage 4 外部门禁与 Stage 5

- 目标 Chrome 七项流程按 V4 §29，由用户在最新候选 `http://127.0.0.1:18088` 手动验收；不能以 Node 或内置浏览器替代。
- 实施团队外的独立 Reviewer 审查 `9ee7939..HEAD`，重点见 VALIDATION；本代理自审、测试和运行时 Review Agent 不计入。
- 上述门禁通过并更新统一验收记录后，才进入 Stage 5：发布 PR、从已接受的 `main` 重建/验收 ZIP、打 tag。旧网页已按本页顶部的用户新授权提前单独清理；父目录旧工作区仍未清理。不声明 `CommPlan-Agent Demo Release Ready`。
