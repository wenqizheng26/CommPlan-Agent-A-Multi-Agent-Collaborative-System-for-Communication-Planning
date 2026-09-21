# 自由空间单链路确认计算闭环

范围依据：用户对上一轮三步方案回复“继续”，并要求合理重选 skills。实现本地单用户页面，不修改旧 /api/query，不扩展海上传播、预算、设备推荐或自主 LLM 总控。

1. 服务端拥有 task_id、revision、state_version、当前请求、报告、确认快照、结果和轨迹。外部只能创建、编辑完整输入、确认指定 review_hash、取消；严格字段校验，不接受自由 result/snapshot 注入。
2. create 从 revision=0/state_version=0 开始。edit 必须 CAS 命中两个当前版本，revision+1，旧 snapshot/result/report 不再作为当前结果，历史仍保存。新的 request_id 来自事件 id。
3. 服务端返回带 hash 的完整核对资料（原文、规范参数与来源、条件、模型、计划、依据、限制）。只有 AWAITING_CONFIRMATION 可确认，确认时校验 CAS、review_hash、报告和当前知识目录。确认请求不夹带参数修改。
4. LangGraph 路径：已有需求子流程 → human_confirmation(interrupt) → calculation → validate_result → publish。缺项/冲突/模型缺口直接等待，不自动循环。每个 revision 独立 thread_id；修改创建新图状态，不恢复旧 revision。
5. SQLite 负责任务、历史、事件幂等和 LangGraph checkpoints。SqliteSaver 3.1.1 的 cursor 适配为由外层事务提交；setup 在事务前完成。BEGIN IMMEDIATE 串行化本地写入，graph.invoke 完成后才发布状态和 ack。异常回滚包括 checkpoint。此内部适配需锁版本并测试回滚；无异步图、多实例吞吐承诺。
6. 同 task/event_id 同内容返回原 ack 和当前状态，不晋升旧结果；同 id 不同内容拒绝。新事件才检查 CAS。确认后刷新/重复点击不重复执行。崩溃在提交前允许重做纯计算，但不会出现两个已提交结果。
7. 计算角色只选择已确认 plan 中白名单 fspl_ghz；计算服务校验完整 snapshot 与冻结 report、知识版本、域、条件、scope，调用既有 evaluate，检查 result_issues 与有限数。不得把自然语言重组后再次交给旧 parser。
8. 正式报告由已校验结果构建，包含参数、模型版本、公式、依据、限制和组件模式。负值/非有限值/校验失败没有可发布 outputs，保留有效输入、失败节点、原因和下一步。
9. 页面提供需求输入、可选手工频率/距离和单位、确定性/本地模型模式、核对、明确确认、修改、取消、任务恢复和历史查看。原文与手工冲突需用户修改完整输入。页面默认确定性演示并明确标识，真实 LLM 需选本机模式；不自动启动模型。
10. loopback HTTP 独立端口 18082，固定静态文件白名单，同源写请求和会话 token，大小/JSON 边界校验；本地运行数据写 outputs/planning.sqlite。无云部署、Git 发布和真实通信可行性承诺。

验收：基准2GHz/1km正确；未确认零次计算；缺参/冲突/海面实际损耗不计算；改参旧确认失效；两客户端竞争只有一次提交；幂等重放不覆写当前版本；确认/计算失败可见；新进程恢复待确认任务；故障注入事务回滚；浏览器完整闭环与刷新恢复；旧回归保留。
