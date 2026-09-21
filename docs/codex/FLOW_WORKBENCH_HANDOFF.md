# 流程工作台交接

2026-09-18。用户确认八模块和双视图布局后实施。启动方式不变：planning/run_planning.cmd，浏览器 http://127.0.0.1:18082。代码位于现有隔离 worktree，无 Git 提交/推送。核心确认计算合同仍为 confirmed-fspl-loop-v1。

## 页面入口

左侧输入原文与手工参数；中间默认执行流程，可切总体架构；右侧节点详情含概览、参数、计划、公式、依据、结果，支持展开宽面板。底部执行时间线与任务历史；顶部导出当前查看版本的 JSON。

参数页点击参数名可高亮原文，包括 emoji 前缀的 codepoint 定位。表格同时保留原始数值/单位和规范值/单位；公式页提供变量定义、数学排版、实际代入与来源回链。依据区明确区分库内摘要和原始文献，保留定位、版本、核查日期；本次未重审原文。历史版本只读，返回当前后才能发命令。

## Visio 对应关系

参考 C:/Users/nntm/Desktop/天大信号/通信筹划多智能体协同流程.vsdx，两页 XML 已读取。原文件 SHA256：e5cf33fbcf22e8a7d48d2254cfc8efea90321f9dd6b3394ac28de891f0cb8fb8。未改原图，页面不是原图逐像素复制。

| 原 Visio | 页面位置 | 当前实现说明 |
|---|---|---|
| page1 Shape35/39/44/49/54 | 总体架构的输入、总控、三个角色 | 总控标未接入；需求已接入；专业计算为确定性调度；验证解释为部分接入 |
| page1 Shape59/66/71 | 确认、损耗模型、结果 | 真实确认、计算和硬校验后发布 |
| page1 Shape77/82/89/95 | 检查点、LLM、RAG、知识库 | SQLite；可选本机意图建议；当前词项检索；登记公式卡 |
| page2 Shape92–145 | 解析、检索、意图建议、计划、确认 | 依当前代码顺序显示程序解析→检索→可选LLM建议→规则计划；不冒称完整LLM规划已完成 |
| page2 Shape150–171 | 专业计算 | 当前确认快照进入受控模型，数值由程序计算 |
| page2 Shape176–211 | 校验、报告、保存 | 程序校验和报告可用；完整LLM解释/审查标未接入；JSON导出可用 |
| page2 Shape215/220/227 | 补参、模型缺口、异常 | 分支状态及原因可见；不添加虚构自动重试 |

图中任务关系、共享能力调用、状态关系用不同线型/颜色。架构关系不意味着运行先后；执行图中的蓝色运行、绿色完成、橙色等待、红色失败来自运行观察或已保存状态。可选步骤未调用时明确标记。

## 真实运行观察

ActivityStore 在 `<主数据库路径>.activity.sqlite` 中记录旁路事件，默认 outputs/planning.sqlite.activity.sqlite。任务、幂等回执与 LangGraph checkpoint 继续同一次主事务提交；观察事件不能授权计算或发布。

GET /api/tasks/<id>/activity 返回本任务最近最多1000条事件、available 和 authoritative:false。允许任务尚未提交时查询。原同源/Host约束保留。event含seq、run_id、event_id、task_id、revision、node、phase、at和details。

同步POST执行期间前端约500ms轮询；快步骤不会人为减速，时间线保留实际开始结束与耗时。finish committed 只在主事务已返回后写入；重放用replayed；操作回滚用rejected。服务启动将未终结观察标interrupted，随后仍以主任务状态为准。旁路记录故障不回滚业务，可能缺少进度；刷新检查保存状态。只支持本地单服务，不支持多个服务同时操作同一activity文件。

前端隔离任务、输入版本、请求代际和单调seq，拒绝迟到的旧观察；已完成保存状态优先。恢复时若发现open run，继续观察直到终结，再读取已保存任务；历史查看不显示该版本保存以后发生的活动。

## 验收

全量Python 169项，56.463秒，exit0，见 evidence/flow-workbench-tests.log。此后变更仅为前端竞态修复和连线/文案整理；最新Node 7项通过、JS语法通过。pip check通过，旧formula_rag/app.py/web/knowledge无diff。

独立审查发现两个P2并均复核关闭：迟到activity覆盖completed、迟到历史响应跨任务插入。修复包含generation失效、seq单调守卫、COMPLETED优先、history请求/按钮闭包task校验、切任务清历史和空current保护。

可见Chrome验收：新建需求；2000MHz/1000m→2GHz/1km；emoji原文定位；参数→公式→来源；MathML与实际代入；确认98.420600dB；总体架构未接入标记；宽详情；真实时间线；历史只读及返回当前；JSON下载文件读取确认；修改为缺少距离后旧结果失效并进入补问。没有宣称全面移动端兼容或逐帧动画录像验收。

范围仍为自由空间单程损耗。本轮没有启动真实Qwen重新验收，没有新增云依赖、模型权重或科学公式。先前真实Qwen/离线验证保留在 CONFIRMED_LOOP_HANDOFF.md。
