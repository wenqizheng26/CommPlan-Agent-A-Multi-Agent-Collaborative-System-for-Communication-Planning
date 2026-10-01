import test from 'node:test';
import assert from 'node:assert/strict';
import {records,matchModelCalls,renderRecords,modelLine,toolLine,parameterLine,purposeNames} from '../planning/web/records.mjs';
import {install,t} from '../planning/web/i18n.mjs';
import * as en from '../planning/web/i18n-en.mjs';
import {readFileSync} from 'node:fs';

const state = {task_id:'teacher-records', revision:2};
const at = milliseconds => new Date(Date.UTC(2026,9,1,0,0,0,milliseconds)).toISOString();
const event = (node,phase,ms,details={},over={}) => ({...state,run_id:'r1',seq:ms,node,phase,at:at(ms),details,...over});
const model = [event('llm','started',10000,{caller:'requirements',purpose:'intent',model_id:'qwen-local'}),
 event('llm','completed',31300,{caller:'requirements',purpose:'intent'})];
const single = event('tool','completed',32000,{caller:'compute_agent',step_id:'loss',tool_id:'fspl_mhz',
 inputs:{distance_km:10,frequency_mhz:5800},output:{name:'path_loss_db',value:127.7085598713,unit:'dB'}});
const composite = event('tool','completed',33000,{caller:'compute_agent',tool_id:'calc_link_margin',label:'QPSK',
 arguments:{distance_km:10,frequency_mhz:5800,tx_power_dbm:20,tx_gain_dbi:18,rx_gain_dbi:18,modulation:'QPSK'},
 result:{path_loss_db:127.7085598713,rx_power_dbm:-71.7085598713,rx_sensitivity_dbm:-100,link_margin_db:28.2914401287,required_margin_db:0,meets:true},
 steps:[{card:'fspl_mhz',inputs:{distance_km:10,frequency_mhz:5800},value:127.7085598713,unit:'dB'}]});
const call = (ms,over={}) => ({...state,call_id:`call-${ms}`,agent:'requirements',model:'qwen-local',at:at(ms),
 messages:[{role:'system',content:'原样系统提示'},{role:'user',content:'原样用户输入'}],response:'{"ready":true}',status:'ok',latency_ms:1200,...over});

test('the captured deterministic MARGIN state shows exactly its three real step events',()=>{
 const fixture=JSON.parse(readFileSync(new URL('./fixtures/teacher_ui/margin-completed.json',import.meta.url),'utf8'));
 const cards=records(fixture.state,fixture.events);
 assert.equal(fixture.state.status,'COMPLETED'); assert.equal(fixture.fixture.kind,'real_deterministic_state');
 assert.deepEqual(cards.map(card=>card.tool),['fspl_ghz','received_power','link_margin']);
 for (const [index,card] of cards.entries()) assert.deepEqual(card.output,fixture.state.result.steps[index].output);
});

test('future composite/model fixtures honor card counts and include all matched HTTP retries',()=>{
 const fixture=JSON.parse(readFileSync(new URL('./fixtures/teacher_ui/records-model.json',import.meta.url),'utf8'));
 const cards=records(fixture.state,fixture.events), models=cards.filter(card=>card.kind==='model');
 assert.equal(cards.length,fixture.fixture.expected.cards);
 assert.deepEqual(models.map(card=>card.status),fixture.fixture.expected.statuses);
 assert.equal(cards.filter(card=>card.tool==='calc_link_margin').length,fixture.fixture.expected.tool_cards);
 const matches=matchModelCalls(models[0],[...fixture.model_calls.calls,...fixture.excluded_calls]);
 assert.deepEqual(matches.map(call=>call.call_id),fixture.fixture.expected.requirements_call_ids);
});

test('model started/completed events become one card with the owning Agent and measured duration',()=>{
 const [card] = records(state,[...model].reverse());
 assert.equal(card.kind,'model'); assert.equal(card.agent,'Requirement'); assert.equal(card.purpose,'intent');
 assert.equal(card.status,'completed'); assert.equal(card.model,'qwen-local'); assert.equal(card.duration_ms,21300);
 assert.equal(card.started_at,model[0].at); assert.equal(card.finished_at,model[1].at);
 assert.equal(modelLine(card),'Requirement Agent → qwen-local · 需求解析 · 完成 · 21.3 s');
});

