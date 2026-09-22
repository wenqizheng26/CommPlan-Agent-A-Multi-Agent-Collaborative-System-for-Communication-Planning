import test from 'node:test';
import assert from 'node:assert/strict';
import {draftStore} from '../planning/web/drafts.mjs';
import {openRun,nodeStates} from '../planning/web/flow.mjs';
test('drafts survive refresh and discard old revisions without mixing tasks',()=>{
 let raw='';const storage={getItem:()=>raw,setItem:(k,v)=>raw=v};
 let drafts=draftStore(storage);drafts.set('a:0:q','2GHz');drafts.set('b:1:q','1km');
 drafts=draftStore(storage);assert.equal(drafts.get('a:0:q'),'2GHz');
 drafts.retain('a',1,['new']);assert.equal(drafts.get('a:0:q'),undefined);assert.equal(drafts.get('b:1:q'),'1km');
});
test('unavailable storage and corrupt data do not block questions',()=>{
 const drafts=draftStore({getItem:()=>'{bad',setItem:()=>{throw Error('full');}});drafts.set('a','x');assert.equal(drafts.get('a'),'x');
});
test('cancelled runs stop restore polling and cannot remain running',()=>{
 const events=[{task_id:'a',revision:0,run_id:'r',node:'llm',phase:'started'}, {task_id:'a',revision:0,run_id:'r',node:'command',phase:'cancelled'}];
 assert.equal(openRun(events),null);assert.notEqual(nodeStates({task_id:'a',revision:0,status:'AWAITING_INPUT'},events).llm,'running');
});
