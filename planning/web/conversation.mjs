import {formatDomain} from './values.mjs';
import {el,parameterNames} from './details.mjs';
const modeNames={user_answer:'逐项回答',deterministic:'规则合并',llm_grounded:'大模型理解 · 原话核验',deterministic_fallback:'规则接管',manual_edit:'直接编辑'};
function value(v){if(Array.isArray(v))return v.length?v.map(value).join(' / '):'未填写';if(v&&typeof v==='object')return v.kind?formatDomain(v):`${formatDomain(v.value)} ${v.unit}`;return String(v??'未填写');}
// Each supplement is kept as said; only the newest turn starts open.
export function renderConversation(host,state,{open}={}){
 host.replaceChildren();const c=state?.conversation;if(!c?.turns?.length)return;
 const fold=(key,summary,byDefault)=>{const d=el('details',undefined,'turn'),saved=open?.get(key);if(saved??byDefault)d.open=true;d.addEventListener('toggle',()=>open?.set(key,d.open));d.append(el('summary',summary));return d;};
 const original=c.original_input||state.request,initial=fold('turn:original','最初输入',false);
 initial.append(el('p',original.raw_text,'turn-text'));
 if(Object.keys(original.manual_parameters||{}).length)initial.append(el('pre',JSON.stringify(original.manual_parameters,null,2)));
 host.append(initial);
 for(const turn of c.turns){
  const pending=(c.pending||[]).some(p=>p.turn_id===turn.turn_id);
  const card=fold('turn:'+turn.turn_id,`第 ${turn.number} 条 · ${turn.kind==='answer'?'回答':turn.kind==='edit'?'编辑':turn.applied?'已合并':pending?'待澄清':'已处理'}`,turn===c.turns.at(-1));
  card.append(el('p',turn.message,'turn-text'),el('p',modeNames[turn.mode]||turn.mode,'hint'));
  for(const change of turn.changes){
   if(change.field==='task')continue;
   // Merged fields record the whole description as "before"; show only the new value then.
   const name=parameterNames[change.field]||({condition:'条件',pending:'补充状态'})[change.field]||change.field;
   const snapshot=typeof change.before==='string'&&change.before===turn.before?.raw_text;
   const after=typeof change.after==='string'&&change.after===turn.after?.raw_text?'已更新':value(change.after);
   card.append(el('p',snapshot?`${name} → ${after}`:`${name}：${value(change.before)} → ${after}`,'change-line'));
  }
  for(const text of turn.diagnostics||[])card.append(el('p',text,'hint'));
  if(!turn.applied)card.append(el('p',pending?'尚未合并，等待说明':'已由后续补充处理，原话保留','hint'));
  const versions=el('details');versions.append(el('summary','修改前后'),el('p','前：'+turn.before.raw_text,'turn-text'),el('p','后：'+turn.after.raw_text,'turn-text'));card.append(versions);host.append(card);
 }
}
