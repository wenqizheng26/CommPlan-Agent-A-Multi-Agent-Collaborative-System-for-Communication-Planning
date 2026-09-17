# 仓库真实基线

AUD-01，2026-09-17；只读审计，未修改业务代码，未启动模型/服务/安装依赖/提交推送。

分支 `codex/p1-applicability`，HEAD `7342866450b08dafca10278bf98812f9f0fac137`。完整文件元数据库存 27230 项，含 .git/.venv/models/runtime/ignored 文件，非仅 rg 默认列表；Git跟踪123项。详见 evidence/repository_inventory.json。该快照生成后docs/codex仍在写入，不能把文件总数当最终工作树计数。

## 目录与职责

|目录|文件数|职责|
|---|---:|---|
| .git | 172 | Git内部元数据 |
| .gitignore | 1 | 根目录文件或缓存 |
| .venv | 26624 | 本地Python环境 |
| BACKUP.md | 1 | 根目录文件或缓存 |
| HANDOVER.md | 1 | 根目录文件或缓存 |
| LICENSE | 1 | 根目录文件或缓存 |
| README.md | 1 | 根目录文件或缓存 |
| THIRD_PARTY.md | 1 | 根目录文件或缓存 |
| __pycache__ | 2 | 根目录文件或缓存 |
| app.py | 1 | 根目录文件或缓存 |
| docs | 19 | 历史需求/设计/新审计 |
| examples | 2 | 根目录文件或缓存 |
| formula_rag | 22 | 解析/检索/模型选择/计算/校验核心 |
| knowledge | 3 | 公式目录与来源资料 |
| launch.py | 1 | 根目录文件或缓存 |
| models | 10 | 本地模型资产 |
| outputs | 1 | 用户导出结果 |
| reports | 15 | 历史报告，非本轮测试证据 |
| requirements.lock.txt | 1 | 根目录文件或缓存 |
| runtime | 248 | llama.cpp及索引 |
| runtime_config.json | 1 | 根目录文件或缓存 |
| scripts | 13 | 导入/评测/运行检查 |
| tests | 20 | unittest测试 |
| tests.zip | 1 | 根目录文件或缓存 |
| web | 67 | 旧页面及本地KaTeX |
| 启动.cmd | 1 | 根目录文件或缓存 |

## 真实入口与调用链

|入口/能力|证据|行为|
|---|---|---|
|桌面启动|启动.cmd:3; launch.py:59|.venv Python启动launcher；本审计未启动|
|CLI/API|app.py:114,18|--query或loopback HTTP 18080；--calculator-only显式降级|
|GET|app.py:43|/、/assets、/api/status、/api/catalog|
|POST|app.py:58,64|仅/api/query和/api/save-result，无confirm/resume端点|
|UI|web/index.html; web/assets/app.js:16|一次提交直接query与计算；参数核对在结果之后|
|解析/单位|formula_rag/parsing.py:39,76|convert/extract_request；手动覆盖路径168起|
|检索|formula_rag/retrieval.py:34,62,89|本地BGE + 词项 + RRF，卡级索引|
|模型|formula_rag/model.py:8|单LocalSelector，非四角色运行时|
|解释输入核验|formula_rag/interpretation.py:12|merge_interpretation核对原文依据|
|计算/适用性|formula_rag/core.py:94; pipeline.py:74; applicability.py:54|递归依赖+确定性AST；scope在pipeline层|
|导入|formula_rag/importing.py:20,42|登记/审批公式|
|测试/评测|tests/test_*.py; scripts/evaluate.py|unittest；真实RAG评测与程序测试分开|

请求链：app Handler → Engine.query → extract_request → Retriever.search → LocalSelector(可关闭) → merge_interpretation → calculate递归 → scope/evaluate/result gates → JSON/UI。RAG和确定性计算应增量wrapper，禁止重建核心。

## committed 与 local

审计前15项旧改动：9 modified，6 untracked，当前status仍列出这些路径；各执行者报告未改写。没有开始时的逐文件内容hash，因此独立复核不能证明逐字未变。Modified: HANDOVER.md、README.md、app.py、docs/requirements.md、docs/superpowers/plans/2026-09-14-01-applicability.md、examples/complete_budget.txt、formula_rag/pipeline.py、tests/test_app.py、tests/test_pasted_input.py。Untracked: docs/p1-applicability.md、formula_rag/applicability.py、reports/stages/p1-applicability.json、reports/stages/p1-changes.json、reports/stages/p1-red.json、tests/test_scientific_scope.py。

本报告行号针对当前working tree；P1适用性模块与相关分支不是HEAD已提交能力。HEAD已有RAG/公式/API基础；不能通过reset、checkout或覆盖来恢复所谓干净基线。后续需单独批准旧改动整合策略。

## 验证边界

仓库下rg未发现AGENTS.md。只读检索未找到业务StateGraph/GraphState/checkpoint/interrupt/resume实现；requirements.lock.txt未列LangGraph/Pydantic。安装状态、全套测试和测试数量以独立TEST_BASELINE.md为准；本agent没有重复运行测试。runtime_config.json声明BGE/Qwen及本地端口，配置存在不是本轮真实模型运行证明。

保存JSON由服务端内存results缓存取值(app.py:21,74)，不接受客户端计算值；它是最多64条的进程内缓存，不是任务持久化/checkpoint。源事实/版本/确认状态仍须新契约。

## 独立运行基线汇合

AUD-03报告101项unittest通过，30 Python/33 JSON静态解析通过，app.js语法通过；BGE只读probe输出[1,512]有限归一化向量。Qwen 18081无监听，真实生成与完整RAG未验证。见TEST_BASELINE.md及其原日志。本审计只引用该独立证据，不重复测试。
