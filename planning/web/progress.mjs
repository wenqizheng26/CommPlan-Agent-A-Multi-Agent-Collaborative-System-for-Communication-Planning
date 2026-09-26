import {nodeStates,relevantEvents} from './flow.mjs';
const labels=['需求理解','参数确认','专业计算','结果审查','结果生成'];
export function taskProgress(state,events=[],{dirty=false,historical=false}={}){
 const status=labels.map(()=> 'idle');
 let action='输入需求，开始筹划。';
 if(state){
  const n=nodeStates(state,events),relevant=relevantEvents(state,events);
  const last=relevant.at(-1),run=relevant.filter(e=>e.run_id===last?.run_id);
  const terminal=run.findLast(e=>e.node==='command'&&['rejected','cancelled','interrupted','committed','replayed'].includes(e.phase));
  const rollback=['rejected','cancelled','interrupted'].includes(terminal?.phase);
  if(state.status==='COMPLETED'&&state.final_report){status.fill('completed');action='结果已保存。可核对结果、公式与适用限制。';}
  else if(state.status==='AWAITING_INPUT'||state.status==='NEEDS_MODEL'){
   status[0]='waiting';action=state.waiting_reason||(state.status==='NEEDS_MODEL'?'当前目标或模型超出范围，请查看缺口说明。':'请补充或修正下方问题，已回答内容会保留。');
  }else if(state.status==='CANCELLED'){
   status[0]=state.report?'completed':'idle';status[1]='cancelled';action='任务已取消，未生成本版本正式结果。';
  }else if(state.status==='FAILED'){
   status[0]=state.report?'completed':'failed';status[state.confirmed_snapshot?2:1]='failed';action=state.failure?.message||'本次处理失败，请查看原因后修正。';
  }else{
   if(state.report)status[0]='completed';
   if(state.status==='RUNNING'){status[0]='running';action='正在理解需求，等待保存后再核对。';}
   if(state.status==='AWAITING_CONFIRMATION'){status[1]='waiting';action='请核对本版本参数、来源和模型假设，再确认计算。';}
   if(!rollback){
    if(n.calculation==='running'){status[0]=status[1]='completed';status[2]='running';action='正在执行确定性专业计算，结果尚未发布。';}
    if(n.validation==='running'||n.review==='running'){
     status[0]=status[1]=status[2]='completed';status[3]='running';action='正在校验和审查结果，正式报告尚未保存。';
    }
    if(n.publish==='running'||n.publish==='completed'){
     status[0]=status[1]=status[2]=status[3]='completed';status[4]='running';action='正在保存结果；保存完成后才显示正式报告。';
    }
   }
   if(rollback)action='上次操作未提交，请按当前保存版本继续核对。';
  }
 }
 if(historical)action='历史只读：'+action;
 if(dirty)action='输入已修改；当前显示上次保存版本，请保存修改后重新确认。';
 return {steps:labels.map((label,i)=>({label,status:status[i]})),action};
}

const STATUS={AWAITING_CONFIRMATION:'待确认',AWAITING_INPUT:'待补充',NEEDS_MODEL:'超出范围',FAILED:'失败',COMPLETED:'已完成',CANCELLED:'已取消'};
// The one sentence that says what to do now; the flow diagram shows where the task is.
export function headline(state,{busy=false,action=null,editing=false,historical=false,modelLabel='',ran=''}={}){
 if(historical)return {text:`第 ${state.revision} 版 · 只读`,sub:STATUS[state.status]||'',tone:'idle'};
 if(busy){
  if(action==='confirm')return {text:'计算中…',sub:'确定性求值',tone:'run'};
  if(action==='cancel')return {text:'取消中…',sub:'',tone:'run'};
  if(action==='restore')return {text:'恢复中…',sub:'',tone:'run'};
  return {text:'解析中…',sub:modelLabel,tone:'run'};
 }
 if(editing)return {text:'编辑原文中',sub:'保存后需重新确认',tone:'wait'};
 if(!state)return {text:'输入需求开始',sub:'支持：路径损耗 · 接收电平 · 链路余量',tone:'idle'};
 const open=(state.input_issues||[]).filter(q=>q.status==='open'),n=open.length,kinds=new Set(open.map(q=>q.kind));
 const only=(...k)=>n&&[...kinds].every(x=>k.includes(x));
 switch(state.status){
  case 'AWAITING_INPUT':
   if(only('missing'))return {text:`缺 ${n} 项参数`,sub:'在对话栏补充',tone:'wait'};
   if(only('conflict'))return {text:`${n} 处冲突`,sub:'在对话栏选定',tone:'wait'};
   if(only('clarification','pending','review'))return {text:`${n} 处待澄清`,sub:'在对话栏说明',tone:'wait'};
   return {text:n?`${n} 项待处理`:'待补充',sub:'见对话栏',tone:'wait'};
  case 'NEEDS_MODEL':return {text:'超出计算范围',sub:'见对话栏',tone:'wait'};
  case 'AWAITING_CONFIRMATION':{
   const steps=state.report?.calculation_plan_proposal?.steps?.length;
   return {text:steps?`${steps} 步计算链 · 待确认`:'待确认',sub:'',tone:'wait'};
  }
  case 'COMPLETED':{
   const v=state.validations||[];
   return {text:v.length?`完成 · ${v.filter(x=>x.passed).length}/${v.length} 校验通过`:'完成',sub:ran,tone:'ok'};
  }
  case 'FAILED':return {text:'未完成',sub:state.failure?.message||'',tone:'bad'};
  case 'CANCELLED':return {text:'已取消',sub:'',tone:'idle'};
  default:return {text:'解析中…',sub:'',tone:'run'};
 }
}
