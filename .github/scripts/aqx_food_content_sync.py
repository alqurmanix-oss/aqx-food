#!/usr/bin/env python3
"""Sync AQX-authored Blogger posts into the private AQX Food recipe staging area.

This does not publish recipes or create canonical ingredients. It stores source
snapshots only; nutrition claims in blog content are not treated as nutrient data.
"""
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

FEED_BASE = "https://aqxfood.blogspot.com/feeds/posts/default"
GATEWAY = os.environ.get(
    "AQX_FOOD_CONTENT_SYNC_URL",
    "https://vuszqzgldbsscuxdfhdz.supabase.co/functions/v1/aqx-food-github-content-sync",
).rstrip("/")
AUDIENCE = "aqx-food-content-sync"
BATCH_SIZE = 8
MAX_POSTS = 1000
MAX_HTML_CHARS = 120000

INGREDIENT_CLASSES = {
    "aqx-ing-name", "aqx-ingredient-name", "aqx-ing-title",
    "aqx-ing-amount", "aqx-ingredient-amount", "aqx-ing-card",
    "aqx-ingredient-card", "aqx-ing-item", "aqx-ingredient-item",
    "aqx-ingredients-grid", "aqx-ing-list", "aqx-ingredients-list",
    "aqx-ingredients-section", "aqx-ingredients-box", "aqx-ingredient-list",
}
RECIPE_TITLE_RE = re.compile(
    r"(وصفة|شوربة|سمبوسة|سلطة|برجر|برياني|بسبوسة|مكرونة|باستا|عجينة|"
    r"كفتة|بسكويت|خشاف|معجنات|بابا غنوج|فطير|أومليت|تغميسة|ساندويتش|"
    r"قلاية|عصير|دجاج|طاجن|حمص|فطائر|كيك|كوكيز|recipe)",
    re.IGNORECASE,
)
NON_RECIPE_TITLE_RE = re.compile(
    r"(تحميل.*(?:كتاب|كتب)|كتاب.*(?:مطبخ|طهي)|\bPDF\b|تنظيف|الأرضيات|"
    r"ممسحة|معطرات|مخطط الوجبات|حيل ذكية|10 استخدامات|من بقايا العشاء|"
    r"إعادة تدوير الطعام|قشور الفاكهة|نصائح منزلية)",
    re.IGNORECASE,
)


class RecipeSignals(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.has_ingredient_markup = False
        self.has_recipe_schema = False
        self.has_ingredient_heading = False
        self.has_method_heading = False
        self.heading_tag = None
        self.heading_text = []
        self.in_jsonld = False
        self.jsonld_text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = set((attrs.get("class") or "").lower().split())
        if classes.intersection(INGREDIENT_CLASSES):
            self.has_ingredient_markup = True
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.heading_tag = tag
            self.heading_text = []
        if tag == "script" and "ld+json" in (attrs.get("type") or "").lower():
            self.in_jsonld = True
            self.jsonld_text = []

    def handle_data(self, data):
        if self.heading_tag:
            self.heading_text.append(data)
        if self.in_jsonld:
            self.jsonld_text.append(data)

    def handle_endtag(self, tag):
        if self.heading_tag == tag:
            heading = " ".join(self.heading_text)
            if re.search(r"(مقادير|المكونات|المقادير|ingredients)", heading, re.I):
                self.has_ingredient_heading = True
            if re.search(r"(طريقة التحضير|خطوات التحضير|طريقة عمل|instructions|method)", heading, re.I):
                self.has_method_heading = True
            self.heading_tag = None
            self.heading_text = []
        if tag == "script" and self.in_jsonld:
            raw = " ".join(self.jsonld_text)
            if "recipeIngredient" in raw or re.search(r'"@type"\s*:\s*"Recipe"', raw):
                self.has_recipe_schema = True
            self.in_jsonld = False
            self.jsonld_text = []


def http_json(url, headers=None, timeout=45):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "AQX-Food-Content-Sync/1.0", **(headers or {})},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8")), response.status


def fetch_all_posts():
    start = 1
    entries = []
    total = None
    feed_updated = None
    last_status = None

    while True:
        query = urllib.parse.urlencode({
            "alt": "json",
            "max-results": 50,
            "start-index": start,
        })
        feed_data, last_status = http_json(f"{FEED_BASE}?{query}")
        feed = feed_data.get("feed") or {}
        if total is None:
            try:
                total = int((feed.get("openSearch$totalResults") or {}).get("$t", 0))
            except (TypeError, ValueError):
                total = 0
        feed_updated = (feed.get("updated") or {}).get("$t") or feed_updated
        page = feed.get("entry") or []
        if not page:
            break
        entries.extend(page)
        if len(entries) > MAX_POSTS:
            raise RuntimeError(f"Blogger feed exceeded safety limit of {MAX_POSTS} posts")
        if total and len(entries) >= total:
            break
        if len(page) < 50:
            break
        start += len(page)

    if total is not None and total > 0 and len(entries) != total:
        raise RuntimeError(f"Incomplete Blogger feed: expected {total}, received {len(entries)}")
    if not entries:
        raise RuntimeError("AQX Blogger feed returned no posts")
    return entries, feed_updated, last_status


