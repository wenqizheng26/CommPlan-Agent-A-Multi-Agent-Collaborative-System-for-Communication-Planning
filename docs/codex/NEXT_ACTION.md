# Demo delivery 当前入口（2026-09-23）

分工原则：需要判断的设计、取舍与风险由 Claude 决定并写成任务；规则明确的迁移、重跑、记录与推送交给 Codex。按顺序执行 C3 → C2，任一步失败即停止并记录原始输出。

## Codex 任务 C3：把历史内容移到项目外（先做）

> **目标**：仓库只留当前 Demo 需要的文档；历史阶段记录与旧验证产物移到 `E:\codex\项目\信号与AI\_archive\2026-09-23-commplan\`（下称 ARCHIVE），保持原相对路径。Git 历史仍保留全部内容。
> **范围**：只移动文件、修正剩余文档中的失效链接、更新 `AGENTS.md` 一句说明。
> **禁止**：删除任何文件（只移动）；改 `planning/`、`formula_rag/`、`tests/`、`scripts/`、`.github/`、`app.py`、`web/`、`launch.py`；移动正在被运行中服务使用的数据库；动父目录中非本项目的文件夹（`content_review_v*`、`final_polish_v*`、`review_revision_v*`、`backups`、`pelican*`、`test.txt`）。
> **步骤**：
> 1. 受 Git 跟踪的内容：复制到 ARCHIVE 后 `git rm`。
>    - `docs/codex/` 下除 `NEXT_ACTION.md`、`DEMO_HANDOFF_V4.md`、`DEMO_STAGE0.md`–`DEMO_STAGE3.md`、`GITHUB_PUBLICATION.md`、`evidence/` 以外的全部文件（含 `validate_control_files.py`、`TASK_BACKLOG.yaml`）。
>    - `docs/codex/evidence/` 中未被上述保留文档或 `docs/demo/VALIDATION.md` 引用的文件（先 grep 引用再移动）。
>    - `docs/superpowers/`、`docs/mockups/`、`docs/diagrams/`、`docs/2026-09-14-interface-refinement.md`、`docs/p1-applicability.md`、`docs/system-flow.md`、`docs/通信公式RAG案例问题.txt`、`HANDOVER.md`、`BACKUP.md`、`reports/`。保留 `docs/requirements.md`、`docs/demo/`。
>    - 本文件第一条 `---` 之后的历史记录剪切为 ARCHIVE 下 `docs/codex/NEXT_ACTION_HISTORY.md`。
> 2. 不受跟踪的 `outputs/`：先用 `Get-CimInstance Win32_Process` 查出运行中工作台的 `--db` 参数，这些数据库与 `planning.sqlite*`、`releases/` 留下；其余解压目录（`audit-clean-env`、`clean-install-*`、`final-candidate-unpacked-*`、`stage4-extracted-*`）和验收数据库移到 ARCHIVE 的 `outputs/`。
> 3. 在保留的 Markdown 中 grep 指向已移动文件的相对链接，改为纯文本“（已归档）”。仓库 `AGENTS.md` 中“旧交接与 WBS 是阶段记录”一句改为“历史阶段记录已移到仓库外 `_archive/2026-09-23-commplan/`，Git 历史可查”。
> 4. 在 ARCHIVE 根目录写 `MANIFEST.md`：每个移动项的原路径、大小、对应 Git 提交。
> 5. 运行 `node --test tests/planning_*.test.mjs` 与 `.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests -p "test_*.py"`，确认与移动前计数一致；单独提交，信息以 `chore: archive` 开头。
> **完成标准**：`git status` 干净；测试计数不变；保留文档内无失效相对链接；ARCHIVE 有清单。

讲解：H0 时期的控制文档体系（WBS、TASK_BACKLOG 及其校验器）已被 V4 规格与 VALIDATION 取代，仓库里没有代码或测试依赖它们；`outputs/` 中的旧候选各带一整份 `.venv`，只增加检索噪声。旧版 Formula RAG 应用（`app.py`、`web/`、`test_app.py`、旧脚本、CI legacy-full）和父目录的 `.workareas`、`signal-formula-rag` 留到打 tag 之后的 C4 处理：此时改 CI 会改变 Stage 4 门禁的含义。

## Codex 任务 C2：视觉改版后的 Stage 4 重新验证（C3 之后）

> **目标**：2a83419（Visio 布局）与 6ef0882（苹果风格视觉系统）改了发布包内的前端源码，在 C3 之后的 HEAD 上重跑门禁、重建正式源码包、推送并取得 CI 结果。
> **范围**：只运行命令和更新 `docs/codex/NEXT_ACTION.md`、`docs/codex/DEMO_STAGE3.md`（或 Stage 4 记录）、`docs/demo/VALIDATION.md`。
> **禁止**：改源码或测试；PR、合并、打 tag；把本地或内置浏览器结果写成目标 Chrome 通过或独立审查通过；`reset`/`clean`/`stash`。
> **步骤与验证命令**（Windows，仓库根目录）：
> 1. `.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests -p "test_*.py"`、`node --test tests/planning_*.test.mjs`（应为 27）、`.venv\Scripts\python.exe -m pip check`。
> 2. `.venv\Scripts\python.exe -B -X utf8 scripts\build_planning_release.py --require-clean`，再 `.venv\Scripts\python.exe -B -X utf8 scripts\validate_planning_release.py <ZIP>`（不加 `--no-smoke`）。
> 3. 模型在线与离线降级各跑一次完整示例，确认流程图高亮与结果一致；浅色与系统深色各看一次。
> 4. 文档提交后 `git push commplan codex/demo-delivery-final`，记录 CI run 号与两个 job 结果。
> 5. VALIDATION 中 Stage 4 各行改为新 SHA、ZIP SHA-256 与 CI run；删除 C3、C2 两节，把结果写进下方状态段。
> **完成标准**：三项回归通过；`--require-clean` ZIP 验证通过；CI 两个 job 通过；文档与 HEAD 一致。

讲解：流程图按 `项目流程图_2026-09-16/双页版/通信筹划多智能体协同流程_双页节点完整版.vsdx` 第 1 页重排，用户批准的偏离：补问并入参数确认；确认→计算门控虚线；总控↔LLM 标“未接入”；计算 Agent→LLM 细虚线“工具建议 · 可选”（数值只来自登记 FSPL）。6ef0882 按用户要求改为苹果风格：`app.css` 从四层叠加主题重写为单一变量体系（默认浅色、随系统深色），一个强调色，系统状态色只表示状态；节点统一为卡片，能力类（LLM、RAG、知识库、计算模型）同一淡靛蓝色族。运行高亮逻辑未改。目标 Chrome 七项流程须在 C2 完成后的新候选上由用户进行。

## 当前关口：Stage 4 外部验收

主工程已从 `.workareas` 迁至父目录的 `CommPlan-Agent/` 独立 Git 仓库；旧 worktree 与外部模型源保留作回滚。当前在 `codex/demo-delivery-final`，发布目标只使用 `commplan` remote。Stage 3 已推送。三栏 UI 源码为 `b62aaef`；Stage 4 修正 Windows CI 路径断言的测试提交为 `5c43630`，没有改变发布包内的业务源码。该提交的干净 source ZIP 已通过解压 smoke；哈希和边界见 [VALIDATION](../demo/VALIDATION.md)。

GitHub `workflow` scope 已补齐，分支远端 CI 的 `planning-minimal` 和 `legacy-full` 均通过（run `35820319930`）。Stage 4 的剩余外部门禁是目标 Chrome 七项流程和实施团队外 Reviewer 的最终 diff 审查；内置浏览器的 2560×1440 预览不能代替前者。验收工作台为 `http://127.0.0.1:18084`，使用独立数据库且模型服务已就绪。完成这些门禁并更新统一验收记录后才进入 Stage 5 的 PR、合并、main 重建包与 tag。

