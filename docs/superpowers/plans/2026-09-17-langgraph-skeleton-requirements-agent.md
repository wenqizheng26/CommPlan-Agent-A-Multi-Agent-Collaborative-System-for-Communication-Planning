# LangGraph 工作流骨架与需求解析 Agent 实现计划

> **面向 AI 代理的工作者：** 按任务顺序执行，每个任务完成后运行其验收命令并记录结果；不得把未完成的真实 Qwen 接入写成已通过。

**目标：** 在一周内搭出可运行的 LangGraph 最小工作流，并完成一个能够把通信筹划自然语言转换成结构化参数、识别缺失/冲突字段的需求解析与参数提取 Agent。

**架构：** 保留现有 `formula_rag` 解析和确定性计算能力，新增 `planning` 层作为工作流和 Agent 适配层。LangGraph 只负责节点、状态和条件路由；本周不让大模型直接计算数值。需求 Agent 先使用现有解析器形成可追溯的参数候选报告，并预留真实 Qwen 适配器；若 Qwen 服务不可用，必须明确标记为 deterministic/fallback 模式。

**技术栈：** Python 3.12、LangGraph（经隔离环境验证后锁版本）、现有 `formula_rag`、stdlib `TypedDict`/dataclass 加运行时校验、unittest、现有本地网页/API不扩展功能。

---

## 本周完成标准

- [ ] 能从一个原始自然语言请求创建 `TaskState`。
- [ ] LangGraph 至少包含 `receive_request`、`extract_parameters`、`check_parameters`、`finish` 四个节点，并有可观察的条件路由。
- [ ] 需求解析 Agent 能输出参数候选、来源、缺失字段、冲突字段和解析模式。
- [ ] 完整输入可以到达 `ready_for_calculation`，缺参输入进入 `awaiting_input`，冲突输入进入 `needs_review`。
- [ ] 不允许用默认值静默补齐缺失参数，不允许 Agent 直接输出正式计算数值。
- [ ] 新增测试全部通过，原有 101 项回归测试不退化。
- [ ] 有一份可追问的交接记录，包含命令、exit code、测试结果、限制和下一步。

## 文件边界

### 创建

- `planning/__init__.py`：planning 包入口。
- `planning/contracts.py`：本周使用的请求、候选参数、状态和 Agent 报告运行时契约。
- `planning/workflow/__init__.py`：工作流包入口。
- `planning/workflow/state.py`：`TaskState` 和状态更新辅助函数。
- `planning/workflow/graph.py`：LangGraph StateGraph、节点和条件边。
- `planning/agents/__init__.py`：Agent 包入口。
- `planning/agents/requirements.py`：需求解析与参数提取 Agent。
- `planning/services/__init__.py`：服务包入口。
- `planning/services/parameter_service.py`：现有 parser/interpretation 能力的受控适配器。
- `tests/test_workflow_dependencies.py`：LangGraph 依赖和最小 StateGraph 验证。
- `tests/test_workflow_skeleton.py`：节点、状态和路由测试。
- `tests/test_requirements_agent.py`：参数提取、缺参、冲突和禁止默认值测试。
- `docs/codex/WEEK1_AGENT_HANDOFF.md`：本周交接与追问记录。

### 修改

- `requirements.lock.txt`：仅在 T1 隔离验证成功后加入确实需要的依赖和精确版本。
- `docs/codex/IMPLEMENTATION_LOG.md`：记录任务、基线、命令、限制和验收结论。
- `docs/codex/NEXT_ACTION.md`：更新下一个可执行任务。

### 禁止修改

- 原始 WBS、VSDX 文件和用户原始资料。
- `formula_rag/core.py` 中的既有公式常数和旧 API 语义。
- 模型权重、`runtime/`、`outputs/`、生产报告和 `.git`。
- 未列入本计划的 UI、复杂传播模型、候选优化和完整生产部署。

## 任务 1：验证并锁定最小 LangGraph 依赖

**文件：**

- 创建：`tests/test_workflow_dependencies.py`
- 修改：`requirements.lock.txt`
- 创建：`docs/codex/DEPENDENCY_DECISION.md`

- [ ] 检查当前 Python 3.12 环境和已锁定的 torch/transformers 是否可安装 LangGraph。
- [ ] 在隔离环境中安装候选 LangGraph 版本，不修改主工作树和模型文件。
- [ ] 写一个最小 `StateGraph`：输入字符串，经过一个节点后返回 `done=true`。
- [ ] 验证本周所需的 StateGraph、条件边和 interrupt/resume API；不使用未验证的 streaming API。
- [ ] 只有验证通过后，才把精确版本写入 `requirements.lock.txt`，并在 `DEPENDENCY_DECISION.md` 记录版本、许可证、安装命令和限制。
- [ ] 运行：

```powershell
& 'E:\codex\项目\信号与AI\signal-formula-rag\.venv\Scripts\python.exe' -X utf8 -m unittest discover -s tests -p test_workflow_dependencies.py -v
```

预期：最小 StateGraph 测试通过；若环境不兼容，保留失败证据，不伪造依赖已锁定。

## 任务 2：定义本周的状态和报告契约

**文件：**

- 创建：`planning/contracts.py`
- 创建：`planning/workflow/state.py`
- 创建：`tests/test_workflow_skeleton.py`

