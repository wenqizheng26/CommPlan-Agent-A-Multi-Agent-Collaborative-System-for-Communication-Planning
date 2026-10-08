import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {reportModel,renderReportDocument,renderReport} from '../planning/web/report.mjs';
import {originLabel,comparisonPresentation} from '../planning/web/m1.mjs';
import {install,t} from '../planning/web/i18n.mjs';
import * as en from '../planning/web/i18n-en.mjs';

const fixture=name=>JSON.parse(readFileSync(new URL(`./fixtures/teacher_report/${name}.json`,import.meta.url),'utf8'));
const readJson=path=>JSON.parse(readFileSync(new URL(path,import.meta.url),'utf8'));
const teacherCases=readFileSync(new URL('./eval/teacher_cases.jsonl',import.meta.url),'utf8').trim().split(/\r?\n/).map(line=>JSON.parse(line));
const facts=Object.fromEntries(['devices','sites','modulations'].flatMap(name=>readJson(`../knowledge/facts/${name}.json`)).map(row=>[row.id,row]));
const cards=Object.fromEntries(readJson('../knowledge/formulas.json').map(card=>[card.id,card]));
const context={facts,cards};
const modelFor=name=>{const f=fixture(name);return reportModel(f.state,f.events,context);};
const metric=(model,id,label='')=>model.results.find(row=>row.id===id&&row.label===label)?.value;
const near=(actual,expected)=>assert.ok(Math.abs(actual-expected)<1e-9,`${actual} differs from ${expected}`);

class Element {
 constructor(tag){this.tag=tag;this.children=[];this.textContent='';this.attributes={};this.handlers={};this.hidden=false;
  const classes=new Set();this.classList={add:value=>classes.add(value),remove:value=>classes.delete(value),contains:value=>classes.has(value)};}
 append(...children){for(const child of children){child.remove?.();child.parent=this;this.children.push(child);}}
 replaceChildren(...children){for(const child of this.children)child.parent=null;this.children=[];this.append(...children);}
 setAttribute(name,value){this.attributes[name]=String(value);}
 addEventListener(name,handler){this.handlers[name]=handler;}
 remove(){if(!this.parent)return;this.parent.children=this.parent.children.filter(child=>child!==this);this.parent=null;}
 focus(){globalThis.document.activeElement=this;}
 click(){this.handlers.click?.();}
}
const walk=node=>[node,...node.children.flatMap(walk)];
const leafText=host=>walk(host).filter(node=>node.textContent).map(node=>node.textContent);
const named=(host,text)=>walk(host).find(node=>node.textContent===text);
function withDOM(run){
 const previousDocument=globalThis.document,previousWindow=globalThis.window;
 globalThis.document={createElement:tag=>new Element(tag),body:new Element('body'),activeElement:null};
 let prints=0;globalThis.window={print:()=>prints++};
 try{return run(()=>prints);}finally{globalThis.document=previousDocument;globalThis.window=previousWindow;}
}
const eventFor=(state,node,phase,details={},extra={})=>({task_id:state.task_id,revision:state.revision,node,phase,details,...extra});

test('captured completed states retain deterministic provenance and commands',()=>{
 for(const name of ['margin','comparison','defaults']){
  const f=fixture(name);
  assert.equal(f.state.status,'COMPLETED',name);
  assert.ok(f.provenance,name);
  assert.ok(f.commands.some(command=>command.action==='create'&&command.mode==='deterministic'),name);
  assert.ok(f.commands.some(command=>command.action==='confirm'),name);
  assert.ok(f.events.some(event=>event.node==='tool'&&event.phase==='completed'),name);
 }
});

test('the report retains the original conversation input before later supplemented request text',()=>{
 const f=fixture('defaults'),before=JSON.stringify(f),model=reportModel(f.state,f.events,context);
 assert.equal(model.original_input,f.state.conversation.original_input.raw_text);
 assert.notEqual(model.original_input,f.state.request.raw_text);
 assert.equal(model.original_input,teacherCases.find(row=>row.id==='teacher_02').text);
 assert.equal(JSON.stringify(f),before,'pure projection must leave state and events intact');
});

