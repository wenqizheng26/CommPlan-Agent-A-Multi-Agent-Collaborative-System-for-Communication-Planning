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

// Page 1 of the two-page Visio: one orchestrator, three peer agents with their
// artifacts, shared state below and shared capabilities on the right.
// Roles and artifacts are plain cards; shared capabilities form one tinted family.
const architecture=[
 ['input',215,6,190,38,'input'],
 ['orchestrator',160,80,300,56,'role'],
 ['requirements',12,176,188,62,'role'],
 ['compute_agent',216,176,188,62,'role'],
 ['validator_agent',420,176,188,62,'role'],
 ['confirmation',12,300,188,58,'role'],
 ['model',216,300,188,58,'cap'],
 ['publish',420,300,188,58,'role'],
 ['state',12,396,596,58,'role'],
 ['llm',640,80,184,64,'cap'],
 ['rag',640,300,184,58,'cap'],
 ['knowledge',640,392,184,62,'cap'],
];
// [from,to,type,path,label,labelX,labelY,both]; from/to follow activity caller/node aliases.
const architectureEdges=[
 ['input','orchestrator','task','M310 44V80'],
 ['orchestrator','requirements','task','M250 136V150H106V176','',0,0,true],
 ['orchestrator','compute_agent','task','M310 136V176','',0,0,true],
 ['orchestrator','validator_agent','task','M370 136V150H514V176','',0,0,true],
 ['requirements','confirmation','task','M106 238V300','用户核对',114,285,true],
 ['confirmation','compute_agent','gate','M200 350H208V226H216'],
 ['validator_agent','publish','task','M514 238V300'],
 ['compute_agent','model','capability','M310 238V300','参数 / 损耗',318,285,true],
 ['requirements','llm','capability','M176 176V164H612V112H640'],
 ['validator_agent','llm','capability','M590 176V164H612V112H640'],
 ['compute_agent','llm','optional','M380 176V164H612V112H640','工具建议 · 可选',520,159],
 ['orchestrator','llm','unavailable','M460 100H640','未接入',530,94],
 ['requirements','rag','capability','M176 238V262H616V329H640'],
 ['validator_agent','rag','capability','M590 238V262H616V329H640'],
 ['rag','knowledge','capability','M732 358V392','',0,0,true],
 ['state','orchestrator','state','M12 425H6V108H160','',0,0,true],
];
// Static descriptions live in the detail panel; the diagram keeps only integration caveats.
const nodeText={validator_agent:'解释未接入',rag:'词项检索'};
const integration={orchestrator:'部分接入',llm:'可选'};
const titles={input:'用户输入通信需求'};
function box(x,y,w,h,r){return `M${x+r} ${y}H${x+w-r}Q${x+w} ${y} ${x+w} ${y+r}V${y+h-r}Q${x+w} ${y+h} ${x+w-r} ${y+h}H${x+r}Q${x} ${y+h} ${x} ${y+h-r}V${y+r}Q${x} ${y} ${x+r} ${y}Z`;}
function svgEl(tag, attrs={},text){const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);if(text)n.textContent=text;return n;}
function marker(id){const m=svgEl('marker',{id,viewBox:'0 0 10 10',refX:9,refY:5,markerWidth:5,markerHeight:5,orient:'auto-start-reverse'});m.append(svgEl('path',{d:'M 0 0 L 10 5 L 0 10 z',fill:'context-stroke'}));return m;}
function chip(text,x,y,w){return [svgEl('path',{d:box(x,y,w,18,9),class:'integration-chip'}),svgEl('text',{x:x+w/2,y:y+13,'text-anchor':'middle',class:'integration-text'},text)];}
export function renderFlow(host,{view,state,events,selected,onSelect}){
 const states=nodeStates(state,events);
 // Page 1 has no separate follow-up node: the user check loop carries it.
 const awaitingSupplement=states.supplement==='waiting'&&states.confirmation!=='waiting';
 if(awaitingSupplement)states.confirmation='waiting';
 const svg=svgEl('svg',{viewBox:'0 0 840 494',role:'group','aria-label':'总体协同架构'});
 const defs=svgEl('defs');defs.append(marker('arrow'));svg.append(defs);
 svg.append(svgEl('path',{d:box(4,56,616,410,16),class:'flow-lane'}),svgEl('text',{x:14,y:72,class:'lane-label'},'LangGraph 编排与状态'));
 svg.append(svgEl('path',{d:box(628,56,208,410,16),class:'flow-lane'}),svgEl('text',{x:638,y:72,class:'lane-label'},'共享能力'));
 for(const[from,to,type,d,label,lx,ly,both]of architectureEdges){
  const phase=edgeState(state,events,from,to);
  const active=['running','completed','waiting','failed'].includes(phase);
  const attrs={d,class:`flow-edge ${type} ${active?'traversed':''} ${phase==='running'?'moving':''} ${phase==='failed'?'failed':''}`,'data-edge':`${from}:${to}`,'data-relation':RELATION_SEMANTICS,'aria-label':RELATION_DESCRIPTION,'marker-end':'url(#arrow)'};
  if(both)attrs['marker-start']='url(#arrow)';
  svg.append(svgEl('path',attrs));
  if(label)svg.append(svgEl('text',{x:lx,y:ly,class:`edge-label ${type}`},label));
 }
 // Visio's knowledge-enhancement step; only lexical formula-card retrieval is wired today.
 const note=svgEl('g',{class:'flow-note'});
 note.append(svgEl('text',{x:732,y:212,'text-anchor':'middle',class:'note-title'},'知识增强过程'),...chip('部分接入 · 仅公式卡',662,224,140));
 svg.append(note);
 for(const[id,x,y,w,h,kind]of architecture){
  const status=states[id],label=titles[id]||nodes[id][0];
  const g=svgEl('g',{transform:`translate(${x},${y})`,class:`flow-node kind-${kind} ${status} ${selected===id?'selected':''}`,role:'button',tabindex:0,'aria-label':`${label}，${statusText[status]||status}`,'aria-pressed':String(selected===id),'data-node':id});
  g.append(svgEl('path',{d:box(0,0,w,h,id==='input'?h/2:12),class:'shape'}));
  const sub=status==='running'?'运行中 · 等待返回':status==='waiting'?(awaitingSupplement&&id==='confirmation'?'等待补充 · 见右侧问题':'等待用户处理'):status==='degraded'?'部分调用已降级':nodeText[id]||'';
  if(id==='input')g.append(svgEl('text',{x:w/2,y:h/2+5,'text-anchor':'middle',class:'node-title'},label));
  else{
   const titleY=sub?h/2-3:h/2+5;
   g.append(svgEl('circle',{cx:18,cy:titleY-5,r:4}),svgEl('text',{x:30,y:titleY,class:'node-title'},label));
   if(sub)g.append(svgEl('text',{x:30,y:titleY+19,class:'node-sub'},sub));
  }
  if(integration[id]){const cw=integration[id].length*11+14;g.append(...chip(integration[id],w-cw-8,8,cw));}
  const activate=()=>onSelect(id);g.addEventListener('click',activate);g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();activate();}});svg.append(g);
 }
 svg.append(svgEl('text',{x:10,y:486,class:'flow-footnote'},'三个专业 Agent 平级；确认后计算。连线按运行活动高亮，不表示直接调用链。'));
 host.replaceChildren(svg);
}
