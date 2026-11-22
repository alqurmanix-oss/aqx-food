(function(){
"use strict";
const API="https://fkiokwwztbyztleeuwks.supabase.co/functions/v1/aqx-visitor-push";
const SITE="aqx_food_github";
const TOKEN_KEY="aqx_push_visitor_v1";
const DISMISS_KEY="aqx_push_dismissed_v1";
const ACTIVE_KEY="aqx_push_registered_v1";
const $=(id)=>document.getElementById(id);
function b64urlToBytes(s){const p="=".repeat((4-s.length%4)%4);const b=atob((s+p).replace(/-/g,"+").replace(/_/g,"/"));const a=new Uint8Array(b.length);for(let i=0;i<b.length;i++)a[i]=b.charCodeAt(i);return a;}
function visitorToken(){let t=localStorage.getItem(TOKEN_KEY);if(!t){const a=new Uint8Array(32);crypto.getRandomValues(a);t=Array.from(a,x=>x.toString(16).padStart(2,"0")).join("");localStorage.setItem(TOKEN_KEY,t);}return t;}
async function config(){const r=await fetch(API+"?site_key="+encodeURIComponent(SITE),{method:"GET",cache:"no-store"});const j=await r.json();if(!r.ok||!j.ok)throw new Error(j.error||"config_failed");return j;}
async function post(action,subscription){const r=await fetch(API,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({action,site_key:SITE,visitor_token:visitorToken(),push_consent:true,subscription})});const j=await r.json();if(!r.ok||!j.ok)throw new Error(j.error||"request_failed");return j;}
function ui(){
 if($("aqx-push-ui"))return;
 const wrap=document.createElement("section");wrap.id="aqx-push-ui";wrap.dir="rtl";
 wrap.innerHTML='<div class="aqx-push-card"><button type="button" class="aqx-push-x" aria-label="إغلاق">×</button><div class="aqx-push-title">🔔 إشعارات AQX FOOD</div><p>فعّل الإشعارات ليصلك جديد الوصفات والمحتوى. لن نرسل إشعارات دون موافقتك.</p><button type="button" class="aqx-push-on">تفعيل الإشعارات</button><small class="aqx-push-msg" aria-live="polite"></small></div>';
 const style=document.createElement("style");style.textContent='#aqx-push-ui{position:fixed;z-index:2147483000;inset:auto 14px 14px 14px;display:none;font-family:Arial,sans-serif;color:#30234a}#aqx-push-ui .aqx-push-card{max-width:460px;margin:auto;background:#fff;border:1px solid #e6dcfa;border-radius:16px;padding:16px 18px;box-shadow:0 8px 32px #1b103522;position:relative}#aqx-push-ui .aqx-push-title{font-weight:700;color:#673ab7;font-size:17px;margin:0 30px 8px 0}#aqx-push-ui p{font-size:14px;line-height:1.7;margin:0 0 12px}#aqx-push-ui .aqx-push-on{background:#673ab7;color:white;border:0;border-radius:9px;padding:11px 18px;font-weight:700;cursor:pointer}#aqx-push-ui .aqx-push-x{position:absolute;left:12px;top:8px;border:0;background:#f4f0fa;border-radius:50%;width:30px;height:30px;font-size:22px;color:#5c4a76;cursor:pointer}#aqx-push-ui .aqx-push-msg{display:block;margin-top:9px;font-size:12px;color:#6b5b80}';
 document.head.appendChild(style);document.body.appendChild(wrap);
 wrap.querySelector(".aqx-push-x").onclick=()=>{localStorage.setItem(DISMISS_KEY,"1");wrap.style.display="none";};
 wrap.querySelector(".aqx-push-on").onclick=async()=>{const btn=wrap.querySelector(".aqx-push-on"),msg=wrap.querySelector(".aqx-push-msg");btn.disabled=true;msg.textContent="جارٍ التفعيل…";try{const c=await config();if(!c.site_active)throw new Error("الإشعارات غير مفعّلة للموقع بعد");const permission=await Notification.requestPermission();if(permission!=="granted")throw new Error("لم يتم السماح بالإشعارات");const reg=await navigator.serviceWorker.ready;let sub=await reg.pushManager.getSubscription();if(!sub)sub=await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:b64urlToBytes(c.vapid_public_key)});await post("register",sub.toJSON());localStorage.setItem(ACTIVE_KEY,"1");localStorage.removeItem(DISMISS_KEY);wrap.style.display="none";}catch(e){msg.textContent="تعذر التفعيل: "+e.message;}finally{btn.disabled=false;}};
}
async function start(){
 if(!("serviceWorker" in navigator)||!("PushManager" in window)||!("Notification" in window)||!window.isSecureContext)return;
 try{
  const c=await config();if(!c.site_active)return;
  await navigator.serviceWorker.register("/sw.js",{scope:"/"});
  const reg=await navigator.serviceWorker.ready;
  if(Notification.permission==="denied")return;
  let sub=await reg.pushManager.getSubscription();
  if(Notification.permission==="granted"&&sub){await post("register",sub.toJSON());localStorage.setItem(ACTIVE_KEY,"1");return;}
  if(!sub&&localStorage.getItem(ACTIVE_KEY)==="1"){localStorage.removeItem(ACTIVE_KEY);localStorage.removeItem(DISMISS_KEY);}
  if((Notification.permission==="default"||(Notification.permission==="granted"&&!sub))&&!localStorage.getItem(DISMISS_KEY)){ui();$("aqx-push-ui").style.display="block";}
 }catch(e){console.warn("AQX Push unavailable:",e);}
}
if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",start,{once:true});else start();
})();