import {serviceText,callSummary,diagnosticMessages} from './model-status.mjs';
import {formatDomain} from './values.mjs';
import {sourceExcerpt} from './text.mjs';
import {nodes,statusText,nodeStates} from './flow.mjs';
import {roleModeNames,reviewDecisionNames,reviewQuestion} from './roles.mjs';
import {provenance,settingsDrift,RETRIEVAL} from './settings.mjs';
import {fmt} from './timing.mjs';
export const parameterNames={frequency_ghz:'载波频率',distance_km:'路径距离',tx_power_dbm:'发射功率',tx_gain_dbi:'发射天线增益',rx_gain_dbi:'接收天线增益',
 tx_loss_db:'发射馈线损耗',rx_loss_db:'接收馈线损耗',path_loss_db:'路径损耗',extra_loss_db:'额外损耗',rx_power_dbm:'接收信号电平',rx_threshold_dbm:'接收门限',reserve_db:'预留余量',link_margin_db:'链路余量'};
export const symbols={frequency_ghz:'f',distance_km:'d',tx_power_dbm:'Pt',tx_gain_dbi:'Gt',rx_gain_dbi:'Gr',tx_loss_db:'Lt',rx_loss_db:'Lr',path_loss_db:'L',extra_loss_db:'La',rx_power_dbm:'Pr',rx_threshold_dbm:'Pth',reserve_db:'M₀'};
export const toolNames={fspl_ghz:'自由空间路径损耗',received_power:'接收信号电平',link_margin:'链路余量'};
// Internal parameter ids never reach the reader; distance/frequency keep their unit hint.
export function humanize(q){return q.replaceAll('distance_km','路径距离（km）').replaceAll('frequency_ghz','载波频率（GHz）').replace(/[a-z]+(?:_[a-z0-9]+)+/g,n=>parameterNames[n]||n);}
// One row per plan step: every input names its source (parameter value, missing, or an earlier step).
export function planSteps(plan,report,result){
 const order=Object.fromEntries(plan.steps.map((s,i)=>[s.step_id,i+1]));
 const params=Object.fromEntries(report.parameters_proposal.map(p=>[p.parameter_id,p]));
 const done=Object.fromEntries((result?.steps||[]).map(s=>[s.step_id,s]));
 return plan.steps.map((step,i)=>({n:i+1,title:toolNames[step.tool_id]||step.tool_id,unit:step.expected_unit,
  value:done[step.step_id]?.output.value??(plan.steps.length===1&&result?result.outputs[0].value:null),
  inputs:Object.entries(step.inputs).map(([name,b])=>{
   if(b.kind==='step')return {name,label:parameterNames[name]||name,source:`步骤 ${order[b.ref]} 的结果`,kind:'step'};
   const p=params[b.ref];
   if(!p||p.value===null)return {name,label:parameterNames[name]||name,source:p?.status==='conflicting'?'来源冲突，待确认':'缺失，待补充',kind:'missing'};
   return {name,label:parameterNames[name]||name,source:`${formatDomain(p.value)} ${p.unit} · ${p.origins.some(o=>o.kind==='manual_form')?'手工填写':'原文'}`,kind:'parameter'};
  })}));
}
function stepsBlock(plan,report,result){
 const sec=el('section',undefined,'detail-block'),list=el('ol',undefined,'plan-steps');
 for(const s of planSteps(plan,report,result)){
  const li=el('li',undefined,'plan-step'),head=el('div',undefined,'plan-step-head');
  head.append(el('strong',`${s.n}. ${s.title}`),el('span',s.value==null?`输出 ${s.unit}`:`${formatDomain(s.value,2)} ${s.unit}`,'plan-step-out'+(s.value==null?'':' done')));
  const ins=el('ul',undefined,'plan-inputs');
  for(const x of s.inputs){const row=el('li',undefined,x.kind);row.append(el('span',x.label),el('span',x.source));ins.append(row);}
  li.append(head,ins);list.append(li);
 }
 sec.append(el('h3',`计算步骤 · 共 ${plan.steps.length} 步`),list,el('p','每一步都用登记公式计算，输入只来自已确认的参数或上一步的结果；执行后逐步独立复算。','hint'));
 return sec;
}
export const labels={AWAITING_CONFIRMATION:'等待核对确认',AWAITING_INPUT:'需要补充或修正',NEEDS_MODEL:'模型或依据不足',FAILED:'处理失败',COMPLETED:'已完成',CANCELLED:'已取消',RUNNING:'正在处理'};
export const tabNames={overview:'概览',parameters:'参数',plan:'计划',formula:'公式',evidence:'依据',result:'结果'};
export function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function button(text,fn,cls='text-button'){const b=el('button',text,cls);b.type='button';b.addEventListener('click',fn);return b;}
function block(title,text,cls=''){const b=el('section',undefined,'detail-block '+cls);b.append(el('h3',title));if(Array.isArray(text)){const ul=el('ul');text.forEach(t=>ul.append(el('li',t)));b.append(ul);}else if(text)b.append(el('p',text));return b;}
function jsonDetails(label,data){const d=el('details');d.append(el('summary',label),el('pre',JSON.stringify(data,null,2)));return d;}
function sourceLink(ref){if(!ref.source_url)return el('p','本地资料：'+(ref.source_id||'未提供路径'),'hint');try{const u=new URL(ref.source_url);if(!['http:','https:'].includes(u.protocol))return el('p','来源链接不可打开','hint');const a=el('a','打开专业资料 ↗');a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';return a;}catch{return el('p','来源链接格式无效','hint');}}
function formulaMath(){
 const ns='http://www.w3.org/1998/Math/MathML';
 const m=(tag,text,...children)=>{const n=document.createElementNS(ns,tag);if(text)n.textContent=text;n.append(...children);return n;};
 const term=(symbol,unit)=>m('mrow',null,m('mn','20'),m('msub',null,m('mi','log'),m('mn','10')),m('mo','('),m('mfrac',null,m('mi',symbol),m('mrow',null,m('mn','1'),m('mtext',unit))),m('mo',')'));
 const math=m('math',null,m('mrow',null,m('msub',null,m('mi','L'),m('mtext','dB')),m('mo','='),m('mn','92.4'),m('mo','+'),term('f','GHz'),m('mo','+'),term('d','km')));
 math.setAttribute('display','block');math.setAttribute('aria-label','L dB 等于 92.4 加 20 log10(f/GHz) 加 20 log10(d/km)');return math;
}
function retrievalTable(found){
 const b=el('section',undefined,'detail-block');
 b.append(el('h3','检索命中'),el('p',`${RETRIEVAL[found.mode_used]}检索 · 知识库 ${found.corpus.size} 条 · 返回 ${found.hits.length} / ${found.top_k} · 前 ${found.top_n} 条送入模型 · ${fmt(found.latency_ms.total)}`+(found.degraded?`。请求${RETRIEVAL[found.mode_requested]}检索，向量模型未就绪，已按词项检索`:'')+'。','hint'));
 const table=el('table'),head=el('tr');['#','公式卡','词项','向量','融合','上下文'].forEach(t=>head.append(el('th',t)));const thead=el('thead');thead.append(head);table.append(thead);
 const body=el('tbody'),num=v=>v==null?'—':v.toFixed(4);
 for(const h of found.hits){const row=el('tr'),card=el('td'),used=found.used.includes(h.id);card.append(el('strong',h.title),el('small',h.id+(h.source?.title?' · '+h.source.title:'')));
  row.append(el('td',String(h.rank)),card,el('td',num(h.scores.lexical),'num'),el('td',num(h.scores.dense),'num'),el('td',num(h.scores.fused),'num'),el('td',used?'已送入':'未送入','chip '+(used?'run':'')));body.append(row);}
 table.append(body);const wrap=el('div',undefined,'table-wrap');wrap.append(table);b.append(wrap);
 b.append(el('p','只有送入模型且含词项证据的候选，才可能成为计算模型；检索结果不是数值依据，公式仍须登记并经你确认。','hint'));
 return b;
}
export function renderDetails(host,{state,events=[],node='input',tab='overview',focusParameter=null,onTab,onParameter,historical=false,modelService=null,settings=null,models=null,onReparse=null}){
 host.replaceChildren();const [title,subtitle]=nodes[node]||nodes.input;
 const heading=el('div',undefined,'detail-heading');heading.append(el('span',tab==='result'?'计算结果':'任务核对','eyebrow'),el('h2',title),el('p',subtitle,'hint'));host.append(heading);
 if(historical)host.append(block('历史只读','正在查看保存时的版本，不能在此确认或修改。','warning'));
 const r=state?.report,model=state?.review?.model,plan=r?.calculation_plan_proposal;
 if(['orchestrator','explanation','validator_agent'].includes(node))host.append(block('接入范围',node==='orchestrator'?'按状态与审查意见调度；每版本最多计算两次。当前是受控程序策略，尚无自主任务拆解。':node==='explanation'?'报告正文由已验证数据生成；未启用自由生成的科学解释。':'先执行硬校验，再进行可选结构化审查。模型建议不能改数值或绕过硬校验。','scope-note'));
 if(node==='llm'){host.append(block('模型服务 · 当前检查',serviceText(modelService)+(modelService?.checked_at?`\n检查时间：${new Date(modelService.checked_at).toLocaleString('zh-CN')}。`:'')+'\n此处是当前服务状态，与任务保存时的调用结果分别记录。'));if(state)host.append(block(historical?'此历史版本的调用结果':'本任务当前版本的调用结果',callSummary(state)));}
 if(!state){host.append(block('开始一条任务','在左侧输入自然语言需求，或填入完整示例。图中可点击查看各模块职责。'));return;}
 if(reviewQuestion(state))host.append(block('审查意见',reviewQuestion(state),'warning'));
 if(state.failure)host.append(block('当前阻断',[state.failure.message,state.failure.next_action],'warning'));
 const roles=()=>{
  const section=el('details');section.append(el('summary','计算、审查与调度记录'));
  if(state.calculation_role)section.append(block('计算角色',`${roleModeNames[state.calculation_role.mode]||state.calculation_role.mode}；已执行 ${state.calculation_attempts||1} 次计算（上限 2 次）。`));
  if(state.review_assessment){const a=state.review_assessment;section.append(block('审查角色',`${roleModeNames[a.role.mode]||a.role.mode} · ${reviewDecisionNames[a.role.proposal.decision]}。审查绑定当前结果版本。`),jsonDetails('审查依据与角色记录',a));}
  if(state.routing_decisions?.length)section.append(jsonDetails('调度与重算记录',state.routing_decisions));
  return section;
 };
 if(tab!=='result'&&['compute_agent','validator_agent','orchestrator','review'].includes(node))host.append(roles());
 if(tab==='overview'){
  const status=nodeStates(state,events)[node];host.append(block(node==='llm'?'任务调用状态（非服务状态）':'本步骤状态',statusText[status]||status));
  host.append(block('当前任务描述',state.request?.raw_text||'等待输入'));
  if(state.failure)host.append(block('失败原因',[state.failure.message,state.failure.code,'下一步：'+state.failure.next_action],'warning'));
  if(r){host.append(block('运行方式',`需求解析：${r.component_modes.interpretation==='llm'?'本机 LLM':'确定性解析'}；检索：${RETRIEVAL[state.retrieval?.mode_used]||'词项'}检索；${r.runtime_health==='degraded'?'已明确降级':'本地运行'}。`));
   const ds=diagnosticMessages(r.diagnostics);if(ds.length)host.append(block('处理说明',ds),jsonDetails('逐次诊断记录',r.diagnostics));
   host.append(button('查看参数与原文对应 →',()=>onTab('parameters')),button('查看计算计划 →',()=>onTab('plan')));
  }
  host.append(jsonDetails('本节点可追溯数据',node==='state'?state:{task_id:state.task_id,revision:state.revision,status:state.status,request:state.request,events:events.filter(e=>e.node===node&&e.revision===state.revision)}));
  return;
 }
 if(!r){host.append(block('尚无可用产物','当前步骤还没有生成可核对数据。运行事件可在下方查看。'));return;}
 if(tab==='parameters'){
  const raw=block('当前描述定位');const quote=el('p',undefined,'source-quote');const p=r.parameters_proposal.find(p=>p.canonical_name===focusParameter);const origin=p?.origins.find(o=>o.kind==='user_text'&&o.span);const text=state.request.raw_text;
  if(origin){const chars=Array.from(text);quote.append(document.createTextNode(chars.slice(0,origin.span[0]).join('')),el('mark',sourceExcerpt(text,origin.span)),document.createTextNode(chars.slice(origin.span[1]).join('')));}else quote.textContent=text;
  raw.append(quote);host.append(raw);
  if(r.questions.length)host.append(block('需要处理',r.questions.map(humanize),'warning'));
  const table=el('table');const tr=el('tr');['参数 / 符号','规范值','来源与原始值'].forEach(t=>tr.append(el('th',t)));const thead=el('thead');thead.append(tr);table.append(thead);const body=el('tbody');
  for(const param of r.parameters_proposal){const row=el('tr',undefined,param.canonical_name===focusParameter?'highlight-row':'');const titleCell=el('td');titleCell.append(button(`${parameterNames[param.canonical_name]||param.canonical_name} · ${symbols[param.canonical_name]||''}`,()=>onParameter(param.canonical_name)));row.append(titleCell,el('td',param.value===null?(param.status==='conflicting'?'冲突':'缺失'):`${formatDomain(param.value)} ${param.unit}`));const sources=el('td');
   for(const o of param.origins){sources.append(el('strong',`${formatDomain(o.value)} ${o.unit}`),el('small',o.kind==='user_text'?`当前描述：${o.span?sourceExcerpt(text,o.span):'未提供定位'}`:'用户手工填写'));}
   const provenance=state.conversation?.field_sources?.[param.canonical_name];if(provenance)sources.append(el('small',`来自第 ${provenance.number} 条补充：${provenance.message}`));
   if(!param.origins.length)sources.append(el('small','未知，需补充'));row.append(sources);body.append(row);
  }table.append(body);const wrap=el('div',undefined,'table-wrap');wrap.append(table);host.append(wrap);
  host.append(block('本版本确认',state.confirmed_snapshot?`已确认 · ${state.confirmed_snapshot.confirmed_at}`:historical?'此历史版本为未确认草稿，仅供查看。':'当前为参数草稿。核对原文、单位、模型假设与计划后，在下方确认。'));
  host.append(button('查看这些参数代入的公式 →',()=>onTab('formula')));return;
 }
 if(tab==='plan'){
  host.append(block('计算目标',plan?.objective||'尚未形成可执行计划'));
  if(!plan){host.append(block('当前阻断',r.questions.length?r.questions.map(humanize):['模型或依据不足，不能进入计算。'],'warning'));return;}
  host.append(stepsBlock(plan,r,state.result));
  host.append(block('登记模型',plan.steps.length>1?plan.selected_model.map(id=>toolNames[id]||id).join(' → '):`${model?.title||plan.selected_model.join('、')} · v${model?.version||'未知'}`));
  host.append(block('模型选择依据',model?.description||'无可用模型说明'));
  host.append(block('用户声明条件',r.conditions.map(c=>({free_space:'采用自由空间模型',free_space_reference:'只求自由空间基准',non_free_space:'实际非自由空间环境'})[c]||c)));
  host.append(block('关键假设与边界',r.assumptions));
  host.append(button('核对公式与参数绑定 →',()=>onTab('formula')),button('查看模型依据 →',()=>onTab('evidence')));host.append(jsonDetails('详细计划与绑定',plan));return;
 }
 if(tab==='formula'){
  if(!plan||!model){host.append(block('尚未选定可执行模型','请先解决当前参数或模型依据问题。'));return;}
  host.append(block('登记公式',`${model.title} · ${model.id} v${model.version}`));
  const math=el('div',undefined,'math-formula');
  if(model.id==='fspl_ghz'&&model.expression==='92.4 + 20*log10(frequency_ghz) + 20*log10(distance_km)')math.append(formulaMath());else math.append(el('code',model.expression));host.append(math);
  host.append(el('p','以 GHz 与 km 为单位取数值；对数的自变量为相应无量纲比值。','hint'));
  const last=plan.steps[plan.steps.length-1];
  for(const [name,spec]of Object.entries(model.parameters)){const param=r.parameters_proposal.find(p=>p.canonical_name===name);const fromStep=last.inputs[name]?.kind==='step';const b=block(`${symbols[name]||name} · ${spec.description}`,`单位 ${spec.unit}；${fromStep?'由上一步计算得出':param?.value==null?'尚无唯一可用值':`当前值 ${formatDomain(param.value)} ${param.unit}`}。`);b.classList.toggle('highlight-row',name===focusParameter);b.append(button('定位参数原文与来源',()=>onParameter(name)));host.append(b);}
  const actual=state.result?.normalized_inputs;
  if(actual&&state.result.steps){host.append(block('实际代入（逐步）',state.result.steps.map((s,i)=>`${i+1}. ${toolNames[s.tool_id]||s.tool_id}：${Object.entries(s.inputs).map(([k,v])=>`${symbols[k]||k} ${formatDomain(v,2)}`).join('，')} → ${formatDomain(s.output.value,2)} ${s.output.unit}`)));}
  else if(actual&&state.result.outputs.length>1){host.append(block('实际代入（分候选执行）',state.final_report?.conclusion||'候选分别执行；完整输入与结果见任务 JSON。'));}
  else if(actual){host.append(block('实际代入（已确认输入）',`92.4 + 20 × log₁₀(${formatDomain(actual.frequency_ghz)}) + 20 × log₁₀(${formatDomain(actual.distance_km)}) = ${formatDomain(state.result.outputs[0].value,2)} dB`));}
  else host.append(block('待执行','当前只展示登记公式和参数草稿，确认后由专业程序代入计算。'));
  host.append(block('模型假设',r.assumptions));host.append(button('定位公式来源与原式换算 →',()=>onTab('evidence')));host.append(jsonDetails('登记程序表达式',model.expression));return;
 }
 if(tab==='evidence'){
  if(state.retrieval)host.append(retrievalTable(state.retrieval));
  host.append(block('证据用途','参数事实来自用户原文或手工输入；下列资料用于公式、参数定义和适用条件。检索命中不等于新完成了原文审核。'));
  if(!r.evidence_refs.length)host.append(block('暂无可用证据','不能根据空的检索结果继续推定模型适用。','warning'));
  for(const [i,ref]of r.evidence_refs.entries()){
   const b=block(`依据 ${i+1} · ${ref.source_title}`);b.append(el('p','定位：'+(ref.locator==='formula card source metadata'?'仅有卡片元数据，未提供精确页码/公式编号':ref.locator||'未提供精确定位')));
   b.append(el('p',`模型 ${ref.catalog_id} · 卡片版本 ${ref.card_version} · 库内状态 ${ref.status==='verified'?'已登记审核':ref.status}`,'hint'));
   b.append(block('检索片段（库内摘要，非原文逐字摘录）',ref.excerpt));
   const source=model?.sources?.find(x=>x.title===ref.source_title);if(source?.derivation)b.append(block('原式与单位换算',source.derivation));
   if(source?.checked_date)b.append(el('p','库内记录的核查日期：'+source.checked_date,'hint'));
   b.append(sourceLink(ref),el('p','支持：登记公式、变量定义及自由空间适用范围。','hint'),button('返回公式 →',()=>onTab('formula')),jsonDetails('证据身份与快照',ref));host.append(b);
  }
  host.append(el('p','本次执行未独立重审外部原始文献；缺失的出处定位不会自动补造。','hint'));return;
 }
 if(tab==='result'){
  if(!state.final_report||state.status!=='COMPLETED'){host.append(block('尚无正式发布结果',state.failure?.message||'确认计算且结果校验通过后在此展示。'));return;}
  const drift=historical?[]:settingsDrift(state,settings);
  if(drift.length){const b=block('当前默认设置已改变',`${drift.join('；')}。这个结果按生成时的配置保存，不会自动重算；数值只取决于已确认的参数。`,'warning');if(onReparse)b.append(button('按新设置重新解析',onReparse,'secondary compact'));host.append(b);}
  for(const [i,value] of state.result.outputs.entries()){const metric=el('div',undefined,'metric');metric.append(el('strong',formatDomain(value.value,2)),el('span',value.unit));host.append(el('p',state.result.steps?toolNames[state.result.model_id]||state.result.model_id:state.result.outputs.length>1?`候选 ${i+1} · 自由空间单程路径损耗`:'自由空间单程路径损耗','eyebrow'),metric);if(value.inputs)host.append(el('p',Object.entries(value.inputs).map(([k,v])=>`${parameterNames[k]||k} ${formatDomain(v)} ${{frequency_ghz:'GHz',distance_km:'km'}[k]||''}`).join('；'),'hint'));}host.append(el('p',state.final_report.conclusion));
  if(state.result.steps)host.append(stepsBlock(state.review.report.calculation_plan_proposal,state.review.report,state.result));
  const names={step_chain:'逐步代入链',independent_magnitude:'逐步独立复算',result_integrity:'结果完整性',snapshot_identity:'确认快照版本',input_consistency:'输入一致性',plan_identity:'执行计划',evidence_consistency:'引用依据',model_identity:'模型与公式版本',numeric_domain:'数值、名称与单位',fspl_magnitude:'独立数量级检查'};
  const checks=block('程序校验');for(const v of state.validations)checks.append(el('p',`${v.passed?'✓':'×'} ${names[v.validator_id]||v.validator_id}`,'check-result'));host.append(checks);
  const made=provenance(state,models);if(made.length){const b=el('section',undefined,'detail-block provenance');b.append(el('h3','生成配置'));const grid=el('dl');for(const [k,v] of made)grid.append(el('dt',k),el('dd',v));b.append(grid);host.append(b);}
  host.append(block('结果含义与适用限制',state.final_report.limitations),roles());host.append(el('p',state.final_report.review?'报告数值与正文来自已验证数据；结构化审查模式：'+(roleModeNames[state.final_report.review.mode]||state.final_report.review.mode)+'。':'此历史记录为确定性程序报告，未记录独立审查角色。','hint'));
  host.append(button('追溯公式与实际代入 →',()=>onTab('formula')),button('追溯参数原文 →',()=>onTab('parameters')),button('查看来源证据 →',()=>onTab('evidence')));return;
 }
}
