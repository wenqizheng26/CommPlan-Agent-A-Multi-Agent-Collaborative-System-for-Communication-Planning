import test from 'node:test';
import assert from 'node:assert/strict';
import {fieldLabel,shownValue,draftTitle,exampleLine,preview} from '../planning/web/library.mjs';
import {lastSwap,previousVersion,comparisonLine} from '../planning/web/compare.mjs';

test('draft fields read as names a reviewer knows',()=>{
 assert.equal(fieldLabel('tx_power_dbm'),'额定发射功率 dBm');
 assert.equal(fieldLabel('band_ghz.1'),'频段上限 GHz');
 assert.equal(fieldLabel('examples.0.inputs.tx_loss_db'),'算例 · 发射馈线损耗');
 assert.equal(fieldLabel('parameters.tx_gain_dbi'),'发射天线增益 单位');
 assert.equal(shownValue(['XX-300','甲']),'XX-300、甲');
 assert.equal(shownValue(null),'未写明');
 assert.equal(draftTitle({kind:'device',record:{names:['XX-300']}}),'设备 · XX-300');
 assert.equal(draftTitle({kind:'formula',record:{title:'等效全向辐射功率'}}),'公式 · 等效全向辐射功率');
});

test('the formula example line shows the computed and the written result',()=>{
 const line=exampleLine({inputs:{tx_power_dbm:40,tx_gain_dbi:6,tx_loss_db:2},expected:44,value:44,unit:'dBm',passed:true});
 assert.equal(line.text,'算例：发射功率 40，发射天线增益 6，发射馈线损耗 2 → 44 dBm；原文 44 dBm');
 assert.equal(line.passed,true);
 assert.equal(exampleLine(null),null);
 assert.equal(exampleLine({inputs:{},expected:1,value:null,unit:'dB',passed:false}).text,'算例： → 无法计算；原文 1 dB');
});

test('a section preview starts at its own text, not the headings the locator names',()=>{
 assert.equal(preview('# XX-300 手册（模拟）\n## §1 规格表\n| 型号 | 功率 |\n| --- | ---: |\n\n\n\n额定发射功率'),'| 型号 | 功率 |\n| --- | ---: |\n\n额定发射功率');
 assert.equal(preview('<!-- page 3 -->\n正文'),'正文');
});

const ask=radio=>({raw_text:`A 站到 B 站用 ${radio} 电台`,manual_parameters:{},condition:null,target:null});
function saved(revision,status,{turns=[],value=5.93,met=false,radio='XX-100'}={}){
 return {revision,state_version:revision*2,state:{status,conversation:{turns},request:{...ask(radio),revision},
  result:{model_id:'link_margin',outputs:[{value,unit:'dB'}]},final_report:{requirement:{value:10,met}}}};
}

test('a swap result is compared with the last result before that swap only',()=>{
 const swap={turn_id:'t2',followup:true,applied:true,before:ask('XX-100'),changes:[{field:'device',before:'XX-100',after:'XX-200'}]};
 const earlier={turn_id:'t1',followup:true,applied:true,before:ask('XX-50'),changes:[{field:'device',before:'XX-50',after:'XX-100'}]};
 const history=[saved(0,'COMPLETED',{value:1.5,radio:'XX-50'}),saved(1,'COMPLETED',{turns:[earlier]}),
  saved(2,'AWAITING_CONFIRMATION',{turns:[earlier,swap],radio:'XX-200'}),saved(2,'COMPLETED',{turns:[earlier,swap],value:21.93,met:true,radio:'XX-200'})];
 const current=history.at(-1).state;
 assert.equal(lastSwap(current),swap);
 const previous=previousVersion(current,history);
 assert.equal(previous.state,history[1].state);
 assert.equal(comparisonLine(current,previous),'上一版（XX-100）链路余量 5.93 dB，不满足 → 本版（XX-200）21.93 dB，满足');
 assert.equal(previousVersion(saved(0,'COMPLETED').state,history),null);
 assert.equal(previousVersion(current,history.slice(2)),null);
 // The input the swap changed was never computed (out of range here): no older result stands in for it.
 const later={turn_id:'t3',followup:true,applied:true,before:ask('XX-150'),changes:[{field:'device',before:'XX-150',after:'XX-200'}]};
 const skipped=[saved(1,'COMPLETED',{turns:[earlier]}),saved(2,'NEEDS_MODEL',{turns:[earlier],radio:'XX-150'}),
  saved(3,'COMPLETED',{turns:[earlier,later],value:21.93,met:true,radio:'XX-200'})];
 assert.equal(previousVersion(skipped.at(-1).state,skipped),null);
 const both={...swap,changes:[...swap.changes,{field:'site',before:'B站',after:'C站'}]};
 assert.equal(comparisonLine(current,{state:history[1].state,swap:both}),'上一版（XX-100、B站）链路余量 5.93 dB，不满足 → 本版（XX-200、C站）21.93 dB，满足');
});
