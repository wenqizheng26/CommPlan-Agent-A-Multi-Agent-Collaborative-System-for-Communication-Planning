// Global model/retrieval defaults: sheet, header summary and per-result provenance.
export const ROLES=[['requirements','需求理解'],['supplement','补问合并'],['compute_agent','计算建议'],['validator_agent','结构化审查']];
export const RETRIEVAL={lexical:'词项',dense:'向量',hybrid:'混合'};
const STATUS={ready:'就绪',loading:'加载中',not_ready:'未就绪',unreachable:'未启动',not_installed:'未安装',unexpected:'端口被占用',unknown:'状态未知'};
const EMBED={ready:'就绪',loading:'预热中',cold:'未预热',not_installed:'未安装',failed:'加载失败',disabled:'未启用'};

export function factorySettings(models){
 return {mode_default:'deterministic',chat:{default:models.defaults.chat,roles:Object.fromEntries(ROLES.map(([r])=>[r,null]))},
  params:{temperature:null,timeout_s:null},retrieval:{mode:'lexical',embedding:models.defaults.embedding??null,top_k:8,top_n:3}};
}
const byId=(models,id)=>models?.models?.find(m=>m.id===id);
const shortName=(models,id)=>(byId(models,id)?.display_name||id||'').replace(' · Q4_K_M','');

export function summary(settings,models){
 if(!settings)return {badge:'设置载入中',lines:['正在载入模型与检索设置…']};
 const r=settings.retrieval,llm=settings.mode_default==='llm';
 const retrieval=`${RETRIEVAL[r.mode]}检索 · k = ${r.top_k} · n = ${r.top_n}`;
 return {badge:(llm?shortName(models,settings.chat.default):'确定性规则')+' · '+RETRIEVAL[r.mode]+'检索',
  lines:[llm?`本机模型 · ${shortName(models,settings.chat.default)}`:'确定性规则 · 不调用模型',retrieval]};
}

// What this saved result actually ran with, phase by phase.
export function provenance(state,models){
 const phases=state?.run_settings||{},rows=[];
 for(const [phase,name] of [['requirements','解析'],['calculation','计算与审查']]){
  const run=phases[phase];if(!run)continue;
  const ids=run.chat?[...new Set(Object.values(run.chat).map(b=>b.model_id))]:[];
  rows.push([`${name} · 模型`,run.chat?ids.map(id=>shortName(models,id)).join('、')+(ids.length>1?'（按角色）':''):'确定性规则，未调用模型']);
 }
 const found=state?.retrieval;
 if(found){
  let text=`${RETRIEVAL[found.mode_used]} · k = ${found.top_k} · n = ${found.top_n}`;
  if(found.degraded)text+=`（请求${RETRIEVAL[found.mode_requested]}，向量未就绪，已降为词项）`;
  rows.push(['知识检索',text]);
 }
 return rows;
}

// Differences between the defaults a result ran with and today's defaults. Never triggers a recalculation.
export function settingsDrift(state,settings){
 const run=state?.run_settings?.requirements;if(!run||!settings)return [];
 const now=settings.retrieval,then=run.retrieval,out=[];
 if(now.mode!==then.mode||now.top_k!==then.top_k||now.top_n!==then.top_n)out.push(`检索改为${RETRIEVAL[now.mode]} k = ${now.top_k} n = ${now.top_n}`);
 if(run.chat){
  const changed=ROLES.filter(([r])=>(settings.chat.roles[r]||settings.chat.default)!==run.chat[r]?.model_id);
  if(changed.length)out.push(`${changed.map(([,n])=>n).join('、')}的模型已更换`);
 }
 return out;
}

function segmented(el,options,value,onPick,label){
 const group=el('div',undefined,'segmented');group.setAttribute('role','group');group.setAttribute('aria-label',label);
 for(const [id,text] of options){const b=el('button',text,id===value?'selected':'');b.type='button';b.setAttribute('aria-pressed',String(id===value));b.addEventListener('click',()=>onPick(id));group.append(b);}
 return group;
}
function section(el,title,...children){const s=el('section',undefined,'sheet-section');s.append(el('h3',title),...children);return s;}

