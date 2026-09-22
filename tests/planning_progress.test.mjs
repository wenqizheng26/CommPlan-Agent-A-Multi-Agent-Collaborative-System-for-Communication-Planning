import test from 'node:test';
import assert from 'node:assert/strict';
import {taskProgress} from '../planning/web/progress.mjs';
const draft={task_id:'one',revision:1,status:'AWAITING_CONFIRMATION',report:{},state_version:1};
const event=(node,phase,extra={})=>({task_id:'one',revision:1,run_id:'r',node,phase,...extra});
const stages=(s,e=[])=>taskProgress(s,e).steps.map(s=>s.status);
test('progress preserves confirmation and missing-input gates',()=>{
 assert.deepEqual(stages(draft),['completed','waiting','idle','idle','idle']);
 assert.deepEqual(stages({...draft,status:'AWAITING_INPUT'}),['waiting','idle','idle','idle','idle']);
 assert.equal(stages({...draft,status:'NEEDS_MODEL'})[0],'waiting');
});
test('observed calculation and review are progress, never a published result',()=>{
 assert.deepEqual(stages(draft,[event('calculation','started')]),['completed','completed','running','idle','idle']);
 assert.equal(stages(draft,[event('review','started')])[3],'running');
 assert.equal(stages(draft,[event('publish','completed')])[4],'running');
});
test('rollback and stale activity cannot complete current revision',()=>{
 assert.deepEqual(stages(draft,[event('calculation','started',{revision:0})]),stages(draft));
 for(const phase of ['rejected','cancelled','interrupted'])assert.deepEqual(stages(draft,[event('calculation','completed'),event('command',phase)]),stages(draft));
});
test('only committed published state completes all stages; editing resets progress',()=>{
 const done={...draft,status:'COMPLETED',final_report:{}};
 assert.deepEqual(stages(done,[event('calculation','started')]),Array(5).fill('completed'));
 assert.notEqual(stages({...done,final_report:null})[4],'completed');
 assert.deepEqual(stages({...draft,revision:2},[event('publish','completed')]),stages(draft));
 assert.match(taskProgress(done,[],{dirty:true}).action,/上次保存版本/);
 assert.match(taskProgress(done,[],{historical:true}).action,/历史只读/);
});