## 当前状态（2026-09-23）

- 最新代码/测试提交 5c43630；新仓库完整 `.venv` 运行 Python 233 OK（1 symlink 权限 skip），Node 25 PASS，pip check PASS。
- 发布目标已定为 CommPlan-Agent 仓库，本地 remote 名为 `commplan`（`origin` 仍为 signal-formula-rag，不用于发布）。远端 main 为 9ee7939，是本分支祖先，可快进。
- 远端分支已推送；CI run `35820319930` 两个 job PASS。旧 `origin` 为历史 signal-formula-rag 仓库，不用于本轮发布。
- 目标 Chrome 验收：用户手动。独立最终代码审查：用户另找人工审查者，审查范围 `9ee7939..HEAD`，关注点见 VALIDATION 末段。

唯一实施规格：[V4](DEMO_HANDOFF_V4.md)。严格按 Stage 0 → 5，只交付当前 FSPL Demo；下方提到扩展传播模型的旧计划仅为历史，不是本轮授权。

Stage 0 已保全当前本地候选并完成 Windows Python 217 / Node 16 / pip check。提交 d3e7f60，分支 codex/demo-delivery-final。首次 push 被 GitHub 拒绝：OAuth 缺 workflow scope，CI 不得宣称通过。

无单位距离残留检测已经存在于当前源码，Stage 0 全量回归通过；历史“仍待修复”结论已过期。Stage 1 补齐四个 V4 拒绝例与合法共享单位候选回归。运行连线现在明确表示观测到的活动/责任关系，不声称 LangGraph 直接调用；fingerprint 纳入公式知识与启动资源配置，排除运行历史和日志。后端图、状态与数值执行不变。

Stage 1 已完成：3ac8819；Stage 2 已完成：8aabb57。Stage 3 的本地实施与回归已完成：模型/llama 从真实外部 asset root 先复制进被 Git 忽略的项目内目录并逐文件验哈希；实际内部 llama 服务 `/health`、`/v1/models`、工作台识别及三角色 Qwen 流程通过；Windows Python 3.12 全新解压安装、pip check、HTTP 创建/确认/重启恢复 smoke 通过。新三栏 UI 在内置浏览器中验证：整页无滚动，输入、流程、结果和补充回答同屏；流程图无内滚动，提示不覆盖右上角。

下一步：等待用户在目标 Chrome 完成七项流程并报告结果，等待独立 Reviewer 审查 `9ee7939..HEAD`。Stage 4 本地回归、模型在线/离线降级、Windows 解压 smoke 和远端 CI 已通过。Stage 5 的 PR、合并、main 重建与 tag 均未执行。权威状态表见 [VALIDATION](../demo/VALIDATION.md)。完整阶段记录见 DEMO_STAGE0.md 与 DEMO_STAGE3.md 等。
