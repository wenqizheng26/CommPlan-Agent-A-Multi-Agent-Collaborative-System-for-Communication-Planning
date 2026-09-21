# 通信筹划：Visio 流程工作台

当前网页已接通：需求解析 → 参数与来源核对 → 用户确认 → 专业公式计算 → 结果校验。支持修改后重新确认、任务历史、刷新与服务重启恢复；范围为自由空间单程路径损耗。

## 当前页面

当前为总体架构单视图。点击节点查看参数、计划、公式、来源和结果；点击参数定位原文；展开详情查看长公式。支持持续补参，修改后旧确认与结果失效。节点状态来自后端事件，快速步骤在执行时间线中回看。历史只读，顶部可导出当前查看版本的 JSON。

新增计算调用建议、结构化审查与有次数上限的主控策略。选择“本机 Qwen”时，需求、计算建议和审查分别调用现有本地模型；数值仍由确定性公式产生。无效模型输出或离线情况明确降级。审查可退回用户、提出模型缺口或请求重算，每版本最多计算两次。尚未实现自主任务拆解、新传播模型或候选优化。当前交接见 [ROLE_EXTENSION_HANDOFF_20260921.md](../docs/codex/ROLE_EXTENSION_HANDOFF_20260921.md)。

## 网页入口（推荐）

需要同时启动本机模型和网页时，双击仓库根目录的 [`启动.cmd`](../启动.cmd)。它会寻找本地资源、复用已就绪服务并打开浏览器；详情与资源路径设置见[根 README](../README.md#2-一键启动推荐)。模型启动失败时仍可使用确定性模式，页面会保留明确的模式标记。

双击本目录的 `run_planning.cmd`，在 Chrome 打开 <http://127.0.0.1:18082>。默认确定性解析，无需启动模型；选“本机 Qwen”时只连接已有本地服务，不可用会明确降级。不要重复启动同一端口的服务。

填入完整示例 → 解析 → 核对参数、来源和模型假设 → 勾选确认 → 计算。2 GHz、1 km 的结果为 **98.420600 dB**。修改输入后须先保存并重新确认；缺项和冲突会阻止计算。

任务保存在工作区 `outputs/planning.sqlite`。保存页面中的任务 ID，可在同一数据库恢复任务。启动窗口按 Ctrl+C 停止服务，数据仍保留。使用其他端口或数据库：

```powershell
.\planning\run_planning.cmd --port 18083 --db outputs/demo.sqlite
```

仅供本机单用户、串行执行使用；不包含账号权限、分布式调度或真实海上传播模型。当前检索为词项检索。正式交接、API、验收与限制见 [CONFIRMED_LOOP_HANDOFF.md](../docs/codex/CONFIRMED_LOOP_HANDOFF.md)。

## 独立需求 Agent CLI

以下命令行入口保留首个 Agent 的单独体验：输入通信需求，查看参数、来源、冲突/缺项、模型依据和计划建议。该 CLI 只做规划，不输出正式损耗；确认计算请使用上述网页。

## 最快试用

在 Windows 资源管理器双击本目录的 `run_requirements.cmd`，按提示输入一行需求。例如：

> 按自由空间基准计算，频率2GHz，距离1km，求路径损耗。

默认尝试本机 Qwen；没有服务时明确降级为确定性解析。要完全不调用模型，在项目工作区 PowerShell 中运行：

```powershell
.\planning\run_requirements.cmd --deterministic
```

工作目录为 `E:\codex\项目\信号与AI\.workareas\signal-formula-rag-h0-implementation`。已有隔离 `.venv` 可用，模型权重和 ML 库复用源仓库的本地资产；迁移到另一台机器需按 `docs/codex/DEPENDENCY_DECISION.md` 重建环境，不能仅复制本目录。

## 三个现成例子

```powershell
.venv/Scripts/python.exe -B -X utf8 -m planning.demo --deterministic --request planning/examples/complete.json
.venv/Scripts/python.exe -B -X utf8 -m planning.demo --deterministic --request planning/examples/missing.json
.venv/Scripts/python.exe -B -X utf8 -m planning.demo --deterministic --request planning/examples/conflict.json
```

分别应看到等待用户确认、距离缺失、原文 2 GHz 与手工 3 GHz 冲突。加 `--json` 输出完整可检查状态；例如：

```powershell
.venv/Scripts/python.exe -B -X utf8 -m planning.demo --deterministic --request planning/examples/complete.json --json
```

手工参数使用 `{规范字段名: {value: 数字, unit: 单位}}`。主频字段为 frequency_ghz，距离字段为 distance_km；value 可以使用 MHz/m 等兼容单位，报告同时保留原值和规范值。独立 CLI 修改时需提交完整新请求，增加 revision 并更换 request_id；使用 `--expected-revision N` 检查预期版本。网页的独立补充框可以直接发送“频率改为3GHz”，由服务端受控合并并创建新版本。

## 真实 Qwen 模式

模型地址固定为本机 `127.0.0.1:18081`。服务已启动时，去掉 `--deterministic` 即可；加 `--no-fallback` 可以要求模型失败时明确失败：

```powershell
.venv/Scripts/python.exe -B -X utf8 -m planning.demo --request planning/examples/complete.json --no-fallback
```

如果本机服务未启动，可复用源仓库已有启动器（不会下载模型）：

```powershell
& 'E:/codex/项目/信号与AI/signal-formula-rag/.venv/Scripts/python.exe' -B -X utf8 'E:/codex/项目/信号与AI/signal-formula-rag/launch.py' --model-only
```

本入口不自动启动或关闭模型服务。`interpretation=llm`、模型身份和 usage 在报告诊断中可查；`deterministic` 表示确定性解析，`stub` 仅用于测试。检索当前是 `lexical_fallback`，没有宣称使用 dense embedding。

## 状态和问题处理

| 状态 | 含义与操作 |
|---|---|
| AWAITING_CONFIRMATION | 参数、条件和计划可供核对；当前入口不会继续计算。 |
| AWAITING_INPUT | 按问题清单补充或统一原文/手工值，再完整提交。 |
| NEEDS_MODEL | 当前目标、模型或专业依据不足；不能直接解释成现实通信不可行。 |
| FAILED | 查看失败节点、错误码和下一步；没有正式结果。 |

范围/多个候选值不会自动取一个。真实海面、多径、散射、双程和链路预算超出首版范围。明确请求自由空间基准可以规划，但不会证明真实环境满足自由空间或远场。

CLI 正常产生业务等待报告返回 exit 0，非法请求返回 2，执行失败返回 1。网页已实现限定范围的确认计算闭环；完整多 Agent 工程仍未完成。
