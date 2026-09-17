# Contract / Plan 独立复核 REV-02

状态：PASS_WITH_LIMITATIONS（二轮闭合）；审查日期：2026-09-17。首轮 CHANGES_REQUESTED 发现保留如下。仅审阅 CONTRACTS、TASK_BACKLOG、MASTER_IMPLEMENTATION_PLAN、AGENT_ASSIGNMENTS、ARCHITECTURE_DECISIONS、NEXT_ACTION、RISK_REGISTER。没有修改被审文件、业务实现或 Git 状态。

## 实质发现

| ID | 等级 | 证据（首轮行号） | 问题与最小修正 |
|---|---|---|---|
| CP-01 | P1 | TASK_BACKLOG:143–240、316；AGENT_ASSIGNMENTS:5–18、36 | exact allowlist/default deny 与当前审计/计划 ownership 不闭合。PLN-01 仅允许三个控制文件，AUD 项缺各自 evidence；REV-01 仅允许 REVIEW_REPORT，Contract reviewer 没有独立任务及其两份产物权限。补齐实际允许文件，单列 REV-02 并让 H0 依赖两份独立 review；保持业务禁区。 |
| CP-02 | P1 | CONTRACTS:35–37、46–47 | ConfirmedSnapshot 只含参数 ID，没有冻结值/单位/conditions 或其不可变存储引用；CalculationRequest 又含独立 parameters/conditions。“来自快照”尚不能形成可执行逐值校验。冻结规范参数、条件、场景/模型身份、计划内容或受控不可变引用，并定义服务端构建与偏差拒绝。 |
| CP-03 | P1 | CONTRACTS:105–110 | CAS 在重复提交识别之前。第一次成功后 state_version 增加，响应丢失后原请求重放会先被 CAS 拒绝，无法满足“完全重复返回先前 commit”。schema/权限之后先按可信 task/操作身份查幂等记录；同 key 同 payload 返回原 ack，未命中才 CAS；新过期请求仍拒绝。 |
| CP-04 | P1 | TASK_BACKLOG:408、463、512；MASTER_IMPLEMENTATION_PLAN:97 | T001/T002/T003 的 READY 条件也要求 Contract 已冻结，而 T003 才负责冻结，导致前置自锁。为三项准备任务明确批准草案与基线逐步建立的规则；冻结完成后的任务才强制 frozen hash。 |
| CP-05 | P2 | CONTRACTS:131、157–158 | Router 支持 reject/edit，API enum 只有 confirm/edit/cancel；edit 不含修改数据，也未定义和 parameters 新 revision 的关系。统一 action 集并明确 edit 只退回编辑状态还是携带参数、何时递增 revision。 |

P0：未发现。以上是契约/计划缺口，不是已运行实现缺陷。

## 已核实与边界

- 控制文件校验命令 `.\.venv\Scripts\python.exe -X utf8 docs/codex/validate_control_files.py` exit 0：PASS，43 tasks、35 future implementation tasks、38/38 WBS、DAG acyclic、H0 false。该结果只证明结构，不覆盖上述语义。
- 35 项未来任务均 BLOCKED_HUMAN_GATE_0；主计划和 NEXT_ACTION 明确停止 H0，没有发现本轮实现授权泄漏。
- 本轮审计采用 Astra low，机械测试/发布采用 Luna；未来复杂状态任务的 medium/high 明确属于后续策略，没有将其误称本轮 low 审计。
- T001–T035 主计划编号和 YAML 的任务标题/依赖总体相符；future test 路径在对应 allowed_files 中列为任务产物，不能当作现有测试通过。本轮不运行它们。
- GitHub 用户目标为 wenqizheng26 下新 private 仓库；账号/通道问题为已知外部发布阻塞，不计为业务实现失败。
- 未读取模型二进制、未重新审计全仓库、未运行全套业务测试。待 Main 修正后仅复核这五项与控制文件变化。


## 二轮最终闭合（2026-09-17）

独立结论：CP-01 至 CP-05 全部 RESOLVED；本次有界契约/计划复核无未解决阻塞项。PASS_WITH_LIMITATIONS 只表示五项文档修正闭合，不表示业务实现、未来测试、专业公式或发布已通过。

| ID | 最终核对结果 |
|---|---|
| CP-01 | P0 allowlist 已补齐报告和 evidence；REV-02 独立条目及两个输出存在；H0 依赖 REV-01/REV-02；Main 仅在原 owner 交接后整合对应报告。 |
| CP-02 | CONTRACTS 第35、39行冻结参数值/单位/来源、条件、场景、模型及计划；服务端逐项比对，偏差拒绝 SNAPSHOT_INPUT_MISMATCH。 |
| CP-03 | CONTRACTS 第108–111行先校验身份/schema，查持久幂等记录，未命中新请求才CAS；旧ack不晋升当前结果。 |
| CP-04 | T001–T003 requires_frozen_contract=false，后续为true；Main调度区分批准草案和冻结版本；MASTER 第38行 T007 已同步依赖 T003。 |
| CP-05 | CONTRACTS 第133、159行统一 confirm/edit/cancel；edit 不夹patch、不增revision，实际parameters提交才增revision并使旧interrupt失效。 |

二轮再次运行现有控制校验器，exit 0 / PASS / 44 tasks / 35 implementation tasks / 38 WBS覆盖 / DAG无环 / 无错误警告。运行时文件记录的 human_gate_0_approved 仍为 false；Main 已通知用户在完整报告后明确要求“执行”，批准记录与Backlog状态由 Main 更新，本 Reviewer 不替代记录该授权。

REVIEW_RESOLUTION.md 中 INDEPENDENT_FINALIZATION_PENDING 为此前历史；本节与JSON为当前独立最终结论。未重新审计源码、未运行业务单测、未修改被审文件、未执行 Git 操作。GitHub发布的外部阻塞继续单列。
