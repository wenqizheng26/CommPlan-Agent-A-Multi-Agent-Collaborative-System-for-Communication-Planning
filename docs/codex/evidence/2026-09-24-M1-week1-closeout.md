# M1 第 1 周收尾（2026-09-24）

工作区 `CommPlan-Agent-M1`，分支 `claude/calc-plans`，起点 `6297076`（C7）。Qwen 从主工作区项目内资源启动在 127.0.0.1:18081（`launch.model_command`），`/health` 为 `ok`。

## 发现与修正

| # | 现象 | 原因 | 修正 |
| --- | --- | --- | --- |
| 1 | C7：两条“链路余量缺预算参数”用例，Qwen 三次都不过校验后降级 | 模型把公式卡说明当作 evidence；该句解析出三个目标，在 `target_semantics` 被拒。纠错反馈只有错误码，重试等于盲改 | `formula_rag/model.py`：evidence 在 JSON Schema 中限定为原文分句及其连词两侧的部分（解码约束）；`requirements.py`：`correction_hints` 说明哪一项错、为什么错，以及原文未写时应留空 |
| 2 | 补参问题说可以在“补充与修改”里写“发射功率 30 dBm”，实际只认频率和距离，会被挂成待澄清 | `supplement.py`、`clarification.py` 只处理 `frequency_ghz`、`distance_km` | 链路预算参数逐项出题（按链路顺序），可带标签或只写数值；补充面板一次可写多项；负馈线损耗等越界值以逐项问题改正；替换原文时只保留“标签+数值” |
| 3 | 本机模型模式下补充面板从不合并，包括“频率改为3GHz” | 补充判断提示词没有示例，Qwen 一律回答 `clarify`。主工作区 v0.1.0 候选同样如此（只读运行复现，未修改） | 加入一正一反两个示例；8 条探针（5 条明确、3 条含糊）全部判断正确 |
| 4 | 多轮补充后审查角色 `MODEL_CONTEXT_LIMIT`，退回默认结论 | 审查输入含最近 3 轮的修改前后原文（与 `request` 重复）及来源内部编号，估算约 4270 token | `review_context` 只保留轮次、类型和用户原话；参数来源只保留类型与原文摘录；新增测试断言多轮后审查输入 ≤ 4096 |

## 自动测试

Python 269 tests OK（1 skip）；Node 36 pass；`pip check` 无问题。新增测试覆盖：逐项回答（带标签与裸数值）、一次补充多项、修改已有预算值、越界值改正、错误回答被拒、审查输入上限、evidence 候选与纠错提示。

## 真实 Qwen 评测

命令：`python -B -X utf8 scripts/eval_models.py --models qwen3-4b-q4 qwen3-4b-q4-fast-fail`，36 条；报告在被忽略的 `outputs/eval/2026-09-24T060102Z-*.json`。

| 档案 | 六类评分 | 结构化成功 / 尝试 | 降级案例 |
| --- | --- | --- | --- |
| C7 标准 / 快速失败 | 各 36/36 | 29/33 | 4 |
| 本次 标准 / 快速失败 | 各 36/36 | 33/33 | 0 |

与 C7 逐条比较（状态、各项检查、非模型诊断码、健康状态、失败尝试次数）：两档均为 **变差 0 条、变好 7 条、不变 29 条**。变好的是 `missing_condition`（3→1 次失败尝试）、`missing_target`（3→2）、`link_margin_missing_budget`（3→0）、`chain_margin_complete`（2→0）、`chain_margin_missing_budget`（3→0）、`chain_margin_interval`（1→0）、`chain_margin_negative_loss`（1→0）。原有 FSPL 用例全部在“不变”之列。评测后只改了补充判断与审查输入，二者不在需求评测路径内。

## 真实模型全流程

- 服务层（`TaskService`，本机模型模式）：单步 FSPL `COMPLETED`，98.42059991327963 dB；链路余量经一次逐项回答、两次补充（补齐门限与余量、发射功率改为 33 dBm）后 `COMPLETED`，20.57940008672037 dB。两者的需求、计算、审查角色均为 `llm`，审查无诊断。
- 内置浏览器（本机模型模式，Qwen3 4B 标准）：任务 `f076d3a9-dd6e-44e8-8e00-34052d8baa2f`，缺 7 项 → 问题面板答 5 项 → 补充面板补 2 项（`llm_grounded`）→ 勾选核对 → 确认并计算。三步 118.42 dB、−72.42 dBm、17.58 dB，校验 9/9，三个模型角色均为 `llm`，控制台无错误。**这是内置浏览器检查，不是目标 Chrome 验收。**

## 未改动

主工作区 `CommPlan-Agent`（v0.1.0 候选）未修改。第 3 项在 v0.1.0 中同样存在，是否在发布前处理由用户与独立审查决定。
