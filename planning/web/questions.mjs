import {el,raw} from './details.mjs';

import {draftStore} from './drafts.mjs';
let storage;try{storage=globalThis.localStorage;}catch{}
const drafts=draftStore(storage);
export function openQuestions(state){return (state?.input_issues||[]).filter(q=>q.status==='open');}
export function questionTitle(state){return openQuestions(state).length?'待补充':'无待补充项';}
const PLACEHOLDER={distance_km:'1km、1–2km',frequency_ghz:'2GHz、2±0.1GHz、2GHz或3GHz'};
const example=q=>PLACEHOLDER[q.field]||q.detail?.match(/例如\s*([^，。；）)]+)/)?.[1]||'数值和单位';
// Goal choices from reviewed cards come in groups: dedicated programs first, then generic cards, then cards needing a program.
export const GROUPS={generic:'其他已入库公式（通用计算）',needs_tool:'需专用程序（暂不能计算）'};
export function fillChoices(select,choices,option){
 const groups={};
 for(const c of choices){
  const o=option(c);if(!c.group){select.append(o);continue;}
  if(!groups[c.group]){groups[c.group]=el('optgroup');groups[c.group].label=GROUPS[c.group]||c.group;}
  groups[c.group].append(o);
 }
 for(const g of Object.values(groups))select.append(g);
}
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
  if(q.excerpt&&!q.excerpt.startsWith('issue-')&&q.kind!=='pending')row.append(raw('blockquote',q.excerpt));
  if(q.field==='task'){const b=el('button','编辑原文','secondary compact');b.type='button';b.disabled=disabled;b.addEventListener('click',onEdit);row.append(b);}
  else{
   const input=el(q.choices.length?'select':'input');input.id='answer-'+q.id;input.dataset.field=q.field;input.disabled=disabled;
   if(q.choices.length){const blank=el('option','—');blank.value='';input.append(blank);fillChoices(input,q.choices,choice=>{const o=el('option',choice.label);o.value=choice.value;
    if(q.field==='goal'&&['link_feasibility','scheme_comparison'].includes(choice.value)){o.disabled=true;o.textContent+='（暂不支持）';}
    else if(choice.disabled){o.disabled=true;if(choice.group!=='needs_tool')o.textContent+=/已停用/.test(choice.reason||'')?'（公式卡已停用）':'（暂不可用）';}
    return o;});}
   else{input.type='text';input.maxLength=500;input.placeholder=example(q);}
   const key=state.task_id+':'+state.revision+':'+q.id;
   // A suggested table value is prefilled until the user types something else (TEACHER_CASES).
   input.value=drafts.get(key)??q.suggestion?.value??'';if(input.selectedOptions?.[0]?.disabled)input.value='';
   input.addEventListener('input',()=>{drafts.set(key,input.value);count();});input.addEventListener('change',()=>{drafts.set(key,input.value);count();});
   row.append(input);inputs.push({input,id:q.id,suggestion:q.suggestion?.value});
   if(q.suggestion){const note=el('p',undefined,'hint suggestion-note');note.append(el('span',q.suggestion.note,'tag suggested'),el('span',' '+q.suggestion.reason));row.append(note);}
  }
  form.append(row);
 }
 const suggested=inputs.filter(x=>x.suggestion);
 if(suggested.length){
  // One click adopts every suggestion; the other answers typed so far go with them.
  const adopt=el('button',`全部采用默认值（${suggested.length} 项）`,'secondary compact');adopt.type='button';adopt.disabled=disabled;
  adopt.addEventListener('click',()=>{for(const x of suggested)x.input.value=x.suggestion;
   const answers=Object.fromEntries(inputs.filter(x=>x.input.value.trim()).map(x=>[x.id,x.input.value.trim()]));onSubmit(answers);});
  form.append(adopt);
 }
 if(inputs.length){form.append(submit);count();}
 form.addEventListener('submit',e=>{e.preventDefault();const answers=Object.fromEntries(inputs.filter(x=>x.input.value.trim()).map(x=>[x.id,x.input.value.trim()]));if(Object.keys(answers).length)onSubmit(answers);});
 host.append(form);
}
