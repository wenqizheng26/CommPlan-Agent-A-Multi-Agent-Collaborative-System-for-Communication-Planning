export const roleModeNames={deterministic:'确定性规则',llm:'本机 Qwen',stub:'测试替身',deterministic_fallback:'规则接管 · 数值不变',bounded_policy:'受控调度策略'};
export const reviewDecisionNames={pass:'通过',caution:'请核对',not_applicable:'超出适用范围',needs_input:'需补充或核对假设',recalculate:'请求重新计算'};
export function reviewQuestion(state){
 const decision=state?.review_assessment?.role?.proposal?.decision;
 if(decision==='needs_input')return '审查建议核对已声明的模型假设。请补充说明或编辑需求，保存后重新确认。';
 if(decision==='not_applicable')return '审查对目标与模型的适用范围提出疑问，当前结果未发布。请核对需求或等待对应模型接入。';
 return null;
}
