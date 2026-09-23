# 模型与检索：设计规格

状态：设计定稿，未实施。纳入 v0.1.0-demo，实施后按 V4 重跑 Stage 2–4 门禁。
决策来源：用户 2026-09-23 确认——纳入本次发布；仅本机模型；全局默认 + 逐次记录；RAG 实现由其他人按本文接口完成。
本文取代 V4 §1.2 与 §32 中“不做新 RAG 栈”的限制，仅限本文范围；runtime Skills、LoRA、远程模型仍不在范围内。

## 0. 不变量

1. 专业数值只来自登记的确定性工具。模型与检索只影响参数草稿、候选公式、调用建议、审查意见与引用片段。
2. 更换模型或检索设置**不使已确认快照失效**，只作用于下一次操作；已保存结果保留其生成时的配置记录。
3. 运行期只走本机回环，启动与运行都不下载。注册表中非回环地址一律拒绝。
4. activity 只用于观察；耗时摘要可写入报告来源信息，但不进入任务权威状态判断。
5. 模型不可用时沿用现有降级语义：明确显示“调用已降级”，由程序给出同一受控结果。

## 1. 现状与缺口

| 项 | 现状 | 缺口 |
| --- | --- | --- |
| 生成模型 | 仅 Qwen3-4B Q4（llama.cpp，18081）。模型名与端口写死在 `role_model.py`、`supplement.py`、`model_status.py`、`formula_rag/model.py`、`formula_rag/model_transport.py`；`max_tokens` 分散为 700/400/600 | 无注册表、无统一接口、无按角色选择 |
| 向量模型 | `formula_rag/retrieval.py` 已有 bge-small-zh + 词项 RRF 融合（k=60，limit=8） | 工作台以 `dense=False` 构造，只用词项；无重排 |
| top-k / top-n | 固定 limit=8；无 top-n 概念 | 不可配置，页面看不到哪些片段进入 LLM |
| 响应时间 | activity 有开始/结束时间戳；时间线显示单条耗时；LLM usage 已记录但不显示 | 无汇总、无跨任务统计、无模型对比 |
| 评测 | 无 | 换模型缺乏证据 |
| 页面 | “高级设置”仅确定性 / 本机 Qwen 二选一 | 无模型、检索、参数与性能的交互 |

## 2. 模型注册表

受版本控制的配置文件 `config/models.json`（不含权重）。启动器、工作台与评测脚本都只读它；`runtime_config.json` 保留给旧版应用，C4 时退役。

```json
{
  "schema_version": 1,
  "defaults": {"chat": "qwen3-4b-q4", "embedding": "bge-small-zh-v1.5", "reranker": null},
  "models": [
    {
      "id": "qwen3-4b-q4",
      "kind": "chat",
      "display_name": "Qwen3 4B · Q4_K_M",
      "runtime": "llama.cpp",
      "endpoint": "http://127.0.0.1:18081",
      "alias": "signal-formula-qwen3",
      "context": 4096,
      "capabilities": {"json_schema_strict": true, "thinking_toggle": true},
      "defaults": {"temperature": 0, "max_tokens": 700, "timeout_s": 30},
      "launch": {"executable": "runtime/llama.cpp-b10950/llama-server.exe",
                 "weights": "models/Qwen3-4B-GGUF/Qwen3-4B-Q4_K_M.gguf",
                 "gpu_layers": 99, "device": "Vulkan1"},
      "revision": "bc640142c66e1fdd12af0bd68f40445458f3869b"
    },
    {
      "id": "bge-small-zh-v1.5",
      "kind": "embedding",
      "display_name": "BGE small zh v1.5",
      "runtime": "transformers-cpu",
      "path": "models/bge-small-zh-v1.5",
      "dimension": 512,
      "query_prefix": "为这个句子生成表示以用于检索相关文章：",
      "revision": "7999e1d3359715c523056ef9478215996d62a620"
    }
  ]
}
```

校验规则：`id` 唯一；`kind ∈ {chat, embedding, reranker}`；`endpoint` 主机必须是 `127.0.0.1`、`::1` 或 `localhost`；所有路径为项目内相对路径；权重缺失时模型显示“未安装”，不报错。注册表内容纳入 build fingerprint。

新增模型只需：用户手动把权重放入 `models/`，在注册表加一项。运行期从不下载。

## 3. 生成与向量提供方接口

```python
class ChatProvider(Protocol):
    def chat(self, messages: list[dict], *, schema: dict | None, params: ChatParams) -> ChatResult: ...
    def health(self) -> ModelHealth: ...

@dataclass
class ChatResult:
    output: Any            # 已按 schema 解析
    raw_output: str
    model_id: str          # 注册表 id，而非服务返回的别名
    usage: dict            # prompt_tokens / completion_tokens
    latency_ms: int
    attempts: int

class EmbeddingProvider(Protocol):
    def embed(self, texts: list[str], *, kind: Literal['query', 'passage']) -> EmbedResult: ...
```

