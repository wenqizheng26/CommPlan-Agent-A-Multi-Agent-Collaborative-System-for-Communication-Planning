# AUD-02 RAG 与确定性计算资产审计

日期：2026-09-17。阶段：AUDIT，最终停在 HUMAN_GATE_0。本报告只记录当前代码和小型只读 probe；不表示公开来源已重新审核，不替代 AUD-03 的全套测试基线。已读完整 v3 交接；仓库及逐层父目录检查未找到 AGENTS.md。没有改业务代码、知识库、依赖、原输出、公共 Contract，没有运行索引更新/模型下载。保留现有用户业务修改。

## 结论

应保留并包装现有 RAG，不得整体重建 `formula_rag/`，不得新增第二套索引。7 条 verified、版本 1.0.0 的卡实际存在，8 个数值样例本轮按其声明容差通过。存在完整的 parser→retrieval→意图约束→适用性→依赖计算→后验检查链，但不存在独立 RAGService、CalculationService、ValidationService 契约。`Engine.query` 是现有集成入口，不等同于已有 workflow/agent service。

## 模块事实与最小复用映射

| 资产 | 代码证据 | 可保留/包装及缺口 |
|---|---|---|
| 目录与准入 | catalog.py:17-88 | load_catalog/validate_card 校验表达式、参数域、verified/draft、来源字段、样例结构；保留。不是来源真实性验证，也不在加载时复算样例。 |
| 检索 | retrieval.py:15-19,34-107 | 卡级 document→中文二元词/英文词项 cosine，加本地 BGE CLS 归一化向量，RRF 排名；包装为 RAGService。无 PDF/Word 通用切块管道。 |
| 索引 | retrieval.py:70-87 | runtime/formula_index.npz，catalog SHA256 + model.safetensors SHA256 判定缓存；不得第二套向量库。fingerprint 未含 tokenizer/config/pooling 实现版本，需新增 snapshot 身份表达，先兼容旧缓存。 |
| 参数 | parsing.py:7-174 | FIELDS 规范字段，标签/单位绑定、原文片段、规范单位、冲突拒绝；复用 parser。手工覆盖无 revision/confirmation history。 |
| 意图 | model.py:8-50; interpretation.py:12-79 | loopback-only 本地 JSON schema selector；候选 ID、连续原文、否定语境核验。模型不进入数值字典，专业数值始终 evaluate。 |
| 算术 | core.py:11-141 | AST 解释器，无 Python eval；函数与运算白名单，长度4096/节点128/深度32/指数1024限制，有限数与参数域校验；保留。 |
| 适用性 | applicability.py:6-108; pipeline.py:85-139 | free_space/最大单程多普勒/噪声290K参考及结果 gate。包装 ValidationService 时必须复用全链，不能只暴露 evaluate。 |
| 依赖计算 | pipeline.py:14-15,73-145 | FSPL→Pr→margin，noise_density→threshold→margin；同次 completed 避免重复依赖；没有统一 LinkBudgetEngine 类，现有关系可增量包装。 |
| 展示 | presentation.py:25-78 | 数学展示来自表达式 AST，保留。 |
| 登记 | importing.py:20-59 | 导入强制 draft、拒绝同 ID/单位冲突，approve 复算样例并写 reviewer/time；保留。status 本身不是认证，直接编辑 JSON 可绕过 approve。 |
| API | app.py:18-111 | /api/status、/api/catalog、POST /api/query、/api/save-result。服务端保存不可由客户端传入结果或路径；query 锁串行，结果64项内存缓存，无持久 task/revision。 |
| UI | web/assets/app.js:11-18 | 参数补充、目标/条件选择、来源目录、结果状态、JSON保存。不存在 confirmed snapshot / interrupt-resume。 |
| 评测 | scripts/evaluate.py:29-74 | 23 场景、本地 dense+LLM、socket audit guard；实际写 reports/acceptance.json，本轮未运行。全套测试由 AUD-03 负责。 |
| 包标识 | __init__.py:1 | 仅 docstring，不存在隐藏 service 层。 |

现有字段不等同于已冻结的任务级公共契约。

## 7 条公式的实际数据与可信边界

全部 `knowledge/formulas.json` 卡自报 verified、v1.0.0。来源含 title/url/locator，多数 checked_date=2026-09-14；这些日期只是仓库元数据，未在本轮重新联网核实。精确卡内容、输入域、样例均保存于 evidence/rag_calculation_assets.json。

