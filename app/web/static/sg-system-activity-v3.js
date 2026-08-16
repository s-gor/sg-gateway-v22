(() => {
"use strict";
const root=document.querySelector("[data-system-activity]");
if(!root)return;
const url=root.dataset.activityUrl;
let running=false;
const set=(name,value)=>{const node=root.querySelector(`[data-activity="${name}"]`);if(node)node.textContent=value};
const compact=(value)=>{const text=String(value||"");return text.length>34?`${text.slice(0,18)}…${text.slice(-12)}`:text};
const applyNetwork=(network)=>{
 if(!network)return;
 const cards=Array.from(document.querySelectorAll(".sv1-summary .sv1-summary-card"));
 const card=cards[3];if(!card)return;
 let mode=card.querySelector("[data-sg-network-mode]");
 let addresses=card.querySelector("[data-sg-network-addresses]");
 if(!mode){mode=document.createElement("div");mode.className="sv1-summary-note";mode.dataset.sgNetworkMode="1";card.querySelector("div:last-child")?.appendChild(mode)}
 if(!addresses){addresses=document.createElement("div");addresses.className="sv1-summary-note";addresses.dataset.sgNetworkAddresses="1";card.querySelector("div:last-child")?.appendChild(addresses)}
 const ipv4=String(network.ipv4||"");const ipv6=String(network.ipv6||"");
 if(mode)mode.textContent=network.dual_stack?"Dual Stack · IPv4 + IPv6":(ipv6?"IPv6":"IPv4");
 if(addresses){
   const parts=[];if(ipv4)parts.push(`IPv4 ${compact(ipv4)}`);if(ipv6)parts.push(`IPv6 ${compact(ipv6)}`);
   addresses.textContent=parts.join(" · ")||"Сетевой адрес определяется";
   addresses.title=[ipv4&&`IPv4 ${ipv4}`,ipv6&&`IPv6 ${ipv6}`].filter(Boolean).join("\n");
 }
};
const apply=(data)=>{
 set("today-total",data.today_total);set("today-pair",`↓ ${data.today_rx} · ↑ ${data.today_tx}`);
 set("month-total",data.month_total);set("month-pair",`↓ ${data.month_rx} · ↑ ${data.month_tx}`);
 set("last24-total",data.last24_total);set("peak24",data.peak_24h);set("updated","LIVE");
 if(data.clients){set("clients-total",String(data.clients.total));set("clients-note",`${data.clients.enabled} включено`);set("devices-total",String(data.clients.devices_total));set("devices-note",`${data.clients.devices_enabled} активно`)}
 applyNetwork(data.network);
 const bars=Array.from(root.querySelectorAll("[data-activity-hour]"));
 if(Array.isArray(data.hourly))data.hourly.slice(-24).forEach((item,index)=>{const bar=bars[index];if(!bar)return;bar.style.setProperty("--sa2-level",`${Math.max(0,Number(item.level)||0)}%`);bar.dataset.title=`${item.label} · ${item.total_text}`});
};
async function tick(){if(running||document.hidden||!url)return;running=true;try{const response=await fetch(url,{headers:{"Accept":"application/json"},cache:"no-store"});if(!response.ok)throw new Error(String(response.status));apply(await response.json())}catch(_){set("updated","ожидание")}finally{running=false}}
tick();window.setInterval(tick,15000);
})();