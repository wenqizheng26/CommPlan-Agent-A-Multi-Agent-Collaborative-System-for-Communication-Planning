import {parameterNames,toolNames} from './details.mjs';
import {originLabel,comparisonPresentation} from './m1.mjs';
import {relevantEvents} from './flow.mjs';
import {roleModeNames} from './roles.mjs';

const NONE='无';
const textOrNull=value=>typeof value==='string'&&value.trim()?value:null;
const names={...parameterNames,modulation:'调制方式',rx_sensitivity_dbm:'接收灵敏度',required_margin_db:'要求余量',
 sensitivity_source:'灵敏度来源',simulated:'模拟参数',meets:'是否满足'};
const units={path_loss_db:'dB',rx_power_dbm:'dBm',rx_sensitivity_dbm:'dBm',link_margin_db:'dB'};
const number=value=>typeof value==='number'&&Number.isFinite(value);
const LABEL_SOURCE='原文 · 只作标签，不参与计算';
const SITE_SOURCE='名称来自原文';
const FSPL_MHZ_NOTE='路径损耗按 MHz 形式计算，常数取 32.44；与 GHz 形式（常数 92.4）相比，同一条链路的结果约高 0.04 dB。';
const display=(value,id='meets')=>value==null?NONE:number(value)?value.toFixed(2):typeof value==='boolean'?
 (id==='meets'?(value?'满足':'不满足'):(value?'是':'否')):String(value);
const unitFor=name=>name.endsWith('_dbm')?'dBm':name.endsWith('_dbi')?'dBi':name.endsWith('_db')?'dB':name.endsWith('_mhz')?'MHz':name.endsWith('_ghz')?'GHz':name.endsWith('_km')?'km':name.endsWith('_m')?'m':name.endsWith('_deg')?'°':'';
const parameters=inputs=>Object.entries(inputs||{}).map(([id,value])=>({id,name:names[id]||id,
 value:id==='sensitivity_source'?({modulation_table:'调制表 · 模拟参数',argument:'调用参数'}[value]||value):value,
 raw_value:id!=='sensitivity_source',unit:unitFor(id)}));

function toolsFor(state){
 const calls=state.final_report?.tool_calls;
 if(calls?.length)return calls.map(call=>({tool:call.tool,name:toolNames[call.tool]||(call.tool==='calc_link_margin'?'链路余量计算':call.tool),
  label:call.label||'',status:call.status,inputs:parameters(call.arguments),outputs:parameters(call.result)}));
 if(state.result?.steps?.length)return state.result.steps.map(step=>({tool:step.tool_id,name:toolNames[step.tool_id]||step.tool_id,
  label:'',inputs:parameters(step.inputs),outputs:[{id:step.output?.name,name:names[step.output?.name]||step.output?.name||NONE,
   value:step.output?.value,unit:step.output?.unit||''}]}));
 // Earlier single-formula states have normalized_inputs and outputs, but no steps.
 const result=state.result;
 if(!result)return [];
 return [{tool:result.model_id,name:toolNames[result.model_id]||result.model_id||NONE,label:'',
  inputs:parameters(result.normalized_inputs),outputs:(result.outputs||[]).map(output=>({id:output.name,
   name:names[output.name]||output.name,value:output.value,unit:output.unit||''}))}];
}

