# 通信公式本地 RAG

## 工程设计入口

最新需求见 [工程需求基线 R1](docs/requirements.md)，配套 [多 Agent + LangGraph 目标流程 v1.4](docs/diagrams/2026-09-15/通信筹划协同流程_v1.4.md)。已确定：自然语言自动填表、核对确认后计算、一个总控与三个专业 Agent、在用户确认范围内生成参数组合、并列比较方案并由用户选择。

2026-09-15 已保存非多 Agent 旧版，完成 P1 适用性与结果解释修复。**LangGraph、多 Agent 和先解析后确认表单仍待 P4/P5 实现**。当前程序继续使用本地公式 RAG；P2 的公式基本式与噪声路线、P3 的显示精度尚未实施。备份入口见 [BACKUP.md](BACKUP.md)，P1 规则见 [P1 说明](docs/p1-applicability.md)。当前状态、历史证据与实施顺序见 [HANDOVER](HANDOVER.md)、[科学审查](docs/superpowers/specs/2026-09-14-scientific-review-design.md)和[需求基线](docs/requirements.md)。

## 现有程序

输入中文通信环境和已知参数，检索公式及出处，再由程序检查条件并计算。现有知识库包含自由空间损耗、最大多普勒频移、热噪声功率、热噪声谱密度、接收门限、接收电平和链路余量 7 条公式。

[现有程序与目标流程](docs/system-flow.md) · [2026-09-14 界面修改记录](docs/2026-09-14-interface-refinement.md)

## 启动

在此电脑上双击 `启动.cmd`。首次加载模型约需几十秒，随后打开 http://127.0.0.1:18080 。模型和依赖已经保存在项目内，启动时不下载。

PowerShell 也可执行：

```powershell
Set-Location -LiteralPath 'E:\codex\项目\信号与AI\signal-formula-rag'
& '.\.venv\Scripts\python.exe' -X utf8 launch.py
```

应用仅监听本机。模型服务端口为 18081，网页端口为 18080。重复启动会检查并复用本应用服务。若显卡设备发生变化，运行 `runtime\llama.cpp-b10950\llama-server.exe --list-devices` 核对 `runtime_config.json` 中的 device；CPU 备用入口是 `launch.py --cpu`。已运行的模型服务不会因再次启动自动切换设备。

## 输入示例

`按自由空间基准计算，频率4.5GHz，距离200米，求传输损耗。`

程序结果为 `91.48485018878651 dB`，页面显示 `91.48485019 dB`，采用 ITU-R P.525-5 的舍入常数 92.4。返回 JSON 保留未按展示精度舍入的双精度值、公式版本、输入和来源。

`岸站到海上平台，频率4.5GHz，距离30公里，求传输损耗。`

系统应要求明确传播模型条件。不会因为频率和距离齐全就把自由空间公式当成实际海上传播损耗。

`温度290K，噪声带宽1MHz，求热噪声功率。`

温度和噪声带宽都必须给出。比特率不会自动当作噪声带宽。

描述可自由输入，但数值解析采用可核验的数量与单位绑定，首版支持常见中文参数名称、阿拉伯数字和 GHz/MHz/Hz、公里/米、W/dBm、dBi/dB 等单位。复杂复合条件、多链路、多候选值或未覆盖的措辞需要通过页面补充参数、选择计算目标或改写。页面会显示实际解析的参数及原文，便于核对。

支持按行粘贴 `工作频率（GHz）4.5`、`发射信号电平（dBm）40` 这类“单位在前”的输入。在“计算”之后分行列出多个待求量，会分别计算。缺参数、单位不明或缺适用模型时，提示用户补充，不使用参考表中的默认值。

完整链路示例见 `examples/complete_budget.txt`。它明确确认标准 290 K 噪声路线，并写出噪声谱密度 -174 dBm/Hz、Eb/N0 的 dB 单位、dBi 增益和损耗。算得路径损耗 91.48485019 dB、接收电平 -51.48485019 dBm、门限 -62 dBm、余量 10.51514981 dB。这些输入仅用于示例，不会预填到其他查询。

计算目标和传播条件默认自动识别，手动覆盖收在“修正识别”；参数名称精简，悬停 ⓘ 查看定义。结果中的公式由本地 KaTeX 排版，点击“查看定义与来源”自动展开下方公式集合、定位并高亮；“返回结果”保留当前输入和结果。

点击“保存结果 JSON”由本地服务把该次程序结果写入 `outputs/` 并显示绝对路径。浏览器不能提交新的数值或文件路径，保存内容来自服务端已有结果。应用重启或记录超过最近64条后，需要重新计算才能保存。

## 数值如何避免模型改写