test('request text is the legacy fallback and absent input remains missing',()=>{
 const f=fixture('margin'),state=structuredClone(f.state);delete state.conversation;
 assert.equal(reportModel(state).original_input,state.request.raw_text);
 state.conversation={original_input:{raw_text:''}};
 assert.equal(reportModel(state).original_input,state.request.raw_text);
 state.request.raw_text='';assert.equal(reportModel(state).original_input,null);
 assert.equal(reportModel({}).original_input,null);
 assert.equal(reportModel(null).original_input,null);
});

test('real parsed parameters reuse the shared origin labels, values and units',()=>{
 for(const name of ['margin','comparison','defaults']){
  const f=fixture(name),model=reportModel(f.state,f.events,context);
  assert.equal(model.parameters.length,f.state.report.parameters_proposal.length);
  for(const [index,param] of f.state.report.parameters_proposal.entries()){
   const shown=model.parameters[index],origin=originLabel(param,facts,cards,f.state.request.raw_text);
   assert.equal(shown.id,param.canonical_name);assert.equal(shown.value,param.value);assert.equal(shown.unit,param.unit);
   assert.equal(shown.source,origin.tag);assert.equal(shown.source_kind,origin.kind);assert.ok(shown.name);
  }
 }
});

test('modulation sensitivity and adopted default sources visibly retain their confirmation and simulation notes',()=>withDOM(()=>{
 const comparison=modelFor('comparison'),defaults=modelFor('defaults');
 assert.ok(comparison.parameters.some(param=>param.source_kind==='modulation'&&param.simulated));
 assert.ok(defaults.parameters.filter(param=>param.source_kind==='suggested').length>=4);
 assert.ok(defaults.parameters.filter(param=>param.source_kind==='suggested').every(param=>param.source_note==='默认补全，需确认'));
 const host=new Element('article');renderReportDocument(host,defaults);
 assert.ok(leafText(host).includes('默认补全，需确认'));
 assert.ok(leafText(host).includes('模拟参数，可配置'));
}));

test('teacher 02 preserves every real resolved missing field and the round that adopted all defaults',()=>{
 const f=fixture('defaults'),model=modelFor('defaults');
 const missing=f.state.resolved_input_issues.filter(issue=>issue.kind==='missing');
 assert.deepEqual(new Set(missing.map(issue=>issue.field)),new Set(['distance_km','tx_power_dbm','tx_gain_dbi','rx_gain_dbi']));
 assert.equal(model.completion.missing.length,4);
 for(const [index,issue] of missing.entries()){
  assert.equal(model.completion.missing[index].id,issue.id);
  assert.equal(model.completion.missing[index].field,issue.field);
  assert.equal(model.completion.missing[index].answer,issue.answer??null);
 }
 const answers=f.state.conversation.turns.filter(turn=>turn.kind==='answer'&&turn.mode==='suggestion').flatMap(turn=>turn.answers);
 assert.equal(answers.length,5);assert.equal(model.completion.answers.length,5);
 for(const [index,answer] of answers.entries()){
  assert.equal(model.completion.answers[index].id,answer.issue_id);
  assert.equal(model.completion.answers[index].answer,answer.display??answer.answer??null);
 }
 assert.equal(metric(model,'rx_sensitivity_dbm','QPSK'),-100);
 near(metric(model,'path_loss_db','QPSK'),32.44+20*Math.log10(10)+20*Math.log10(5800));
});

