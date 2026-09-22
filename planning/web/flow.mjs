// Catalog labels refer to the two-page source Visio; status is runtime evidence.
export const nodes = {
 input:['任务输入','原文与补充条件','overview'],
 requirements:['需求与规划 Agent','已接入 · 受规则约束','overview'],
 parse:['解析需求','程序抽取参数与单位','parameters'],
 retrieval:['检索专业依据','词项检索 · 保留出处','evidence'],
 interpretation:['意图建议（可选）','本机 LLM · 可明确降级','overview'],
 planning:['生成参数与计划','登记模型 · 条件检查','plan'],
 confirmation:['参数核对与确认','用户确认当前版本','parameters'],
 calculation:['专业计算','受控调用登记公式','formula'],
 validation:['结果校验','程序执行 8 项检查','result'],
 publish:['结果与证据报告','经校验后发布','result'],
 supplement:['需求确认与补充','多问题汇总 · 保存部分回答','parameters'],
 gap:['模型或依据缺口','说明缺口，停止计算','evidence'],
 failure:['异常处理','失败原因与下一步','overview'],
 explanation:['LLM 解释与审查','未接入 · 当前为程序报告','result'],
 orchestrator:['总控 Agent','受控策略 · 退回与重算有上限','overview'],
 compute_agent:['专业计算 Agent','工具调用建议 · 程序受控执行','formula'],
 validator_agent:['验证与解释 Agent','硬校验 + 可选结构化审查','result'],
 review:['结构化审查','引用结果与已确认假设','result'],
 model:['链路损耗计算模型','登记公式与程序','formula'],
 llm:['共享大模型 LLM','可选 · 需求、计算与审查','overview'],
 rag:['RAG 检索服务','当前仅词项检索','evidence'],
 knowledge:['专业知识库','版本化公式卡与来源','evidence'],
 state:['共享状态／检查点','确认快照、历史与恢复','overview'],
};
export const statusText={idle:'未开始',running:'运行中',completed:'已完成',waiting:'等待处理',failed:'失败',degraded:'调用已降级',skipped:'未调用',cancelled:'已取消',unavailable:'未接入',partial:'部分接入',interrupted:'已中断'};
export function relevantEvents(state, events){return state ? events.filter(e=>e.task_id===state.task_id&&e.revision===state.revision):[];}
export function activityFresh(previous,next){return !previous.length||(next.at(-1)?.seq||0)>=(previous.at(-1)?.seq||0);}
export function openRun(events){const last=events.at(-1);if(!last)return null;const run=events.filter(e=>e.run_id===last.run_id);return run.some(e=>e.node==='command'&&['committed','replayed','rejected','interrupted'].includes(e.phase))?null:last;}
export function nodeStates(state, events=[]){
 const s=Object.fromEntries(Object.keys(nodes).map(n=>[n,'idle']));
 s.explanation='unavailable';s.orchestrator=s.validator_agent='partial';
 if(!state)return s;
 s.input='completed';
 if(state.report){
  for(const n of ['parse','retrieval','planning','requirements'])s[n]='completed';
  s.interpretation=state.report.component_modes?.interpretation==='llm'?'completed':'skipped';
 }
 if(state.status==='AWAITING_CONFIRMATION')s.confirmation='waiting';
 if(state.status==='AWAITING_INPUT')s.supplement='waiting';
 if(state.resolved_input_issues?.length&&!state.input_issues?.length)s.supplement='completed';
 if(state.status==='NEEDS_MODEL')s.gap='waiting';
 if(state.status==='FAILED')s.failure='failed';
 if(state.status==='CANCELLED')s.confirmation='cancelled';
 if(state.status==='COMPLETED')for(const n of ['confirmation','calculation','validation','publish'])s[n]='completed';
 const relevant=relevantEvents(state,events);
 const last=relevant.at(-1);
 if(last&&state.status!=='COMPLETED'){
  const run=relevant.filter(e=>e.run_id===last.run_id);
  const terminal=run.findLast(e=>e.node==='command'&&['rejected','interrupted','committed','replayed'].includes(e.phase));
  if(['rejected','interrupted'].includes(terminal?.phase)){
   if(state.status!=='COMPLETED')s.failure=terminal.phase==='rejected'?'failed':'interrupted';
  }else if(terminal?.phase!=='replayed'){
   for(const e of run)if(e.node in s&&e.node!=='explanation'){
    s[e.node]=e.phase==='started'?'running':e.phase;
   }
   // A parent failure terminates an unfinished child; never leave a stuck spinner.
   if(s.requirements==='failed'||s.failure==='failed')for(const n of ['parse','retrieval','interpretation','planning'])if(s[n]==='running')s[n]='failed';
   if(terminal)for(const n in s)if(s[n]==='running')s[n]='interrupted';
  }
 }
 s.compute_agent=s.calculation;s.validator_agent=s.validation==='idle'?'partial':s.validation;
 if(state.review_assessment){const decision=state.review_assessment.role.proposal.decision;s.review=s.validator_agent=decision==='pass'?'completed':'waiting';}
 else if(s.review!=='idle')s.validator_agent=s.review;
 const explicit=new Set(relevant.filter(e=>e.run_id===last?.run_id).map(e=>e.node));
 if(!explicit.has('model')||state.status==='COMPLETED')s.model=s.calculation;
 if(!explicit.has('rag')||state.status==='COMPLETED')s.rag=s.retrieval;
 if(!explicit.has('knowledge')||state.status==='COMPLETED')s.knowledge=s.retrieval;
 if(!explicit.has('llm')||state.status==='COMPLETED')s.llm=s.interpretation;
 if(state.status==='COMPLETED'){
  const modes=[state.report?.component_modes?.interpretation,state.calculation_role?.mode,state.review_assessment?.role?.mode];
  if(modes.includes('llm'))s.llm='completed';
  else if(modes.includes('deterministic_fallback'))s.llm='failed';
 }
 if(!explicit.has('state')||state.status==='COMPLETED')s.state=state.state_version?'completed':'idle';
 if(!explicit.has('orchestrator')||state.status==='COMPLETED')s.orchestrator=state.state_version?'completed':'partial';
 if(['AWAITING_INPUT','NEEDS_MODEL'].includes(state.status))s.requirements='waiting';
 const fallback=state.report?.runtime_health==='degraded'||state.calculation_role?.mode==='deterministic_fallback'||state.review_assessment?.role?.mode==='deterministic_fallback';
 if(fallback&&s.llm!=='running')s.llm='degraded';
 return s;
}