1. BGE 与词项检索查找候选公式；Qwen 接收资料，返回公式 ID、目标/条件判断及用户原文证据。
2. 程序核对计算目标、参数、单位、定义域和已登记的适用条件。模型建议不具有修改输入值、准入状态或计算结果的权限。
3. 公式表达式用白名单 AST 求值，不执行模型生成代码。
4. 页面直接渲染计算结果 JSON，模型生成文本不进入结果数值。不能明确识别目标时先让用户明确目标。

程序算术正确不能证明物理模型对任意环境正确。知识库未支持的环境会要求补充模型或明确基准；不会自动给出可靠度、现场通信成功率或未经验证的传播损耗。

## 新增公式

复制 `examples/new_formula.json` 编写一个公式卡，包含唯一 ID、版本、表达式、输入输出单位、适用条件、来源和独立数值样例。

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 scripts/import_formula.py add examples/new_formula.json
```

无论导入文件写什么状态，导入后都是 `draft`。审核人核对物理条件、来源和样例后，执行下面的命令；命令本身会进一步检查结构与数值样例：

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 scripts/import_formula.py approve vacuum_wavelength --reviewer '实际审核人姓名'
```

上述命令中的审核人应替换为实际审核者，不能把“测试通过”等同于物理审核。独立样例应来自标准、手册或人工复算，避免用待审核公式自身产生期望值。

下一次查询会检查知识库哈希并自动重建本地索引，无需重新训练模型；刷新网页可看到新增的计算目标和输入参数。新增参数初期可通过页面的规范单位输入框填写。新增复杂的条件规则或依赖链需要扩展程序并添加测试，单靠写 JSON 不会自动产生新的环境判断能力。

## 原始 Excel

原件未修改。副本位于 `knowledge/sources/链路预算-传输.xls`，审计在 `reports/workbook_audit.json`。按照用户要求，表格只用于开发复核：不进入运行时检索、不补参数、不出现在页面公式来源中，原表 API 与页面入口已移除。开发时仍可用下面的命令重新提取并独立复算 16 个公式：

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 scripts/inspect_workbook.py
```

表内 C11/D11 的多普勒损耗公式缺少物理适用依据，保留在原表复算中，未进入通用已审核公式。表名里的“可靠度”不表示原表已有可靠度计算。

## 验证

2026-09-14 的历史检查和浏览器核验见 `reports/final_checks.json`、`reports/acceptance.json`、`reports/browser_qa.json`。23 个案例为预设断言通过，包含完整计算、部分结果、追问和拒算；不能解释为 23 题全部完整算通。它们也不是新版多 Agent 的验收证据。这些历史报告只保留本机，未上传 GitHub；P1 无模型验证见 [阶段报告](reports/stages/p1-applicability.json)。最新状态见 `HANDOVER.md`。

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 -m unittest discover -s tests -v
& '.\.venv\Scripts\python.exe' -X utf8 scripts/runtime_smoke.py
& '.\.venv\Scripts\python.exe' -X utf8 scripts/evaluate.py
```

最后两项需要本地模型服务已启动。`evaluate.py` 在 Python 审计钩子中禁止非回环网络连接和外部 DNS，并调用本地 BGE/Qwen，记录 `reports/acceptance.json`。这是应用层离线验证，不声称已进行物理拔网测试。

`app.py --calculator-only` 是显式的轻量测试/故障排查模式，不使用向量模型或 LLM，不算完整 RAG。

## 开源与依赖

应用源代码使用 MIT 许可；Qwen 模型 Apache-2.0，BGE/llama.cpp MIT。Python 依赖、版本及许可见 `THIRD_PARTY.md`、`requirements.lock.txt` 和 `reports/environment.json`。用户原始表与外部参考资料保留各自权利，不因放入项目而变成 MIT 内容。

本版本使用现有电脑和本地模型，没有软件订阅或 API 调用费用。当前 `.venv` 依赖此电脑的基础 Python 路径，不能宣称整个目录复制到另一台电脑就可直接运行。新电脑需先准备 Python 3.12、对应驱动和锁定依赖；模型可以离线拷贝，下载脚本 `scripts/setup_runtime.py` 只在明确准备资源时运行。`--offline` 仅核对现有文件。

## 文件和状态

- `docs/requirements.md`：当前工程需求与阶段验收基线。
- `docs/diagrams/2026-09-15/通信筹划协同流程_v1.4.md`：当前目标图与可编辑图稿入口。
- `docs/superpowers/specs/2026-09-14-scientific-review-design.md`：科学缺陷、来源与修复依据。
- `docs/superpowers/plans/2026-09-14-01-applicability.md`：P1 已完成的实施计划与验收清单。
- `formula_rag/`：解析、检索、模型接口、公式计算与校验。
- `knowledge/formulas.json`：版本化知识库。
- `reports/`：原表复算、模型运行、依赖清单及验收结果。
- `runtime/*.log`：实际启动日志。
- `HANDOVER.md`：本轮交接和尚未验证的边界。
