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

> **C8 状态（2026-09-25，Codex）**：9B 权重大小与 SHA256 核对、Vulkan1 全层加载、三条中文提示、速度、严格 JSON、启动器就绪与 36 条真实模型评测已验证；与同分支 4B 逐案比较无合同或结构化退化。Python 287 项（1 skip）、Node 41 项、`pip check` 通过；回归与限制见 [C8 证据](evidence/2026-09-25-C8.md)。仅本地工作区，待 Claude 审核。

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

> **C9 状态（2026-09-25，Codex）**：两张卡、白名单计算、独立复算、程序源码哈希与假设值目录校验已实现；附录 A 距离/视距均与估算相差小于 0.01 km。Python 294 项（1 skip）、Node 41 项、`pip check` 通过，详见 [C9 证据](evidence/2026-09-25-C9.md)。仅本地工作区，待 Claude 审核。

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

> **C10 状态（2026-09-25，Codex）**：7 站、2 设备、3 份模拟文档及 `FactService` 已完成；歧义、缺高度、来源、文档数值与快照变化均有测试。附录 A 弦长、视距与余量复核见 [C10 证据](evidence/2026-09-25-C10.md)。Python 全量 299 项（1 skip），后续源根目录修正的 34 项定向测试、Node 41 项、`pip check` 通过。仅本地工作区，待 Claude 审核。

### Codex 任务 C11：反求工具

> **目标**：实现 `solve`，对计划中的一个未知量做一维反求并复核，满足 CALCULATION_PLANS §7。
> **范围**：新模块（建议 `planning/services/solve.py`），复用现有多步执行器（必要时抽出一个不依赖任务状态的纯函数），测试。不接入流程与页面。
> **步骤**：
> 1. 接口：`solve(plan, unknown, condition, bracket=None) -> dict`；失败时抛出以错误码为消息的 `ValueError`（与现有 `require` 一致），不给数值。`condition` 如 `{"quantity": "link_margin_db", "op": ">=", "value": 10}`。搜索区间取卡片参数的 `search_range`，没有时报 `SOLVE_BRACKET`。给 `received_power.tx_power_dbm` 加 `search_range: [-30, 70]`（dBm），`fspl_ghz.distance_km` 加 `[0.001, 1000]`（km）。
> 2. 算法：区间内等距取 ≥ 16 个点，确认严格单调、两端点的“条件量 − 阈值”异号；否则报 `SOLVE_NOT_MONOTONIC` 或 `SOLVE_NO_ROOT`。二分至区间宽度 ≤ 1e-9 × max(1, |x|)；按单调方向把解解释为“最小”或“最大”；把解代回整条计划算残差；在解两侧各取一点（±1e-6 相对）确认一侧满足、一侧不满足。
> 3. 返回：解与单位、方向、区间、迭代次数、残差、两侧点的条件量与判断、每步中间值。
> 4. 测试：附录 A 的 A→B（距离直接给 34.064 km）最小发射功率与闭式解（37 + 10 − 余量）相对误差 ≤ 1e-6；最远距离与闭式解比较（只在单测里）；无解、非单调、缺区间各一条；同一输入重复 3 次结果一致。
> **完成标准**：以上测试通过；结果写入证据。

> **C11 状态（2026-09-25，Codex）**：`solve` 已按单调采样、异号检查、二分和两侧复核实现；最低发射功率 41.066609409 dBm，最远距离单测 21.328975946 km。Python 303 项（1 skip）、Node 41 项、`pip check` 通过，详见 [C11 证据](evidence/2026-09-25-C11.md)。仅本地工作区，待 Claude 审核。

### Claude（同期进行）

- A1 需求抽取扩展：模型抽取参数、站点、设备、要求与反求意图（schema、提示词、摘录核对），规则改为核对，不一致时列为冲突。**第一部分已完成（2026-09-25）**：模型标注程序找出的数量、余量要求、反求意图、站点与设备，核对时重放；Python 287 项、Node 41 项通过；4B 的 36 条评测无退化。见 [A1 记录](evidence/2026-09-25-A1-labels.md)。**第二部分已完成（同日）**：补充由模型读、规则核对，合并前先删掉只由模型标注的旧值；Python 293 项、Node 41 项通过；真实模型实测等 C8 完成后用 9B 做。
- A2 计划格式扩展：`requirement`、`solve_if_unmet`、站点与设备来源、假设值，校验加 H3。**已完成（2026-09-25）**：视距外停止、余量要求比较、反求最小发射功率并与额定值比较，结果按参考模型复核。
- A3 站点、设备接入参数来源：同名、缺项、冲突走原有提问面板。**已完成（同日）**：查库取坐标、天线高度与电台参数，缺项取卡片假设值随确认一起确认；同名可选、缺天线高度可填、原文与库值冲突由用户选定。
- 第 3 周的“审查与解释”提前完成：模型写结论、答复、审查意见与逐步说明，数字过 H4。真实 9B 跑通演示问题 A→B、A→C、A→F。见 [A2/A3 与审查记录](evidence/2026-09-25-A2-A3-review.md)。Python 333 项、Node 41 项通过。
- 下一步（Claude）：专业计算 Agent 的确认前检查、模型写计划；页面规格先与用户确认，再写 Codex 任务单。

