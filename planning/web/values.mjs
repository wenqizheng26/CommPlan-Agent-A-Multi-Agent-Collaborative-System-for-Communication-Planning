export function formatDomain(value, digits=null){
 const fmt=n=>typeof n==='number'?(digits===null?String(n):n.toFixed(digits)):String(n??'');
 if(value&&typeof value==='object'){
  if(value.kind==='interval')return `${fmt(value.lower)}–${fmt(value.upper)}`;
  if(value.kind==='choices')return value.values.map(fmt).join(' / ');
 }
 return fmt(value);
}
