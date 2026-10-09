import {taskProgress,headline} from './progress.mjs';
import {serviceText} from './model-status.mjs';
import {nodes,renderFlow,relevantEvents,activityFresh,openRun} from './flow.mjs';
import {renderRight,nodeCard,el,labels,parameterNames,conditionNames,targetNames} from './details.mjs';
import {formatDomain} from './values.mjs';
import {assumptionEdit} from './m1.mjs';
import {renderConversation} from './conversation.mjs';
import {renderRecords} from './records.mjs';
import {renderQuestions,openQuestions} from './questions.mjs';
import {renderReport} from './report.mjs';
import {summary,factorySettings,renderSettingsForm,switchView} from './settings.mjs';
import {nodeLatency,stepTimes,runSummary,renderWaterfall,miniWaterfall,renderMetrics} from './timing.mjs';
import {headerText,setMarquee,fitMarquee} from './marquee.mjs';
import {renderLibrary,draftTitle,MAX_CHUNKS,manualRecord,sourcePayload} from './library.mjs';
import {lastSwap,previousVersion,comparisonLine} from './compare.mjs';
import {lang,setLang,install,watch} from './i18n.mjs';
// English swaps rendered text through the dictionary; Chinese needs nothing loaded.
if(lang()==='en'){install(await import('./i18n-en.mjs'));watch(document.body);}
const $=id=>document.getElementById(id);
const narrow=()=>window.matchMedia('(max-width: 899px)').matches;
let current=null, historical=null, activeContext=null, activity=[], token='', dirty=false, editing=false, busy=false, busyAction=null, pendingCommand=null;
let modelService=null, checkingModel=false;
let settings=null, models=null, draft=null, savingSettings=false, switcher=null, switchTimer=null;
const switching=()=>switcher?.state==='switching';
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
let toastTimer,toastCount=0;
function notice(text,error=false){
 if(error){$('notice').textContent=text;$('notice').hidden=!text;return;}
 clearTimeout(toastTimer);const toast=$('toast'),shown=++toastCount;toast.textContent=text;toast.hidden=!text;
 if(text)toastTimer=setTimeout(()=>{if(toastCount===shown)toast.hidden=true;},4000);
}
const clearError=()=>notice('',true);
const TIMEOUTS={'/api/commands':125000,'/api/drafts/extract':200000,'/api/drafts/model':200000,'/api/drafts/review':30000,'/api/documents':30000};
async function api(path,body){const r=await fetch(path,{signal:AbortSignal.timeout(TIMEOUTS[path]||(path.startsWith('/api/documents/')?30000:10000)),method:body?'POST':'GET',headers:body?{'Content-Type':'application/json','X-Planning-Token':token}:{},body:body?JSON.stringify(body):undefined});const data=await r.json();if(!r.ok){const err=new Error(data.error.message+' ['+data.error.code+']');err.status=r.status;throw err;}return data;}
// Which folder, branch and commit this page is served from, so two working copies are never confused.
function showInstance(x){
 const line=$('instance-line');if(!line||!x?.folder)return;
 const text=[x.folder,x.branch,x.commit&&x.commit+(x.dirty?'*':'')].filter(Boolean).join(' · ');
 line.textContent=text;line.title=text+(x.dirty?'（* 有未提交改动）':'');line.hidden=false;
}
function syncButtons(){
 // A model switch holds every command that may call a model; cancelling a task still works.
 const hold=busy||switching()||lib.uploading||lib.busy;
 document.querySelectorAll('#request-form input,#request-form textarea,#request-form select,#request-form button').forEach(n=>n.disabled=hold||!!historical);
 for(const id of ['supplement-message','supplement-submit'])$(id).disabled=hold||!!historical||!current||dirty||editing;
 document.querySelectorAll('#clarification-panel input,#clarification-panel select,#clarification-panel button').forEach(n=>n.disabled=hold||dirty||editing||!!historical);
 const can=current?.status==='AWAITING_CONFIRMATION'&&!historical&&!activeContext;
 $('actions').hidden=!can;
 $('confirm').disabled=hold||dirty||editing||!can||!$('accept').checked;
 $('accept').disabled=hold||dirty||editing||!can;
 $('cancel').disabled=busy||!can;
 $('stop-operation').hidden=!busy;$('stop-operation').disabled=!busy;
 $('return-current').hidden=!historical;
 const unfinished=!!current&&!historical&&!['COMPLETED','CANCELLED'].includes(current.status);
 $('menu-cancel').hidden=!unfinished||current.status==='AWAITING_CONFIRMATION';$('menu-cancel').disabled=busy;
 for(const id of ['new','restore','refresh','history','refresh-tasks'])$(id).disabled=busy||(['history','refresh'].includes(id)&&!current);
 $('export').disabled=busy||!shown();
}
function readInput(){const p={...current?.request?.manual_parameters};delete p.frequency_ghz;delete p.distance_km;for(const[id,name]of [['frequency','frequency_ghz'],['distance','distance_km']])if($(id).value!==''){const value=Number($(id).value);if(!Number.isFinite(value))throw new Error('手工参数必须是有限数值。');p[name]={value,unit:$(id+'-unit').value};}return {raw_text:$('raw-text').value,manual_parameters:p,condition:$('condition').value||null,target:$('target').value||null};}
function fillInput(s){$('raw-text').value=s.request.raw_text;$('condition').value=s.request.condition||'';$('target').value=s.request.target||'';for(const[id,name]of [['frequency','frequency_ghz'],['distance','distance_km']]){const p=s.request.manual_parameters[name];$(id).value=p?p.value:'';if(p)$(id+'-unit').value=p.unit;}$('manual-details').open=Object.keys(s.request.manual_parameters).length>0||!!s.request.condition||!!s.request.target;}
// Registered cards for the formula view, verified against the task's evidence hashes when shown.
const cards={},facts={};let cardsLoading=false;
async function ensureCards(){
 const s=shown(),plan=(s?.review?.report||s?.report)?.calculation_plan_proposal;if(!plan||cardsLoading)return;
 const ids=[...new Set(plan.steps.map(x=>x.tool_id))].filter(id=>!(id in cards));if(!ids.length)return;
 cardsLoading=true;
 let loaded=false;
 try{const data=await api('/api/formula-cards?ids='+ids.join(','));for(const c of data.cards)cards[c.id]=c;for(const id of data.missing)cards[id]=null;loaded=true;}
 catch(e){notice('公式卡读取失败：'+e.message,true);}
 finally{cardsLoading=false;if(loaded)drawRight();}
}
function setView(next){view=next;popover=null;if(next==='main')focusParameter=null;if(next==='formula'||next==='evidence')ensureCards();if(!matchMedia('(min-width: 1350px)').matches)sideChoice='plan';draw();$('detail-content').scrollTop=0;}
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
 const body=el('p',text,'original-text');body.translate=false;card.append(head,body);
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
 renderRecords($('execution-records'),mode==='task'?s:null,historical?[]:activity);
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
// The version before the last follow-up swap, for one line under the result.
const comparisons=new Map();
async function ensureComparison(){
 const s=shown();if(!s||s.status!=='COMPLETED'||!lastSwap(s))return;
 const key=`${s.task_id}:${s.revision}`;if(comparisons.has(key))return;
 comparisons.set(key,null);
 try{const data=await api('/api/tasks/'+encodeURIComponent(s.task_id)+'/history');comparisons.set(key,comparisonLine(s,previousVersion(s,data.history)));drawRight();}
 catch{comparisons.delete(key);}
}
// The 资料 page: documents, sections, extraction and review.
const lib={library:null,selectedDoc:null,sections:null,chosen:new Set(),kind:'device',extracting:null,message:'',drafts:null,reviewer:'',reason:'',rejecting:null,busy:false,uploading:false,
 cards:null,capabilities:{},deleting:null,cardForm:null,forms:{manual:{},model:{}},reviewForms:{},drafting:null};