## M1 第 3 周：Codex 任务单（C8–C11 合入后开始）

- **工作区**：C8–C11 已合入 `claude/calc-plans`（2026-09-25，合并提交 aa9ec5d）。Claude 已删除旧工作区，并从合入后的分支新建同名工作区 `CommPlan-Agent-M1-codex`，分支 `codex/m1-week3`。开始前在 cmd 中建两个目录联接：`mklink /J models E:\codex\项目\信号与AI\CommPlan-Agent\models` 与 `mklink /J knowledge\sources E:\codex\项目\信号与AI\CommPlan-Agent\knowledge\sources`（后者的目标目录不存在时先建）；两者都被 git 忽略。其余约定同第 2 周（不推送、不合并、每个任务单独提交、证据与状态行）。
- **顺序**：C12 → C13 第 1–4 步 → C14（页面）。C13 第 5 步等 Claude 通知。
- 报告合同没有升版：新字段都是可选的，旧任务照常读取；AGENT_LED §8 的“升一版”不再单独做。

### Codex 任务 C12：文档库与混合检索

> **目标**：建立文档库（模拟文档与三份公开 ITU-R 建议书），切块后用词项加向量混合检索。向量模型换成中英文通用的 Qwen3-Embedding-0.6B，由 llama.cpp 在 CPU 上运行。检索只提供可引用的原文片段，不参与数值。
> **范围**：`knowledge/documents/`、`planning/retrieval/`、`formula_rag/retrieval.py`（如需要）、`config/models.json`、启动器与模型状态、`scripts/`（文档导入）、`requirements-planning.txt`（加 pypdf）、`THIRD_PARTY.md`、测试与证据。不改需求、计划、审查的业务逻辑；审查与解释如何使用检索由 Claude 接入。
> **步骤**：
> 1. 下载（只下这些）：
>    - `Qwen/Qwen3-Embedding-0.6B-GGUF` 的 `Qwen3-Embedding-0.6B-Q8_0.gguf`（639,150,592 字节；SHA256 以文件页为准，设计时查到以 `06507c7b` 开头），放到 `CommPlan-Agent\models\signal-formula-qwen3\models\Qwen3-Embedding-0.6B-GGUF\`，附上游许可证。
>    - ITU-R P.525-5（11/2024）、P.530-19（09/2025）、P.453-14（08/2019）的英文 PDF，从 ITU 官网各建议书页面下载在用版本，放到主工作区被 git 忽略的 `CommPlan-Agent\knowledge\sources\itu\`，各工作区经 `knowledge\sources` 联接读取（与 `models` 相同）。ITU 原文不进入 Git 和源码包（THIRD_PARTY 已写明不再分发原文）。
> 2. 注册表：新增 embedding 项 `qwen3-embedding-0.6b-q8`（runtime `llama.cpp`，endpoint `http://127.0.0.1:18084`，1024 维），`defaults.embedding` 改为它，bge 项保留。启动器在生成模型之后另起一个 CPU 进程（`--embedding --pooling last -ngl 0`，`-c`、`-b`、`-ub` 均不小于 2048，端口 18084；18082 是工作台端口），身份核验与停止规则和生成模型相同；查询前缀和文本结尾是否要加结束符，以模型卡说明为准。权重缺失时显示“未安装”，检索降为词项，不报错；模型状态同时报告两个模型。
> 3. 文档清单 `knowledge/documents/manifest.json`（入库）：每份文档记 `doc_id`、标题、版本、语言、来源 URL 或仓库内路径、本地路径、SHA256、`redistributable`（ITU 为 false）、`simulated`。C10 的三份模拟文档也列入。本地文件缺失或哈希不符的文档，标为“未安装”或“已变化”，不进索引，并在 `describe()` 中列出。
> 4. 切块：Markdown 按标题分节；PDF 用 pypdf 逐页取文本，再按段落切到每块 ≤ 800 字。块 id 形如 `doc:<doc_id>:<定位>`（如 `doc:itu-p530-19:p12-2`）；每块记录文档 id、标题、定位（页码与页内序号，或章节标题路径）、文本、文档 SHA256。同一文件重复切块，结果逐字相同。
> 5. 检索：`DefaultRetrievalService` 同时索引公式卡与文档块。`filters` 支持 `{"source_type": "formula_card" | "document_chunk"}` 和 `{"doc_ids": [...]}`；不传 filters 时只返回公式卡，需求 Agent 的行为不变。词项检索按 `knowledge/documents/glossary.json`（见下表）做中英术语扩展：查询里出现中文术语时，追加对应的英文词。向量通过 HTTP `/v1/embeddings` 获取；块向量按文档 SHA256 与模型 revision 缓存到被忽略的目录；后台预热，未就绪时按词项检索并标“降级”（沿用现有语义）。
> 6. 测试：`tests/test_retrieval_contract.py` 覆盖文档块（字段、确定性、越界参数、无网络、未就绪降级、`used` 与 top_n）。一律用假的 encoder 或假的 HTTP 服务，不依赖真实模型。另加：切块确定性与定位；清单哈希不符时不进索引；ITU 文件缺失时只少这几份，测试照常通过；术语扩展能让“海面多径”检索到英文段落（用自己写的小段英文样例，不用 ITU 原文）；用 3 组中英句子核对向量相似度排序（真实模型，可 skip）。
> 7. 真实模型实测，写入证据：以下 8 条查询在词项、向量、混合三种方式下各自的前 3 条命中（块 id、定位、各项分数）与延迟：自由空间损耗公式；视距与等效地球半径；k 因子取值；海面反射与多径衰落；衰落余量；A站坐标与天线高度；XX-100 发射功率；XX-200 接收灵敏度。另记首次建索引的耗时与向量缓存大小。
> **完成标准**：以上测试通过；实测结果写入证据；`git ls-files knowledge/sources` 为空。
>
> 术语表（`glossary.json` 按此写入，一个中文词可对应多个英文词）：
>
> | 中文 | 英文 |
> | --- | --- |
> | 自由空间 | free space, free-space |
> | 路径损耗、传输损耗 | path loss, transmission loss, basic transmission loss, free-space attenuation |
> | 视距 | line-of-sight, line of sight, radio horizon |
> | 等效地球半径、k 因子 | effective earth radius, k-factor |
> | 折射、折射率 | refraction, refractive index, refractivity |
> | 余量、衰落余量 | margin, fade margin |
> | 多径 | multipath |
> | 衰落 | fading |
> | 海面、水面 | sea, over-water, water surface |
> | 反射 | reflection |
> | 菲涅耳区、余隙 | Fresnel zone, clearance |
> | 天线高度 | antenna height |
> | 馈线 | feeder |
> | 天线增益 | antenna gain |
> | 接收灵敏度、门限 | receiver sensitivity, threshold |
> | 发射功率 | transmit power, transmitter power |
> | 地形、遮挡、绕射 | terrain, obstruction, diffraction |
> | 大气、气体吸收 | atmospheric, gaseous absorption |
> | 雨衰、降雨 | rain attenuation, rain |
> | 可用性、中断 | availability, outage |
> | 链路预算 | link budget |
> | 距离 | distance, path length |
> | 频率 | frequency |

