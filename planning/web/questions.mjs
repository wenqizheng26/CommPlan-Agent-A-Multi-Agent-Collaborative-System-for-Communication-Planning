import {el,parameterNames} from './details.mjs';
import {formatDomain} from './values.mjs';

import {draftStore} from './drafts.mjs';
let storage;try{storage=globalThis.localStorage;}catch{}
const drafts=draftStore(storage);
export function openQuestions(state){return (state?.input_issues||[]).filter(q=>q.status==='open');}
export function questionTitle(state){const n=openQuestions(state).length;return `需求确认与补充 · ${n?`还有 ${n} 项待完成`:'当前无待完成项'}`;}
export function renderQuestions(host,state,{disabled=false,onSubmit,onEdit}={}){
 const questions=openQuestions(state);host.replaceChildren();host.hidden=!questions.length;host.classList.toggle('multi-question',questions.length>1);
 if(!disabled&&state?.task_id&&state.status!=='RUNNING')drafts.retain(state.task_id,state.revision,questions.map(q=>q.id));
 if(!questions.length)return;
 host.append(el('h2',questionTitle(state)),el('p',`${state.waiting_reason||'等待补充'}。可只回答已确定的项目，其余问题会保留；未提交的回答保留在本机浏览器；回答后仍需确认本版本才能计算。`,'hint'));
 const form=el('form');const inputs=[],cards=[],tabs=[];
 const nav=questions.length>1?el('div',undefined,'question-nav'):null;
 if(nav){nav.setAttribute('role','tablist');nav.setAttribute('aria-label','待确认项目');form.append(nav);}
 for(const [index,q] of questions.entries()){
  const card=el('fieldset',undefined,'question-card');card.id=`question-card-${index}`;card.hidden=index!==0;cards.push(card);
  card.append(el('legend',`${index+1}. ${q.title}`),el('p',q.detail,'hint'));
  if(nav){const tab=el('button',`${index+1}. ${q.title}`,'secondary');tab.type='button';tab.setAttribute('role','tab');tab.setAttribute('aria-controls',card.id);tab.setAttribute('aria-selected',String(index===0));tab.addEventListener('click',()=>{cards.forEach((item,i)=>item.hidden=i!==index);tabs.forEach((item,i)=>item.setAttribute('aria-selected',String(i===index)));});tabs.push(tab);nav.append(tab);}
  if(q.excerpt&&!q.excerpt.startsWith('issue-')&&q.kind!=='pending')card.append(el('blockquote','原文 / 来源：'+q.excerpt));
  const key=state.task_id+':'+state.revision+':'+q.id;
  if(q.field==='task'){
   const b=el('button','编辑当前任务','secondary');b.type='button';b.disabled=disabled;b.addEventListener('click',onEdit);card.append(b);
  }else{
   const input=el(q.choices.length?'select':'input');input.id='answer-'+q.id;input.setAttribute('aria-label',q.title);input.disabled=disabled;
   if(q.choices.length){const blank=el('option','暂不回答');blank.value='';input.append(blank);for(const choice of q.choices){const o=el('option',choice.label);o.value=choice.value;if(q.field==='goal'&&['link_feasibility','scheme_comparison'].includes(choice.value)){o.disabled=true;o.textContent+='（后续范围，当前不支持）';}input.append(o);}}
   else{input.type='text';input.maxLength=500;input.placeholder={distance_km:'例如 1km、1–2km',frequency_ghz:'例如 2GHz、2±0.1GHz、2GHz或3GHz'}[q.field]||'单个数值和单位';}
   input.value=drafts.get(key)||'';if(input.selectedOptions?.[0]?.disabled)input.value='';input.addEventListener('input',()=>drafts.set(key,input.value));card.append(input);inputs.push({input,id:q.id});
  }
  form.append(card);
 }
 if(inputs.length){const submit=el('button','提交已填写的回答并继续','primary');submit.type='submit';submit.disabled=disabled;form.append(submit);}
 form.addEventListener('submit',e=>{e.preventDefault();const answers=Object.fromEntries(inputs.filter(x=>x.input.value.trim()).map(x=>[x.id,x.input.value.trim()]));if(Object.keys(answers).length)onSubmit(answers);});
 host.append(form);
 const approximate=new Set((state.report?.diagnostics||[]).filter(d=>d.code==='PARAMETER_APPROXIMATE').map(d=>d.details.field));
 const known=(state.report?.parameters_proposal||[]).filter(p=>p.value!==null);
 if(known.length){const box=el('div',undefined,'known-inputs');box.append(el('h3','已理解的信息'));for(const p of known)box.append(el('p',`${parameterNames[p.canonical_name]||p.canonical_name}：${formatDomain(p.value)} ${p.unit}${approximate.has(p.canonical_name)?'（近似表达，尚待明确范围）':''}`));host.append(box);}
 if(state.resolved_input_issues?.length)host.append(el('p',`此前已处理 ${state.resolved_input_issues.length} 项；回答原文保留在任务历史中。`,'hint'));
}
