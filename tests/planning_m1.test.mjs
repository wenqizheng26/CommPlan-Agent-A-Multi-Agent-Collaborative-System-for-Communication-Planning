import test from 'node:test';
import assert from 'node:assert/strict';
import {assessmentNoteText,originLabel,assumptionEdit,answerPresentation,horizonPresentation,solvePresentation,planPresentation} from '../planning/web/m1.mjs';

test('plan titles distinguish preview, program, model and fallback with advisory assessment',()=>{
 assert.equal(planPresentation({status:'AWAITING_INPUT'}).title,'计划预览 · 程序拼链');
 assert.equal(planPresentation({}).title,'计划 · 程序拼链');
 const state={report:{calculation_plan_proposal:{origin:'model',steps:[{tool_id:'fspl_ghz',why:'计算路径损耗'}],assessment:{mode:'llm',verdict:'review',notes:[]}}}};
 assert.match(planPresentation(state).title,/专业计算 Agent 编写/);
 assert.equal(planPresentation(state).assessment.verdict,'review');
 assert.equal(planPresentation(state).reasons.fspl_ghz,'计算路径损耗');
 state.report.calculation_plan_proposal={origin:'program',origin_note:'缺视距一步',assessment:{mode:'skipped',notes:[]}};
 assert.match(planPresentation(state).title,/模型计划未通过校验：缺视距一步/);
 assert.equal(planPresentation(state).skipped,true);
 assert.deepEqual(planPresentation(state).reasons,{});
 delete state.report.calculation_plan_proposal.origin_note;
 assert.equal(planPresentation(state).title,'计划 · 程序拼链');
});

test('knowledge labels mark only records verified as simulated',()=>{
 const p={canonical_name:'tx_power_dbm',origins:[{kind:'device',source_ref:'device:one#tx_power_dbm'}]};
 assert.equal(originLabel(p,{'device:one':{simulated:true}}).tag,'设备库 · 模拟');
 assert.equal(originLabel(p,{}).tag,'设备库');
 assert.equal(originLabel({...p,origins:[{kind:'default'}]}).editable,true);
 assert.equal(originLabel({...p,origins:[{kind:'manual_form'}]}).editable,false);
 const cards={received_power:{parameters:{tx_power_dbm:{default:{value:37,unit:'dBm'}}}}};
 assert.equal(originLabel({...p,origins:[{kind:'manual_form'}]}, {},cards).tag,'手填（原假设 37 dBm）');
});

test('assumption edit preserves original input and other manual values but never results',()=>{
 const state={request:{raw_text:'原文',condition:'free_space',target:null,request_id:'internal',manual_parameters:{frequency_ghz:{value:2,unit:'GHz'}}},
  report:{parameters_proposal:[{canonical_name:'tx_loss_db',unit:'dB',origins:[{kind:'default'}]}]},result:{value:999}};
 const input=assumptionEdit(state,'tx_loss_db','3');
 assert.deepEqual(input,{raw_text:'原文',condition:'free_space',target:null,manual_parameters:{frequency_ghz:{value:2,unit:'GHz'},tx_loss_db:{value:3,unit:'dB'}}});
 assert.equal(state.request.manual_parameters.tx_loss_db,undefined);
 for(const value of ['', ' ', 'NaN','Infinity'])assert.throws(()=>assumptionEdit(state,'tx_loss_db',value));
 assert.throws(()=>assumptionEdit(state,'frequency_ghz','3'));
});

test('model answer is distinct from deterministic fallback and withheld explanations',()=>{
 assert.equal(answerPresentation({answer:{text:null,mode:'deterministic_fallback'}}).show,false);
 const result=answerPresentation({answer:{text:null,withheld:true},review:{decision:'caution',opinions:[{kind:'risk',text:null}]}});
 assert.equal(result.show,true);assert.equal(result.caution,true);
 assert.match(result.text,/说明未通过数字核对/);assert.match(result.opinions[0],/该条未通过数字核对/);
});

test('line-of-sight failure is explicitly uncomputed',()=>{
 const p=horizonPresentation({status:'NEEDS_MODEL',failure:{code:'BEYOND_LINE_OF_SIGHT',details:{distance_km:85.065609,radio_horizon_km:40.99137},next_action:'更换传播模型'}});
 assert.equal(p.title,'超出视距，未计算');assert.match(p.text,/85.07/);assert.match(p.text,/40.99/);
 assert.equal(horizonPresentation({status:'FAILED',failure:{code:'OTHER'}}),null);
});

test('solver shows bounds, rating, sides and failures',()=>{
 const result=solvePresentation({value:41.066609,unit:'dBm',direction:'minimum',iterations:32,residual:1e-9,rated:{value:37,unit:'dBm',exceeded:true},left:{unknown_value:41,condition_value:9.9,satisfies:false},right:{unknown_value:42,condition_value:10.9,satisfies:true}});
 assert.match(result.headline,/至少 41.07 dBm/);assert.match(result.warning,/额定发射功率 37 dBm/);
 assert.match(result.sides[0],/不满足/);assert.match(result.sides[1],/满足/);
 assert.match(solvePresentation({error:'SOLVE_NO_ROOT'}).error,/无解/);
});

test('assessment hides only withheld text and skips when no note is visible',()=>{
 assert.equal(assessmentNoteText({text:null,withheld:true}),'该条未通过数字核对');
 assert.equal(assessmentNoteText({text:'自由空间仅作基准'}),'自由空间仅作基准');
 const presentation=planPresentation({report:{calculation_plan_proposal:{origin:'model',assessment:{mode:'skipped',notes:[{text:null,withheld:true}]}}}});
 assert.match(presentation.title,/专业计算 Agent 编写/);
 assert.equal(presentation.assessment,null);
 assert.equal(presentation.skipped,true);
});

test('a web document links out and a simulated one names its local file',async()=>{
 const {documentSource}=await import('../planning/web/m1.mjs');
 assert.deepEqual(documentSource({uri:'https://www.itu.int/rec/R-REC-P.525-5-202411-I/en',doc_id:'itu-p525-5'}),
  {source_url:'https://www.itu.int/rec/R-REC-P.525-5-202411-I/en',source_id:'itu-p525-5'});
 assert.deepEqual(documentSource({uri:'knowledge/documents/simulated/XX-100 手册.md',doc_id:'sim-xx100'}),
  {source_id:'knowledge/documents/simulated/XX-100 手册.md'});
});
