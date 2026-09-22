import test from 'node:test';
import assert from 'node:assert/strict';
import {nodeStates, relevantEvents, activityFresh, openRun} from '../planning/web/flow.mjs';
const draft={task_id:'one',revision:1,state_version:3,status:'AWAITING_CONFIRMATION',report:{component_modes:{interpretation:'deterministic'}}};
test('revision and task isolate old activity, confirmation remains waiting',()=>{
 const events=[{task_id:'one',revision:0,node:'calculation',phase:'completed',run_id:'a'}, {task_id:'other',revision:1,node:'calculation',phase:'completed',run_id:'b'}];
 assert.equal(nodeStates(draft,events).calculation,'idle');
 assert.equal(nodeStates(draft,events).confirmation,'waiting');
 assert.equal(relevantEvents(draft,events).length,0);
});
test('rolled back observed calculation cannot look like saved success',()=>{
 const events=[{task_id:'one',revision:1,node:'calculation',phase:'completed',run_id:'a'}, {task_id:'one',revision:1,node:'command',phase:'rejected',run_id:'a'}];
 assert.notEqual(nodeStates(draft,events).calculation,'completed');
 assert.equal(nodeStates(draft,events).failure,'failed');
});
test('active stage is visible, unsupported targets never appear complete',()=>{
 const events=[{task_id:'one',revision:1,node:'calculation',phase:'started',run_id:'a'}];
 assert.equal(nodeStates(draft,events).calculation,'running');
 assert.equal(nodeStates(draft,events).explanation,'unavailable');
});
test('interrupted observation does not override committed completed state',()=>{
 const done={...draft,status:'COMPLETED',result:{},final_report:{}};
 const events=[{task_id:'one',revision:1,node:'command',phase:'interrupted',run_id:'a'}];
 assert.equal(nodeStates(done,events).publish,'completed');
});
test('late started observation cannot override committed success',()=>{
 const done={...draft,status:'COMPLETED',result:{},final_report:{}};
 assert.equal(nodeStates(done,[{task_id:'one',revision:1,node:'calculation',phase:'started',run_id:'a'}]).calculation,'completed');
});
test('monotone observations and open runs support refresh recovery',()=>{
 const started=[{seq:4,run_id:'a',node:'command',phase:'started',revision:2}];
 const finished=[...started,{seq:5,run_id:'a',node:'command',phase:'committed'}];
 assert.equal(activityFresh(finished,started),false);
 assert.equal(openRun(started).revision,2);
 assert.equal(openRun(finished),null);
});

test('review role and grounded model calls have truthful statuses',()=>{
 const review={role:{mode:'llm',proposal:{decision:'needs_input'}}};
 assert.equal(nodeStates({...draft,status:'AWAITING_INPUT',review_assessment:review}).validator_agent,'waiting');
 const done={...draft,status:'COMPLETED',calculation_role:{mode:'llm'},review_assessment:{role:{mode:'deterministic',proposal:{decision:'pass'}}}};
 assert.equal(nodeStates(done).llm,'completed');
 const fallback={...done,calculation_role:{mode:'deterministic_fallback'}};
 assert.equal(nodeStates(fallback).llm,'degraded');
});
