# CommPlan-Agent Planning Workbench

**当前 Demo：在用户明确采用自由空间假设后，计算单链路单程路径损耗（FSPL）。** 输入、缺项与冲突处理、参数确认、确定性计算、硬校验、结构化审查和任务恢复已连成可操作工作流。结果只代表自由空间基准，不能证明实际海面链路可用。总体架构流程图与输入、结果并列展示；图上高亮表示观测到的活动与责任关系，不逐条声称 LangGraph 直接调用。

**本 Demo 主入口是 `start.cmd` / `启动.cmd` → `start_commplan.py` → Planning Workbench（127.0.0.1:18082）。** 早期 Formula RAG 网页应用已从当前源码树移除；工作台仍复用 `formula_rag/` 的公式、解析和检索代码，`launch.py` 仅提供本地模型启动命令。

## Windows 首次设置

准备 Python **3.12** 和 Node.js（Node 仅用于开发测试）。在解压后的仓库/源码包根目录运行：

```bat
setup_planning.cmd
```

脚本创建 `.venv`，安装 `requirements-planning.txt`，执行 `pip check`。若 `py` 或 `python` 未在 PATH，可先将 `COMMPLAN_PYTHON` 设置为 Python 3.12 的 `python.exe` 完整路径再运行。此最小 Planning 环境无需 Torch、模型权重或 llama runtime；正常确定性模式也无需模型服务。

日常双击 `start.cmd`（ASCII 文件名）或 `启动.cmd`。启动器默认尝试项目内 `models/signal-formula-qwen3/` 的本地模型；未找到模型时仍打开确定性工作台。页面默认选“确定性规则”；进入高级设置才可选择本机 Qwen。只启工作台：

```bat
start.cmd --without-model
```

进阶选项：`--asset-root <目录>` 或 `COMMPLAN_ASSET_ROOT` 指向含 `runtime_config.json`、权重和 llama 可执行文件的资源根目录；`--cpu` 用于本次新启动模型，`--port` / `--db` 用于新工作台实例。启动器不下载模型，也不更改防火墙设置。模型在 127.0.0.1:18081，工作台默认在 127.0.0.1:18082。

**source Demo ZIP 不含模型、llama 二进制、Python、虚拟环境或用户任务数据。** 若自行准备本地模型，保持 `runtime_config.json` 中 `generation.path` 和 `generation.executable` 相对资源根目录有效。项目内资源目录被 `.gitignore` 排除，不应提交或上传。可用 `--without-model` 完全跳过模型启动。

关闭 CMD 窗口不会停止启动器在后台创建的服务。需要停服务时，先查看 `runtime/commplan-web-<port>.pid` 和 `runtime/commplan-model.pid` 对应进程的命令行/可执行路径，确认属于本目录和本次实例后再停止对应 PID；不要按进程名批量结束，也不要停止只是被启动器复用的外部模型服务。前台 `planning/run_planning.cmd` 可在其窗口按 Ctrl+C 结束。任务保存在 `outputs/planning.sqlite`；该目录不进 source ZIP。

## 使用

输入“按自由空间基准计算，频率 2 GHz，距离 1 km，求路径损耗。” → 核对参数/来源/模型条件 → 勾选确认 → 运行后得到约 **98.42 dB**。编辑为 3 GHz 会使旧确认和结果失效，重新确认后约为 **101.94 dB**。页面的最近任务可恢复保存状态，历史版本只读。

缺参和原文/手工冲突会阻止确认；多问题可部分回答并继续保存。`2±0.1 GHz` 的区间保留上下界，2 GHz / 1 km 的对应损耗约 **97.98–98.84 dB**，不是置信区间。`2 GHz 或 3 GHz` 会分别计算，不当作连续范围。没有明确误差边界的“大约”需要澄清。当前仅频率、距离支持区间或候选；每个离散参数最多 8 个候选、一次最多 64 个端点/候选组合。

当前需求解析可用确定性规则或可选 Qwen；计算建议与审查也可尝试本地 Qwen，失败会明确降级。**专业数值始终由登记公式的确定性工具计算并硬校验。** 总控是有上限的程序调度策略，不是自由 Agent 路由。未实现真实海面/散射传播、完整链路预算、判断能否通信或比较方案。

[详细操作和独立 CLI](planning/README.md) · [第三方资源与许可](THIRD_PARTY.md) · [当前验证记录](docs/demo/VALIDATION.md)

## 当前验证状态

权威验收状态见 [VALIDATION.md](docs/demo/VALIDATION.md)。阶段源码测试、内置浏览器验收、目标 Chrome、干净安装、独立审查及 GitHub CI 分别记录；只有真实执行后才标 PASS。演示视频尚未发布，录制说明见 [RECORDING.md](docs/demo/RECORDING.md)。

项目代码采用 [MIT 许可证](LICENSE)。现有公式资料只按链接和简短说明引用；模型和本地运行库各遵循其上游许可。安装依赖由 `requirements-planning.txt` 固定，source Demo 不再分发第三方模型或 Python 包。
