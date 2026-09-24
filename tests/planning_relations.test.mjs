import test from 'node:test';
import assert from 'node:assert/strict';
import {edgeState, renderFlow, RELATION_SEMANTICS, RELATION_DESCRIPTION} from '../planning/web/flow.mjs';

const state={task_id:'one',revision:1,state_version:2,status:'AWAITING_CONFIRMATION'};
const activity={task_id:'one',revision:1,run_id:'run',node:'calculation',phase:'started',details:{caller:'orchestrator'}};

test('logical ownership highlights observed activity without claiming direct calls',()=>{
 assert.equal(RELATION_SEMANTICS,'observed_activity');
 assert.match(RELATION_DESCRIPTION,/运行活动/);
 assert.match(RELATION_DESCRIPTION,/不表示.*直接调用/);
 assert.equal(edgeState(state,[activity],'orchestrator','compute_agent'),'running');
});

test('architecture alone, old revisions and rolled back runs do not highlight edges',()=>{
 assert.equal(edgeState(state,[],'orchestrator','compute_agent'),'idle');
 assert.equal(edgeState(state,[{...activity,revision:0}],'orchestrator','compute_agent'),'idle');
 assert.equal(edgeState(state,[{...activity,task_id:'other'}],'orchestrator','compute_agent'),'idle');
 for(const phase of ['rejected','cancelled','interrupted','replayed']){
  const terminal={...activity,node:'command',phase,details:{}};
  assert.equal(edgeState(state,[activity,terminal],'orchestrator','compute_agent'),'idle');
 }
});

test('rendered relation carries truthful accessible semantics',()=>{
 const previous=globalThis.document;
 const created=[];
 globalThis.document={createElementNS:(_ns,tag)=>{
  const node={tag,attrs:{},children:[],setAttribute(k,v){this.attrs[k]=v;},append(...nodes){this.children.push(...nodes);},addEventListener(){}};
  created.push(node);return node;
 }};
 try{
  const host={replaceChildren(){}};
  renderFlow(host,{state,events:[activity],selected:null,onSelect(){}});
  const path=created.find(n=>n.attrs['data-edge']==='orchestrator:compute_agent');
  assert.ok(path);
  assert.match(path.attrs.class,/moving/);
  assert.equal(path.attrs['data-relation'],'observed_activity');
  assert.equal(path.attrs['aria-label'],RELATION_DESCRIPTION);
  assert.notEqual(path.attrs['data-relation'],'direct_call');
 }finally{
  if(previous===undefined)delete globalThis.document;
  else globalThis.document=previous;
 }
});

function renderNodes(renderState,events=[]){
 const previous=globalThis.document;
 const created=[];
 globalThis.document={createElementNS:(_ns,tag)=>{
  const node={tag,attrs:{},children:[],textContent:'',setAttribute(k,v){this.attrs[k]=v;},append(...nodes){this.children.push(...nodes);},addEventListener(){}};
  created.push(node);return node;
 }};
 try{renderFlow({replaceChildren(){}},{state:renderState,events,selected:null,onSelect(){}});}
 finally{
  if(previous===undefined)delete globalThis.document;
  else globalThis.document=previous;
 }
 return created;
}

test('Visio page 1: peer agents dispatched by the orchestrator, confirmation gates calculation',()=>{
 const created=renderNodes(state);
 const edges=new Map(created.filter(n=>n.attrs['data-edge']).map(n=>[n.attrs['data-edge'],n.attrs.class]));
 for(const agent of ['requirements','compute_agent','validator_agent'])assert.match(edges.get('orchestrator:'+agent),/task/);
 for(const edge of ['requirements:confirmation','validator_agent:publish'])assert.match(edges.get(edge),/task/);
 assert.match(edges.get('confirmation:compute_agent'),/gate/);
 assert.match(edges.get('compute_agent:model'),/capability/);
 // Peers are not chained, and no separate follow-up node exists on page 1.
 assert.equal(edges.has('compute_agent:validator_agent'),false);
 assert.equal(created.some(n=>n.attrs['data-node']==='supplement'),false);
 assert.equal(created.find(n=>n.tag==='svg').attrs.viewBox,'0 0 840 494');
});

test('unwired and optional capabilities are drawn as such',()=>{
 const edges=new Map(renderNodes(state).filter(n=>n.attrs['data-edge']).map(n=>[n.attrs['data-edge'],n.attrs.class]));
 assert.match(edges.get('orchestrator:llm'),/unavailable/);
 assert.match(edges.get('compute_agent:llm'),/optional/);
});

test('awaiting supplement is shown on the confirmation node',()=>{
 const created=renderNodes({...state,status:'AWAITING_INPUT'});
 const node=created.find(n=>n.attrs['data-node']==='confirmation');
 assert.match(node.attrs.class,/waiting/);
 assert.ok(node.children.some(c=>c.textContent==='等待补充 · 见对话栏'));
});
