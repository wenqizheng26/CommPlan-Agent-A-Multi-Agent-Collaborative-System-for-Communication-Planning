// Durations derived from activity events. Observation only: saved task state stays authoritative.
const LABELS={state:'读取 / 保存状态',knowledge:'知识库读取',parse:'规则解析',retrieval:'知识检索',planning:'生成计划',
 model:'计算模型 FSPL',validation:'硬校验',publish:'发布结果','llm/intent':'需求理解 · 模型','llm/supplement':'补问合并 · 模型',
 'llm/compute_agent':'计算建议 · 模型','llm/validator_agent':'结构化审查 · 模型',requirements:'需求与规划（整体）',
 calculation:'专业计算（整体）',review:'结果审查（整体）',interpretation:'意图理解（整体）',rag:'RAG 检索（整体）',orchestrator:'总控调度'};
export const REASONS={offline:'离线',timeout:'超时',structure:'输出不合格',numbers:'数字未通过核对',rejected:'请求被拒',unrecorded:'未记录原因'};
export const label=key=>LABELS[key]||key;
// Leaf spans for the waterfall: containers (requirements, calculation, review, rag) overlap their children.
const LEAVES=new Set(['state','knowledge','parse','retrieval','planning','model','validation','publish']);

export function fmt(ms){
 if(ms==null||!Number.isFinite(ms))return '';
 return ms>=1000?(ms/1000).toFixed(2)+' s':ms>=10?Math.round(ms)+' ms':ms.toFixed(1)+' ms';
}

export function spans(events=[]){
 const open=new Map(),done=[];
 for(const e of events){
  if(e.node==='command')continue;
  const key=e.node==='llm'?`llm/${e.details?.purpose||e.details?.caller||'?'}`:e.node;
  const slot=e.run_id+'|'+key,t=Date.parse(e.at);
  if(e.phase==='started')open.set(slot,{run_id:e.run_id,node:e.node,key,start:t,details:{...e.details}});
  else if(['completed','failed','skipped'].includes(e.phase)&&open.has(slot)){
   const s=open.get(slot);open.delete(slot);done.push({...s,end:t,ms:t-s.start,phase:e.phase,details:{...s.details,...e.details}});
  }
 }
 return {done,open:[...open.values()]};
}

function lastRunWith(done,keys){
 const hit=done.findLast(s=>keys.includes(s.key));
 return hit?done.filter(s=>s.run_id===hit.run_id&&keys.includes(s.key)):[];
}
const sum=list=>list.reduce((a,s)=>a+s.ms,0);

// Flow node -> activity keys. The shared LLM badge totals every model call of this version.
const NODE_KEYS={requirements:['requirements'],compute_agent:['calculation'],validator_agent:['validation','review'],
 model:['model'],publish:['publish'],rag:['rag'],knowledge:['knowledge']};
export function nodeLatency(events=[],now=Date.now()){
 const {done,open}=spans(events),out={};
 for(const [node,keys] of Object.entries(NODE_KEYS)){const list=lastRunWith(done,keys);if(list.length)out[node]=fmt(sum(list));}
 const llm=done.filter(s=>s.node==='llm');if(llm.length)out.llm=fmt(sum(llm));
 const waiting=open.findLast(s=>s.node==='llm');
 if(waiting){
  const text=`已等待 ${Math.max(0,Math.round((now-waiting.start)/1000))} s`+(waiting.details.timeout_s?` / 超时 ${Math.round(waiting.details.timeout_s)} s`:'');
  out.llm=text;
  const owner={intent:'requirements',supplement:'requirements',compute_agent:'compute_agent',validator_agent:'validator_agent'}[waiting.details.purpose];
  if(owner)out[owner]=text;
 }
 return out;
}

const STEP_KEYS=[['requirements'],[],['calculation'],['validation','review'],['publish']];
export function stepTimes(events=[]){
 const {done}=spans(events);
 return STEP_KEYS.map(keys=>{const list=keys.length?lastRunWith(done,keys):[];return list.length?fmt(sum(list)):'';});
}

// One sentence for the latest committed run: total, model share, failed model calls.
export function runSummary(events=[]){
 const last=events.findLast(e=>e.node==='command'&&e.phase==='committed');if(!last)return '';
 const run=events.filter(e=>e.run_id===last.run_id),start=run.find(e=>e.node==='command'&&e.phase==='started');if(!start)return '';
 const total=Date.parse(last.at)-Date.parse(start.at),{done}=spans(run);
 const model=sum(done.filter(s=>s.node==='llm')),failed=done.filter(s=>s.node==='llm'&&s.phase==='failed').length;
 let text=`本次 ${fmt(total)}`;
 if(model>0)text+=`，其中模型 ${Math.round(model/total*100)}%`;
 if(failed)text+=`，模型调用失败 ${failed} 次`;
 return text+'。';
}

