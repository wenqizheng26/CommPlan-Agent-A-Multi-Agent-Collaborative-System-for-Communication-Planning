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
 const texts=render({library:{documents:[],formats:[],converter:true},cards}).map(n=>n.textContent);
 for(const t of ['专用程序','通用计算','需专用程序','内置','手填','已停用'])assert.ok(texts.includes(t),t);
 assert.equal(texts.filter(t=>t==='删除').length,1);
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
