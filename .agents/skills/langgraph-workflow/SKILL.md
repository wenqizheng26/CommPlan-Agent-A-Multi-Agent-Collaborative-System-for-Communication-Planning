---
name: langgraph-workflow
description: 修改通信筹划项目的 LangGraph 状态、用户确认、补参版本或 SQLite 恢复时使用。
---

# 通信筹划工作流

只提供本项目的状态与信任边界，不规定通用开发步骤。

## 按改动定位

- 命令、幂等与版本：[task_service.py](../../../planning/workflow/task_service.py)。这是业务命令边界；确认快照由服务端生成，不信任客户端提交的结果或计划。
- 中断和计算路由：[planning_graph.py](../../../planning/workflow/planning_graph.py)。确认节点恢复会重新进入，interrupt 前避免非幂等副作用；使用同一 task/revision 的 thread_id 和 Command(resume=...) 恢复。
- 持久化：[task_store.py](../../../planning/workflow/task_store.py)。任务、事件回执、历史与 checkpoint 同事务提交；schema setup 在业务事务开始前完成。
- 持续补参：[supplement.py](../../../planning/services/supplement.py)。补参产生新 revision，保留原话和来源，使旧确认与结果失效；未解决的歧义继续阻止确认。

## 修改时保留的约束

- 幂等回执查找先于版本拒绝；重复请求不重做计算，也不把旧状态写回。新请求校验 expected_revision 和 expected_state_version，确认还校验 review_hash 与当前登记模型。
- 专业数值由现有受控计算服务产生；图节点和模型建议不能绕过确认、适用性与结果校验。
- activity 是旁路观察；主事务失败时，已出现的运行事件不能成为正式成功结果。
- 保持当前本地 SQLite 架构；跨进程恢复要验证持久化路径，内存 checkpoint 测试不能作为恢复证据。

相关行为测试位于 [test_planning_loop.py](../../../tests/test_planning_loop.py)、[test_planning_supplement.py](../../../tests/test_planning_supplement.py) 和 [test_planning_activity.py](../../../tests/test_planning_activity.py)，按改动选择验证。API 语义不确定时查项目锁定版本的文档或实现，不按教程示例升级依赖。
