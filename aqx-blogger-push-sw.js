/* AQX FOOD Blogger visitor Push Service Worker.
 * Must be hosted at the Blogger origin root before registration can work.
 */
"use strict";

self.addEventListener("push", (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch (_) {
    payload = { body: event.data ? event.data.text() : "" };
  }

  const title = String(payload.title || "AQX FOOD").slice(0, 120);
  const body = String(payload.body || "").slice(0, 300);
  const requestedUrl = typeof payload.url === "string" ? payload.url : "/";
  let target = "/";
  try {
    const parsed = new URL(requestedUrl, self.location.origin);
    if (parsed.origin === self.location.origin) target = parsed.pathname + parsed.search + parsed.hash;
  } catch (_) {}

  event.waitUntil(self.registration.showNotification(title, {
    body,
    data: { target },
    tag: "aqx-food-" + (payload.data && payload.data.event_id || "notice"),
    renotify: false,
    requireInteraction: false,
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = event.notification.data && event.notification.data.target || "/";
  event.waitUntil((async () => {
    const url = new URL(target, self.location.origin);
    if (url.origin !== self.location.origin) return;
    const windows = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const client of windows) {
      if (new URL(client.url).origin === self.location.origin) {
        await client.navigate(url.href);
        return client.focus();
      }
    }
    return self.clients.openWindow(url.href);
  })());
});
