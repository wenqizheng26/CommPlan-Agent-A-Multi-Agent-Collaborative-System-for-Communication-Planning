# 确认计算闭环实施计划

采用本会话内执行。用户已授权实施，沿用既有隔离 worktree；不提交或推送 Git。

**目标：** 可在本地网页核对、确认、计算和恢复自由空间单链路任务。
**架构：** LangGraph 确认中断与确定性计算；SQLite 同事务任务/幂等/checkpoint；独立 loopback 页面。
**技术栈：** 现有 Python、LangGraph 1.2.11、SQLite saver 3.1.1、标准库 HTTP、原生 HTML/CSS/JS。

- [x] 1. tests/test_planning_loop.py：先覆盖待确认、计算正确性、缺项/冲突/不支持、编辑失效、重放和过期请求、重启、目录变化、失败回滚。运行 `.venv/Scripts/python.exe -B -m unittest discover -s tests -p test_planning_loop.py -v`，确认因未实现而失败。
- [x] 2. planning/workflow/task_store.py 实现同事务 saver 和历史；planning/workflow/task_service.py 实现命令字段白名单、幂等优先查询与双版本 CAS。新增包仅安装到当前隔离环境并锁定，保存安装报告。
- [x] 3. planning/services/confirmation.py 构建核对内容和不可变确认快照；planning/services/calculation.py 和 planning/agents/calculation.py 实现受控执行与完整 gates；planning/workflow/planning_graph.py 接入 interrupt 和可信发布。运行第1步测试到通过。
- [x] 4. tests/test_planning_web.py 先测试 API 请求边界、同源限制和业务闭环，再实现 planning/web_server.py、planning/web/{index.html,app.js,app.css}、planning/run_planning.cmd。复用服务命令，不在 HTTP 层计算。
- [x] 5. 使用 requesting-code-review 独立审查；补漏洞回归并运行全量 unittest。可见浏览器验证确认、修改、缺项、刷新恢复；将实际结果写 evidence/planning_loop_validation.json。
- [x] 6. 更新 planning/README.md、NEXT_ACTION.md 和本轮交接，提供启动入口，明确本地串行/自由空间/模式与未实现范围。

关键行为样例：
```python
draft = service.apply(create_command)['state']
assert draft['status'] == 'AWAITING_CONFIRMATION'
assert draft['result'] is None
done = service.apply(confirm_command_for(draft))['state']
assert done['status'] == 'COMPLETED'
assert abs(done['result']['outputs'][0]['value'] - 98.42059991327963) < 1e-8
```

每个命令都有 event_id；版本及 review_hash 取自服务器最新返回，任何字段修改必须新 edit 事件。运行失败先调查再修复；正式结果必须通过确定性校验。
