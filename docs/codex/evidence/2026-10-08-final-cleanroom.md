# 2026-10-07～08 真实模型回归（B2c）与干净环境完整矩阵

执行：Claude。依据：用户 10-06 授权接管（项目总账 R60）。相关修补均为单方审核，准确 head CI 全绿后合入。原始输出不在仓库内，路径列在每节末尾。

## 环境

- 机器：Windows 11，RTX 4060 Laptop 8 GB；另有 Radeon 610M 核显。
- 模型：Qwen3.5-9B Q4_K_M，注册表 revision `3885219b6810b007914f3a7950a8d1b469d598a5`，llama.cpp b10950 Vulkan，上下文 16384，温度 0。
- B2c：只开 chat，不开 embedding，检索走词项。
- 干净环境：`E:\cleanroom\commplan-B3b-20261006T1052Z-7f298c`。
  - 固定 Python 3.12.15、MinGit 2.56.0、Node 22.23.3。
  - 独立 venv，pip 不读用户配置，Git 不读系统和用户配置。
  - 源码从 GitHub 重新克隆，0 个未提交文件。

## 真实模型回归

| 项 | 源码 | 结果 |
|---|---|---|
| teacher20（含 3 条原题） | de6b522 三遍；b520b49；正式包 cb6fb63 | 每遍 20/20，source_stable=true |
| heldout21（留出集） | de6b522、b520b49 | 19/21。heldout_06、heldout_11 两次相同，自 cc039b3 起一直失败；属留出参考项，不按其改代码 |
| eval_m1（main、variant、offline_equivalence，共 28 条） | f849d37 | 28/28（de6b522 26/28，b520b49 27/28） |
| hard rules（8 条） | de6b522、b520b49 | 通过 |
| week4 | f849d37 | 抽取 5/5，追问 16/16，模型调用 8 次、同意 8 次，链路通过 |
| week4_completion | f849d37 | 9/9，全部角色走模型 |

f849d37 与最终 main cb6fb63 只差 Agent 名称（PR25），不影响上述评测的逻辑。

原始输出：`CommPlan-Agent-M1/outputs/teacher-eval-b2c/`、`b2c-de6b522/`、`b2c-b520b49/`、`b2c-f849d37/`。中断或作废的运行目录带 `interrupted`、`igpu-timeouts` 后缀，原样保留。

## 回归中发现并已修的问题

| PR | 问题 | 性质 |
|---|---|---|
| 19 | CI 临时目录是 8.3 短名，Git 重建配不上 worktree 指针 | 工具缺陷 |
| 20 | week4 两个 runner 建副本时缺事实表引用的文件 | runner 过时 |
| 21、23 | 模型引用「……的达标判断」「评估 A岸站 到 B岛站」作 link_margin 证据，被语义检查和来源校验先后拒绝（main_07、conflict_2） | 产品缺陷 |
| 22 | 双语检索金标的 index 指纹没随 PR16 的 LF 更新（只在装了 ITU 时报错） | 测试数据 |
| 24 | 注册表写死 `--device Vulkan1`；重启后 Vulkan 编号对调，9B 落到核显，处理提示约 40 tok/s（原约 580），调用全部超时。改为默认 auto，按名称优先选独显 | 产品缺陷 |

另有 PR25：用户 10-08 决定，Agent 名称中英文都改回原名。

## 干净环境完整矩阵（main cb6fb63）

| 步骤 | 结果 |
|---|---|
| 全量 Python | 629 项 OK；2 skip 都是本账户没有 symlink 权限；装有 3 份 ITU 资料 |
| Node | 113/113 |
| 正式包构建并校验 | PASS；168 个文件；版本 0.2.0-dev；SHA256 `1a1c2f22b71f67a40921ad230444129ce688d7265f7f271cee4634a33cb77cb9` |
| 解包与资源 | 按字面顶层白名单解包；9B、embedding、runtime、ITU 共 57 个文件与参照 SHA256 一致；app 环境 pip check 通过 |
| 自有实例 | `scripts/owned_instance.py start`：chat（auto 选到 RTX 4060）、embedding 和工作台 18098 均按 PID、创建时间和命令行核对，状态 running |
| 正式包 teacher20 | 20/20，source_stable=true，来源记为包内 BUILD_INFO |
| HTTP | 8/8：案例 1 确认后完成；案例 3 修改后旧确认 STALE_REVISION，新稿确认后完成；案例 2 停在补充，强行确认返回 NOT_CONFIRMABLE |
| Chrome 152 | 三条案例在页面中以“本机 Qwen”跑完；案例 1、3 打开报告，用 Chrome 打印成 PDF（201 KB、255 KB） |
| 重启恢复 | 停止后只用同一数据库重启工作台，三个任务原样读回 3/3 |
| 端口 | 全部停止后，18081/18084/18098 无监听 |

截图与 PDF：父目录 `项目材料/M1-当前结果-cb6fb63/`（附 SHA256SUMS）。全部原始证据：`final-cb6fb63/evidence/`。

## 限制

- 未断网：最终离线验收按 U14 由用户关闭 Wi-Fi 后执行。
- 包内不含模型权重：权重按独立安装说明另行取得并核对 SHA256。
- 页面阶段只按 1.5 s 采样，记录到“解析中”和停下两个状态，不是逐节点轨迹。
- 本轮 B2c 与 cleanroom 都是 Claude 单方执行；Codex 可按总账补审。