def make_record(entry):
    post_id = str((entry.get("id") or {}).get("$t") or "")
    match = re.search(r"\.post-(\d+)$", post_id)
    if not match:
        raise RuntimeError(f"Could not extract Blogger post ID from {post_id!r}")
    external_id = match.group(1)

    links = entry.get("link") or []
    source_url = next((x.get("href", "") for x in links if x.get("rel") == "alternate"), "")
    if not source_url.startswith("https://aqxfood.blogspot.com/"):
        raise RuntimeError(f"Unexpected AQX recipe source URL: {source_url!r}")

    title = str((entry.get("title") or {}).get("$t") or "").strip()
    html_content = str((entry.get("content") or {}).get("$t") or "")
    if not title or not html_content:
        raise RuntimeError(f"Post {external_id} is missing title or full content")
    if len(title) > 300 or len(html_content) > MAX_HTML_CHARS:
        raise RuntimeError(f"Post {external_id} exceeds the safe title/content size limit")

    signals = RecipeSignals()
    signals.feed(html_content)
    excluded = bool(NON_RECIPE_TITLE_RE.search(title))
    title_signal = bool(RECIPE_TITLE_RE.search(title))
    is_recipe = not excluded and (
        signals.has_recipe_schema
        or signals.has_ingredient_markup
        or (signals.has_ingredient_heading and (signals.has_method_heading or title_signal))
    )

    reasons = []
    if signals.has_recipe_schema:
        reasons.append("recipe_schema")
    if signals.has_ingredient_markup:
        reasons.append("ingredient_markup")
    if signals.has_ingredient_heading:
        reasons.append("ingredient_heading")
    if signals.has_method_heading:
        reasons.append("method_heading")
    if title_signal:
        reasons.append("recipe_title")
    if excluded:
        reasons = ["non_recipe_editorial_title"]
    if not reasons:
        reasons = ["no_recipe_signals"]

    labels = [
        str(item.get("term"))
        for item in (entry.get("category") or [])
        if item.get("term")
    ]
    authors = entry.get("author") or []
    author_name = (authors[0].get("name") or {}).get("$t") if authors else None

    return {
        "external_record_id": external_id,
        "source_url": source_url,
        "title": title,
        "author_name": author_name,
        "published_at": (entry.get("published") or {}).get("$t"),
        "source_updated_at": (entry.get("updated") or {}).get("$t"),
        "labels": labels,
        "raw_content_html": html_content,
        "is_recipe_candidate": is_recipe,
        "recipe_signal": "+".join(reasons),
    }


def oidc_token():
    request_url = os.environ["ACTIONS_ID_TOKEN_REQUEST_URL"]
    request_token = os.environ["ACTIONS_ID_TOKEN_REQUEST_TOKEN"]
    parts = urllib.parse.urlsplit(request_url)
    params = [
        (key, value)
        for key, value in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
        if key != "audience"
    ]
    params.append(("audience", AUDIENCE))
    url = urllib.parse.urlunsplit((
        parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(params), parts.fragment
    ))
    data, _ = http_json(url, headers={"Authorization": f"Bearer {request_token}"}, timeout=30)
    token = data.get("value")
    if not token:
        raise RuntimeError("GitHub Actions OIDC token response did not contain a value")
    return token


def gateway(payload, token):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        GATEWAY,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "AQX-Food-Content-Sync/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:700]
        raise RuntimeError(f"Content gateway HTTP {exc.code}: {detail}") from exc


def version_from_feed(feed_updated):
    if feed_updated:
        date_part = str(feed_updated)[:10]
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_part):
            return f"blogger-{date_part}"
    return "blogger-" + dt.datetime.now(dt.timezone.utc).date().isoformat()


def main():
    version = "blogger-" + dt.datetime.now(dt.timezone.utc).date().isoformat()
    records = []
    inserted = 0
    updated = 0
    http_status = None
    token = None
    finished = False

    try:
        entries, feed_updated, http_status = fetch_all_posts()
        version = version_from_feed(feed_updated)
        records = [make_record(entry) for entry in entries]
        candidates = sum(1 for item in records if item["is_recipe_candidate"])
        print(json.dumps({
            "event": "aqx_blogger_feed_fetched",
            "dataset_version": version,
            "posts_received": len(records),
            "recipe_candidates": candidates,
            "non_recipe_posts": len(records) - candidates,
            "http_status": http_status,
        }, ensure_ascii=False), flush=True)

        token = oidc_token()
        for offset in range(0, len(records), BATCH_SIZE):
            batch = records[offset:offset + BATCH_SIZE]
            result = gateway({"action": "batch", "records": batch}, token)
            inserted += int(result.get("inserted") or 0)
            updated += int(result.get("updated") or 0)
            print(json.dumps({
                "event": "aqx_content_batch_synced",
                "batch_number": offset // BATCH_SIZE + 1,
                "records": len(batch),
                "inserted": int(result.get("inserted") or 0),
                "updated": int(result.get("updated") or 0),
                "processed": int(result.get("processed") or 0),
            }), flush=True)

        finish = gateway({
            "action": "finish",
            "dataset_version": version,
            "records_received": len(records),
            "records_inserted": inserted,
            "records_updated": updated,
            "http_status": http_status,
            "error": None,
        }, token)
        finished = True
        print(json.dumps({"event": "aqx_content_sync_finished", **finish}, ensure_ascii=False), flush=True)

    except Exception as exc:
        message = str(exc)[:1000]
        print(json.dumps({"event": "aqx_content_sync_error", "error": message}), file=sys.stderr, flush=True)
        if token is None:
            try:
                token = oidc_token()
            except Exception as token_error:
                print(f"Could not obtain OIDC token for failure reporting: {token_error}", file=sys.stderr)
        if token is not None and not finished:
            try:
                finish = gateway({
                    "action": "finish",
                    "dataset_version": version,
                    "records_received": len(records),
                    "records_inserted": inserted,
                    "records_updated": updated,
                    "http_status": http_status,
                    "error": message,
                }, token)
                print(json.dumps({"event": "aqx_content_sync_failure_recorded", **finish}, ensure_ascii=False), flush=True)
            except Exception as finish_error:
                print(f"Could not record sync failure: {finish_error}", file=sys.stderr)
        raise


if __name__ == "__main__":
    main()