function resultsFor(state){
 const final=state.final_report||{},result=state.result||{},calls=final.tool_calls||[];
 const metrics=(values,label='')=>['path_loss_db','rx_power_dbm','rx_sensitivity_dbm','link_margin_db'].map(id=>({id,
  name:id==='rx_sensitivity_dbm'?'接收灵敏度':names[id],value:values[id],unit:units[id],label}));
 if(calls.length)return calls.flatMap(call=>{
  const values=call.result||{},required=values.required_margin_db??final.requirement?.value??0;
  return [...metrics(values,call.label),{id:'required_margin_db',name:'要求余量',value:required,unit:'dB',label:call.label},
   {id:'meets',name:'是否满足',value:number(values.link_margin_db)&&number(required)?values.link_margin_db>=required:null,unit:'',label:call.label}];
 });
 const outputs=[...(final.outputs||[]),...(result.outputs||[]),...(result.steps||[]).map(s=>s.output).filter(Boolean)];
 const find=id=>outputs.find(o=>o.name===id)?.value;
 const threshold=result.steps?.find(s=>s.tool_id==='link_margin')?.inputs?.rx_threshold_dbm??result.normalized_inputs?.rx_threshold_dbm;
 const values={path_loss_db:find('path_loss_db'),rx_power_dbm:find('rx_power_dbm'),rx_sensitivity_dbm:threshold,link_margin_db:find('link_margin_db')};
 const required=final.requirement?.value??result.requirement?.value??state.report?.calculation_plan_proposal?.requirement?.value??0;
 return [...metrics(values),{id:'required_margin_db',name:'要求余量',value:number(values.link_margin_db)?required:null,unit:'dB',label:''},
  {id:'meets',name:'是否满足',value:number(values.link_margin_db)&&number(required)?values.link_margin_db>=required:null,unit:'',label:''}];
}

function comparisonFor(comparison){
 const view=comparisonPresentation(comparison);
 if(!view)return null;
 // Keep the shared presentation and add the teacher's FSPL column to the report.
 return {...view,head:[...view.head.slice(0,2),'路径损耗 dB',...view.head.slice(2)],
  rows:view.rows.map((row,i)=>({...row,cells:[...row.cells.slice(0,2),display(comparison.rows[i].path_loss_db),...row.cells.slice(2)]}))};
}

function metadataFor(state,events,tools){
 const current=relevantEvents(state,events),final=state.final_report||{},toolEvents=current.filter(e=>e.node==='tool'&&e.phase==='completed');
 const models=[...new Set(current.filter(e=>e.node==='llm').map(e=>e.details?.model_id).filter(Boolean))];
 const modes={...state.report?.component_modes,...final.component_modes};
 const modelModes=Object.entries(modes).filter(([key])=>['interpretation','calculation','review','suggestion','supplement'].includes(key));
 const deterministic=state.mode==='deterministic'||modelModes.length>0&&modelModes.every(([,mode])=>mode==='deterministic');
 return {task_id:state.task_id??null,revision:state.revision??null,
  completed_at:final.generated_at||state.result?.finished_at||null,
  models:models.length?models:deterministic?['确定性模式（无模型调用）']:modelModes.map(([key,mode])=>`${key}: ${roleModeNames[mode]||mode}`),
  model_calls:current.length?current.filter(e=>e.node==='llm'&&e.phase==='started').length:deterministic?0:null,
  // States from before the tool events logged formula steps as node 'model'; count their saved calls instead.
  tool_calls:toolEvents.length?toolEvents.length:tools.length,
  count_note:!current.length?'没有活动记录，工具次数按保存的调用记录统计。':toolEvents.length?'调用次数按当前版本的活动事件统计；模型重试不单独计数。':
   '模型调用按当前版本的活动事件统计；工具次数按保存的调用记录统计。'};
}

// Pure projection of the saved state. Events/context are optional for historical states.
export function reportModel(state,events=[],{facts={},cards={}}={}){
 const s=state||{},final=s.final_report||{},text=s.request?.raw_text||'';
 const parsed=(s.report?.parameters_proposal||[]).map(parameter=>{
  const origin=originLabel(parameter,facts,cards,text);
  return {id:parameter.canonical_name,name:names[parameter.canonical_name]||parameter.canonical_name,
   value:parameter.value,unit:parameter.unit||'',source:origin.tag,source_kind:origin.kind,
   source_note:origin.kind==='suggested'?'默认补全，需确认':null,
   simulated:origin.kind==='modulation'||origin.tag.includes('模拟')};
 });
 const missing=(s.resolved_input_issues||[]).filter(issue=>issue.kind==='missing').map(issue=>({
  id:issue.id,field:issue.field,title:issue.title||names[issue.field]||issue.field||NONE,
  answer:issue.answer??null}));
 const answers=(s.conversation?.turns||[]).filter(turn=>turn.kind==='answer'&&turn.mode==='suggestion')
  .flatMap(turn=>(turn.answers||[]).map(answer=>({id:answer.issue_id,title:answer.title||NONE,
   answer:answer.display??answer.answer??null})));
 const tools=toolsFor(s),service=s.report?.service;
 const labels={sites:(s.report?.entities||[]).filter(e=>e.kind==='site').map(e=>e.mention),
  service:service?{kind:service.kind,label:service.label,mention:service.mention}:null};
 return {original_input:textOrNull(s.conversation?.original_input?.raw_text)||textOrNull(s.request?.raw_text),
  parameters:parsed,labels,completion:{missing,answers},tool_calls:tools,results:resultsFor(s),
  comparison:comparisonFor(final.comparison),explanation:{answer:textOrNull(final.answer?.text),
   steps:(final.explanation||[]).map(step=>({id:step.id,text:textOrNull(step.note??step.text)})),
   opinions:(final.review?.opinions||[]).map(opinion=>({kind:opinion.kind,text:textOrNull(opinion.text)}))},
  metadata:{...metadataFor(s,events,tools),fspl_mhz:usesMhzLoss(s)}};
}