export function renderSettingsForm(host,{draft,models,status,corpus,el,onChange}){
 host.replaceChildren();
 const set=fn=>{fn(draft);onChange(draft);};
 const llm=draft.mode_default==='llm';
 host.append(section(el,'运行方式',segmented(el,[['deterministic','确定性规则'],['llm','本机模型']],draft.mode_default,v=>set(d=>{d.mode_default=v;}),'运行方式'),
  el('p',llm?'需求理解、补问、计算建议与审查可调用本机模型；不可用时明确降级。':'全程由登记规则处理，不调用模型。','hint')));

 const chats=models.models.filter(m=>m.kind==='chat'),list=el('div',undefined,'model-list');
 for(const m of chats){
  const row=el('label',undefined,'model-option'),radio=el('input');radio.type='radio';radio.name='chat-default';radio.value=m.id;
  radio.checked=draft.chat.default===m.id;radio.disabled=!m.strict;radio.addEventListener('change',()=>set(d=>{d.chat.default=m.id;}));
  const text=el('span',undefined,'model-text');text.append(el('strong',m.display_name),
   el('small',`${m.runtime} · 上下文 ${m.context} · 超时 ${m.defaults?.timeout_s??30} s`+(m.strict?'':' · 不支持严格结构化输出')));
  const st=status?.[m.id]||'unknown';
  row.append(radio,text,el('span',STATUS[st]||st,'chip '+(st==='ready'?'ok':st==='loading'?'run':'')));list.append(row);
 }
 const roles=el('details',undefined,'sheet-details');roles.append(el('summary','按角色覆盖（4 个角色）'));
 for(const [role,name] of ROLES){
  const row=el('label',undefined,'role-row'),select=el('select');
  const follow=el('option',`跟随默认（${shortName(models,draft.chat.default)}）`);follow.value='';select.append(follow);
  for(const m of chats.filter(m=>m.strict)){const o=el('option',m.display_name);o.value=m.id;select.append(o);}
  select.value=draft.chat.roles[role]||'';select.addEventListener('change',()=>set(d=>{d.chat.roles[role]=select.value||null;}));
  row.append(el('span',name),select);roles.append(row);
 }
 host.append(section(el,'生成模型',list,el('p','在 config/models.json 登记并把权重放入 models/ 后，新模型出现在这里。运行期从不下载。','hint'),roles));
 if(!llm)host.lastChild.classList.add('dimmed');

 const r=draft.retrieval,embed=models.embeddings?.[r.embedding];
 const retrieval=section(el,'知识检索',segmented(el,Object.entries(RETRIEVAL),r.mode,v=>set(d=>{d.retrieval.mode=v;}),'检索方式'),
  el('p',{lexical:'只按关键词匹配，不需要向量模型。',dense:'只按语义相似度排序；向量模型未就绪时本次按词项检索并标明。',hybrid:'词项与向量两路排序后用 RRF 融合；向量未就绪时按词项检索并标明。'}[r.mode],'hint'));
 if(r.mode!=='lexical'){
  const row=el('label',undefined,'role-row'),select=el('select');
  for(const m of models.models.filter(m=>m.kind==='embedding')){const o=el('option',m.display_name);o.value=m.id;select.append(o);}
  select.value=r.embedding||'';select.addEventListener('change',()=>set(d=>{d.retrieval.embedding=select.value;}));
  row.append(el('span','向量模型'),select);retrieval.append(row);
  const st=embed?.status||'cold';
  retrieval.append(el('p',`状态：${EMBED[st]||st}`+(embed?.warm_ms?` · 预热用时 ${(embed.warm_ms/1000).toFixed(1)} s`:'')+'。冷启动实测约 48 s，保存后在后台预热。','hint'));
 }
 const slider=(id,text,value,max,apply)=>{
  const wrap=el('div',undefined,'slider'),head=el('div',undefined,'slider-head'),lab=el('label',text),out=el('output',String(value)),input=el('input');
  lab.htmlFor=id;input.id=id;input.type='range';input.min='1';input.max=String(max);input.value=String(value);
  input.addEventListener('input',()=>{out.textContent=input.value;});input.addEventListener('change',()=>set(d=>apply(d,Number(input.value))));
  head.append(lab,out);wrap.append(head,input);return wrap;
 };
 retrieval.append(slider('top-k','召回数 top-k',r.top_k,20,(d,v)=>{d.retrieval.top_k=v;d.retrieval.top_n=Math.min(d.retrieval.top_n,v);}),
  slider('top-n','送入模型 top-n',r.top_n,r.top_k,(d,v)=>{d.retrieval.top_n=Math.min(v,d.retrieval.top_k);}));
 const size=corpus?.size??0;
 retrieval.append(el('p',`知识库当前 ${size} 条：返回 ${Math.min(r.top_k,size)} 条，前 ${Math.min(r.top_n,size)} 条送入模型上下文。检索只提供候选与出处，公式仍须登记并经你确认后才计算。`,'hint'));
 host.append(retrieval);

 const expert=el('details',undefined,'sheet-details');expert.append(el('summary','专家选项'));
 const grid=el('div',undefined,'expert-grid');
 const number=(text,value,placeholder,attrs,apply)=>{const lab=el('label',text),input=el('input');input.type='number';Object.assign(input,attrs);input.placeholder=placeholder;input.value=value??'';
  input.addEventListener('change',()=>set(d=>apply(d,input.value===''?null:Number(input.value))));lab.append(input);return lab;};
 grid.append(number('temperature',draft.params.temperature,'模型默认',{min:0,max:1,step:0.1},(d,v)=>{d.params.temperature=v;}),
  number('超时（秒）',draft.params.timeout_s,'模型默认',{min:5,max:120,step:1},(d,v)=>{d.params.timeout_s=v;}));
 expert.append(grid,el('p','留空时使用各模型档案的默认值。失败的调用要等到超时才降级：本机实测审查失败 p95 为 30 s。','hint'));
 host.append(section(el,'专家',expert));
}