test('unmatched starts remain running, failed ends preserve reasons, and repeated purposes remain separate calls',()=>{
 const events = [model[0],event('llm','failed',11000,{caller:'requirements',purpose:'intent',reason:'timeout',latency_ms:800}),
  event('llm','started',12000,{caller:'requirements',purpose:'intent'})];
 const cards = records(state,events);
 assert.equal(cards.length,2); assert.equal(cards[0].status,'failed'); assert.equal(cards[0].reason,'timeout');
 assert.equal(cards[0].duration_ms,800); assert.equal(cards[1].status,'running'); assert.equal(cards[1].duration_ms,null);
 assert.notEqual(cards[0].key,cards[1].key); assert.equal(records(state,[model[0]])[0].key,cards[0].key);
});

test('an optional attempt on a start does not leave a spinner when failure omits it',()=>{
 const cards = records(state,[event('llm','started',0,{caller:'compute_agent',purpose:'compute_agent',attempt:1}),
  event('llm','failed',2000,{caller:'compute_agent',purpose:'compute_agent',reason:'offline'})]);
 assert.equal(cards[0].status,'failed'); assert.equal(cards[0].agent,'LinkBudget');
 const withAttempt = records(state,[event('llm','started',0,{caller:'compute_agent',purpose:'compute_agent',attempt:1}),
  event('llm','failed',2000,{caller:'compute_agent',purpose:'compute_agent',attempt:2,reason:'offline'})]);
 assert.equal(withAttempt[0].status,'running');
});

test('purpose maps all three teacher Agents and extraction and separates runs',()=>{
 const purposes = Object.keys(purposeNames);
 const cards = records(state,purposes.map((purpose,index) => event('llm','started',index,{caller:purpose,purpose})));
 assert.deepEqual(cards.map(card=>card.agent),['Requirement','Requirement','Requirement','LinkBudget','Report','资料抽取']);
 const otherRun = event('llm','completed',31300,{caller:'requirements',purpose:'intent'},{run_id:'r2'});
 assert.equal(records(state,[model[0],otherRun])[0].status,'running');
});

test('single-step and composite tool events retain inputs and output without creating duplicate steps',()=>{
 const [first,second] = records(state,[composite,single]);
 assert.equal(first.kind,'tool'); assert.equal(first.agent,'LinkBudget'); assert.equal(first.tool,'fspl_mhz');
 assert.deepEqual(first.inputs,single.details.inputs); assert.deepEqual(first.output,single.details.output);
 assert.equal(second.tool,'calc_link_margin'); assert.equal(second.label,'QPSK');
 assert.deepEqual(second.arguments,composite.details.arguments); assert.deepEqual(second.steps,composite.details.steps);
 assert.deepEqual(second.result,composite.details.result);
 assert.equal(toolLine(first),'LinkBudget Agent → fspl_mhz：路径距离 = 10.00 km，载波频率 = 5800.00 MHz → 127.71 dB');
});

test('only the current task and revision are shown in event time order, without mutating supplied data',()=>{
 const events = [composite,...model,single,event('llm','started',0,{caller:'requirements',purpose:'intent'},{revision:1}),
  event('tool','completed',1,single.details,{task_id:'another-task'})];
 const before = JSON.stringify({state,events});
 const cards = records(state,events);
 assert.deepEqual(cards.map(card=>card.kind),['model','tool','tool']);
 assert.deepEqual(cards.map(card=>card.tool).filter(Boolean),['fspl_mhz','calc_link_margin']);
 assert.equal(JSON.stringify({state,events}),before); assert.deepEqual(records(null,events),[]);
});