function usesMhzLoss(state){
 return (state.final_report?.tool_calls||[]).some(call=>(call.steps||[]).some(step=>step.card==='fspl_mhz'))||
  [...(state.final_report?.steps||[]),...(state.result?.steps||[])].some(step=>step.tool_id==='fspl_mhz');
}

// Site names come from the text (report.entities); a name the site library knows may supply coordinates.
// The service (report.service) is only a label and never a calculation input.
function labelRows(labels){
 const rows=[];
 if(labels?.sites?.length)rows.push({id:'sites',name:'站点',value:labels.sites.join('、'),unit:'',source:SITE_SOURCE});
 if(labels?.service)rows.push({id:'service',name:'业务',value:labels.service.label,raw_value:false,unit:'',source:LABEL_SOURCE});
 return rows;
}

function el(tag,text,className){
 const node=document.createElement(tag);
 if(text!=null)node.textContent=String(text);
 if(className)node.className=className;
 return node;
}
function cell(text,raw=false){return {text:text??NONE,raw:raw&&text!=null};}
function rawNode(tag,text,className){
 const node=el(tag,text??NONE,className);
 if(text!=null)node.setAttribute('translate','no');
 return node;
}
function table(head,rows){
 const wrap=el('div',null,'report-table-wrap'),node=el('table',null,'report-table'),thead=el('thead'),tr=el('tr');
 for(const name of head){const th=el('th',name);th.scope='col';tr.append(th);}thead.append(tr);node.append(thead);
 const body=el('tbody');
 for(const row of rows){const line=el('tr');for(const value of row){const data=typeof value==='object'&&value!==null?value:cell(value);
  line.append(data.raw?rawNode('td',data.text):el('td',data.text));}body.append(line);}node.append(body);wrap.append(node);return wrap;
}
function section(host,title){const node=el('section',null,'report-section');node.append(el('h2',title));host.append(node);return node;}
const empty=host=>host.append(el('p',NONE,'report-empty'));
function paramTable(host,rows,source=false){
 if(!rows.length){empty(host);return;}
 host.append(table(source?['参数','值','单位','来源']:['参数','值','单位'],rows.map(row=>[
  row.name,cell(display(row.value,row.id),row.raw_value!==false&&row.value!=null&&typeof row.value==='string'),row.unit||NONE,
  ...(source?[row.source_note||row.source]:[])])));
 if(rows.some(row=>row.simulated))host.append(el('p','模拟参数，可配置','hint'));
}