- 五处现有调用全部改走 `ChatProvider`，错误映射到现有 `ModelResponseError` 代码，降级语义不变。
- 需要严格结构化输出的角色（需求、补问、计算建议、审查）只允许选择 `json_schema_strict=true` 的模型；页面上不满足的模型置灰并说明原因。
- `ModelHealth`：`ready / loading / stopped / not_installed / failed / unexpected`，取代只认单一别名的 `model_status.probe_model()`。

## 4. 检索接口（RAG 由其他人实现）

工作台只依赖下面的协议；随发布附带一个默认实现（现有词项检索，可选开启 bge 向量与 RRF 混合）。RAG 负责人替换实现，但必须通过第 4.3 节的合同测试。

### 4.1 协议

```python
class RetrievalService(Protocol):
    def search(self, query: str, *, top_k: int, top_n: int,
               mode: Literal['lexical', 'dense', 'hybrid'],
               filters: dict | None = None) -> RetrievalResult: ...
    def describe(self) -> CorpusInfo: ...   # 条目数、语料版本、可用模式、向量模型 id

@dataclass
class Hit:
    id: str                       # 知识库条目 id；公式卡为 formula id
    source_type: Literal['formula_card', 'document_chunk']
    title: str
    excerpt: str                  # 送入 LLM 与页面展示的文本，≤ 800 字
    source: dict                  # uri / version / locator（页码、章节）
    scores: dict                  # lexical / dense / fused / rerank，未计算的为 None
    rank: int                     # 1 起，按最终排序

@dataclass
class RetrievalResult:
    hits: list[Hit]               # 长度 ≤ top_k
    used: list[str]               # 送入 LLM 的 id，= hits 前 top_n 条
    mode_used: str                # 实际模式；向量不可用时降为 'lexical'
    degraded: bool
    embedding_model_id: str | None
    reranker_id: str | None
    latency_ms: dict              # lexical / dense / fusion / rerank / total
    corpus: dict                  # size / version
    diagnostics: list[dict]
```

### 4.2 语义

- **top-k**：最终保留的候选数（融合、重排之后）。默认 8，范围 1–20。
- **top-n**：送入 LLM 上下文的条数，取 `hits` 前 n 条。默认 3，范围 1–top_k。无重排器时即截断。
- 排序确定：同分按 `id` 升序；同一输入、同一语料版本、同一设置必须得到相同结果。
- 只返回知识库中存在的条目；不联网；超出范围的参数直接报错而不是静默截断。
- 检索结果**不是数值权威**：公式仍须是登记卡并经用户确认后才能计算。
- 预算：词项 ≤ 300 ms；CPU 上混合检索 ≤ 1.5 s；超时返回已完成部分并置 `degraded=true`。

### 4.3 合同测试（`tests/test_retrieval_contract.py`，由本项目提供，RAG 实现必须通过）

1. 返回类型与字段完整；`len(hits) ≤ top_k`，`used == [h.id for h in hits[:top_n]]`。
2. 确定性：同一调用重复 3 次结果一致。
3. 越界参数（top_k=0、top_n>top_k、未知 mode）抛出约定异常。
4. 向量模型缺失时 `mode='hybrid'` 降为词项并 `degraded=true`。
5. 所有 `id` 存在于知识库；`excerpt` 长度上限。
6. 运行期间无网络访问（测试中禁用 socket 外连）。
7. `latency_ms.total` 存在且为非负整数。

### 4.4 接入点

需求 Agent 用 `used` 对应的片段组织 LLM 上下文；「依据」页签列出全部 `hits` 及各项分数，标明哪些进入了 LLM。

## 5. 设置：全局默认 + 逐次记录

- 存储：任务数据库中独立的 `settings` 表（单行 JSON + 版本号），与任务事务分离。
- 接口：`GET /api/models`（注册表 + 实时健康状态）、`GET /api/settings`、`PUT /api/settings`（沿用写令牌与 Origin 校验，按注册表和能力校验）。
- 内容：`mode`（确定性 / 本机模型）、`chat.default`、`chat.roles{requirements, supplement, compute_agent, validator_agent}`（缺省跟随默认）、`params{temperature, max_tokens, timeout_s}`、`retrieval{mode, embedding, top_k, top_n}`。
- 逐次记录：每个命令把实际生效的配置 `effective_settings` 与提示词哈希写入该命令的事件回执，并进入报告来源信息。页面在结果上显示“由 Qwen3 4B 生成 · 检索 混合 k=8 n=3”；若当前默认已改变，提示“当前结果使用的是旧设置”，不自动重算。

## 6. 本机模型切换

- 一个 llama-server 进程只加载一个模型。切换默认生成模型时，由工作台调用启动器逻辑：只停止本项目启动且身份已核验的进程，从不结束外部复用的服务；按注册表启动新模型并等待就绪。
- 工作台只能启动注册表中列出的、项目内相对路径的可执行文件；参数由注册表生成，不接受页面传入的任意命令行。
- 加载期间页面显示“加载中”；此时需要 LLM 的操作按现有语义等待至超时后明确降级。
- 显存允许时可在注册表为不同模型配置不同端口同时常驻，属后续优化。

