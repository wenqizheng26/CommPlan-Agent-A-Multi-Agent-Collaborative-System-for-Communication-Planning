# 本轮 skills 选择与使用

用户已批准继续“共享任务状态 → 参数确认 → 专业计算 → 结果检查 → 页面展示”，并要求重新筛选本地与 GitHub skills。保留该授权，不重复启动设计问答。

## 已核对的来源

- 本地 writing-plans：记录实施顺序、接口和验收；不把建议的频繁 commit 当作绕过项目唯一发布者规则的授权。
- 本地 test-driven-development：先验证缺失功能的失败，再实现确认、版本、恢复和数值门控。
- 本地 requesting-code-review / verification-before-completion：独立审查信任边界，使用本轮实际结果验收。
- 本地 systematic-debugging：只在故障出现时按根因排查，不每一步重复调用。
- GitHub [langgraph-human-in-the-loop](https://github.com/langchain-ai/langchain-skills/blob/88df7d9b0cf8fedf40b99c1de806135fc2e2582d/config/skills/langgraph-human-in-the-loop/SKILL.md)：确认节点使用 interrupt/Command；恢复会重入，节点前半段无外部副作用。
- GitHub [langgraph-persistence](https://github.com/langchain-ai/langchain-skills/blob/88df7d9b0cf8fedf40b99c1de806135fc2e2582d/config/skills/langgraph-persistence/SKILL.md)：固定 task/revision 对应 thread_id，SQLite 持久化，本地串行执行。内存 checkpoint 不宣称可重启恢复。

两份官方 LangChain skill 使用 skill-installer 的 Git 模式按 commit 固定，放在被 Git 忽略的 runtime/selected-skills 中；初次 ZIP 下载遇到 IncompleteRead，Git 下载成功。仅项目内按路径读取，不是全局安装或下一轮自动注册。

## 排除和按需使用

- brainstorming 已用于澄清并获得用户继续授权，本轮不重开审批。
- using-git-worktrees 检查已有隔离目录，复用原 worktree。
- 未采用第三方综合 LangGraph 技能包：官方两项已覆盖当前技术缺口。
- 检查过 anthropics/skills 的 webapp-testing；其强制无头浏览器与当前可见 Chrome 工作习惯不一致。本轮用已有 cua 浏览器能力进行页面验收，不额外安装浏览器运行时。
- computer-use 本地 skill 面向 sky 原生 Windows API；当前浏览器使用 cua_repl，不能混用工具名。Figma、Sites、数据分析和论文技能不符合这次本地 Python 功能实现，不加载。
- 不因 skill 示例包含 Postgres、云模型或 Store 就新增这些依赖；保持本地 Qwen、现有词项检索和已锁 LangGraph。

## 技能不能替代的校验

checkpoint 不等于用户确认，thread_id 不等于授权，hash 不等于可信来源。业务版本、幂等记录、确认快照与 checkpoint 必须同一次 SQLite 事务提交。公式仍由现有 AST calculator 和 scope/result gates 执行。真实端到端、重启恢复、过期请求和故障回滚必须实测。
