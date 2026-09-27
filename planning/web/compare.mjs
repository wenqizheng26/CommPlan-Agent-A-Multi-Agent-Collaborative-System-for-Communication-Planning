// One line under a result produced by a follow-up swap: the version before that follow-up, then this one.
const NAMES={fspl_ghz:'路径损耗',received_power:'接收信号电平',link_margin:'链路余量'};
export function lastSwap(state){
 return [...(state?.conversation?.turns||[])].reverse().find(t=>t.followup&&t.applied)||null;
}
export function previousVersion(state,history){
 const swap=lastSwap(state);
 if(!swap||state.status!=='COMPLETED'||!state.final_report)return null;
 // The swap made the first version that carries its turn; compare with the last result before it.
 const made=history.filter(h=>h.state?.conversation?.turns?.some(t=>t.turn_id===swap.turn_id)).map(h=>h.revision);
 if(!made.length)return null;
 const before=history.filter(h=>h.revision<Math.min(...made)&&h.state?.status==='COMPLETED'&&h.state.final_report&&h.state.result)
  .sort((a,b)=>b.revision-a.revision||b.state_version-a.state_version)[0];
 return before?{state:before.state,swap}:null;
}
function outcome(state){
 const out=state.result?.outputs?.[0];if(!out||typeof out.value!=='number')return null;
 const req=state.final_report?.requirement;
 return `${out.value.toFixed(2)} ${out.unit}${req?(req.met?'，满足':'，不满足'):''}`;
}
export function comparisonLine(state,previous){
 if(!previous)return null;
 const before=outcome(previous.state),after=outcome(state);if(!before||!after)return null;
 const change=previous.swap.changes?.[0];if(!change)return null;
 const name=NAMES[state.result?.model_id]||'结果';
 return `上一版（${change.before}）${name} ${before} → 本版（${change.after}）${after}`;
}
