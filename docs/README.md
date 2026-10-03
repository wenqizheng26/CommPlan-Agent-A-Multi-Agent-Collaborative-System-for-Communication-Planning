# 工程文档导航

更新：2026-10-02；查询基线 `54a7b4a`。先选阅读目的，再按各文件注明的版本核对，不能从目标设计推断当前能力。

| 阅读目的 | 入口 | 适用范围 |
|---|---|---|
| 安装与使用 | [产品说明](../README.md)、[操作与CLI](../planning/README.md)、[资源与许可](../THIRD_PARTY.md) | 当前源码；模型安装说明仍在整理，完整独立安装未验收 |
| 当前交接 | [NEXT_ACTION](codex/NEXT_ACTION.md) | 当前批次、所有权、日期和历史入口；实际提交以Git为准 |
| 当前验收 | [三条案例](design/TEACHER_CASES.md)、[状态矩阵](codex/M1_ACCEPTANCE_STATUS.md) | 最新确认的M1标准与逐类证据；不能合并不同SHA为一次通过 |
| 原M1技术约束 | [原三档](design/ACCEPTANCE_M1.md)、[模型/规则职责](design/AGENT_LED.md) | 案例优先；旧三档保留兼容回归，专业计算/来源/确认约束仍有效 |
| 计算与知识设计 | [计算计划](design/CALCULATION_PLANS.md)、[事实机制](design/KNOWLEDGE_FACTS.md)、[模型与检索](design/MODEL_RETRIEVAL.md)、[第4周](design/M1_WEEK4.md) | 各文档记录设计时状态；后来实现与证据见状态条，不把所有设想称已完成 |
| 长期产品 | [需求基线](requirements.md)、[公式调研](design/FORMULA_SURVEY.md)、[有界总控设计](design/ORCHESTRATOR_LLM.md) | 候选/选型/组网覆盖等长期方向；不扩大本次M1验收 |
| 历史实施与验证 | [旧交接原件](codex/NEXT_ACTION.history-2026-10-02.md)、[早期合并记录](codex/M1_COMPLETION.md)、[原发布验证](demo/VALIDATION.md)、[历史证据目录](codex/evidence/) | 原日期、源码与验证方式；保留失败、回退和旧数字 |
| 演示材料 | [早期录制提纲](demo/RECORDING.md) | FSPL阶段提纲；三例新版报告/截图和演示范围另批准备 |

项目父目录还有架构图、旧交付、研究修订和 `协作记录/`。它们不由这个源码仓库自动管理。当前工程成果与历史材料标明版本；独立研究正文修改单列范围。根级版本、依赖及归档方案以父目录项目总览和本次总账为入口。
