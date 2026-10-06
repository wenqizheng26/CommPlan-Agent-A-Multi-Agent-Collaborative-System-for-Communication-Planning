# 独立安装准备

这份说明面向接手安装与验证的开发者。资源工具仅取得固定字节并安全解包，不安装依赖、不执行包内程序。先准备独立目录和已核对的资源，随后才进行运行与验收；最终验收按冻结源码的完整矩阵记录。

## 资源工具

入口：[prepare_delivery_assets.ps1](../../scripts/prepare_delivery_assets.ps1)。需要 **Windows、PowerShell 7.4+、.NET 8+**；使用可信宿主工具引导，不能用待安装的旧 Python 解开新解释器。所有输入和输出在本次新 run 内，不借用开发目录的 venv、数据库、缓存或 models 联接。

创建本次唯一目录，例如 `E:\cleanroom\commplan-B3b-<UTC>-<ID>\`，保留 `downloads/`、`evidence/`、解包 staging 与失败日志。选定目录由总负责人分配，测试使用自己的临时目录。一个 run 只由一个操作人/进程写入，不能让外部程序同时替换目录或资源。

工具有 `Download` 和 `Extract` 两种模式。输出已存在一律失败，不覆盖旧包、旧环境或旧证据。

| 参数 | 用途 |
| --- | --- |
| `RunRoot` | 已存在的本次绝对本地目录；不允许卷根或目录联接。所有输入、输出和证据须在其中 |
| `ExpectedSize`、`ExpectedSha256` | 必需，精确资源字节数与 64 位十六进制 SHA256；解包前再次核对 |
| `Destination` | 新下载文件或新解包目录的绝对路径 |
| `ManifestOut` | 新 JSON 证据文件的绝对路径，须在输出目录外 |
| `Uri` | Download 的固定 HTTPS 来源；不允许凭据、HTTP、latest 路径或关闭 TLS 校验 |
| `Archive`、`Format` | Extract 的普通本地输入文件和显式 `Zip`、`Tar`、`TarGzip` |
| `AllowedTopLevel` | Extract 必需，第一层名称的字面量数组，不接受通配符 |
| `MaxMembers` | 默认 20000；普通成员和 TAR 扩展元数据均计数 |
| `MaxMemberBytes` | 默认 536870912（512 MiB）；声明与实际普通成员字节均有界 |
| `MaxTotalBytes` | 默认 2147483648（2 GiB）；包括文件和 TAR 扩展元数据正文 |

GGUF 是普通下载文件，由精确 ExpectedSize 控制，不使用解包总量作为下载大小上限。ZIP 中央目录额外上限 16 MiB、TAR 单个路径扩展元数据上限 1 MiB；TAR 解压读取预算还包括有界的 header/padding。提高限额前确认真实成员及理由，不能静默自动抬高。

以下示例使用新的独立 run。2026-10-06 已从固定来源取得 Python、Node、MinGit、llama 四个包，大小/SHA、解包及版本加载均通过；原始记录见项目总账 R49。嵌入权重已实际下载通过，9B 下载进行中；最终冻结包安装验收按后续批次执行：

```powershell
$run = 'E:\cleanroom\commplan-B3b-<UTC>-<ID>'
$tool = Join-Path $PWD 'scripts\prepare_delivery_assets.ps1'
pwsh -NoProfile -NonInteractive -File $tool -Mode Download -RunRoot $run -Uri 'https://nodejs.org/dist/v22.23.3/node-v22.23.3-win-x64.zip' -ExpectedSize 35574076 -ExpectedSha256 '2b0ff57b049cda1bbcea2240eec20467018713c1efe1f7360c2681859b90ed71' -Destination (Join-Path $run 'downloads\node.zip') -ManifestOut (Join-Path $run 'evidence\node-download.json')
if ($LASTEXITCODE -ne 0) { throw '资源取得失败' }
pwsh -NoProfile -NonInteractive -File $tool -Mode Extract -RunRoot $run -Format Zip -Archive (Join-Path $run 'downloads\node.zip') -ExpectedSize 35574076 -ExpectedSha256 '2b0ff57b049cda1bbcea2240eec20467018713c1efe1f7360c2681859b90ed71' -Destination (Join-Path $run 'tools\node') -AllowedTopLevel 'node-v22.23.3-win-x64' -ManifestOut (Join-Path $run 'evidence\node-extract.json')
if ($LASTEXITCODE -ne 0) { throw '解包失败，禁止启用输出' }
```

多个顶层名称须在 PowerShell 7.4+ 中以真正的字符串数组调用脚本；原生 `pwsh -File` 不会传递该数组。实际 MinGit 2.56.0 包的顶层是 `cmd`、`etc`、`LICENSE.txt`、`ucrt64`、`usr`，校验已下载文件后这样解包：

```powershell
$gitTop = @('cmd','etc','LICENSE.txt','ucrt64','usr')
& $tool -Mode Extract -RunRoot $run -Format Zip -Archive (Join-Path $run 'downloads\mingit.zip') -ExpectedSize 39602073 -ExpectedSha256 '064b440ff870ed5198527e8f3a92cdf5bd2fd0fedf5e718af95e3fdaddeff718' -Destination (Join-Path $run 'tools\git') -AllowedTopLevel $gitTop -ManifestOut (Join-Path $run 'evidence\git-extract.json')
```

Download 流式读入唯一 partial 文件，严格控制大小、SHA 和 30 分钟操作期限，最多五次 HTTPS 重定向。只有校验通过才发布新文件。Extract 先在不写成员的情况下核对所有路径、类型、数量、字节及内容，再第二遍写新 staging；输入使用禁止共享写入的句柄，前后 SHA 一致才发布。

解包接受普通文件/目录，拒绝软硬链接、reparse 标志、特殊文件、稀疏 TAR、路径穿越、UNC/drive/ADS、设备名、尾点/尾空格、大小写重名、父组件为文件、文件/目录冲突以及已有祖先联接。不恢复 ACL 或 owner。ZIP64、多卷、加密、非 store/deflate ZIP 不支持；TAR 接受普通 POSIX/GNU 长路径和有限 PAX 字段，其他类型/扩展先拒绝并核实，不回退宽松提取器。

JSON 记录来源、预期/实际输入大小与 SHA、限额、成员类型/大小/实际 SHA、起止 UTC 和 PASSED/FAILED。参数/路径预检失败不会写不安全的证据路径；操作开始后的失败保存 FAILED 清单和本次 partial/staging，退出码非零。失败输出不启用，另建新 run 再尝试。`LibraryOnly` 只加载实现供离线测试，`FromFixtureStream` 的清单明确标 `TRANSPORT_FIXTURE`；它与真实 HTTPS 取得证据分开。

## 固定资源

以下版本与来源在方案审核中已固定。**Node 22.23.3、普通 MinGit 2.56.0 已双方选定**，四个 runtime 已完成 10-06 独立预检的取得/解包/加载；模型取得按上文实际状态记录，启用和最终验收继续按批次执行。Python 是 Astral 二进制，不是 PSF Windows installer。官方来源、固定版本、大小与 SHA 是资源取得标准；许可原文及组件通知保留，签名来源记录可补充，不新增 GPG 工具门禁。

| 资源 | 字节数 | SHA256 / 来源 |
| --- | --- | --- |
| Astral CPython 3.12.15/20261001 Windows x64 install_only_stripped | 22013771 | `52124cee54126f3f360eaa378288f6f64c402c983a3c14c95eff67f4af986aaa`；[固定 tar.gz](https://github.com/astral-sh/python-build-standalone/releases/download/20261001/cpython-3.12.15%2B20261001-x86_64-pc-windows-msvc-install_only_stripped.tar.gz) |
| Node 22.23.3 Windows x64 | 35574076 | `2b0ff57b049cda1bbcea2240eec20467018713c1efe1f7360c2681859b90ed71`；[固定 ZIP](https://nodejs.org/dist/v22.23.3/node-v22.23.3-win-x64.zip)、[官方 SHASUMS](https://nodejs.org/dist/v22.23.3/SHASUMS256.txt) |
| 普通 MinGit 2.56.0 64-bit | 39602073 | `064b440ff870ed5198527e8f3a92cdf5bd2fd0fedf5e718af95e3fdaddeff718`；[固定 ZIP](https://github.com/git-for-windows/git/releases/download/v2.56.0.windows.1/MinGit-2.56.0-64-bit.zip) |
| llama.cpp b10950 Windows Vulkan x64 | 31673509 | `787061f560eb2f14db7c03396cb56e59759b6dfccd162dc341b10cfa3bd5b779`；[固定 ZIP](https://github.com/ggml-org/llama.cpp/releases/download/b10950/llama-b10950-bin-win-vulkan-x64.zip) |
| Qwen3.5-9B-Q4_K_M.gguf，revision 3885219b6810b007914f3a7950a8d1b469d598a5 | 5680522464 | `03b74727a860a56338e042c4420bb3f04b2fec5734175f4cb9fa853daf52b7e8`；[固定 GGUF](https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/resolve/3885219b6810b007914f3a7950a8d1b469d598a5/Qwen3.5-9B-Q4_K_M.gguf) |
| Qwen3-Embedding-0.6B-Q8_0.gguf，revision 370f27d7550e0def9b39c1f16d3fbaa13aa67728 | 639150592 | `06507c7b42688469c4e7298b0a1e16deff06caf291cf0a5b278c308249c3e439`；[固定 GGUF](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B-GGUF/resolve/370f27d7550e0def9b39c1f16d3fbaa13aa67728/Qwen3-Embedding-0.6B-Q8_0.gguf) |

权重不入交付包，必须真正从固定来源取得。本地已校验副本和 HEAD 成功都不能写成实际下载成功。真实包的成员与许可证仍须核对；Python/Node 顶层候选分别为 `python`、`node-v22.23.3-win-x64`，MinGit 第一层按上文五个字面名称；llama 本次包为 52 个根文件，其精确名单与逐成员 SHA 留在预检清单，不能用 `*` 放行。

模型放置按 [config/models.json](../../config/models.json) 当前 registry 的路径，9B 生成与 embedding CPU 服务的 alias/参数在实例批固定。旧 `runtime/runtime_config.json` 是历史 4B/BGE 配置，不作为当前 registry 的替代；未纳入源码包的 setup_runtime/runtime 也不能当现有交付入口。

## ITU 资料取得与放置

资料检索使用 [documents/manifest.json](../../knowledge/documents/manifest.json) 登记的三个固定英文版本。该清单标为 `redistributable=false`，正式交付须纳入取得步骤，原 PDF 不入对外交付包。在线准备时从以下 ITU 官方固定 PDF 链接下载到本次 `downloads/itu/`，用资源工具 `Download` 的精确大小和 SHA 核对；原始下载证据须保留。

| 文件 | 字节数 | SHA256 / 固定来源 |
| --- | --- | --- |
| P.525-5.pdf（11/2024） | 246217 | `55ff9bf5bb4534b91863fd84d760fe689e2f969b91db0ea786717fd078df1da5`；[官方 PDF](https://www.itu.int/dms_pubrec/itu-r/rec/p/R-REC-P.525-5-202411-I!!PDF-E.pdf) |
| P.530-19.pdf（09/2025） | 2260727 | `07fb5e005b873120569e7d32442bfa867153a179ba75fac4f952017c2f5977f2`；[官方 PDF](https://www.itu.int/dms_pubrec/itu-r/rec/p/R-REC-P.530-19-202509-I!!PDF-E.pdf) |
| P.453-14.pdf（08/2019） | 4730459 | `fd163ef75cb4fd03848d4fe1fc0a043cb78e0edc164ba29a6bb69209204c17a0`；[官方 PDF](https://www.itu.int/dms_pubrec/itu-r/rec/p/R-REC-P.453-14-201908-I!!PDF-E.pdf) |

在本次普通源码目录中新建 `knowledge/sources/itu/`，将已校验的三个文件按表中名称复制进去；目标已有文件时先停止核实，不覆盖、不建开发模型或资料目录的联接。再次核对目标文件 SHA 与登记清单一致，再执行完整验证源码中的 `python -B -X utf8 -m unittest discover -s tests -p test_retrieval_bilingual_cases.py`，要求索引核对项实际执行且没有缺源跳过。保留下载、安装路径、逐文件 SHA 和测试结果；不要把检索降级或缺源跳过计作通过。

10-06 本机独立预检已真正下载三个原件并按上述路径安装，8 项测试无跳过通过，冻结的 48 条标签及 314/305 chunk 索引核对通过。这个结果证明固定资料与索引对应；真实 embedding 检索与最终离线验收仍单列记录。

当前 168 成员的源码预检 ZIP 尚未收录本说明、资源工具和完整验证层。正式交付组装须包含这些文件并核对全部包内链接；本预检 ZIP 不能作为完整交付包。

## 独立 Python 和依赖

获准实际解包后再执行新基础 Python，记录版本、绝对路径、base_prefix 和架构。新建 venv，清本次子进程的 PYTHONPATH、PYTHONHOME 和继承 PIP_*，再设置 `PIP_CONFIG_FILE` 为**该新 Python 的 `os.devnull` 精确值**；Windows 预期为小写 `nul`。保存新 pip 版本、`pip config debug`、明确的索引/离线 wheelhouse 参数。大写 `NUL` 与 pip 的精确比较不符；`pip --isolated` 单独也不能跳过 global/site 配置。

环境分开：app-venv 安装 planning+docs，服务正常运行与报告导出；minimal-venv 仅 planning，复现 CI 最小依赖；full-venv 使用同提交的完整验证层和全依赖。不能从开发目录补文件或插入 PYTHONPATH。full 安装按当前 [Windows CI](../../.github/workflows/tests.yml) 的三个独立解析步骤：

```powershell
# 只在本次独立 Python、完整验证源码及校验过的 wheelhouse 均已取得后执行。
& $fullPython -B -I -m pip install --no-index --find-links $fullWheels 'torch==2.8.0+cpu'
if ($LASTEXITCODE -ne 0) { throw 'torch 安装失败' }
& $fullPython -B -I -m pip install --no-index --find-links $fullWheels -r (Join-Path $fullSource 'requirements.lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'lock 安装失败' }
& $fullPython -B -I -m pip install --no-index --find-links $fullWheels -r (Join-Path $fullSource 'requirements-docs.txt')
if ($LASTEXITCODE -ne 0) { throw 'docs 安装失败' }
& $fullPython -B -I -m pip check
if ($LASTEXITCODE -ne 0) { throw '依赖检查失败' }
```

在线收集 wheel 也分 torch → lock → docs，保留每步解析和最终 hash 清单。平台缺轮子或锁冲突先修正，不降版本凑通过。本机只读查询 `LongPathsEnabled=1`；full-venv Torch 长路径是宿主前提。目标机先读取该值、记录实际根路径和最长成员；不偷偷改注册表。Windows、驱动和系统运行库仍与宿主共享，须记录限制。

## 独立 Git、Node 与服务窗口

固定 Node 用绝对路径运行内建测试，不启用 npm/Corepack 全局安装。清本次 Node 子进程的 NODE_OPTIONS/NODE_PATH。固定 MinGit 仅用于本次临时仓库和验证，不操作项目现有 worktree/标签。

Git 子进程先清继承的 GIT_*，再设 `GIT_CONFIG_NOSYSTEM=1`、`GIT_CONFIG_GLOBAL=<本次普通配置文件>`、`GIT_TEMPLATE_DIR=<本次新空目录>`。XDG 配置目录也指向本次空目录；不使用 NUL 作为配置路径，不更改 HOME、用户/系统 PATH 或开发 config。受控 global 明确对齐 Windows CI 默认：

```ini
[core]
    autocrlf = true
    symlinks = false
    fscache = true
```

保留配置原字节 SHA，不含 include、alias、filter 或 hook 注入。测试自己显式设置的 CRLF/config 优先规则照常保留并记录。MinGit clean-filter、worktree、外部支持程序与实际 ZIP 组件须后续真实验证。

模型 **18081/18084** 与开发 B2c 的真实 9B 共用：负责人先在总账公布操作人、批次、实例根、起止 UTC 和端口的独占窗口，避开 B2c。启动/停止须在每次有作用的操作核对实例归属，不能一次检查后调用会停别的实例的全局启动/关闭器。当前资源工具不启动模型/工作台、不占端口、不杀进程。

## 验证与后续

[test_planning_delivery_assets.py](../../tests/test_planning_delivery_assets.py) 在现 Windows CI planning-minimal 的 `test_planning_*.py` 和 full job 中自动发现。测试实际调用 `pwsh -NoProfile -NonInteractive`，缺工具或前提不符就失败，不能 skip。小 fixture 覆盖正常 ZIP/TAR/GZIP/PAX、输入大小/SHA、损坏/CRC、路径/重名/冲突/软硬链接/特殊项/已有 junction、输入输出重叠、覆盖与计数/字节/元数据限制；假下载 stream 只验证同一校验/发布管道，记录 TRANSPORT_FIXTURE。

10-06 预检已取得四个 runtime、独立源码验证层及固定依赖 wheel；新 app-venv 从本批 wheelhouse 安装，源码预检包 Python 93 项、Node 33 项与 HTTP 创建/确认/恢复通过，整套 Node 113 项通过。最小环境首轮 126 项出现两处空 Git 模板 fixture 错误和一次 Windows 请求连接中止；fixture 已补建自有 info 目录，边界复测 24 项（1 权限 skip）通过。独立完整环境安装及 pip check 通过，601 项首轮为 1 error、2 skip：跨域拒绝 POST 收到 Win10054，符号链接权限不可用，ITU 尚未安装。ITU 后续实际下载/索引验证见上节；原失败记录保留，完整矩阵仍未通过。

针对拒绝 POST 的最小实验已复现 Windows 连接竞态：原代码普通请求 595/600 返回 403，5 次 Win10053；请求头和正文间隔 5 ms 时 120/120 失败。只在诊断内存中调用既有有界 `drain` 后，对应 600/600 和 120/120 返回 403。生产源码未改，业务修补、当前回归、真实 GPU/模型、服务实例及关闭释放继续按批次验证。诊断不能替代实际修补验证。

最终执行完整自动矩阵、三条案例和 teacher20、适用/拒绝/变更确认、保存恢复、报告导出、目标浏览器和准确提交 CI。源码/环境/步骤/预期/实测/限制分别记录。离线采用已确认的关 Wi-Fi 方法：所有下载/安装先完成，核网卡/隧道/直接 IP 与域名失败及回环；离线脚本自行落盘或用户执行浏览器清单，联网后双方读证据。当前首微批不切网络。

10-20 冻结、10-21～23 验包、10-24 前交付；不提前冻结。资源取得、归档恢复、自动测试、真实模型、浏览器、CI 和 M1 验收是各自的验证记录。
