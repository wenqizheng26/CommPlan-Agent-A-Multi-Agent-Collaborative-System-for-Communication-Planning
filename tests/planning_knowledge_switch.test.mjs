import test from 'node:test';
import assert from 'node:assert/strict';
import {renderLibrary,manualRecord,parseParameters,sourcePayload} from '../planning/web/library.mjs';

const make=tag=>({tag,children:[],textContent:'',className:'',hidden:false,value:'',type:'',append(...children){this.children.push(...children);},replaceChildren(...children){this.children=children;},
 setAttribute(){},addEventListener(){},classList:{toggle(){}}});
const flatten=n=>[n,...(n.children||[]).flatMap(flatten)];
function render(ctx){
 const old=globalThis.document;globalThis.document={createElement:make};
 try{const host=make('div');renderLibrary(host,{chosen:new Set(),drafts:[],facts:{records:[]},forms:{manual:{},model:{}},reviewForms:{},...ctx});return flatten(host);}
 finally{globalThis.document=old;}
}
const doc=(id,extra={})=>({doc_id:id,title:id+' 手册',version:'1',language:'zh',simulated:true,added:false,source:'s',status:'ready',chunks:2,...extra});

test('document switches and delete appear only when the server reports them',()=>{
 const old=render({library:{documents:[doc('a'),doc('b')],formats:[],converter:true},cards:undefined});
 assert.ok(!old.some(n=>n.className==='item-controls'),'an older server keeps the plain rows');
 assert.ok(!old.some(n=>n.textContent==='公式卡'),'no card section without the card library');
 const all=render({library:{documents:[doc('a',{enabled:false}),doc('b',{enabled:true,added:true})],formats:[],converter:true},cards:[]});
 assert.equal(all.filter(n=>n.className==='item-controls').length,2);
 assert.ok(all.some(n=>n.className==='lib-item off'));
 assert.equal(all.filter(n=>n.tag==='button'&&n.textContent==='删除').length,1,'only the added document can be deleted');
 const confirm=render({library:{documents:[doc('b',{enabled:true,added:true})],formats:[],converter:true},cards:[],deleting:'doc:b'});
 assert.ok(confirm.some(n=>n.textContent==='确认删除'));
});

test('cards show what they can be used for and where they came from',()=>{
 const cards=[{id:'fspl_ghz',title:'自由空间',version:'1.0.0',expression:'92.4',output:{name:'path_loss_db',unit:'dB'},sources:[{title:'ITU',locator:'(6)'}],calc:'dedicated',source_kind:'builtin',enabled:true,added:false},
  {id:'x',title:'新卡',version:'1.0.0',expression:'a*b',output:{name:'c',unit:'dB'},sources:[],calc:'generic',source_kind:'manual',enabled:false,added:true},
  {id:'slant',title:'直线距离',version:'1.0.0',expression:null,output:{name:'d',unit:'km'},sources:[],calc:'needs_tool',source_kind:'builtin',enabled:true,added:false}];
 const all=caps=>render({library:{documents:[],formats:[],converter:true},cards,capabilities:caps}).map(n=>n.textContent);
 const texts=all({generic_calculation:true,manual_drafts:true,model_drafts:true});
 for(const t of ['专用程序','通用计算','需专用程序','内置','手填','已停用','新建公式卡','让模型起草'])assert.ok(texts.includes(t),t);
 assert.equal(texts.filter(t=>t==='删除').length,1);
 assert.equal(texts.filter(t=>t==='参与计算').length,2);
});

test('a build without card drafts or generic calculation does not offer them',()=>{
 const cards=[{id:'x',title:'新卡',version:'1.0.0',expression:'a*b',output:{name:'c',unit:'dB'},sources:[],calc:'generic',source_kind:'document',enabled:true,added:true},
  {id:'fspl_ghz',title:'自由空间',version:'1.0.0',expression:'92.4',output:{name:'path_loss_db',unit:'dB'},sources:[],calc:'dedicated',source_kind:'builtin',enabled:true,added:false}];
 for(const capabilities of [undefined,{manual_drafts:false,model_drafts:false}]){
  const texts=render({library:{documents:[],formats:[],converter:true},cards,capabilities,cardForm:'manual'}).map(n=>n.textContent);
  assert.ok(!texts.includes('新建公式卡')&&!texts.includes('让模型起草')&&!texts.includes('提交草稿'),'no draft entry that would answer 404');
  assert.ok(texts.includes('仅作检索')&&!texts.includes('通用计算'));
  assert.deepEqual(texts.filter(t=>t==='参与计算'||t==='参与检索'),['参与检索','参与计算']);
 }
});

