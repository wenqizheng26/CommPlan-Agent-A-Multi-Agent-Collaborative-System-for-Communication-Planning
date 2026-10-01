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
  row.append(tags);row.disabled=d.status!=='ready';list.append(row);
 }
 host.append(list);
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
function draftCard(draft,ctx){
 const card=el('article',undefined,'draft-card '+draft.status),[label,tone]=STATUS[draft.status]||[draft.status,''];
 const head=el('div',undefined,'draft-head');head.append(el('strong',draftTitle(draft)),el('span',label,'chip '+tone));card.append(head);
 const doc=ctx.library?.documents.find(d=>d.doc_id===draft.doc_id);
 const at=new Date(draft.created_at).toLocaleString('zh-CN',{hour12:false});
 card.append(el('p',`来源：${doc?.title||draft.doc_id} · ${draft.origin?.model||'模型'} · ${at}`,'hint'));
 if(draft.checks?.length)card.append(checkTable(draft));
 const example=exampleLine(draft.example);
 if(example)card.append(el('p',example.text+(example.passed?' · 一致':' · 不一致'),example.passed?'ok':'warn-text'));
 for(const p of draft.problems||[])card.append(el('p',p,'warn-text'));
 if(draft.status==='draft'){
  const actions=el('div',undefined,'draft-actions');
  const approve=button('通过入库',()=>ctx.onReview(draft,'approve',''),'primary compact');
  approve.disabled=!!ctx.busy||!draft.approvable;
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
  if(draft.status==='approved'&&draft.kind==='formula')card.append(el('p','公式卡已入库；计算规划目前只用已支持的公式，这张卡先作资料与检索使用。','hint'));
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
 const top=el('div',undefined,'lib-top');top.append(docs,sections);
 host.replaceChildren(...(ctx.message?[el('p',ctx.message,'lib-message')]:[]),top,drafts,modulationSection(ctx));
}