| ID / JSON 行 | 表达式/样例结果 | 代码与声明边界 |
|---|---|---|
| fspl_ghz / 3-60 | 92.4+20log10(f_GHz)+20log10(d_km)；4.5GHz、0.2km→91.48485018878651dB；0.4km→97.50545010206613dB | 明确自由空间或理想基准；f,d>0；不含散射、遮挡、海反射。92.4 舍入保持旧基线，不能擅改。近场异常检查不是完整天线远场证明。 |
| doppler_max / 63-119 | f*1e9*(v/3.6)/299792458；4.5GHz、108km/h→450.3115285175053Hz | 仅单程一阶频移幅度上界，速度0至1079252.8488km/h，需 maximum_doppler，双程拒绝；不能当多普勒dB损耗。 |
| thermal_noise / 122-176 | 10log10(1.380649e-23*T*B*1000)；290K、1MHz→-113.97518719422811dBm | T/B显式且正；不暗加NF，不把Rb等同B；匹配与经典热噪声条件仅描述，不被完整物理校验。 |
| received_power / 179-253 | Pt+Gt+Gr-Lt-Lr-Lp-Le；样例→-51.48485018878651dBm | 馈损、路径损耗、额外损耗非负且必须输入（0也显式）；同频同链路同参考面只是声明，当前缺结构化证明。 |
| link_margin / 256-307 | Pr-Pmin-reserve；样例→10.51514981121349dB | reserve非负显式；未舍入值判上下门限；正margin不是现场可靠性证明。 |
| noise_density / 310-354 | 10log10(k*T*1000)；290K→-173.97518719422808dBm/Hz | T正且显式，不默认290K。 |
| receiver_threshold / 357-436 | N0+10log10(Rb)+Eb/N0+NF+工程损失；样例→-62dBm | pipeline要求明确标准290K噪声路线，仅允许精确k290或显式-174，非290K拒绝；卡 notes 比当前 gate 宽，包装应遵守实际更严 gate。 |

FSPL 与散射不可互换。实际 probe “散射链路…计算路径损耗”返回 not_applicable 且无数值。知识库没有经审核散射模型；扩展只能预留模型标识/条件/输入/输出契约，禁止把自由空间基准标成散射估算。

链路预算与 Pr/margin 是同一计算链的模型与输出关系，不能为 WBS3.2/3.3 写两套算法。已显式提供 Pr/门限/路径损耗时，当前引擎直接采用该数值，缺少 task 级来源和适用范围校验。

## 已证实风险与复现

| ID / 等级 | 证据 | 影响与建议 |
|---|---|---|
| RC-01 HIGH | parsing.py:168-174；probe manual_overwrite | 文本200米 + parameters.distance_km=1 → request变1km、issues=[]、status=ok，原文本值不作为冲突保存。这是旧手工优先语义，不能映射成已确认事实；新wrapper保留双方来源并要求显式resolution。 |
| RC-02 HIGH | pipeline.py:100-108；probe conflicting_derived | 同次请求提供路径损耗100dB并要求FSPL与Pr，Pr按100计算为-60dBm，FSPL为91.48485018878651dB，整体ok且依赖为空。不能断言算术错误：可能是不同来源的有意比较，但当前无场景/模型身份区分，不能当一致单链路正式结果。新ValidationService检测同名不同来源，明确选择或拒绝。 |
| RC-03 HIGH integration | core.py:94-141 vs pipeline.py:85-139；probe core_scope_bypass | evaluate对1GHz/1e-9km返回ok/-87.6dB，符合“算术内核不管环境”既有设计。CalculationService若直接包装 evaluate 会丢物理gate。必须将准入、scope、结果检查作为原子执行协议。 |
| RC-04 MEDIUM | scripts/evaluate.py:50；probe stale_eval_threshold | 旧threshold case无290K明确确认却期待ok；当前calculator-only返回needs_input/missing_conditions。评测预期与新scope不一致，修复测试数据/目标，不放宽gate。 |
| RC-05 MEDIUM | retrieval.py:89-107; scripts/evaluate.py:64 | limit默认8，只有7卡，不相关查询词项相似度全0仍返回7卡，contains_target近乎恒真；不能据此称高检索质量。增加top-k/rank、拒识、扩充只读fixture，不先扩知识库。 |
| RC-06 MEDIUM | pipeline.py:80-84,192-196 | calculation有version/sources，candidate无version，runtime只有catalog_hash/rule_version；无稳定EvidenceRef、知识快照文件hash、逐参数origin/dependency hash、task/revision。需服务返回统一追溯，而不是复制RAG。 |
| RC-07 MEDIUM | catalog.py:59-70; importing.py:42-58 | verified结构校验只要可定位字段/样例；无法证明网址有效、正文支持论断、科学边界已审。来源复核需独立任务，严禁把状态当标准认证。 |
| RC-08 MEDIUM | web/assets/app.js:11 | 目录所有卡硬编码“已核对”，连未来draft也如此；后端draft不执行但UI可信标识误导。保留后端gate，后续UI按status展示。 |
| RC-09 MEDIUM | retrieval.py:46,79-87 | 缓存只hash模型权重，不覆盖tokenizer/config/编码逻辑变更；同权重不同预处理存在stale embedding风险。扩大snapshot fingerprint，并做兼容性测试。 |
| RC-10 LOW/MEDIUM | pipeline.py:52-67,180-190; app.py:105 | LLM失败可退化程序计算并仍整体ok，但warning明确不是完整RAG。HTTP200代表请求处理成功，业务needs_input/not_applicable不等于success。新Contract须分开业务结果与组件运行状态。 |

