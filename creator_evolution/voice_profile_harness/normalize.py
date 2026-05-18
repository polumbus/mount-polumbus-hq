"""Normalize raw X/twitterapi.io/archive rows into the harness schema."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from .config import utc_now_iso


TEAM_ALIASES = {
    "Broncos": ("broncos", "bo nix", "sean payton", "denver broncos"),
    "Nuggets": ("nuggets", "jokic", "jamal murray", "denver nuggets"),
    "Avalanche": ("avs", "avalanche", "mackinnon", "cale makar", "colorado avalanche"),
    "Rockies": ("rockies", "colorado rockies"),
    "Buffs": ("buffs", "coach prime", "deion", "cu football", "colorado buffaloes"),
}
SPORT_ALIASES = {
    "NFL": ("nfl", "broncos", "quarterback", "offensive line", "qb", "coach payton"),
    "NBA": ("nba", "nuggets", "jokic", "basketball"),
    "NHL": ("nhl", "avs", "avalanche", "hockey"),
    "MLB": ("mlb", "rockies", "baseball"),
    "College Football": ("coach prime", "buffs", "cu football", "college football"),
}


def _dig(data: dict, *keys: str, default: Any = "") -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key, default)
    return cur


def _metric(raw: dict, *names: str) -> int:
    for name in names:
        value = raw.get(name)
        if value is None and "public_metrics" in raw:
            value = raw.get("public_metrics", {}).get(name)
        try:
            if value not in ("", None):
                return int(float(value))
        except Exception:
            continue
    return 0


def parse_datetime(value: object) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            dt = datetime.fromisoformat(candidate)
            if not dt.tzinfo:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            pass
    for fmt in ("%a %b %d %H:%M:%S %z %Y", "%Y-%m-%d %H:%M:%S%z"):
        try:
            return datetime.strptime(text, fmt).astimezone(timezone.utc)
        except Exception:
            pass
    return None


def clean_text(text: object) -> str:
    text = str(text or "")
    text = re.sub(r"https?://t\.co/\S+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _listify(value: Any) -> list:
    if not value:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _urls(raw: dict, text: str) -> list[str]:
    urls = []
    entities = raw.get("entities") or {}
    for item in _listify(entities.get("urls")) + _listify(raw.get("urls")):
        if isinstance(item, dict):
            urls.append(str(item.get("expanded_url") or item.get("url") or ""))
        else:
            urls.append(str(item))
    urls.extend(re.findall(r"https?://\S+", text))
    return [u for u in dict.fromkeys(urls) if u]


def _labels(text: str, aliases: dict[str, tuple[str, ...]]) -> list[str]:
    low = text.lower()
    return [label for label, keys in aliases.items() if any(key in low for key in keys)]


def _mentions(text: str) -> list[str]:
    return sorted(set(re.findall(r"@([A-Za-z0-9_]{1,20})", text)))


def _hashtags(text: str) -> list[str]:
    return sorted(set(re.findall(r"#([A-Za-z0-9_]+)", text)))


def normalize_tweet(raw: dict, *, source_system: str, raw_ref: str = "") -> dict:
    tweet = raw.get("tweet") if isinstance(raw.get("tweet"), dict) else raw
    text_raw = str(
        tweet.get("text")
        or tweet.get("full_text")
        or tweet.get("tweet_text")
        or tweet.get("content")
        or ""
    )
    text_clean = clean_text(text_raw)
    author = tweet.get("author") if isinstance(tweet.get("author"), dict) else {}
    author_username = str(
        tweet.get("author_username")
        or tweet.get("username")
        or author.get("userName")
        or author.get("username")
        or author.get("screen_name")
        or ""
    ).lstrip("@")
    created = parse_datetime(tweet.get("createdAt") or tweet.get("created_at") or tweet.get("created_at_utc"))
    tweet_id = str(tweet.get("id") or tweet.get("id_str") or tweet.get("tweet_id") or "")
    conversation_id = str(tweet.get("conversationId") or tweet.get("conversation_id") or "")
    in_reply = str(tweet.get("in_reply_to_status_id") or tweet.get("in_reply_to_tweet_id") or "")
    quoted = str(tweet.get("quoted_tweet_id") or _dig(tweet, "quoted_tweet", "id", default="") or "")
    retweeted = str(tweet.get("retweeted_tweet_id") or _dig(tweet, "retweeted_tweet", "id", default="") or "")
    is_repost = bool(retweeted or text_raw.startswith("RT ") or str(tweet.get("type", "")).lower() in {"repost", "retweet"})
    is_reply = bool(in_reply or text_clean.startswith("@"))
    is_quote = bool(quoted or tweet.get("is_quote_status") or tweet.get("quoted_tweet"))
    urls = _urls(tweet, text_raw)
    media = _listify(tweet.get("media")) + _listify(_dig(tweet, "entities", "media", default=[]))
    media_types = sorted(set(str(item.get("type", "")) for item in media if isinstance(item, dict) and item.get("type")))
    return {
        "tweet_id": tweet_id,
        "source_system": source_system,
        "author_username": author_username,
        "author_id": str(tweet.get("author_id") or author.get("id") or author.get("id_str") or ""),
        "created_at_utc": created.isoformat(timespec="seconds") if created else "",
        "text_raw": text_raw,
        "text_clean": text_clean,
        "lang": str(tweet.get("lang") or ""),
        "url": str(tweet.get("url") or (f"https://x.com/{author_username}/status/{tweet_id}" if author_username and tweet_id else "")),
        "is_original": not is_repost and not is_reply,
        "is_reply": is_reply,
        "is_repost": is_repost,
        "is_quote": is_quote,
        "is_thread_part": bool(conversation_id and tweet_id and conversation_id != tweet_id and not is_reply),
        "conversation_id": conversation_id,
        "in_reply_to_tweet_id": in_reply,
        "quoted_tweet_id": quoted,
        "retweeted_tweet_id": retweeted,
        "has_media": bool(media_types),
        "media_types": media_types,
        "has_link": bool(urls),
        "expanded_urls": urls,
        "mentions": _mentions(text_raw),
        "hashtags": _hashtags(text_raw),
        "source_app": str(tweet.get("source") or tweet.get("source_app") or ""),
        "topic_labels": _labels(text_clean, {**TEAM_ALIASES, **SPORT_ALIASES}),
        "sport_labels": _labels(text_clean, SPORT_ALIASES),
        "team_labels": _labels(text_clean, TEAM_ALIASES),
        "player_labels": [],
        "ingested_at_utc": utc_now_iso(),
        "raw_ref": raw_ref,
    }


def metric_snapshot(raw: dict, normalized: dict, *, metric_source: str) -> dict:
    tweet = raw.get("tweet") if isinstance(raw.get("tweet"), dict) else raw
    created = parse_datetime(normalized.get("created_at_utc"))
    age_hours = 0.0
    if created:
        age_hours = max(0.0, (datetime.now(timezone.utc) - created).total_seconds() / 3600)
    views = _metric(tweet, "viewCount", "views", "impression_count", "impressions")
    likes = _metric(tweet, "likeCount", "likes", "like_count")
    replies = _metric(tweet, "replyCount", "replies", "reply_count")
    reposts = _metric(tweet, "retweetCount", "reposts", "retweet_count")
    quotes = _metric(tweet, "quoteCount", "quotes", "quote_count")
    bookmarks = _metric(tweet, "bookmarkCount", "bookmarks", "bookmark_count")
    engagements = _metric(tweet, "engagements") or (likes + replies + reposts + quotes + bookmarks)
    return {
        "tweet_id": normalized.get("tweet_id", ""),
        "snapshot_at_utc": utc_now_iso(),
        "age_hours_at_snapshot": round(age_hours, 2),
        "views": views,
        "impressions": _metric(tweet, "impressions", "impression_count") or views,
        "likes": likes,
        "replies": replies,
        "reposts": reposts,
        "quotes": quotes,
        "bookmarks": bookmarks,
        "profile_clicks": _metric(tweet, "profile_clicks", "user_profile_clicks"),
        "url_clicks": _metric(tweet, "url_clicks"),
        "engagements": engagements,
        "metric_source": metric_source,
        "is_partial": views == 0,
        "notes": "",
    }