const aliases={calculation:'compute_agent',validation:'validator_agent',review:'validator_agent',retrieval:'rag',interpretation:'llm'};
// Only a real observed call animates an edge. Architecture relations alone do not.
export function edgeState(state,events,from,to){
 const relevant=relevantEvents(state,events), runs=new Map();
 for(const e of relevant)if(e.node==='command')runs.set(e.run_id,e.phase);
 const calls=relevant.filter(e=>{
  const terminal=runs.get(e.run_id);
  if(['rejected','interrupted','replayed'].includes(terminal))return false;
  if(state.status==='COMPLETED'&&terminal!=='committed')return false;
  const a=aliases[e.details?.caller]||e.details?.caller,b=aliases[e.node]||e.node;
  return (a===from&&b===to)||(from==='state'&&to==='orchestrator'&&a==='orchestrator'&&b==='state');
 });
 const phase=calls.at(-1)?.phase;
 return phase==='started'?'running':phase||'idle';
}

const execution=[
 ['input',40,48],['parse',40,148],['retrieval',40,248],['interpretation',40,348],['planning',40,448],
 ['confirmation',330,448],['calculation',330,348],['validation',330,248],['publish',330,148],
 ['supplement',620,448],['gap',620,348],['failure',620,248],['explanation',620,148],
];
const architecture=[
 ['input',330,40],['orchestrator',330,145],
 ['requirements',40,270],['compute_agent',330,270],['validator_agent',620,270],
 ['supplement',40,390],['model',330,390],['publish',620,390],
 ['confirmation',40,490],
 ['llm',40,610],['rag',330,610],['knowledge',620,610],['state',330,720],
];
// mode: task / capability / state. Branch labels reflect actual decision meaning.
const executionEdges=[['input','parse'],['parse','retrieval'],['retrieval','interpretation'],['interpretation','planning'],['planning','confirmation'],['confirmation','calculation'],['calculation','validation'],['validation','publish'],['planning','supplement','缺项/冲突'],['planning','gap','不支持'],['calculation','failure','失败'],['validation','failure','不通过'],['supplement','input','修正后重新提交','return']];
const architectureEdges=[['input','orchestrator'],['orchestrator','requirements'],['orchestrator','compute_agent'],['orchestrator','validator_agent'],['requirements','supplement'],['supplement','confirmation'],['supplement','requirements','','return'],['compute_agent','model'],['validator_agent','publish'],['requirements','llm','','capability'],['compute_agent','llm','','capability'],['validator_agent','llm','','capability'],['requirements','rag','','capability'],['validator_agent','rag','','capability'],['rag','knowledge','','capability'],['state','orchestrator','','state']];
function svgEl(tag, attrs={},text){const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);if(text)n.textContent=text;return n;}
export function renderFlow(host,{view,state,events,selected,onSelect}){
 const arch=true, positions=architecture, edges=architectureEdges, states=nodeStates(state,events);
 const svg=svgEl('svg',{viewBox:`0 0 910 ${arch?830:590}`,role:'group','aria-label':arch?'总体协同架构':'任务执行流程'});
 const defs=svgEl('defs');const marker=svgEl('marker',{id:'arrow',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:5,markerHeight:5,orient:'auto-start-reverse'});marker.append(svgEl('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'context-stroke'}));defs.append(marker);svg.append(defs);
 if(!arch){['需求与规划','确认、计算与发布','分支与扩展'].forEach((t,i)=>svg.append(svgEl('text',{x:40+i*290,y:24,class:'lane-label'},t)));}
 const map=Object.fromEntries(positions.map(([id,x,y])=>[id,{x,y}]));
 for(const[from,to,label='',type='task']of edges){
  const a=map[from],b=map[to];if(!a||!b)continue;
  let x1=a.x+115,y1=a.y+68,x2=b.x+115,y2=b.y,d;
  if(type==='state'){d=`M ${a.x+230} ${a.y+34} H 895 V ${b.y+34} H ${b.x+230}`;}
  else if(arch&&type==='capability'&&from!=='rag'){
   const rail=from==='requirements'?20:890;
   const sx=from==='requirements'?a.x:a.x+230;
   d=`M ${sx} ${a.y+34} H ${rail} V ${b.y-15} H ${b.x+115} V ${b.y}`;
  }
  else if(arch&&from==='supplement'){d=`M ${a.x} ${a.y+34} H 8 V ${b.y+34} H ${b.x}`;}
  else if(type==='return'){d=`M ${a.x+230} ${a.y+34} H 882 V 42 H ${b.x+115} V ${b.y}`;}
  else if(a.x===b.x){if(a.y>b.y){y1=a.y;y2=b.y+68;}d=`M ${x1} ${y1} L ${x2} ${y2}`;}
  else if(a.y===b.y){x1=a.x+230;y1=a.y+34;x2=b.x;y2=b.y+34;d=`M ${x1} ${y1} H ${x2}`;}
  else {d=`M ${x1} ${y1} C ${x1} ${(y1+y2)/2}, ${x2} ${(y1+y2)/2}, ${x2} ${y2}`;}
  const phase=edgeState(state,events,from,to);
  const active=['running','completed','waiting','failed'].includes(phase);
  const path=svgEl('path',{d,class:`flow-edge ${type} ${active?'traversed':''} ${phase==='running'?'moving':''} ${phase==='failed'?'failed':''}`,'data-edge':`${from}:${to}`,'marker-end':'url(#arrow)'});svg.append(path);
  if(label&&type!=='return')svg.append(svgEl('text',{x:(x1+x2)/2,y:(y1+y2)/2-7,class:'edge-label'},label));
 }
 for(const[id,x,y]of positions){
  const [label,sub]=nodes[id],status=states[id];
  const g=svgEl('g',{transform:`translate(${x},${y})`,class:`flow-node ${status} ${selected===id?'selected':''}`,role:'button',tabindex:0,'aria-label':`${label}，${statusText[status]||status}`,'aria-pressed':String(selected===id),'data-node':id});
  const visibleSub=status==='running'?'运行中 · 等待真实返回':status==='waiting'?'等待补充或核对 · 点击查看':status==='degraded'?'部分调用已降级 · 点击查看':sub;
  g.append(svgEl('rect',{width:230,height:68,rx:10}),svgEl('circle',{cx:18,cy:22,r:4}),svgEl('text',{x:30,y:27,class:'node-title'},label),svgEl('text',{x:15,y:50,class:'node-sub'},visibleSub));
  const activate=()=>onSelect(id);g.addEventListener('click',activate);g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activate();}});svg.append(g);
 }
 host.replaceChildren(svg);
}
