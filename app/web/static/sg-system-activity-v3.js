(() => {
"use strict";
const root=document.querySelector("[data-system-activity]");
if(!root)return;
const url=root.dataset.activityUrl;
let running=false;
const set=(name,value)=>{const node=root.querySelector(`[data-activity="${name}"]`);if(node)node.textContent=value};
const apply=(data)=>{
 set("today-total",data.today_total);set("today-pair",`↓ ${data.today_rx} · ↑ ${data.today_tx}`);
 set("month-total",data.month_total);set("month-pair",`↓ ${data.month_rx} · ↑ ${data.month_tx}`);
 set("last24-total",data.last24_total);set("peak24",data.peak_24h);set("updated","LIVE");
 if(data.clients){set("clients-total",String(data.clients.total));set("clients-note",`${data.clients.enabled} включено`);set("devices-total",String(data.clients.devices_total));set("devices-note",`${data.clients.devices_enabled} активно`)}
 const bars=Array.from(root.querySelectorAll("[data-activity-hour]"));
 if(Array.isArray(data.hourly))data.hourly.slice(-24).forEach((item,index)=>{const bar=bars[index];if(!bar)return;bar.style.setProperty("--sa2-level",`${Math.max(0,Number(item.level)||0)}%`);bar.dataset.title=`${item.label} · ${item.total_text}`});
};
async function tick(){if(running||document.hidden||!url)return;running=true;try{const response=await fetch(url,{headers:{"Accept":"application/json"},cache:"no-store"});if(!response.ok)throw new Error(String(response.status));apply(await response.json())}catch(_){set("updated","ожидание")}finally{running=false}}
tick();window.setInterval(tick,15000);
})();