import {formatDomain} from './values.mjs';

export function originLabel(parameter,facts={},cards={}){
 const origins=parameter?.origins||[];
 const kind=origins.some(o=>o.kind==='manual_form')?'manual_form':origins[0]?.kind;
 const origin=origins.find(o=>o.kind===kind),record=facts[(origin?.source_ref||'').split('#')[0]];
 const names={user_text:'原文',manual_form:'手填',site:'站点库',device:'设备库',default:'假设'};
 let tag=names[kind]||'原文',original=null;
 if(['site','device'].includes(kind)&&record?.simulated)tag+=' · 模拟';
 if(kind==='manual_form')for(const card of Object.values(cards)){
  const value=card?.parameters?.[parameter.canonical_name]?.default;
  if(value){original=value;tag+=`（原假设 ${formatDomain(value.value)} ${value.unit}）`;break;}
 }
 return {kind:kind==='manual_form'?'manual':kind==='user_text'?'text':kind||'text',tag,original,
  source:record?.source||null,editable:kind==='default'};
}

export function assumptionEdit(state,name,value){
 const parameter=state.report?.parameters_proposal?.find(p=>p.canonical_name===name);
 if(!parameter?.origins?.some(o=>o.kind==='default'))throw new Error('只能直接修改假设值');
 if(typeof value!=='string'||!value.trim()||!Number.isFinite(Number(value)))throw new Error('请输入有限数值');
 return {raw_text:state.request.raw_text,condition:state.request.condition,target:state.request.target,manual_parameters:{...structuredClone(state.request.manual_parameters||{}),
  [name]:{value:Number(value),unit:parameter.unit}}};
}

export function answerPresentation(final){
 const answer=final?.answer,review=final?.review;
 return {show:!!answer&&(!!answer.withheld||typeof answer.text==='string'&&!!answer.text.trim()),
  caution:review?.decision==='caution',label:review?.decision==='caution'?'请核对':'通过',
  text:answer?.withheld?'说明未通过数字核对，只显示逐步数值':answer?.text||'',
  opinions:(review?.opinions||[]).map(o=>`${{risk:'风险',assumption:'假设',suggestion:'建议'}[o.kind]||'意见'}：${o.text??'该条未通过数字核对'}`)};
}

export function horizonPresentation(state){
 if(state?.status!=='NEEDS_MODEL'||state.failure?.code!=='BEYOND_LINE_OF_SIGHT')return null;
 const d=state.failure.details||{};
 return {title:'超出视距，未计算',text:`直线距离 ${formatDomain(d.distance_km,2)} km · 无线电视距 ${formatDomain(d.radio_horizon_km,2)} km`,next:state.failure.next_action};
}

export function solvePresentation(solve){
 if(!solve)return null;
 if(solve.error)return {error:`反求没有结果：${{SOLVE_NO_ROOT:'搜索区间内无解',SOLVE_NOT_MONOTONIC:'结果不单调',SOLVE_BRACKET:'缺少搜索区间'}[solve.error]||solve.error}`};
 return {headline:`发射功率${solve.direction==='minimum'?'至少':'至多'} ${formatDomain(solve.value,2)} ${solve.unit}`,
  warning:solve.rated?.exceeded?`超过所选电台的额定发射功率 ${formatDomain(solve.rated.value)} ${solve.rated.unit}`:null,
  sides:['left','right'].map((key,i)=>`${i?'右':'左'}侧：${formatDomain(solve[key].unknown_value,6)} ${solve.unit} → ${formatDomain(solve[key].condition_value,6)} dB · ${solve[key].satisfies?'满足':'不满足'}`),
  detail:`${solve.iterations} 次迭代 · 残差 ${Number(solve.residual).toExponential(2)} dB`};
}

export function renderSolve(host,solve,el){
 const info=solvePresentation(solve);if(!info)return;
 const section=el('section',undefined,'detail-block solve');section.append(el('h3','反求发射功率'));
 if(info.error){section.append(el('p',info.error,'warning'));host.append(section);return;}
 section.append(el('strong',info.headline));if(info.warning)section.append(el('p',info.warning,'warn-text'));
 info.sides.forEach(text=>section.append(el('p',text,'hint')));section.append(el('p',info.detail,'hint'));
 const points=solve.samples||[];
 if(points.length>=2&&points.every(p=>Number.isFinite(p.unknown_value)&&Number.isFinite(p.condition_value))){
  const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg');svg.setAttribute('viewBox','0 0 500 220');svg.setAttribute('role','img');svg.setAttribute('aria-label','发射功率与链路余量曲线，含要求线和解');
  const make=(name,attrs,text)=>{const n=document.createElementNS(ns,name);Object.entries(attrs).forEach(([k,v])=>n.setAttribute(k,String(v)));if(text)n.textContent=text;svg.append(n);return n;};
  const xs=points.map(p=>p.unknown_value),ys=points.map(p=>p.condition_value),minX=Math.min(...xs),maxX=Math.max(...xs),minY=Math.min(...ys,solve.condition.value),maxY=Math.max(...ys,solve.condition.value);
  const x=v=>48+(v-minX)/(maxX-minX||1)*426,y=v=>180-(v-minY)/(maxY-minY||1)*145;
  make('path',{d:`M48 30V180H480`,fill:'none',stroke:'currentColor'});
  make('polyline',{points:points.map(p=>`${x(p.unknown_value)},${y(p.condition_value)}`).join(' '),fill:'none',stroke:'#176e8f','stroke-width':3});
  make('line',{x1:48,x2:474,y1:y(solve.condition.value),y2:y(solve.condition.value),stroke:'#b67500','stroke-dasharray':'5 4'});
  make('circle',{cx:x(solve.value),cy:y(solve.condition_value),r:5,fill:'#a43324'});
  make('text',{x:48,y:20},`余量（dB） · 要求 ${solve.condition.value} dB`);
  make('text',{x:300,y:210},'发射功率（dBm）');
  make('text',{x:48,y:197},String(minX));make('text',{x:450,y:197},String(maxX));
  make('text',{x:Math.min(x(solve.value)+8,375),y:y(solve.condition_value)-10},`${formatDomain(solve.value,2)} dBm`);
  section.append(svg);
 }
 host.append(section);
}

export function planPresentation(state){
 const r=state.report||{};
 if(state.status==='AWAITING_INPUT')return {title:'计划预览 · 程序拼链',assessment:null,reasons:{}};
 const plan=r.calculation_plan_proposal||{},model=plan.origin==='model',a=plan.assessment;
 const title=model?'计划 · 专业计算 Agent 编写 · 程序校验通过':plan.origin_note?`计划 · 程序拼链（模型计划未通过校验：${plan.origin_note}）`:'计划 · 程序拼链';
 return {title,assessment:a?.mode==='skipped'?null:a||null,skipped:a?.mode==='skipped',
  reasons:model?Object.fromEntries((plan.steps||[]).map(s=>[s.tool_id,s.why])):{}};
}

export function assessmentNoteText(note){return note.withheld?'该条未通过数字核对':note.text;}