export function renderReportDocument(host,model){
 host.replaceChildren();host.append(el('h1','通信筹划报告'));
 const original=section(host,'原始输入');original.append(rawNode('p',model.original_input,'report-raw'));
 paramTable(section(host,'解析字段'),[...model.parameters,...labelRows(model.labels)],true);
 const completion=section(host,'缺失项与补全');
 if(!model.completion.missing.length&&!model.completion.answers.length)empty(completion);
 if(model.completion.missing.length){completion.append(el('h3','缺失项'));completion.append(table(['缺失项'],model.completion.missing.map(issue=>[issue.title])));}
 if(model.completion.answers.length){completion.append(el('h3','采用默认补全'));completion.append(table(['缺失项','补全回答'],model.completion.answers.map(answer=>[answer.title,cell(answer.answer,true)])));}
 const calls=section(host,'工具调用参数');
 if(!model.tool_calls.length)empty(calls);
 for(const call of model.tool_calls){const article=el('article',null,'report-call');article.append(el('h3',call.name));
  if(call.label)article.append(rawNode('p',call.label));article.append(el('h4','调用参数'));paramTable(article,call.inputs);
  article.append(el('h4','调用结果'));paramTable(article,call.outputs);calls.append(article);}
 const results=section(host,'计算结果');
 if(model.results.every(row=>row.value==null))empty(results);
 else results.append(table(['调制','参数','值','单位'],model.results.map(row=>[cell(row.label||NONE,!!row.label),row.name,display(row.value),row.value==null?NONE:row.unit||NONE])));
 const comparison=section(host,'对比表');
 if(!model.comparison)empty(comparison);
 else {comparison.append(table(model.comparison.head,model.comparison.rows.map(row=>row.cells)));comparison.append(el('p',model.comparison.summary),el('p',model.comparison.note,'hint'));}
 const explanation=section(host,'模型解释');explanation.append(rawNode('p',model.explanation.answer,'report-raw'));
 for(const [title,rows] of [['步骤说明',model.explanation.steps],['审查意见',model.explanation.opinions]]){
  explanation.append(el('h3',title));if(!rows.length)empty(explanation);
  for(const row of rows)explanation.append(rawNode('p',row.text,'report-raw'));
 }
 const meta=section(host,'附注'),list=el('dl',null,'report-meta');
 const data=model.metadata;
 for(const [name,value,raw] of [['任务编号',data.task_id,true],['版本',data.revision,false],['完成时间',data.completed_at,true],
  ['模型名',data.models.join(' · ')||null,false],['模型调用次数',data.model_calls,false],['工具计算次数',data.tool_calls,false]]){
  list.append(el('dt',name),raw?rawNode('dd',value):el('dd',value??NONE));
 }
 meta.append(list,el('p',data.count_note,'hint'));
 if(data.fspl_mhz)meta.append(el('p',FSPL_MHZ_NOTE,'hint'));
}

const panels=new WeakMap();
// Keep a stable panel/button while the existing workbench polls activity.
export function renderReport(host,button,state,events=[],context={}){
 if(!host||!button)return;
 let view=panels.get(host);
 if(!view){
  const toolbar=el('div',null,'report-toolbar'),title=el('h2','报告');title.id='report-title';
  const actions=el('div',null,'report-actions'),print=el('button','打印 / 存为 PDF','primary'),close=el('button','关闭报告','secondary');
  print.type=close.type='button';actions.append(print,close);toolbar.append(title,actions);
  const document=el('article',null,'report-document');host.replaceChildren(toolbar,document);
  view={document,close,model:null,key:null,signature:null,open:false};panels.set(host,view);
  const dismiss=()=>{view.open=false;host.hidden=true;button.setAttribute('aria-expanded','false');globalThis.document.body.classList.remove('report-print-ready');button.focus();};
  button.addEventListener('click',()=>{if(button.hidden||!view.model)return;view.open=true;host.hidden=false;button.setAttribute('aria-expanded','true');
   globalThis.document.body.classList.add('report-print-ready');renderReportDocument(document,view.model);host.scrollTop=0;close.focus();});
  close.addEventListener('click',dismiss);view.dismiss=dismiss;
  print.addEventListener('click',()=>{if(view.open)window.print();});
  host.addEventListener('keydown',event=>{
   if(event.key==='Escape'){event.preventDefault();dismiss();}
   if(event.key==='Tab'){event.preventDefault();(globalThis.document.activeElement===close?print:close).focus();}
  });
 }
 const key=state?.status==='COMPLETED'?`${state.task_id}:${state.revision}`:null;
 button.hidden=!key;
 if(key!==view.key){if(view.open)view.dismiss();view.key=key;view.signature=null;}
 if(!key){view.model=null;return;}
 const model=reportModel(state,events,context),signature=JSON.stringify(model);view.model=model;
 if(view.open&&signature!==view.signature)renderReportDocument(view.document,model);
 view.signature=signature;
}