export function renderWaterfall(host,events,el){
 host.replaceChildren();
 const runs=[...new Set(events.filter(e=>e.node==='command'&&e.phase==='started').map(e=>e.run_id))];
 if(!runs.length){host.append(el('p','尚无本版本的运行记录。','hint'));return;}
 for(const id of runs.slice(-2)){
  const run=events.filter(e=>e.run_id===id),start=Date.parse(run[0].at),end=Date.parse(run.at(-1).at),span=Math.max(1,end-start);
  const action=run[0].details?.action,box=el('section',undefined,'waterfall');
  box.append(el('h3',`${{create:'提交需求',edit:'修改需求',supplement:'补充',answer:'回答问题',confirm:'确认后计算',cancel:'取消'}[action]||action} · ${fmt(end-start)}`));
  for(const s of spans(run).done.filter(s=>LEAVES.has(s.key)||s.node==='llm')){
   const row=el('div',undefined,'waterfall-row'),track=el('div',undefined,'waterfall-track'),bar=el('span',undefined,'waterfall-bar '+(s.node==='llm'?(s.phase==='failed'?'failed':'model'):'deterministic'));
   bar.style.left=((s.start-start)/span*100).toFixed(2)+'%';bar.style.width=`max(3px, ${((s.ms)/span*100).toFixed(2)}%)`;
   track.append(bar);
   row.append(el('span',label(s.key)+(s.phase==='failed'?`（失败 · ${REASONS[s.details.reason]||s.details.reason||'未记录原因'}）`:''),s.node==='llm'?'':'muted'),track,el('span',fmt(s.ms),'waterfall-ms'));
   box.append(row);
  }
  host.append(box);
 }
}

export function miniWaterfall(host,events,el){
 host.replaceChildren();
 const last=events.findLast(e=>e.node==='command'&&e.phase==='started');if(!last)return;
 const run=events.filter(e=>e.run_id===last.run_id),start=Date.parse(run[0].at),span=Math.max(1,Date.parse(run.at(-1).at)-start);
 for(const s of spans(run).done.filter(s=>s.node==='llm')){
  const bar=el('span',undefined,'mini-bar '+(s.phase==='failed'?'failed':'model'));
  bar.style.left=((s.start-start)/span*100).toFixed(2)+'%';bar.style.width=((s.ms)/span*100).toFixed(2)+'%';host.append(bar);
 }
}

export function renderMetrics(host,metrics,el){
 host.replaceChildren();
 if(!metrics?.runs){host.append(el('p','尚无运行记录。完成几次任务后在此统计。','hint'));return;}
 host.append(el('p',`最近 ${metrics.runs} 次运行 · 运行观察记录，不是任务的正式状态。条形为 p95，按对数刻度。`,'hint'));
 const max=Math.log10(Math.max(31000,...metrics.modules.map(m=>m.p95))),min=Math.log10(3);
 const groups=[['模型调用（成功）',m=>m.key.startsWith('llm/')&&m.phase==='completed','model'],
  ['模型调用（失败后降级）',m=>m.key.startsWith('llm/')&&m.phase==='failed','failed'],
  ['确定性模块',m=>LEAVES.has(m.key)&&m.phase==='completed','deterministic']];
 const table=el('div',undefined,'metrics-table');
 const head=el('div',undefined,'metrics-row metrics-head');['模块','','p50','p95','n'].forEach(t=>head.append(el('span',t)));table.append(head);
 for(const [title,match,kind] of groups){
  const rows=metrics.modules.filter(match);if(!rows.length)continue;
  table.append(el('div',title,'metrics-group'));
  for(const m of rows){
   const row=el('div',undefined,'metrics-row'),track=el('span',undefined,'metrics-track'),bar=el('span',undefined,'metrics-bar '+kind);
   bar.style.width=(Math.max(0,(Math.log10(Math.max(3,m.p95))-min)/(max-min))*100).toFixed(1)+'%';track.append(bar);
   row.append(el('span',label(m.key)),track,el('span',fmt(m.p50),'num'),el('span',fmt(m.p95),'num'+(kind==='failed'&&m.p95>=25000?' alert':'')),el('span',String(m.n),'num muted'));
   table.append(row);
  }
 }
 host.append(table);
 const reasons=Object.entries(metrics.failures||{});
 if(reasons.length)host.append(el('p','模型调用失败原因：'+reasons.map(([r,n])=>`${REASONS[r]||r} ${n} 次`).join('，')+'。','hint'));
 if(metrics.models?.length){
  const compare=el('section',undefined,'detail-block');compare.append(el('h3','按模型（成功调用）'));
  for(const m of metrics.models)compare.append(el('p',`${m.model_id} · p50 ${fmt(m.p50)} · p95 ${fmt(m.p95)} · ${m.n} 次`));
  if(metrics.models.length<2)compare.append(el('p','换用另一个模型或参数档案运行后，在此并列比较。','hint'));
  host.append(compare);
 }
}
