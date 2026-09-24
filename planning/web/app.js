import {taskProgress,headline} from './progress.mjs';
import {serviceText} from './model-status.mjs';
import {nodes,renderFlow,relevantEvents,activityFresh,openRun} from './flow.mjs';
import {renderRight,nodeCard,el,labels,parameterNames,conditionNames,targetNames} from './details.mjs';
import {formatDomain} from './values.mjs';
import {renderConversation} from './conversation.mjs';
import {renderQuestions,openQuestions} from './questions.mjs';
import {summary,factorySettings,renderSettingsForm} from './settings.mjs';
import {nodeLatency,stepTimes,runSummary,renderWaterfall,miniWaterfall,renderMetrics} from './timing.mjs';
const $=id=>document.getElementById(id);
const narrow=()=>window.matchMedia('(max-width: 899px)').matches;
let current=null, historical=null, activeContext=null, activity=[], token='', dirty=false, editing=false, busy=false, busyAction=null, pendingCommand=null;
let modelService=null, checkingModel=false;
let settings=null, models=null, draft=null, savingSettings=false;
let view='main', focusParameter=null, pollGeneration=0, popover=null, sideChoice=null, sideKey='', foldKey='', originalOpen=false;
const folds=new Map();
// Event nodes that are not drawn map onto the architecture node that owns them.
const ARCH={parse:'requirements',planning:'requirements',interpretation:'llm',retrieval:'rag',calculation:'compute_agent',validation:'validator_agent',review:'validator_agent',supplement:'confirmation',gap:'requirements',failure:'orchestrator',explanation:'validator_agent'};
const DRAWN=new Set(['input','orchestrator','requirements','compute_agent','validator_agent','confirmation','model','publish','state','llm','rag','knowledge']);
async function checkModel(){
 if(checkingModel)return;checkingModel=true;$('check-model').disabled=true;
 $('model-service-status').textContent='正在检查本机 Qwen 服务…';
 try{modelService=await api('/api/model-status');}
 catch{modelService={status:'unknown',checked_at:new Date().toISOString()};}
 finally{checkingModel=false;$('check-model').disabled=busy||!!historical;
  $('model-service-status').textContent=serviceText(modelService);
  $('model-service-time').textContent=`最近检查：${new Date(modelService.checked_at).toLocaleTimeString('zh-CN',{hour12:false})}。服务就绪不代表每次调用都会通过校验。`;
  if(view==='model'||popover?.id==='llm')draw();
 }
}
function shown(){return historical||activeContext||current;}
let toastTimer;
function notice(text,error=false){
 if(error){$('notice').textContent=text;$('notice').hidden=!text;return;}
 clearTimeout(toastTimer);const toast=$('toast');toast.textContent=text;toast.hidden=!text;
 if(text)toastTimer=setTimeout(()=>{if(toast.textContent===text)toast.hidden=true;},4000);
}
const clearError=()=>notice('',true);
async function api(path,body){const r=await fetch(path,{signal:AbortSignal.timeout(path==='/api/commands'?125000:10000),method:body?'POST':'GET',headers:body?{'Content-Type':'application/json','X-Planning-Token':token}:{},body:body?JSON.stringify(body):undefined});const data=await r.json();if(!r.ok){const err=new Error(data.error.message+' ['+data.error.code+']');err.status=r.status;throw err;}return data;}
function syncButtons(){
 document.querySelectorAll('#request-form input,#request-form textarea,#request-form select,#request-form button').forEach(n=>n.disabled=busy||!!historical);
 for(const id of ['supplement-message','supplement-submit'])$(id).disabled=busy||!!historical||!current||dirty||editing;
 document.querySelectorAll('#clarification-panel input,#clarification-panel select,#clarification-panel button').forEach(n=>n.disabled=busy||dirty||editing||!!historical);
 const can=current?.status==='AWAITING_CONFIRMATION'&&!historical&&!activeContext;
 $('actions').hidden=!can;
 $('confirm').disabled=busy||dirty||editing||!can||!$('accept').checked;
 $('accept').disabled=busy||dirty||editing||!can;
 $('cancel').disabled=busy||!can;
 $('stop-operation').hidden=!busy;$('stop-operation').disabled=!busy;
 $('return-current').hidden=!historical;
 const unfinished=!!current&&!historical&&!['COMPLETED','CANCELLED'].includes(current.status);
 $('menu-cancel').hidden=!unfinished||current.status==='AWAITING_CONFIRMATION';$('menu-cancel').disabled=busy;
 for(const id of ['new','restore','refresh','history','refresh-tasks'])$(id).disabled=busy||(['history','refresh'].includes(id)&&!current);
 $('export').disabled=busy||!shown();
}
function readInput(){const p={};for(const[id,name]of [['frequency','frequency_ghz'],['distance','distance_km']])if($(id).value!==''){const value=Number($(id).value);if(!Number.isFinite(value))throw new Error('手工参数必须是有限数值。');p[name]={value,unit:$(id+'-unit').value};}return {raw_text:$('raw-text').value,manual_parameters:p,condition:$('condition').value||null,target:$('target').value||null};}
function fillInput(s){$('raw-text').value=s.request.raw_text;$('condition').value=s.request.condition||'';$('target').value=s.request.target||'';for(const[id,name]of [['frequency','frequency_ghz'],['distance','distance_km']]){const p=s.request.manual_parameters[name];$(id).value=p?p.value:'';if(p)$(id+'-unit').value=p.unit;}$('manual-details').open=Object.keys(s.request.manual_parameters).length>0||!!s.request.condition||!!s.request.target;}
function setView(next){view=next;popover=null;if(!matchMedia('(min-width: 1350px)').matches)sideChoice='plan';draw();$('detail-content').scrollTop=0;}
function chooseParameter(name){focusParameter=name;setView('parameters');}
// Fixed-height panels are overflow:hidden; scroll only the thread there so no panel shifts.
function reveal(node,align='top'){
 if(!node)return;
 if(narrow()){node.scrollIntoView({block:align==='top'?'start':'center'});return;}
 const thread=$('thread'),c=thread.getBoundingClientRect(),r=node.getBoundingClientRect();
 if(align==='top'||r.top<c.top||r.bottom>c.bottom)thread.scrollTop+=r.top-c.top-(align==='top'?8:Math.max(8,(c.height-r.height)/2));
}
function focusQuestion(field){
 sideChoice='chat';draw();
 const input=[...document.querySelectorAll('#clarification-panel [data-field]')].find(n=>n.dataset.field===field)||$('clarification-panel').querySelector('input,select');
 reveal(input,'center');input?.focus({preventScroll:true});
}
function startEdit(){if(!current||busy||historical)return;editing=true;fillInput(current);draw();$('raw-text').focus();}
function discardEdit(){editing=false;dirty=false;if(current)fillInput(current);draw();}
function renderOriginal(s){
 const card=$('original-card'),text=s.request?.raw_text||'',req=s.request||{};card.replaceChildren();
 const head=el('div',undefined,'card-head');head.append(el('span','需求原文','eyebrow'));
 if(current&&!historical&&!activeContext){const b=el('button','编辑原文','text-button');b.type='button';b.disabled=busy;b.addEventListener('click',startEdit);head.append(b);}
 const body=el('p',text,'original-text');card.append(head,body);
 if(text.split('\n').length>3||text.length>90){
  if(!originalOpen)body.classList.add('clamp');
  const more=el('button',originalOpen?'收起':'展开','text-button more-toggle');more.type='button';
  more.addEventListener('click',()=>{originalOpen=!originalOpen;body.classList.toggle('clamp',!originalOpen);more.textContent=originalOpen?'收起':'展开';});card.append(more);
 }
 const chips=Object.entries(req.manual_parameters||{}).map(([k,v])=>`手工 · ${parameterNames[k]||k} ${formatDomain(v.value)} ${v.unit}`);
 if(req.target)chips.push('目标 · '+(targetNames[req.target]||req.target));
 if(req.condition)chips.push('条件 · '+(conditionNames[req.condition]||req.condition));
 if(chips.length){const box=el('div',undefined,'chips');chips.forEach(c=>box.append(el('span',c,'chip')));card.append(box);}
}
function drawLeft(){
 const s=shown(),mode=editing?'edit':s?'task':'new';
 $('request-form').hidden=mode==='task';
 $('raw-label').textContent=mode==='edit'?'编辑原文':'需求';
 $('examples').hidden=mode!=='new';
 $('submit').textContent=mode==='edit'?'保存修改':'开始筹划';
 $('discard-edit').hidden=mode!=='edit';
 $('original-card').hidden=mode!=='task';
 $('supplement-form').hidden=mode!=='task';
 if(mode==='task')renderOriginal(s);
 renderConversation($('conversation-log'),mode==='task'?s:null,{open:folds});
 renderQuestions($('clarification-panel'),mode==='task'?s:null,{disabled:busy||dirty||editing||!!historical,onSubmit:answers=>submit('answer',answers).catch(e=>notice(e.message,true)),onEdit:startEdit});
 $('composer-hint').textContent=historical?'历史版本只读':'';
}
function drawFlow(){
 const s=shown(),ev=historical?[]:activity,relevant=relevantEvents(s,ev);
 renderFlow($('flow-canvas'),{state:s,events:ev,selected:popover?.id||null,onSelect:openNodeCard,latency:historical?{}:nodeLatency(relevant)});
 const steps=taskProgress(s,ev,{dirty,historical:!!historical}).steps,times=historical?[]:stepTimes(relevant);
 const words={completed:'已完成',running:'处理中',waiting:'待处理',failed:'已阻断',cancelled:'已停止',idle:'未开始'};
 $('task-progress').replaceChildren(...steps.map((step,i)=>{
  const row=el('li',undefined,step.status);row.title=`${step.label} · ${words[step.status]||''}`;
  row.append(el('span',({completed:'✓',running:'●',waiting:'◐',failed:'!',cancelled:'—',idle:'○'})[step.status]||'○','progress-symbol'),el('span',step.label));
  if(step.status==='completed'&&times[i])row.append(el('span',times[i],'progress-state'));
  if(['running','waiting'].includes(step.status))row.setAttribute('aria-current','step');return row;}));
 renderNodeCard();
}
function openNodeCard(id){popover=popover?.id===id?null:{id};drawFlow();}
function renderNodeCard(){
 const card=$('node-card');
 if(!popover){card.hidden=true;return;}
 const s=shown(),ev=historical?[]:activity,info=nodeCard(popover.id,{state:s,events:ev,latency:historical?{}:nodeLatency(relevantEvents(s,ev)),modelService});
 const head=el('div',undefined,'node-card-head'),close=el('button','✕','icon-button');close.type='button';close.setAttribute('aria-label','关闭');close.addEventListener('click',()=>{popover=null;drawFlow();});
 head.append(el('strong',info.title),close);
 card.replaceChildren(head,el('p',info.status,'node-card-status '+info.tone),...info.lines.map(line=>el('p',line)));
 if(info.link&&s?.report){const b=el('button',info.link.label+' →','text-button');b.type='button';b.addEventListener('click',()=>setView(info.link.view));card.append(b);}
 card.hidden=false;
 const g=$('flow-canvas').querySelector(`[data-node="${popover.id}"]`);if(!g)return;
 const r=g.getBoundingClientRect(),p=card.parentElement.getBoundingClientRect(),w=card.offsetWidth,h=card.offsetHeight;
 let left=r.left-p.left,top=r.bottom-p.top+6;
 if(left+w>p.width-8)left=p.width-w-8;if(top+h>p.height-8)top=r.top-p.top-h-6;
 card.style.left=Math.max(8,left)+'px';card.style.top=Math.max(8,top)+'px';
}
function modelLabel(){return settings?.settings?.mode_default==='llm'?summary(settings.settings,models).badge.split(' · ').slice(0,2).join(' · '):'确定性规则';}
function drawRight(){
 const s=shown(),relevant=relevantEvents(s,activity);
 const h=headline(s,{busy,action:busyAction,editing,historical:!!historical,modelLabel:modelLabel(),ran:historical?'':runSummary(relevant)});
 $('headline-text').textContent=h.text;$('headline-sub').textContent=h.sub||'';$('headline').className='headline '+h.tone;
 renderRight($('detail-content'),{state:s,view,focusParameter,historical:!!historical,activeContext:!!activeContext,modelService,settings:settings?.settings,models,open:folds,
  onView:setView,onParameter:chooseParameter,onMissing:focusQuestion,onReparse:()=>submit('edit').catch(e=>notice(e.message,true))});
 const n=openQuestions(s).length;
 $('pending-bar').hidden=!n||!!historical||busy||editing;$('pending-bar').textContent=`${h.text} · 去处理`;
}
function autoSide(){const s=shown();return !s||editing||['AWAITING_INPUT','NEEDS_MODEL'].includes(s.status)?'chat':'plan';}
function drawSide(){
 const s=shown(),key=[s?.task_id,s?.revision,s?.status,editing].join('|');
 if(key!==sideKey){sideKey=key;sideChoice=null;}
 const side=sideChoice||autoSide();$('workspace').dataset.side=side;
 for(const b of $('side-switch').querySelectorAll('button'))b.setAttribute('aria-pressed',String(b.dataset.side===side));
}
function drawTimeline(){
 const s=shown();$('trace').replaceChildren();const ev=historical?[]:relevantEvents(s,activity);
 $('event-count').textContent=`${ev.length||s?.trace?.length||0} 条记录`;
 if(ev.length){const start=new Map();for(const e of ev){const row=el('div',undefined,'trace-row');const time=new Date(e.at);row.append(el('span',Number.isNaN(time.getTime())?'时间未知':time.toLocaleTimeString('zh-CN',{hour12:false})));
  const b=el('button',nodes[e.node]?.[0]||(e.node==='command'?'命令与保存':e.node));b.addEventListener('click',()=>{const id=ARCH[e.node]||e.node;openNodeCard(DRAWN.has(id)?id:'state');});row.append(b);
  const key=e.run_id+':'+e.node;if(e.phase==='started')start.set(key,time.getTime());
  const duration=e.phase!=='started'&&start.has(key)?` · ${((time.getTime()-start.get(key))/1000).toFixed(3)} s`:'';
  const phase={started:'开始',completed:'完成',waiting:'等待用户处理',skipped:'未调用／降级',failed:'失败',cancelled:'已取消',committed:'已提交保存',rejected:'未提交／操作失败',replayed:'返回已有回执',interrupted:'观察中断，核对保存状态'}[e.phase]||e.phase;
  row.append(el('span',phase+duration+(e.details?.status?' · '+(labels[e.details.status]||e.details.status):'')+(e.details?.mode?' · '+e.details.mode:'')));$('trace').append(row);
 }}else for(const t of s?.trace||[]){const row=el('div',`${t.node} → ${t.status} · ${t.finished_at||t.at||''}`,'hint');$('trace').append(row);}
 $('raw-state').textContent=s?JSON.stringify(s,null,2):'尚无任务';
 renderWaterfall($('waterfall'),ev,el);miniWaterfall($('mini-waterfall'),ev,el);
}
function draw(){
 // Each status is a new reading: steps open while checking, closed once computed.
 const s=shown(),key=s?`${s.task_id}:${s.revision}:${s.status}:${historical?'h':''}`:'';
 if(key!==foldKey){foldKey=key;folds.clear();originalOpen=false;}
 const text=activeContext?'正在处理':s?.request?.raw_text?.trim()||'未开始';$('task-meta').textContent=text;$('task-meta').title=text;
 drawSide();drawLeft();drawFlow();drawRight();drawTimeline();syncButtons();
}
function acceptState(s){$('history-list').replaceChildren();if(current?.task_id!==s.task_id)activity=[];current=s;historical=null;activeContext=null;dirty=false;editing=false;$('accept').checked=false;fillInput(s);$('task-id').value=s.task_id;localStorage.setItem('planning-task',s.task_id);history.replaceState(null,'','#'+s.task_id);}
async function loadActivity(id,generation){try{const data=await api('/api/tasks/'+encodeURIComponent(id)+'/activity');if(generation!==pollGeneration||shown()?.task_id!==id)return;if(!activityFresh(activity,data.events))return;activity=data.events;draw();}catch{}}
async function poll(id,generation){await loadActivity(id,generation);if(busy&&generation===pollGeneration)setTimeout(()=>poll(id,generation),500);}
function afterCommand(action){
 $('detail-content').scrollTop=0;
 const questions=$('clarification-panel'),thread=$('thread');
 if(narrow()){
  if(!current)return;
  if(!questions.hidden)questions.scrollIntoView({block:'start'});
  else if(['AWAITING_CONFIRMATION','COMPLETED'].includes(current.status))document.querySelector('.detail-panel').scrollIntoView({block:'start'});
  return;
 }
 if(!questions.hidden)reveal(questions);
 else thread.scrollTop=['supplement','answer'].includes(action)?thread.scrollHeight:0;
}
async function submit(action,answers=null){
 if(busy||historical)return;
 const c={action,task_id:current?.task_id||(pendingCommand?.action==='create'?pendingCommand.task_id:crypto.randomUUID()),event_id:crypto.randomUUID(),expected_revision:current?.revision||0,expected_state_version:current?.state_version||0};
 if(['create','edit'].includes(action)){c.input=readInput();c.mode=$('mode').value;}if(action==='supplement'){c.message=$('supplement-message').value.trim();c.mode=$('mode').value;if(!c.message||dirty||editing)return;}if(action==='confirm')c.review_hash=current.review.review_hash;
 if(action==='answer'){if(dirty||editing||!answers)return;c.answers=answers;c.mode=$('mode').value;}
 if(pendingCommand){const comparable=x=>JSON.stringify({...x,event_id:''});if(comparable(pendingCommand)===comparable(c))c.event_id=pendingCommand.event_id;}
 clearError();pendingCommand=c;busy=true;busyAction=action;historical=null;popover=null;view='main';const generation=++pollGeneration;
 activeContext=['create','edit','supplement','answer'].includes(action)?{task_id:c.task_id,revision:c.expected_revision+(action==='create'?0:1),state_version:0,status:'RUNNING',request:c.input||current.request,conversation:current?.conversation,report:null,trace:[]}:null;
 localStorage.setItem('planning-task',c.task_id);history.replaceState(null,'','#'+c.task_id);$('task-id').value=c.task_id;
 draw();
 // Poll in parallel with the synchronous command. No artificial node progression.
 const request=api('/api/commands',c);poll(c.task_id,generation);
 try{const data=await request;pendingCommand=null;acceptState(data.state);if(action==='supplement')$('supplement-message').value='';
  notice(data.replayed?'已恢复已有回执':data.state.status==='COMPLETED'?'计算完成，结果已保存':action==='cancel'?'任务已取消':'已保存');}
 catch(e){if(e.status&&e.status<500)pendingCommand=null;activeContext=null;notice(e.message,true);}
 finally{checkModel();recentTasks();busy=false;busyAction=null;const finalGeneration=++pollGeneration;await loadActivity(c.task_id,finalGeneration);draw();afterCommand(action);}
}
async function restore(id){
 if(busy||!id)return;
 clearError();busy=true;busyAction='restore';popover=null;view='main';draw();const generation=++pollGeneration;
 try{
  let saved=null;
  try{saved=(await api('/api/tasks/'+encodeURIComponent(id))).state;}catch(e){if(e.status!==404)throw e;}
  const observed=await api('/api/tasks/'+encodeURIComponent(id)+'/activity');
  if(generation!==pollGeneration)return;
  if(saved)acceptState(saved);else{current=null;historical=null;$('history-list').replaceChildren();}
  activity=observed.events;
  let running=openRun(activity);
  if(!saved&&!running)throw new Error('未找到已保存任务；该次操作可能未提交。');
  if(running){
   const restoreDeadline=Date.now()+125000;
   if(!saved||running.revision!==saved.revision)activeContext={task_id:id,revision:running.revision,state_version:0,status:'RUNNING',request:{raw_text:'正在恢复运行观察，原文以提交后的记录为准。',manual_parameters:{}},report:null,trace:[]};
   notice('检测到仍在执行的操作，正在恢复观察');draw();
   while(running&&generation===pollGeneration){
    if(Date.now()>restoreDeadline)throw new Error('运行观察超过两分钟，请刷新保存状态；该提示不表示后端已停止。');
    await new Promise(resolve=>setTimeout(resolve,500));
    const fresh=await api('/api/tasks/'+encodeURIComponent(id)+'/activity');
    if(generation!==pollGeneration)return;
    if(activityFresh(activity,fresh.events))activity=fresh.events;
    running=openRun(activity);draw();
   }
   const result=await api('/api/tasks/'+encodeURIComponent(id));acceptState(result.state);
  }
  pendingCommand=null;activeContext=null;notice('已恢复任务');
 }catch(e){activeContext=null;notice(e.message,true);}finally{busy=false;busyAction=null;draw();afterCommand('restore');}
}
async function recentTasks(){
 try{
  const data=await api('/api/tasks'),list=$('recent-list');list.replaceChildren();
  if(!data.tasks.length)list.append(el('p','暂无保存的任务','hint'));
  for(const task of data.tasks){
   const row=el('button',undefined,'recent-row'+(task.task_id===current?.task_id?' current':''));row.type='button';
   row.append(el('span',labels[task.status]||task.status,'chip '+({COMPLETED:'ok',AWAITING_CONFIRMATION:'run',AWAITING_INPUT:'warn',NEEDS_MODEL:'warn'}[task.status]||'')),el('span',task.description||'未填写描述','recent-text'),el('small',task.task_id.slice(0,8)));
   row.addEventListener('click',()=>{closeSheets();restore(task.task_id);});list.append(row);
  }
 }catch(e){notice('任务列表加载失败：'+e.message,true);}
}
$('refresh-tasks').addEventListener('click',recentTasks);
$('stop-operation').addEventListener('click',async()=>{
 const run=pendingCommand||openRun(activity);
 if(!run){notice('尚未取得本次操作编号，请稍后重试。');return;}
 $('stop-operation').disabled=true;
 try{const response=await api('/api/cancel-operation',{task_id:run.task_id,event_id:run.event_id});notice(response.message);}catch(e){notice(e.message,true);}finally{$('stop-operation').disabled=!busy;}
});
$('check-model').addEventListener('click',checkModel);

