# Demo delivery 当前入口（2026-09-23）

## 模型与检索：已实施，待 Codex 联调与复验（2026-09-23）

分支 `claude/model-retrieval`（独立工作树 `../.workareas/commplan-model-retrieval`，基于 `main` a48b431）：084b29a 后端核心、2acadf6 接口、4b68159 页面，以及本文档提交。本地 Python 255 OK（1 skip）、Node 33 PASS；真实 bge 模型通过检索合同 7 项；浏览器内确定性与模型离线两条完整流程通过，无控制台错误。设计与取舍见 [MODEL_RETRIEVAL](../design/MODEL_RETRIEVAL.md) 第 12 节，RAG 对接见第 13 节。真实 Qwen 在线调用、目标 Chrome、独立审查、远端 CI 均**尚未进行**。

分工原则不变：判断与设计由 Claude；以下两项规则明确，交给 Codex。按 C5 → C6 顺序执行，任一步失败即停止并记录原始输出。

### Codex 任务 C5：模型评测集与运行脚本

> **目标**：规格第 8 节。换模型前必须有可比较的证据。
> **范围**：新增 `tests/eval/requirements_cases.jsonl`、`scripts/eval_models.py`、对应单元测试；不改 `planning/` 业务代码。
> **内容**：约 30 条用例（完整、缺参、冲突、区间、离散候选、无单位、超出范围、手工目标/条件），每条写期望参数（值与单位）、目标、条件与期望状态；可复用 `planning/examples/` 与现有测试中的句子。脚本 `--models <注册表 id...>`（默认全部生成模型，外加确定性基线），用 `Registry.binding()` 绑定 `LocalSelector`，逐条运行 `RequirementsAgent`，统计：结构化通过率、参数抽取正确率、状态正确率、降级率与原因、p50/p95 延迟、token；输出 `outputs/eval/<日期>-<模型>.json`。模型离线时如实记为离线，不伪造成绩。
> **完成标准**：确定性基线可在无模型环境复现；单元测试覆盖统计口径；提交信息以 `test: add` 或 `feat(eval):` 开头。

### Codex 任务 C6：合并、真实模型联调与全量复验

> **目标**：把本分支与 `codex/github-prune`（旧应用清理，当前在主工作区未提交）合成一个候选，完成规格第 11 节门禁中可在本机完成的部分。
> **禁止**：改变确认、计算、校验语义；把内置浏览器或本机结果写成目标 Chrome 或独立审查通过；`reset`/`clean`/丢弃任何一方的修改。
> **步骤**：
> 1. 先提交 `codex/github-prune` 自身的修改；新建集成分支，合并两边。冲突（预计在 `scripts/build_planning_release.py`、`README.md`）保留两边意图：发布白名单同时去掉旧应用文件、加入 `config/models.json`、`planning/providers/*`、`planning/retrieval/*`、`planning/web/settings.mjs`、`planning/web/timing.mjs`。
> 2. 全量回归：Python、Node、`pip check`；`--require-clean` 重建源码包并用验证器解压 smoke。
> 3. 真实联调（主工作区，含 `models/`）：启动本机 Qwen；本机模型模式跑完整示例到完成；把「结构化审查」覆盖为“快速失败”档案再跑一次，核对 `run_settings`、性能视图按模型分组；切到混合检索，确认向量预热后「依据」页签出现向量分与融合分；停掉模型再跑一次，核对失败原因为“离线”。记录任务 id 与截图到 `docs/codex/evidence/`。
> 4. 推送集成分支到 `commplan`，记录 CI run；更新 `docs/demo/VALIDATION.md`（新增第 11 节门禁行）和本文件。
> **完成标准**：回归、源码包、CI 通过；联调四个场景有证据；未完成项如实标为待办。

讲解：模型只影响参数草稿、候选与审查意见，数值仍只来自登记 FSPL；设置每次命令开始时复制一份并记录，改设置不会让已确认结果失效。检索的候选准入仍要求词项证据，向量相似度只影响排序和送入模型的范围。

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
- 上述门禁通过并更新统一验收记录后，才进入 Stage 5：PR、合并 `main`、从已接受的 `main` 重建/验收 ZIP、打 tag。此时之前不执行 C4 旧应用与旧工作区清理，不声明 `CommPlan-Agent Demo Release Ready`。
