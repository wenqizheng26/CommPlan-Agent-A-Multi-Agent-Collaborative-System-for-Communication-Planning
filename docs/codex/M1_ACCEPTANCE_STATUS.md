# 当前验收状态矩阵

更新：2026-10-06。已集成 main 为 `bd85d06412c8a52fc8f60b4edbac0d30360a6f8e`，准确 CI run37208706807 SUCCESS；只读审计基线 `54a7b4a327f9612d9b06882db7431d24c183dc91` 仍作为历史。PR14 head `cc039b3` 的三项工具尚未集成，准确 head 的 push37448511208 / PR37448518739 四项 CI 已 SUCCESS，归档短路径修补的实际审核待完成。此表区分历史证据、当前提交结果和待执行验收，不是完成证书。

当前验收以 [三条案例](../design/TEACHER_CASES.md) 为准；原 [M1技术约束](../design/ACCEPTANCE_M1.md) 与对应兼容回归保留。最终产品目标见 [需求基线](../requirements.md)，不作为所有长期能力本次必做的依据。

| 类别 | 已有事实与对应版本 | 当前/最终尚需验证 |
|---|---|---|
| Git与正式版本 | 正式 `v0.1.0` → `b9575a5`，发布FSPL。审计时开发/main=`54a7b4a`，PR #7/#8已合；B1、原B3a、ROADMAP、B2a、F1现已集成至main `bd85d06` | M1未冻结/发布；候选10-20才建立，稳定晋升等完整验收；PR14准确CI已通过，待修补独立审核，未合main |
| CI | main `54a7b4a` 的 [run36969071160](https://github.com/wenqizheng26/CommPlan-Agent-A-Multi-Agent-Collaborative-System-for-Communication-Planning/actions/runs/36969071160) 两作业成功；准确main `bd85d06` 的 [run37208706807](https://github.com/wenqizheng26/CommPlan-Agent-A-Multi-Agent-Collaborative-System-for-Communication-Planning/actions/runs/37208706807) SUCCESS | 最终验收SHA的CI；不代替模型/浏览器/包验收 |
| 自动回归 | [文案批次](evidence/2026-10-02-product-copy.md)：当时Python509项（2 skip）、Node111项、HTTP冒烟。10-06独立Python3.12.15完整环境首轮601项/168.259s为1 error、2 skip：跨域拒绝POST出现Win10054，symlink权限不可用，ITU缺源；完整Node113通过。源码基线cc039b3仅有已记录的两行test fixture修补 | 完整矩阵尚未通过；HTTP未读POST正文的连接竞态已有最小复现，生产修补及当前回归待完成。ITU后续官方取得、索引8项无skip通过；权限skip仍保留说明；最终隔离环境约定全量另验 |
| 老师固定集真实模型 | [9B记录](evidence/2026-10-02-teacher-9b.md)及原始JSONL：首轮13/20，后续修复子集；当时汇总20条通过 | 不能拼成同SHA一次全量；当前20条及三原题，source SHA/模型版本/实际角色/计划origin/回退分列 |
| 原M1真实模型 | [历史最终运行](evidence/2026-09-26-M1-final-run.md)；09-27 summary对应`6dd412e`；另有10-02实际调用日志 | 当前实现全量36、硬规则；新调用缺SHA/完整断言不能证明回归通过 |
| 第4周真实模型 | [历史统一验收](evidence/2026-09-30-week4-completion.md)，固定9/9、分工与回退记录 | 当前实现全量复验，不能外推其他场景 |
| 输入/报告完整性 | [离线检查记录](evidence/2026-10-02-offline.md)记录站点/业务展示缺口；fixture已有service期望。B2a业务/站点投影已合main，保留原文与旧任务兼容 | B2b断言/失败门禁已在隔离提交实现、待PR14集成；当前真实模型与浏览器复验仍待B2c |
| 浏览器与报告 | cb2dd89三例；[T3](evidence/2026-10-01-T3-records.md)、[T4](evidence/2026-10-02-T4-report.md)为各自内置浏览器检查；有打印前DOM | 目标浏览器当前版本、执行进度、业务/站点、实际打印PDF；内置浏览器不自动算Chrome |
| 真离线 | [历史记录](evidence/2026-10-02-offline.md)有外连采样和服务过程检查；用户U14已定在线准备后关闭Wi-Fi | 尚未执行最终离线验收；确认全部外网通路、域名/直接IP外网失败及回环正常后跑完整矩阵与实际三例，采样不能替代 |
| 修改确认与保存恢复 | 历史自动/HTTP检查覆盖若干确认与恢复路径 | 最终包：修改失效、再确认、保存与恢复、适用/拒绝路径 |
| 源码/独立安装包 | [v0.1.0验证](../demo/VALIDATION.md)保存当时包结果；原B3a与F1已合main。10-06独立cc039b3源码预检ZIP为168成员，Python93/Node33及HTTP创建/确认/恢复通过；四runtime实际下载/解包/加载通过，新venv固定wheel无索引安装和pip check通过，embedding权重及3份ITU资料已真实取得并安装 | B3b工具首批已实际双审、准确CI成功，待PR14整体集成；9B取得仍在进行，实例/真离线/最终tag完整验收未完成。正式交付组装仍须纳入安装说明、资源工具和完整验证层，不能把168成员预检ZIP当作完整交付包 |
| 历史归档恢复 | 已有 `_archive`、backups记录，它们是旧快照；B3c-1 FILE_PAYLOAD捕获/校验工具在隔离提交实现，准确PR14 CI已成功，修补独立审核待回 | 实际完整捕获、受控恢复、三Git bundle与独立实际文件/依赖恢复尚未完成，工具fixture通过不代替历史恢复 |
| 双方审核 | 本次S2-v1由Codex和Claude各自实际通过，原文保存在父目录协作总账 | 每个实现批次重新独立复核；内部代理、CI和历史审核都不能代替另一方 |

## 最终包验收记录要求

每项记录源码标签/SHA、包SHA256、Python/依赖/OS与硬件、模型revision/SHA与runtime、独立路径/配置/缓存/DB/端口、步骤、预期与实测、原始证据及限制。仅照包内说明安装并从指定来源实际下载模型；在线准备完成后按U14关闭Wi-Fi，核验外网失败与回环正常，三案例与约定评测、浏览器、打印、恢复、关闭及端口释放全通过才称完整验收。

归档可恢复、交付可运行、M1功能达标分别结论；服务启动、固定用例、历史记录或某次CI成功不能互相替代。运行相关包内容变化完整复验；非运行材料变化仍做事实/渲染核对和hash更新。冻结修补保留旧标签及旧记录，复验后新标签。若未过，准确列失败项，稳定版保持v0.1.0。
