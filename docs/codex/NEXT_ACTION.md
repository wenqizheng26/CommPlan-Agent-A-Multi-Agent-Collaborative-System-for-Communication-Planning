# 当前工程交接

更新：2026-10-06。B1、原 B3a、ROADMAP、B2a 与 F1 已合入 main `bd85d06412c8a52fc8f60b4edbac0d30360a6f8e`，准确提交 [CI run37208706807](https://github.com/wenqizheng26/CommPlan-Agent-A-Multi-Agent-Collaborative-System-for-Communication-Planning/actions/runs/37208706807) 为 SUCCESS。10-02 审计基线 `54a7b4a` 保留为历史；实际工作区、后续提交及验证以查询为准。

## 当前范围与入口

- 产品入口与支持范围：[README](../../README.md)。文档导航：[docs/README](../README.md)。
- M1 当前验收以 [三条案例](../design/TEACHER_CASES.md) 为先；[原三档](../design/ACCEPTANCE_M1.md) 保留兼容回归和技术约束，不替代最新案例。
- 自动测试、真实模型、浏览器、离线安装、发布及打包分别记录在 [验收状态矩阵](M1_ACCEPTANCE_STATUS.md)。历史结果不自动代表当前提交通过。
- 正式稳定标签仍是 `v0.1.0`（FSPL 范围）；开发源码已扩展预算、补充计算、资料与报告。当前没有 M1 冻结标签。

## 当前协作与下一步

项目级双方独立审查与分批方案 S2-v1 已通过。仓库外的 `协作记录/总账.md` 是本次协调与交接记录，完整方案和原始分歧保留在那里；不能把 Codex 内部代理当作 Claude 审核。

Codex 隔离目录当前为 `codex/m1-install-precheck（安装预检修补284909a，实际HEAD查询为准）`。[PR14](https://github.com/wenqizheng26/CommPlan-Agent-A-Multi-Agent-Collaborative-System-for-Communication-Planning/pull/14) 包含 B3b 首批 `d359d39`、B3c-1 `5956001`、B2b `0683588` 和归档路径修补 `cc039b3`；Claude 已通过 B3b/B2b，准确 head 的 push37448511208 / PR37448518739 四项 CI 已 SUCCESS，待路径修补的独立审核后集成。此次文档状态修正是独立批次，不并入 PR14。

| 批次 | 所有权与状态 |
|---|---|
| B1 文档入口与状态 | 已经实际双审、PR9 与准确提交 CI 合入 main；`codex/m1-convergence-docs` 为该批历史分支 |
| ROADMAP 长期路线 | 已经实际双审、PR11 与准确提交 CI 合入 main；设计路线不代表长期能力已实现 |
| B2a 业务与站点标签、报告 | 已经实际双审、PR13 与准确提交 CI 合入 main；日常开发目录仍为 `CommPlan-Agent-M1`，实际 checkout 另查 |
| B2b 评测门禁 | 隔离提交 `0683588` 已实现，Claude R45 独立通过；随 PR14 待归档修补的独立审核，尚未合入 main |
| B2c 当前全量真实回归 | B2a 已合，待 B2b runner 合入后执行；老师20、M1 36、硬规则、第4周；预先锁留出、原题重复，模型与回退分列 |
| 原 B3a 与 F1 源码包工具 | PR10/PR12 已经实际双审与准确 CI 合入 main；白名单漏项、正式 Git blob 来源及换行可重现已修，验证范围仍为源码预检 |
| B3b / B3c-1 工具首批 | 安全资源工具已由 Claude R45 独立通过；FILE_PAYLOAD 已补短路径根与输出比较，PR14 完整 CI 已通过，待修补独立审核；实际资源已取得，独立安装预检进行中，历史恢复未完成 |
| B3 后续、B4–B5 | 按已审依赖推进独立安装、成果材料及完整历史恢复；尚未宣布最终包可运行或旧目录可删 |

B2a 业务仅是原文需求标签，不参与计算，不承诺视频吞吐。B2b 隔离实现已加入失败非零退出、空/未知/重复选择拒绝、已有期望断言及实际角色/计划来源/模型身份/source SHA 记录；在 PR14 合入前不能当作 main 已有门禁。数值计算仍应为 `deterministic`。

真实模型回归显式执行 `python -B -X utf8 scripts/eval_teacher.py --mode llm`；可用 `--cases <题集路径>` 跑留出集。runner 默认 `deterministic`，该模式不调用语言模型。

## 日程与安全边界

- 新能力最晚 2026-10-14 合入；10-15～19 只修缺陷、补测试及文档，不做代码职责重构或全库格式化。
- 10-20 才冻结候选；10-21～23 完成最终包和完整隔离安装验收；10-24 前完成通过批次与交付。不提前冻结，不把等待日期当成阻塞。
- 合入 main 按 PR、对应提交 CI、双方实际复核。冻结后必要修补用新标签，旧标签及记录保留。
- 稳定版接替、旧目录移除必须等完整验收与归档独立恢复，M1 入口路径在 10-24 前保持。
- 共享 Git、主环境和模型不并发改；快照前在项目总账公布安全窗口。离线方法已按用户 U14 确认为在线准备完毕后关闭 Wi-Fi；届时核对全部外网通路、外网失败与回环正常，再执行完整验收。当前保持在线，其他独立批次继续推进。

## 历史记录

此前叠加的状态、授权、下一步和验证数字的完整原文保留在 [2026-10-02 历史快照](NEXT_ACTION.history-2026-10-02.md)。它描述各记录当时的事实，不是当前执行指令；旧限制若被本次用户授权取代，在项目总账追溯依据。原始证据继续在 [evidence](evidence/) 中，不覆盖失败记录。

未经 Git 换行转换的原字节快照另保存在项目父目录的协作记录/B1_原件/M1-NEXT_ACTION-before-B1.md，SHA256 为 203A6EFBF6C5126B9CDB0BAC048406076067153ED619EE23E6D9B3F76CF7DFA5。仓库历史文档可能随检出配置转换换行；原件归档以该快照及最终历史包清单为准。
