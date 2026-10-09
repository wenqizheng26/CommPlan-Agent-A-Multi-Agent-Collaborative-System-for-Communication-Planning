import test from 'node:test';
import assert from 'node:assert/strict';
import {renderRight,uncitedCards} from '../planning/web/details.mjs';

const make=tag=>({tag,children:[],textContent:'',className:'',append(...children){this.children.push(...children);},replaceChildren(...children){this.children=children;},
 setAttribute(){},addEventListener(){},classList:{toggle(){}}});
const flatten=n=>[n,...(n.children||[]).flatMap(flatten)];
const hit=(id,rank,doc,title,excerpt)=>({id,rank,source_type:'document_chunk',title,excerpt,
 source:{title,doc_id:doc,locator:`${title} / §1, chunk 1`,simulated:true,uri:'本机'},scores:{lexical:0.1,dense:0.5,fused:0.03}});
const found={hits:[hit('doc:a:s1-1',1,'sim-a','A 手册','## §1 规格表\n\n| 型号 | 功率 |\n| --- | ---: |\n| A | 37 |'),hit('doc:b:s1-1',2,'sim-b','B 手册','另一段')],
 used:['doc:a:s1-1'],mode_requested:'hybrid',mode_used:'hybrid',degraded:false,top_k:4,top_n:1,latency_ms:{total:12},query:'A站 到 B站 2 GHz'};
const plan={steps:[{step_id:'s1',tool_id:'fspl_ghz',inputs:{},expected_unit:'dB'}]};

function render(view,cards={}){
 const old=globalThis.document;globalThis.document={createElement:make};
 try{
  const s={status:'AWAITING_CONFIRMATION',request:{raw_text:'test'},report:{document_retrieval:found,evidence_refs:[],calculation_plan_proposal:plan,parameters_proposal:[]}};
  const host=make('div');renderRight(host,{state:s,view,open:new Map(),cards,onView(){}});return flatten(host);
 }finally{globalThis.document=old;}
}

test('the main view names how many document chunks were used and links to the evidence',()=>{
 const all=render('main');
 assert.ok(all.some(n=>n.tag==='button'&&n.textContent==='参考文档 1 段'));
});

test('the evidence view lists every hit with rank, locator and scores, adopted ones first-class',()=>{
 const all=render('evidence');
 const texts=all.map(n=>n.textContent);
 assert.ok(texts.includes('文档检索'));
 assert.ok(texts.includes('#1')&&texts.includes('#2'));
 assert.equal(texts.filter(t=>t==='已采用').length,1);
 assert.equal(texts.filter(t=>t==='未采用').length,1);
 assert.ok(texts.includes('向量 0.500'));
 assert.ok(texts.includes('A站 到 B站 2 GHz'),'the query is shown');
 const excerpt=all.find(n=>n.className==='excerpt'&&n.textContent.includes('| A | 37 |'));
 assert.ok(excerpt&&!excerpt.textContent.includes('##')&&!excerpt.textContent.includes('---'),'headings and table rules are dropped');
 assert.ok(all.some(n=>n.tag==='li'&&n.className==='hit used'));
});

test('a plan card whose source document was not retrieved is named; unknown sources stay silent',()=>{
 const cards={fspl_ghz:{title:'自由空间基本传输损耗',sources:[{doc_id:'itu-p525-5'}]}};
 assert.deepEqual(uncitedCards(plan,found,cards).map(c=>c.title),['自由空间基本传输损耗']);
 assert.equal(uncitedCards(plan,found,{fspl_ghz:{title:'x',sources:[{}]}}),null);
 assert.ok(render('evidence',cards).some(n=>n.textContent==='未检索到「自由空间基本传输损耗」的原文片段，仅有公式卡登记的出处。'));
 const used={...found,hits:[...found.hits,hit('doc:p525:p1-1',3,'itu-p525-5','P.525','free space')],used:['doc:p525:p1-1']};
 assert.equal(uncitedCards(plan,used,cards).length,0);
 const saved={fspl_ghz:{...cards.fspl_ghz,title:'老师验收口径的自由空间基本传输损耗'}};
 const texts=render('evidence',saved).map(n=>n.textContent);
 assert.ok(texts.includes('未检索到「自由空间基本传输损耗」的原文片段，仅有公式卡登记的出处。'),'a saved card title shows its display name');
 assert.ok(!texts.some(t=>/老师|验收/.test(t)));
});
