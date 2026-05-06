"""Creator Evolution Pulse opportunity scoring.

Pulse is the "what should I post right now?" decision layer. It does not
generate tweets and it never posts. It normalizes live signals, clusters them
into moments, scores the opportunity, and returns either one recommended brief
or a no-op decision.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import math
import re
from typing import Any

import creator_evolution as ce


PULSE_VERSION = "ce-pulse-v5-room-reader"
DEFAULT_THRESHOLD = 68.0
SAVE_THRESHOLD = 58.0
BLOCKING_HARD_BLOCKS = {
    "stale_source",
    "low_fact_confidence",
    "monetization_risk",
    "duplicate_recent_angle",
}
SOURCE_RELIABILITY = {
    "trusted_list": 7.2,
    "twitter": 5.8,
    "espn": 8.4,
    "news": 7.5,
    "sports_context": 8.0,
    "reddit": 4.8,
    "google_trends": 4.4,
    "fallback": 3.0,
}
FRESHNESS_HOURS = {
    "trusted_list": 8.0,
    "twitter": 6.0,
    "espn": 18.0,
    "news": 18.0,
    "sports_context": 4.0,
    "reddit": 8.0,
    "google_trends": 12.0,
    "fallback": 3.0,
}
PRIMARY_AUDIENCE_TERMS = (
    "broncos", "nuggets", "rockies", "avalanche", "avs", "colorado",
    "denver", "bo nix", "jokic", "murray", "mackinnon", "makar",
    "sean payton", "broncoscountry", "buffs", "cu buffs", "coach prime",
    "deion", "colorado buffaloes",
)
SPORTS_TERMS = (
    "game", "coach", "trade", "draft", "injury", "rumor", "playoff",
    "refs", "call", "contract", "roster", "starter", "bench", "loss",
    "win", "final", "halftime", "quarter", "series", "practice",
)
AVALANCHE_PULSE_TERMS = (
    "colorado avalanche", "avalanche", "avs",
)
PREGAME_OR_BREAKING_TERMS = (
    "game", "pregame", "puck drop", "starts", "scheduled", "tonight",
    "playoff", "series", "lineup", "scratch", "injury", "report",
    "breaking", "news", "quote", "coach", "goalie", "starter",
)
TENSION_TERMS = (
    "drama", "argue", "debate", "meltdown", "panic", "angry", "fired",
    "controversy", "bad take", "quote", "called out", "refs", "blame",
    "pressure", "awkward", "problem", "excuse", "rumor", "trade",
    "bench", "starter", "mistake", "weird", "absurd", "ignored",
    "melting down", "boring", "hinted", "fans",
)
LIVE_TERMS = (
    "now", "today", "tonight", "live", "breaking", "just",
    "halftime", "quarter", "injury", "trade", "report", "rumor",
    "pregame", "puck drop", "starts", "scheduled",
)
LIVE_GAME_TERMS = (
    "period", "quarter", "half", "halftime", "intermission", "in progress",
    "end of", "puck drop", "kickoff", "tipoff", "starts", "scheduled",
)
COLORADO_TEAM_TERMS = (
    "broncos", "denver broncos", "nuggets", "denver nuggets",
    "avalanche", "colorado avalanche", "avs", "rockies", "colorado rockies",
    "buffs", "cu buffs", "colorado buffaloes", "coach prime", "deion",
)
UNSAFE_MONETIZATION_TERMS = (
    "slur", "kill", "die", "crime", "arrested", "lawsuit", "gambling lock",
    "guaranteed bet", "free money", "medical", "diagnosis",
)
BETTING_SIGNAL_TERMS = (
    "betting lines", "moneyline", "money line", "spread:", "spread ",
    "over/under", "over under", "parlay", "odds", "sportsbook",
    "draftkings", "fanduel", "bet365", "betrivers",
)
FALLBACK_RISK_TERMS = (
    "idiot", "moron", "clown", "trash", "garbage", "hate", "stupid",
    "fraud", "loser", "shut up", "dumb",
)


def _ce_default_lane() -> str:
    try:
        return str(getattr(ce, "DEFAULT_LANE", "Witty Edge") or "Witty Edge")
    except Exception:
        return "Witty Edge"


def _ce_metric(item: dict[str, Any], *names: str) -> int:
    if not isinstance(item, dict):
        return 0
    try:
        metric = getattr(ce, "metric")
    except Exception:
        metric = None
    if callable(metric):
        try:
            return int(metric(item, *names))
        except Exception:
            pass
    for name in names:
        try:
            value = item.get(name)
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def _ce_parse_datetime(value: Any) -> datetime | None:
    try:
        parser = getattr(ce, "parse_datetime")
    except Exception:
        parser = None
    if callable(parser):
        try:
            return parser(value)
        except Exception:
            return None
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _ce_tweet_text(tweet: dict[str, Any]) -> str:
    if not isinstance(tweet, dict):
        return _text(tweet)
    try:
        getter = getattr(ce, "tweet_text")
    except Exception:
        getter = None
    if callable(getter):
        try:
            return str(getter(tweet) or "").strip()
        except Exception:
            pass
    return str(tweet.get("text") or tweet.get("full_text") or "").strip()


def _ce_topic_tags(text: str) -> list[str]:
    lower = text.lower()

    def has_topic_word(word: str) -> bool:
        cleaned = word.strip()
        if not cleaned:
            return False
        if " " in cleaned:
            return cleaned in lower
        return bool(re.search(rf"\b{re.escape(cleaned)}\b", lower))

    try:
        tagger = getattr(ce, "topic_tags")
    except Exception:
        tagger = None
    if callable(tagger):
        try:
            tags = tagger(text)
            tags = list(tags or ["general"])
            if "avs" in tags and not any(has_topic_word(word) for word in AVALANCHE_PULSE_TERMS + ("mackinnon", "makar")):
                tags = [tag for tag in tags if tag != "avs"]
            return tags or ["general"]
        except Exception:
            pass
    tags = []
    for tag, words in {
        "broncos": ("broncos", "bo nix", "sean payton", "paton"),
        "nuggets": ("nuggets", "jokic", "murray"),
        "avs": ("avs", "avalanche", "mackinnon", "makar"),
        "buffs": ("buffs", "cu buffs", "colorado buffaloes", "coach prime", "deion"),
        "rockies": ("rockies", "colorado rockies"),
        "draft": ("draft", "pick ", "combine", "prospect"),
        "media": ("media", "espn", "reporter", "narrative"),
    }.items():
        if any(has_topic_word(word) for word in words):
            tags.append(tag)
    return tags or ["general"]


def _ce_approved_rules_text(state: dict[str, Any] | None) -> str:
    try:
        formatter = getattr(ce, "approved_rules_text")
    except Exception:
        formatter = None
    if callable(formatter):
        try:
            return str(formatter(state) or "")
        except Exception:
            pass
    rules = (state or {}).get("approved_rules", [])
    return "\n".join(f"- {rule.get('rule', '')}" for rule in rules if isinstance(rule, dict) and rule.get("rule"))


def _heated_risk_hits(text: str) -> list[str]:
    try:
        terms = tuple(getattr(ce, "RISK_TERMS", FALLBACK_RISK_TERMS) or FALLBACK_RISK_TERMS)
    except Exception:
        terms = FALLBACK_RISK_TERMS
    lower = text.lower()
    return [term for term in terms if term in lower]


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _parse_time(value: Any, now: datetime | None = None) -> datetime | None:
    return _ce_parse_datetime(value)


def _text(value: Any) -> str:
    try:
        raw = "" if value is None else str(value)
    except Exception:
        raw = ""
    return re.sub(r"\s+", " ", raw).strip()


def _tokens(text: str) -> set[str]:
    return {tok for tok in re.findall(r"[a-z0-9]+", text.lower()) if len(tok) >= 3}


def _stable_id(text: str, source: str) -> str:
    return hashlib.sha1(f"{source}|{text}".encode("utf-8")).hexdigest()[:14]


def _metric(item: dict[str, Any], *names: str) -> int:
    return _ce_metric(item, *names)


def _iter_feed_items(value: Any, *preferred_keys: str) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, dict):
        for key in preferred_keys:
            nested = value.get(key)
            if isinstance(nested, (list, tuple, set)):
                return list(nested)
        return [value]
    if isinstance(value, (list, tuple, set)):
        return list(value)
    if isinstance(value, str):
        return [value]
    return []


def _split_sports_context_line(line: str) -> list[str]:
    clean = _text(line)
    if not clean:
        return []
    if " | " not in clean or ":" not in clean:
        return [clean]
    label, rest = clean.split(":", 1)
    label_clean = label.strip()
    if label_clean.upper() not in {"AVALANCHE GAME", "NUGGETS GAME", "BRONCOS GAME", "ROCKIES GAME", "BUFFS GAME", "NFL NEWS", "NBA NEWS", "NHL NEWS", "MLB NEWS", "AVALANCHE NEWS", "COLORADO NEWS"}:
        return [clean]
    return [f"{label_clean}: {part.strip()}" for part in rest.split(" | ") if part.strip()]


def _age_hours(timestamp: datetime | None, now: datetime | None = None) -> float:
    if timestamp is None:
        return 999.0
    return max(0.0, (_now(now) - timestamp).total_seconds() / 3600.0)


def _signal_age_hours(signal: dict[str, Any]) -> float:
    try:
        return max(0.0, float(signal.get("age_hours")))
    except Exception:
        return 999.0


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lower = text.lower()
    return any(term in lower for term in terms)


def _audience_fit(text: str) -> float:
    lower = text.lower()
    primary_hits = sum(1 for term in PRIMARY_AUDIENCE_TERMS if term in lower)
    sports_hits = sum(1 for term in SPORTS_TERMS if term in lower)
    if primary_hits:
        return min(10.0, 6.5 + primary_hits * 1.2 + min(sports_hits, 3) * 0.4)
    if sports_hits:
        return min(8.0, 3.5 + sports_hits * 0.8)
    return 2.0


def _reply_tension(text: str) -> float:
    lower = text.lower()
    if _is_colorado_current_context(lower):
        return 5.4
    hits = sum(1 for term in TENSION_TERMS if term in lower)
    if hits:
        return min(10.0, 5.0 + hits * 1.1)
    if text.endswith("?"):
        return 4.0
    return 2.5


def _is_avalanche_pregame_or_news(text: str) -> bool:
    lower = text.lower()
    if _is_completed_game_context(lower):
        return False
    return any(term in lower for term in AVALANCHE_PULSE_TERMS) and any(
        term in lower for term in PREGAME_OR_BREAKING_TERMS
    )


def _is_colorado_pregame_or_news(text: str) -> bool:
    return _is_colorado_current_context(text)


def _is_completed_game_context(text: str) -> bool:
    """True for scoreboard-style finals, not news about a Cup Final."""
    clean = _text(text)
    lower = clean.lower()
    if not clean:
        return False
    if lower.startswith("avalanche news:") or lower.startswith("nhl news:"):
        return False
    has_matchup_shape = " @ " in clean or bool(re.search(r"\b\d+\s*[-@]\s*\d+\b", clean))
    has_game_label = "game:" in lower or " game" in lower or has_matchup_shape
    has_final_status = bool(
        re.search(r"\((?:f|final|final/ot|final\s*-\s*ot|final\s+ot)\)", clean, re.I)
        or re.search(r"\bfinal\s+(?:ot|so)\b", lower)
        or re.search(r"\b(final score|game final|went final|completed)\b", lower)
    )
    return bool(has_game_label and has_final_status)


def _is_live_game_context(text: str) -> bool:
    clean = _text(text)
    lower = clean.lower()
    if not clean or _is_completed_game_context(clean):
        return False
    has_game_label = bool(re.match(r"^(avalanche game|nuggets game|broncos game|rockies game|buffs game|nba|nhl|nfl|mlb|ncaa):", lower))
    has_score = bool(re.search(r"\b\d+\s*[-@]\s*\d+\b", clean))
    return has_game_label and (has_score or _contains_any(lower, LIVE_GAME_TERMS))


def _is_colorado_current_context(text: str) -> bool:
    lower = _text(text).lower()
    if _is_completed_game_context(lower):
        return False
    return any(term in lower for term in COLORADO_TEAM_TERMS) and (
        _is_live_game_context(lower)
        or any(term in lower for term in PREGAME_OR_BREAKING_TERMS)
        or any(term in lower for term in ("breaking", "report", "rumor", "quote", "coach", "trade", "injury"))
    )


def _is_betting_signal_text(text: str) -> bool:
    lower = str(text or "").lower()
    return any(term in lower for term in BETTING_SIGNAL_TERMS)


def _opportunity_text(item: dict[str, Any]) -> str:
    parts = [str(item.get("summary_text") or "")]
    for source in item.get("source_basis", []) or []:
        if isinstance(source, dict):
            parts.append(str(source.get("text") or ""))
    return " ".join(parts)


def _is_avalanche_opportunity(item: dict[str, Any]) -> bool:
    return _is_avalanche_pregame_or_news(_opportunity_text(item))


def _is_colorado_opportunity(item: dict[str, Any]) -> bool:
    return _is_colorado_current_context(_opportunity_text(item))


def _risk_flags(text: str) -> list[str]:
    flags = []
    lower = text.lower()
    for term in UNSAFE_MONETIZATION_TERMS:
        if term in lower:
            flags.append(f"unsafe:{term}")
    for term in _heated_risk_hits(text):
        flags.append(f"heated:{term}")
    if re.search(r"\b\d+(\.\d+)?\s*%\b", lower) and not ("source" in lower or "report" in lower):
        flags.append("unverified-stat")
    return list(dict.fromkeys(flags))


def _source_reliability(source: str) -> float:
    return SOURCE_RELIABILITY.get((source or "").lower(), SOURCE_RELIABILITY["news"])


def _freshness_status(source: str, timestamp: datetime | None, text: str, now: datetime | None = None) -> str:
    source_key = (source or "news").lower()
    if timestamp is None:
        if source_key == "sports_context" and _is_live_game_context(text):
            return "fresh"
        return "unknown_time"
    age = _age_hours(timestamp, now)
    max_age = FRESHNESS_HOURS.get(source_key, 12.0)
    if _contains_any(text, LIVE_TERMS):
        max_age = min(max_age, 4.0)
    if age <= max_age * 0.5:
        return "fresh"
    if age <= max_age:
        return "usable"
    return "stale"


def _velocity(item: dict[str, Any], age: float) -> float:
    replies = _metric(item, "replyCount", "reply_count", "replies")
    reposts = _metric(item, "retweetCount", "retweet_count", "reposts", "retweets")
    likes = _metric(item, "likeCount", "like_count", "likes")
    quotes = _metric(item, "quoteCount", "quote_count", "quotes")
    views = _metric(item, "viewCount", "view_count", "views")
    active = replies + reposts + quotes
    passive_like_credit = min(likes, max(4, active * 4)) if active else min(likes, 3)
    engagement = replies * 4 + reposts * 3 + quotes * 3 + passive_like_credit
    if views and active:
        engagement += min(8, math.log10(max(views, 1)) * 1.5)
    return round(engagement / max(age, 0.5), 2)


def signal_from_tweet(tweet: dict[str, Any], *, source: str = "twitter",
                      now: datetime | None = None) -> dict[str, Any]:
    if not isinstance(tweet, dict):
        return signal_from_text(_text(tweet), source=source, now=now)
    text = _text(tweet.get("text") or tweet.get("full_text"))
    timestamp = _parse_time(tweet.get("createdAt") or tweet.get("created_at"), now)
    age = _age_hours(timestamp, now)
    src = source or "twitter"
    author = _text(tweet.get("author") or tweet.get("userName") or tweet.get("username") or tweet.get("screen_name"))
    url = _text(tweet.get("url") or tweet.get("twitterUrl"))
    if not url and tweet.get("id") and author:
        url = f"https://x.com/{author.lstrip('@')}/status/{tweet.get('id')}"
    return {
        "id": str(tweet.get("id") or tweet.get("tweet_id") or _stable_id(text, src)),
        "source": src,
        "source_reliability": _source_reliability(src),
        "timestamp": timestamp.isoformat(timespec="seconds") if timestamp else "",
        "timestamp_missing": timestamp is None,
        "age_hours": round(age, 2),
        "topic": ", ".join(_ce_topic_tags(text)),
        "text": text,
        "url": url,
        "author": author,
        "engagement": {
            "views": _metric(tweet, "viewCount", "view_count", "views"),
            "likes": _metric(tweet, "likeCount", "like_count", "likes"),
            "replies": _metric(tweet, "replyCount", "reply_count", "replies"),
            "reposts": _metric(tweet, "retweetCount", "retweet_count", "reposts", "retweets"),
            "quotes": _metric(tweet, "quoteCount", "quote_count", "quotes"),
        },
        "velocity": _velocity(tweet, age),
        "entities": sorted(_tokens(text) & _tokens(" ".join(PRIMARY_AUDIENCE_TERMS + SPORTS_TERMS)))[:12],
        "fact_confidence": max(0.0, min(10.0, _source_reliability(src) + (1.0 if url else 0.0) - (1.5 if timestamp is None else 0.0))),
        "audience_fit": _audience_fit(text),
        "reply_tension": _reply_tension(text),
        "risk_flags": _risk_flags(text),
        "freshness_status": _freshness_status(src, timestamp, text, now),
        "is_reply_target": bool(author and not text.startswith("@")),
    }


def signal_from_text(text: str, *, source: str = "news", url: str = "",
                     now: datetime | None = None, timestamp: Any = None) -> dict[str, Any]:
    clean = _text(text)
    ts = _parse_time(timestamp, now)
    src = source or "news"
    return {
        "id": _stable_id(clean, src),
        "source": src,
        "source_reliability": _source_reliability(src),
        "timestamp": ts.isoformat(timespec="seconds") if ts else "",
        "timestamp_missing": ts is None,
        "age_hours": round(_age_hours(ts, now), 2),
        "topic": ", ".join(_ce_topic_tags(clean)),
        "text": clean,
        "url": url,
        "author": "",
        "engagement": {},
        "velocity": 0.0,
        "entities": sorted(_tokens(clean) & _tokens(" ".join(PRIMARY_AUDIENCE_TERMS + SPORTS_TERMS)))[:12],
        "fact_confidence": max(0.0, min(10.0, _source_reliability(src) + (1.0 if url else 0.0) - (1.5 if ts is None else 0.0))),
        "audience_fit": _audience_fit(clean),
        "reply_tension": _reply_tension(clean),
        "risk_flags": _risk_flags(clean),
        "freshness_status": _freshness_status(src, ts, clean, now),
        "is_reply_target": False,
    }


def build_signals(tweets: list[dict[str, Any]] | None,
                  headlines: list[Any] | None,
                  *, sports_context: str = "",
                  now: datetime | None = None) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for tweet in _iter_feed_items(tweets, "tweets", "statuses", "data", "results"):
        try:
            text = _ce_tweet_text(tweet)
            if not text or text.startswith("RT "):
                continue
            signals.append(signal_from_tweet(tweet, source="twitter", now=now))
        except Exception:
            continue
    for item in _iter_feed_items(headlines, "headlines", "articles", "items", "data"):
        try:
            if isinstance(item, dict):
                text = _text(item.get("title") or item.get("headline") or item.get("text"))
                url = _text(item.get("url") or item.get("link"))
                source = _text(item.get("source") or "news").lower()
                timestamp = item.get("publishedAt") or item.get("published_at") or item.get("createdAt")
            else:
                text = _text(item)
                url = ""
                source = "news"
                timestamp = None
            if text:
                if "espn" in text.lower() or source == "espn":
                    source = "espn"
                signals.append(signal_from_text(text, source=source, url=url, timestamp=timestamp, now=now))
        except Exception:
            continue
    if sports_context:
        for raw_line in str(sports_context).splitlines():
            for line in _split_sports_context_line(raw_line):
                line = _text(line)
                if _is_betting_signal_text(line):
                    continue
                if _is_completed_game_context(line):
                    continue
                if len(line) >= 24 and _contains_any(line, SPORTS_TERMS + PRIMARY_AUDIENCE_TERMS):
                    timestamp = _now(now) if _is_live_game_context(line) else None
                    signals.append(signal_from_text(line, source="sports_context", timestamp=timestamp, now=now))
    seen = set()
    unique = []
    for signal in signals:
        key = signal["id"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(signal)
    return unique


def _cluster_key(signal: dict[str, Any]) -> str:
    topic = signal.get("topic") or "general"
    if topic != "general":
        return topic.split(",")[0].strip()
    tokens = [tok for tok in _tokens(signal.get("text", "")) if tok not in {"this", "that", "with", "from", "they", "have"}]
    return " ".join(tokens[:3]) or "general"


def cluster_signals(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for signal in signals:
        grouped.setdefault(_cluster_key(signal), []).append(signal)
    clusters = []
    for key, items in grouped.items():
        sorted_items = sorted(items, key=lambda s: (s.get("freshness_status") == "stale", -float(s.get("velocity") or 0)))
        text = " ".join(item.get("text", "") for item in sorted_items[:4])
        clusters.append({
            "id": _stable_id(key + text[:160], "cluster"),
            "topic": key,
            "signals": sorted_items,
            "signal_count": len(sorted_items),
            "summary_text": _text(sorted_items[0].get("text", ""))[:320],
            "sources": sorted({item.get("source", "source") for item in sorted_items}),
        })
    return clusters


def _recent_texts(state: dict[str, Any] | None) -> list[str]:
    tweets = (state or {}).get("tweets", [])
    texts = []
    for tweet in _iter_feed_items(tweets, "tweets", "data", "results")[:120]:
        text = _ce_tweet_text(tweet)
        if text:
            texts.append(text)
    return [t for t in texts if t]


def _similarity(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _novelty_score(text: str, state: dict[str, Any] | None) -> tuple[float, str]:
    best = 0.0
    for recent in _recent_texts(state):
        best = max(best, _similarity(text, recent))
    if best >= 0.42:
        return 1.0, "duplicate_recent_angle"
    if best >= 0.28:
        return 5.5, "near_recent_angle"
    return 10.0, ""


def score_cluster(cluster: dict[str, Any], state: dict[str, Any] | None = None,
                  *, now: datetime | None = None) -> dict[str, Any]:
    signals = [s for s in (cluster.get("signals", []) or []) if isinstance(s, dict)]
    if not signals:
        return {}
    primary = signals[0]
    text = " ".join(s.get("text", "") for s in signals[:4])
    colorado_now = _is_colorado_pregame_or_news(text)
    fresh_count = sum(1 for s in signals if s.get("freshness_status") in ("fresh", "usable"))
    best_age = min(_signal_age_hours(s) for s in signals)
    max_velocity = max(float(s.get("velocity") or 0) for s in signals)
    audience_fit = max(float(s.get("audience_fit") or 0) for s in signals)
    reply_tension = max(float(s.get("reply_tension") or 0) for s in signals)
    fact_confidence = min(10.0, max(float(s.get("fact_confidence") or 0) for s in signals) + (1.0 if len(signals) >= 2 else 0.0))
    if colorado_now:
        audience_fit = max(audience_fit, 9.4)
        reply_tension = max(reply_tension, 6.6)
        fact_confidence = max(fact_confidence, 8.0)
    novelty, novelty_flag = _novelty_score(text, state)
    safety = 10.0
    risk_flags = []
    for signal in signals:
        for flag in signal.get("risk_flags", []) or []:
            if flag.startswith("unsafe:"):
                safety -= 5.0
            elif flag == "unverified-stat":
                safety -= 2.5
            else:
                safety -= 1.2
            risk_flags.append(flag)
    safety = max(0.0, safety)
    timeliness = min(20.0, max(0.0, 20.0 - best_age * 1.7))
    if fresh_count >= 2:
        timeliness = min(20.0, timeliness + 2.0)
    velocity = min(15.0, max_velocity / 2.0 + len(signals) * 1.5)
    if colorado_now:
        timeliness = max(timeliness, 18.5)
        velocity = max(velocity, 6.0)
    urgency = 10.0 if _contains_any(text, LIVE_TERMS) else max(3.0, timeliness / 2.5)
    if colorado_now:
        urgency = 10.0
    voice_fit = min(10.0, 3.0 + reply_tension * 0.45 + audience_fit * 0.25)
    weighted = {
        "timeliness": timeliness,
        "velocity": velocity,
        "audience_fit": min(15.0, audience_fit * 1.5),
        "reply_tension": min(15.0, reply_tension * 1.5),
        "fact_confidence": fact_confidence,
        "novelty": novelty,
        "voice_fit": voice_fit,
        "monetization_safety": safety,
        "post_now_urgency": urgency,
    }
    raw_score = sum(weighted.values())
    score = round(min(100.0, raw_score / 115.0 * 100.0), 2)
    hard_blocks = []
    soft_flags = []
    if fresh_count == 0:
        hard_blocks.append("stale_source")
    if fact_confidence < 5.5:
        hard_blocks.append("low_fact_confidence")
    if audience_fit < 4.0:
        soft_flags.append("weak_audience_fit")
    if reply_tension < 4.0:
        soft_flags.append("weak_reply_tension")
    if len(signals) == 1 and max_velocity < 8 and reply_tension < 5.0 and not colorado_now:
        soft_flags.append("thin_room_signal")
    if safety < 6.0:
        hard_blocks.append("monetization_risk")
    if novelty_flag == "duplicate_recent_angle":
        hard_blocks.append("duplicate_recent_angle")
    action = "tweet"
    if score < DEFAULT_THRESHOLD and score >= SAVE_THRESHOLD:
        action = "save"
    elif primary.get("source") == "twitter" and primary.get("is_reply_target") and score >= DEFAULT_THRESHOLD:
        action = "reply"
    return {
        "id": cluster.get("id", ""),
        "topic": cluster.get("topic", "general"),
        "summary_text": primary.get("text", ""),
        "sources": cluster.get("sources", []),
        "signal_count": len(signals),
        "source_basis": [
            {
                "source": s.get("source", ""),
                "text": s.get("text", "")[:220],
                "url": s.get("url", ""),
                "freshness_status": s.get("freshness_status", ""),
                "age_hours": s.get("age_hours", 0),
                "timestamp_missing": bool(s.get("timestamp_missing")),
            }
            for s in signals[:4]
        ],
        "score": score,
        "raw_score": round(raw_score, 2),
        "weighted_scores": {k: round(v, 2) for k, v in weighted.items()},
        "hard_blocks": hard_blocks,
        "soft_flags": soft_flags,
        "risk_flags": list(dict.fromkeys(risk_flags)),
        "recommended_action": action,
        "recommended_lane": _recommended_lane(text, reply_tension, safety),
        "freshness_score": round(timeliness, 2),
        "confidence": round((score + fact_confidence * 10 + safety * 10) / 3.0, 2),
        "why_now": _why_now(signals, weighted),
    }


def _blocking_blocks(item: dict[str, Any] | None) -> list[str]:
    if not isinstance(item, dict):
        return []
    return [block for block in item.get("hard_blocks", []) if block in BLOCKING_HARD_BLOCKS]


def _has_strong_now_signal(item: dict[str, Any] | None) -> bool:
    if not isinstance(item, dict):
        return False
    text = _opportunity_text(item)
    weighted = item.get("weighted_scores", {}) or {}
    sources = item.get("source_basis", []) or []
    fresh_sources = [s for s in sources if isinstance(s, dict) and s.get("freshness_status") == "fresh"]
    if _is_live_game_context(text):
        return True
    if _is_colorado_current_context(text) and fresh_sources and any(
        term in text.lower() for term in ("breaking", "just", "report", "rumor", "quote", "coach", "trade", "injury")
    ):
        return True
    if len(fresh_sources) >= 2 and float(weighted.get("reply_tension", 0) or 0) >= 8:
        return True
    if "twitter" in {str(s.get("source", "")) for s in sources if isinstance(s, dict)}:
        return (
            float(weighted.get("velocity", 0) or 0) >= 8
            and float(weighted.get("reply_tension", 0) or 0) >= 7
            and float(weighted.get("audience_fit", 0) or 0) >= 9
        )
    return False


def _can_be_best_available(item: dict[str, Any] | None) -> bool:
    if not isinstance(item, dict) or _blocking_blocks(item):
        return False
    weighted = item.get("weighted_scores", {}) or {}
    if float(item.get("score", 0) or 0) < SAVE_THRESHOLD:
        return False
    if float(weighted.get("audience_fit", 0) or 0) < 8:
        return False
    if "thin_room_signal" in (item.get("soft_flags") or []) and float(weighted.get("reply_tension", 0) or 0) < 7:
        return False
    return True


def _recommended_lane(text: str, reply_tension: float, safety: float) -> str:
    lower = text.lower()
    if safety < 7:
        return "Skeptical"
    if any(term in lower for term in ("absurd", "weird", "funny")):
        return "Amused"
    if any(term in lower for term in ("final", "win", "clutch")):
        return "Celebratory"
    if any(term in lower for term in ("refs", "excuse", "mistake", "problem")):
        return "Annoyed"
    if reply_tension >= 7:
        return "Witty Edge"
    return _ce_default_lane()


def _why_now(signals: list[dict[str, Any]], weighted: dict[str, float]) -> str:
    source_count = len({s.get("source") for s in signals})
    newest = min(_signal_age_hours(s) for s in signals)
    parts = [f"{source_count} source type{'s' if source_count != 1 else ''}", f"newest signal {newest:.1f}h old"]
    if weighted.get("velocity", 0) >= 8:
        parts.append("engagement is moving")
    if weighted.get("reply_tension", 0) >= 9:
        parts.append("reply tension is strong")
    return "; ".join(parts)


def find_pulse(tweets: list[dict[str, Any]] | None,
               headlines: list[Any] | None,
               state: dict[str, Any] | None = None,
               *, sports_context: str = "",
               handle: str = "",
               now: datetime | None = None,
               threshold: float = DEFAULT_THRESHOLD) -> dict[str, Any]:
    signals = build_signals(tweets, headlines, sports_context=sports_context, now=now)
    clusters = cluster_signals(signals)
    scored = [score_cluster(cluster, state, now=now) for cluster in clusters]
    scored = [item for item in scored if item]
    scored.sort(key=lambda item: item.get("score", 0), reverse=True)
    usable = [item for item in scored if not _blocking_blocks(item)]
    colorado_usable = [item for item in usable if _is_colorado_opportunity(item)]
    strong_colorado = [item for item in colorado_usable if _has_strong_now_signal(item)]
    best = strong_colorado[0] if strong_colorado else (usable[0] if usable else (scored[0] if scored else None))
    status = "no_op"
    if best and not _blocking_blocks(best):
        _thin_room_signal = "thin_room_signal" in (best.get("soft_flags") or [])
        if _has_strong_now_signal(best):
            status = "ready"
        elif best.get("score", 0) >= threshold and not _thin_room_signal:
            status = "ready"
        elif _can_be_best_available(best):
            status = "best_available"
    if best and status == "best_available":
        best = dict(best)
        best["recommended_action"] = "tweet"
        best["why_now"] = (
            f"{best.get('why_now', 'Fresh timeline context is active.')}; "
            "selected as the best available Colorado timeline angle right now"
        )
    elif (
        best
        and status == "no_op"
        and best.get("score", 0) >= SAVE_THRESHOLD
        and not _blocking_blocks(best)
        and "thin_room_signal" not in (best.get("soft_flags") or [])
    ):
        status = "save_for_later"
        best = dict(best)
        best["recommended_action"] = "save"
    decision = {
        "version": PULSE_VERSION,
        "status": status,
        "handle": handle,
        "threshold": threshold,
        "checked_at": _now(now).isoformat(timespec="seconds"),
        "search_depth": ["fast_check", "deep_hunt", "reply_hunt", "best_available_now", "safety_gate"],
        "signals_checked": len(signals),
        "clusters_checked": len(clusters),
        "best": best,
        "top_rejected": [item for item in scored if item.get("id") != (best or {}).get("id")][:5],
        "message": (
            "No safe Pulse source right now."
            if status == "no_op"
            else "Pulse found the best tweet available right now."
            if status == "ready"
            else "Pulse found the best available Colorado timeline angle right now."
        ),
    }
    if best:
        decision["brief"] = build_pulse_brief(best, state)
    else:
        decision["brief"] = ""
    return decision


def pulse_error_decision(message: str = "Pulse could not safely read the live feed.",
                         *, handle: str = "", now: datetime | None = None) -> dict[str, Any]:
    return {
        "version": PULSE_VERSION,
        "status": "pulse_error",
        "handle": handle,
        "threshold": DEFAULT_THRESHOLD,
        "checked_at": _now(now).isoformat(timespec="seconds"),
        "search_depth": ["fast_check", "deep_hunt", "reply_hunt", "fallback_angle", "fail_closed"],
        "signals_checked": 0,
        "clusters_checked": 0,
        "best": None,
        "top_rejected": [],
        "message": message,
        "brief": "",
        "error": message,
    }


def safe_find_pulse(tweets: Any,
                    headlines: Any,
                    state: dict[str, Any] | None = None,
                    *, sports_context: str = "",
                    handle: str = "",
                    now: datetime | None = None,
                    threshold: float = DEFAULT_THRESHOLD) -> dict[str, Any]:
    try:
        return find_pulse(
            tweets,
            headlines,
            state,
            sports_context=sports_context,
            handle=handle,
            now=now,
            threshold=threshold,
        )
    except Exception as exc:
        return pulse_error_decision(str(exc)[:240], handle=handle, now=now)


def build_pulse_brief(opportunity: dict[str, Any], state: dict[str, Any] | None = None) -> str:
    action = opportunity.get("recommended_action", "tweet")
    topic = opportunity.get("topic", "live opportunity")
    lane = opportunity.get("recommended_lane", _ce_default_lane())
    source_lines = []
    for source in opportunity.get("source_basis", [])[:4]:
        source_lines.append(
            f"- {source.get('source', 'source')} | {source.get('freshness_status', '')} | "
            f"{source.get('text', '')}"
        )
    rules = _ce_approved_rules_text(state)
    return f"""PULSE OPPORTUNITY:
{topic}

RECOMMENDED ACTION:
{action}

WHY NOW:
{opportunity.get('why_now', '')}

CONFIDENCE:
score {opportunity.get('score', 0)} | freshness {opportunity.get('freshness_score', 0)} | lane {lane}

SOURCE BASIS:
{chr(10).join(source_lines)}

CREATOR EVOLUTION LIVE RULES:
{rules or "- No approved rule changes yet. Use base Creator Evolution rules only."}

PULSE WRITING CONTRACT:
- Write only from the source basis above.
- If the action is reply, sound like a sharp human joining the conversation, not quote-tweeting a strategy deck.
- If the action is tweet, make it feel immediate without inventing facts.
- No Hall of Fame hooks, no Creator Studio calibration, no old What's Hot formulas.
- No fake engagement questions, no invented stats, no unsafe claims.
- Default to witty edge unless the recommended lane says otherwise."""
