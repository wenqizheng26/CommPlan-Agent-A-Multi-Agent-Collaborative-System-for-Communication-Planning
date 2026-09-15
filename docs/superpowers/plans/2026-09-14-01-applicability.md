# 项目 1：适用范围与结果解释实施计划

2026-09-15 执行前说明：本文件继续作为 P1 的详细草案，尚未执行。开工时先按[工程需求基线 R1](../../requirements.md)核对科学边界与验收；该基线已确定后续必须采用 LangGraph 与多 Agent，但 P1 仍只处理适用性和结果解释，不借此提前接入全部后续模块。

> 面向执行者：使用 executing-plans 在当前任务逐项实现。当前仅保存计划，所有实施步骤尚未执行。本项目完成后再进入公式版本与精度调整，不同时修改全部模块。

**目标：** 不让明显不适用或定义不清的公式输出无条件“计算完成”，并明确解释用户海上例题的模型缺口。

**架构：** 保留确定性计算核心和现有查询接口。新增独立的适用性/结果解释模块，由流水线在依赖计算和返回结果时调用；不让模型生成适用性判定代码。暂不改 FSPL 常量和显示位数，以隔离行为变化。

**技术栈：** 现有 Python 标准库、unittest、JSON。检查不加载 BGE、Qwen，不操作浏览器。

**工作目录：** `E:\codex\项目\信号与AI\signal-formula-rag`。

## 1. 文件与职责

| 文件 | 操作及职责 |
| --- | --- |
| `formula_rag/applicability.py` | 新增：公式适用性问题码、参数组合约束、功率和余量解释；纯函数 |
| `formula_rag/pipeline.py` | 接入适用性检查，阻断不适用节点及其依赖；保留独立可算结果 |
| `tests/test_scientific_scope.py` | 新增：下列回归用例与预期状态 |
| `tests/test_pipeline.py`、`tests/test_pasted_input.py` | 调整真正受语义变化影响的预期；保留明确缺项断言 |
| `reports/` | 新增本项目证据，不覆盖旧真实 RAG 报告 |

建议纯函数接口 `scope_issues(formula_id, values, request)` 返回含 `code`、`severity`、`message`、`fields` 的列表；`describe_result(formula_id, value)` 返回语义标签。请求/返回结构用字典，与现有工程一致。

## 2. 必须满足的行为

1. 用户海上例题：不给实际传播数值；提示目前可用的是自由空间基准，实际模型未覆盖，用户需先明确计算范围。保留已识别频率和距离，不说“缺频率或距离”。
2. 自由空间 f=1 GHz、d=0.000001 km：输出节点 `not_applicable`，正式结果无 `value`。保留负值的算术诊断可放独立诊断记录，不能展示为有效损耗。
3. 使用 d/λ 组合检查，不设置脱离频率的固定最小距离。d<λ/(4π) 的明显异常必须拒算；通过此检查仍须提示远场条件未必完整验证，不能写成充分条件。
4. 接收功率或噪声功率为负 dBm：正常计算，不判输入错误；注明相对于 1 mW 的功率电平。
5. 余量为负：数值仍保留；新增 `assessment.code='below_threshold'`、差额说明。零为 `at_threshold`，正值为 `above_threshold`；判断使用未作显示舍入的数值，仅表示所填预算条件下的门限关系。
6. 未确认噪声参考关系时，不输出无条件接收门限。例如 T=100 K 配 NF=3 dB，必须追问是否为标准 290 K 定义的 NF，以及输入温度/谱密度是否包含接收机噪声。第一项先阻断歧义；项目 2 再加入已审核的完整噪声路线。
7. 输入中只出现 −174 dBm/Hz，不得据此自动证明 NF 参考定义或源温度正确。新增确认字段应从用户显式说明/结构化输入取得，不能来自模型推断。若旧例题缺确认信息，将其标为待确认，而不是为了保留旧“通过”状态跳过检查。

## 3. 按顺序实施

- [ ] 保存修改前文件哈希，以 `reports/scientific_audit_2026-09-14.json` 中的已复现缺口作为初始证据。
- [ ] 创建 `tests/test_scientific_scope.py`，先加入以下最小回归用例：

