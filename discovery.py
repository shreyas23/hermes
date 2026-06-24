# Copyright (C) 2026 Shreyas Niradi. Licensed under AGPL-3.0.

"""Article discovery: Wikipedia search and RSS/Atom feed aggregation.

This module only *finds* articles and produces URLs. Importing is delegated to
the existing /api/import/url pipeline, so discovery never duplicates extraction
or audio logic.
"""

import calendar
import concurrent.futures
import json
import threading
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser

USER_AGENT = "Hermes/1.0 (local article reader)"
HTTP_TIMEOUT = 10
MAX_FEED_BYTES = 5 * 1024 * 1024

WIKI_SEARCH_URL = "https://en.wikipedia.org/w/rest.php/v1/search/page"
WIKI_ARTICLE_BASE = "https://en.wikipedia.org/wiki/"

ENTRIES_PER_FEED = 20
FEED_FETCH_WORKERS = 8
FEED_SUMMARY_MAX = 280

# In-memory TTL cache of normalized feed entries, keyed by feed URL.
CACHE_TTL = 300  # seconds
_cache: dict[str, tuple[float, list[dict]]] = {}
_cache_lock = threading.Lock()


# --- HTML stripping (feed/Wikipedia content is untrusted markup) ---


class _TagStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data):
        self._parts.append(data)

    def text(self):
        return "".join(self._parts)


def strip_html(value: str | None) -> str:
    if not value:
        return ""
    parser = _TagStripper()
    try:
        parser.feed(value)
    except Exception:
        return value
    return " ".join(parser.text().split())


# --- HTTP ---


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
        return resp.read(MAX_FEED_BYTES + 1)


# --- Wikipedia ---


def search_wikipedia(query: str, limit: int = 10) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []
    params = urllib.parse.urlencode({"q": query, "limit": limit})
    data = _get_json(f"{WIKI_SEARCH_URL}?{params}")
    results = []
    for page in data.get("pages", []):
        key = page.get("key")
        if not key:
            continue
        results.append(
            {
                "title": page.get("title") or key,
                "description": page.get("description") or "",
                "snippet": strip_html(page.get("excerpt")),
                "url": WIKI_ARTICLE_BASE + urllib.parse.quote(key),
            }
        )
    return results


# --- Feeds ---


def _parse_feed(url: str):
    import feedparser

    return feedparser.parse(_fetch_bytes(url))


def _normalize_entry(entry, feed_title: str) -> dict:
    ts = 0
    for key in ("published_parsed", "updated_parsed"):
        tm = entry.get(key)
        if tm:
            ts = calendar.timegm(tm)
            break
    summary = strip_html(entry.get("summary") or "")
    if len(summary) > FEED_SUMMARY_MAX:
        summary = summary[:FEED_SUMMARY_MAX].rstrip() + "…"
    return {
        "title": strip_html(entry.get("title") or "") or "(untitled)",
        "url": entry.get("link") or "",
        "summary": summary,
        "published": entry.get("published") or entry.get("updated") or "",
        "feed_title": feed_title,
        "ts": ts,
    }


def load_feed(url: str) -> tuple[dict, list]:
    """Validate a feed and return (metadata, raw entries). Raises ValueError if
    the URL is not a usable feed."""
    parsed = _parse_feed(url)
    entries = parsed.get("entries") or []
    if not entries:
        # feedparser sets .bozo instead of raising on malformed input.
        raise ValueError("No entries found — is this a valid RSS/Atom feed URL?")
    meta = parsed.get("feed", {})
    return {"title": meta.get("title") or url, "site_url": meta.get("link") or ""}, entries


def _cached_entries(feed: dict) -> list[dict]:
    url = feed["feed_url"]
    now = time.time()
    with _cache_lock:
        hit = _cache.get(url)
        if hit and now - hit[0] < CACHE_TTL:
            return hit[1]
    try:
        parsed = _parse_feed(url)
        title = feed.get("title") or parsed.get("feed", {}).get("title") or url
        entries = [_normalize_entry(e, title) for e in (parsed.get("entries") or [])[:ENTRIES_PER_FEED]]
    except Exception:
        entries = []
    with _cache_lock:
        _cache[url] = (now, entries)
    return entries


def fetch_entries(feeds: list[dict]) -> list[dict]:
    """Aggregate normalized entries across all feeds, newest first.

    Each feed is fetched concurrently and cached for CACHE_TTL seconds.
    """
    if not feeds:
        return []
    workers = min(FEED_FETCH_WORKERS, len(feeds))
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        batches = list(ex.map(_cached_entries, feeds))
    merged = [entry for batch in batches for entry in batch]
    merged.sort(key=lambda e: e["ts"], reverse=True)
    return merged
