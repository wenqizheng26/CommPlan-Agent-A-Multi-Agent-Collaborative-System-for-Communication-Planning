# AUD-03 Baseline Test Runner

执行窗口：2026-09-17（Europe/London），仓库 `E:\codex\项目\信号与AI\signal-formula-rag`。

## 结论

- `python -X utf8 -m unittest discover -s tests -v`：收集/运行 101，passed 101，failed 0，skipped 0，exit code 0；日志见 `docs/codex/evidence/test-unittest.log`。
- Python AST/JSON 只读静态检查：Python 文件 30 个可解析，JSON 文件 33 个可解析，exit code 0；见 `test-static.log`。
- `node --check web/assets/app.js`：exit code 0；见 `test-js.log`。
- 本地 BGE 只读 probe：模型成功加载，输出形状 `[1, 512]`，有限值为真，范数约 1；见 `test-runtime-readonly.log`。
- Qwen 本地 GGUF 文件存在，但 127.0.0.1:18081 无监听；真实生成、真实 LLM 选择和完整 dense RAG 未验证。

## 环境

使用 `.venv\Scripts\python.exe`，Python 3.12.14；torch 2.8.0+cpu、transformers 4.57.6、numpy 2.2.6、tokenizers 0.22.2、safetensors 0.8.0。`llama-server.exe --list-devices` 可见 Vulkan0 AMD Radeon(TM) 610M 与 Vulkan1 NVIDIA GeForce RTX 4060 Laptop GPU。未安装、下载或修改依赖。

## 未执行命令

README 列出的 `scripts/runtime_smoke.py` 和 `scripts/evaluate.py` 均未执行：代码会覆盖现有 `reports/runtime_smoke.json` 或 `reports/acceptance.json`，超出本任务允许写入范围；两者依赖当前未启动的本地模型服务。历史 reports 不作为本轮结果。

## 测试边界与风险

unittest 当前由 `Engine(dense=False, llm=False)` 的确定性/模拟路径组成，覆盖解析、单位、公式 AST、适用性、API、保存安全等，但不代表真实 embedding、LLM、完整 RAG 或生产运行。测试中的保存写入均使用临时目录。模型和依赖文件存在不等于服务已启动；本轮也未进行浏览器验收、物理拔网测试或生产部署测试。

## 工作区完整性

测试前和测试后 `git status --short` 均为 16 项（9 项已有修改、7 个未跟踪路径的聚合状态，其中docs/codex为本轮新增）；测试执行者只写允许的 `docs/codex/TEST_BASELINE.md` 与 `docs/codex/evidence/test-*.log`、`test_baseline.json`，并报告未修改业务逻辑、依赖、索引、模型、reports 或 `.gitignore`，未 commit/push。状态清单不能证明文件内容完全一致；未捕获开始时的逐文件hash，独立复核不作逐字未变断言。

## 后续条件

在 HUMAN_GATE_0 之后，如允许且模型服务由维护者启动，应单独安排受控真实 smoke/evaluate，并把输出改写到允许的临时证据路径或先获得报告写入授权；不得把本文件的 101 项 unittest 结果升级解释成真实 LLM/RAG 通过。

## T001 H0 Implementation Baseline (2026-09-17)

独立 Tester 在目标 worktree `E:\codex\项目\信号与AI\.workareas\signal-formula-rag-h0-implementation`、分支 `codex/h0-implementation-20260917` 执行：

`E:\codex\项目\信号与AI\signal-formula-rag\.venv\Scripts\python.exe -X utf8 -B -m unittest discover -s tests -v`

结果：`Ran 101 tests in 6.785s`，`OK`，exit code 0；完整 stdout 见 `docs/codex/evidence/t001-tests.log`。测试前后 status 均为 16 项；source 与 target 各有 123 个 tracked 文件。source 15 个既有改动文件的逐文件 SHA-256 与 target 对应文件一致，manifest 见 `docs/codex/evidence/accepted_baseline.json`。

目标 worktree 没有 `models/`、`runtime/`、`.venv/`，本轮未复制大型资产、未安装依赖；命令借用 source `.venv`，仅验证确定性 unittest 路径，不代表真实 embedding、LLM、dense RAG 或生产运行。未修改业务逻辑，未执行 git mutation、commit 或 push。T001 可 Accept。
