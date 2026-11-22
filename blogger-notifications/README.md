# AQX FOOD — Blogger visitor Push (isolated preparation)

**Status: prepared separately; not installed or deployed.**

This package is intentionally on branch `prep/blogger-notifications`, not the production branch. The adapter is designed for an expanding registry of Blogger and GitHub origins; it has no hard-coded blog-count ceiling. Each origin receives its own registered `site_key` and must satisfy that origin's Service Worker hosting requirements. It does not edit Blogger, the live homepage, the existing notification icon, the newsletter, Supabase functions, database rows, secrets, or schedules.

## Confirmed integration values

- Blogger origin: `https://food-aqx.blogspot.com`
- Initial Food site key: `aqx_food_blogger` (configuration example only; other registered origins use their own keys)
- Push endpoint: `https://fkiokwwztbyztleeuwks.supabase.co/functions/v1/aqx-visitor-push`
- Supabase project: `fkiokwwztbyztleeuwks`
- The site's current backend status was read as **pending**. The client intentionally refuses to register while the site is pending.
- The existing visitor endpoint requires explicit Push consent and stores a hash of a random visitor token. It does not collect visitor email.
- Visitors receive Push only. Email is not part of this visitor flow.

## Multi-site configuration

The shared client does not assume one fixed blog or one fixed site key. Configure `window.AQX_BLOGGER_PUSH_CONFIG` separately on each participating origin with that origin's unique `siteKey`, the same central endpoint, and a same-origin Service Worker URL. Visitor tokens are namespaced per site key. New sites are added through the platform/site registry; do not clone or hard-code an origin allowlist into the browser bundle. The existing server registry must authorize each new origin/site key before subscriptions can be accepted.

Example configuration (replace the key with the one issued for that site):

```html
<script>
window.AQX_BLOGGER_PUSH_CONFIG = {
  siteKey: "ISSUED_SITE_KEY",
  endpoint: "https://fkiokwwztbyztleeuwks.supabase.co/functions/v1/aqx-visitor-push",
  serviceWorkerUrl: "/aqx-blogger-push-sw.js",
  serviceWorkerScope: "/",
  triggerSelector: "YOUR_EXISTING_ICON_SELECTOR"
};
</script>
```

## Files

- `aqx-blogger-push.js`: opt-in client adapter. It fetches the public VAPID key, registers the worker, and registers/unregisters a visitor subscription only after an explicit click.
- `aqx-blogger-push-sw.js`: service worker source for displaying notifications and handling same-origin navigation.
- Repository-root `/aqx-blogger-push-sw.js`: root-scope worker copy for the GitHub Pages custom-domain origin.
- `github-pages-install-snippet.html`: ready-to-adapt GitHub Pages template using the registered GitHub site key.
- `blogger-notifications/cloudflare-blogger-worker.js` and `wrangler.toml`: prepared Cloudflare same-origin bridge for a Blogger blog that has first been moved to a Cloudflare-managed custom domain.
- `blogger-notifications/blogger-custom-domain-install.html`: Blogger snippet for that custom-domain arrangement.
- `blogger-install-snippet.html`: a separate installation snippet. It contains a placeholder selector for the existing icon; it does not change the icon's markup or SVG.
- `demo.html`: isolated UI preview. It performs no network requests and sends no notifications.

## Deployment status and origin constraints

**GitHub Pages:** the root worker and a separate install snippet are now present on this preparation branch. They become usable only after the branch is deployed to GitHub Pages at the configured custom domain, the exact worker URL returns JavaScript over HTTPS, and the server registry changes the site's status from pending to active. None of those deployment/activation steps has been performed here.

**Blogger:** the actual `https://food-aqx.blogspot.com` origin cannot use a worker hosted on GitHub Pages or another domain. A Cloudflare bridge has been prepared, but it requires the Blogger blog to be published on a custom domain whose DNS is managed/proxied by Cloudflare, with the Worker route attached to that exact custom domain. The current recorded Blogger setup is still `blogspot.com` with no custom domain. The bridge is not deployed, and no DNS or Blogger domain settings have been changed.

## Deployment checklist

### GitHub Pages
1. Deploy this preparation branch to GitHub Pages (or merge it only after review).
2. Confirm `https://food-aqx.alqurmanix.com/aqx-blogger-push-sw.js` returns HTTP 200, JavaScript MIME type, and the expected worker body.
3. Confirm the endpoint returns `site_active: true` for `aqx_food_github`.
4. Replace the icon selector in `github-pages-install-snippet.html` and add it to the GitHub Pages template.

### Blogger custom domain
1. Assign a dedicated custom domain to the Blogger blog and point/proxy it through the relevant Cloudflare zone. Do not reuse a hostname that currently serves the GitHub Pages site.
2. Replace `BLOG_CUSTOM_DOMAIN` and `CLOUDFLARE_ZONE_NAME` in `wrangler.toml`; deploy the Worker route only on that Blogger custom domain.
3. Confirm `https://BLOG_CUSTOM_DOMAIN/aqx-blogger-push-sw.js` returns HTTP 200, JavaScript MIME type, and `Service-Worker-Allowed: /`.
4. Confirm the endpoint returns `site_active: true` for `aqx_food_blogger`.
5. Replace the icon selector in `blogger-custom-domain-install.html` and add the snippet to the Blogger theme.

Do not deploy the Blogger bridge against a `*.blogspot.com` hostname. Do not activate either site's visitor subscription flow while its registry status is pending.

## Important Blogger hosting blocker — do not install yet

A browser Service Worker must be served as JavaScript from the **same origin** as the page, with an appropriate JavaScript MIME type, and its URL must be within the intended scope. For this Blogger origin, the worker needs to be reachable at:

`https://food-aqx.blogspot.com/aqx-blogger-push-sw.js`

Blogger themes do not provide a normal arbitrary root-file upload for `/aqx-blogger-push-sw.js`. A worker hosted on GitHub Pages, Supabase Storage, or another domain cannot control pages on `food-aqx.blogspot.com` because Service Workers are origin-bound.

Therefore this package is prepared, but real Push cannot be enabled until a same-origin root worker delivery path is verified. Do not paste the installation snippet into the live Blogger theme before that check.

## Safe test procedure

1. Preview `demo.html` locally; it is UI-only and makes no requests.
2. Verify the worker URL on the Blogger origin returns JavaScript (not an HTML Blogger page), with a JavaScript content type.
3. Verify `GET /functions/v1/aqx-visitor-push?site_key=aqx_food_blogger` from the Blogger origin returns `site_active: true` and a VAPID public key.
4. Only after both checks pass, bind `triggerSelector` to the existing icon's current selector. Do not edit its SVG or markup.
5. Obtain explicit visitor consent before requesting browser notification permission.
6. Test with one authorized test browser. Do not send a broadcast or test notification to real visitors.

## Security and behavior

- No service-role key, worker secret, or VAPID private key is exposed to the browser.
- No automatic permission prompt.
- No email capture or email channel for visitors.
- The client checks the active flag before subscription changes.
- Unsubscribe uses the same visitor token and endpoint.
- Notification click URLs are constrained to the Blogger origin.
- No edits are made to the newsletter or registered-user notification preferences.


## Current execution boundary

All additions are on `prep/blogger-notifications` only. The default branch, GitHub Pages settings, Cloudflare, Blogger settings, DNS, Supabase functions, database rows, secrets, and schedules have not been changed. No visitor notifications were sent.