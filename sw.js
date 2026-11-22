"use strict";
self.addEventListener("install", event => self.skipWaiting());
self.addEventListener("activate", event => event.waitUntil(self.clients.claim()));
self.addEventListener("push", event => {
  let payload = {};
  try { payload = event.data ? event.data.json() : {}; } catch (_) {
    payload = { body: event.data ? event.data.text() : "" };
  }
  const title = String(payload.title || "AQX FOOD").slice(0,120);
  const options = {
    body: String(payload.body || "هناك جديد في AQX FOOD").slice(0,500),
    icon: "/assets/icon-192.png",
    badge: "/assets/icon-192.png",
    dir: "rtl",
    lang: "ar",
    tag: "aqx-food-update",
    renotify: false,
    data: { url: payload.url || payload.action_url || "/" }
  };
  event.waitUntil(self.registration.showNotification(title, options));
});
self.addEventListener("notificationclick", event => {
  event.notification.close();
  const raw = event.notification.data && event.notification.data.url || "/";
  let target = "/";
  try {
    const u = new URL(raw, self.location.origin);
    if (u.origin === self.location.origin) target = u.href;
  } catch (_) {}
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of windows) {
      if (new URL(client.url).origin === self.location.origin) {
        await client.focus();
        if ("navigate" in client) await client.navigate(target);
        return;
      }
    }
    await self.clients.openWindow(target);
  })());
});