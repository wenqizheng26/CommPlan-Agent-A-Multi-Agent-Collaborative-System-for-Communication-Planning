# Visio 流程工作台实现计划

> 使用 executing-plans 在当前已隔离 worktree 内逐项实施；独立审查采用 requesting-code-review。用户已确认设计，不重复请求批准；项目 Git 发布约束优先，不 commit/push。

**目标：** 以已确认八模块展示可追溯的真实运行流程。
**架构：** 保留同步业务命令和事务，旁路持久化观察事件；原生 SVG 双图与模块化详情面板。
**技术栈：** 既有 Python/SQLite/标准库 HTTP、原生 JS/CSS/SVG/MathML，无新增运行库。

## 文件职责

- planning/workflow/activity.py：旁路运行事件、结束标记和重启中断。
- planning/workflow/task_service.py / planning_graph.py / requirements_graph.py / agents/requirements.py：真实节点开始结束观测。
- planning/web_server.py：activity 查询及静态白名单，不增加业务写入口。
- planning/web/flow.mjs：节点和状态投影、SVG 图与可访问交互。
- planning/web/details.mjs：原文/参数/模型/公式/来源/结果联动。
- planning/web/app.js：命令、轮询、历史、导出和视图状态。
- planning/web/index.html / app.css：三栏布局、宽详情与响应式。
- tests/test_planning_activity.py / test_planning_web.py / planning_flow.test.mjs：真进度、回滚、HTTP和版本隔离。

## 任务 1：旁路运行观测

- [x] 添加测试：另一个线程阻塞 RequirementsAgent.run，主线程查询 activity，断言 running 已见而主任务未提交；释放后 assert last phase committed。
- [x] RED：`.venv/Scripts/python.exe -B -m unittest discover -s tests -p test_planning_activity.py -v` 应缺少 activity 功能失败。
- [x] 实现独立 `<db>.activity.sqlite`，start run / append / finish / events / interrupt_open；task service apply 外层记录 terminal，_apply 保持原事务。
- [x] 图与需求 Agent 通过 observer(node, phase, details) 报实际操作；确认等待与可选 LLM skipped 独立事件。
- [x] GREEN：上述测试及既有 test_planning_loop.py，验证错误回滚、重放和版本归属。

接口样例：
```python
run = activity.start(command)
observer = lambda node, phase, details=None: activity.append(run, node, phase, details)
# committed 仅在原事务返回之后写入
activity.finish(run, 'committed', status=result['state']['status'])
```

## 任务 2：HTTP 与数据投影

- [x] 测试 GET /api/tasks/<id>/activity 的同源、ID边界、运行中可见及静态模块路径。
- [x] 接入查询，服务启动将旧 open run 标 interrupted。
- [x] 添加 Node 测试，覆盖新版本不继承旧结果节点、rejected 不显示成功、历史事件隔离、缺参/未接入状态。
- [x] 实现 flow.mjs 的纯投影函数 nodeStates(state, events) 和图目录。

```js
assert.equal(nodeStates(edited, oldEvents).calculation, 'idle');
assert.equal(nodeStates(draft, []).confirmation, 'waiting');
```

## 任务 3：画布与八模块

- [x] 重建 index.html 与 app.css，保留输入控件ID及业务行为；增加双视图、节点详情tabs、宽模式、时间线。
- [x] SVG 定义主要执行路径、补参/缺口/失败分支、目标未接入节点；总体架构使用1+3关系，能力线和状态线独立。
- [x] details.mjs 使用 textContent 与 DOM 创建节点；参数原文 codepoint span 高亮；原始/规范值与符号齐全，公式 MathML 原生排版与规范单位注明。
- [x] 依据卡显示 excerpt 为库内摘要，locator/source/version/status 明确；安全 http/https 链接，本地路径文本显示。
- [x] app.js 接入轮询（处理期间约500ms），拒绝旧task/版本响应，确认仍基于当前hash；历史只读、回当前、JSON Blob导出。
- [x] 不将前端动画当运行事实；详情列显示已登记公式的草稿/实际代入区分。

## 任务 4：真实验收与交接

- [x] 全量 Python unittest 与 Node 测试、pip check、旧路径 diff 检查。
- [x] 独立审查真实事件/事务/版本及页面来源边界，修复有依据的问题。
- [x] 可见 Chrome 检查双图、节点详情、参数/公式/依据回链、完整计算、缺参、修改、恢复、历史只读与JSON导出按钮；截图检查版面。
- [x] 保存证据和设计映射，更新 NEXT_ACTION/README/HANDOFF；保留本地服务可试用。