test('a hand-written card is checked before it is sent as a draft',()=>{
 assert.equal(parseParameters('frequency_ghz GHz 载波频率\nspeed_kmh km/h').speed_kmh.description,'speed_kmh');
 assert.equal(parseParameters('a GHz\na MHz'),null,'a repeated name');
 assert.equal(parseParameters('Bad GHz'),null);
 assert.match(manualRecord({id:'Bad'}).error,/编号/);
 assert.match(manualRecord({id:'ok',title:'t',expression:'a',output_name:'c',output_unit:'dB',parameters:''}).error,/参数/);
 const {record}=manualRecord({id:'thermal',title:'热噪声',expression:'-174 + 10*log10(b)',output_name:'n_dbm',output_unit:'dBm',parameters:'b Hz 带宽'});
 assert.deepEqual(record.parameters,{b:{unit:'Hz',description:'带宽'}});
 assert.equal(record.status,'draft');assert.deepEqual(record.sources,[]);
});

test('approving a draft without a document needs a source and a numeric example',()=>{
 const record={parameters:{f:{unit:'GHz'},v:{unit:'km/h'}},output:{unit:'Hz'}};
 const form={title:'Rappaport',locator:'式(5.4)','in:f':'2','in:v':'100',expected:'185.3'};
 assert.deepEqual(sourcePayload(form,record),{source:{title:'Rappaport',locator:'式(5.4)'},example:{inputs:{f:2,v:100},expected:185.3,note:''}});
 assert.equal(sourcePayload({...form,'in:v':''},record),null);
 assert.equal(sourcePayload({...form,expected:'abc'},record),null);
 assert.equal(sourcePayload({...form,locator:' '},record),null);
 assert.equal(sourcePayload({...form,url:'ftp://x'},record),null);
 assert.equal(sourcePayload({...form,url:'https://itu.int'},record).source.url,'https://itu.int');
 assert.equal(sourcePayload(undefined,record),null);
});

test('goal choices from cards come after the dedicated targets, in their own groups',async()=>{
 const {fillChoices}=await import('../planning/web/questions.mjs');
 const old=globalThis.document;globalThis.document={createElement:make};
 try{
  const select=make('select');
  fillChoices(select,[{value:'fspl_ghz',label:'路径损耗'},{value:'doppler_max',label:'多普勒',group:'generic'},{value:'slant',label:'直线距离',group:'needs_tool',disabled:true},{value:'link_margin',label:'链路余量'}],
   c=>{const o=make('option');o.textContent=c.label;return o;});
  assert.deepEqual(select.children.map(n=>n.tag==='optgroup'?n.label:n.textContent),['路径损耗','链路余量','其他已入库公式（通用计算）','需专用程序（暂不能计算）']);
  const plain=make('select');fillChoices(plain,[{value:'a',label:'A'}],c=>{const o=make('option');o.textContent=c.label;return o;});
  assert.deepEqual(plain.children.map(n=>n.tag),['option']);
 }finally{globalThis.document=old;}
});

test('a result from a card expression names the card and says it has no independent check',async()=>{
 const {renderRight}=await import('../planning/web/details.mjs');
 const old=globalThis.document;globalThis.document={createElement:make};
 try{
  const state={status:'COMPLETED',request:{raw_text:'t'},report:{},validations:[],final_report:{conclusion:'',limitations:[]},
   result:{outputs:[{name:'doppler_hz',value:185.3,unit:'Hz',inputs:{speed_kmh:100}}],calculation_mode:'generic_card',card:{id:'doppler_max',version:'1.0.0'}}};
  const cards={doppler_max:{title:'最大多普勒频移',parameters:{speed_kmh:{unit:'km/h',description:'相对速率'}}}};
  const host=make('div');renderRight(host,{state,view:'main',open:new Map(),cards,onView(){}});
  const texts=flatten(host).map(n=>n.textContent);
  assert.ok(texts.includes('最大多普勒频移'));
  assert.ok(texts.includes('相对速率 100 km/h'));
  assert.ok(texts.includes('按审核入库公式卡计算，无独立复核模型 · doppler_max v1.0.0'));
 }finally{globalThis.document=old;}
});

test('a unit guess is offered as a suggestion, not as a default value',async()=>{
 const {renderQuestions}=await import('../planning/web/questions.mjs');
 const old=globalThis.document;globalThis.document={createElement:tag=>({...make(tag),dataset:{}})};
 const issue=(id,field,suggestion)=>({id,field,kind:'missing',status:'open',title:'请补充'+field,choices:[],suggestion});
 const unit={value:'1km',display:'1 km',reason:'kn 不是距离单位，可能是 km',note:'单位猜测，需确认'};
 const typical={value:'2GHz',display:'2 GHz',reason:'典型值',note:'默认补全，需确认'};
 const button=state=>{const host=make('div');renderQuestions(host,state,{disabled:true});return flatten(host).find(n=>n.tag==='button'&&/^全部采用/.test(n.textContent))?.textContent;};
 try{
  assert.equal(button({task_id:'t1',revision:1,status:'AWAITING_INPUT',input_issues:[issue('a','distance_km',unit),issue('b','frequency_ghz',typical)]}),'全部采用建议（2 项）');
  assert.equal(button({task_id:'t2',revision:1,status:'AWAITING_INPUT',input_issues:[issue('b','frequency_ghz',typical)]}),'全部采用默认值（1 项）');
 }finally{globalThis.document=old;}
});
