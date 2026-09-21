# 当前技能安排

2026-09-21，用户批准 B：精简本项目，并移除三个全局旧技能入口；随后明确要求保留 AGENTS.md。两个 AGENTS.md 均保留，只删除重复流程和强制技能链。

当前项目只保留 `.agents/skills/langgraph-workflow/SKILL.md`，针对图状态、人工确认、补参版本与 SQLite 恢复按需读取。正文保留项目特有的事务与信任边界，以代码和行为测试为参考，不附通用语言教程，不规定固定开发步骤。

原项目技能 `langgraph-fundamentals`、`langgraph-human-in-the-loop`、`langgraph-persistence` 已完整归档；原来源仍为 LangChain 官方仓库提交 `88df7d9b0cf8fedf40b99c1de806135fc2e2582d`。新增技能是依据本项目代码整理的精简说明，不是官方技能原文。

全局 `brainstorming`、`writing-plans`、`test-driven-development` 的发现入口已归档。这三个入口原为 Junction，实际源文件位于 `E:/codex/项目/skills/.agents/skills/`；源文件保留，另有独立内容备份。因此本次是移除全局注册路径，不是删除共享技能库；在技能库项目内部，它们仍可能作为项目技能被发现。其他全局技能未改。

## 备份与恢复

- 项目旧技能、规则修改前副本及全局技能内容快照：`E:/codex/项目/信号与AI/backups/skills-slimming-20260921-023930`。
- 全局 Junction 归档：`C:/Users/nntm/.codex/skill-archives/skills-slimming-20260921-023930`。
- 源路径、归档路径和 SHA256 见项目备份目录的 `manifest.json`；操作记录见 `runtime/skills-slimming-backup.json`。
- 恢复时先核对目标不存在，再将对应归档目录或 Junction 移回记录中的 source；若恢复三个项目旧技能，同时归档新技能并恢复相应 AGENTS.md，避免恢复后出现相互冲突的调用规则。

不新增 communication-domain、rag-pipeline 或 repo-audit。科学边界保留在 AGENTS.md；本地模型 Agent 的运行时 skills 按用户要求留待下一轮。

文件调整不会撤回已经进入当前会话的旧指令；后续上下文重新发现技能时再核对实际列表。此轮只验证技能结构、引用、归档完整性及业务源码未变，不重复运行无关业务测试，也不据此宣称模型表现已经提升。