test('the real MARGIN chain has three tools, their real inputs and independently computed results',()=>{
 const f=fixture('margin'),model=modelFor('margin');
 assert.deepEqual(model.tool_calls.map(call=>call.tool),['fspl_ghz','received_power','link_margin']);
 for(const [index,call] of model.tool_calls.entries()){
  const step=f.state.result.steps[index];
  assert.deepEqual(Object.fromEntries(call.inputs.map(param=>[param.id,param.value])),step.inputs);
  assert.equal(call.outputs[0].id,step.output.name);assert.equal(call.outputs[0].value,step.output.value);
  assert.equal(call.outputs[0].unit,step.output.unit);
 }
 const fspl=92.4+20*Math.log10(2)+20*Math.log10(10),power=30+10+10-2-2-fspl;
 near(metric(model,'path_loss_db'),fspl);near(metric(model,'rx_power_dbm'),power);
 assert.equal(metric(model,'rx_sensitivity_dbm'),-100);near(metric(model,'link_margin_db'),power+100-10);
 assert.equal(metric(model,'meets'),true);
 assert.deepEqual(model.completion,{missing:[],answers:[]});assert.equal(model.comparison,null);
});

test('required margin controls whether a real completed chain satisfies the requirement',()=>{
 const f=fixture('margin'),state=structuredClone(f.state),margin=metric(modelFor('margin'),'link_margin_db');
 state.final_report.requirement={value:margin};assert.equal(metric(reportModel(state),'meets'),true);
 state.final_report.requirement={value:margin+0.01};assert.equal(metric(reportModel(state),'meets'),false);
 state.final_report.requirement={value:margin-0.01};assert.equal(metric(reportModel(state),'meets'),true);
 const composite=structuredClone(fixture('comparison').state);
 for(const call of composite.final_report.tool_calls){call.result.required_margin_db=30;call.result.meets=true;}
 assert.ok(reportModel(composite).results.filter(row=>row.id==='meets').every(row=>row.value===false));
});

test('teacher 03 uses two real composite calls and shows every teacher result column, spread and recommendation',()=>{
 const f=fixture('comparison'),model=modelFor('comparison'),saved=f.state.final_report.comparison;
 assert.deepEqual(model.tool_calls.map(call=>[call.tool,call.label]),[['calc_link_margin','QPSK'],['calc_link_margin','16QAM']]);
 const fspl=32.44+20*Math.log10(8)+20*Math.log10(2400),power=17+12+12-fspl;
 for(const [label,sensitivity] of [['QPSK',-100],['16QAM',-95]]){
  near(metric(model,'path_loss_db',label),fspl);near(metric(model,'rx_power_dbm',label),power);
  assert.equal(metric(model,'rx_sensitivity_dbm',label),sensitivity);near(metric(model,'link_margin_db',label),power-sensitivity);
  assert.equal(metric(model,'meets',label),true);
  const call=model.tool_calls.find(call=>call.label===label),raw=f.state.final_report.tool_calls.find(call=>call.label===label);
  assert.deepEqual(Object.fromEntries(call.inputs.map(param=>[param.id,param.value])),raw.arguments);
  assert.deepEqual(new Set(call.outputs.map(param=>param.id)),new Set(Object.keys(raw.result)));
  for(const param of call.outputs){
   if(param.id==='sensitivity_source')assert.equal(param.value,'调制表 · 模拟参数');
   else assert.equal(param.value,raw.result[param.id]);
  }
 }
 const shared=comparisonPresentation(saved);
 assert.equal(model.comparison.head.length,6);assert.equal(model.comparison.rows.length,2);
 assert.deepEqual(model.comparison.head,['调制','灵敏度 dBm','路径损耗 dB','接收电平 dBm','余量 dB','满足']);
 assert.deepEqual(model.comparison.rows.map(row=>row.cells),[
  ['QPSK','-100','118.11','-77.11','22.89','满足'],['16QAM','-95','118.11','-77.11','17.89','满足']]);
 assert.equal(model.comparison.summary,shared.summary);assert.equal(model.comparison.note,shared.note);
 assert.equal(model.comparison.summary,'相差 5.00 dB · 推荐 QPSK（余量最大）');
});

