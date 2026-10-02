// One line under a result produced by a follow-up swap: the version before that follow-up, then this one.
const NAMES={fspl_ghz:'路径损耗',received_power:'接收信号电平',link_margin:'链路余量'};
export function lastSwap(state){
 return [...(state?.conversation?.turns||[])].reverse().find(t=>t.followup&&t.applied)||null;
}
// Two inputs are the same task when the text and the explicit parameters match.
function sameInput(a,b){
 const key=x=>JSON.stringify([x?.raw_text,x?.condition??null,x?.target??null,Object.entries(x?.manual_parameters||{}).sort()]);
 return key(a)===key(b);
}
export function previousVersion(state,history){
 const swap=lastSwap(state);
 if(!swap||state.status!=='COMPLETED'||!state.final_report)return null;
 // The swap made the first version that carries its turn; compare with the last result before it.
 const made=history.filter(h=>h.state?.conversation?.turns?.some(t=>t.turn_id===swap.turn_id)).map(h=>h.revision);
 if(!made.length)return null;
 const before=history.filter(h=>h.revision<Math.min(...made)&&h.state?.status==='COMPLETED'&&h.state.final_report&&h.state.result)
  .sort((a,b)=>b.revision-a.revision||b.state_version-a.state_version)[0];
 // Only the result of the very input the swap changed: an older result differs in more than the swap.
 return before&&sameInput(before.state.request,swap.before)?{state:before.state,swap}:null;
}
function outcome(state){
 const out=state.result?.outputs?.[0];if(!out||typeof out.value!=='number')return null;
 const req=state.final_report?.requirement;
 return `${out.value.toFixed(2)} ${out.unit}${req?(req.met?'，满足':'，不满足'):''}`;
}
export function comparisonLine(state,previous){
 if(!previous)return null;
 const before=outcome(previous.state),after=outcome(state);if(!before||!after)return null;
 const changes=previous.swap.changes||[];if(!changes.length)return null;
 const name=NAMES[state.result?.model_id]||'结果',side=key=>changes.map(c=>c[key]).join('、');
 return `上一版（${side('before')}）${name} ${before} → 本版（${side('after')}）${after}`;
}