```python
import unittest
from pathlib import Path
from formula_rag.pipeline import Engine

class ScientificScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = Engine(Path(__file__).resolve().parents[1], dense=False, llm=False)

    def test_sea_case_explains_model_coverage(self):
        r = self.engine.query('岸站到海上平台，频率4.5GHz，距离30公里，求传输损耗')
        self.assertEqual(r['request']['parameters']['distance_km'], 30)
        self.assertFalse(any(c.get('status') == 'ok' for c in r['calculations']))
        self.assertTrue(any('模型' in q and '当前' in q for q in r['questions']))

    def test_nearfield_not_published_as_valid_loss(self):
        r = self.engine.query('按自由空间基准，频率1GHz，距离0.000001km，求传输损耗')
        c = next(c for c in r['calculations'] if c['id'] == 'fspl_ghz')
        self.assertEqual(c['status'], 'not_applicable')
        self.assertNotIn('value', c)

    def test_negative_dbm_remains_a_valid_power_level(self):
        r = self.engine.query('温度290K，带宽1MHz，求热噪声功率')
        c = next(c for c in r['calculations'] if c['id'] == 'thermal_noise')
        self.assertEqual(c['status'], 'ok')
        self.assertAlmostEqual(c['value'], -113.97518719422808, places=8)

    def test_negative_margin_is_not_link_success(self):
        r = self.engine.query('接收功率-70dBm，接收门限-62dBm，预留余量0dB，求链路余量')
        c = next(c for c in r['calculations'] if c['id'] == 'link_margin')
        self.assertEqual(c['value'], -8)
        self.assertEqual(c['assessment']['code'], 'below_threshold')

    def test_noise_reference_is_not_silently_assumed(self):
        r = self.engine.query('温度100K，比特率1000000bit/s，Eb/N0 10dB，噪声系数3dB，工程损失0dB，求接收门限')
        c = next(c for c in r['calculations'] if c['id'] == 'receiver_threshold')
        self.assertNotEqual(c['status'], 'ok')
        self.assertNotIn('value', c)
        self.assertTrue(any('参考' in q for q in r['questions']))
```

- [ ] 运行最小测试并记录预期失败，负 dBm 控制组应通过：

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 -m unittest discover -s tests -p test_scientific_scope.py -v
```

- [ ] 实现独立的组合检查与结果解释。远场异常检查采用同单位关系：`wavelength_m = 299792458.0 / (frequency_ghz * 1e9)`，`distance_m = distance_km * 1000`，在已有有限且正数域检查后比较 `distance_m < wavelength_m / (4 * math.pi)`。这只是明显异常门槛，不自动设置“远场已确认”。
- [ ] 在流水线计算前核验来源/参考关系，计算后组装语义状态。若上游公式不适用，下游接收电平、余量不得得到数值；已输入的独立有效量可继续计算。
- [ ] 用明确问题码解释缺口：`model_coverage_gap`、`free_space_nearfield`、`noise_reference_unconfirmed`。面向用户展示完整中文原因及可采取的下一步，不能只显示问题码。
- [ ] 加入对称边界用例：同一 d/λ 比在不同频率应同样判定；零/负距离仍拒绝；余量 −0.004 dB、0、+0.004 dB 分别判负、零、正；确认结构化标准噪声路线与未确认输入有不同状态。
- [ ] 重跑最小测试，再运行相关解析/依赖测试及整套无模型测试：

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 -m unittest discover -s tests -v
```

- [ ] 更新 `HANDOVER.md` 的适用范围，明确新旧行为变化；保存项目 1 报告中的版本、问题码、完整计算节点和测试结果。只报告实跑结果，不沿用“23 项真实 RAG 全通过”作为本次新版本结论。
- [ ] 人工检查本项目差异，确认未修改网页布局、FSPL 常量、显示位数、历史 JSON 和用户参考表。完成本项目后再进入项目 2。

## 4. 项目边界

本项目不新增海面反射、两径、散射或多普勒损耗模型，不实现完整远场场分布解算，不运行真实模型评估，不操作屏幕。噪声参考未确认时的暂缓计算属于明确能力边界，不能通过默认填零或 290 K 绕过。

当前仓库尚无提交且未配置作者身份。保留文件级变更与报告；不虚构作者、不修改用户 Git 全局配置来完成提交步骤。
