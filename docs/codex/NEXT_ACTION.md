# CommPlan-Agent 当前交接（2026-09-25）

## M1 第 2 周：模型主导（分支 `claude/calc-plans`）

设计见 [AGENT_LED](../design/AGENT_LED.md)，验收见 [ACCEPTANCE_M1](../design/ACCEPTANCE_M1.md)。v0.1.0 发布之前，不要把该分支合入 `codex/model-eval-integration` 或 `main`。

分工：C8–C11 由 Codex 执行，用户已确认（2026-09-25），可以开始。Claude 同期在本工作区做需求抽取扩展、计划格式扩展与硬规则 H3、站点和设备接入参数来源，C9–C11 合入后接上。

四个任务的共同约定：
- **工作区**：Codex 在单独的工作区做，避免与 Claude 同时改一个目录。第一次开始时在 cmd 中执行 `git -C E:/codex/项目/信号与AI/CommPlan-Agent-M1 worktree add ../CommPlan-Agent-M1-codex -b codex/m1-week2`，此后所有命令都在 `E:/codex/项目/信号与AI/CommPlan-Agent-M1-codex` 运行（`git worktree list` 核对）。按 C8 → C9 → C10 → C11 依次做，每个任务单独提交；C9 与 C11 都会改 `knowledge/formulas.json`，不要同时进行。
- Python 用主工作区的 `CommPlan-Agent\.venv`。需要模型时，在该工作区执行 `mklink /J models E:\codex\项目\信号与AI\CommPlan-Agent\models` 建目录联接（该路径被忽略，完成后可删）。
- 不推送、不合并；每完成一个任务，把提交号告诉 Claude，由 Claude 审核后合入 `claude/calc-plans`。发现与设计不符的地方，记录原始输出交给 Claude 判断，不要自行改设计。
- 回归：Python、Node、`pip check` 全部通过；证据写入 `docs/codex/evidence/`，并在对应任务末尾补一行状态。

### Codex 任务 C8：换用本机 9B 模型

