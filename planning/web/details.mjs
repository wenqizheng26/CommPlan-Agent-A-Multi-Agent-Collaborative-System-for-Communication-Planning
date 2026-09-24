import {serviceText,callSummary,diagnosticMessages} from './model-status.mjs';
import {formatDomain} from './values.mjs';
import {sourceExcerpt} from './text.mjs';
import {nodes,statusText,nodeStates} from './flow.mjs';
import {roleModeNames,reviewDecisionNames} from './roles.mjs';
import {provenance,settingsDrift,RETRIEVAL} from './settings.mjs';
import {fmt} from './timing.mjs';
export const parameterNames={frequency_ghz:'载波频率',distance_km:'路径距离',tx_power_dbm:'发射功率',tx_gain_dbi:'发射天线增益',rx_gain_dbi:'接收天线增益',
 tx_loss_db:'发射馈线损耗',rx_loss_db:'接收馈线损耗',path_loss_db:'路径损耗',extra_loss_db:'额外损耗',rx_power_dbm:'接收信号电平',rx_threshold_dbm:'接收门限',reserve_db:'预留余量',link_margin_db:'链路余量'};
export const symbols={frequency_ghz:'f',distance_km:'d',tx_power_dbm:'Pt',tx_gain_dbi:'Gt',rx_gain_dbi:'Gr',tx_loss_db:'Lt',rx_loss_db:'Lr',path_loss_db:'L',extra_loss_db:'La',rx_power_dbm:'Pr',rx_threshold_dbm:'Pth',reserve_db:'M₀',link_margin_db:'M'};
// Registered expression written with symbols for reading; the program expression itself stays unchanged.
export function symbolic(model){
 const expr=model.expression.replace(/[a-z]+(?:_[a-z0-9]+)+/g,n=>symbols[n]||parameterNames[n]||n).replaceAll('*',' · ').replace(/ - /g,' − ');
 return model.output?.name?`${symbols[model.output.name]||parameterNames[model.output.name]||model.output.name} = ${expr}`:expr;
}
export const toolNames={fspl_ghz:'自由空间损耗',received_power:'接收电平',link_margin:'链路余量'};
export const conditionNames={free_space:'自由空间模型',free_space_reference:'自由空间基准',non_free_space:'非自由空间环境'};
export const targetNames={fspl_ghz:'路径损耗',received_power:'接收信号电平',link_margin:'链路余量'};
export const labels={AWAITING_CONFIRMATION:'待确认',AWAITING_INPUT:'待补充',NEEDS_MODEL:'超出范围',FAILED:'失败',COMPLETED:'已完成',CANCELLED:'已取消',RUNNING:'处理中'};
const checkNames={result_integrity:'结果完整',snapshot_identity:'快照一致',input_consistency:'输入一致',plan_identity:'计划一致',evidence_consistency:'证据链一致',
 model_identity:'公式版本一致',numeric_domain:'量纲单位',step_chain:'逐步代入',independent_magnitude:'独立复算',fspl_magnitude:'数量级复核'};
