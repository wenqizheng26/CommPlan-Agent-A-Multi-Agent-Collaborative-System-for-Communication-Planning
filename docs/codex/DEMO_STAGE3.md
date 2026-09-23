# Demo Stage 3 — Delivery Engineering

实施范围遵循 [V4](DEMO_HANDOFF_V4.md)，仅交付当前 FSPL-stage Planning Workbench。模型权重和 llama runtime 留在被 Git 忽略的本机项目目录，不属于 source ZIP，也不提交或推送。

## 本地资源迁入

- 从实际使用的外部 `signal-formula-rag` asset root 核对配置、相对路径和目标磁盘空间后，先复制 63 个文件共 2,683,695,110 bytes 至项目内 `models/signal-formula-qwen3/`，逐文件 SHA-256 相符；外部源目录保留可回滚。
- 保留原有 `models/Qwen3-4B-GGUF/`、`runtime/llama.cpp-b10950/` 相对结构和随资源提供的许可文件；项目内 `runtime_config.json` 的权重、llama 可执行文件和嵌入路径均为相对引用。
- 启动器默认优先项目内资源，同时保留 `--asset-root` / `COMMPLAN_ASSET_ROOT` 覆盖；测试覆盖优先级、回退和 `--without-model` 不访问模型资源。
- 实际项目内 `llama-server.exe` 在 18081 启动，`/health` 为 `ok`、`/v1/models` 含 `signal-formula-qwen3`；工作台模型状态为 ready，真实 Qwen 需求、计算建议和审查调用完成 FSPL 任务，确定性原始值为 `98.42059991327963` dB。

## 交付工程

- 最小 Planning `setup_planning.cmd` 固定 Python 3.12 合同，`start.cmd` 为 ASCII 启动别名；启动/停止进程身份与复用边界写入 README。
- source ZIP 由显式清单打包，拒绝符号链接/重解析点并生成 `VERSION`、`BUILD_INFO.json`、SHA-256 `MANIFEST.json`；验证器先验路径/大小/哈希，再解压并运行 HTTP 创建、确认、重启恢复 smoke。
- ZIP 排除 `models/`、`runtime/`、`.venv/`、`outputs/`、测试及工作区元数据。README、Planning 使用说明和 THIRD_PARTY 与此分发边界一致。
- Windows CI 分为 Planning minimal 与 legacy full，两者远端状态仍待实际 push/运行验证。

## Stage 3 验证

- `.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests -p 'test_*.py'`：233 OK，1 symlink 创建权限 skip。
- `node --test tests/planning_*.test.mjs`：24 PASS。
- `.venv\Scripts\python.exe -m pip check`：PASS。
- 源码包预提交候选：builder / validator / 解压 HTTP smoke PASS。全新解压后 `setup_planning.cmd`、`pip check` 和 HTTP smoke PASS；网络沙箱内首次 pip 下载被拒绝，获准的同目录重试成功。

预提交 ZIP 的 `source_dirty=true`，不充当正式发布包。提交后须以 `--require-clean` 重建并再次验证；目标 Chrome、独立最终审查、远端 CI、PR/main/tag 属 Stage 4/5 门禁。浏览器中的默认展开架构图已目视核对，但它不能代替目标 Chrome 验收。
