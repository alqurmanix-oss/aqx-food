/* AQX Blogger same-origin Service Worker bridge.
 * Deploy ONLY as a Cloudflare Worker route on the Blogger custom domain.
 * This does not work on a *.blogspot.com origin.
 */
const SERVICE_WORKER_SOURCE = "/* AQX FOOD Blogger visitor Push Service Worker.\n * Must be hosted at the Blogger origin root before registration can work.\n */\n\"use strict\";\n\nself.addEventListener(\"push\", (event) => {\n  let payload = {};\n  try {\n    payload = event.data ? event.data.json() : {};\n  } catch (_) {\n    payload = { body: event.data ? event.data.text() : \"\" };\n  }\n\n  const title = String(payload.title || \"AQX FOOD\").slice(0, 120);\n  const body = String(payload.body || \"\").slice(0, 300);\n  const requestedUrl = typeof payload.url === \"string\" ? payload.url : \"/\";\n  let target = \"/\";\n  try {\n    const parsed = new URL(requestedUrl, self.location.origin);\n    if (parsed.origin === self.location.origin) target = parsed.pathname + parsed.search + parsed.hash;\n  } catch (_) {}\n\n  event.waitUntil(self.registration.showNotification(title, {\n    body,\n    data: { target },\n    tag: \"aqx-food-\" + (payload.data && payload.data.event_id || \"notice\"),\n    renotify: false,\n    requireInteraction: false,\n  }));\n});\n\nself.addEventListener(\"notificationclick\", (event) => {\n  event.notification.close();\n  const target = event.notification.data && event.notification.data.target || \"/\";\n  event.waitUntil((async () => {\n    const url = new URL(target, self.location.origin);\n    if (url.origin !== self.location.origin) return;\n    const windows = await self.clients.matchAll({ type: \"window\", includeUncontrolled: true });\n    for (const client of windows) {\n      if (new URL(client.url).origin === self.location.origin) {\n        await client.navigate(url.href);\n        return client.focus();\n      }\n    }\n    return self.clients.openWindow(url.href);\n  })());\n});\n";

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname === "/aqx-blogger-push-sw.js") {
      if (request.method !== "GET" && request.method !== "HEAD") {
        return new Response("Method Not Allowed", { status: 405, headers: { "Allow": "GET, HEAD" } });
      }
      return new Response(request.method === "HEAD" ? null : SERVICE_WORKER_SOURCE, {
        status: 200,
        headers: {
          "Content-Type": "application/javascript; charset=utf-8",
          "Service-Worker-Allowed": "/",
          "Cache-Control": "no-store, max-age=0",
          "X-Content-Type-Options": "nosniff"
        }
      });
    }
    return fetch(request);
  }
};