### Codex 任务 C13：M1 评测集 v2（验收用）

> **目标**：写一套验收用例，用于 ACCEPTANCE_M1 目标档：演示问题换说法、5 个变体、四条硬规则的拦截、离线时规则结果与在线相同。说法必须独立于 Claude 调提示词时用过的句子。
> **范围**：`tests/eval/m1_cases.jsonl`（新）、`scripts/eval_m1.py`（新，端到端运行）、测试、证据。不改业务代码和提示词。
> **独立性**：写说法之前，不读 `formula_rag/model.py`、`planning/services/supplement.py` 里的示例和提示词，不读 `tests/test_requirement_labels.py`、`tests/test_supplement_labels.py` 与 A1 记录。第一次提交只含用例文件，之后再读代码写运行脚本。Claude 在第一次正式运行之前不看这些说法（合入时只核对格式测试）。
> **步骤**：
> 1. 演示问题：以“A 站到 B 站用 XX-100 电台、2 GHz，要留 10 dB 余量，能通吗？不行的话发射功率最小要多少？”为基准，写 12 种说法。覆盖：口语与书面；语序打乱；省略“站”字；用别名（A岸站、B岛站）；问法换成“够不够”“能否满足”等；余量要求放在句尾；反求换一种问法（如“功率得提到多少”）；频率写成 MHz；夹一句无关的话。数字一律用阿拉伯数字（中文数字暂不支持，不写进验收用例）。每条期望：状态、目标 `link_margin`、要求 ≥ 10 dB、反求 `tx_power_dbm`、站点 A 与 B、设备 XX-100、余量与最小发射功率的数值（取 C9–C11 实现复核后的附录 A 数值）、超过额定功率的提示。
> 2. 五个变体（AGENT_LED 附录 A）各写 2 种说法：D 站缺天线高度 → 追问；C 站超出视距 → 拦截、不给损耗值；原文 40 dBm 与设备库 37 dBm 不一致 → 追问用哪个；“港口站”同名 → 让用户选；F 站 → 能通、不反求。
> 3. 硬规则 H1–H4 各至少 2 条：H1 计划用了未审核的卡；H2 越界或超出视距；H3 同一个量的来源冲突；H4 用替身模型给出与结果不符的数字，确认该段被隐藏并注明“说明未通过数字核对”（H4 用替身，不依赖真实模型）。
> 4. 离线等价：6 条参数写全的请求（路径损耗、接收电平、链路余量各 2 条），模型离线时规则算出的正式数值与在线逐位相同。
> 5. 运行脚本 `scripts/eval_m1.py --models <id>`：通过 `TaskService` 逐条创建任务，按期望回答追问或做选择，确认，取结果；逐条输出是否通过、不通过的原因、耗时、模型调用次数，汇总写入 `outputs/eval/`。确定性基线只跑硬规则与离线等价两类。
> **开始条件**：第 1–4 步只写用例与格式测试，可以随时做；第 5 步要等 Claude 完成第 3 周的模型接入（A2、A3 已完成），届时本任务单补一行“可以运行”。
> **完成标准**：用例文件通过格式测试；第一次正式运行的结果原样写入证据，之后的修正另行记录，不覆盖第一次的数字。

