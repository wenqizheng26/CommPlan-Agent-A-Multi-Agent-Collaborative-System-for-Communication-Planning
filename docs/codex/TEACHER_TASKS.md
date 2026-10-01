# Codex 任务单：老师的三条验收案例（2026-10-01）

背景与决定见 [TEACHER_CASES](../design/TEACHER_CASES.md)。本单只交出两项：T1 冻结验收用例，T2 工具与数据。接入需求、计划、提示词和页面流程由 Claude 做。T3（报告视图、评测脚本、浏览器与断网验收）等 Claude 做完阶段 2–4 后另派。

## 环境与约定

- **工作区**：`CommPlan-Agent-M1-codex`。
  - 开始前执行：`git switch -c codex/m1-teacher codex/m1-week4-tasks`。
  - 第 4 周的 7 个提交由 Claude 同期审核，期间不要修改 `codex/m1-week4-tasks`。
- **本单位置**：在 `claude/calc-plans` 上，路径 `E:/codex/项目/信号与AI/CommPlan-Agent-M1/docs/codex/TEACHER_TASKS.md`，也可以用 `git show claude/calc-plans:docs/codex/TEACHER_TASKS.md` 查看。不要复制进你的分支。
- **Python**：`E:/codex/项目/信号与AI/CommPlan-Agent/.venv/Scripts/python.exe`。
- **约定**：
  - 不推送、不合并、不开 PR。
  - 每个任务单独提交，先做 T1，再做 T2。
  - 证据写进 `docs/codex/evidence/`。
  - 每个任务做完，在你分支的 `docs/codex/NEXT_ACTION.md` 顶部加一行状态，写明提交号和测试数。
  - 下载或安装任何东西前，先问用户，说明名称、来源和大小。
  - 环境里没有 `jsonschema`，不要安装；T2 自己写校验器。
  - 端口上已在运行的模型和工作台照常使用，不要停掉。
  - 遇到本单没写到、又必须改需求、计划或审查逻辑的情况，停下报告。

## T1：冻结验收用例