- [ ] 定义 `TaskRequest`：`task_id`、`raw_text`、`manual_parameters`、`condition`、`target`。
- [ ] 定义 `ParameterCandidate`：`name`、`value`、`unit`、`source`、`confidence`、`status`。
- [ ] 定义 `RequirementsReport`：候选参数、缺失字段、冲突字段、解析模式和证据引用。
- [ ] 定义 `TaskState`：原始请求、当前节点、参数报告、状态、trace、错误和 revision。
- [ ] 定义允许状态：`received`、`awaiting_input`、`needs_review`、`ready_for_calculation`、`failed`、`completed`。
- [ ] 对 NaN、Infinity、bool 数值、未知字段、重复字段和空 task_id 做运行时拒绝。
- [ ] 测试 JSON 往返、非法输入拒绝和状态迁移边界。

## 任务 3：封装现有参数解析能力

**文件：**

- 创建：`planning/services/parameter_service.py`
- 只读复用：`formula_rag/parsing.py`、`formula_rag/interpretation.py`
- 创建：`tests/test_requirements_agent.py`

- [ ] 建立 `ParameterService.extract(request: TaskRequest) -> RequirementsReport`。
- [ ] 复用现有单位转换、冲突检测、否定表达和显式参数优先级规则。
- [ ] 每个参数必须保留来源，例如 `manual`、`text`、`catalog` 或 `derived`。
- [ ] 缺失字段只进入 `missing_fields`，不得使用隐式默认值补齐。
- [ ] 冲突字段进入 `conflicts`，不得直接进入正式计算请求。
- [ ] 对已知完整输入、缺频率、缺距离、单位冲突和否定场景各写一个测试。

## 任务 4：实现需求解析与参数提取 Agent

**文件：**

- 创建：`planning/agents/requirements.py`
- 修改：`planning/contracts.py`（仅当契约需要补充）
- 创建：`tests/test_requirements_agent.py`

- [ ] 定义 `RequirementsAgent.run(state: TaskState) -> RequirementsReport`。
- [ ] Agent 只负责理解需求和提出结构化参数，不负责公式计算、不负责修改最终确认值。
- [ ] 默认使用确定性 `ParameterService`，输出 `mode=deterministic`。
- [ ] 预留 `LLMAdapter` 接口；只有真实 Qwen 服务可用并有独立日志时，才允许增加 `mode=local_llm`。
- [ ] 真实模型不可用时，Agent 仍能完成确定性路径，但必须在报告中写明 fallback，不得称为真实 LLM 通过。
- [ ] 测试输出包含参数、缺失字段、冲突字段、来源和模式。

## 任务 5：搭建 LangGraph 工作流骨架

**文件：**

- 创建：`planning/workflow/graph.py`
- 创建：`planning/workflow/__init__.py`
- 创建：`tests/test_workflow_skeleton.py`

- [ ] 实现 `build_requirements_graph()`。
- [ ] 添加节点：

```text
receive_request
→ extract_parameters
→ check_parameters
→ finish
```

- [ ] `check_parameters` 的路由规则：

```text
有冲突 → needs_review
有缺失 → awaiting_input
无缺失且无冲突 → ready_for_calculation
```

- [ ] 每个节点写入 trace：节点名、开始/结束状态、revision 和错误信息。
- [ ] 不在节点中执行正式公式计算，计算服务留给后续任务。
- [ ] 测试完整输入、缺参输入和冲突输入的最终状态。

## 任务 6：连接一个可演示入口

**文件：**

- 创建：`planning/demo.py` 或 `scripts/run_requirements_demo.py`
- 创建：`tests/test_demo_entrypoint.py`

- [ ] 接收一段自然语言通信需求。
- [ ] 创建唯一 `task_id` 和初始 `TaskState`。
- [ ] 调用 LangGraph，打印每个节点的 trace。
- [ ] 输出参数候选、缺失字段、冲突字段、当前状态和解析模式。
- [ ] 使用一条完整输入、一条缺参输入和一条冲突输入完成演示。
- [ ] 不把演示输出包装成最终链路计算结果。

## 任务 7：回归、复核和交接

**文件：**

- 创建：`docs/codex/WEEK1_AGENT_HANDOFF.md`
- 修改：`docs/codex/IMPLEMENTATION_LOG.md`
- 修改：`docs/codex/NEXT_ACTION.md`

- [ ] 运行新增测试和原有测试：

```powershell
& 'E:\codex\项目\信号与AI\signal-formula-rag\.venv\Scripts\python.exe' -X utf8 -m unittest discover -s tests -v
```

- [ ] 记录新增测试数量、总测试数量、失败数和 exit code。
- [ ] 记录 LangGraph 精确版本和安装结果。
- [ ] 记录 Agent 当前是 deterministic 还是 local_llm 模式。
- [ ] 记录已完成、未完成、已知限制和下周推荐任务。
- [ ] 由非实现者复核工作流状态迁移和 Agent 权限边界。

## 本周最终验收

只有同时满足以下条件，才能说“本周完成 LangGraph 骨架和一个 Agent”：

1. `build_requirements_graph()` 可以被测试和 Demo 调用；
2. 至少一个 Agent 能把自然语言转成结构化参数报告；
3. 完整、缺参、冲突三类输入进入不同状态；
4. trace 能显示节点执行顺序；
5. 不使用默认值掩盖缺参，不让 Agent 直接生成计算数值；
6. 新测试和原有回归通过；
7. 文档明确真实 Qwen 是否接入，不能混淆 deterministic fallback 与 local LLM。

