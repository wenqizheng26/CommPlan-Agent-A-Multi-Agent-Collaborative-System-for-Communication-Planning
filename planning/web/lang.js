// English page: keep the Chinese source text hidden until app.js has swapped it, so it does not flash.
// If the swap never comes, the page shows anyway after three seconds.
try{
 if(localStorage.getItem('planning-lang')==='en'){
  const root=document.documentElement;root.classList.add('translating');
  setTimeout(()=>root.classList.remove('translating'),3000);
 }
}catch{}
