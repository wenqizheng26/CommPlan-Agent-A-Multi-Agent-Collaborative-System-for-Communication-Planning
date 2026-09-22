import test from 'node:test';
import assert from 'node:assert/strict';
import {serviceText,callSummary,diagnosticMessages} from '../planning/web/model-status.mjs';
import {nodeStates} from '../planning/web/flow.mjs';

const diagnostics=[1,2,3].map(attempt=>({code:'MODEL_OUTPUT_INVALID',message:'模型结构或原文证据不合法。',details:{attempt}}));
const state={task_id:'t',revision:1,status:'COMPLETED',report:{runtime_health:'degraded',component_modes:{interpretation:'deterministic'},diagnostics},calculation_role:{mode:'llm'},review_assessment:{role:{mode:'llm',proposal:{decision:'pass'}}}};
test('online service and degraded task are independent',()=>{
 assert.match(serviceText({status:'ready'}),/已就绪/);
 const rows=callSummary(state);
 assert.match(rows[0],/3 次模型输出未通过校验.*已改用确定性规则/);
 assert.match(rows[1],/模型调用通过校验/);
 assert.match(rows[2],/模型调用通过校验/);
 assert.equal(nodeStates(state).llm,'degraded');
 assert.equal(nodeStates(state).publish,'completed');
 assert.match(serviceText({status:'unreachable'}),/无法连接/);
 assert.doesNotMatch(serviceText({status:'unreachable'}),/未启动/);
});
test('duplicate diagnostics are grouped without deleting attempts',()=>{
 const messages=diagnosticMessages(diagnostics);
 assert.equal(messages.length,1);assert.match(messages[0],/共 3 次/);
 assert.deepEqual(diagnostics.map(d=>d.details.attempt),[1,2,3]);
});
test('no fallback claim when retry eventually succeeded or fallback was disabled',()=>{
 assert.match(callSummary({report:{component_modes:{interpretation:'llm'},diagnostics}})[0],/通过校验/);
 assert.match(callSummary({report:{runtime_health:'unavailable',component_modes:{interpretation:'deterministic'},diagnostics}})[0],/未降级/);
 assert.match(callSummary(null)[0],/尚无已保存/);
});
