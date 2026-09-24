import test from 'node:test';
import assert from 'node:assert/strict';
import {planSteps,humanize} from '../planning/web/details.mjs';

const param=(name,value,unit,kind='user_text')=>({parameter_id:'r:'+name,canonical_name:name,value,unit,
 status:value===null?'missing':'user_provided',origins:value===null?[]:[{kind}]});
const plan={steps:[
 {step_id:'fspl-step',tool_id:'fspl_ghz',expected_unit:'dB',inputs:{frequency_ghz:{kind:'parameter',ref:'r:frequency_ghz'},distance_km:{kind:'parameter',ref:'r:distance_km'}}},
 {step_id:'link_margin-step',tool_id:'link_margin',expected_unit:'dB',inputs:{rx_power_dbm:{kind:'step',ref:'fspl-step'},reserve_db:{kind:'parameter',ref:'r:reserve_db'}}}]};
const report={parameters_proposal:[param('frequency_ghz',2,'GHz'),param('distance_km',10,'km','manual_form'),param('reserve_db',null,'dB')]};

test('each plan input names its source: text, manual, missing or an earlier step',()=>{
 const [first,second]=planSteps(plan,report,null);
 assert.equal(first.title,'自由空间路径损耗');assert.equal(first.value,null);
 assert.deepEqual(first.inputs.map(x=>x.source),['2 GHz · 原文','10 km · 手工填写']);
 assert.deepEqual(second.inputs.map(x=>[x.label,x.kind,x.source]),[['接收信号电平','step','步骤 1 的结果'],['预留余量','missing','缺失，待补充']]);
});

test('executed steps carry their own outputs',()=>{
 const result={outputs:[{value:17.5}],steps:[{step_id:'fspl-step',output:{value:118.4}},{step_id:'link_margin-step',output:{value:17.5}}]};
 assert.deepEqual(planSteps(plan,report,result).map(s=>s.value),[118.4,17.5]);
});

test('questions never show internal parameter ids',()=>{
 assert.equal(humanize('请补充：tx_power_dbm、rx_threshold_dbm'),'请补充：发射功率、接收门限');
 assert.equal(humanize('请补充：distance_km'),'请补充：路径距离（km）');
});
