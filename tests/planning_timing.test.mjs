import test from 'node:test';
import assert from 'node:assert/strict';
import {spans,nodeLatency,stepTimes,runSummary,fmt} from '../planning/web/timing.mjs';
import {settingsDrift,provenance,summary} from '../planning/web/settings.mjs';

const at=ms=>new Date(Date.UTC(2026,8,23,0,0,0,ms)).toISOString();
const ev=(run,node,phase,ms,details={})=>({run_id:run,task_id:'t',revision:0,node,phase,at:at(ms),details});
const confirmRun=[
 ev('r2','command','started',0,{action:'confirm'}),ev('r2','calculation','started',10),
 ev('r2','llm','started',20,{caller:'compute_agent',purpose:'compute_agent',timeout_s:30}),
 ev('r2','llm','failed',2020,{caller:'compute_agent',purpose:'compute_agent',reason:'offline'}),
 ev('r2','model','started',2030),ev('r2','model','completed',2037),ev('r2','calculation','completed',2040),
 ev('r2','validation','started',2050),ev('r2','validation','completed',2055),
 ev('r2','review','started',2060),ev('r2','review','completed',3060),
 ev('r2','publish','started',3070),ev('r2','publish','completed',3079),ev('r2','command','committed',3100)];

test('spans pair start and end per run and model purpose',()=>{
 const {done,open}=spans(confirmRun);
 assert.equal(open.length,0);
 const llm=done.find(s=>s.key==='llm/compute_agent');
 assert.equal(llm.ms,2000);assert.equal(llm.phase,'failed');assert.equal(llm.details.reason,'offline');
});

test('node latency and step times come from the last run of each node',()=>{
 const lat=nodeLatency(confirmRun);
 assert.equal(lat.compute_agent,'2.03 s');assert.equal(lat.model,'7.0 ms');assert.equal(lat.llm,'2.00 s');
 assert.equal(lat.validator_agent,'1.00 s');
 assert.deepEqual(stepTimes(confirmRun),['','','2.03 s','1.00 s','9.0 ms']);
});

test('a running model call shows elapsed time against its timeout',()=>{
 const running=[ev('r1','command','started',0),ev('r1','requirements','started',5),
  ev('r1','llm','started',10,{caller:'requirements',purpose:'intent',timeout_s:12})];
 const lat=nodeLatency(running,Date.parse(at(5010)));
 assert.equal(lat.llm,'已等待 5 s / 超时 12 s');assert.equal(lat.requirements,lat.llm);
});

test('run summary reports total, model share and failed calls of the committed run',()=>{
 assert.equal(runSummary(confirmRun),'本次 3.10 s，其中模型 65%，模型调用失败 1 次。');
 assert.equal(runSummary(confirmRun.slice(0,-1)),'');
 assert.equal(fmt(3.04),'3.0 ms');assert.equal(fmt(12.6),'13 ms');
});

const models={defaults:{chat:'a'},models:[{id:'a',kind:'chat',display_name:'Qwen3 4B · Q4_K_M · 标准'},{id:'b',kind:'chat',display_name:'Qwen3 4B · Q4_K_M · 快速失败'}]};
const settings=(over={})=>({mode_default:'llm',chat:{default:'a',roles:{requirements:null,supplement:null,compute_agent:null,validator_agent:null}},
 params:{temperature:null,timeout_s:null},retrieval:{mode:'lexical',embedding:null,top_k:8,top_n:3},...over});
const binding=id=>({model_id:id});
const state={run_settings:{requirements:{mode:'llm',chat:{requirements:binding('a'),supplement:binding('a'),compute_agent:binding('a'),validator_agent:binding('a')},
 retrieval:{mode:'lexical',top_k:8,top_n:3}}},retrieval:{mode_requested:'hybrid',mode_used:'lexical',degraded:true,top_k:8,top_n:3}};

test('drift lists only changed retrieval and role models',()=>{
 assert.deepEqual(settingsDrift(state,settings()),[]);
 const changed=settings({retrieval:{mode:'hybrid',embedding:'e',top_k:5,top_n:2}});
 changed.chat.roles.validator_agent='b';
 assert.deepEqual(settingsDrift(state,changed),['检索改为混合 k = 5 n = 2','结构化审查的模型已更换']);
 assert.deepEqual(settingsDrift({},changed),[]);
});

test('provenance names the model and says when retrieval degraded',()=>{
 const rows=Object.fromEntries(provenance(state,models));
 assert.equal(rows['解析 · 模型'],'Qwen3 4B · 标准');
 assert.match(rows['知识检索'],/请求混合，向量未就绪/);
 assert.equal(summary(settings(),models).badge,'Qwen3 4B · 标准 · 词项检索');
 assert.equal(summary(settings({mode_default:'deterministic'}),models).badge,'确定性规则 · 词项检索');
});
