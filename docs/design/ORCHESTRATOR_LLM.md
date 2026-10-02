# 总控升级：模型参与的总控（M1 之后）

状态：用户 2026-09-28 确认方向（两轮问答），M1（2026-10-24）之后实施；开工前再补问下文“开工前再定”各项。

## 现状

- `planning/agents/orchestrator.py` 是固定规则，按任务状态决定下一步：有结果就校验，审查通过就发布，工具失败最多重算 2 次，其余一律停止。审查判“需重算”时也只是停止。
- 对话消息先检查是否换电台或站点（`planning/services/entity_followup.py`），不是就当补充合并（`planning/services/supplement.py`）。概念提问、比较方案、判断能否通信都没有入口。
- 流程图上总控到大模型的连线标“未接入”。

## 决定

| 项 | 决定 |
| --- | --- |
| 判断范围 | 四项都做：对话入口分流、审查后的下一步、失败恢复、多任务拆分 |
| 权限 | 混合：<br>① 分流用 Router：模型从固定的意图集合里选一个，由代码分派；<br>② 审查后和失败时，由程序列出当前合法动作（重算、追问用户、停止），模型选一个并写理由，追问的问题由模型写；<br>③ 多任务拆分用规划-执行：模型写子任务清单（如“比较 XX-100 与 XX-200”），程序逐项校验，每项仍走现有计算链；用户确认一次即覆盖全部子任务；最后由模型汇总，程序核对数字。<br>程序始终核对确认闸门、次数上限与状态合法性；模型离线或输出不合规时，退回现有固定规则 |
| 调用时机 | 按需：<br>- 每条对话消息调用一次（分流），可顺带取代“换用检测”那次调用；<br>- 只有一个合法动作时，程序直接走，不问模型；<br>- 拆分任务时，规划、汇总各调用一次 |
| 展示 | 对话消息下显示一行：“总控：判为……→……（理由）”。流程图的总控节点和“记录与配置”里有完整决策；总控到大模型的连线改为已接入 |
| 不做 | 完全自由的 supervisor 循环或 swarm 交接：工程计算要能复现、能审计，本机 9B 每多走一步就多一次等待和出错的机会 |

## 调研（2026-09）

- 代码编排加模型分类：[OpenAI Agents SDK · Agent orchestration](https://openai.github.io/openai-agents-python/multi_agent/)。文中用结构化输出分类，并区分 agents as tools 与 handoffs。
- routing 与 orchestrator-workers：[Anthropic · Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)。建议先用简单的工作流，只在确有收益时才加复杂度，并设停止条件与人工检查点。
- supervisor：[langgraph-supervisor](https://github.com/langchain-ai/langgraph-supervisor-py)。官方现在推荐直接用 tool-calling 实现 supervisor。
- 路由优先、复杂时升级：[Amazon Bedrock multi-agent collaboration](https://aws.amazon.com/blogs/machine-learning/amazon-bedrock-announces-general-availability-of-multi-agent-collaboration/)（supervisor with routing）。
- 任务清单与重新规划：[Magentic-One](https://www.microsoft.com/en-us/research/articles/magentic-one-a-generalist-multi-agent-system-for-solving-complex-tasks/)。

## 开工前再定

- 意图集合及每个意图的去向，例如概念提问由谁回答、依据哪些资料。
- “重算”的含义：同一确认快照下重跑，还是改输入后重新确认。
- 拆分上限（子任务个数）与汇总形式。
- 评测：准备中英文对话消息分流集（标明期望去向），比较模型与规则的准确率和耗时。
- 分流要同时支持中英文消息，与第 4 周的英文需求衔接。
