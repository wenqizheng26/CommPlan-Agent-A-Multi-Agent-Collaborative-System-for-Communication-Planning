// Display language. Chinese is the source text everywhere, including server messages;
// in English the page swaps rendered text through a dictionary (i18n-en.mjs) as it appears.
const KEY='planning-lang';
const HAN=/[㐀-鿿]/;
const SEP=/(，|；|：|。|？|！|、|（|）| · | → )/;
const PUNCT={'，':', ','；':'; ','：':': ','。':'. ','？':'? ','！':'! ','、':', ','（':' (','）':') ',' · ':' · ',' → ':' → '};
const STOP=new Set(['。','？','！']);
// Phrases that sit inside a sentence are written in lower case; a sentence start is raised.
const raise=s=>s.replace(/^[a-z]/,c=>c.toUpperCase());
let exact=new Map(),patterns=[];
const cache=new Map();

export function lang(){try{return localStorage.getItem(KEY)==='en'?'en':'zh';}catch{return 'zh';}}
export function setLang(value){try{localStorage.setItem(KEY,value==='en'?'en':'zh');}catch{}}
export function install(dict){exact=new Map(Object.entries(dict.EXACT||{}));patterns=dict.PATTERNS||[];cache.clear();}

function pattern(text,depth){
 for(const [re,rep] of patterns){
  const m=re.exec(text);
  // A captured part ($1: a field name, a model name, a server message) is translated in turn;
  // $=1 is inserted as written (a person's name, a quote).
  if(m)return rep.replace(/\$(=?)(\d)/g,(_,keep,i)=>keep?m[Number(i)]??'':find(m[Number(i)]??'',depth+1));
 }
 return undefined;
}
// A sentence built from known phrases: every Chinese segment must be known, or nothing is changed.
function segments(text,depth){
 const parts=text.split(SEP);if(parts.length<2)return undefined;
 let out='',start=false;
 for(let i=0;i<parts.length;i++){
  if(i%2){out+=PUNCT[parts[i]];start=STOP.has(parts[i]);continue;}
  const s=parts[i].trim();if(!s)continue;
  if(!HAN.test(s)){out+=s;start=false;continue;}
  const hit=exact.get(s)??pattern(s,depth);
  if(hit===undefined)return undefined;
  out+=start?raise(hit):hit;start=false;
 }
 return out.replace(/\s+([,.;:)])/g,'$1').replace(/\(\s+/g,'(').replace(/\s{2,}/g,' ').trim();
}
// A message of several sentences (a server reply often joins two): each sentence must be known.
function sentences(text,depth){
 const parts=text.match(/[^。？！]+[。？！]?/g)||[];if(parts.length<2)return undefined;
 const out=[];
 for(const part of parts){const s=part.trim(),hit=find(s,depth+1);if(hit===s&&HAN.test(s))return undefined;out.push(raise(hit));}
 return out.join(' ');
}
// A server error as the page shows it: the message, then its code in brackets.
const ERROR=/^([\s\S]+?) \[([A-Z][A-Z0-9_]*)(:[^\]]*)?\]$/;
function find(text,depth){
 const key=text.trim();
 if(!key||!HAN.test(key)||depth>4)return text;
 const hit=exact.get(key)??pattern(key,depth);
 if(hit!==undefined)return hit;
 const error=ERROR.exec(key);
 if(error)return find(error[1],depth+1)+' ['+error[2]+(error[3]||'')+']';
 return sentences(key,depth)??segments(key,depth)??key;
}
export function t(text){
 if(typeof text!=='string'||!HAN.test(text)||!exact.size&&!patterns.length)return text;
 let out=cache.get(text);
 if(out===undefined){
  const lead=text.match(/^\s*/)[0],trail=text.match(/\s*$/)[0],found=find(text,0);
  out=lead+(found!==text.trim()&&HAN.test(text.trim()[0])?raise(found):found)+(text.trim()?trail:'');
  if(cache.size>5000)cache.clear();
  cache.set(text,out);
 }
 return out;
}

// Text inside these is user content, code or raw data: never translated.
const SKIP='script,style,textarea,pre,[translate="no"]';
const ATTRS=['placeholder','title','aria-label'];
const written=new WeakMap();
function text(node){
 const parent=node.parentElement;
 if(!parent||parent.closest(SKIP)||written.get(node)===node.data)return;
 const out=t(node.data);
 if(out!==node.data){written.set(node,out);node.data=out;}
}
function attrs(el){
 if(el.closest('[translate="no"]'))return;
 for(const a of ATTRS){const v=el.getAttribute(a);if(v&&HAN.test(v)){const out=t(v);if(out!==v)el.setAttribute(a,out);}}
}
function tree(root){
 if(root.nodeType===3){text(root);return;}
 if(root.nodeType!==1)return;
 attrs(root);
 const walk=document.createTreeWalker(root,NodeFilter.SHOW_ELEMENT|NodeFilter.SHOW_TEXT);
 for(let n=walk.nextNode();n;n=walk.nextNode())n.nodeType===3?text(n):attrs(n);
}
export function watch(root=document.body){
 document.documentElement.lang='en';document.title=t(document.title);
 tree(root);document.documentElement.classList.remove('translating');
 new MutationObserver(records=>{
  for(const r of records){
   if(r.type==='characterData')text(r.target);
   else if(r.type==='attributes')attrs(r.target);
   else for(const n of r.addedNodes)tree(n);
  }
 }).observe(root,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:ATTRS});
}