test('history falls back to result steps, prefers final tool calls, and never invents model calls',()=>{
 const old = {...state,result:{steps:[{tool_id:'fspl_ghz',inputs:{distance_km:10},output:{value:127.67,unit:'dB'}}]}};
 const [card] = records(old,[]);
 assert.equal(card.tool,'fspl_ghz'); assert.equal(card.historical,true); assert.equal(card.kind,'tool');
 const withCalls = {...old,final_report:{tool_calls:[{tool:'calc_link_margin',label:'QPSK',arguments:composite.details.arguments,result:composite.details.result}]}};
 assert.equal(records(withCalls,[])[0].tool,'calc_link_margin'); assert.equal(records(withCalls,[]).length,1);
 assert.equal(records(old,[event('command','committed',0)]).length,0);
});

test('model logs match every retry inside the same revision, Agent and two-second time window',()=>{
 const [card] = records(state,model);
 const logs = [call(7900),call(8000),call(14000),call(33200),call(33300),call(33301),
  call(14000,{revision:1}),call(14000,{task_id:'other'}),call(14000,{agent:'validator_agent'})];
 assert.deepEqual(matchModelCalls(card,logs).map(row=>row.at),[8000,14000,33200,33300].map(at));
 assert.deepEqual(matchModelCalls(card,[call(60000)]),[]); assert.deepEqual(matchModelCalls(records(state,[single])[0],logs),[]);
});

test('supplement and other purposes use the documented log Agent rather than the displayed teacher name',()=>{
 for (const [purpose,caller,agent] of [['supplement','requirements','supplement'],['followup','requirements','requirements'],['compute_agent','compute_agent','compute_agent'],['validator_agent','validator_agent','validator_agent']]) {
  const [card] = records(state,[event('llm','started',10000,{purpose,caller}),event('llm','completed',20000,{purpose,caller})]);
  assert.equal(matchModelCalls(card,[call(15000,{agent})]).length,1);
 }
});

class Element {
 constructor(tag) { this.tag=tag; this.children=[]; this.textContent=''; this.attributes={}; this.handlers={}; }
 append(...children) { for (const child of children) { child.remove?.(); child.parent=this; this.children.push(child); } }
 replaceChildren(...children) { for (const child of this.children) child.parent=null; this.children=[]; this.append(...children); }
 setAttribute(name,value) { this.attributes[name]=value; }
 addEventListener(name,handler) { this.handlers[name]=handler; }
 remove() { if (!this.parent) return; this.parent.children=this.parent.children.filter(child=>child!==this); this.parent=null; }
 toggle(open) { this.open=open; this.handlers.toggle?.(); }
}
const walk = node => [node,...node.children.flatMap(walk)];
const flush = () => new Promise(resolve=>setImmediate(resolve));
async function withDOM(run) {
 const previous=globalThis.document; globalThis.document={createElement:tag=>new Element(tag)};
 try { await run(); } finally { globalThis.document=previous; }
}

test('polling appends cards and preserves the expanded model details, fetching logs lazily once',async()=>withDOM(async()=>{
 const host = new Element('section'); let fetched=0,endpoint;
 const fetch = async url=>{fetched++;endpoint=url;return {ok:true,json:async()=>({calls:[call(14000),call(18000)]})};};
 renderRecords(host,state,model,{fetch}); assert.equal(fetched,0);
 const details = walk(host).find(node=>node.tag==='details'), article=walk(host).find(node=>node.tag==='article');
 details.toggle(true); await flush();
 assert.equal(fetched,1); assert.equal(endpoint,'/api/tasks/teacher-records/model-calls');
 const pre = walk(host).filter(node=>node.tag==='pre');
 assert.equal(pre.length,6); assert.ok(pre.every(node=>node.attributes.translate==='no'));
 assert.equal(pre[2].textContent,'{\n  "ready": true\n}'); assert.equal(pre[0].textContent,'原样系统提示');
 renderRecords(host,state,[...model,single,composite],{fetch}); await flush();
 assert.equal(walk(host).find(node=>node.tag==='details'),details); assert.equal(details.open,true);
 assert.equal(walk(host).find(node=>node.tag==='article'),article); assert.equal(fetched,1);
 assert.equal(walk(host).filter(node=>node.tag==='article').length,3);
 assert.ok(walk(host).some(node=>node.textContent==='-71.71 dBm'));
 assert.ok(walk(host).some(node=>node.textContent==='28.29 dB'));
 assert.ok(walk(host).some(node=>node.textContent==='满足'));
}));

