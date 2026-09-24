import {taskProgress} from './progress.mjs';
import {serviceText} from './model-status.mjs';
import {nodes,statusText,nodeStates,renderFlow,relevantEvents,activityFresh,openRun} from './flow.mjs';
import {renderDetails,el,labels,tabNames} from './details.mjs';
import {renderConversation} from './conversation.mjs';
import {reviewQuestion} from './roles.mjs';
import {renderQuestions} from './questions.mjs';
import {summary,factorySettings,renderSettingsForm} from './settings.mjs';
import {nodeLatency,stepTimes,runSummary,renderWaterfall,miniWaterfall,renderMetrics} from './timing.mjs';
const $=id=>document.getElementById(id);
const scrollOnSmallScreen=(id,block='start')=>{if(window.matchMedia('(max-width: 899px)').matches)$(id).scrollIntoView({block});};
const resetCockpitPanes=()=>{if(window.matchMedia('(min-width: 900px)').matches)for(const selector of ['.input-panel','.detail-panel'])document.querySelector(selector).scrollTop=0;};
let current=null, historical=null, activeContext=null, activity=[], token='', dirty=false, busy=false, pendingCommand=null;
let modelService=null, checkingModel=false;
let settings=null, models=null, draft=null, savingSettings=false;
let view='architecture', selected='input', tab='overview', focusParameter=null, pollGeneration=0;
async function checkModel(){
 if(checkingModel)return;checkingModel=true;$('check-model').disabled=true;
 $('model-service-status').textContent='正在检查本机 Qwen 服务…';
 try{modelService=await api('/api/model-status');}
 catch{modelService={status:'unknown',checked_at:new Date().toISOString()};}
 finally{checkingModel=false;$('check-model').disabled=busy||!!historical;
  $('model-service-status').textContent=serviceText(modelService);
  $('model-service-time').textContent=`最近检查：${new Date(modelService.checked_at).toLocaleTimeString('zh-CN',{hour12:false})}。服务就绪不代表每次调用都会通过校验。`;
  if(selected==='llm')drawDetails();
 }
}
function shown(){return historical||activeContext||current;}
let noticeTimer;
function notice(text,error=false){
 clearTimeout(noticeTimer);
 const message=$('notice');message.textContent=text;message.hidden=!text;message.classList.toggle('problem',error);
 if(text&&!error)noticeTimer=setTimeout(()=>{if(message.textContent===text)message.hidden=true;},5000);
}
async function api(path,body){const r=await fetch(path,{signal:AbortSignal.timeout(path==='/api/commands'?125000:10000),method:body?'POST':'GET',headers:body?{'Content-Type':'application/json','X-Planning-Token':token}:{},body:body?JSON.stringify(body):undefined});const data=await r.json();if(!r.ok){const err=new Error(data.error.message+' ['+data.error.code+']');err.status=r.status;throw err;}return data;}
function syncButtons(){
 document.querySelectorAll('#request-form input,#request-form textarea,#request-form select,#request-form button').forEach(n=>n.disabled=busy||!!historical);
 for(const id of ['supplement-message','supplement-submit'])$(id).disabled=busy||!!historical||!current||dirty;
 document.querySelectorAll('#clarification-panel input,#clarification-panel select,#clarification-panel button').forEach(n=>n.disabled=busy||dirty||!!historical);
 const can=current?.status==='AWAITING_CONFIRMATION'&&!historical;
 $('confirm').disabled=busy||dirty||!can||!$('accept').checked;
 $('accept').disabled=busy||dirty||!can;
 $('stop-operation').hidden=!busy;
 $('stop-operation').disabled=!busy;
 $('cancel').disabled=busy||!!historical||!current||['COMPLETED','CANCELLED'].includes(current.status);
 for(const id of ['new','restore','refresh','history','recent-tasks','refresh-tasks'])$(id).disabled=busy||(id==='history'&&!current)||(id==='refresh'&&!current);
 $('export').disabled=busy||!shown();
 $('actions').hidden=!current||!!historical||!!activeContext||['COMPLETED','CANCELLED'].includes(current.status);
 $('dirty-hint').textContent=dirty?'输入已修改；请先保存，再核对并确认。':can?'修改输入后需要重新确认。':'';
 $('history-banner').hidden=!historical;
 if(historical)$('history-label').textContent=`正在查看历史记录（输入版本 ${historical.revision}）；返回当前任务后可继续操作。`;
}
function readInput(){const p={};for(const[id,name]of [['frequency','frequency_ghz'],['distance','distance_km']])if($(id).value!==''){const value=Number($(id).value);if(!Number.isFinite(value))throw new Error('手工参数必须是有限数值。');p[name]={value,unit:$(id+'-unit').value};}return {raw_text:$('raw-text').value,manual_parameters:p,condition:$('condition').value||null,target:$('target').value||null};}
function fillInput(s){$('raw-text').value=s.request.raw_text;$('condition').value=s.request.condition||'';$('target').value=s.request.target||'';for(const[id,name]of [['frequency','frequency_ghz'],['distance','distance_km']]){const p=s.request.manual_parameters[name];$(id).value=p?p.value:'';if(p)$(id+'-unit').value=p.unit;}$('manual-details').open=Object.keys(s.request.manual_parameters).length>0||!!s.request.condition||!!s.request.target;}
function chooseNode(id){if(id==='supplement')scrollOnSmallScreen('clarification-panel','center');selected=id;tab=nodes[id]?.[2]||'overview';draw();}
function chooseTab(id){tab=id;drawDetails();}
function chooseParameter(name){focusParameter=name;tab='parameters';selected='confirmation';draw();}
function drawDetails(){
 const s=shown();$('detail-tabs').replaceChildren();for(const[id,label]of Object.entries(tabNames)){const b=el('button',label,id===tab?'selected':'');b.setAttribute('aria-pressed',String(id===tab));b.addEventListener('click',()=>chooseTab(id));$('detail-tabs').append(b);}
 renderDetails($('detail-content'),{state:s,events:historical?[]:activity,node:selected,tab,focusParameter,onTab:chooseTab,onParameter:chooseParameter,historical:!!historical,modelService,settings:settings?.settings,models,onReparse:()=>submit('edit').catch(e=>notice(e.message,true))});
}
function drawTimeline(){
 const s=shown();$('trace').replaceChildren();const ev=historical?[]:relevantEvents(s,activity);
 $('event-count').textContent=`${ev.length||s?.trace?.length||0} 条记录`;
 if(ev.length){const start=new Map();for(const e of ev){const row=el('div',undefined,'trace-row');const time=new Date(e.at);row.append(el('span',Number.isNaN(time.getTime())?'时间未知':time.toLocaleTimeString('zh-CN',{hour12:false})));
  const b=el('button',nodes[e.node]?.[0]||(e.node==='command'?'命令与保存':e.node));b.addEventListener('click',()=>chooseNode(e.node in nodes?e.node:'state'));row.append(b);
  const key=e.run_id+':'+e.node;if(e.phase==='started')start.set(key,time.getTime());
  const duration=e.phase!=='started'&&start.has(key)?` · ${((time.getTime()-start.get(key))/1000).toFixed(3)} s`:'';
  const phase={started:'开始',completed:'完成',waiting:'等待用户处理',skipped:'未调用／降级',failed:'失败',cancelled:'已取消',committed:'已提交保存',rejected:'未提交／操作失败',replayed:'返回已有回执',interrupted:'观察中断，核对保存状态'}[e.phase]||e.phase;
  row.append(el('span',phase+duration+(e.details?.status?' · '+(labels[e.details.status]||e.details.status):'')+(e.details?.mode?' · '+e.details.mode:'')));$('trace').append(row);
 }}else for(const t of s?.trace||[]){const row=el('div',`${t.node} → ${t.status} · ${t.finished_at||t.at||''}`,'hint');$('trace').append(row);}
 $('raw-state').textContent=s?JSON.stringify(s,null,2):'尚无任务';
 renderWaterfall($('waterfall'),ev,el);miniWaterfall($('mini-waterfall'),ev,el);
}
function draw(){
 const s=shown(),ev=historical?[]:activity;
 renderFlow($('flow-canvas'),{view,state:s,events:ev,selected,onSelect:chooseNode,latency:historical?{}:nodeLatency(relevantEvents(s,ev))});

 $('flow-caption').textContent='连线按运行活动高亮，不表示直接调用链；正式结果以保存状态为准。';
 $('status').textContent=historical?'历史只读':busy?'正在处理':s?(s.waiting_reason||labels[s.status]||s.status):'等待输入';
 const taskDescription=activeContext?'正在处理输入':s?.request?.raw_text?.trim()||'未开始';
 $('task-meta').textContent=taskDescription;$('task-meta').title=taskDescription;
 const progress=taskProgress(s,ev,{dirty,historical:!!historical});
 const times=historical?[]:stepTimes(relevantEvents(s,ev)),ran=busy||historical?'':runSummary(relevantEvents(s,ev));
 $('current-action').textContent=progress.action+(ran?' '+ran:'');
 $('task-progress').replaceChildren(...progress.steps.map((step,i)=>{const row=el('li',undefined,step.status);row.append(el('span',({completed:'✓',running:'●',waiting:'◐',failed:'!',cancelled:'—',idle:'○'})[step.status]||'○','progress-symbol'),el('span',step.label),el('span',(step.status==='completed'&&times[i]?times[i]:({completed:'已完成',running:'处理中',waiting:'待处理',failed:'已阻断',cancelled:'已停止',idle:'未开始'})[step.status])||'未开始','progress-state'));if(['running','waiting'].includes(step.status))row.setAttribute('aria-current','step');return row;}));
 const states=nodeStates(s,ev),running=Object.entries(states).find(([id,status])=>status==='running'&&!['requirements','rag','knowledge','compute_agent','model','llm'].includes(id));
 const latest=relevantEvents(s,ev).at(-1);
 $('live-status').textContent=running?`正在运行：${nodes[running[0]][0]} · 等待后端返回`:
  latest?.phase==='interrupted'?'上次运行观察中断，请以已保存任务状态为准。':latest?.phase==='rejected'?'上次操作未提交，已保存版本保持有效。':s?(s.waiting_reason||labels[s.status]||s.status):'等待任务开始';
 drawDetails();drawTimeline();
 const questions=s?.input_issues?.length?[]:[...(s?.report?.questions||[]),reviewQuestion(s)].filter(Boolean);$('supplement-questions').replaceChildren(...questions.map(q=>el('p',q.replaceAll('distance_km','路径距离（km）').replaceAll('frequency_ghz','载波频率（GHz）'),'supplement-question')));
 renderConversation($('conversation-log'),s);
 renderQuestions($('clarification-panel'),s,{disabled:busy||dirty||!!historical,onSubmit:answers=>submit('answer',answers).catch(e=>notice(e.message,true)),onEdit:()=>{scrollOnSmallScreen('raw-text','center');$('raw-text').focus();}});syncButtons();
}
function acceptState(s){$('history-list').replaceChildren();if(current?.task_id!==s.task_id)activity=[];current=s;historical=null;activeContext=null;dirty=false;$('accept').checked=false;fillInput(s);$('task-id').value=s.task_id;localStorage.setItem('planning-task',s.task_id);history.replaceState(null,'','#'+s.task_id);$('submit').textContent='保存修改并重新解析';}
async function loadActivity(id,generation){try{const data=await api('/api/tasks/'+encodeURIComponent(id)+'/activity');if(generation!==pollGeneration||shown()?.task_id!==id)return;if(!activityFresh(activity,data.events))return;activity=data.events;draw();if(!data.available)$('live-status').textContent='运行观察不可用；任务完成后将显示保存状态。';}catch{if(generation===pollGeneration)$('live-status').textContent='运行观察暂不可用，请等待命令结果或刷新保存状态。';}}
async function poll(id,generation){await loadActivity(id,generation);if(busy&&generation===pollGeneration)setTimeout(()=>poll(id,generation),500);}
async function submit(action,answers=null){
 if(busy||historical)return;
 const c={action,task_id:current?.task_id||(pendingCommand?.action==='create'?pendingCommand.task_id:crypto.randomUUID()),event_id:crypto.randomUUID(),expected_revision:current?.revision||0,expected_state_version:current?.state_version||0};
 if(['create','edit'].includes(action)){c.input=readInput();c.mode=$('mode').value;}if(action==='supplement'){c.message=$('supplement-message').value.trim();c.mode=$('mode').value;if(!c.message||dirty)return;}if(action==='confirm')c.review_hash=current.review.review_hash;
 if(action==='answer'){if(dirty||!answers)return;c.answers=answers;c.mode=$('mode').value;}
 if(pendingCommand){const comparable=x=>JSON.stringify({...x,event_id:''});if(comparable(pendingCommand)===comparable(c))c.event_id=pendingCommand.event_id;}
 pendingCommand=c;busy=true;historical=null;const generation=++pollGeneration;
 activeContext=['create','edit','supplement','answer'].includes(action)?{task_id:c.task_id,revision:c.expected_revision+(action==='create'?0:1),state_version:0,status:'RUNNING',request:c.input||current.request,conversation:current?.conversation,report:null,trace:[]}:null;
 selected=action==='confirm'?'compute_agent':action==='cancel'?'confirmation':'requirements';tab=nodes[selected][2];
 localStorage.setItem('planning-task',c.task_id);history.replaceState(null,'','#'+c.task_id);$('task-id').value=c.task_id;
 notice('请求已发送。节点进度来自后端，产物提交前不作为正式结果。');draw();
 // Poll in parallel with the synchronous command. No artificial node progression.
 const request=api('/api/commands',c);poll(c.task_id,generation);
 try{const data=await request;pendingCommand=null;acceptState(data.state);if(action==='supplement')$('supplement-message').value='';selected=data.state.status==='COMPLETED'?'publish':data.state.status==='AWAITING_CONFIRMATION'?'confirmation':data.state.status==='AWAITING_INPUT'?'requirements':data.state.status==='NEEDS_MODEL'?'requirements':'failure';tab=nodes[selected][2];notice(data.replayed?'已恢复已有操作回执；显示当前保存状态。':data.state.status==='COMPLETED'?'计算与校验完成，正式结果已保存。':'本版本已保存，请核对当前节点。');}
 catch(e){if(e.status&&e.status<500)pendingCommand=null;activeContext=null;notice(e.message,true);}
 finally{checkModel();recentTasks();busy=false;const finalGeneration=++pollGeneration;await loadActivity(c.task_id,finalGeneration);draw();resetCockpitPanes();if(!pendingCommand&&current?.task_id===c.task_id){if(current.input_issues?.length)scrollOnSmallScreen('clarification-panel');else if(['AWAITING_CONFIRMATION','COMPLETED'].includes(current.status))scrollOnSmallScreen('detail-content');}}
}
async function restore(id){
 if(busy||!id)return;
 busy=true;syncButtons();const generation=++pollGeneration;
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
   notice('检测到仍在执行的操作，正在恢复实时观察。');draw();
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
  pendingCommand=null;activeContext=null;
  selected=current.status==='COMPLETED'?'publish':current.status==='AWAITING_INPUT'?'requirements':current.status==='NEEDS_MODEL'?'requirements':'confirmation';tab=nodes[selected][2];notice('已恢复任务的保存状态。');
 }catch(e){activeContext=null;notice(e.message,true);}finally{busy=false;draw();}
}
async function recentTasks(){
 try{const data=await api('/api/tasks');const select=$('recent-tasks');select.replaceChildren();const blank=el('option','选择最近任务（最多 50 项）');blank.value='';select.append(blank);for(const task of data.tasks){const option=el('option',`${labels[task.status]||task.status} · ${task.description||'未填写描述'} · ${task.task_id.slice(0,8)}`);option.value=task.task_id;select.append(option);}}catch(e){notice('任务列表加载失败：'+e.message,true);}
}
$('recent-tasks').addEventListener('change',()=>restore($('recent-tasks').value));
$('refresh-tasks').addEventListener('click',recentTasks);
$('stop-operation').addEventListener('click',async()=>{
 const run=pendingCommand||openRun(activity);
 if(!run){notice('尚未取得本次操作编号，请稍后重试。');return;}
 $('stop-operation').disabled=true;
 try{const response=await api('/api/cancel-operation',{task_id:run.task_id,event_id:run.event_id});notice(response.message);}catch(e){notice(e.message,true);}finally{$('stop-operation').disabled=!busy;}
});
$('check-model').addEventListener('click',checkModel);

