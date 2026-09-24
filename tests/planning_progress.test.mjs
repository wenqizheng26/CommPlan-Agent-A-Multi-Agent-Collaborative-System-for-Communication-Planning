import test from 'node:test';
import assert from 'node:assert/strict';
import {taskProgress,headline} from '../planning/web/progress.mjs';
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
test('headline says once what to do now, per state',()=>{
 const issue=(kind,status='open')=>({kind,status});
 const text=(s,o)=>headline(s,o).text;
 assert.equal(text(null),'输入需求开始');
 assert.equal(text({...draft,status:'AWAITING_INPUT',input_issues:[issue('missing'),issue('missing'),issue('missing','resolved')]}),'缺 2 项参数');
 assert.equal(text({...draft,status:'AWAITING_INPUT',input_issues:[issue('conflict')]}),'1 处冲突');
 assert.equal(text({...draft,status:'AWAITING_INPUT',input_issues:[issue('clarification'),issue('pending')]}),'2 处待澄清');
 assert.equal(text({...draft,status:'AWAITING_INPUT',input_issues:[issue('missing'),issue('conflict')]}),'2 项待处理');
 assert.equal(text({...draft,report:{calculation_plan_proposal:{steps:[1,2,3]}}}),'3 步计算链 · 待确认');
 const done={...draft,status:'COMPLETED',validations:[{passed:true},{passed:true}]};
 assert.deepEqual(headline(done,{ran:'本次 1.00 s。'}),{text:'完成 · 2/2 校验通过',sub:'本次 1.00 s。',tone:'ok'});
 assert.equal(text({...draft,status:'FAILED',failure:{message:'x'}}),'未完成');
 assert.equal(text(done,{historical:true}),'第 1 版 · 只读');
 assert.equal(text(draft,{busy:true,action:'confirm'}),'计算中…');
 assert.deepEqual(headline(draft,{busy:true,action:'create',modelLabel:'Qwen3 4B · 标准'}),{text:'解析中…',sub:'Qwen3 4B · 标准',tone:'run'});
 assert.equal(text(draft,{editing:true}),'编辑原文中');
});
