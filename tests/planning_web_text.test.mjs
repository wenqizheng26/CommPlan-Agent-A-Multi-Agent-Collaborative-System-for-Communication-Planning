import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {renderRight} from '../planning/web/details.mjs';

test('source evidence spans use Python code points, including emoji', async () => {
  const {sourceExcerpt} = await import('../planning/web/text.mjs');
  const text='📡按自由空间基准计算，频率2GHz，距离1km，求路径损耗。';
  assert.equal(sourceExcerpt(text,[11,17]),'频率2GHz');
  assert.equal(sourceExcerpt(text,[18,23]),'距离1km');
  assert.equal(sourceExcerpt('频率2000MHz',[0,9]),'频率2000MHz');
});

test('historical catalog labels display as product copy while snapshots and input stay intact',()=>{
 const state=JSON.parse(readFileSync(new URL('./fixtures/teacher_report/comparison.json',import.meta.url),'utf8')).state;
 const cards=Object.fromEntries(JSON.parse(readFileSync(new URL('../knowledge/formulas.json',import.meta.url),'utf8')).map(c=>[c.id,c]));
 const oldTitle='老师验收口径的自由空间基本传输损耗',ref=state.report.evidence_refs.find(r=>r.catalog_id==='fspl_mhz');
 // Simulate the exact historical card version. A current card with a different hash must still be withheld.
 cards.fspl_mhz={...cards.fspl_mhz,title:oldTitle,content_hash:ref.content_hash};
 state.retrieval.hits.find(h=>h.id==='fspl_mhz').title=oldTitle;
 const before=JSON.stringify(state),catalogBefore=JSON.stringify(cards),previous=globalThis.document;
 class Element {
  constructor(tag){this.tag=tag;this.children=[];this.textContent='';}
  append(...children){this.children.push(...children);}
  replaceChildren(...children){this.children=children;}
  setAttribute(name,value){this[name]=value;} addEventListener(){}
 }
 const walk=node=>typeof node==='string'?[]:[node,...(node.children||[]).flatMap(walk)];
 const strings=host=>walk(host).filter(n=>n.tag!=='pre').map(n=>n.textContent).filter(Boolean);
 globalThis.document={createElement:tag=>new Element(tag),createTextNode:text=>({textContent:text})};
 try{
  const host=new Element('div'),ctx={state,cards,view:'formula',onView(){}};
  renderRight(host,ctx);
  assert.ok(strings(host).includes('自由空间基本传输损耗'));
  assert.ok(!strings(host).includes(oldTitle));
  renderRight(host,{...ctx,view:'evidence'});
  assert.ok(strings(host).includes('自由空间基本传输损耗'));
  assert.ok(!strings(host).some(s=>/老师|验收/.test(s)));
  assert.ok(walk(host).filter(n=>n.className==='excerpt').every(n=>n.translate!==false));
  renderRight(host,{...ctx,view:'main',historical:true});
  assert.ok(!strings(host).some(s=>/老师|验收/.test(s)));
  renderRight(host,{...ctx,state:{...state,status:'AWAITING_CONFIRMATION'},view:'main'});
  assert.ok(!strings(host).some(s=>/老师|验收/.test(s)));
  assert.equal(JSON.stringify(state),before);assert.equal(JSON.stringify(cards),catalogBefore);
  renderRight(host,{...ctx,cards:{...cards,fspl_mhz:{...cards.fspl_mhz,content_hash:'different'}},view:'formula'});
  assert.ok(strings(host).includes('公式卡已变更，与本任务所用版本不同，不显示'));
  const originalState=structuredClone(state);originalState.request.raw_text=oldTitle;
  for(const p of originalState.report.parameters_proposal)p.origins=[];
  renderRight(host,{...ctx,state:originalState,view:'parameters'});
  assert.ok(strings(host).includes(oldTitle));
 }finally{globalThis.document=previous;}
});
