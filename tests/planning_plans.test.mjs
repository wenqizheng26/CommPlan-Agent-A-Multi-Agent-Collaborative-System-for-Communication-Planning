import test from 'node:test';
import assert from 'node:assert/strict';
import {planSteps,humanize,citation} from '../planning/web/details.mjs';

const param=(name,value,unit,kind='user_text')=>({parameter_id:'r:'+name,canonical_name:name,value,unit,
 status:value===null?'missing':'user_provided',origins:value===null?[]:[{kind}]});
const plan={steps:[
 {step_id:'fspl-step',tool_id:'fspl_ghz',expected_unit:'dB',inputs:{frequency_ghz:{kind:'parameter',ref:'r:frequency_ghz'},distance_km:{kind:'parameter',ref:'r:distance_km'}}},
 {step_id:'link_margin-step',tool_id:'link_margin',expected_unit:'dB',inputs:{rx_power_dbm:{kind:'step',ref:'fspl-step'},reserve_db:{kind:'parameter',ref:'r:reserve_db'}}}]};
const refs=[{catalog_id:'fspl_ghz',source_title:'ITU-R P.525-5 (11/2024), Calculation of free-space attenuation',locator:'Annex 1 and 2.3; printed pages 1 and 3; equation (6)'},
 {catalog_id:'received_power',source_title:'NASA, State-of-the-Art of Small Spacecraft Technology, Ground Data Systems and Mission Operations',locator:'11.3.1 Frequency Selection: Link Budget'},
 {catalog_id:'link_margin',source_title:'Texas Instruments SWRA479A, Achieving Optimum Radio Range (2017)',locator:'page 4, section 2.4: link margin definition'}];
const report={parameters_proposal:[param('frequency_ghz',2,'GHz'),param('distance_km',10,'km','manual_form'),param('reserve_db',null,'dB')],evidence_refs:refs};

test('each plan input names its source: text, manual, missing or an earlier step',()=>{
 const [first,second]=planSteps(plan,report,null);
 assert.equal(first.title,'自由空间损耗');assert.equal(first.value,null);assert.equal(first.out,null);
 assert.deepEqual(first.inputs.map(x=>[x.value,x.tag]),[['2 GHz','原文'],['10 km','手工']]);
 assert.deepEqual(second.inputs.map(x=>[x.label,x.kind,x.tag]),[['接收信号电平','step','上一步'],['预留余量','missing','待补充']]);
 assert.equal(second.inputs[0].ref,1);
});

test('executed steps carry their own outputs, rounded only for display',()=>{
 const result={outputs:[{value:17.5}],steps:[{step_id:'fspl-step',output:{value:118.42059991327963}},{step_id:'link_margin-step',output:{value:17.5}}]};
 const steps=planSteps(plan,report,result);
 assert.deepEqual(steps.map(s=>s.value),[118.42059991327963,17.5]);
 assert.deepEqual(steps.map(s=>s.out),['118.42 dB','17.50 dB']);
});

test('a single FSPL step with several candidate outputs does not pick one',()=>{
 const single={steps:[plan.steps[0]]},result={outputs:[{value:98.4},{value:101.9}]};
 assert.equal(planSteps(single,report,result)[0].out,'2 组结果');
});

test('steps cite the registered source of their formula card',()=>{
 assert.deepEqual(refs.map(citation),['ITU-R P.525-5 式(6)','NASA SST-SOA §11.3.1','TI SWRA479A §2.4']);
 assert.equal(citation({source_title:'Some Handbook, 2nd ed.',locator:'formula card source metadata'}),'Some Handbook');
 assert.equal(citation(undefined),'');
 assert.equal(planSteps(plan,report,null)[0].cite,'ITU-R P.525-5 式(6)');
});

test('questions never show internal parameter ids',()=>{
 assert.equal(humanize('请补充：tx_power_dbm、rx_threshold_dbm'),'请补充：发射功率、接收门限');
 assert.equal(humanize('请补充：distance_km'),'请补充：路径距离（km）');
 assert.equal(humanize('reserve_db 是此项目显式扣除的预留量'),'预留余量 是此项目显式扣除的预留量');
});

test('registered expressions read with symbols, not program ids',async()=>{
 const {symbolic}=await import('../planning/web/details.mjs');
 assert.equal(symbolic({expression:'rx_power_dbm - rx_threshold_dbm - reserve_db',output:{name:'link_margin_db'}}),'M = Pr − Pth − M₀');
 assert.equal(symbolic({expression:'tx_power_dbm + tx_gain_dbi - path_loss_db'}),'Pt + Gt − L');
});

test('each step shows its registered formula only when the card hash matches the task',async()=>{
 const {stepFormulas}=await import('../planning/web/details.mjs');
 const evidence={...report,evidence_refs:[{...refs[0],content_hash:'a',card_version:'1.0.0'},{...refs[2],content_hash:'c',card_version:'1.0.0'}]};
 const model={id:'link_margin',title:'扣除预留量后的链路电平余量',expression:'rx_power_dbm - rx_threshold_dbm - reserve_db',version:'1.0.0'};
 const status=cards=>stepFormulas(plan,evidence,null,cards,model).map(s=>s.status);
 assert.deepEqual(status({}),['loading','ok']);
 assert.deepEqual(status({fspl_ghz:{id:'fspl_ghz',content_hash:'a'}}),['ok','ok']);
 assert.deepEqual(status({fspl_ghz:{id:'fspl_ghz',content_hash:'b'}}),['changed','ok']);
 assert.deepEqual(status({fspl_ghz:null}),['missing','ok']);
 const [first,last]=stepFormulas(plan,evidence,null,{fspl_ghz:{id:'fspl_ghz',content_hash:'b'}},model);
 assert.equal(first.card,null);assert.equal(last.card,model);assert.equal(first.version,'1.0.0');
});
