import {el,raw,parameterNames} from './details.mjs';
// The 资料 page: documents, sections to extract from, and drafts waiting for review.
export const KINDS=[['device','设备'],['site','站点'],['formula','公式']];
export const MAX_CHUNKS=6;
const NAMES={names:'名称',model:'型号',tx_power_dbm:'额定发射功率 dBm',antenna_gain_dbi:'天线增益 dBi',rx_sensitivity_dbm:'接收灵敏度 dBm',
 'band_ghz.0':'频段下限 GHz','band_ghz.1':'频段上限 GHz','position.lat':'纬度 °','position.lon':'经度 °','position.ground_m':'地面高程 m',
 'position.antenna_m':'天线离地高度 m','position.datum':'坐标基准',environment:'环境',title:'名称',description:'说明',expression:'表达式',
 'output.unit':'结果单位','examples.0.expected':'算例结果','applicability.notes':'适用条件'};
const CHECKS={match:['与原文一致','ok'],manual:['需人工核对','warn'],missing:['无原文','bad']};
const STATUS={draft:['待审核','run'],approved:['已入库','ok'],rejected:['已驳回','']};
const DOC_STATUS={ready:'可用',not_installed:'原文不在本机',changed:'原文已变',unreadable:'无法读取'};
export function fieldLabel(field){
 if(NAMES[field])return NAMES[field];
 const [group,,,name]=field.split('.');
 if(field.startsWith('parameters.'))return (parameterNames[field.slice(11)]||field.slice(11))+' 单位';
 if(field.startsWith('examples.0.inputs.'))return '算例 · '+(parameterNames[name]||name);
 return group;
}
export function shownValue(value){
 if(value===null||value===undefined)return '未写明';
 if(Array.isArray(value))return value.join('、');
 return String(value);
}
export function draftTitle(draft){
 const r=draft.record,kind=Object.fromEntries(KINDS)[draft.kind]||draft.kind;
 return `${kind} · ${draft.kind==='formula'?r.title:r.names.join('、')}`;
}
export function exampleLine(example){
 if(!example)return null;
 const inputs=Object.entries(example.inputs).map(([k,v])=>`${parameterNames[k]||k} ${v}`).join('，');
 const value=example.value===null?'无法计算':`${Number(example.value.toFixed(6))} ${example.unit}`;
 return {text:`算例：${inputs} → ${value}；原文 ${example.expected} ${example.unit}`,passed:example.passed};
}
// The locator already names the headings; the preview starts at the section's own text.
export function preview(text){
 return text.split('\n').filter(line=>!/^#{1,6}\s/.test(line)&&!/^<!--.*-->$/.test(line.trim())).join('\n').replace(/\n{3,}/g,'\n\n').trim();
}
function button(text,fn,cls='secondary compact'){const b=el('button',text,cls);b.type='button';b.addEventListener('click',fn);return b;}
function documentList(host,ctx){
 const lib=ctx.library;
 const head=el('div',undefined,'lib-head');head.append(el('h3','文档'));
 const pick=el('input');pick.type='file';pick.hidden=true;pick.accept=(lib?.formats||[]).join(',');
 pick.addEventListener('change',()=>{const file=pick.files[0];pick.value='';if(file)ctx.onUpload(file);});
 const add=button(ctx.uploading?'正在转换…':'添加文档',()=>pick.click());add.disabled=!!ctx.uploading||!!ctx.busy;head.append(add,pick);host.append(head);
 if(!lib){host.append(el('p','正在读取…','hint'));return;}
 host.append(el('p',lib.converter?'支持 PDF、Word、Excel、PPT、HTML、Markdown、文本，单个不超过 20 MB。原文只存本机，清单进 Git。'
  :'PDF、Markdown、文本可直接添加；Word、Excel、PPT、HTML 需先安装 requirements-docs.txt。','hint'));
 const list=el('div',undefined,'doc-list');
 for(const d of lib.documents){
  const row=button('',()=>ctx.onSelectDoc(d.doc_id),'doc-row'+(d.doc_id===ctx.selectedDoc?' selected':''));
  row.setAttribute('aria-pressed',String(d.doc_id===ctx.selectedDoc));
  row.append(el('span',d.title,'doc-title'));
  const tags=el('span',undefined,'doc-tags');
  if(d.simulated)tags.append(el('span','模拟','chip'));
  if(d.added)tags.append(el('span','本机添加','chip'));
  if(d.language==='en')tags.append(el('span','英文','chip'));
  tags.append(el('span',d.status==='ready'?`${d.chunks} 段`:DOC_STATUS[d.status]||d.status,'chip '+(d.status==='ready'?'':'warn')));
  if(d.enabled===false)tags.append(el('span','已停用','chip warn'));
  row.append(tags);row.disabled=d.status!=='ready';
  const item=el('div',undefined,'lib-item'+(d.enabled===false?' off':''));item.append(row);
  // Older servers do not report the switch; then the row stays as it was.
  if('enabled' in d)item.append(itemControls(ctx,'doc',d.doc_id,d.enabled,d.added,'参与检索'));
  list.append(item);
 }
 host.append(list);
}
// Enable switch for a document or formula card, and a two-step delete for what this machine added.
function itemControls(ctx,kind,id,enabled,removable,onText){
 const bar=el('div',undefined,'item-controls'),label=el('label',undefined,'toggle'),box=el('input');
 box.type='checkbox';box.checked=enabled;box.disabled=!!ctx.busy;box.addEventListener('change',()=>ctx.onSwitch(kind,id,box.checked));
 label.append(box,el('span',onText));bar.append(label);
 if(removable){
  const key=kind+':'+id;
  if(ctx.deleting===key){
   const yes=button('确认删除',()=>ctx.onDelete(kind,id),'danger compact'),no=button('取消',()=>ctx.onDeleteToggle(null),'text-button');
   yes.disabled=!!ctx.busy;yes.title=kind==='doc'?'删除本机原文与清单条目，不可恢复':'从公式库删除；历史任务的记录不受影响';bar.append(yes,no);
  }else{const b=button('删除',()=>ctx.onDeleteToggle(key),'text-button danger-text');b.disabled=!!ctx.busy;bar.append(b);}
 }
 return bar;
}
const CALC={dedicated:['专用程序','ok'],generic:['通用计算','run'],needs_tool:['需专用程序','warn']};
export const SOURCE_KINDS={builtin:'内置',document:'文档抽取',model_knowledge:'模型起草',manual:'手填'};
// The server says which card features this build has; anything not reported as true stays hidden.
const can=(ctx,name)=>ctx.capabilities?.[name]===true;
const calcLabel=(ctx,calc)=>calc==='generic'&&!can(ctx,'generic_calculation')?['仅作检索','']:CALC[calc]||[calc,''];
const computable=(ctx,calc)=>calc==='dedicated'||calc==='generic'&&can(ctx,'generic_calculation');
// Registered formula cards: what each can be used for, where it came from, and its switch.
function cardList(host,ctx){
 if(ctx.cards===undefined)return;  // a server without the card library endpoint
 const head=el('div',undefined,'lib-head'),actions=el('div',undefined,'lib-actions');
 for(const [form,text] of [['manual','新建公式卡'],['model','让模型起草']]){
  if(!can(ctx,form+'_drafts'))continue;
  const b=button(ctx.cardForm===form?'收起':text,()=>ctx.onCardForm(ctx.cardForm===form?null:form));b.disabled=!!ctx.busy;actions.append(b);
 }
 head.append(el('h3','公式卡'),actions);host.append(head);
 host.append(el('p',can(ctx,'generic_calculation')
  ?'专用程序：已有独立计算与复核。通用计算：已审核的封闭式公式按卡上表达式求值。需迭代或查表的公式要专用程序。停用后不参与检索和计算。'
  :'专用程序：已有独立计算与复核，可参与计算链。其余公式卡已入库，目前只参与公式检索，尚未支持计算。停用后不参与检索和计算。','hint'));
 if(ctx.cardForm==='manual'&&can(ctx,'manual_drafts'))host.append(manualForm(ctx));
 if(ctx.cardForm==='model'&&can(ctx,'model_drafts'))host.append(modelForm(ctx));
 if(ctx.cards===null){host.append(el('p','正在读取…','hint'));return;}
 const list=el('div',undefined,'card-list');
 for(const c of ctx.cards){
  const item=el('div',undefined,'lib-item card-item'+(c.enabled===false?' off':'')),top=el('div',undefined,'card-top'),tags=el('span',undefined,'doc-tags');
  const [calc,tone]=calcLabel(ctx,c.calc);
  tags.append(el('span',calc,'chip '+tone));
  if(SOURCE_KINDS[c.source_kind])tags.append(el('span',SOURCE_KINDS[c.source_kind],'chip'));
  if(c.enabled===false)tags.append(el('span','已停用','chip warn'));
  top.append(el('strong',c.title,'doc-title'),tags);item.append(top);
  item.append(el('p',`${c.id} · v${c.version}${c.output?` · 输出 ${c.output.name}（${c.output.unit}）`:''}`,'hint mono'));
  if(c.expression)item.append(raw('code',c.expression,'card-expr mono'));
  const src=c.sources?.[0];if(src)item.append(raw('p',[src.title,src.locator].filter(Boolean).join(' · '),'hint'));
  item.append(itemControls(ctx,'card',c.id,c.enabled!==false,c.added,computable(ctx,c.calc)?'参与计算':'参与检索'));
  list.append(item);
 }
 host.append(list);
}
function field(ctx,form,key,label,attrs={}){
 const wrap=el('label',undefined,'form-field'),input=el(attrs.rows?'textarea':'input');
 for(const [k,v] of Object.entries(attrs))input[k]=v;
 input.value=ctx.forms?.[form]?.[key]??'';input.disabled=!!ctx.busy;
 input.addEventListener('input',()=>ctx.onFormInput(form,key,input.value));
 wrap.append(el('span',label),input);return wrap;
}
// A card written by hand becomes a draft; its source and a checked example are given at review.
function manualForm(ctx){
 const box=el('div',undefined,'card-form');
 box.append(el('p','手填的公式先进草稿；审核时须填写真实出处与算例，算例经程序重算一致才能入库。','hint'));
 const grid=el('div',undefined,'form-grid');
 grid.append(field(ctx,'manual','id','编号（小写字母、数字、下划线）',{maxLength:64,placeholder:'doppler_max',className:'mono'}),
  field(ctx,'manual','title','名称',{maxLength:80}),
  field(ctx,'manual','output_name','输出量',{maxLength:64,placeholder:'doppler_hz',className:'mono'}),
  field(ctx,'manual','output_unit','输出单位',{maxLength:16,placeholder:'Hz'}));
 box.append(grid,field(ctx,'manual','expression','表达式（+ - * /、括号；函数 log10 ln sqrt sin cos abs；常数 pi）',{maxLength:500,className:'mono'}),
  field(ctx,'manual','parameters','参数：每行“名称 单位 说明”',{rows:3,maxLength:2000,placeholder:'frequency_ghz GHz 载波频率\nspeed_kmh km/h 相对速率',className:'mono'}),
  field(ctx,'manual','description','说明与适用条件',{rows:2,maxLength:500}));
 const go=button('提交草稿',ctx.onManualDraft,'primary compact');go.disabled=!!ctx.busy;box.append(go);
 return box;
}
function modelForm(ctx){
 const box=el('div',undefined,'card-form');
 box.append(el('p','模型按自身知识起草，出处未核；审核时须补上真实出处与算例，算例经程序重算一致才能入库。','hint'));
 box.append(field(ctx,'model','topic','要起草的公式',{maxLength:100,placeholder:'例如：最大多普勒频移'}));
 const go=button(ctx.drafting!=null?`起草中 · ${ctx.drafting} s`:'起草',ctx.onModelDraft,'primary compact');go.id='model-draft';go.disabled=!!ctx.busy;box.append(go);
 return box;
}
// "frequency_ghz GHz 载波频率" lines → card parameters; returns null on a malformed line.
export function parseParameters(text){
 const out={};
 for(const line of text.split('\n').map(l=>l.trim()).filter(Boolean)){
  const m=line.match(/^([a-z][a-z0-9_]{0,63})\s+(\S+)\s*(.*)$/);if(!m||m[1] in out)return null;
  out[m[1]]={unit:m[2],description:m[3]||m[1]};
 }
 return Object.keys(out).length?out:null;
}
export function manualRecord(form){
 const parameters=parseParameters(form.parameters||'');
 if(!/^[a-z0-9_]{1,64}$/.test(form.id||''))return {error:'编号只能用小写字母、数字和下划线。'};
 if(!(form.title||'').trim()||!(form.expression||'').trim())return {error:'名称和表达式必填。'};
 if(!/^[a-z][a-z0-9_]{0,63}$/.test(form.output_name||'')||!(form.output_unit||'').trim())return {error:'输出量与输出单位必填。'};
 if(!parameters)return {error:'参数每行写“名称 单位 说明”，名称不能重复。'};
 const description=(form.description||'').trim()||form.title.trim();
 return {record:{id:form.id,title:form.title.trim(),description,version:'1.0.0',status:'draft',expression:form.expression.trim(),
  output:{name:form.output_name,unit:form.output_unit.trim()},parameters,applicability:{requires:[],notes:[]},sources:[],examples:[]}};
}
function sectionList(host,ctx){
 const doc=ctx.library?.documents.find(d=>d.doc_id===ctx.selectedDoc);
 if(!doc){host.append(el('p','选一份文档，勾选要抽取的片段。','hint'));return;}
 const head=el('div',undefined,'lib-head');head.append(el('h3',`片段 · 已选 ${ctx.chosen.size}/${MAX_CHUNKS}`));host.append(head);
 if(!ctx.sections){host.append(el('p','正在读取…','hint'));return;}
 const list=el('div',undefined,'section-list');
 for(const s of ctx.sections){
  const row=el('label',undefined,'section-row'),box=el('input');box.type='checkbox';box.checked=ctx.chosen.has(s.id);
  box.disabled=!!ctx.busy||(!box.checked&&ctx.chosen.size>=MAX_CHUNKS);
  box.addEventListener('change',()=>ctx.onToggleChunk(s.id));
  const text=el('span',undefined,'section-text');text.append(el('span',s.locator.replace(/, chunk (\d+)$/,' · 第 $1 块'),'section-loc'),raw('span',preview(s.text),'section-excerpt'));
  row.append(box,text);list.append(row);
 }
 host.append(list);
 const bar=el('div',undefined,'extract-bar'),kinds=el('div',undefined,'segmented');kinds.setAttribute('role','group');kinds.setAttribute('aria-label','抽取类型');
 for(const [id,label] of KINDS){const b=button(label,()=>ctx.onKind(id),'');b.setAttribute('aria-pressed',String(ctx.kind===id));b.disabled=!!ctx.busy;kinds.append(b);}
 const go=button(ctx.extracting!==null&&ctx.extracting!==undefined?`抽取中 · ${ctx.extracting} s`:'抽取草稿',ctx.onExtract,'primary compact');
 go.id='extract-draft';go.disabled=!!ctx.busy||!ctx.chosen.size;
 bar.append(kinds,go);host.append(bar);
}
function checkTable(draft){
 const table=el('div',undefined,'draft-fields');
 for(const text of ['字段','值','原文','核对'])table.append(el('span',text,'draft-th'));
 for(const row of draft.checks){
  const [text,tone]=CHECKS[row.status]||[row.status,''];
  table.append(el('span',fieldLabel(row.field),'draft-name'),(row.value==null?el:raw)('span',shownValue(row.value),'draft-value'+(row.field==='expression'?' mono':'')));
  const quotes=el('span',undefined,'draft-quote');
  for(const q of row.quotes){const b=raw('blockquote');if(q.header)b.append(el('span',q.header,'quote-head'));b.append(el('span',q.quote));b.title=q.locator;quotes.append(b);}
  if(!row.quotes.length)quotes.append(el('span','—','muted'));
  table.append(quotes,el('span',text,'chip '+tone));
 }
 return table;
}
// What a hand-written or model-drafted formula says, since there is no source quote to check it against.
function recordSummary(record){
 const box=el('div',undefined,'record-summary');
 if(record.expression)box.append(raw('code',`${record.output?.name||''} = ${record.expression}`,'card-expr mono'));
 const ul=el('ul');
 for(const [name,p] of Object.entries(record.parameters||{}))ul.append(raw('li',`${name}（${p.unit}）${p.description&&p.description!==name?' '+p.description:''}`));
 box.append(ul);
 if(record.description)box.append(raw('p',record.description,'hint'));
 return box;
}
// Review fields for a draft without a document behind it: a real source and an example from it.
function sourceForm(draft,ctx,changed){
 const form=ctx.reviewForms?.[draft.id]||{},box=el('div',undefined,'source-form'),record=draft.record||{};
 const input=(key,label,attrs={})=>{
  const wrap=el('label',undefined,'form-field'),i=el('input');for(const [k,v] of Object.entries(attrs))i[k]=v;
  i.value=form[key]??'';i.disabled=!!ctx.busy;i.addEventListener('input',()=>{ctx.onReviewForm(draft.id,key,i.value);changed();});wrap.append(el('span',label),i);return wrap;
 };
 box.append(el('h4','出处与算例（审核人填写）'),el('p','填写你核对过的真实出处，并从该出处取一个算例；程序按表达式重算，一致才能入库。','hint'));
 const grid=el('div',undefined,'form-grid');
 grid.append(input('title','出处名称',{maxLength:200,placeholder:'例如 ITU-R P.525-5'}),input('locator','定位',{maxLength:120,placeholder:'例如 式(6)、第 3 页'}),
  input('url','链接（可选）',{maxLength:500,placeholder:'https://'}));
 for(const [name,p] of Object.entries(record.parameters||{}))grid.append(input('in:'+name,`${name}（${p.unit}）`,{inputMode:'decimal'}));
 grid.append(input('expected',`期望结果${record.output?.unit?`（${record.output.unit}）`:''}`,{inputMode:'decimal'}));
 box.append(grid,input('note','算例说明（可选）',{maxLength:200}));
 return box;
}
// The approve body's source and example, or null while a required value is missing or not a number.
export function sourcePayload(form,record){
 if(!form)return null;
 const title=(form.title||'').trim(),locator=(form.locator||'').trim(),url=(form.url||'').trim();
 if(!title||!locator||(url&&!/^https?:\/\//.test(url)))return null;
 const num=v=>(v??'').trim()===''?NaN:Number(v);
 const inputs={};
 for(const name of Object.keys(record?.parameters||{})){const v=num(form['in:'+name]);if(!Number.isFinite(v))return null;inputs[name]=v;}
 const expected=num(form.expected);if(!Number.isFinite(expected))return null;
 return {source:{title,locator,...(url?{url}:{})},example:{inputs,expected,note:(form.note||'').trim()}};
}
function draftCard(draft,ctx){
 const card=el('article',undefined,'draft-card '+draft.status),[label,tone]=STATUS[draft.status]||[draft.status,''];
 const head=el('div',undefined,'draft-head');head.append(el('strong',draftTitle(draft)),el('span',label,'chip '+tone));card.append(head);
 const doc=ctx.library?.documents.find(d=>d.doc_id===draft.doc_id);
 const at=new Date(draft.created_at).toLocaleString('zh-CN',{hour12:false});
 const kind=draft.source_kind||'document',ownSource=kind!=='document';
 if(kind==='model_knowledge')card.append(el('p',`来源：${draft.status==='approved'?'模型起草，审核人已补出处':'模型知识，出处未核'} · ${draft.origin?.model||'模型'} · ${at}`,'hint'+(draft.status==='draft'?' warn-text':'')));
 else if(kind==='manual')card.append(el('p',`来源：手填 · ${at}`,'hint'));
 else card.append(el('p',`来源：${doc?.title||draft.doc_id} · ${draft.origin?.model||'模型'} · ${at}`,'hint'));
 if(draft.checks?.length)card.append(checkTable(draft));
 else if(draft.kind==='formula'&&draft.record)card.append(recordSummary(draft.record));
 const example=exampleLine(draft.example);
 if(example&&draft.example.self_check)card.append(el('p',example.text.replace(/；原文 (.+)$/,'；模型给出 $1').replace(/^算例：/,'模型给的算例（只说明表达式自洽）：')+(example.passed?' · 一致':' · 不一致'),example.passed?'hint':'warn-text'));
 else if(example)card.append(el('p',example.text+(example.passed?' · 一致':' · 不一致'),example.passed?'ok':'warn-text'));
 for(const p of draft.problems||[])card.append(el('p',p,'warn-text'));
 if(draft.status==='draft'){
  const actions=el('div',undefined,'draft-actions');
  const approve=button('通过入库',()=>ctx.onReview(draft,'approve',''),'primary compact');
  const ready=()=>!ctx.busy&&draft.approvable&&(!ownSource||!!sourcePayload(ctx.reviewForms?.[draft.id],draft.record));
  approve.disabled=!ready();
  if(ownSource)card.append(sourceForm(draft,ctx,()=>{approve.disabled=!ready();}));
  const reject=button(ctx.rejecting===draft.id?'收起':'驳回',()=>ctx.onRejectToggle(draft.id));reject.disabled=!!ctx.busy;
  actions.append(approve,reject);card.append(actions);
  if(ctx.rejecting===draft.id){
   const reason=el('textarea');reason.rows=2;reason.maxLength=500;reason.placeholder='驳回原因';reason.setAttribute('aria-label','驳回原因');
   reason.value=ctx.reason||'';reason.addEventListener('input',()=>ctx.onReason(reason.value));
   const confirm=button('确认驳回',()=>ctx.onReview(draft,'reject',reason.value),'secondary compact');
   confirm.disabled=!!ctx.busy;
   const box=el('div',undefined,'reject-box');box.append(reason,confirm);card.append(box);
  }
 }else if(draft.review){
  const when=new Date(draft.review.at).toLocaleString('zh-CN',{hour12:false});
  card.append(el('p',`${label} · 审核人 ${draft.review.reviewer} · ${when}${draft.review.reason?' · '+draft.review.reason:''}`,'hint'));
  if(draft.status==='approved'&&draft.kind==='formula'){
   const calc=ctx.cards?.find(c=>c.id===draft.record?.id)?.calc;
   card.append(el('p',calc==='generic'?(can(ctx,'generic_calculation')?'公式卡已入库，可作为计算目标（通用计算）。':'公式卡已入库，目前只参与公式检索，尚未支持作为计算目标。')
    :calc==='needs_tool'?'公式卡已入库；这类公式需要专用程序，暂不能计算。'
    :'公式卡已入库；计算规划目前只用已支持的公式，这张卡先作资料与检索使用。','hint'));
  }
 }
 return card;
}
function draftList(host,ctx){
 const head=el('div',undefined,'lib-head');head.append(el('h3','草稿与审核'));
 const who=el('input');who.value=ctx.reviewer;who.placeholder='审核人';who.maxLength=40;who.setAttribute('aria-label','审核人');who.className='reviewer';
 who.addEventListener('input',()=>ctx.onReviewer(who.value));head.append(who);host.append(head);
 host.append(el('p','草稿未审核不能参与计算。审核人必填；通过后写入仓库的站点、设备或公式库。','hint'));
 if(!ctx.drafts){host.append(el('p','正在读取…','hint'));return;}
 if(!ctx.drafts.length){host.append(el('p','暂无草稿','hint'));return;}
 for(const d of ctx.drafts)host.append(draftCard(d,ctx));
}
export function renderModulations(host,records){
 const head=el('div',undefined,'lib-head');
 head.append(el('h3','调制灵敏度'),el('span','模拟参数，可配置','hint'));
 const table=el('table'),thead=el('thead'),labels=el('tr'),body=el('tbody');
 labels.append(el('th','调制方式'),el('th','灵敏度（dBm）'));thead.append(labels);
 for(const record of records.filter(r=>r.type==='modulation')){
  const row=el('tr');row.append(raw('td',record.names[0]),el('td',String(record.rx_sensitivity_dbm),'num'));body.append(row);
 }
 table.append(thead,body);host.replaceChildren(head,table);
}
function modulationSection(ctx){
 const section=el('section',undefined,'lib-drafts');
 if(ctx.facts){renderModulations(section,ctx.facts.records||ctx.facts);return section;}
 section.append(el('p','正在读取调制灵敏度…','hint'));
 // This read-only table loads its own presentation data; the task input remains untouched.
 fetch('/api/facts').then(response=>{
  if(!response.ok)throw new Error('facts');return response.json();
 }).then(data=>renderModulations(section,data.records)).catch(()=>{
  section.replaceChildren(el('p','调制灵敏度读取失败，请重新打开资料页。','warn-text'));
 });
 return section;
}
export function renderLibrary(host,ctx){
 const docs=el('section',undefined,'lib-column'),sections=el('section',undefined,'lib-column'),drafts=el('section',undefined,'lib-drafts');
 documentList(docs,ctx);sectionList(sections,ctx);draftList(drafts,ctx);
 const cards=el('section',undefined,'lib-drafts lib-cards');cardList(cards,ctx);
 const top=el('div',undefined,'lib-top');top.append(docs,sections);
 host.replaceChildren(...(ctx.message?[el('p',ctx.message,'lib-message')]:[]),top,...(ctx.cards===undefined?[]:[cards]),drafts,modulationSection(ctx));
}