不存在已证据支持的“所有不可执行结果都success”：当前业务状态明确区分，缺馈损/额外损耗probe返回needs_input且无数值；draft/缺参/非法输入都被gate。RC-02 是一致性语义未建模，而不是失效公式强制成功。partial允许独立有效结果与未完成结果同返，Workflow不得把partial直接当终态成功。

## 最小 Service 边界（建议，未冻结）

- RAGService：调用 load_catalog + 现有 Retriever.search；返回候选排名、来源、卡版本、catalog/model/规则snapshot身份。只检索，不隐式确认参数、不另建索引。候选是不是可执行由ValidationService负责。
- CalculationService：受控接收冻结 CalculationRequest 与明确模型/参数snapshot。第一版可兼容适配 Engine.query 的确定性模式，但需评估其文本再解析/覆盖语义；最终单公式调用 evaluate 必须在前后执行现有scope/result gate，依赖复用现有映射。不能直接把core.evaluate发布为“专业计算已验证”。
- ValidationService：复用 validate_card、finite/domain、scope_issues/result_issues，再新增跨来源冲突、snapshot/revision一致性、证据版本匹配；新增逻辑只在冻结Contract后实现。
- 旧 /api/query 保持兼容，不把新Workflow字段硬塞旧参数字典。GraphState/Schema/路由/提交权限由Main独占；Service子任务只能消费冻结Contract，发现不足提交 CONTRACT_CHANGE_REQUEST。

## WBS 真正状态建议

2.0/2.1 PARTIAL（公式知识有，筹划体系广度不足）；2.2 PARTIAL（单公式字典有，任务级身份/确认/冲突缺）；2.3 PARTIAL：卡级向量/索引为BASELINE，通用文档分块未实现；2.4 BASELINE（检索本体）/service缺；2.5 PARTIAL；2.6 PARTIAL（有测试/评测，质量指标和旧case缺口）；2.7 PARTIAL。

3.0 PARTIAL（单公式参数，缺统一CalculationRequest）；3.1 BASELINE但仅自由空间声明域；3.2 PARTIAL（现有依赖预算链，无统一任务对象/对账）；3.3 BASELINE（Pr/margin算式，非现场验证）；3.4 PARTIAL（无隐式0/290K，但无suggested/confirmed）；3.5 PARTIAL（Engine存在、稳定service缺）；3.6 PARTIAL（单位/domain/部分物理gate具备，任务hard validation不全）；3.7 PARTIAL（8样例本轮通过，不等独立科学验证）；3.8 DESIGN/未找到通用扩展service；3.9 PARTIAL。

## 验证与未验证

本轮命令：PowerShell here-string管道至 `.venv/Scripts/python.exe -B -`；只在进程内实例化 `Engine(root,dense=False,llm=False)`，执行5个定向场景、8个卡样例、不相关检索和单独core边界。完整输入/返回值在 evidence/rag_calculation_assets.json；无bytecode写入、无cache更新、无网络。

尚未验证：实时dense/LLM可用性与性能、来源正文和最新标准、全部浏览器交互、噪声/远场之外的物理条件完备性、完整测试与回归。全套基线参见AUD-03，不能用历史报告代替。后续候选任务见 evidence/aud02_tasks.json，全为 BLOCKED_HUMAN_GATE_0。
