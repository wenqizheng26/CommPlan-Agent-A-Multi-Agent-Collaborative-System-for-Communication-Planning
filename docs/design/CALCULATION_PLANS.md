# 计算计划：多公式串联、链路预算与反求（设计规格）

状态：构思定稿，未实施。v0.1.0-demo 发布之后的下一阶段主线；[KNOWLEDGE_FACTS](KNOWLEDGE_FACTS.md) 作为它的参数来源接入。
2026-09-25：M1 按 [AGENT_LED](AGENT_LED.md)（在原框架上改）实施，本文继续有效；计划新增的 `requirement`、`solve_if_unmet` 与站点、设备来源见 AGENT_LED §4。
决策来源：用户 2026-09-24 确认——
- 使用场景是多种公式、多种用途，先做链路预算与反求；
- 计算链由模型写计划、程序校验；用户对整份计划确认一次；
- 允许公式卡上的典型默认值，标为“假设”，随计划一并确认；
- 新公式由 RAG 抽取草稿、人工审核后入库。

## 1. 要解决的问题

公式库 `knowledge/formulas.json` 已有 7 张核验卡片（`fspl_ghz`、`received_power`、`link_margin`、`noise_density`、`receiver_threshold`、`thermal_noise`、`doppler_max`），其中前五张的输出名与下游输入名一致，可以串成完整链路预算。但计算流程写死了只用 FSPL（`planning/services/domain_calculation.py` 的 `require(card['id']=='fspl_ghz')`，另有约 11 个文件引用 FSPL 专有参数名），其余卡片只能被检索、不能参与计算。

目标：用户问“余量够不够”“最远能通多远”“发射功率至少多少”时，系统能给出一条可审阅的计算链，确认一次后逐步执行，每一步都可复核。

## 2. 不变量

1. 数值只来自登记卡片的确定性求值；模型只写计划（用哪些卡、怎么连、目标是什么），不写数字。
2. 计划里的每个输入都必须有来源：原文、手工、知识库、上一步输出或卡片假设值；没有来源就追问。
3. 草稿卡片（`status: draft`）永远不进入计划。
4. 模型不可用时仍能完成：程序自带的反向拼链作为后备（见 §5），确定性模式直接使用它。

## 3. 计划格式

```json
{"goal": {"kind": "solve", "evidence": "最远能通多远",
          "unknown": "distance_km",
          "condition": {"quantity": "link_margin_db", "op": ">=", "value": "param:required_margin_db"}},
 "steps": [
   {"id": "s1", "card": "fspl_ghz",        "inputs": {"frequency_ghz": "param:frequency_ghz", "distance_km": "unknown"}},
   {"id": "s2", "card": "received_power",  "inputs": {"path_loss_db": "step:s1", "tx_power_dbm": "param:tx_power_dbm",
                                                        "tx_loss_db": "assume", "...": "..."}},
   {"id": "s3", "card": "noise_density",   "inputs": {"temperature_k": "assume"}},
   {"id": "s4", "card": "receiver_threshold", "inputs": {"noise_density_dbm_hz": "step:s3", "...": "..."}},
   {"id": "s5", "card": "link_margin",     "inputs": {"rx_power_dbm": "step:s2", "rx_threshold_dbm": "step:s4",
                                                        "reserve_db": "assume"}}],
 "rationale": "按接收功率与接收门限求余量，反求余量等于要求值时的距离"}
```

- `goal.kind`：`evaluate`（求某个量）或 `solve`（求一个未知量，使条件量达到阈值）。
- 输入绑定只有五种：`param:<名>`、`knowledge:<事实 id>`、`step:<步骤 id>`、`assume`（取卡片默认值）、`unknown`（仅 solve，且全计划恰好一处）。
- 计划由 `compute_agent` 角色按 JSON Schema 严格输出；逐字证据规则与现有需求解析相同。

## 4. 程序校验（全部通过才展示给用户）

| 检查 | 失败码 |
| --- | --- |
| 结构符合 Schema；步骤数 ≤ 8 | PLAN_SHAPE |
| 卡片存在且为 verified | PLAN_CARD |
| 每张卡的每个输入恰好绑定一次；`step:` 只引用前面的步骤（无环） | PLAN_BINDING |
| 连接两端单位完全一致；名称不同的连接允许，但在计划中高亮提示 | PLAN_UNIT |
| 最后一步输出即目标量（evaluate）或条件量（solve）；没有用不到的步骤 | PLAN_GOAL |
| `assume` 只能用于卡片声明了默认值的参数 | PLAN_ASSUMPTION |
| solve 恰好一个 `unknown`，且该参数有搜索区间（卡片 min/max 或 `search_range`） | PLAN_SOLVE |
| `param:` 缺失的量转为追问，不算失败 | — |

失败处理：把失败码与说明回给模型重写一次；仍失败则用程序后备链，并在计划上标明“模型计划未通过校验，已改用程序生成的计划”，失败原因进入活动记录。

