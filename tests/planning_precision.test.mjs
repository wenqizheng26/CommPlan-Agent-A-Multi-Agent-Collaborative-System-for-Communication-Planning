import test from 'node:test';
import assert from 'node:assert/strict';
import {renderRight} from '../planning/web/details.mjs';

test('published result comes before collapsed records and rounds only display',()=>{
 const old=globalThis.document;
 const make=tag=>({tag,children:[],textContent:'',append(...children){this.children.push(...children);},replaceChildren(...children){this.children=children;},setAttribute(){},addEventListener(){},classList:{toggle(){}}});
 globalThis.document={createElement:make};
 const output={name:'path_loss_db',value:98.42059991327963,unit:'dB'};
 const s={status:'COMPLETED',request:{raw_text:'test'},report:{},result:{outputs:[output]},validations:[{validator_id:'fspl_magnitude',passed:true}],final_report:{conclusion:'98.42 dB',limitations:['自由空间基准']},calculation_role:{mode:'deterministic'}};
 try{
  const host=make('div');renderRight(host,{state:s,view:'main',open:new Map(),onView(){}});
  const flatten=n=>[n,...(n.children||[]).flatMap(flatten)];const all=flatten(host);
  const metric=all.findIndex(n=>n.tag==='strong'&&n.textContent==='98.42');
  const records=all.findIndex(n=>n.tag==='summary'&&n.textContent==='记录与配置');
  const checks=all.findIndex(n=>n.tag==='summary'&&n.textContent==='1/1 校验通过');
  assert.ok(metric>=0&&checks>metric&&records>checks);
  assert.equal(output.value,98.42059991327963);
  assert.ok(all.filter(n=>n.tag==='details').every(n=>n.open!==true));
 }finally{if(old===undefined)delete globalThis.document;else globalThis.document=old;}
});
