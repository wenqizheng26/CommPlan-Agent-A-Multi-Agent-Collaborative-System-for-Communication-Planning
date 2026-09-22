import {formatDomain} from './values.mjs';
import {el,parameterNames} from './details.mjs';
const modeNames={user_answer:'用户逐项回答',deterministic:'规则核验与合并',llm_grounded:'本机模型理解 · 原话核验',deterministic_fallback:'模型不可用或建议无效 · 规则合并',manual_edit:'用户直接编辑'};
function value(v){if(Array.isArray(v))return v.length?v.map(value).join(' / '):'未填写';if(v&&typeof v==='object')return v.kind?formatDomain(v):`${formatDomain(v.value)} ${v.unit}`;return String(v??'未填写');}
export function renderConversation(host,state){
 host.replaceChildren();if(!state){host.append(el('p','任务开始后，可在下方持续补充；每次补充都会保留。','hint'));return;}
 const c=state.conversation,original=c?.original_input||state.request;
 const initial=el('details');initial.append(el('summary','最初输入（保留）'),el('p',original.raw_text,'conversation-text'));
 if(Object.keys(original.manual_parameters||{}).length)initial.append(el('pre',JSON.stringify(original.manual_parameters,null,2)));
 host.append(initial);
 for(const turn of c?.turns||[]){
  const card=el('details',undefined,'conversation-turn');card.open=turn==c.turns.at(-1);
  const pending=(c.pending||[]).some(p=>p.turn_id===turn.turn_id);
  card.append(el('summary',`第 ${turn.number} 条 · ${turn.kind==='answer'?'已保存回答':turn.kind==='edit'?'直接编辑':turn.applied?'已合并 / 已处理':pending?'待澄清':'疑问已处理（原话保留）'}`));
  card.append(el('p',turn.message,'conversation-text'),el('p',modeNames[turn.mode]||turn.mode,'hint'));
  for(const change of turn.changes)card.append(el('p',`${parameterNames[change.field]||({task:'描述',condition:'条件',pending:'补充状态'})[change.field]||change.field}：${value(change.before)} → ${value(change.after)}`,'change-line'));
  for(const text of turn.diagnostics||[])card.append(el('p',text,'hint'));
  if(!turn.applied)card.append(el('p',pending?'尚未合并，等待明确说明。':'后续补充或编辑已处理这条疑问，原话保留。','hint'));
  const versions=el('details');versions.append(el('summary','查看本次修改前后描述'),el('p','修改前：'+turn.before.raw_text,'conversation-text'),el('p','修改后：'+turn.after.raw_text,'conversation-text'));card.append(versions);host.append(card);
 }
}