> **目标**：演示模型换成 Qwen3.5-9B（Q4_K_M，Vulkan，上下文 16384），在注册表中设为默认；达不到下面的标准时改用 Qwen3-8B。
> **范围**：`config/models.json`、`launch.py`、`start_commplan.py`、模型状态探测、主工作区被忽略的 `models/`、相关测试与证据。不改 `planning/agents`、`planning/services` 的业务逻辑。
> **步骤**：
> 1. 从 Hugging Face `unsloth/Qwen3.5-9B-GGUF` 下载 `Qwen3.5-9B-Q4_K_M.gguf`（5,680,522,464 字节）到 `CommPlan-Agent\models\signal-formula-qwen3\models\Qwen3.5-9B-GGUF\`；SHA256 以该文件页的 LFS 信息为准（设计时查到以 `03b74727` 开头）。只下载这一个文件，不下载 mmproj 视觉文件。
> 2. 先停掉 4B 服务（8 GB 显存放不下两个模型）。用项目内 `llama.cpp-b10950`（Vulkan）按 `launch.py` 现有参数启动，`-c 16384`，端口仍为 18081。检查：启动日志显示全部层在 GPU、没有算子回落 CPU（Qwen3.5 的 DeltaNet 层在部分 Vulkan 版本上回落 CPU 会导致输出异常，见 llama.cpp issue #19957）；3 条固定中文提示输出正常；记录生成速度与首字延迟；一条 `response_format: json_schema`（strict）请求输出合法。
> 3. 通过标准：输出正常，生成 ≥ 15 token/s，严格 JSON 可用。任何一项不通过，改下 `Qwen/Qwen3-8B-GGUF` 的 `Qwen3-8B-Q4_K_M.gguf`（5,027,783,488 字节，SHA256 以文件页为准，设计时查到以 `d98cdcbd` 开头），重复第 2 步，并在证据中写明原因。
> 4. 注册表新增一项（如 id `qwen35-9b-q4`，显示名“Qwen3.5 9B · Q4_K_M”，context 16384，`json_schema_strict: true`，timeout 60 s，别名如 `commplan-qwen35-9b`），`defaults.chat` 改为它；两项 4B 保留。
> 5. 启动器改为按注册表的默认生成模型启动（权重、别名、端口、上下文、设备都取自注册表），不再读 `runtime_config.json` 的 `generation` 段；状态探测按注册表中的别名判断“就绪”或“不是目标模型”。同一时间只启动一个生成模型。
> 6. 用新模型跑 `scripts/eval_models.py`（36 条），与 [A1 记录](evidence/2026-09-25-A1-labels.md) 中 4B 的结果（六类各 36/36、33/33 结构化成功、0 降级）逐条比较，退化项逐条列出；工作区若不含 A1 提交（提示词不同），改与 [第 1 周收尾](evidence/2026-09-24-M1-week1-closeout.md) 比较并注明。
> **完成标准**：新模型能由启动器启动、健康检查就绪；评测报告与比较写入证据；未通过的项如实标注。

### Codex 任务 C9：直线距离、视距两张卡与假设值

> **目标**：公式库新增 `slant_range_wgs84`、`radio_horizon`；卡片参数支持假设值 `default`。
> **范围**：`knowledge/formulas.json`、`formula_rag/`（目录校验、计算内核、内容哈希、公式展示）、`planning/services/reference_models.py`（独立复算）、测试。不接入需求解析和页面流程。
> **步骤**：
> 1. `radio_horizon`：表达式卡 `4.12*(sqrt(antenna1_m)+sqrt(antenna2_m))`，输出 `radio_horizon_km`（km），参数单位 m、`min: 0`；适用说明写明 k = 4/3、不含地形与菲涅耳区余隙。出处在公开文献（ITU-R 建议书或教材）中查到并记录定位；找不到时写明由 k = 4/3、R = 6371 km 推导，并引用 k 因子的出处。两条算例。
> 2. `slant_range_wgs84`：登记的程序工具卡（`"kind": "python_tool"`，实现函数登记在白名单里；表达式语言写不下）。输入 8 个：`lat1_deg`、`lon1_deg`、`ground1_m`、`antenna1_m`、`lat2_deg`、`lon2_deg`、`ground2_m`、`antenna2_m`；输出 `distance_km`（km）。算法：WGS84 大地坐标（高度 = 地面高程 + 天线离地高度）→ 地心坐标 → 两点弦长。独立复算用另一种写法（如 ENU 分解），两者相差 ≤ 1e-6 km。数值基准：至少一个公开的大地坐标转地心坐标算例（如 NGA、NOAA 文档或教材），误差 ≤ 0.01 m；AGENT_LED 附录 A 的 A→B、A→F 作为回归值。卡片内容哈希要覆盖实现函数的源码。
> 3. 参数 `default`：`{"value", "unit", "note"}`，目录校验要求单位与参数一致、值在范围内。设置：`received_power.tx_loss_db`、`rx_loss_db` 为 2 dB（note：“工程假设，典型取值，非标准值；请按实际馈线修改”，用户 2026-09-25 确认）；`received_power.extra_loss_db` 为 0 dB（“按自由空间假设，不计其他损耗”）；`link_margin.reserve_db` 为 0 dB（“要求余量单独比较，不预先扣除”）。
> 4. 公式页：程序工具卡显示算法说明与出处，不显示表达式。
> 5. 测试：两张卡的算例；复算一致；`default` 校验（单位不符、越界被拒）；改动实现源码后内容哈希变化；现有 FSPL 单步结果与 v0.1.0 逐位一致。
> **完成标准**：以上测试通过；附录 A 各链路的距离与视距实现值写入证据，与附录 A 相差超过 0.01 km 时报告 Claude。

### Codex 任务 C10：模拟站点库、设备库与查询

> **目标**：按 AGENT_LED 附录 A 建立模拟站点库、设备库，实现 `FactService` 的 `find_site`、`find_device` 查询。
> **范围**：`knowledge/facts/`、`knowledge/documents/simulated/`、新模块（建议 `planning/knowledge/facts.py`）、知识快照、测试。不接入需求解析和页面流程。
> **步骤**：
> 1. 写 `knowledge/facts/sites.json`、`devices.json`：字段按 KNOWLEDGE_FACTS §3，`position.height_m` 拆成 `ground_m` 与 `antenna_m`（D 站 `antenna_m: null`）；新增设备类型 `device`：`model`、`tx_power_dbm`、`antenna_gain_dbi`、`rx_sensitivity_dbm`、`band_ghz`；每条 `simulated: true`，`source` 指向第 2 步文档的具体行或章节。
> 2. 写三份模拟文档（Markdown，开头标“模拟数据，仅供演示”）：`站址表.md`（附录 A 全部站点）、`XX-100 手册.md`、`XX-200 手册.md`（规格表加两三段说明）。数值与 JSON 一致，由测试核对。
> 3. `FactService`：`find_site(name)`、`find_device(name)`、`describe()`。匹配顺序：名称精确 → 别名精确 → 去掉空格和末尾“站”字后的包含匹配；返回全部候选、匹配方式与来源；同级按 id 排序；不联网；只返回库中记录；空输入或超过 50 字报错。
> 4. 事实库与模拟文档的内容哈希进入知识快照；变化时，已确认任务按“知识目录已变化”处理。
> 5. 测试：“A站”“A岸站”精确命中；“港口站”返回东港站、西港站两个候选；D 站天线高度为 null；未知名称返回空列表；文档与 JSON 数值一致；KNOWLEDGE_FACTS §7 的合同要点。C9 完成后，再用两张卡算附录 A 的预期表（容差：距离 0.001 km、余量 0.01 dB）。
> **完成标准**：以上测试通过；与附录 A 不符时报告 Claude，不改数据。

### Codex 任务 C11：反求工具

> **目标**：实现 `solve`，对计划中的一个未知量做一维反求并复核，满足 CALCULATION_PLANS §7。
> **范围**：新模块（建议 `planning/services/solve.py`），复用现有多步执行器（必要时抽出一个不依赖任务状态的纯函数），测试。不接入流程与页面。
> **步骤**：
> 1. 接口：`solve(plan, unknown, condition, bracket=None) -> dict`；失败时抛出以错误码为消息的 `ValueError`（与现有 `require` 一致），不给数值。`condition` 如 `{"quantity": "link_margin_db", "op": ">=", "value": 10}`。搜索区间取卡片参数的 `search_range`，没有时报 `SOLVE_BRACKET`。给 `received_power.tx_power_dbm` 加 `search_range: [-30, 70]`（dBm），`fspl_ghz.distance_km` 加 `[0.001, 1000]`（km）。
> 2. 算法：区间内等距取 ≥ 16 个点，确认严格单调、两端点的“条件量 − 阈值”异号；否则报 `SOLVE_NOT_MONOTONIC` 或 `SOLVE_NO_ROOT`。二分至区间宽度 ≤ 1e-9 × max(1, |x|)；按单调方向把解解释为“最小”或“最大”；把解代回整条计划算残差；在解两侧各取一点（±1e-6 相对）确认一侧满足、一侧不满足。
> 3. 返回：解与单位、方向、区间、迭代次数、残差、两侧点的条件量与判断、每步中间值。
> 4. 测试：附录 A 的 A→B（距离直接给 34.064 km）最小发射功率与闭式解（37 + 10 − 余量）相对误差 ≤ 1e-6；最远距离与闭式解比较（只在单测里）；无解、非单调、缺区间各一条；同一输入重复 3 次结果一致。
> **完成标准**：以上测试通过；结果写入证据。

### Claude（同期进行）

- A1 需求抽取扩展：模型抽取参数、站点、设备、要求与反求意图（schema、提示词、摘录核对），规则改为核对，不一致时列为冲突。**第一部分已完成（2026-09-25）**：模型标注程序找出的数量、余量要求、反求意图、站点与设备，核对时重放；Python 287 项、Node 41 项通过；4B 的 36 条评测无退化。见 [A1 记录](evidence/2026-09-25-A1-labels.md)。第二部分（补充与回答追问由模型理解）待做。
- A2 计划格式扩展：`requirement`、`solve_if_unmet`、站点与设备来源、假设值，校验加 H3。
- A3 站点、设备接入参数来源：同名、缺项、冲突走原有提问面板（C10 完成后接入）。

## M1 第 1 周（已完成，分支 `claude/calc-plans`）

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
> **C7 状态（2026-09-24）**：36 条确定性及两档真实 Qwen 评测完成，29 条与 C6 同 id 案例无退化；内置浏览器三步链路预算及九项校验通过；Python 262 项、Node 36 项、`pip check` 通过。C6 `link_margin` 与 M1 同原文 `link_margin_missing_budget` 的状态及模型降级差异见 [C7 证据](evidence/2026-09-24-C7.md)；仅本地提交，未推送或合并。

> **第 1 周收尾（2026-09-24，Claude）**：C7 发现的模型降级、链路预算参数无法逐项回答或补充、模型模式下补充从不合并、多轮后审查超出上下文，均已修正。两档 Qwen 33/33 结构化成功、0 条降级，与 C7 相比无退化；Python 269 项、Node 36 项通过。见 [收尾记录](evidence/2026-09-24-M1-week1-closeout.md)。其中“模型模式下补充从不合并”在 v0.1.0 候选中同样存在，未在主工作区修改。

> **工作台可读性改版（2026-09-24，Claude）**：布局与文案按 [WORKBENCH_UI](../design/WORKBENCH_UI.md) 重做；后端只加了只读接口 `/api/formula-cards`（公式页逐步显示登记公式，按内容哈希核对）；Python 270 项、Node 41 项通过，内置浏览器三种宽度已检查，目标 Chrome 未验。

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
