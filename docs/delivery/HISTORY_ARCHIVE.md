# 历史文件归档工具

当前实现 `plan`、`capture`、`verify`（范围 `FILE_PAYLOAD`），`restore`、`verify-restored`（把已封口批次恢复到全新的 `original/` 区），以及 `reconstruct-git`、`verify-reconstructed-git`（从已恢复的原字节另建可用 Git 历史、bundle 和工作树）。只验证过独立临时 fixture；真实项目捕获和恢复要另开安全窗口。依赖可用性恢复和保留版本脱离仍需按真实工程验证。

## 运行

使用 Windows、Python 3.12、支持数据流和文件身份查询的文件系统。当前普通账户读取文件、数据流与 owner/group/DACL，不取得管理员或备份权限，不更改源权限和系统长路径设置。

`dependencies.json` 是精确外部依赖根列表。没有外部根时写 `[]`；已经处于项目树内的目标不重复登记。

```json
[
  {"dependency_id": "base-python", "path": "E:\\fixture\\external-python"}
]
```

从工程根执行，每次使用新计划文件、新批次目录，二者都位于所有源根之外：

```powershell
python -B -X utf8 scripts/project_archive.py plan --project-root E:\fixture\project --dependencies E:\fixture\dependencies.json --output E:\fixture\plan.json
python -B -X utf8 scripts/project_archive.py capture --plan E:\fixture\plan.json --window-record E:\fixture\window.json --output E:\fixture\batch-001
```

窗口记录的 `approved_root_paths` 顺序与计划的 `roots[].path` 相同。实际窗口由 Codex 与 Claude 在停止写入后记录；JSON 本身不提供身份认证。

```json
{
  "scope": "FILE_PAYLOAD",
  "window_id": "fixture-window-001",
  "source_writers_stopped": true,
  "approved_root_paths": ["E:\\fixture\\project", "E:\\fixture\\external-python"]
}
```

真实停止写入清单包括业务、评测、数据库及 sidecar、模型下载、文稿、IDE/Git 集成、应用 diff 后台 Git 查询和相关索引器。窗口内原库查询必须使用 `--no-optional-locks` 或 `GIT_OPTIONAL_LOCKS=0`。本工具当前不运行源 Git 查询，`.git` 文件按普通历史材料保存。

捕获输出给出 `checksums_sha256`，将该值在批次之外独立保存，再验证：

```powershell
python -B -X utf8 scripts/project_archive.py verify --archive-dir E:\fixture\batch-001 --expected-checksums-sha256 <独立保存的64位小写SHA256>
```

`verify` 只读包和清单，逐成员读到 EOF 核对大小、CRC、SHA256 与完整成员表，不访问原源根或执行归档内的 Git。内部摘要证明一致性，外部校验值须来自可信交接。

## 内容与关系

每个原路径保留默认流原字节，包括 ignored、隐藏文件、原 `.git`、原 ZIP/tar、空目录及重复文件。内包按普通文件保存。ZIP64 开启；普通成员通过流式读写，压缩算法只允许 STORED 和 DEFLATED。压缩包及大文件采用 STORED。

普通文件和非 reparse 目录都通过 [Windows 数据流枚举 API](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-findfirststreamw) 记录完整 `$DATA` 集合。命名流保存为独立 `streams/<ID>.bin`，原名保存在清单，ZIP 路径不使用冒号。文件身份使用 [卷及文件 ID](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getfileinformationbyhandle)；硬链接每条原路径仍有完整成员，组内别名与范围外未解析别名分别记录。

symlink/junction 本体只记录类型、原目标文本与解析关系，不递归跟随。目标须已经位于项目实际树或精确外部根；未登记目标、未知 reparse、数据流/必要权限读取失败均阻止封口。联接本体的数据流与安全描述符标为 `NOT_RUN_NOFOLLOW`，目标内容按实际根捕获。

计划、捕获前、捕获字节和捕获后核对成员、内容摘要、流集合、时间属性、身份、硬链接数和可读权限记录。源变更、流增加/删除、同大小改字节或关系变化均失败。该检查需要实际停写窗口，不是系统原子快照。

## 产物与失败

