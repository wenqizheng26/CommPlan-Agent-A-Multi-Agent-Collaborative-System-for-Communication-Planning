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

---
以下全部为历史记录；计数、缺陷状态、下一步与发布状态不代表当前候选。

# 当前状态与下一步

## 2026-09-22 用户选择作为独立模型上下文

用户在页面或澄清问题中选择的目标、模型条件，现在通过独立字段传给本机需求模型，不拼接进原文。已选择字段的模型提议数组由 JSON Schema 限制为空，程序继续采用用户选择，并记录 `USER_TARGET_SELECTION` / `USER_CONDITION_SELECTION` 及对应 request 字段来源。未选择字段仍要求逐字原文证据；原文与选择冲突仍由程序拦截。

模型输出拒绝记录新增校验阶段、具体原因、拒绝项和最多 4000 字符的原始模型输出（仅在调用已返回原始输出时可用）。历史记录缺失的信息不补造。完整 Python 回归 207 项通过；真实 Qwen 使用截图任务原文与已选目标，一次调用通过；全部使用手工选择/参数且原文为空的对照也一次通过。证据见 [user-selection-live-20260922.json](evidence/user-selection-live-20260922.json)。正式网页服务已更新，原任务未被重算或修改；旧的无单位距离表达残留仍待修复。

## 2026-09-22 模型服务与调用状态分离

新增只读 `/api/model-status`，检查固定本机端口的健康状态及目标模型标识；页面展示检查时间并支持手动刷新。该状态不写入任务或历史快照。共享 LLM 的降级调用用“调用已降级”展示，详情分列需求、计算建议、审查结果；重复诊断聚合展示次数并保留原始记录。连接失败只表示无法连接，不推断进程未启动。

验证：9 项后端测试、12 项前端测试通过；JS 语法与 diff 检查通过。正式工作台已重启，复用原 Qwen 进程。内置浏览器在既有任务中同时确认“服务已就绪”、需求解析三次校验失败后降级、后续计算与审查调用成功，控制台无 warning/error。此轮未改变参数替换逻辑，也未补录旧模型调用中缺失的详细错误原因；旧的无单位距离表达残留仍待修复。

## 当前入口：2026-09-21 需求澄清与区间计算

用户确认“需求确认与补充”的名称、集中多问题/部分回答、明确区间输出范围与离散候选分别计算。实现与验证见 [CLARIFICATION_HANDOFF_20260921.md](CLARIFICATION_HANDOFF_20260921.md)。底层沿用 AWAITING_INPUT，新增结构化问题、等待原因与 answer 命令；问题与回答继续随任务事务和版本保存。

当前支持频率/距离的区间与离散候选，不代表自主多模型规划或任意语义需求访谈。下方旧交接为历史状态，本节优先。


## 当前入口：2026-09-21 计算与审查角色增量

用户已授权按“补参阶段收尾 → 计算 Agent → 审查 Agent → 主控”推进。本轮完成受控初版，先读 [最新交接](ROLE_EXTENSION_HANDOFF_20260921.md) 与 [范围和实施合同](ROLE_EXTENSION_20260921.md)。189 项 Python、8 项 Node、pip check 通过；真实 Qwen 三个专业角色调用与真实离线降级均有证据。主控为 bounded_policy，支持审查退回、一次重算、暂时故障重试与预算终止，不是自主 LLM 总控。

补参和新增角色的内置浏览器验收已进行。Chrome 工具不可用，独立审查因子代理额度限制未执行，这两项仍待补；不要把本地自审或系统的审查 Agent 当作独立代码审查。海面/散射、多模型计划、候选优化与单/多 Agent 对照实验未完成。现有未提交修改均保留，本轮没有 Git 提交、推送或合并。

下一步先补独立代码审查与目标 Chrome 验收，再围绕已确认场景定义下一种专业模型的合同与独立数值基准，并开展角色增量的对照评估；不直接扩大传播模型范围。以下均为历史交接，不覆盖本节。

技能最新调整：用户批准 B，项目三项技能已合并为 `langgraph-workflow`；三个全局旧技能入口归档。外层和本仓库 AGENTS.md 均保留并精简，恢复位置见 [当前技能安排](SKILL_SELECTION_20260921.md)。本地模型 Agent 的 skills 留待下一轮；以下业务进度不变。

## 最新核对：2026-09-21

先读 [当前进度核对](STATUS_REVIEW_20260921.md) 与 [项目技能安排](SKILL_SELECTION_20260921.md)。持续补参与总体架构单视图已经有实现，取代下方历史双视图描述；本轮 177 项 Python、7 项 Node 和 pip check 通过。最新浏览器、真实模型与独立审查证据尚待补齐，下一步优先收尾该阶段，再整理首月研究验收材料。没有修改业务源码或发布 Git。

以下是先前阶段的历史交接，不能代替最新源码的完整验收。

## 最新：Visio 流程工作台已验收

用户确认的八模块及双视图已实现。当前权威交接为 FLOW_WORKBENCH_HANDOFF.md；证据为 evidence/flow_workbench_validation.json。169 项 Python 与 7 项 Node 测试通过，浏览器完成参数/公式/来源/确认/历史/JSON链路验收。真实观察不替代主任务提交，未接入角色明确标注。当前本地网页服务保留供试用。

以下为前一确认计算阶段记录。

2026-09-18：用户继续授权的“共享状态 → 参数确认 → 受控计算 → 校验 → 页面”已完成本地自由空间单链路切片。profile 为 `confirmed-fspl-loop-v1`，不是完整 CONTRACTS/35 项工程完成声明。

入口：`planning/run_planning.cmd` → <http://127.0.0.1:18082>。默认无需模型。权威交接：`CONFIRMED_LOOP_HANDOFF.md`；技能选择：`SKILL_SELECTION_20260918.md`；验收：`evidence/planning_loop_validation.json`。首个 Agent 的 CLI 和其历史交接仍保留。

全量 Python 164 项通过；随后来源 emoji 修复的前端 1 项和 HTTP 4 项通过，浏览器实际确认得到 98.420600 dB。真实 Qwen 和模型离线降级均完成确认计算闭环。SQLite 原子提交、重启恢复、进程中断回滚、幂等和过期请求均有测试。

下一工程阶段可从新的传播模型及其适用性、输入/输出契约和独立数值基准开始，再接入更多业务 Agent；当前不得把自由空间结果当作实际海面损耗或链路可用性。完整 GraphState 合同、分布式执行、多用户权限和全部 35 项验收仍未完成。

当前工作台可试用；验证时启动的模型进程已停止。没有提交、推送或合并 Git；已有发布任务和用户修改保持独立。既往 STOPPED_BY_USER 已在用户明确继续的本轮切片内被覆盖，不构成自动展开全部工程的授权。
