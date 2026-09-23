# Planning Workbench 使用说明

当前正式计算范围：用户确认自由空间条件后的单链路单程路径损耗。真实海面、散射、多径、链路预算、能否通信判断和方案比较不在此版。主入口见[根 README](../README.md)。

## 网页工作台

首次运行仓库根目录 `setup_planning.cmd`（Python 3.12，安装 `requirements-planning.txt`）。日常运行 `start.cmd` 或 `启动.cmd`，打开 <http://127.0.0.1:18082>；确定性模式无需模型。已有环境时也可以从根目录运行 `planning/run_planning.cmd`。需要自选端口与数据库：

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m planning.web_server --port 18083 --db outputs/demo.sqlite
```

页面先展示任务描述、五步进度、待回答问题、参数确认和结果。下方直接展示 Visio 风格的**总体协同架构单视图**与运行观察，点击节点可追溯公式、依据和角色；连线高亮是运行活动与责任关系，不能推断为每一条直接图调用。执行时间线和原始 JSON 可展开。模型运行方式与模型健康检查在高级设置；任务编号恢复在高级恢复，最近任务列表仍在主界面。

完整示例：“按自由空间基准计算，频率2GHz，距离1km，求路径损耗。”确认后约 **98.42 dB**。只给频率会出现距离问题；原文 2 GHz 与手工 3 GHz 会提示冲突；区间 `2±0.1 GHz` 给出 **97.98–98.84 dB**；候选 `2 GHz 或 3 GHz` 分别计算。示例按钮只填内容，不自动发送。修改已完成任务会使旧确认/结果失效；重新确认后才能再计算。刷新和重启后可从 SQLite 恢复。

关闭后台启动器窗口不会停止其创建的服务。停服务时须核对 `runtime/commplan-*.pid` 的进程身份与命令行，只停止本目录创建的服务；不要按进程名结束被复用的外部服务。前台单独启动的窗口可以 Ctrl+C。任务数据位于 `outputs/`，source ZIP 不包含它。

## 独立需求 CLI

在根目录执行：

```powershell
.\.venv\Scripts\python.exe -B -X utf8 -m planning.demo --deterministic --request planning/examples/complete.json
.\.venv\Scripts\python.exe -B -X utf8 -m planning.demo --deterministic --request planning/examples/missing.json
.\.venv\Scripts\python.exe -B -X utf8 -m planning.demo --deterministic --request planning/examples/conflict.json
```

CLI 只生成规划报告，正式结果须在网页确认计算。模型服务可选，连接 127.0.0.1:18081；`--no-fallback` 会使模型不可用时明确失败。模型权重与 llama runtime 需自行准备，并放在项目内 `models/signal-formula-qwen3/` 或通过 `--asset-root`/`COMMPLAN_ASSET_ROOT` 覆盖。不会自动下载。

状态含义：`AWAITING_CONFIRMATION` 等待核对；`AWAITING_INPUT` 等待补充或处理冲突；`NEEDS_MODEL` 表示目标或专业依据超出当前范围；`FAILED` 表示执行失败；`COMPLETED` 仅在确认、计算、硬校验和审查后保存。输入编辑使旧确认失效，版本和历史可查。