```text
batch-001/
  PLAN.json                    原计划与观测值
  WINDOW.json                  本次停写窗口记录
  ARCHIVE_INFO.json            FILE_PAYLOAD 状态、工具摘要与运行环境
  files.jsonl                  全路径、流及 before/captured/after
  links.jsonl                  联接原关系与目标映射
  dependencies.json            精确根、硬链接组和恢复状态
  events.jsonl                 封口前事件
  payload.zip                  原路径与独立流成员
  CHECKSUMS.json                上述固定产物大小与 SHA256
  FILE_PAYLOAD_COMPLETE.json    最后独占生成的本批封口
```

输出目录必须全新；临时 `.part` 关闭并校验后，在同卷使用不覆盖目标的硬链接发布。已存在目录、发布瞬间出现的目标、输出位于源内或经 reparse 返回源内都会失败。其他文件系统的发布支持需实测。

失败非零退出，保留 `.part`、`ARCHIVE_INFO.json.part`、`FAILURE.json` 和已取得的源差异，不自动重试、删除或改源。修正后用新计划/新批次路径。成功批次不包含语义为完整历史验收的 `COMPLETE.json`。

分项状态包括文件与数据流完整性、关系记录；owner/group/DACL 只记录，SACL `NOT_READ`，ACL 恢复 `RECORD_ONLY`。Git 分类与历史恢复、依赖可用性恢复及保留版本脱离留给后续微批。

## 恢复到 original 区

先用独立保存的 `checksums_sha256` 恢复，再单独复核。目标目录必须不存在，且不能落在批次目录、任何原捕获根内，也不能经 8.3 短名或联接别名回到原根：

```powershell
python -B -X utf8 scripts/project_archive.py restore --archive-dir E:\fixture\batch-001 --destination E:\fixture\restore-001 --expected-checksums-sha256 <独立保存的64位小写SHA256>
python -B -X utf8 scripts/project_archive.py verify-restored --archive-dir E:\fixture\batch-001 --destination E:\fixture\restore-001 --expected-checksums-sha256 <同一SHA256>
```

`restore` 先完整执行 `verify`，再在新目标下建立 `original/project/...` 与 `original/dependencies/<依赖ID>/...`。写入时父目录逐级持有不可删除句柄，文件以 CREATE_NEW 方式写，不覆盖、不跟随 reparse。恢复内容如下：

- 每条原路径的默认流和全部命名流，逐流核对大小与 SHA256；
- 范围内硬链接组在新根重建为同一文件，范围外别名只记录（`outside_scope_recovery=NOT_RUN`）；
- junction 和符号链接在新根重建，目标改指向新根内对应的已恢复对象，原目标文本保存在 `RESTORE_MAPPING.json`。符号链接需要当前账户有创建权限，没有权限时恢复失败；
- 修改时间与只读、隐藏、系统、存档四个属性；创建时间及其他属性只记录。

全部写完后重新扫描整个 `original/`，路径与类型集合、流集合、字节、修改时间、四个属性、硬链接与链接目标都必须与清单一致，并再次核对批次外部校验值，然后依次写 `RESTORE_MAPPING.json`、`RESTORE_INFO.json`，最后写 `ORIGINAL_RESTORE_COMPLETE.json`。`verify-restored` 只读，重新执行同样的全量扫描，多出文件、多出数据流、同大小改字节或时间变化都失败。

结果状态为 `ORIGINAL_FILE_PAYLOAD_COMPLETE`，`original_restore_integrity`、`streams_integrity` 为 PASS，链接和硬链接分别给出 PASS / PASS_IN_SCOPE 或 NOT_APPLICABLE；`acl_restoration=RECORD_ONLY`，`full_ntfs_restore`、`git_history_recovery`、`dependency_recovery`、`retained_version_independence` 为 NOT_RUN。原 `.git` 文件只作为原字节恢复，不在 original 区执行 Git。中途失败保留已写内容和 `RESTORE_FAILURE.json`，不自动清理；换新目标重做。

## 从 original 区重建 Git 历史

`original/` 区只保留原字节，Git 不在那里运行。历史另建到一个全新目录，目标不能与批次、恢复目录或原捕获根重叠：

```powershell
python -B -X utf8 scripts/project_archive.py reconstruct-git --archive-dir E:\fixture\batch-001 --restore-dir E:\fixture\restore-001 --destination E:\fixture\git-001 --expected-checksums-sha256 <同一SHA256>
python -B -X utf8 scripts/project_archive.py verify-reconstructed-git --archive-dir E:\fixture\batch-001 --restore-dir E:\fixture\restore-001 --destination E:\fixture\git-001 --expected-checksums-sha256 <同一SHA256>
```