> **目标**：在 Claude 接入之前，把老师的三条案例和变体连同期望值一起冻结。这样 Claude 接入时，不能反过来按用例调整实现。
>
> **范围**：只新增 `tests/eval/teacher_cases.jsonl`、`tests/test_teacher_cases_format.py` 和证据，不改其他文件。
>
> **每行格式**：
>
> ```json
> {"id": "teacher_01", "category": "teacher", "text": "……",
>  "expected": {
>    "first_stop": "AWAITING_CONFIRMATION",
>    "parsed": {"distance_km": 10, "frequency_mhz": 5800, "tx_power_dbm": 20,
>               "tx_gain_dbi": 18, "rx_gain_dbi": 18, "modulations": ["QPSK"]},
>    "nodes": ["A", "B"],
>    "results": [{"modulation": "QPSK", "rx_sensitivity_dbm": -100, "path_loss_db": 127.7085598713,
>                 "rx_power_dbm": -71.7085598713, "link_margin_db": 28.2914401287, "meets": true}],
>    "tolerance": 1e-6}}
> ```
>
> 字段说明：
>
> | 字段 | 说明 |
> | --- | --- |
> | `category` | `teacher`、`variant`、`missing`、`clarify`、`english` 之一 |
> | `first_stop` | 第一次停下时的状态：参数齐全为 `AWAITING_CONFIRMATION`（等用户确认计划），需要补充为 `AWAITING_INPUT` |
> | `parsed` | 只写原文里明确给出的字段。名称只能用 `distance_km`、`frequency_mhz`、`tx_power_dbm`、`tx_gain_dbi`、`rx_gain_dbi`、`modulations`（列表，按原文顺序）。单位一律换算成 km、MHz、dBm、dBi |
> | `nodes` | 可选。两端的标签，评测时去掉空格后互相包含即算对 |
> | `service` | 可选。业务，如 `"视频"` |
> | `missing` | 仅 `missing` 类。必须列出的缺失项，按这个顺序：`distance_km`、`frequency_mhz`、`tx_power_dbm`、`tx_gain_dbi`、`rx_gain_dbi`、`modulation` |
> | `ask` | 仅 `clarify` 类。系统必须就哪些字段反问 |
> | `after_defaults` | 仅 `missing` 类。用户一键采用建议值以后的完整输入，格式同 `parsed`。默认值：距离 10 km、发射功率 20 dBm、两端增益 18 dBi、调制 QPSK |
> | `results` | 每种调制一条，顺序同 `modulations`。`missing` 类按 `after_defaults` 计算；`clarify` 类不写 |
> | `margin_diff_db`、`recommend` | 仅两种及以上调制时写：最大余量减最小余量；余量最大的调制 |
>
> **计算口径**（按老师给的式子，不用项目里的卡）：
> - FSPL = 32.44 + 20·log10(d_km) + 20·log10(f_MHz)；
> - Prx = Ptx + Gtx + Grx − FSPL，不计任何损耗；
> - 余量 = Prx − 灵敏度；
> - 灵敏度：QPSK −100、16QAM −95、64QAM −90 dBm；
> - `meets` = 余量 ≥ 0。
>
> 数值保留至少 10 位有效数字。
>
> **用例清单**：共 20 条，问法由你来写。
>
> | 类别 | 条数 | 内容 |
> | --- | --- | --- |
> | `teacher` | 3 | TEACHER_CASES 里的三条原文，逐字照抄 |
> | `variant` | 8 | 案例一 4 条：口语短句；单位换写（10000 米、5800 MHz）；写成“5.8G”并打乱参数顺序；“两端天线都是 18dBi”这种合写。案例三 3 条：“16QAM 和 QPSK 哪个余量大”；加上 64QAM 共三种；“对比一下”的问法。干扰项 1 条：案例一另加“信道带宽 20MHz”，频率必须仍是 5800 MHz |
> | `missing` | 5 | 案例二换说法 1 条、换地名 1 条（两条都只给频率）；只缺调制 1 条；只缺发射功率 1 条；缺距离和两个增益 1 条 |
> | `clarify` | 2 | 表里没有的调制（如 8PSK），`ask` 为 `["modulation"]`；同一频率给出两个互相矛盾的值，`ask` 为 `["frequency_mhz"]` |
> | `english` | 2 | 案例一、案例三的英文问法 |
>
> **测试 `tests/test_teacher_cases_format.py`**：不 import 项目代码。
> 1. id 不重复；各类别条数等于上表。
> 2. 三条 `teacher` 的 `text` 与本单写死的三句原文逐字相等。
> 3. `parsed`、`after_defaults` 只出现上面规定的字段名；`missing` 按规定顺序。
> 4. 在测试里按计算口径独立重算每条 `results`，与文件中的值相差不超过 1e-9；`meets`、`margin_diff_db`、`recommend` 也要一致。
> 5. 三条原文的结果四舍五入到 2 位小数后，必须等于老师给的值：
>    - 案例一：127.71、−71.71、28.29；
>    - 案例三：118.11、−77.11、22.89、17.89。
>
> **步骤**：
> 1. 写用例和测试，Python 与 Node 全量回归。
> 2. 用例和测试单独提交。之后不再修改问法或期望值。如果发现错误，另起一个提交修正，并在证据里说明原因。
>
> **完成标准**：
> - 测试通过，全量回归通过。
> - 证据 `docs/codex/evidence/2026-10-0X-T1-cases.md` 写明三项：用例清单（id、类别、一句话说明）、提交号、测试数。

## T2：调制灵敏度表、典型值表、`fspl_mhz` 卡与工具注册表

