(() => {
  "use strict";
  const clamp=n=>Math.max(0,Math.min(100,n));
  const pct=t=>{const m=String(t||"").replace(",",".").match(/(-?\d+(?:\.\d+)?)\s*%/);return m?clamp(Number(m[1])):null;};
  function apply(selector,barSelector){
    const card=document.querySelector(selector); if(!card) return;
    const center=card.querySelector('.sv1-donut-center strong');
    const available=center?pct(center.textContent):null; if(available===null) return;
    const bar=card.querySelector(barSelector); if(bar) bar.style.width=`${clamp(100-available)}%`;
  }
  function all(){
    apply('[data-sg-memory-card="1"]','.sv1-peer-progress-memory .sv1-peer-progress-track > span');
    apply('[data-sg-disk-card="1"]','.sv1-disk-bar > span');
  }
  let scheduled=false; const schedule=()=>{if(scheduled)return; scheduled=true; requestAnimationFrame(()=>{scheduled=false;all();});};
  document.addEventListener('DOMContentLoaded',all);
  new MutationObserver(schedule).observe(document.documentElement,{childList:true,subtree:true,characterData:true});
})();
