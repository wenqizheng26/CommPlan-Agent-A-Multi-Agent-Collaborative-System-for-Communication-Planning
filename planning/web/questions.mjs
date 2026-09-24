import {el} from './details.mjs';

import {draftStore} from './drafts.mjs';
let storage;try{storage=globalThis.localStorage;}catch{}
const drafts=draftStore(storage);
export function openQuestions(state){return (state?.input_issues||[]).filter(q=>q.status==='open');}
export function questionTitle(state){return openQuestions(state).length?'待补充':'无待补充项';}
const PLACEHOLDER={distance_km:'1km、1–2km',frequency_ghz:'2GHz、2±0.1GHz、2GHz或3GHz'};
const example=q=>PLACEHOLDER[q.field]||q.detail?.match(/例如\s*([^，。；）)]+)/)?.[1]||'数值和单位';
// All open questions in one form; partial answers are allowed and unsent input survives refresh.
export function renderQuestions(host,state,{disabled=false,onSubmit,onEdit}={}){
 const questions=openQuestions(state);host.replaceChildren();host.hidden=!questions.length;
 if(!disabled&&state?.task_id&&state.status!=='RUNNING')drafts.retain(state.task_id,state.revision,questions.map(q=>q.id));
 if(!questions.length)return;
 host.append(el('h3',questionTitle(state)));
 const form=el('form',undefined,'question-form'),inputs=[],submit=el('button','提交','primary compact');submit.type='submit';
 const count=()=>{const n=inputs.filter(x=>x.input.value.trim()).length;submit.textContent=n?`提交 ${n} 项`:'提交';submit.disabled=disabled||!n;};
 for(const q of questions){
  const simple=q.kind==='missing'&&q.field!=='task',row=el('div',undefined,`q-row ${simple?'simple':'wide'} kind-${q.kind}`);
  const label=el('label',q.title.replace(/^请补充/,''));label.htmlFor='answer-'+q.id;row.append(label);
  if(!simple&&q.detail)row.append(el('p',q.detail,'hint'));
  if(q.excerpt&&!q.excerpt.startsWith('issue-')&&q.kind!=='pending')row.append(el('blockquote',q.excerpt));
  if(q.field==='task'){const b=el('button','编辑原文','secondary compact');b.type='button';b.disabled=disabled;b.addEventListener('click',onEdit);row.append(b);}
  else{
   const input=el(q.choices.length?'select':'input');input.id='answer-'+q.id;input.dataset.field=q.field;input.disabled=disabled;
   if(q.choices.length){const blank=el('option','—');blank.value='';input.append(blank);for(const choice of q.choices){const o=el('option',choice.label);o.value=choice.value;if(q.field==='goal'&&['link_feasibility','scheme_comparison'].includes(choice.value)){o.disabled=true;o.textContent+='（暂不支持）';}input.append(o);}}
   else{input.type='text';input.maxLength=500;input.placeholder=example(q);}
   const key=state.task_id+':'+state.revision+':'+q.id;
   input.value=drafts.get(key)||'';if(input.selectedOptions?.[0]?.disabled)input.value='';
   input.addEventListener('input',()=>{drafts.set(key,input.value);count();});input.addEventListener('change',count);
   row.append(input);inputs.push({input,id:q.id});
  }
  form.append(row);
 }
 if(inputs.length){form.append(submit);count();}
 form.addEventListener('submit',e=>{e.preventDefault();const answers=Object.fromEntries(inputs.filter(x=>x.input.value.trim()).map(x=>[x.id,x.input.value.trim()]));if(Object.keys(answers).length)onSubmit(answers);});
 host.append(form);
}
