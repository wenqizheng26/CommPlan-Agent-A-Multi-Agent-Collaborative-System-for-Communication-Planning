export function serviceText(service){
 const labels={ready:'本机 Qwen 服务已就绪（后台运行）',unreachable:'无法连接本机 Qwen 服务',loading:'本机 Qwen 正在加载',not_ready:'本机 Qwen 服务暂未就绪',unexpected:'端口可访问，但未找到目标 Qwen',unknown:'无法确认本机 Qwen 服务状态'};
 return service?labels[service.status]||labels.unknown:'正在检查本机 Qwen 服务…';
}
export function callSummary(state){
 const report=state?.report, diagnostics=report?.diagnostics||[];
 const invalid=diagnostics.filter(d=>d.code==='MODEL_OUTPUT_INVALID').length;
 const unavailable=diagnostics.some(d=>d.code==='MODEL_UNAVAILABLE');
 const mode=report?.component_modes?.interpretation;
 const rows=[];
 if(!report)rows.push('需求解析：尚无已保存的调用结果。');
 else if(mode==='llm')rows.push('需求解析：模型调用通过校验。');
 else if(invalid||unavailable)rows.push(`需求解析：${invalid?`${invalid} 次模型输出未通过校验`:'模型请求未成功返回'}；${report.runtime_health==='degraded'?'已改用确定性规则。':'未降级，请处理后重试。'}`);
 else rows.push('需求解析：使用确定性规则，未采用模型输出。');
 for(const [label,role] of [['计算建议',state?.calculation_role],['结构化审查',state?.review_assessment?.role]]){
  const modes={llm:'模型调用通过校验',deterministic:'使用确定性规则',deterministic_fallback:'模型调用未成功或输出无效，已改用确定性规则',stub:'使用测试替身'};
  rows.push(`${label}：${role?(modes[role.mode]||'未得到可用模型结果'):'尚无已保存的调用结果'}。`);
 }
 return rows;
}
export function diagnosticMessages(diagnostics=[]){
 const groups=new Map();
 for(const d of diagnostics){
  if(['SOURCE_EXCERPT','MODEL_CALL','EXPLICIT_CARD_LOOKUP'].includes(d.code))continue;
  const key=d.code+'\0'+d.message;
  const item=groups.get(key)||{message:d.message,count:0};item.count++;groups.set(key,item);
 }
 return [...groups.values()].map(d=>d.message+(d.count>1?`（共 ${d.count} 次，逐次记录见下方详情）`:''));
}