## 5. 程序后备链

从目标量出发，按“卡片输出名 = 所需量”反向查找，唯一路线直接采用；存在多条路线时不猜，列出候选让用户选（模型在线时由模型推荐并说明理由）。它同时是评测基线：C5 评测集增加“计划”用例，比较模型计划与后备链的一致率。

## 6. 假设值

- 卡片参数新增可选 `default`：`{"value": 290, "source": {...}, "note": "未给出噪声温度时按参考温度"}`。只收录有出处的标准参考值或保守取值；设备相关量（增益、功率）不设默认值。
- 计划中单独列出“假设”区，确认计划即确认假设；结果注明“含 N 项假设”，用户改动任何一项假设都需重新确认。

## 7. 执行与反求

- **evaluate**：按步骤顺序求值，每步都做现有的适用范围检查与结果检查；每步的输入、输出都写入报告。
- **solve**：在未知量的搜索区间上对“条件量 − 阈值”做一维求解：
  1. 在区间内取样，确认单调，并确认两端点异号；否则给出“区间内无解”或“非单调，无法唯一反求”，不给数值。
  2. 用二分法求根，收敛到卡片精度。
  3. 按单调方向把等号解释为“最大 / 最小”：余量随距离增大而减小，所以解是“最远距离”。
  4. 复核：把解代回整条链计算残差，并在解的两侧各取一点，确认一侧满足条件、一侧不满足。
- 区间输入（现有的“范围”参数）只允许出现在声明了单调方向的参数上，沿用逐角点求值；其余参数遇到区间时，追问一个确定值。

## 8. 公式草稿入库（给 RAG 负责人）

```python
class FormulaDrafts(Protocol):
    def submit(self, card: dict, evidence: list[Excerpt]) -> str: ...  # 返回草稿 id；卡片 status 必须是 draft
    def list(self) -> list[DraftSummary]: ...
```

- 草稿保存在 `knowledge/drafts/`，不进入检索或计划。
- 审核：用 `scripts/review_formula.py <草稿 id>` 展示卡片、原文摘录，运行 `examples` 并做量纲检查；审核人通过后，卡片以 `verified` 状态写入 `formulas.json`，记录审核人与日期，公式库版本号加一，已确认任务按现有“知识目录已变化”规则处理。
- 要求：必须有至少一个带出处的参考算例；表达式只能使用现有表达式语言（`formula_rag/core.py` 的白名单）；需要迭代或查表的复杂模型（如 ITU-R 雨衰）改写成 Python 工具，由开发者录入，不走草稿。

## 9. 页面

- 参数确认页改为“计划确认”：顶部写明目标，比如“求最远距离，使余量 ≥ 10 dB”；中部用小流程图列出各步骤及每个输入的来源标签（原文 / 手工 / 知识库 / 假设 / 上一步）；底部是假设区；只有一个“确认计划”按钮。
- 结果页逐步展开每一步的数值；solve 另附“条件量 − 未知量”曲线，标出阈值线和解的位置。
- 模型计划被改写或替换时，在计划上用一行说明原因。

## 10. 冻结合同的改动

- 报告新增 `plan`：步骤、绑定、来源 `origin: model | program`、假设列表；计算结果从单值改为逐步输出，另加 `solve` 区（区间、迭代次数、残差、两侧复核）。
- `requirement_validation` 与结果复核从 FSPL 专用改为按计划逐步重算。
- 合同版本号升级；v0.1.0 的报告仍按旧版本读取。

## 11. 分期

| 期 | 内容 | 执行 |
| --- | --- | --- |
| P1 | 计划 Schema、校验器、执行器、程序后备链、evaluate；卡片 `default`；合同 v2；FSPL 专用代码改为通用 | Claude 设计与核心，Codex 补测试与迁移 |
| P2 | solve 与复核 | Claude |
| P3 | 模型写计划、重写一次、回退；评测集增加计划用例 | Claude；评测用例交给 Codex |
| P4 | 计划确认页与逐步结果 | Claude |
| P5 | 草稿入库接口与审核脚本 | 接口由 Claude 设计，实现交给 Codex，数据由 RAG 负责人提供 |
| P6 | 接入知识库事实（KNOWLEDGE_FACTS） | Claude |

## 12. 验收基准

- 数值：完整余量链与手算一致；FSPL 在对数距离上是线性的，因此“最远距离”“最小发射功率”都有闭式解，反求结果与闭式解的误差 ≤ 1e-6（相对）。
- 校验：未知卡片、草稿卡片、环、单位不一致、两个未知量、非单调、区间内无解，各至少一条用例被拦截，并给出正确的失败码。
- 回退：模型离线或计划两次不合格时，程序后备链给出与在线相同的数值。
- 兼容：现有 FSPL 单步任务作为只有一步的计划运行，结果与 v0.1.0 逐位一致。
