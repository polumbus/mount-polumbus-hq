"""Read-only twitterapi.io ingestion for Tyler voice profile analysis."""

from __future__ import annotations

import json
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

from .config import artifact_path, load_twitterapiio_key, read_jsonl, redact_secrets, write_jsonl


READ_ONLY_ENDPOINT = "/twitter/tweet/advanced_search"
WRITE_DENYLIST = ("post", "write", "like", "repost", "retweet", "bookmark", "favorite", "delete")


def _assert_read_only(endpoint: str) -> None:
    low = endpoint.lower()
    if any(term in low for term in WRITE_DENYLIST):
        raise RuntimeError(f"refusing non-read endpoint: {endpoint}")


def month_windows(months: int = 12, *, window_days: int = 7) -> list[tuple[datetime, datetime]]:
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=max(1, int(months)) * 31)
    windows = []
    cur = start
    while cur < end:
        nxt = min(cur + timedelta(days=window_days), end)
        windows.append((cur, nxt))
        cur = nxt
    return windows


def build_query(username: str, start: datetime, end: datetime) -> str:
    handle = username.lstrip("@").strip()
    since = start.date().isoformat()
    until = (end.date() + timedelta(days=1)).isoformat()
    return f"from:{handle} since:{since} until:{until}"


def _window_cache_name(start: datetime, end: datetime) -> str:
    return f"raw/twitterapiio_windows/{start.date().isoformat()}_{end.date().isoformat()}.jsonl"


def fetch_window(api_key: str, query: str, *, count: int = 100, max_pages: int = 5, timeout: int = 35) -> list[dict]:
    _assert_read_only(READ_ONLY_ENDPOINT)
    rows = []
    cursor = ""
    for _ in range(max_pages):
        params = {"query": query, "queryType": "Latest", "count": min(100, count), "cursor": cursor}
        resp = requests.get(
            "https://api.twitterapi.io" + READ_ONLY_ENDPOINT,
            headers={"X-API-Key": api_key},
            params=params,
            timeout=timeout,
        )
        if resp.status_code >= 400:
            raise RuntimeError(redact_secrets(f"twitterapi.io HTTP {resp.status_code}: {resp.text[:240]}"))
        data = resp.json()
        tweets = data.get("tweets", []) if isinstance(data, dict) else []
        for tweet in tweets:
            rows.append({"source_system": "twitterapi.io", "query": query, "tweet": tweet})
        cursor = str((data or {}).get("next_cursor") or (data or {}).get("nextCursor") or "")
        if not cursor or not tweets:
            break
    return rows


def ingest_twitterapiio(username: str, *, months: int = 12, root=None, window_days: int = 7, max_pages_per_window: int = 5) -> dict:
    api_key = load_twitterapiio_key()
    if not api_key:
        raise RuntimeError("TWITTER_API_IO_KEY is not configured")
    all_rows = []
    window_meta = []
    for start, end in month_windows(months, window_days=window_days):
        query = build_query(username, start, end)
        cache_path = artifact_path(_window_cache_name(start, end), root)
        error = ""
        if cache_path.exists():
            rows = read_jsonl(cache_path)
            source = "cache"
        else:
            try:
                rows = fetch_window(api_key, query, max_pages=max_pages_per_window)
                write_jsonl(cache_path, rows)
                source = "live"
            except Exception as exc:
                rows = []
                source = "error"
                error = redact_secrets(exc)
        all_rows.extend(rows)
        window_meta.append({
            "query": query,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "tweet_count": len(rows),
            "source": source,
            "error": error,
            "cache_path": str(cache_path),
        })
    raw_path = artifact_path("raw/twitterapiio_last_12_months.jsonl", root)
    write_jsonl(raw_path, all_rows)
    meta_path = artifact_path("raw/twitterapiio_windows.json", root)
    meta_path.write_text(json.dumps({"username": username, "months": months, "windows": window_meta}, indent=2), encoding="utf-8")
    error_count = sum(1 for item in window_meta if item.get("error"))
    return {"raw_path": str(raw_path), "window_meta_path": str(meta_path), "tweet_count": len(all_rows), "window_count": len(window_meta), "window_error_count": error_count}