function showSummary(){
 const text=summary(settings?.settings,models);$('model-badge-text').textContent=text.badge;
 const st=models?.status?.[settings?.settings?.chat?.default];
 $('model-dot').className='dot '+(settings?.settings?.mode_default!=='llm'?'':st==='ready'?'ok':st==='loading'?'run':'off');
 if(settings)$('mode').value=settings.settings.mode_default;
}
async function loadSettings(){
 try{[settings,models]=await Promise.all([api('/api/settings'),api('/api/models')]);}catch(e){notice('模型与检索设置载入失败：'+e.message,true);}
 showSummary();
}
function drawSettings(){renderSettingsForm($('settings-form'),{draft,models,status:models?.status,corpus:models?.corpus,el,onChange:next=>{draft=next;drawSettings();}});}
let sheetReturn=null;
const SHEETS=['settings-sheet','metrics-panel','history-sheet'];
function openSheet(id){toggleMenu(false);sheetReturn=document.activeElement;$('sheet-scrim').hidden=false;$(id).hidden=false;$(id).querySelector('.icon-button').focus();}
function closeSheets(){for(const id of SHEETS)$(id).hidden=true;$('sheet-scrim').hidden=true;sheetReturn?.focus?.();}
async function openSettings(){
 await loadSettings();if(!settings||!models)return;
 draft=structuredClone(settings.settings);drawSettings();openSheet('settings-sheet');checkModel();
}
async function saveSettings(){
 if(savingSettings||!draft)return;savingSettings=true;$('save-settings').disabled=true;
 try{settings=await api('/api/settings',{settings:draft,expected_version:settings.version});showSummary();closeSheets();notice('已保存为默认设置，下一次操作生效');draw();
  // Health probes can take seconds when a port is closed; refresh them without blocking the save.
  api('/api/models').then(m=>{models=m;showSummary();}).catch(()=>{});}
 catch(e){if(e.status===409){await loadSettings();draft=structuredClone(settings.settings);drawSettings();}notice(e.message,true);}
 finally{savingSettings=false;$('save-settings').disabled=false;}
}
async function openMetrics(){
 openSheet('metrics-panel');$('metrics-body').replaceChildren(el('p','正在汇总运行记录…','hint'));
 try{renderMetrics($('metrics-body'),await api('/api/metrics'),el);}catch(e){$('metrics-body').replaceChildren(el('p','汇总失败：'+e.message,'hint'));}
}
function openHistory(focusId=false){openSheet('history-sheet');recentTasks();if(focusId)$('task-id').focus();}
function toggleMenu(open){const menu=$('more-menu'),show=open??menu.hidden;menu.hidden=!show;$('more').setAttribute('aria-expanded',String(show));if(show)menu.querySelector('button:not([hidden]):not(:disabled)')?.focus();}
$('model-badge').addEventListener('click',openSettings);
$('close-settings').addEventListener('click',closeSheets);$('close-metrics').addEventListener('click',closeSheets);$('close-history').addEventListener('click',closeSheets);$('sheet-scrim').addEventListener('click',closeSheets);
$('save-settings').addEventListener('click',saveSettings);
$('reset-settings').addEventListener('click',()=>{if(!models)return;draft=factorySettings(models);drawSettings();});
$('open-history').addEventListener('click',()=>openHistory());
$('more').addEventListener('click',e=>{e.stopPropagation();toggleMenu();});
$('open-metrics').addEventListener('click',openMetrics);
$('open-recovery').addEventListener('click',()=>openHistory(true));
$('menu-cancel').addEventListener('click',()=>{toggleMenu(false);submit('cancel').catch(e=>notice(e.message,true));});
document.addEventListener('click',e=>{
 if(!$('more-menu').hidden&&!e.target.closest('.menu-wrap'))toggleMenu(false);
 if(popover&&!e.target.closest('#node-card')&&!e.target.closest('.flow-node')){popover=null;drawFlow();}
});
$('request-form').addEventListener('submit',e=>{e.preventDefault();submit(current?'edit':'create').catch(e=>notice(e.message,true));});
$('request-form').addEventListener('input',()=>{if(editing&&!dirty){dirty=true;$('accept').checked=false;draw();}});
$('discard-edit').addEventListener('click',discardEdit);
$('accept').addEventListener('change',syncButtons);$('confirm').addEventListener('click',()=>submit('confirm').catch(e=>notice(e.message,true)));$('cancel').addEventListener('click',()=>submit('cancel').catch(e=>notice(e.message,true)));
$('refresh').addEventListener('click',()=>{closeSheets();restore(current?.task_id);});$('restore').addEventListener('click',()=>{const id=$('task-id').value.trim();closeSheets();restore(id);});
function populateExample(text,conflict=false){
 $('raw-text').value=text;
 for(const id of ['frequency','distance','condition','target'])$(id).value='';
 $('frequency-unit').value='GHz';$('distance-unit').value='km';
 if(conflict)$('frequency').value='3';
 $('manual-details').open=conflict;
 notice(conflict?'已填入：原文 2 GHz 与手工 3 GHz 冲突':'示例已填入');
}
$('example').addEventListener('click',()=>populateExample('按自由空间基准计算，频率2GHz，距离1km，求路径损耗。'));
$('budget-example').addEventListener('click',()=>populateExample('按自由空间基准计算链路余量：频率2GHz，距离10km，发射功率30dBm，发射天线增益10dBi，接收天线增益10dBi，发射馈线损耗2dB，接收馈线损耗2dB，额外损耗0dB，接收灵敏度-100dBm，预留余量10dB。'));
$('vague-example').addEventListener('click',()=>populateExample('我想让两艘船之间通信稳定一些，帮我规划一下。'));
$('range-example').addEventListener('click',()=>populateExample('按自由空间基准计算，频率2±0.1GHz，距离1km，求路径损耗。'));
$('missing-example').addEventListener('click',()=>populateExample('按自由空间基准计算，频率2GHz，求路径损耗。'));
$('choices-example').addEventListener('click',()=>populateExample('按自由空间基准计算，频率2GHz或3GHz，距离1km，求路径损耗。'));
$('conflict-example').addEventListener('click',()=>populateExample('按自由空间基准计算，频率2GHz，距离1km，求路径损耗。',true));
$('new').addEventListener('click',()=>{current=historical=activeContext=null;activity=[];dirty=false;editing=false;pendingCommand=null;pollGeneration++;view='main';popover=null;focusParameter=null;clearError();localStorage.removeItem('planning-task');history.replaceState(null,'',location.pathname);$('request-form').reset();$('supplement-form').reset();$('task-id').value='';$('history-list').replaceChildren();notice('新任务已就绪，原任务仍在历史中');draw();$('raw-text').focus();});
$('supplement-form').addEventListener('submit',e=>{e.preventDefault();submit('supplement').catch(e=>notice(e.message,true));});
$('expand-detail').addEventListener('click',()=>{const expanded=$('workspace').classList.toggle('detail-wide');$('expand-detail').textContent=expanded?'收起':'展开';});
$('side-switch').addEventListener('click',e=>{const b=e.target.closest('[data-side]');if(!b)return;sideChoice=b.dataset.side;drawSide();});
$('pending-bar').addEventListener('click',()=>{const first=openQuestions(shown())[0];if(first)focusQuestion(first.field);});
const canvasPanel=document.querySelector('.canvas-panel');
function setFlowExpanded(expanded){canvasPanel.classList.toggle('flow-expanded',expanded);$('expand-flow').textContent=expanded?'恢复工作台':'放大流程图';$('expand-flow').setAttribute('aria-expanded',String(expanded));popover=null;drawFlow();}
$('expand-flow').addEventListener('click',()=>setFlowExpanded(!canvasPanel.classList.contains('flow-expanded')));
document.addEventListener('keydown',e=>{
 if(e.key!=='Escape')return;
 if(!$('more-menu').hidden){toggleMenu(false);$('more').focus();return;}
 if(popover){popover=null;drawFlow();return;}
 if(!$('sheet-scrim').hidden){closeSheets();return;}
 if(canvasPanel.classList.contains('flow-expanded')){setFlowExpanded(false);$('expand-flow').focus();}
});
$('return-current').addEventListener('click',()=>{historical=null;view='main';if(current)fillInput(current);draw();});
$('history').addEventListener('click',async()=>{
 if(!current||busy)return;
 const taskId=current.task_id,generation=pollGeneration;
 try{
  const data=await api('/api/tasks/'+taskId+'/history');
  if(generation!==pollGeneration||current?.task_id!==taskId)return;
  $('history-list').replaceChildren();
  for(const item of data.history){
   const row=el('div',undefined,'history-entry');row.append(el('span',`第 ${item.revision} 版 · 保存 ${item.state_version} · ${labels[item.state.status]||item.state.status}`));const b=el('button','只读查看','secondary');
   b.addEventListener('click',()=>{if(busy||generation!==pollGeneration||current?.task_id!==taskId)return;historical=item.state;fillInput(historical);$('accept').checked=false;editing=false;view='main';popover=null;draw();});row.append(b);$('history-list').append(row);
  }
 }catch(e){if(generation===pollGeneration)notice(e.message,true);}
});
$('export').addEventListener('click',()=>{toggleMenu(false);const s=shown();if(!s||busy)return;const blob=new Blob([JSON.stringify(s,null,2)],{type:'application/json;charset=utf-8'});const url=URL.createObjectURL(blob);const a=el('a');a.href=url;a.download=`planning-${s.task_id}-r${s.revision}-v${s.state_version}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
draw();
checkModel();
(async()=>{try{token=(await api('/api/session')).token;await loadSettings();draw();await recentTasks();const id=location.hash.slice(1)||localStorage.getItem('planning-task');if(id)await restore(id);}catch(e){notice('无法连接本地服务：'+e.message,true);}})();