test('single FSPL legacy output needs no steps and does not invent received power or a success decision',()=>withDOM(()=>{
 const f=fixture('fspl_legacy'),model=modelFor('fspl_legacy');
 assert.equal(model.tool_calls.length,1);assert.equal(model.tool_calls[0].tool,'fspl_ghz');
 assert.ok(model.tool_calls[0].inputs.length);near(metric(model,'path_loss_db'),92.4+20*Math.log10(2)+20*Math.log10(1));
 for(const id of ['rx_power_dbm','rx_sensitivity_dbm','link_margin_db','required_margin_db','meets'])assert.ok(metric(model,id)==null,id);
 const host=new Element('article');renderReportDocument(host,model);
 assert.ok(leafText(host).includes('98.42'));assert.ok(leafText(host).includes('无'));
}));

test('all eight sections render missing historical data as None without throwing',()=>withDOM(()=>{
 const host=new Element('article');renderReportDocument(host,reportModel({}));
 assert.deepEqual(walk(host).filter(node=>node.tag==='h2').map(node=>node.textContent),[
  '原始输入','解析字段','缺失项与补全','工具调用参数','计算结果','对比表','模型解释','附注']);
 assert.ok(leafText(host).filter(text=>text==='无').length>=8);
}));

test('saved model answer, step notes and opinions are projected as original wording',()=>{
 const f=fixture('margin'),state=structuredClone(f.state);
 const answer='结论原话 <em>118.42 dB</em> 不要翻译。',step='步骤原话：按已确认输入计算。',opinion='审查原话：该模拟参数需确认。';
 state.final_report.answer={text:answer};state.final_report.explanation=[{id:'fspl',note:step}];
 state.final_report.review={opinions:[{kind:'risk',text:opinion}]};
 const model=reportModel(state);
 assert.equal(model.explanation.answer,answer);assert.equal(model.explanation.steps[0].text,step);
 assert.equal(model.explanation.opinions[0].kind,'risk');assert.equal(model.explanation.opinions[0].text,opinion);
});

test('metadata counts only model starts and tool completions for the current task and revision',()=>{
 const f=fixture('margin'),state=f.state;
 const events=[...f.events,eventFor(state,'llm','started',{model_id:'local-first',purpose:'intent'}),
  eventFor(state,'llm','completed',{model_id:'local-first'}),eventFor(state,'llm','started',{model_id:'local-review',purpose:'validator_agent'}),
  eventFor(state,'llm','failed',{model_id:'local-review',reason:'timeout'}),
  eventFor(state,'llm','started',{model_id:'excluded'},{revision:state.revision+1}),
  eventFor(state,'tool','completed',{}, {task_id:'another-task'})];
 const model=reportModel(state,events);
 assert.equal(model.metadata.task_id,state.task_id);assert.equal(model.metadata.revision,state.revision);
 assert.equal(model.metadata.completed_at,state.final_report.generated_at);
 assert.deepEqual(model.metadata.models,['local-first','local-review']);assert.equal(model.metadata.model_calls,2);
 assert.equal(model.metadata.tool_calls,3);
});

test('absent event history falls back to saved tool calls and keeps unknown model counts unknown',()=>{
 const composite=structuredClone(fixture('comparison').state);
 delete composite.mode;delete composite.report.component_modes;delete composite.final_report.component_modes;
 const model=reportModel(composite,[]);
 assert.equal(model.metadata.tool_calls,2);assert.equal(model.metadata.model_calls,null);
 assert.deepEqual(model.metadata.models,[]);
 const deterministic=reportModel(fixture('margin').state,[]);
 assert.equal(deterministic.metadata.model_calls,0);assert.ok(deterministic.metadata.models[0].includes('确定性'));
});

