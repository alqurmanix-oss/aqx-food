/* AQX FOOD Blogger visitor Push adapter.
 * Isolated preparation only. Do not install until the same-origin SW URL is verified.
 */
(() => {
  "use strict";

  const defaults = {
    endpoint: "https://fkiokwwztbyztleeuwks.supabase.co/functions/v1/aqx-visitor-push",
    // Supply a unique registered site key per Blogger/GitHub origin; no fixed site count.
    siteKey: "",
    serviceWorkerUrl: "/aqx-blogger-push-sw.js",
    serviceWorkerScope: "/",
    // Set this to the selector of the already-existing icon. Do not rewrite its markup.
    triggerSelector: "",
    panelTitle: "إشعارات AQX FOOD",
  };

  const config = Object.assign({}, defaults, window.AQX_BLOGGER_PUSH_CONFIG || {});
  if (!config.siteKey || !/^[a-zA-Z0-9_-]{3,120}$/.test(config.siteKey)) {
    console.error("[AQX Push] Configure the registered siteKey for this origin before enabling.");
  }
  const TOKEN_KEY = "aqx_visitor_push_token_v1:" + (config.siteKey || "unconfigured");
  let panel;

  const b64url = (bytes) => {
    let binary = "";
    bytes.forEach((byte) => binary += String.fromCharCode(byte));
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "");
  };

  function visitorToken() {
    let token = "";
    try { token = localStorage.getItem(TOKEN_KEY) || ""; } catch (_) {}
    if (/^[A-Za-z0-9_-]{43,128}$/.test(token)) return token;
    const bytes = new Uint8Array(32);
    crypto.getRandomValues(bytes);
    token = b64url(bytes);
    try { localStorage.setItem(TOKEN_KEY, token); } catch (_) {}
    return token;
  }

  async function api(method, body) {
    const url = method === "GET"
      ? config.endpoint + "?site_key=" + encodeURIComponent(config.siteKey)
      : config.endpoint;
    const response = await fetch(url, {
      method,
      mode: "cors",
      cache: "no-store",
      headers: method === "POST" ? { "Content-Type": "application/json" } : {},
      body: method === "POST" ? JSON.stringify(body) : undefined,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok !== true) {
      const error = new Error(data.error || "notification_service_unavailable");
      error.status = response.status;
      throw error;
    }
    return data;
  }

  function statusText(message, isError) {
    const node = panel && panel.querySelector("[data-aqx-status]");
    if (!node) return;
    node.textContent = message;
    node.setAttribute("role", "status");
    node.style.color = isError ? "#a12638" : "#4b1f8f";
  }

  function ensurePanel() {
    if (panel) return panel;
    panel = document.createElement("section");
    panel.id = "aqx-blogger-push-panel";
    panel.dir = "rtl";
    panel.hidden = true;
    panel.setAttribute("aria-label", config.panelTitle);
    panel.innerHTML = [
      '<div class="aqx-bp-card">',
      '<button type="button" class="aqx-bp-close" aria-label="إغلاق">×</button>',
      '<strong class="aqx-bp-title"></strong>',
      '<p class="aqx-bp-copy">فعّل إشعارات AQX FOOD على هذا الجهاز إذا رغبت.</p>',
      '<button type="button" class="aqx-bp-enable">تفعيل الإشعارات</button>',
      '<button type="button" class="aqx-bp-disable">إيقاف الإشعارات</button>',
      '<p class="aqx-bp-status" data-aqx-status aria-live="polite"></p>',
      '</div>'
    ].join("");
    const style = document.createElement("style");
    style.textContent = [
      "#aqx-blogger-push-panel{position:fixed;z-index:2147483000;inset:auto 16px 16px auto;width:min(340px,calc(100vw - 32px));font:600 14px/1.7 Cairo,Tahoma,sans-serif;color:#35116d}",
      "#aqx-blogger-push-panel[hidden]{display:none}",
      "#aqx-blogger-push-panel .aqx-bp-card{position:relative;background:#fff;border:1px solid #e6dcf4;border-radius:18px;padding:22px;box-shadow:0 12px 40px #24104430}",
      "#aqx-blogger-push-panel .aqx-bp-close{position:absolute;left:12px;top:8px;border:0;background:transparent;font-size:25px;color:#4b1f8f;cursor:pointer}",
      "#aqx-blogger-push-panel .aqx-bp-title{display:block;font-size:17px;margin:0 30px 8px 0}",
      "#aqx-blogger-push-panel .aqx-bp-copy{margin:0 0 14px}",
      "#aqx-blogger-push-panel button.aqx-bp-enable,#aqx-blogger-push-panel button.aqx-bp-disable{display:block;width:100%;margin-top:8px;border-radius:10px;padding:10px 14px;font:700 14px Cairo,Tahoma,sans-serif;cursor:pointer}",
      "#aqx-blogger-push-panel .aqx-bp-enable{border:0;background:#4b1f8f;color:#fff}",
      "#aqx-blogger-push-panel .aqx-bp-disable{border:1px solid #4b1f8f;background:#fff;color:#4b1f8f}",
      "#aqx-blogger-push-panel .aqx-bp-status{min-height:1.7em;margin:10px 0 0;font-size:12px}"
    ].join("");
    document.head.appendChild(style);
    document.body.appendChild(panel);
    panel.querySelector(".aqx-bp-title").textContent = config.panelTitle;
    panel.querySelector(".aqx-bp-close").addEventListener("click", () => { panel.hidden = true; });
    panel.querySelector(".aqx-bp-enable").addEventListener("click", enablePush);
    panel.querySelector(".aqx-bp-disable").addEventListener("click", disablePush);
    return panel;
  }

  async function enablePush() {
    try {
      if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
        throw new Error("هذا المتصفح لا يدعم إشعارات الويب.");
      }
      if (!config.siteKey) throw new Error("لم يتم إعداد معرّف هذا الموقع في منظومة AQX.");
      const info = await api("GET");
      if (info.site_active !== true) {
        throw new Error("خدمة الإشعارات غير مفعّلة لهذا الموقع حتى الآن.");
      }
      if (Notification.permission === "denied") {
        throw new Error("إذن الإشعارات مرفوض من إعدادات المتصفح. غيّره يدويًا أولًا.");
      }
      const permission = Notification.permission === "granted"
        ? "granted"
        : await Notification.requestPermission();
      if (permission !== "granted") throw new Error("لم يتم منح إذن الإشعارات.");

      const registration = await navigator.serviceWorker.register(
        config.serviceWorkerUrl,
        { scope: config.serviceWorkerScope, updateViaCache: "none" }
      );
      await navigator.serviceWorker.ready;
      let subscription = await registration.pushManager.getSubscription();
      if (!subscription) {
        subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: decodeVapid(info.vapid_public_key),
        });
      }
      await api("POST", {
        action: "register",
        site_key: config.siteKey,
        visitor_token: visitorToken(),
        push_consent: true,
        subscription: subscription.toJSON(),
      });
      statusText("تم تفعيل الإشعارات على هذا الجهاز.", false);
    } catch (error) {
      statusText(error.message || "تعذر تفعيل الإشعارات.", true);
    }
  }

  async function disablePush() {
    try {
      const registration = await navigator.serviceWorker.getRegistration(config.serviceWorkerScope);
      const subscription = registration && await registration.pushManager.getSubscription();
      if (!subscription) {
        statusText("لا يوجد اشتراك إشعارات نشط على هذا الجهاز.", false);
        return;
      }
      await api("POST", {
        action: "unsubscribe",
        site_key: config.siteKey,
        visitor_token: visitorToken(),
        subscription: { endpoint: subscription.endpoint },
      });
      await subscription.unsubscribe();
      statusText("تم إيقاف الإشعارات على هذا الجهاز.", false);
    } catch (error) {
      statusText(error.message || "تعذر إيقاف الإشعارات.", true);
    }
  }

  function decodeVapid(value) {
    if (typeof value !== "string" || !/^[A-Za-z0-9_-]+$/.test(value)) {
      throw new Error("مفتاح الإشعارات غير صالح.");
    }
    const padded = value + "=".repeat((4 - value.length % 4) % 4);
    const raw = atob(padded.replace(/-/g, "+").replace(/_/g, "/"));
    return Uint8Array.from(raw, (char) => char.charCodeAt(0));
  }

  function bindExistingIcon() {
    if (!config.triggerSelector) {
      console.warn("[AQX Blogger Push] Set triggerSelector to the existing icon selector.");
      return;
    }
    const trigger = document.querySelector(config.triggerSelector);
    if (!trigger) {
      console.warn("[AQX Blogger Push] Existing icon not found:", config.triggerSelector);
      return;
    }
    trigger.addEventListener("click", (event) => {
      event.preventDefault();
      const target = ensurePanel();
      target.hidden = !target.hidden;
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindExistingIcon, { once: true });
  } else {
    bindExistingIcon();
  }
})();
