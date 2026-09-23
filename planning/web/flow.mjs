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
export function openRun(events){const last=events.at(-1);if(!last)return null;const run=events.filter(e=>e.run_id===last.run_id);return run.some(e=>e.node==='command'&&['committed','replayed','rejected','cancelled','interrupted'].includes(e.phase))?null:last;}
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
  const terminal=run.findLast(e=>e.node==='command'&&['rejected','cancelled','interrupted','committed','replayed'].includes(e.phase));
  if(['rejected','cancelled','interrupted'].includes(terminal?.phase)){
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
// Observed responsibility/activity relations are not literal graph predecessors.
// Architecture relations alone never animate an edge.
export const RELATION_SEMANTICS='observed_activity';
export const RELATION_DESCRIPTION='连线表示观测到的运行活动与责任关系，不表示 LangGraph 的直接调用链。';
export function edgeState(state,events,from,to){
 const relevant=relevantEvents(state,events), runs=new Map();
 for(const e of relevant)if(e.node==='command')runs.set(e.run_id,e.phase);
 const calls=relevant.filter(e=>{
  const terminal=runs.get(e.run_id);
  if(['rejected','cancelled','interrupted','replayed'].includes(terminal))return false;
  if(state.status==='COMPLETED'&&terminal!=='committed')return false;
  const a=aliases[e.details?.caller]||e.details?.caller,b=aliases[e.node]||e.node;
  return (a===from&&b===to)||(from==='state'&&to==='orchestrator'&&a==='orchestrator'&&b==='state');
 });
 const phase=calls.at(-1)?.phase;
 return phase==='started'?'running':phase||'idle';
}

// One compact, readable architecture view. The solid spine is the guarded task
// order; the other relations show responsibility and optional support.
const architecture=[
 ['input',230,5],['orchestrator',230,85],
 ['rag',10,165],['requirements',230,165],['llm',450,165],
 ['knowledge',10,245],['confirmation',230,245],['supplement',450,245],
 ['state',10,325],['compute_agent',230,325],['model',450,325],
 ['validator_agent',230,405],['publish',450,405],
];
const architectureEdges=[
 ['input','orchestrator'],['orchestrator','requirements'],
 ['requirements','confirmation'],['confirmation','compute_agent'],
 ['compute_agent','validator_agent'],['validator_agent','publish'],
 ['orchestrator','compute_agent','','ownership'],['orchestrator','validator_agent','','ownership'],
 ['requirements','supplement','','branch'],['supplement','requirements','','return'],
 ['requirements','rag','','capability'],['rag','knowledge','','capability'],
 ['requirements','llm','','capability'],['compute_agent','llm','','capability'],
 ['validator_agent','llm','','capability'],['validator_agent','rag','','capability'],
 ['compute_agent','model','','capability'],['state','orchestrator','','state'],
];
const nodeWidth=190,nodeHeight=58;
const flowSubtitles={
 input:'原文与补充条件',orchestrator:'受控调度 · 重算有上限',
 requirements:'规则解析 · 参数与计划',rag:'当前为词项检索',llm:'可选 · 可明确降级',
 knowledge:'公式卡与来源',confirmation:'核对参数与假设',supplement:'缺项／冲突补充',
 state:'快照、历史与恢复',compute_agent:'受控调用登记公式',model:'确定性 FSPL',
 validator_agent:'硬校验 · 可选审查',publish:'结果、限制与依据',
};
function edgePath(from,to,map){
 const a=map[from],b=map[to],center=p=>p.x+nodeWidth/2,middle=p=>p.y+nodeHeight/2;
 const key=`${from}:${to}`;
 if(key==='state:orchestrator')return `M ${a.x} ${middle(a)} H 4 V ${middle(b)} H ${b.x}`;
 if(key==='orchestrator:compute_agent')return `M ${a.x+nodeWidth} ${middle(a)} H 435 V ${middle(b)} H ${b.x+nodeWidth}`;
 if(key==='orchestrator:validator_agent')return `M ${a.x} ${middle(a)} H 215 V ${middle(b)} H ${b.x}`;
 if(key==='requirements:supplement')return `M ${a.x+nodeWidth} ${middle(a)+13} H 440 V ${middle(b)} H ${b.x}`;
 if(key==='supplement:requirements')return `M ${a.x+nodeWidth} ${middle(a)} H 646 V 154 H ${b.x+nodeWidth+12} V ${middle(b)} H ${b.x+nodeWidth}`;
 if(key==='compute_agent:llm')return `M ${a.x+nodeWidth} ${middle(a)-9} H 441 V ${middle(b)+9} H ${b.x}`;
 if(key==='validator_agent:llm')return `M ${a.x+nodeWidth} ${middle(a)} H 445 V ${middle(b)-9} H ${b.x}`;
 if(key==='validator_agent:rag')return `M ${a.x} ${middle(a)+9} H 205 V 154 H ${b.x+nodeWidth+10} V ${middle(b)+9} H ${b.x+nodeWidth}`;
 if(a.x===b.x)return a.y<b.y?`M ${center(a)} ${a.y+nodeHeight} V ${b.y}`:`M ${center(a)} ${a.y} V ${b.y+nodeHeight}`;
 if(a.y===b.y)return a.x<b.x?`M ${a.x+nodeWidth} ${middle(a)} H ${b.x}`:`M ${a.x} ${middle(a)} H ${b.x+nodeWidth}`;
 return `M ${center(a)} ${a.y+nodeHeight} V ${b.y-8} H ${center(b)} V ${b.y}`;
}
function svgEl(tag, attrs={},text){const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);if(text)n.textContent=text;return n;}
export function renderFlow(host,{view,state,events,selected,onSelect}){
 const positions=architecture, edges=architectureEdges, states=nodeStates(state,events);
 const svg=svgEl('svg',{viewBox:'0 0 650 470',role:'group','aria-label':'总体协同架构'});
 const defs=svgEl('defs');const marker=svgEl('marker',{id:'arrow',viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:5,markerHeight:5,orient:'auto-start-reverse'});marker.append(svgEl('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'context-stroke'}));defs.append(marker);svg.append(defs);
 const map=Object.fromEntries(positions.map(([id,x,y])=>[id,{x,y}]));
 for(const[from,to,label='',type='task']of edges){
  const a=map[from],b=map[to];if(!a||!b)continue;
  const d=edgePath(from,to,map);
  const phase=edgeState(state,events,from,to);
  const active=['running','completed','waiting','failed'].includes(phase);
  const path=svgEl('path',{d,class:`flow-edge ${type} ${active?'traversed':''} ${phase==='running'?'moving':''} ${phase==='failed'?'failed':''}`,'data-edge':`${from}:${to}`,'data-relation':RELATION_SEMANTICS,'aria-label':RELATION_DESCRIPTION,'marker-end':'url(#arrow)'});svg.append(path);
  if(label&&type!=='return')svg.append(svgEl('text',{x:(a.x+b.x+nodeWidth)/2,y:(a.y+b.y+nodeHeight)/2-7,class:'edge-label'},label));
 }
 for(const[id,x,y]of positions){
  const [label,sub]=nodes[id],status=states[id];
  const g=svgEl('g',{transform:`translate(${x},${y})`,class:`flow-node ${status} ${selected===id?'selected':''}`,role:'button',tabindex:0,'aria-label':`${label}，${statusText[status]||status}`,'aria-pressed':String(selected===id),'data-node':id});
  const visibleSub=status==='running'?'运行中 · 等待返回':status==='waiting'?'等待用户处理':status==='degraded'?'部分调用已降级':flowSubtitles[id]||sub;
  g.append(svgEl('rect',{width:nodeWidth,height:nodeHeight,rx:6}),svgEl('circle',{cx:16,cy:20,r:3.5}),svgEl('text',{x:27,y:24,class:'node-title'},label),svgEl('text',{x:14,y:44,class:'node-sub'},visibleSub));
  const activate=()=>onSelect(id);g.addEventListener('click',activate);g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activate();}});svg.append(g);
 }
 host.replaceChildren(svg);
}