function showSummary(){
 const text=summary(settings?.settings,models);
 $('model-badge-text').textContent=text.badge;$('settings-summary-text').replaceChildren(...text.lines.flatMap((line,i)=>i?[el('br'),line]:[line]));
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
function openSheet(id){sheetReturn=document.activeElement;$('sheet-scrim').hidden=false;$(id).hidden=false;$(id).querySelector('.icon-button').focus();}
function closeSheets(){for(const id of ['settings-sheet','metrics-panel'])$(id).hidden=true;$('sheet-scrim').hidden=true;sheetReturn?.focus?.();}
async function openSettings(){
 await loadSettings();if(!settings||!models)return;
 draft=structuredClone(settings.settings);drawSettings();openSheet('settings-sheet');checkModel();
}
async function saveSettings(){
 if(savingSettings||!draft)return;savingSettings=true;$('save-settings').disabled=true;
 try{settings=await api('/api/settings',{settings:draft,expected_version:settings.version});showSummary();closeSheets();notice('已保存为默认设置，从下一次操作开始生效；已保存的结果不变。');draw();
  // Health probes can take seconds when a port is closed; refresh them without blocking the save.
  api('/api/models').then(m=>{models=m;showSummary();}).catch(()=>{});}
 catch(e){if(e.status===409){await loadSettings();draft=structuredClone(settings.settings);drawSettings();}notice(e.message,true);}
 finally{savingSettings=false;$('save-settings').disabled=false;}
}
async function openMetrics(){
 openSheet('metrics-panel');$('metrics-body').replaceChildren(el('p','正在汇总运行记录…','hint'));
 try{renderMetrics($('metrics-body'),await api('/api/metrics'),el);}catch(e){$('metrics-body').replaceChildren(el('p','汇总失败：'+e.message,'hint'));}
}
$('model-badge').addEventListener('click',openSettings);$('open-settings').addEventListener('click',openSettings);
$('close-settings').addEventListener('click',closeSheets);$('close-metrics').addEventListener('click',closeSheets);$('sheet-scrim').addEventListener('click',closeSheets);
$('save-settings').addEventListener('click',saveSettings);
$('reset-settings').addEventListener('click',()=>{if(!models)return;draft=factorySettings(models);drawSettings();});
$('open-metrics').addEventListener('click',openMetrics);
$('request-form').addEventListener('submit',e=>{e.preventDefault();submit(current?'edit':'create').catch(e=>notice(e.message,true));});
$('request-form').addEventListener('input',()=>{dirty=!!current;$('accept').checked=false;draw();});
$('accept').addEventListener('change',syncButtons);$('confirm').addEventListener('click',()=>submit('confirm').catch(e=>notice(e.message,true)));$('cancel').addEventListener('click',()=>submit('cancel').catch(e=>notice(e.message,true)));
$('refresh').addEventListener('click',()=>restore(current?.task_id));$('restore').addEventListener('click',()=>restore($('task-id').value.trim()));
function populateExample(text,conflict=false){
 $('raw-text').value=text;
 for(const id of ['frequency','distance','condition','target'])$(id).value='';
 $('frequency-unit').value='GHz';$('distance-unit').value='km';
 if(conflict)$('frequency').value='3';
 $('manual-details').open=conflict;
 $('raw-text').dispatchEvent(new Event('input',{bubbles:true}));
 notice(conflict?'已填入示例：原文频率 2 GHz 与手工频率 3 GHz 冲突。点击开始筹划后核对修正。':'示例已填入；核对后点击开始筹划。');
}
$('example').addEventListener('click',()=>populateExample('按自由空间基准计算，频率2GHz，距离1km，求路径损耗。'));
$('budget-example').addEventListener('click',()=>populateExample('按自由空间基准计算链路余量：频率2GHz，距离10km，发射功率30dBm，发射天线增益10dBi，接收天线增益10dBi，发射馈线损耗2dB，接收馈线损耗2dB，额外损耗0dB，接收灵敏度-100dBm，预留余量10dB。'));
$('vague-example').addEventListener('click',()=>populateExample('我想让两艘船之间通信稳定一些，帮我规划一下。'));
$('range-example').addEventListener('click',()=>populateExample('按自由空间基准计算，频率2±0.1GHz，距离1km，求路径损耗。'));
$('missing-example').addEventListener('click',()=>populateExample('按自由空间基准计算，频率2GHz，求路径损耗。'));
$('choices-example').addEventListener('click',()=>populateExample('按自由空间基准计算，频率2GHz或3GHz，距离1km，求路径损耗。'));
$('conflict-example').addEventListener('click',()=>populateExample('按自由空间基准计算，频率2GHz，距离1km，求路径损耗。',true));
$('new').addEventListener('click',()=>{current=historical=activeContext=null;activity=[];dirty=false;pendingCommand=null;pollGeneration++;selected='input';tab='overview';focusParameter=null;localStorage.removeItem('planning-task');history.replaceState(null,'',location.pathname);$('request-form').reset();$('supplement-form').reset();$('task-id').value='';$('submit').textContent='开始筹划';$('history-list').replaceChildren();notice('新任务已准备好；原任务仍保存在本地。');draw();});
$('supplement-form').addEventListener('submit',e=>{e.preventDefault();submit('supplement').catch(e=>notice(e.message,true));});
$('expand-detail').addEventListener('click',()=>{const expanded=$('workspace').classList.toggle('detail-wide');$('expand-detail').textContent=expanded?'恢复布局':'展开详情';});
const canvasPanel=document.querySelector('.canvas-panel');
function setFlowExpanded(expanded){canvasPanel.classList.toggle('flow-expanded',expanded);$('expand-flow').textContent=expanded?'恢复工作台':'放大流程图';$('expand-flow').setAttribute('aria-expanded',String(expanded));}
$('expand-flow').addEventListener('click',()=>setFlowExpanded(!canvasPanel.classList.contains('flow-expanded')));
document.addEventListener('keydown',e=>{if(e.key!=='Escape')return;if(!$('sheet-scrim').hidden){closeSheets();return;}if(canvasPanel.classList.contains('flow-expanded')){setFlowExpanded(false);$('expand-flow').focus();}});
$('return-current').addEventListener('click',()=>{historical=null;if(current)fillInput(current);draw();});
$('history').addEventListener('click',async()=>{
 if(!current||busy)return;
 const taskId=current.task_id,generation=pollGeneration;
 try{
  const data=await api('/api/tasks/'+taskId+'/history');
  if(generation!==pollGeneration||current?.task_id!==taskId)return;
  $('history-list').replaceChildren();
  for(const item of data.history){
   const row=el('div',undefined,'history-entry');row.append(el('span',`输入版本 ${item.revision} · 保存序号 ${item.state_version} · ${labels[item.state.status]||item.state.status}`));const b=el('button','只读查看','secondary');
   b.addEventListener('click',()=>{if(busy||generation!==pollGeneration||current?.task_id!==taskId)return;historical=item.state;fillInput(historical);$('accept').checked=false;selected=historical.status==='COMPLETED'?'publish':'confirmation';tab=nodes[selected][2];draw();});row.append(b);$('history-list').append(row);
  }
 }catch(e){if(generation===pollGeneration)notice(e.message,true);}
});
$('export').addEventListener('click',()=>{const s=shown();if(!s||busy)return;const blob=new Blob([JSON.stringify(s,null,2)],{type:'application/json;charset=utf-8'});const url=URL.createObjectURL(blob);const a=el('a');a.href=url;a.download=`planning-${s.task_id}-r${s.revision}-v${s.state_version}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
draw();
checkModel();
(async()=>{try{token=(await api('/api/session')).token;await loadSettings();await recentTasks();const id=location.hash.slice(1)||localStorage.getItem('planning-task');if(id)await restore(id);}catch(e){notice('无法连接本地服务：'+e.message,true);}})();