test('the existing report notes visibly retain the modulation document title, version, locator and simulated source',()=>withDOM(()=>{
 const state=structuredClone(fixture('comparison').state);
 const record=readJson('../knowledge/documents/manifest.json').documents.find(row=>row.doc_id==='sim-modulation');
 const locator='调制方式与接收灵敏度 / 同误码率要求下的信噪比与接收灵敏度, chunk 1';
 state.final_report.document_evidence=[{id:'doc:sim-modulation:s2-1',title:record.title,
  source:{doc_id:record.doc_id,uri:record.source,version:record.version,locator,sha256:record.sha256,simulated:record.simulated}}];
 const before=JSON.stringify(state),model=reportModel(state),host=new Element('article');renderReportDocument(host,model);
 assert.equal(JSON.stringify(state),before);
 const notes=walk(host).find(node=>node.tag==='section'&&node.children.some(child=>child.textContent==='附注'));
 for(const text of ['文档依据',record.title,record.version,locator,'模拟数据',record.source])assert.ok(leafText(notes).includes(text),text);
 assert.equal(walk(notes).some(node=>node.tag==='a'),false,'local knowledge paths must remain literal text');
 assert.equal(walk(host).filter(node=>node.tag==='section').length,8,'no report section or layout is added');
}));

test('document references keep their wording literal and link only valid http or https source URLs',()=>withDOM(()=>{
 const state=structuredClone(fixture('comparison').state),title='<img src=x onerror=alert(1)> 出处原话';
 state.final_report.document_evidence=[{id:'doc:unsafe:1',title,source:{uri:'javascript:alert(1)',version:'v1',locator:'<script>bad()</script>',simulated:false}},
  {id:'doc:remote:1',title:'ITU document',source:{uri:'https://www.itu.int/rec/R-REC-P.525/en',version:'P.525',locator:'section 2',simulated:false}},
  {id:'doc:invalid:1',title:'Bad URL',source:{uri:'https://',version:'v1',locator:'section 1',simulated:false}}];
 const host=new Element('article');renderReportDocument(host,reportModel(state));
 assert.ok(named(host,title));assert.equal(named(host,title).attributes.translate,'no');
 assert.ok(named(host,'<script>bad()</script>'));
 assert.equal(walk(host).some(node=>node.tag==='img'||node.tag==='script'),false);
 const links=walk(host).filter(node=>node.tag==='a');assert.equal(links.length,1);
 assert.equal(links[0].href,'https://www.itu.int/rec/R-REC-P.525/en');assert.equal(links[0].rel,'noopener noreferrer');
 assert.equal(links[0].target,'_blank');
}));

test('states from before the tool events count their saved calls, not zero',()=>{
 // Older runs logged formula steps as node 'model', so the revision has events but no tool events.
 const f=fixture('margin'),state=f.state;
 const events=[...f.events.filter(e=>e.node!=='tool'),eventFor(state,'llm','started',{model_id:'local-first'}),
  eventFor(state,'model','started',{}),eventFor(state,'model','completed',{})];
 const model=reportModel(state,events);
 assert.equal(model.metadata.tool_calls,3);assert.equal(model.metadata.model_calls,1);
 assert.ok(model.metadata.count_note.includes('保存的调用记录'));
});

test('user and model text is safe literal content marked translate=no, including completion answers',()=>withDOM(()=>{
 const state=structuredClone(fixture('defaults').state),payload='<img src=x onerror=alert(1)> 用户原文';
 state.conversation.original_input.raw_text=payload;state.final_report.answer={text:'<script>alert(1)</script> 模型原话'};
 state.final_report.explanation=[{id:'x',note:'步骤原话'}];state.final_report.review={opinions:[{kind:'risk',text:'意见原话'}]};
 const host=new Element('article'),model=reportModel(state);renderReportDocument(host,model);
 for(const text of [payload,state.final_report.answer.text,'步骤原话','意见原话',...model.completion.answers.map(answer=>answer.answer)]){
  const node=named(host,text);assert.ok(node,text);assert.equal(node.attributes.translate,'no',text);
 }
 assert.equal(walk(host).some(node=>node.tag==='img'||node.tag==='script'),false);
}));

