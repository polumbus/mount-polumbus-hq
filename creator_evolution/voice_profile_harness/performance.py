"""Performance scoring for voice profile cohorts."""

from __future__ import annotations

import math


def _per_1k(value: int, views: int) -> float:
    return round((float(value or 0) / max(1, int(views or 0))) * 1000, 3)


def score_snapshot(snapshot: dict) -> dict:
    views = int(snapshot.get("views") or snapshot.get("impressions") or 0)
    age = float(snapshot.get("age_hours_at_snapshot") or 0)
    replies = int(snapshot.get("replies") or 0)
    reposts = int(snapshot.get("reposts") or 0)
    likes = int(snapshot.get("likes") or 0)
    quotes = int(snapshot.get("quotes") or 0)
    bookmarks = int(snapshot.get("bookmarks") or 0)
    engagements = int(snapshot.get("engagements") or (likes + replies + reposts + quotes + bookmarks))
    age_factor = max(1.0, math.sqrt(max(1.0, age) / 24.0))
    age_adjusted_view_score = round(math.log1p(views) * 10 / age_factor, 3)
    reply_rate = _per_1k(replies, views)
    repost_rate = _per_1k(reposts, views)
    like_rate = _per_1k(likes, views)
    quote_rate = _per_1k(quotes, views)
    bookmark_rate = _per_1k(bookmarks, views)
    safe_engagement = round((reply_rate * 2.3) + (repost_rate * 2.0) + quote_rate + bookmark_rate + (like_rate * 0.35), 3)
    normalized = round(age_adjusted_view_score + safe_engagement, 3)
    return {
        "tweet_id": snapshot.get("tweet_id", ""),
        "views_per_age_score": age_adjusted_view_score,
        "likes_per_1k_views": like_rate,
        "replies_per_1k_views": reply_rate,
        "reposts_per_1k_views": repost_rate,
        "quotes_per_1k_views": quote_rate,
        "bookmarks_per_1k_views": bookmark_rate,
        "engagements_per_1k_views": _per_1k(engagements, views),
        "age_adjusted_view_score": age_adjusted_view_score,
        "format_adjusted_score": normalized,
        "topic_adjusted_score": normalized,
        "monetization_safe_engagement_score": safe_engagement,
        "normalized_score": normalized,
    }


def index_latest_snapshots(snapshots: list[dict]) -> dict[str, dict]:
    latest: dict[str, dict] = {}
    for snap in snapshots:
        tid = str(snap.get("tweet_id") or "")
        if not tid:
            continue
        if tid not in latest or str(snap.get("snapshot_at_utc", "")) > str(latest[tid].get("snapshot_at_utc", "")):
            latest[tid] = snap
    return latest


def score_all(snapshots: list[dict]) -> dict[str, dict]:
    return {tid: score_snapshot(snap) for tid, snap in index_latest_snapshots(snapshots).items()}
