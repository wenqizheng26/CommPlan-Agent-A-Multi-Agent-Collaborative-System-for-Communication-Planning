import test from 'node:test';
import assert from 'node:assert/strict';
import {switchView} from '../planning/web/settings.mjs';

const models={models:[{id:'nine',kind:'chat',display_name:'Qwen3.5 9B · Q4_K_M',endpoint:'http://127.0.0.1:18081'},
 {id:'four',kind:'chat',display_name:'Qwen3 4B · Q4_K_M · 标准',endpoint:'http://127.0.0.1:18081'}]};
const draft=id=>({chat:{default:id,roles:{}}});

test('a loaded model needs no switch; another registered one offers it',()=>{
 assert.equal(switchView({draft:draft('nine'),models,status:{nine:'ready',four:'standby'}}),null);
 const view=switchView({draft:draft('four'),models,status:{nine:'ready',four:'standby'}});
 assert.equal(view.text,'Qwen3 4B · 标准 未加载。');
 assert.deepEqual(view.action,{label:'切换',disabled:false,title:''});
 assert.equal(switchView({draft:draft('four'),models,status:{four:'unreachable'}}).text,'Qwen3 4B · 标准 未启动。');
});

test('a running command locks the switch and says why',()=>{
 const view=switchView({draft:draft('four'),models,status:{four:'standby'},locked:'正在处理任务，完成后才能切换。'});
 assert.equal(view.action.disabled,true);
 assert.equal(view.hint,'正在处理任务，完成后才能切换。');
});

test('while switching the line shows the waiting time; afterwards how it went',()=>{
 const running=switchView({draft:draft('four'),models,status:{},switcher:{state:'switching',model_id:'four',elapsed_ms:12400}});
 assert.equal(running.text,'正在切换到 Qwen3 4B · 标准 · 已等待 12 s');
 assert.equal(running.action,undefined);
 const done={state:'done',model_id:'four',message:'已切换到 Qwen3 4B · 标准。'};
 assert.deepEqual(switchView({draft:draft('four'),models,status:{four:'ready'},switcher:done}),{tone:'ok',text:done.message});
 const failed={state:'failed',model_id:'four',message:'Qwen3 4B · 标准 未能启动：模型提前退出。已恢复 Qwen3.5 9B。'};
 const retry=switchView({draft:draft('four'),models,status:{four:'standby'},switcher:failed});
 assert.equal(retry.tone,'err');assert.equal(retry.text,failed.message);assert.equal(retry.action.label,'切换');
 // The message belongs to the model it was about.
 assert.equal(switchView({draft:draft('nine'),models,status:{nine:'ready'},switcher:failed}),null);
});

test('missing weights and a foreign program cannot be switched',()=>{
 assert.equal(switchView({draft:draft('four'),models,status:{four:'not_installed'}}).action,undefined);
 const foreign=switchView({draft:draft('four'),models,status:{four:'unexpected'}});
 assert.equal(foreign.text,'端口 18081 被其他程序占用，不能切换。');
 assert.equal(foreign.action,undefined);
});
