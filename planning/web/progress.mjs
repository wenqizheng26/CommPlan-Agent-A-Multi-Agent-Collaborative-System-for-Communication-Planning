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