test('system completion titles are translatable while adopted answers retain their recorded wording',()=>withDOM(()=>{
 install(en);const model=modelFor('defaults'),host=new Element('article');renderReportDocument(host,model);
 for(const title of new Set([...model.completion.missing,...model.completion.answers].map(item=>item.title))){
  const nodes=walk(host).filter(node=>node.textContent===title);assert.ok(nodes.length,title);
  for(const node of nodes)assert.notEqual(node.attributes.translate,'no',title);
  assert.doesNotMatch(t(title),/[\u3400-\u9fff]/u,title);
 }
 for(const answer of model.completion.answers){const node=named(host,answer.answer);assert.ok(node,answer.answer);assert.equal(node.attributes.translate,'no');}
}));

test('empty original and model strings display None rather than blank protected paragraphs',()=>withDOM(()=>{
 const state=structuredClone(fixture('margin').state);state.conversation.original_input.raw_text='';state.request.raw_text='';
 state.final_report.answer={text:''};state.final_report.explanation=[{id:'empty',note:''}];state.final_report.review={opinions:[{kind:'risk',text:''}]};
 const model=reportModel(state);assert.equal(model.original_input,null);assert.equal(model.explanation.answer,null);
 assert.equal(model.explanation.steps[0].text,null);assert.equal(model.explanation.opinions[0].text,null);
 const host=new Element('article');renderReportDocument(host,model);
 const sections=walk(host).filter(node=>node.tag==='section');
 for(const index of [0,6])assert.ok(leafText(sections[index]).includes('无'));
 assert.equal(walk(host).some(node=>node.attributes.translate==='no'&&node.textContent===''),false);
}));

test('the completed-only report opens, prints, traps keyboard focus and closes back to its button',()=>withDOM(printCount=>{
 const f=fixture('margin'),host=new Element('section'),button=new Element('button');host.hidden=true;
 renderReport(host,button,{...f.state,status:'AWAITING_CONFIRMATION'},f.events);assert.equal(button.hidden,true);
 button.click();assert.equal(host.hidden,true);assert.equal(printCount(),0);
 renderReport(host,button,f.state,f.events);assert.equal(button.hidden,false);button.click();
 assert.equal(host.hidden,false);assert.equal(button.attributes['aria-expanded'],'true');
 assert.ok(document.body.classList.contains('report-print-ready'));
 const print=named(host,'打印 / 存为 PDF'),close=named(host,'关闭报告');assert.equal(document.activeElement,close);
 print.click();assert.equal(printCount(),1);
 let prevented=0;host.handlers.keydown({key:'Tab',preventDefault:()=>prevented++});assert.equal(document.activeElement,print);
 host.handlers.keydown({key:'Tab',shiftKey:true,preventDefault:()=>prevented++});assert.equal(document.activeElement,close);
 host.handlers.keydown({key:'Escape',preventDefault:()=>prevented++});assert.equal(prevented,3);
 assert.equal(host.hidden,true);assert.equal(button.attributes['aria-expanded'],'false');assert.equal(document.activeElement,button);
 assert.equal(document.body.classList.contains('report-print-ready'),false);print.click();assert.equal(printCount(),1);
 button.click();close.click();assert.equal(host.hidden,true);
}));

test('polling preserves report controls, while task/revision and completion changes close stale reports',()=>withDOM(()=>{
 const first=fixture('margin'),second=fixture('comparison'),host=new Element('section'),button=new Element('button');host.hidden=true;
 renderReport(host,button,first.state,first.events);button.click();const close=named(host,'关闭报告');
 renderReport(host,button,first.state,first.events);assert.equal(host.hidden,false);assert.equal(named(host,'关闭报告'),close);
 const changed=structuredClone(first.state);changed.final_report.answer={text:'刚保存的解释'};
 renderReport(host,button,changed,first.events);assert.ok(named(host,'刚保存的解释'));assert.equal(host.hidden,false);
 renderReport(host,button,second.state,second.events);assert.equal(host.hidden,true);assert.equal(button.hidden,false);
 button.click();assert.ok(named(host,'118.11'));assert.equal(named(host,'关闭报告'),close);
 renderReport(host,button,{...second.state,revision:second.state.revision+1},second.events);assert.equal(host.hidden,true);
 button.click();renderReport(host,button,{...second.state,status:'FAILED'},second.events);
 assert.equal(host.hidden,true);assert.equal(button.hidden,true);assert.equal(document.body.classList.contains('report-print-ready'),false);
}));

