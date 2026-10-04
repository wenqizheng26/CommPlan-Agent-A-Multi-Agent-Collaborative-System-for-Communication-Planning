# 源码包构建与预检

本说明面向接手的开发者。源码包包含工作台源码、运行配置、公式与事实资源，以及包内列出的自动验证材料。模型权重、推理运行时、Python 环境和用户任务数据由运行环境另行准备。

`0.2.0-dev` 表示开发预检包。生成 ZIP、校验通过、自动测试通过和工作台启动，分别记录结果；这些步骤不能证明 M1、真实模型、目标浏览器或完整独立安装验收通过。当前状态见 [验收状态矩阵](../codex/M1_ACCEPTANCE_STATUS.md)。

## 构建

构建需要 Git 和已安装仓库依赖的 Python 3.12，从 Git 工作区根目录执行。输出使用新的路径，保存每次构建结果及日志：

```powershell
python -B -X utf8 scripts/build_planning_release.py --version 0.2.0-dev --output outputs/releases/source-precheck.zip
```

需要仅从已提交源码构建时，增加 `--require-clean`：构建器先检查工作区身份与实际修改，再从该 HEAD 的原始 Git blob 读取受审成员。缺失、未提交、未跟踪或被忽略的成员以及被索引标志隐藏的修改仍会拒绝构建。默认开发预检使用工作区实际字节，保留检出换行和未提交内容，并如实记录 dirty 状态。

通过严格工作区 clean 检查后，同一 HEAD 的正式包源码成员、`source_inputs_sha256` 与包内 `build_fingerprint` 可重现，不受工作区 LF、CRLF 或混合换行影响。构建时间、工作区配置和 ZIP 时间属于当次审计资料，因此不同构建的整个 ZIP SHA256 不保证相同；这项约定也不替代历史归档对原实际文件字节的保存。

当前 Git 对象中的 `.cmd` 成员为 LF，正式包保留这些原始字节。完整安装与启动步骤仍须按最终独立环境验收验证；源码预检中的 Python HTTP smoke 不代表批处理入口已经完整通过。

构建器拒绝覆盖已有输出，并在发布 ZIP 前复查工作区源码身份、成员内容、fingerprint 和 `core.autocrlf`。本机 NTFS 卷上通过同目录硬链接发布完成文件；其他文件系统尚未验证。构建失败时保留实际错误，修正后使用新路径。存在未提交内容的源码包不能写成正式验收版。

构建器按明确的成员清单收集文件。新增源码需要审核并登记；模型、运行时、缓存、数据库、环境、仓库元数据和未登记成员不能借此进入交付包。历史归档另用完整快照流程，不能使用这个源码成员清单删减历史内容。

## 校验

```powershell
python -B -X utf8 scripts/validate_planning_release.py outputs/releases/source-precheck.zip
Get-FileHash -Algorithm SHA256 outputs/releases/source-precheck.zip
```

校验包括成员与 SHA256、元数据、路径安全、解包后的源码 fingerprint，以及默认启用的确定性工作台 smoke。`--no-smoke` 只做静态预检，结果不包含运行检查；默认 smoke 也只覆盖其实际执行步骤。

需要运行包内的确定性测试子集时，准备 Node（CI 使用 Node 22；本机预检使用的版本另记），增加 `--offline-tests`。另行运行包边界测试 `test_planning_release.py` 时也需要 Git，其仓库操作只发生在临时测试目录：

```powershell
python -B -X utf8 scripts/validate_planning_release.py outputs/releases/source-precheck.zip --offline-tests
```

Python 子集为 `test_core`、`test_teacher_tools`、`test_teacher_cases_format`、`test_calculation_plans` 和 `test_teacher_path`；Node 子集为 `planning_m1.test.mjs` 和 `planning_report.test.mjs`。校验结果分别记录静态检查、smoke 和子集执行结果，并保留解释器版本、命令、计数与跳过项。它们使用当前解释器及已安装依赖，尚未证明独立安装或操作系统断网；最终完整离线测试矩阵仍须另行执行。

包内保留 `scripts/eval_teacher.py` 及对应的原始老师用例，便于核对源码；本批不运行真实模型。该评测脚本的断言与证据门禁仍在 B2b 改进范围内，当前通过结果不能据此作为最终验收结论。

包内 `BUILD_INFO.json` 记录源码提交、是否存在未提交内容、实际源码成员摘要、版本、构建时间与验证记录入口。`source_content_mode` 区分 `git-blobs` 和 `worktree-bytes`；`build_fingerprint` 对应实际包内字节，`workspace_build_fingerprint` 与 `source_core_autocrlf` 单列本次工作区观察值。旧包若完全缺少这三个字段，校验结果标为 `legacy-worktree-bytes`，仅验证原契约，不追认 Git blob 来源；部分缺字段会拒绝。

`MANIFEST.json` 记录实际成员的校验值。接手时将它们与原始构建日志一并保存；包外 SHA256 用于核对取得的 ZIP，包内成员校验用于核对内容，两者都不能自行证明发布者身份或元数据声称的 Git 来源。

## 文档与材料范围

本包保留文档导航引用的设计和历史任务说明，包括 `WORKBENCH_UI.md`、`TEACHER_TASKS.md` 与 `DEMO_HANDOFF_V4.md`。历史任务中的分支、日期、限制和步骤描述当时的工作，不是本次实施授权；当前状态与验收范围以包内验收状态矩阵及对应源码为准。

文档仍引用 `docs/codex/evidence/` 的历史记录。该目录中的原始日志、截图、运行产物以及父目录的图稿、演示、独立研究文稿没有进入本源码预检包；完整仓库与历史归档保存原材料，最终交付批次另按版本选择必要证据。当前 ZIP 不是完整历史归档或最终成果材料包。

## 后续验收

完整验收还要按最终交付说明，在隔离目录独立安装 Python 和依赖，取得并校验指定模型与推理运行时，完成约定的离线自动测试、三条案例及老师评测集、适用与拒绝路径、修改再确认、保存恢复、浏览器与报告打印、关闭端口，并核对准确提交的 CI。

模型下载与安装说明、三类读者的成果材料、最终标签及完整验收证据按后续交付批次补齐。冻结标签与正式包遵守已确认日期；本工具预检不提前冻结版本。