> **目标**：备齐老师要求的统一工具 `calc_link_margin`。它从工具注册表发现和调用，输入输出受 JSON Schema 约束。这次不接入需求和计划，由 Claude 另做。
>
> **范围**：
> - 可改：
>   - 新文件：`knowledge/facts/modulations.json`、`knowledge/facts/typical_values.json`、`knowledge/tools.json`、`formula_rag/schema.py`、`formula_rag/registry.py`。
>   - `knowledge/formulas.json`：只在末尾追加 `fspl_mhz`，不改已有卡。
>   - `planning/knowledge/facts.py`：加载两张新表，增加调制查询。
>   - `planning/services/reference_models.py`：加 `fspl_mhz` 的独立实现。
>   - `planning/web_server.py`：只加 `GET /api/tools`。
>   - 资料页：`planning/web/library.mjs` 及对应的 `i18n-en.mjs`，只加调制表的显示。
>   - 测试、证据。
> - 不改：
>   - `planning/services/plans.py` 的 TARGETS、SUPPORTED 等清单；
>   - 需求、计划、审查各 Agent 及其提示词；
>   - 已有的卡；
>   - `formula_rag/core.py` 中 `evaluate` 的行为；
>   - `FactService.records()` 的返回内容（它用于在消息里匹配名称，调制不能进入这里）。
>
> **1. 调制灵敏度表 `knowledge/facts/modulations.json`**：
> - 3 条记录，字段与设备记录相同：`id`、`type`（`"modulation"`）、`names`、`rx_sensitivity_dbm`、`simulated: true`、`status: "verified"`、`note`、`source`。
>
>   | id | names | rx_sensitivity_dbm |
>   | --- | --- | --- |
>   | `modulation:qpsk` | `QPSK` | −100 |
>   | `modulation:16qam` | `16QAM`、`16-QAM` | −95 |
>   | `modulation:64qam` | `64QAM`、`64-QAM` | −90 |
>
> - `note` 写“模拟参数，可配置”。
> - `source` 指向 `docs/design/TEACHER_CASES.md`，locator 写“决定 · 调制灵敏度”。T2 的提交要带上这个文件：从 `claude/calc-plans` 取过来，原样不改。
> - 在 `FactService` 里：
>   - 加载并校验这张表，规则同设备：id 唯一，names 非空，灵敏度是有限数，source 文件存在。
>   - 增加 `find_modulation(name)`，返回结构与 `find_device` 相同。比较前统一转大写，并去掉空格、`-` 和 `_`，所以“16 qam”也能查到。
>   - `public_records()` 加入调制行，`describe()` 加 `modulation_count`。
>
> **2. 典型值表 `knowledge/facts/typical_values.json`**：供缺项补全使用。
> - 5 条，每条写 `field`、`unit`、`default`、`candidates`、`note`。
>
>   | field | unit | default | candidates |
>   | --- | --- | --- | --- |
>   | `distance_km` | km | 10 | 只有默认值 |
>   | `tx_power_dbm` | dBm | 20 | 17、20、23、27、30 |
>   | `tx_gain_dbi` | dBi | 18 | 12、18、24 |
>   | `rx_gain_dbi` | dBi | 18 | 12、18、24 |
>   | `modulation` | — | QPSK | QPSK、16QAM、64QAM |
>
> - `note` 写“模拟参数，可配置；默认补全，需用户确认”。
> - 校验规则：
>   - `default` 必须在 `candidates` 里；
>   - 调制的取值必须在调制表里；
>   - 数值必须满足 `calc_link_margin` 输入 schema 的约束。
> - `FactService.typical_values()` 返回深拷贝；`/api/facts` 的返回加 `typical_values` 键。
>
> **3. 公式卡 `fspl_mhz`**：追加到 `knowledge/formulas.json` 末尾，字段写法同 `fspl_ghz`。
> - 表达式：`32.44 + 20*log10(frequency_mhz) + 20*log10(distance_km)`。
> - 输出：`path_loss_db`，单位 dB。
> - 参数：`frequency_mhz`（MHz，>0）；`distance_km`（km，>0，`search_range` 同 `fspl_ghz`）。
> - `applicability.requires` 写 `["free_space"]`。
> - notes 写两点：
>   - 32.44 是 20·log10(4π·10⁹/c) 取两位小数，精确值为 32.4418；
>   - 与 `fspl_ghz` 的 92.4 相比，结果大约大 0.04 dB。单独算 FSPL 时仍用 `fspl_ghz`，以保持 v0.1.0 的结果。
> - sources：物理出处写 ITU-R P.525-5，写法同 `fspl_ghz`；derivation 注明常数取自老师的验收说明（TEACHER_CASES）。
> - 算例：(10 km, 5800 MHz) → 127.7085598713；(8 km, 2400 MHz) → 118.1060245741。
> - 在 `reference_models.py` 的 REFERENCE 里加 `fspl_mhz`，写法照 `fspl_ghz`。
>
> **4. JSON Schema 校验器 `formula_rag/schema.py`**：
> - `validate(instance, schema)` 返回错误列表，为空表示通过。
> - 支持的关键字：`type`（object、number、integer、string、boolean、array）、`properties`、`required`、`additionalProperties`（只支持 false）、`enum`、`minimum`、`maximum`、`exclusiveMinimum`、`exclusiveMaximum`、`oneOf`、`items`、`title`、`description`。
>   - number 不接受 bool、NaN 和无穷大。
>   - `check_schema(schema)` 遇到不支持的关键字就报错，不能静默忽略。
> - 卡片 schema 由参数自动生成：
>   - `card_input_schema(card)`：每个参数为 number，`min`、`exclusive_min`、`max` 换成对应关键字；全部 required；`additionalProperties: false`；description 带上单位。
>   - `card_output_schema(card)`：`{value: number, unit: 枚举 [该卡单位]}`。
>
> **5. 工具注册表**：`knowledge/tools.json` 加 `formula_rag/registry.py`。
> - **`knowledge/tools.json`** 只登记 `calc_link_margin`，包含：
>   - `id`、`title`（“链路余量计算”）、`description`；
>   - `steps`：`["fspl_mhz", "received_power", "link_margin"]`，供页面显示；
>   - `assumptions`：写明馈线损耗、额外损耗、预留量都按 0 计，“只算自由空间，不计遮挡与损耗”；
>   - `input_schema`、`output_schema`。
> - **输入 schema**：
>   - required：`distance_km`（>0）、`frequency_mhz`（>0）、`tx_power_dbm`、`tx_gain_dbi`、`rx_gain_dbi`；
>   - 另外 `modulation`（string）与 `rx_sensitivity_dbm`（number）二选一，用 `oneOf` 表达；
>   - 可选 `required_margin_db`（≥0，默认 0）；
>   - `additionalProperties: false`；
>   - `modulation` 的取值在文件里写成 `"x-enum-from": "modulations"`，加载时换成调制表各条的第一个名字组成的 `enum`。对外公开的 schema 只能含标准关键字。
> - **输出 schema**：
>   - 必有：`path_loss_db`、`rx_power_dbm`、`rx_sensitivity_dbm`、`sensitivity_source`（`modulation_table` 或 `argument`）、`link_margin_db`、`required_margin_db`、`meets`（boolean）；
>   - 来自调制表时，另有 `modulation` 和 `simulated: true`；
>   - `additionalProperties: false`。
> - **`registry.py`**：
>   - `load_tools(root)`：每张 verified 卡是一个 `card` 工具，用自动生成的 schema；`tools.json` 里的条目是 `composite` 工具。每个工具带 `content_hash`，卡工具的 hash 与 `/api/formula-cards` 相同。加载时用 `check_schema` 检查全部 schema。
>   - `call_tool(root, tool_id, arguments)` 返回 `{tool, arguments, status, errors, result, steps}`，`status` 取 `ok`、`invalid_arguments`、`failed` 之一。
>     1. 先按输入 schema 校验参数，不通过返回 `invalid_arguments`。
>     2. 卡工具调用 `core.evaluate`，`result` 为 `{value, unit}`。
>     3. `calc_link_margin` 的执行：
>        - 有 `modulation` 时，用 `find_modulation` 查灵敏度；
>        - 再依次用 `core.evaluate` 计算三张卡：`fspl_mhz`；`received_power`（三项损耗显式传 0）；`link_margin`（`rx_threshold_dbm` 取灵敏度，`reserve_db` 传 0）；
>        - `meets` = 余量 ≥ `required_margin_db`；
>        - `steps` 每步记录 `{card, inputs, value, unit, content_hash}`。
>     4. 最后按输出 schema 校验结果。不通过返回 `failed`，这是程序错误，必须有测试覆盖。
>   - 只按 id 调用已登记的工具，不涉及模型。同样的输入必须得到同样的输出。
> - **`GET /api/tools`** 返回 `{tools: [{id, kind, title, description, input_schema, output_schema, content_hash, steps?, assumptions?}]}`。
>
> **6. 资料页**：
> - 在设备、站点表格之后加一张只读的“调制灵敏度”表，列为调制方式和灵敏度，表头旁标“模拟参数，可配置”。
> - 英文界面下整句能译出，补进 `i18n-en.mjs`。
>
> **测试**：Python 写在 `tests/test_teacher_tools.py`，Node 加在 `tests/planning_library.test.mjs`。
> - **调制表**：
>   - 三条都能查到；“16 qam”“16-QAM”“qpsk”也能查到；8PSK 查不到；
>   - 重复 id 或灵敏度不是数时，加载失败；
>   - `records()` 里没有调制记录。
> - **典型值表**：违反任何一条校验规则时，加载失败。
> - **schema**：
>   - 每个支持的关键字都有通过和不通过的用例；
>   - 遇到不支持的关键字时，`check_schema` 报错；
>   - 对每张 verified 卡，用边界值（等于、略低于、略高于 min 和 exclusive_min，缺参数，多一个参数，bool，NaN）比较 schema 与 `evaluate` 的判定：schema 判为不通过的，`evaluate` 也必须判为不通过；`evaluate` 判为不通过而 schema 判为通过的，只允许是计算域错误（errors 以 `calculation:` 开头）。
> - **`calc_link_margin`**：
>   - 老师的两组数据分别用 QPSK、16QAM、64QAM 计算，与测试里独立写的式子相差不超过 1e-9；四舍五入到 2 位小数后等于 TEACHER_CASES 里的值；
>   - 同时传 modulation 和 rx_sensitivity，或者两个都不传 → `invalid_arguments`；距离为 0、多一个参数、调制不在表里 → `invalid_arguments`；
>   - `required_margin_db` 会改变 `meets`；
>   - 输出不符合 schema 时返回 `failed`（用替身制造）；
>   - 每步的 `content_hash` 与 `/api/formula-cards` 一致。
> - **`/api/tools`**：返回中包含 `calc_link_margin` 和全部 verified 卡；公开的 schema 里没有 `x-enum-from`。
> - **回归**：照 W4-1 的做法，用 `tests/eval/m1_cases.jsonl` 里有 `text` 的用例，比较加 `fspl_mhz` 前后确定性需求 Agent 的结果。最终目标、计算链和状态必须完全相同；检索候选的变化列进证据。有任何不同就停下报告，不改需求代码。
> - Python、Node 全量通过。现有测试只允许改“卡片数量”“事实数量”一类的断言；其他断言失败时，停下报告。
>
> **完成标准**：
> - 以上测试通过。
> - 证据 `docs/codex/evidence/2026-10-0X-T2-tools.md` 写明四项：`/api/tools` 中 `calc_link_margin` 的 schema 原文；老师两组数据的计算结果；回归候选变化列表；测试数。