`reconstruct-git` 先完整执行 `verify-restored`，然后在 `original/` 中查找全部 `.git`（不进入联接或符号链接）：

- **有历史的库**：只复制原 `objects/`、`refs/`、`packed-refs` 和 HEAD 到新建的裸库 `derived/<库ID>.git`。原 config、hooks、info、alternates、index 和 reflog 不带入。所有 git 调用不读系统/全局配置、不运行 hooks、不提示输入。
- **对象核对**：`fsck --full` 发现缺失或损坏即失败；dangling 只计数。原 HEAD 和每个 linked worktree 的 HEAD 记为本批专用 ref `refs/archive/b3c/HEAD`、`refs/archive/b3c/worktrees/<管理名>`，分离 HEAD 因此进入 bundle。原 refs 已占用该前缀时失败。
- **bundle**：`bundles/<库ID>.bundle` 含全部 refs，生成后 `bundle verify`。再从 bundle 镜像克隆到 `reconstructed/<库ID>.git`，逐项比较 refs、附注 tag 的 peeled 值与原 ref 文件，并对克隆再做 `fsck` 和全历史遍历。
- **只有原始对象里才有的部分**：reflog 才能到达的提交等只在原始对象里的对象，数量记为 `raw_only_objects`，保留在 `original/` 和派生裸库中，不在 bundle 里。index、reflog 及 ORIG_HEAD 等伪 ref 只在 `original/`。
- **工作树**：主工作树和每个 linked worktree 以原管理名重新检出到 `worktrees/<库ID>/<管理名>`（主工作树为 `main-worktree`）。原来在分支上的仍检出该分支，分离的按原对象检出。检出后核对 HEAD 和管理名，工作区必须干净。原工作区里的未提交和未跟踪内容只在 `original/`。
- **零历史库**（没有任何 ref）标为 `NO_COMMIT_HISTORY`，嵌套 `.git/.git` 等异常项标为 `ORIGINAL_ONLY`，都不建派生库。
- **不支持的特性**：浅克隆、alternates、partial clone/promisor、reftable、非 SHA-1 对象格式、submodule 的 `modules/`、LFS 目录，以及捕获时残留的 ref `.lock`，都直接失败，不报 PASS。

完成后再次执行 `verify-restored`，证明 `original/` 未被改动，然后写 `GIT_RECONSTRUCT.json`，最后独占写 `GIT_RECONSTRUCT_COMPLETE.json`（含报告和各 bundle 的 SHA256）。失败时写 `GIT_RECONSTRUCT_FAILURE.json`，不清理，换新目标重做。`verify-reconstructed-git` 只读，在临时目录里重新核对标记与 bundle 摘要、`bundle verify`、refs 和工作树 HEAD。`git_history_recovery` 只由这一步给出；`dependency_recovery`、`retained_version_independence` 仍为 NOT_RUN。

## 当前验证范围

```powershell
python -B -X utf8 -m unittest discover -s tests -p test_project_archive.py -v
python -B -X utf8 -m unittest discover -s tests -p test_archive_git.py -v
```

测试只使用自己的小型临时根。真实 Windows fixture 覆盖文件与目录 ADS、硬链接、junction、可读 ACL 记录及 ZIP64 流式分支；ZIP64 阈值替身不等于 5.68 GB 模型实测。恢复 fixture 覆盖文件与目录命名流（含名称排在默认流之前的流）、硬链接、内部与外部 junction、符号链接（无权限时跳过）、只读/隐藏属性和修改时间、已有/重叠/短名别名目标的拒绝、中断留存和复核篡改。Git 重建 fixture 用三套临时库覆盖：packed 与 loose 附注 tag、轻量 tag、分支上的与分离的 linked worktree、reflog 才能到达的提交、脏文件与未跟踪文件、零历史库、嵌套 `.git`、缺失对象、alternates、目标重叠和 CLI 退出码。实际大树容量、吞吐、长路径和全源权限仍在 B5 前按真实对象执行。本批没有捕获项目、模型、venv、数据库或生产 Git。
