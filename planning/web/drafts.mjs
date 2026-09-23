export function draftStore(storage){
 const key='planning-answer-drafts-v1';let entries=[];
 try{const data=JSON.parse(storage?.getItem(key)||'[]');if(Array.isArray(data))entries=data.filter(x=>Array.isArray(x)&&x.length===2&&typeof x[0]==='string'&&typeof x[1]==='string'&&x[1].length<=500).slice(-200);}catch{}
 const values=new Map(entries);
 const save=()=>{while(values.size>200)values.delete(values.keys().next().value);try{storage?.setItem(key,JSON.stringify([...values]));}catch{}};
 return {get:k=>values.get(k),set(k,v){values.delete(k);values.set(k,v);save();},retain(task,revision,ids){const allowed=new Set(ids.map(id=>`${task}:${revision}:${id}`));for(const k of values.keys())if(k.startsWith(task+':')&&!allowed.has(k))values.delete(k);save();}};
}