test('logs with unsafe markup remain literal text and missing logs show the documented message',async()=>withDOM(async()=>{
 const host = new Element('section'), fetch=async()=>({ok:true,json:async()=>({calls:[call(15000,{messages:[{role:'user',content:'<img src=x onerror=alert(1)>'}],response:'<script>unsafe</script>'})]})});
 renderRecords(host,state,model,{fetch}); walk(host).find(node=>node.tag==='details').toggle(true); await flush();
 assert.ok(walk(host).some(node=>node.textContent==='<img src=x onerror=alert(1)>'));
 assert.equal(walk(host).some(node=>node.tag==='img'||node.tag==='script'),false);
 renderRecords(host,{...state,revision:3},model.map(row=>({...row,revision:3})),{fetch:async()=>({ok:true,json:async()=>({calls:[]})})});
 walk(host).find(node=>node.tag==='details').toggle(true); await flush();
 assert.ok(walk(host).some(node=>node.textContent==='日志中没有对应记录'));
}));

test('a model completing after logs were first opened refreshes the cache while keeping details open',async()=>withDOM(async()=>{
 const host=new Element('section'); let fetched=0;
 const fetch=async()=>({ok:true,json:async()=>({calls:++fetched===1?[]:[call(15000)]})});
 renderRecords(host,state,[model[0]],{fetch}); const details=walk(host).find(node=>node.tag==='details');
 details.toggle(true); await flush(); assert.equal(fetched,1);
 renderRecords(host,state,model,{fetch}); await flush();
 assert.equal(details.open,true); assert.equal(fetched,2); assert.equal(walk(host).filter(node=>node.tag==='pre').length,3);
}));

test('a failed log read can be retried by closing and reopening without changing the task',async()=>withDOM(async()=>{
 const host=new Element('section'); let fetched=0;
 const fetch=async()=>({ok:++fetched>1,json:async()=>({calls:[]})});
 renderRecords(host,state,model,{fetch}); const details=walk(host).find(node=>node.tag==='details');
 details.toggle(true); await flush();
 assert.ok(walk(host).some(node=>node.textContent==='调用日志读取失败，请收起后重试。'));
 details.toggle(false); details.toggle(true); await flush();
 assert.equal(fetched,2); assert.ok(walk(host).some(node=>node.textContent==='日志中没有对应记录'));
}));

test('historical rendering visibly labels the fallback and revision changes clear previous cards',async()=>withDOM(async()=>{
 const host=new Element('section');
 renderRecords(host,{...state,result:{steps:[single.details]}},[]);
 assert.ok(walk(host).some(node=>node.textContent==='历史版本只显示工具计算'));
 renderRecords(host,{...state,revision:3},[]);
 assert.equal(walk(host).filter(node=>node.tag==='article').length,0);
 assert.ok(walk(host).some(node=>node.textContent==='暂无执行记录。'));
}));

test('every new records sentence and full model/tool summaries translate without Chinese fragments',()=>{
 install(en);
 for (const label of ['执行记录','模型调用','工具计算','历史版本只显示工具计算','暂无执行记录。','查看 prompt 与 response',
  '正在读取调用日志…','日志中没有对应记录','调用日志读取失败，请收起后重试。',...Object.values(purposeNames),
  '调制方式','接收灵敏度','要求余量','是否满足','满足','不满足','本机模型','链路余量计算',modelLine(records(state,model)[0]),
  toolLine(records(state,[single])[0]),toolLine(records(state,[composite])[0]),
  ...Object.entries(composite.details.arguments).map(([name,value])=>parameterLine({[name]:value}))]) {
  assert.notEqual(t(label),label,label); assert.doesNotMatch(t(label),/[\u3400-\u9fff]/u,label);
 }
});