## 7. 响应时间与可观测性

- activity 的 completed/failed 事件增加 `duration_ms`；LLM 事件增加 `model_id`、`usage`、`latency_ms`、`tokens_per_s`、`attempts`；检索事件增加各阶段 `latency_ms`。
- 任务结果来源信息增加 `timing{total_ms, by_module}` 摘要。
- 页面：流程节点完成后显示耗时角标；时间线改为瀑布图；结果页一行汇总（总耗时、模型耗时占比、token）；新增「性能」视图，按模块与模型给出最近 N 个任务的 p50/p95。
- 初始预算：确定性路径端到端（不含用户操作）≤ 1 s；本机 4B 模型单次角色调用 p95 ≤ 15 s。
- 失败按原因分类统计：`offline`（连接失败）、`structure`（结构不合格）、`timeout`、`cancelled`。现有记录无法区分有意的离线测试与真实失败。

### 7.1 实测基线（2026-09-18 至 09-23，本机运行记录 4 个库合计，Qwen3 4B Q4_K_M）

| 模块 | p50 | p95 | n |
| --- | --- | --- | --- |
| 需求理解 · 模型（成功） | 1.33 s | 6.07 s | 18 |
| 计算建议 · 模型（成功） | 1.64 s | 5.53 s | 15 |
| 结构化审查 · 模型（成功） | 1.36 s | 1.90 s | 14 |
| 结构化审查 · 模型（失败） | 2.11 s | **30.11 s** | 10 |
| 确定性模块（解析、检索、公式、校验、发布、状态） | ≤ 15 ms | ≤ 62 ms | — |

结论：等待几乎全部来自模型调用；C2 在线验收任务中模型占总耗时 90%，且审查首次调用失败后重试才通过。审查失败的 p95 等于写死的 30 s 超时，因此超时必须按角色可配置，页面在模型调用期间显示已等待时间。向量检索冷启动实测约 48 s（加载 bge 并编码卡片），预热后单次约 34 ms：向量模型必须随工作台启动预热，未就绪前检索按降级处理并在页面标明。

原型（画布，数据即上表）：https://claude.ai/artifact/PZMohbRBVZoxC35W7KFnFT

## 8. 模型评测集

- `tests/eval/requirements_cases.jsonl`，约 30 条：完整、缺参、冲突、区间、离散候选、无单位、超出范围、目标/条件显式选择。每条给出期望参数、目标、条件与应触发的问题。
- `scripts/eval_models.py --models <id...>`：本机逐条运行，输出结构化通过率、参数抽取正确率、降级率、p50/p95 延迟与 token，写入 `outputs/eval/<日期>.json`。
- 「性能」视图可载入评测报告做模型对比。新增模型进入默认值前必须附一份评测报告。

## 9. 页面交互

“高级设置”改为「模型与检索」面板，渐进披露：

1. **运行方式**：分段控件——确定性 / 本机模型。
2. **生成模型**：列表项含名称、量化、上下文、状态（就绪 / 加载中 / 未启动 / 未安装 / 不支持结构化输出）；选中后显示“加载此模型”。
3. **按角色覆盖**（折叠）：四个角色各一个选择框，默认“跟随默认模型”。
4. **检索**：方式分段控件（词项 / 向量 / 混合）、向量模型选择、top-k 滑块（1–20，默认 8）、top-n 滑块（1–k，默认 3），下方注明“知识库当前 N 条”。
5. **专家**（折叠）：temperature、max_tokens、超时。
6. 底部固定说明：“作用于下一次操作，不改变已确认的数值。”按钮：保存为默认 / 恢复出厂。

顶栏状态徽标显示当前生成模型名；结果与「依据」页签显示生成配置与耗时。

## 10. 分工

| 部分 | 负责 |
| --- | --- |
| 本文设计、接口与合同测试规格、页面设计、切换与安全边界判断 | Claude |
| 注册表加载与校验、提供方接口、五处调用迁移、设置 API、页面实现 | Claude 实施核心与页面；Codex 按本文做调用迁移、测试补齐 |
| activity 计时字段、评测集运行脚本、文档与验收记录、重跑门禁、推送 | Codex |
| `RetrievalService` 的向量/混合/重排实现、文档切块与入库 | RAG 负责人（其他人），须通过 4.3 合同测试 |
| 选择要加入的本机模型并手动放置权重、目标 Chrome 验收 | 用户 |

## 11. 发布门禁增补

在 V4 §29 七项流程之外，增加：切换生成模型并完成任务；模型加载中与加载失败的降级；按角色覆盖生效且记录正确；检索三种模式与 top-k/top-n 边界；向量模型缺失降级；已确认任务在改设置后不失效且提示旧设置；耗时显示与性能视图；一份评测报告。
