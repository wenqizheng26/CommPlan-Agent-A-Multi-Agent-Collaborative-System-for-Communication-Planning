# 独立复核修正与Main收尾记录

记录者：Main，2026-09-17。本文不覆盖独立Reviewer的原始报告，不将口头/消息条件确认改写成最终无保留PASS。

## 真实状态

REV-01事实审查为PARTIAL，保留范围限制；P2“原15项内容完整性证据不足”的文字已修，Reviewer已写回RESOLVED。Main接受这份有边界的审查。

REV-02首轮提出4项P1、1项P2，原始CONTRACT_PLAN_REVIEW.md及JSON仍保留首轮历史。Main已修正全部五项，Reviewer二轮消息确认CP-01/02/03/05闭合、CP-04前置也闭合，仅指出主计划T007依赖仍写T002。Main随后将其改为T003，与YAML一致。Reviewer在写回最终结论前遭账户usage limit中止。因此当前为 **FIXES_VERIFIED_BY_MAIN / INDEPENDENT_FINALIZATION_PENDING**，不标独立最终PASS。

## 逐项闭合证据

| ID | Main修改 | 独立二轮已收到结论 | 尚需动作 |
|---|---|---|---|
| CP-01 | 全P0 exact allowlist、REV-02单列、H0依赖双review；44任务 | 已闭合 | 写回最终review |
| CP-02 | snapshot完整参数值/单位/来源/条件/scene/model/plan；服务端逐值比对 | 已闭合 | 写回最终review |
| CP-03 | schema/权限→可信幂等记录→未命中新请求CAS；旧ack不晋升当前结果 | 已闭合 | 写回最终review |
| CP-04 | T001–3冻结前置豁免，T004以后frozen强制；T007依赖T003 | 前置已闭合；提出T007主计划文字同步 | Reviewer最终核对已改文字并写回 |
| CP-05 | confirm/edit/cancel统一；edit不夹patch、parameters实际修改才增revision | 已闭合 | 写回最终review |

控制校验器已增加H0双review/P0 ownership/冻结前置规则。最终命令结果单列evidence/control_validation.json；它不替代独立合同语义review或业务测试。

## 发布与后续

Luna publisher同样遭usage limit中止。Main只读核实拟建本地发布目录不存在，没有本地阶段commit。GitHub新目标必须是用户指定wenqizheng26；已连接账号不同，CLI和CUA错误仍未恢复；repository_created=false、upload=false。

本轮停在HUMAN_GATE_0并保留其前置复核待办，不启动T001–T035。额度恢复后首先让REV-02只做五项修正最终记录，再由用户批准H0；publisher在正确账号/可用通道恢复后按allowlist继续。不要重新做已完成的全套审计。

