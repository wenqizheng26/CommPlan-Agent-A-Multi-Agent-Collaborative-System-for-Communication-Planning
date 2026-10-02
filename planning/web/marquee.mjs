import {t} from './i18n.mjs';
// Header "current task": one line that scrolls only when the question does not fit.
const GAP=48,SPEED=40; // px between the two copies; px per second

// The question is shown as written; only the labels follow the page language.
export function headerText(active,state){
 const question=text=>(text||'').trim().replace(/\s+/g,' ');
 // A restore placeholder is not the question; show the saved one instead.
 if(active)return [t('处理中'),question(active.placeholder?state?.request?.raw_text:active.request?.raw_text)].filter(Boolean).join(' · ');
 return question(state?.request?.raw_text)||t('未开始');
}

// Rebuilt only when the text changes, so redraws while polling do not restart the scroll.
export function setMarquee(host,text){
 host.translate=false;
 if(host.dataset.text!==text){
  host.dataset.text=text;host.title=text;
  const track=document.createElement('span'),first=document.createElement('span');
  track.className='marquee-track';first.textContent=text;track.append(first);
  host.replaceChildren(track);host.classList.remove('scrolling');
 }
 fitMarquee(host);
}

export function fitMarquee(host){
 const track=host.firstElementChild,first=track?.firstElementChild;if(!first)return;
 const width=first.getBoundingClientRect().width,over=width>host.clientWidth+1;
 if(over===host.classList.contains('scrolling'))return;
 host.classList.toggle('scrolling',over);
 if(!over){first.nextElementSibling?.remove();return;}
 const copy=first.cloneNode(true);copy.setAttribute('aria-hidden','true');track.append(copy);
 track.style.setProperty('--marquee-shift',`-${Math.ceil(width+GAP)}px`);
 track.style.setProperty('--marquee-time',`${Math.max(6,(width+GAP)/SPEED).toFixed(1)}s`);
}
