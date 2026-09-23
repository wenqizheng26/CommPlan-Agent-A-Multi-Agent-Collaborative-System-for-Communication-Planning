import test from 'node:test';
import assert from 'node:assert/strict';
import {renderDetails} from '../planning/web/details.mjs';

test('published result comes before collapsed role details and rounds only display',()=>{
 const old=globalThis.document;
 const make=tag=>({tag,children:[],textContent:'',append(...children){this.children.push(...children);},replaceChildren(...children){this.children=children;},setAttribute(){},addEventListener(){},classList:{toggle(){}}});
 globalThis.document={createElement:make};
 const output={name:'path_loss_db',value:98.42059991327963,unit:'dB'};
 const s={status:'COMPLETED',request:{raw_text:'test'},report:{},result:{outputs:[output]},validations:[],final_report:{conclusion:'98.42 dB',limitations:['自由空间基准']},calculation_role:{mode:'deterministic'}};
 try{
  const host=make('div');renderDetails(host,{state:s,node:'publish',tab:'result'});
  const flatten=n=>[n,...(n.children||[]).flatMap(flatten)];const all=flatten(host);
  const metric=all.findIndex(n=>n.tag==='strong'&&n.textContent==='98.42');
  const roles=all.findIndex(n=>n.tag==='summary'&&n.textContent==='计算、审查与调度记录');
  assert.ok(metric>=0&&roles>metric);
  assert.equal(output.value,98.42059991327963);
  assert.equal(all.find(n=>n.tag==='details')?.open,undefined);
 }finally{if(old===undefined)delete globalThis.document;else globalThis.document=old;}
});