const circled=n=>'①②③④⑤⑥⑦⑧⑨⑩'[n-1]||`(${n})`;
// Internal parameter ids never reach the reader; distance/frequency keep their unit hint.
export function humanize(q){return q.replaceAll('distance_km','路径距离（km）').replaceAll('frequency_ghz','载波频率（GHz）').replace(/[a-z]+(?:_[a-z0-9]+)+/g,n=>parameterNames[n]||n);}
// Short, real citation of a formula card's registered source, e.g. "ITU-R P.525-5 式(6)".
const SOURCES=[[/^ITU-R (P\.\d+(?:-\d+)?)/,m=>'ITU-R '+m[1]],[/^NASA, State-of-the-Art of Small Spacecraft/,()=>'NASA SST-SOA'],[/^Texas Instruments (\w+)/,m=>'TI '+m[1]]];
export function citation(ref){
 if(!ref?.source_title)return '';
 const title=ref.source_title,known=SOURCES.map(([re,f])=>[title.match(re),f]).find(([m])=>m);
 const name=known?known[1](known[0]):title.split(/[,，(（]/)[0].trim(),loc=ref.locator||'';
 const eq=loc.match(/equation \((\d+)\)/i),sec=loc.match(/section (\d+(?:\.\d+)*)/i)||loc.match(/^(\d+(?:\.\d+)+)\s/);
 return name+(eq?` 式(${eq[1]})`:sec?` §${sec[1]}`:'');
}
// One row per plan step: every input names its source (text, manual, an earlier step, missing or conflicting).
export function planSteps(plan,report,result){
 const order=Object.fromEntries(plan.steps.map((s,i)=>[s.step_id,i+1]));
 const params=Object.fromEntries((report.parameters_proposal||[]).map(p=>[p.parameter_id,p]));
 const refs=Object.fromEntries((report.evidence_refs||[]).map(r=>[r.catalog_id,r]));
 const done=Object.fromEntries((result?.steps||[]).map(s=>[s.step_id,s]));
 const single=plan.steps.length===1&&result&&!result.steps;
 return plan.steps.map((step,i)=>{
  const value=done[step.step_id]?.output.value??(single&&result.outputs.length===1?result.outputs[0].value:null);
  return {n:i+1,id:step.step_id,tool:step.tool_id,title:toolNames[step.tool_id]||step.tool_id,cite:citation(refs[step.tool_id]),unit:step.expected_unit,value,
   out:value!=null?`${formatDomain(value,2)} ${step.expected_unit}`:single&&result.outputs.length>1?`${result.outputs.length} 组结果`:null,
   inputs:Object.entries(step.inputs).map(([name,b])=>{
    const base={name,label:parameterNames[name]||name,symbol:symbols[name]||''};
    if(b.kind==='step')return {...base,kind:'step',tag:'上一步',value:'← '+circled(order[b.ref]),ref:order[b.ref]};
    const p=params[b.ref];
    if(!p||p.value===null)return p?.status==='conflicting'?{...base,kind:'conflict',tag:'冲突',value:'待选定'}:{...base,kind:'missing',tag:'待补充',value:'待补充'};
    const manual=p.origins.some(o=>o.kind==='manual_form');
    return {...base,kind:manual?'manual':'text',tag:manual?'手工':'原文',value:`${formatDomain(p.value)} ${p.unit}`};
   })};
 });
}
export function el(tag,text,cls){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;}
function button(text,fn,cls='text-button'){const b=el('button',text,cls);b.type='button';b.addEventListener('click',fn);return b;}
function block(title,text,cls=''){const b=el('section',undefined,'detail-block '+cls);if(title)b.append(el('h3',title));if(Array.isArray(text)){const ul=el('ul');text.forEach(t=>ul.append(el('li',t)));b.append(ul);}else if(text)b.append(el('p',text));return b;}
function jsonDetails(label,data){const d=el('details');d.append(el('summary',label),el('pre',JSON.stringify(data,null,2)));return d;}
// Folds remember what the reader opened across redraws of the same task version.
function fold(ctx,key,summary,defaultOpen=false,cls=''){
 const d=el('details',undefined,('fold '+cls).trim()),saved=ctx.open?.get(key);
 if(saved??defaultOpen)d.open=true;
 d.addEventListener('toggle',()=>ctx.open?.set(key,d.open));
 d.append(typeof summary==='string'?el('summary',summary):summary);return d;
}
function sourceLink(ref){if(!ref.source_url)return el('p','本地资料：'+(ref.source_id||'未提供路径'),'hint');try{const u=new URL(ref.source_url);if(!['http:','https:'].includes(u.protocol))return el('p','来源链接不可打开','hint');const a=el('a','打开出处 ↗');a.href=u.href;a.target='_blank';a.rel='noopener noreferrer';return a;}catch{return el('p','来源链接格式无效','hint');}}
function formulaMath(){
 const ns='http://www.w3.org/1998/Math/MathML';
 const m=(tag,text,...children)=>{const n=document.createElementNS(ns,tag);if(text)n.textContent=text;n.append(...children);return n;};
 const term=(symbol,unit)=>m('mrow',null,m('mn','20'),m('msub',null,m('mi','log'),m('mn','10')),m('mo','('),m('mfrac',null,m('mi',symbol),m('mrow',null,m('mn','1'),m('mtext',unit))),m('mo',')'));
 const math=m('math',null,m('mrow',null,m('msub',null,m('mi','L'),m('mtext','dB')),m('mo','='),m('mn','92.4'),m('mo','+'),term('f','GHz'),m('mo','+'),term('d','km')));
 math.setAttribute('display','block');math.setAttribute('aria-label','L dB 等于 92.4 加 20 log10(f/GHz) 加 20 log10(d/km)');return math;
}
function retrievalTable(found){
 const b=el('section',undefined,'detail-block');
 b.append(el('h3','检索命中'),el('p',`${RETRIEVAL[found.mode_used]}检索 · 知识库 ${found.corpus.size} 条 · 返回 ${found.hits.length}/${found.top_k} · 送入 ${found.top_n} · ${fmt(found.latency_ms.total)}`+(found.degraded?` · 请求${RETRIEVAL[found.mode_requested]}，向量未就绪`:''),'hint'));
 const table=el('table'),head=el('tr');['#','公式卡','词项','向量','融合','上下文'].forEach(t=>head.append(el('th',t)));const thead=el('thead');thead.append(head);table.append(thead);
 const body=el('tbody'),num=v=>v==null?'—':v.toFixed(4);
 for(const h of found.hits){const row=el('tr'),card=el('td'),used=found.used.includes(h.id);card.append(el('strong',h.title),el('small',h.id+(h.source?.title?' · '+h.source.title:'')));
  row.append(el('td',String(h.rank)),card,el('td',num(h.scores.lexical),'num'),el('td',num(h.scores.dense),'num'),el('td',num(h.scores.fused),'num'),el('td',used?'已送入':'未送入','chip '+(used?'run':'')));body.append(row);}
 table.append(body);const wrap=el('div',undefined,'table-wrap');wrap.append(table);b.append(wrap);
 return b;
}

const TAGS=[['missing','待补充'],['conflict','冲突'],['text','原文'],['manual','手工'],['step','上一步']];
function sourceSummary(inputs){
 const count=new Map();for(const x of inputs)count.set(x.kind,(count.get(x.kind)||0)+1);
 return TAGS.filter(([k])=>count.has(k)).map(([k,t])=>t+(count.get(k)>1?` ×${count.get(k)}`:'')).join(' · ');
}
function inputRows(ctx,inputs){
 const ul=el('ul',undefined,'inputs');
 for(const x of inputs){
  const row=el('li',undefined,'input '+x.kind+(x.name===ctx.focusParameter?' highlight-row':'')),label=el('span',undefined,'in-name');
  label.append(el('span',x.label));if(x.symbol)label.append(el('i',x.symbol));
  const open=['missing','conflict'].includes(x.kind);
  const pick=open?ctx.onMissing:x.kind==='step'?null:ctx.onParameter;
  row.append(label,pick?button(open?x.value+' →':x.value,()=>pick(x.name),'text-button in-value'):el('span',x.value,'in-value'));
  if(!open)row.append(el('span',x.tag,'tag '+x.kind));
  ul.append(row);
 }
 return ul;
}
function stepList(ctx,steps,defaultOpen){
 const list=el('ol',undefined,'steps');
 for(const s of steps){
  const head=el('summary',undefined,'step-head'),name=el('span',undefined,'step-name');
  name.append(el('span',s.title,'step-title'));if(s.cite)name.append(el('span',s.cite,'cite'));
  head.append(el('span',circled(s.n),'step-no'),name,el('span',s.out||s.unit,'step-out'+(s.out?' done':'')),el('span',sourceSummary(s.inputs),'step-sources'));
  const d=fold(ctx,'step:'+s.id,head,defaultOpen,'step');
  d.append(inputRows(ctx,s.inputs));const li=el('li');li.append(d);list.append(li);
 }
 return list;
}
// The registered card of every step. The final card is stored with the task; the others come from
// the catalog and are shown only when their content hash equals the one recorded in the task evidence.
export function stepFormulas(plan,report,result,cards={},model=null){
 const refs=Object.fromEntries((report.evidence_refs||[]).map(r=>[r.catalog_id,r]));
 return planSteps(plan,report,result).map(s=>{
  const ref=refs[s.tool],served=cards[s.tool];
  const status=model?.id===s.tool?'ok':!ref?'missing':served===undefined?'loading':served===null?'missing':served.content_hash===ref.content_hash?'ok':'changed';
  return {...s,status,card:status!=='ok'?null:model?.id===s.tool?model:served,version:ref?.card_version||''};
 });
}
function planCard(host,ctx,open){
 const {state}=ctx,r=state.report,plan=r.calculation_plan_proposal;
 const goal=el('dl',undefined,'goal');goal.append(el('dt','目标'),el('dd',plan.objective||'—'));
 const cond=(r.conditions||[]).map(c=>conditionNames[c]||c).join(' · ');if(cond)goal.append(el('dt','条件'),el('dd',cond));
 host.append(goal,stepList(ctx,planSteps(plan,r,state.result),open));
 const as=(plan.assumptions?.length?plan.assumptions:r.assumptions||[]).map(humanize);
 if(as.length){const d=fold(ctx,'assumptions',`模型假设 ${as.length} 条`);const ul=el('ul');as.forEach(t=>ul.append(el('li',t)));d.append(ul);host.append(d);}
}
function knownView(host,state){
 const known=(state.report?.parameters_proposal||[]).filter(p=>p.value!==null);
 const approx=new Set((state.report?.diagnostics||[]).filter(d=>d.code==='PARAMETER_APPROXIMATE').map(d=>d.details.field));
 const box=el('section',undefined,'known');box.append(el('h3','已识别'));
 if(!known.length)box.append(el('p','尚未识别到参数','muted'));
 const ul=el('ul',undefined,'inputs');
 for(const p of known){const manual=p.origins.some(o=>o.kind==='manual_form'),row=el('li',undefined,'input '+(manual?'manual':'text'));
  row.append(el('span',parameterNames[p.canonical_name]||p.canonical_name,'in-name'),el('span',`${formatDomain(p.value)} ${p.unit}${approx.has(p.canonical_name)?'（近似）':''}`,'in-value'),el('span',manual?'手工':'原文','tag '+(manual?'manual':'text')));ul.append(row);}
 box.append(ul);host.append(box);
}
function answer(host,state){
 const sec=el('section',undefined,'answer'),outs=state.result.outputs;
 const title=state.result.steps?toolNames[state.result.model_id]||state.result.model_id:toolNames.fspl_ghz;
 for(const [i,value] of outs.entries()){
  const metric=el('div',undefined,'metric');metric.append(el('strong',formatDomain(value.value,2)),el('span',value.unit));
  sec.append(el('p',outs.length>1?`候选 ${i+1} · ${title}`:title,'eyebrow'),metric);
  if(value.inputs)sec.append(el('p',Object.entries(value.inputs).map(([k,v])=>`${parameterNames[k]||k} ${formatDomain(v)} ${{frequency_ghz:'GHz',distance_km:'km'}[k]||''}`).join('；'),'hint'));
 }
 sec.append(el('p',state.final_report.conclusion,'conclusion'));host.append(sec);
}
function recordsContent(host,ctx){
 const {state,models}=ctx;
 if(state.calculation_role)host.append(block('计算角色',`${roleModeNames[state.calculation_role.mode]||state.calculation_role.mode} · 计算 ${state.calculation_attempts||1} 次（上限 2）`));
 if(state.review_assessment){const a=state.review_assessment;host.append(block('审查角色',`${roleModeNames[a.role.mode]||a.role.mode} · ${reviewDecisionNames[a.role.proposal.decision]}`),jsonDetails('审查记录',a));}
 const made=provenance(state,models);if(made.length){const b=el('section',undefined,'detail-block provenance');b.append(el('h3','生成配置'));const grid=el('dl');for(const [k,v] of made)grid.append(el('dt',k),el('dd',v));b.append(grid);host.append(b);}
 if(state.routing_decisions?.length)host.append(jsonDetails('调度与重算',state.routing_decisions));
 const ds=diagnosticMessages(state.report?.diagnostics);if(ds.length)host.append(block('处理说明',ds),jsonDetails('逐次诊断',state.report.diagnostics));
}
function resultView(host,ctx){
 const {state}=ctx;answer(host,state);
 const drift=ctx.historical?[]:settingsDrift(state,ctx.settings);
 if(drift.length){const p=el('p',`默认设置已变：${drift.join('；')}。本结果不变。`,'drift');if(ctx.onReparse)p.append(button('按新设置重新解析',ctx.onReparse));host.append(p);}
 const r=state.review?.report||state.report,plan=r?.calculation_plan_proposal;
 if(plan)host.append(stepList(ctx,planSteps(plan,r,state.result),false));
 const v=state.validations||[];
 if(v.length){const d=fold(ctx,'checks',`${v.filter(x=>x.passed).length}/${v.length} 校验通过`,false,'checks'),ul=el('ul',undefined,'check-list');for(const x of v)ul.append(el('li',`${x.passed?'✓':'×'} ${checkNames[x.validator_id]||x.validator_id}`,x.passed?'ok':'bad'));d.append(ul);host.append(d);}
 const lim=(state.final_report.limitations||[]).map(humanize);
 if(lim.length){const scope=el('section',undefined,'scope');scope.append(el('h3','适用范围'),el('p',lim[0]));if(lim.length>1){const more=fold(ctx,'scope',`其余 ${lim.length-1} 条`),ul=el('ul');lim.slice(1).forEach(t=>ul.append(el('li',t)));more.append(ul);scope.append(more);}host.append(scope);}
 const records=fold(ctx,'records','记录与配置');recordsContent(records,ctx);host.append(records);
}
function links(ctx){const nav=el('nav',undefined,'detail-links');for(const [v,t] of [['parameters','参数溯源'],['formula','公式'],['evidence','依据']])nav.append(button(t,()=>ctx.onView(v)));return nav;}
function mainView(host,ctx){
 const {state}=ctx;
 if(!state){const size=ctx.models?.corpus?.size;host.append(el('p',`已登记公式${size?` ${size} 张`:''} · 确定性求值 · 独立校验`,'muted intro'));return;}
 if(ctx.activeContext){host.append(el('p','解析完成后在此生成计算计划','muted intro'));return;}
 if(state.status==='COMPLETED'&&state.final_report){resultView(host,ctx);host.append(links(ctx));return;}
 if(state.failure)host.append(block('原因',[state.failure.message,'下一步：'+state.failure.next_action],'warning'));
 const r=state.report,plan=r?.calculation_plan_proposal;
 if(plan)planCard(host,ctx,state.status!=='CANCELLED');else if(r)knownView(host,state);
 if(r)host.append(links(ctx));
}

function paramsView(host,ctx){
 const {state,focusParameter,onParameter}=ctx,r=state.report,text=state.request.raw_text;
 const quote=el('p',undefined,'source-quote');
 const p=r.parameters_proposal.find(p=>p.canonical_name===focusParameter),origin=p?.origins.find(o=>o.kind==='user_text'&&o.span);
 if(origin){const chars=Array.from(text);quote.append(document.createTextNode(chars.slice(0,origin.span[0]).join('')),el('mark',sourceExcerpt(text,origin.span)),document.createTextNode(chars.slice(origin.span[1]).join('')));}else quote.textContent=text;
 const raw=el('section',undefined,'detail-block');raw.append(el('h3','原文'),quote);host.append(raw);
 const table=el('table'),tr=el('tr');['参数','值','来源'].forEach(t=>tr.append(el('th',t)));const thead=el('thead');thead.append(tr);table.append(thead);const body=el('tbody');
 for(const param of r.parameters_proposal){
  const name=param.canonical_name,row=el('tr',undefined,name===focusParameter?'highlight-row':''),cell=el('td');
  cell.append(button(`${parameterNames[name]||name}${symbols[name]?' · '+symbols[name]:''}`,()=>onParameter(name)));
  row.append(cell,el('td',param.value===null?(param.status==='conflicting'?'冲突':'缺失'):`${formatDomain(param.value)} ${param.unit}`,'num'));
  const sources=el('td');
  for(const o of param.origins)sources.append(el('small',`${o.kind==='user_text'?'原文':'手工'} · ${formatDomain(o.value)} ${o.unit}`+(o.kind==='user_text'&&o.span?` · “${sourceExcerpt(text,o.span)}”`:'')));
  const turn=state.conversation?.field_sources?.[name];if(turn)sources.append(el('small',`第 ${turn.number} 条补充`));
  if(!param.origins.length)sources.append(el('small','待补充'));
  row.append(sources);body.append(row);
 }
 table.append(body);const wrap=el('div',undefined,'table-wrap');wrap.append(table);host.append(wrap);
 if(state.confirmed_snapshot)host.append(el('p',`已确认 · ${new Date(state.confirmed_snapshot.confirmed_at).toLocaleString('zh-CN',{hour12:false})}`,'hint'));
}
const FORMULA_STATUS={loading:'正在读取登记公式…',missing:'未找到登记公式卡',changed:'公式卡已变更，与本任务所用版本不同，不显示'};
function formulaView(host,ctx){
 const {state}=ctx,r=state.review?.report||state.report,plan=r.calculation_plan_proposal;
 if(!plan){host.append(el('p','尚无可执行公式','muted'));return;}
 const steps=stepFormulas(plan,r,state.result,ctx.cards||{},state.review?.model);
 for(const s of steps){
  const sec=el('section',undefined,'formula-step'),head=el('div',undefined,'formula-head');
  head.append(el('span',circled(s.n),'step-no'),el('strong',s.card?.title||s.title));if(s.cite)head.append(el('span',s.cite,'cite'));
  if(s.version)head.append(el('span','v'+s.version,'version'));
  sec.append(head);
  if(s.card){
   const math=el('div',undefined,'math-formula');
   if(s.card.id==='fspl_ghz'&&s.card.expression==='92.4 + 20*log10(frequency_ghz) + 20*log10(distance_km)')math.append(formulaMath());else math.append(el('code',symbolic(s.card),'symbolic'));
   sec.append(math);
  }else sec.append(el('p',FORMULA_STATUS[s.status],s.status==='loading'?'hint':'hint warn-text'));
  const rows=inputRows(ctx,s.inputs);
  if(s.out){const out=el('li',undefined,'input result'),label=el('span',undefined,'in-name');label.append(el('span','结果'));out.append(label,el('span',s.out,'in-value'));rows.append(out);}
  sec.append(rows);host.append(sec);
 }
 const actual=state.result?.normalized_inputs;
 if(actual&&!state.result.steps&&state.result.outputs.length>1)host.append(block('实际代入',state.final_report?.conclusion||'候选分别执行'));
 else if(actual&&!state.result.steps&&actual.frequency_ghz!=null)host.append(block('实际代入',`92.4 + 20 × log₁₀(${formatDomain(actual.frequency_ghz)}) + 20 × log₁₀(${formatDomain(actual.distance_km)}) = ${formatDomain(state.result.outputs[0].value,2)} dB`));
 const raw=steps.filter(s=>s.card).map(s=>`${s.card.id} v${s.card.version}: ${s.card.expression}`);
 if(raw.length)host.append(jsonDetails('程序表达式',raw));
}
function evidenceView(host,ctx){
 const {state}=ctx,r=state.report,model=state.review?.model;
 if(state.retrieval)host.append(retrievalTable(state.retrieval));
 if(!r.evidence_refs.length){host.append(block('暂无可用依据','检索为空时不推定公式适用。','warning'));return;}
 for(const [i,ref] of r.evidence_refs.entries()){
  const b=block(citation(ref)||`依据 ${i+1}`);
  b.append(el('p',ref.source_title,'hint'),el('p','定位：'+(ref.locator==='formula card source metadata'?'仅有卡片元数据':ref.locator||'未提供')),
   el('p',`公式卡 ${ref.catalog_id} · v${ref.card_version} · ${ref.status==='verified'?'已核验':ref.status}`,'hint'));
  if(ref.excerpt)b.append(el('p',ref.excerpt,'excerpt'));
  const source=model?.sources?.find(x=>x.title===ref.source_title);if(source?.derivation)b.append(block('原式与换算',source.derivation));
  b.append(sourceLink(ref),jsonDetails('证据快照',ref));host.append(b);
 }
 host.append(el('p','检索只提供候选与出处；数值只来自登记公式。','hint'));
}
function modelView(host,ctx){
 const {state,modelService,historical}=ctx;
 host.append(block('服务',serviceText(modelService)+(modelService?.checked_at?` · ${new Date(modelService.checked_at).toLocaleTimeString('zh-CN',{hour12:false})}`:'')));
 if(state)host.append(block(historical?'该版本的调用':'本任务的调用',callSummary(state)));
}
function recordsView(host,ctx){recordsContent(host,ctx);host.append(jsonDetails('任务数据',ctx.state));}
const VIEWS={parameters:['参数溯源',paramsView],formula:['公式',formulaView],evidence:['依据',evidenceView],model:['大模型',modelView],records:['记录与配置',recordsView]};
export function renderRight(host,ctx){
 host.replaceChildren();
 const view=VIEWS[ctx.view];
 if(view&&(ctx.state?.report||ctx.view==='model')){
  const head=el('div',undefined,'view-head');head.append(button('← 返回',()=>ctx.onView('main'),'text-button back'),el('h3',view[0]));host.append(head);
  view[1](host,ctx);return;
 }
 mainView(host,ctx);
}

// Popover on a flow node: status, role, a few facts and where to read more.
const NODE_VIEW={input:['parameters','参数溯源'],requirements:['parameters','参数溯源'],confirmation:['parameters','参数溯源'],compute_agent:['formula','公式'],model:['formula','公式'],
 rag:['evidence','依据'],knowledge:['evidence','依据'],llm:['model','大模型'],validator_agent:['records','记录'],publish:['main','结果'],orchestrator:['records','记录'],state:['records','记录']};
export function nodeCard(id,{state=null,events=[],latency={},modelService=null}={}){
 const [title,role]=nodes[id]||[id,''],status=nodeStates(state,events)[id]||'idle';
 const r=state?.report,plan=r?.calculation_plan_proposal,v=state?.validations||[],lines=[role];
 if(state)switch(id){
  case 'input':lines.push(state.request?.raw_text?.slice(0,40)+((state.request?.raw_text?.length||0)>40?'…':''));break;
  case 'orchestrator':if(state.routing_decisions?.length)lines.push(`调度 ${state.routing_decisions.length} 次`);break;
  case 'requirements':if(r){const ps=r.parameters_proposal||[];lines.push(`解析：${r.component_modes?.interpretation==='llm'?'本机大模型':'确定性规则'}`,`目标：${plan?.objective||'待明确'}`,`参数：${ps.filter(p=>p.value!==null).length}/${ps.length}`);}break;
  case 'compute_agent':if(state.calculation_role)lines.push(`${roleModeNames[state.calculation_role.mode]||state.calculation_role.mode} · 计算 ${state.calculation_attempts||1} 次`);if(plan)lines.push(`计算链 ${plan.steps.length} 步`);break;
  case 'validator_agent':if(v.length)lines.push(`${v.filter(x=>x.passed).length}/${v.length} 校验通过`);if(state.review_assessment)lines.push('审查：'+(reviewDecisionNames[state.review_assessment.role.proposal.decision]||''));break;
  case 'confirmation':lines.push(state.confirmed_snapshot?'已确认':state.status==='AWAITING_CONFIRMATION'?'等待确认':'');break;
  case 'model':if(plan)lines.push(plan.steps.map(s=>toolNames[s.tool_id]||s.tool_id).join(' → '));break;
  case 'publish':if(state.final_report)lines.push(state.final_report.conclusion);break;
  case 'state':lines.push(`第 ${state.revision} 版 · 保存 ${state.state_version}`);break;
  case 'llm':lines.push(callSummary(state)[0]);break;
  case 'rag':if(state.retrieval)lines.push(`${RETRIEVAL[state.retrieval.mode_used]}检索 · 命中 ${state.retrieval.hits.length} · 送入 ${state.retrieval.top_n}`);break;
  case 'knowledge':if(r?.evidence_refs?.length)lines.push(r.evidence_refs.map(citation).join('、'));break;
 }
 if(id==='llm')lines.splice(1,0,serviceText(modelService));
 const [view,label]=NODE_VIEW[id]||[];
 return {title,tone:status,status:(statusText[status]||status)+(latency[id]?` · ${latency[id]}`:''),lines:lines.filter(Boolean),link:view&&(view!=='main'||state?.final_report)?{view,label}:null};
}