test('every report UI sentence translates fully into English while protected original text stays marked',()=>withDOM(()=>{
 install(en);
 for(const name of ['margin','comparison','defaults','fspl_legacy']){
  const f=fixture(name),host=new Element('section'),button=new Element('button');
  renderReport(host,button,f.state,f.events,context);button.click();
  for(const node of walk(host)){
   if(node.attributes.translate==='no'||!/[\u3400-\u9fff]/u.test(node.textContent))continue;
   const translated=t(node.textContent);assert.notEqual(translated,node.textContent,`${name}: ${node.textContent}`);
   assert.doesNotMatch(translated,/[\u3400-\u9fff]/u,`${name}: ${node.textContent}`);
  }
 }
 const empty=new Element('article');renderReportDocument(empty,reportModel({}));
 for(const node of walk(empty))if(node.attributes.translate!=='no')assert.doesNotMatch(t(node.textContent),/[\u3400-\u9fff]/u,node.textContent);
}));

test('parsed fields show the site names and the named service as labels from the text, not inputs',()=>withDOM(()=>{
 const f=fixture('defaults'),state=structuredClone(f.state),text=state.request.raw_text;
 const span=word=>[text.indexOf(word),text.indexOf(word)+word.length];
 state.report.entities=[{kind:'site',mention:'石家庄山顶基站',span:span('石家庄山顶基站')},{kind:'site',mention:'乡镇',span:span('乡镇')}];
 state.report.service={kind:'video',label:'视频',mention:'传视频',span:span('传视频')};
 const model=reportModel(state,f.events,context);
 assert.deepEqual(model.labels,{sites:['石家庄山顶基站','乡镇'],service:{kind:'video',label:'视频',mention:'传视频'}});
 assert.ok(!model.parameters.some(row=>['sites','service'].includes(row.id)),'labels stay out of the parameters');
 const host=new Element('article');renderReportDocument(host,model);
 const rows=walk(host).filter(node=>node.tag==='tr').map(row=>row.children.map(cell=>cell.textContent));
 assert.deepEqual(rows.find(row=>row[0]==='站点'),['站点','石家庄山顶基站、乡镇','无','名称来自原文']);
 assert.deepEqual(rows.find(row=>row[0]==='业务'),['业务','视频','无','原文 · 只作标签，不参与计算']);
 assert.equal(named(host,'石家庄山顶基站、乡镇').attributes.translate,'no');
 assert.notEqual(named(host,'视频').attributes.translate,'no');
 install(en);
 for(const text of ['站点','业务','视频','原文 · 只作标签，不参与计算','名称来自原文'])assert.doesNotMatch(t(text),/[\u3400-\u9fff]/u,text);
 const older=reportModel(f.state,f.events,context);
 assert.deepEqual(older.labels,{sites:[],service:null},'states saved before the labels show none');
}));

test('the MHz path-loss constant is noted only when the chain used it',()=>withDOM(()=>{
 const note='路径损耗按 MHz 形式计算，常数取 32.44；与 GHz 形式（常数 92.4）相比，同一条链路的结果约高 0.04 dB。';
 for(const [name,shown] of [['comparison',true],['defaults',true],['margin',false],['fspl_legacy',false]]){
  const host=new Element('article');renderReportDocument(host,modelFor(name));
  assert.equal(leafText(host).includes(note),shown,name);
 }
}));