### Codex 任务 C14：页面——模型答复、查库来源、假设值与反求

> **目标**：按 [WORKBENCH_UI](../design/WORKBENCH_UI.md) “M1 第 3 周”一节（用户 2026-09-25 确认）实现页面。后端字段已由 Claude 实现。
> **范围**：`planning/web/`、`planning/web_server.py`（只加一个只读接口）、测试、证据。不改 `planning/agents`、`planning/services` 的业务逻辑；发现后端字段不够用，记录下来交给 Claude。
> **步骤**：
> 1. 只读接口 `GET /api/facts`：返回 `FactService` 的站点与设备记录（id、名称、`simulated`、来源标题与定位，站点带位置，设备带参数）和 `describe()` 的版本；安全要求与 `/api/formula-cards` 相同。加 Python 测试。
> 2. 结果区：请核对提示条、答复卡、程序结论小字、余量要求、反求块（含 17 点曲线、要求线、解、额定值提示）、审查意见、逐步说明，逐条按规格。没有模型答复时保持现在的样式。
> 3. 视距外停止的显示。
> 4. 计划卡：新来源标签（含“模拟”）、只限“假设”值的直接修改（走原有“编辑”命令，改后标“手填（原假设 X）”）、“本次假设”、目标行、视距检查行、专业计算 Agent 意见的占位。已识别列表同样换标签。
> 5. 流程图说明文字按规格改。
> 6. 测试与检查：新的显示逻辑写成纯函数并加 Node 测试（标签、答复是否显示、反求文字、视距停止文字、假设值修改后发出的命令内容）。在内置浏览器用三种宽度检查以下场景，截图写入证据：A→B 完成（请核对 + 反求 + 曲线）、A→C 视距外停止、A→F 通过、一个假设值直接改后重新确认。需要模型时用本机 9B；只查看页面时可以用 `tests/test_plan_goal.py` 中的替身办法造数据。
> 7. 回归：Python、Node、`pip check` 全部通过。
> **开始条件**：C12 之后，与 C13 第 1–4 步的先后不限。
> **完成标准**：以上测试与检查通过，证据写入 `docs/codex/evidence/`；页面与规格不符的地方逐条列出。

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