try{lib.reviewer=localStorage.getItem('planning-reviewer')||'';}catch{}
function drawLibrary(){
 renderLibrary($('library-body'),{...lib,onSelectDoc:selectDoc,onToggleChunk:toggleChunk,onKind:k=>{lib.kind=k;drawLibrary();},onExtract:extractDraft,
  onUpload:uploadDocument,onReview:reviewDraft,onReason:v=>{lib.reason=v;},onRejectToggle:id=>{lib.rejecting=lib.rejecting===id?null:id;lib.reason='';drawLibrary();},
  onReviewer:v=>{lib.reviewer=v.trim();try{localStorage.setItem('planning-reviewer',lib.reviewer);}catch{}},
  onSwitch:switchItem,onDelete:deleteItem,onDeleteToggle:key=>{lib.deleting=key;drawLibrary();},
  onCardForm:form=>{lib.cardForm=form;drawLibrary();},onFormInput:(form,key,value)=>{lib.forms[form][key]=value;},
  onManualDraft:manualDraft,onModelDraft:modelDraft,
  onReviewForm:(id,key,value)=>{(lib.reviewForms[id]??={})[key]=value;}});
 syncButtons();
}
// The full listing carries what this build can do with cards; switch and delete answers carry the cards only.
function takeCards(data){lib.cards=data.cards;lib.capabilities=data.capabilities||{};}
async function loadLibrary(){
 const [docs,drafts,cards]=await Promise.allSettled([api('/api/documents'),api('/api/drafts'),api('/api/formula-library')]);
 if(docs.status==='fulfilled')lib.library=docs.value;else lib.message='文档读取失败：'+docs.reason.message;
 // A server without the card library answers 404: the card section is simply not shown.
 if(cards.status==='fulfilled')takeCards(cards.value);else if(cards.reason.status===404)lib.cards=undefined;else lib.message='公式卡读取失败：'+cards.reason.message;
 if(drafts.status==='fulfilled')lib.drafts=drafts.value.drafts;else lib.message='草稿读取失败：'+drafts.reason.message;
 drawLibrary();
}
function openLibrary(){openSheet('library-sheet');drawLibrary();loadLibrary();}
async function selectDoc(id){
 if(lib.selectedDoc===id||lib.busy)return;lib.selectedDoc=id;lib.sections=null;lib.chosen=new Set();lib.message='';drawLibrary();
 try{const data=await api('/api/documents/'+encodeURIComponent(id));if(lib.selectedDoc===id)lib.sections=data.sections;}catch(e){lib.message=e.message;}
 drawLibrary();
}
function toggleChunk(id){if(lib.chosen.has(id))lib.chosen.delete(id);else if(lib.chosen.size<MAX_CHUNKS)lib.chosen.add(id);drawLibrary();}
async function extractDraft(){
 if(lib.busy||!lib.chosen.size)return;
 if(switching()){lib.message='正在切换模型，完成后再抽取。';drawLibrary();return;}
 lib.busy=true;lib.message='';lib.extracting=0;drawLibrary();const started=Date.now();
 // Only the button text changes each second, so a half-typed reason is not redrawn away.
 const timer=setInterval(()=>{lib.extracting=Math.round((Date.now()-started)/1000);const b=$('extract-draft');if(b)b.textContent=`抽取中 · ${lib.extracting} s`;},1000);
 try{const data=await api('/api/drafts/extract',{kind:lib.kind,chunk_ids:[...lib.chosen]});
  lib.message=`${data.message}（${Math.round((Date.now()-started)/1000)} s）`;
  if(data.draft)lib.drafts=[data.draft,...(lib.drafts||[]).filter(d=>d.id!==data.draft.id)];}
 catch(e){lib.message='抽取失败：'+e.message;}
 finally{clearInterval(timer);lib.busy=false;lib.extracting=null;drawLibrary();}
}
async function uploadDocument(file){
 if(lib.uploading||lib.busy||busy||switching())return;
 if(file.size>(lib.library?.max_bytes||20*1024*1024)){lib.message='文件超过 20 MB。';drawLibrary();return;}
 lib.uploading=true;lib.message='';drawLibrary();
 try{
  const r=await fetch('/api/documents?name='+encodeURIComponent(file.name),{method:'POST',body:file,signal:AbortSignal.timeout(120000),
   headers:{'Content-Type':'application/octet-stream','X-Planning-Token':token}});
  const data=await r.json();if(!r.ok)throw new Error(data.error.message);
  lib.library=data.library;lib.uploading=false;await selectDoc(data.document.doc_id);
  lib.message=`已添加：${data.document.title}。请选择片段，抽取并核对草稿后填写审核人，通过后才能参与计算。`;
 }catch(e){lib.message='添加失败：'+e.message;}
 finally{lib.uploading=false;drawLibrary();}
}
async function uploadAttachment(file){
 if(busy||historical||switching()||lib.busy||lib.uploading)return;
 openSheet('library-sheet');drawLibrary();
 await loadLibrary();
 await uploadDocument(file);
}
async function reviewDraft(draft,decision,reason){
 if(lib.busy)return;
 if(!lib.reviewer){lib.message='请先填写审核人。';drawLibrary();document.querySelector('#library-body .reviewer')?.focus();return;}
 if(decision==='reject'&&!(reason||lib.reason).trim()){lib.message='驳回时请写明原因。';drawLibrary();return;}
 lib.busy=true;lib.message='';drawLibrary();
 try{
  // A draft without a document behind it is approved with the reviewer's source and example.
  const own=decision==='approve'&&(draft.source_kind||'document')!=='document'?sourcePayload(lib.reviewForms[draft.id],draft.record):null;
  const data=await api('/api/drafts/review',{id:draft.id,decision,reviewer:lib.reviewer,reason:decision==='reject'?(reason||lib.reason).trim():'',content_hash:draft.content_hash,...own});
  lib.rejecting=null;lib.reason='';notice(decision==='approve'?'已入库：'+draftTitle(draft):'已驳回：'+draftTitle(draft));
  lib.drafts=(await api('/api/drafts')).drafts;  // other drafts may now name a record already in the library
  if(decision==='approve'){const f=await api('/api/facts');for(const record of f.records)facts[record.id]=record;
   if(draft.kind==='formula'&&lib.cards!==undefined)takeCards(await api('/api/formula-library'));}
 }catch(e){lib.message=e.message;}
 finally{lib.busy=false;drawLibrary();}
}
const ITEM={doc:{switch:'/api/documents/switch',remove:'/api/documents/delete',key:'doc_id'},card:{switch:'/api/formula-cards/switch',remove:'/api/formula-cards/delete',key:'id'}};
function itemTitle(kind,id){return kind==='doc'?lib.library?.documents.find(d=>d.doc_id===id)?.title||id:lib.cards?.find(c=>c.id===id)?.title||id;}
function takeItems(kind,data){if(kind==='doc')lib.library=data.library;else lib.cards=data.cards;}
// Switching a document or card changes what retrieval and planning can use from the next operation on.
async function switchItem(kind,id,enabled){
 if(lib.busy)return;lib.busy=true;lib.message='';const title=itemTitle(kind,id);drawLibrary();
 try{takeItems(kind,await api(ITEM[kind].switch,{[ITEM[kind].key]:id,enabled}));lib.message=(enabled?'已启用：':'已停用：')+title;}
 catch(e){lib.message='操作失败：'+e.message;}
 finally{lib.busy=false;drawLibrary();}
}
async function deleteItem(kind,id){
 if(lib.busy)return;lib.busy=true;lib.message='';const title=itemTitle(kind,id);drawLibrary();
 try{takeItems(kind,await api(ITEM[kind].remove,{[ITEM[kind].key]:id}));lib.deleting=null;lib.message='已删除：'+title;
  if(kind==='doc'&&lib.selectedDoc===id){lib.selectedDoc=null;lib.sections=null;lib.chosen=new Set();}
  lib.drafts=(await api('/api/drafts')).drafts;}
 catch(e){lib.message='删除失败：'+e.message;}
 finally{lib.busy=false;drawLibrary();}
}
function addDraft(data){lib.message=data.message||'已生成草稿，请填写出处与算例后审核。';if(data.draft)lib.drafts=[data.draft,...(lib.drafts||[]).filter(d=>d.id!==data.draft.id)];}
async function manualDraft(){
 if(lib.busy)return;
 const made=manualRecord(lib.forms.manual);if(made.error){lib.message=made.error;drawLibrary();return;}
 lib.busy=true;lib.message='';drawLibrary();
 try{addDraft(await api('/api/drafts/manual',{kind:'formula',record:made.record}));lib.forms.manual={};lib.cardForm=null;}
 catch(e){lib.message='提交失败：'+e.message;}
 finally{lib.busy=false;drawLibrary();}
}
async function modelDraft(){
 const topic=(lib.forms.model.topic||'').trim();
 if(lib.busy)return;if(!topic){lib.message='请写明要起草的公式。';drawLibrary();return;}
 if(switching()){lib.message='正在切换模型，完成后再起草。';drawLibrary();return;}
 lib.busy=true;lib.message='';lib.drafting=0;drawLibrary();const started=Date.now();
 const timer=setInterval(()=>{lib.drafting=Math.round((Date.now()-started)/1000);const b=$('model-draft');if(b)b.textContent=`起草中 · ${lib.drafting} s`;},1000);
 try{addDraft(await api('/api/drafts/model',{kind:'formula',topic}));lib.forms.model={};lib.cardForm=null;}
 catch(e){lib.message='起草失败：'+e.message;}
 finally{clearInterval(timer);lib.busy=false;lib.drafting=null;drawLibrary();}
}
function openNodeCard(id){popover=popover?.id===id?null:{id};drawFlow();}
function renderNodeCard(){
 const card=$('node-card');
 if(!popover){card.hidden=true;return;}
 const s=shown(),ev=historical?[]:activity,info=nodeCard(popover.id,{state:s,events:ev,latency:historical?{}:nodeLatency(relevantEvents(s,ev)),modelService});
 const head=el('div',undefined,'node-card-head'),close=el('button','✕','icon-button');close.type='button';close.setAttribute('aria-label','关闭');close.addEventListener('click',()=>{popover=null;drawFlow();});
 head.append(el('strong',info.title),close);
 card.replaceChildren(head,el('p',info.status,'node-card-status '+info.tone),...info.lines.map(line=>el('p',line)));
 if(info.quote){const q=el('p',info.quote);q.translate=false;card.append(q);}
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
 ensureCards();ensureComparison();
 renderRight($('detail-content'),{state:s,view,focusParameter,historical:!!historical,comparison:s?comparisons.get(`${s.task_id}:${s.revision}`):null,disabled:busy||dirty||editing,activeContext:!!activeContext,modelService,settings:settings?.settings,models,open:folds,cards,facts,
  onView:setView,onParameter:chooseParameter,onMissing:focusQuestion,onReparse:()=>submit('edit').catch(e=>notice(e.message,true)),
  onAssumption:(name,value)=>{try{const input=assumptionEdit(current,name,value);submit('edit',null,input).catch(e=>notice(e.message,true));}catch(e){notice(e.message,true);}}});
 renderReport($('report-panel'),$('open-report'),s,historical?[]:activity,{facts,cards});
 const n=openQuestions(s).length;
 $('pending-bar').hidden=!n||!!historical||busy||editing;$('pending-bar').textContent=`${h.text} · 去处理`;
}
function autoSide(){const s=shown();return !s||editing||s.status==='AWAITING_INPUT'||(s.status==='NEEDS_MODEL'&&s.failure?.code!=='BEYOND_LINE_OF_SIGHT')?'chat':'plan';}
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
 setMarquee($('task-meta'),headerText(activeContext,historical||current));
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
async function submit(action,answers=null,inputOverride=null){
 if(busy||historical)return;
 if(switching()&&action!=='cancel'){notice('正在切换模型，完成后再提交。',true);return;}
 const c={action,task_id:current?.task_id||(pendingCommand?.action==='create'?pendingCommand.task_id:crypto.randomUUID()),event_id:crypto.randomUUID(),expected_revision:current?.revision||0,expected_state_version:current?.state_version||0,lang:lang()};
 if(['create','edit'].includes(action)){c.input=inputOverride||readInput();c.mode=$('mode').value;}if(action==='supplement'){c.message=$('supplement-message').value.trim();c.mode=$('mode').value;if(!c.message||dirty||editing)return;}if(action==='confirm')c.review_hash=current.review.review_hash;
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
   if(!saved||running.revision!==saved.revision)activeContext={task_id:id,revision:running.revision,state_version:0,status:'RUNNING',placeholder:true,request:{raw_text:'正在恢复运行观察，原文以提交后的记录为准。',manual_parameters:{}},report:null,trace:[]};
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
   row.append(el('span',labels[task.status]||task.status,'chip '+({COMPLETED:'ok',AWAITING_CONFIRMATION:'run',AWAITING_INPUT:'warn',NEEDS_MODEL:'warn'}[task.status]||'')),el('span',task.description||'未填写描述','recent-text'),el('small',task.task_id.slice(0,8)));row.children[1].translate=!task.description;
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
 if(settings)$('mode').value=settings.settings.mode_default;
 if(switching()){$('model-badge-text').textContent=`切换模型 · ${Math.round((switcher.elapsed_ms||0)/1000)} s`;$('model-dot').className='dot run';return;}
 const text=summary(settings?.settings,models);$('model-badge-text').textContent=text.badge;
 const st=models?.status?.[settings?.settings?.chat?.default];
 $('model-dot').className='dot '+(settings?.settings?.mode_default!=='llm'?'':st==='ready'?'ok':st==='loading'?'run':'off');
}
async function loadSettings(){
 const results=await Promise.allSettled([api('/api/settings'),api('/api/models'),api('/api/model-switch')]);
 if(results[0].status==='fulfilled')settings=results[0].value;
 if(results[1].status==='fulfilled')models=results[1].value;
 if(results[2].status==='fulfilled')switcher=results[2].value;
 const failed=results.find(r=>r.status==='rejected');if(failed)notice('部分模型与检索状态载入失败：'+failed.reason.message,true);
 showSummary();
 if(switching()&&!switchTimer)tickSwitch();
}
function switchLock(){return busy?'正在处理任务，完成后才能切换。':lib.busy?'正在抽取资料，完成后才能切换。':'';}
function drawSettings(){renderSettingsForm($('settings-form'),{draft,models,status:models?.status,corpus:models?.corpus,el,switcher,locked:switchLock(),onSwitch:startSwitch,onChange:next=>{draft=next;drawSettings();}});}
async function startSwitch(modelId){
 if(switching()||switchLock())return;
 try{switcher=await api('/api/model-switch',{model_id:modelId});}
 catch(e){notice(e.message,true);return;}
 clearError();showSummary();syncButtons();if(!$('settings-sheet').hidden)drawSettings();tickSwitch();
}
// One poll a second while a switch runs: only the waiting time changes until it ends.
function tickSwitch(){
 clearTimeout(switchTimer);
 switchTimer=setTimeout(async()=>{
  try{switcher=await api('/api/model-switch');}catch{}
  if(switching()){
   const line=document.querySelector('#settings-form .switch-status'),view=switchView({draft,models,status:models?.status,switcher});
   if(line&&view)line.textContent=view.text;
   showSummary();tickSwitch();return;
  }
  switchTimer=null;await loadSettings();
  if(draft)draft.chat=structuredClone(settings.settings.chat);
  if(switcher?.message)notice(switcher.message,switcher.state==='failed');
  if(!$('settings-sheet').hidden)drawSettings();
  checkModel();draw();
 },1000);
}
let sheetReturn=null;
const SHEETS=['settings-sheet','metrics-panel','history-sheet','library-sheet'];
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
$('lang-toggle').textContent=lang()==='en'?'中文':'EN';
$('lang-toggle').addEventListener('click',()=>{setLang(lang()==='en'?'zh':'en');location.reload();});
$('close-settings').addEventListener('click',closeSheets);$('close-library').addEventListener('click',closeSheets);$('open-library').addEventListener('click',openLibrary);$('close-metrics').addEventListener('click',closeSheets);$('close-history').addEventListener('click',closeSheets);$('sheet-scrim').addEventListener('click',closeSheets);
$('add-attachment').addEventListener('click',()=>$('attachment-file').click());
$('attachment-file').addEventListener('change',()=>{const file=$('attachment-file').files[0];$('attachment-file').value='';if(file)uploadAttachment(file);});
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
new ResizeObserver(()=>fitMarquee($('task-meta'))).observe($('task-meta').parentElement);
checkModel();
(async()=>{try{const session=await api('/api/session');token=session.token;showInstance(session.instance);const data=await api('/api/facts');for(const record of data.records)facts[record.id]=record;await loadSettings();draw();await recentTasks();const id=location.hash.slice(1)||localStorage.getItem('planning-task');if(id)await restore(id);}catch(e){notice('无法连接本地服务：'+e.message,true);}})();
