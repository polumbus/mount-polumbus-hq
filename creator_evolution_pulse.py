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


PULSE_VERSION = "ce-pulse-v1-opportunity-gate"
DEFAULT_THRESHOLD = 68.0
SAVE_THRESHOLD = 58.0
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
    "sean payton", "broncoscountry",
)
SPORTS_TERMS = (
    "game", "coach", "trade", "draft", "injury", "rumor", "playoff",
    "refs", "call", "contract", "roster", "starter", "bench", "loss",
    "win", "final", "halftime", "quarter", "series", "practice",
)
TENSION_TERMS = (
    "drama", "argue", "debate", "meltdown", "panic", "angry", "fired",
    "controversy", "bad take", "quote", "called out", "refs", "blame",
    "pressure", "awkward", "problem", "excuse", "rumor", "trade",
    "bench", "starter", "mistake", "weird", "absurd", "ignored",
    "melting down", "boring", "hinted", "fans",
)
LIVE_TERMS = (
    "now", "today", "tonight", "live", "breaking", "just", "final",
    "halftime", "quarter", "injury", "trade", "report", "rumor",
)
UNSAFE_MONETIZATION_TERMS = (
    "slur", "kill", "die", "crime", "arrested", "lawsuit", "gambling lock",
    "guaranteed bet", "free money", "medical", "diagnosis",
)


def _now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def _parse_time(value: Any, now: datetime | None = None) -> datetime:
    parsed = ce.parse_datetime(value)
    return parsed or _now(now)


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _tokens(text: str) -> set[str]:
    return {tok for tok in re.findall(r"[a-z0-9]+", text.lower()) if len(tok) >= 3}


def _stable_id(text: str, source: str) -> str:
    return hashlib.sha1(f"{source}|{text}".encode("utf-8")).hexdigest()[:14]


def _metric(item: dict[str, Any], *names: str) -> int:
    return ce.metric(item, *names)


def _age_hours(timestamp: datetime, now: datetime | None = None) -> float:
    return max(0.0, (_now(now) - timestamp).total_seconds() / 3600.0)


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
    hits = sum(1 for term in TENSION_TERMS if term in lower)
    if hits:
        return min(10.0, 5.0 + hits * 1.1)
    if text.endswith("?"):
        return 4.0
    return 2.5


def _risk_flags(text: str) -> list[str]:
    flags = []
    lower = text.lower()
    for term in UNSAFE_MONETIZATION_TERMS:
        if term in lower:
            flags.append(f"unsafe:{term}")
    for term in ce.risk_hits(text):
        flags.append(f"heated:{term}")
    if re.search(r"\b\d+(\.\d+)?\s*%\b", lower) and not ("source" in lower or "report" in lower):
        flags.append("unverified-stat")
    return list(dict.fromkeys(flags))


def _source_reliability(source: str) -> float:
    return SOURCE_RELIABILITY.get((source or "").lower(), SOURCE_RELIABILITY["news"])


def _freshness_status(source: str, timestamp: datetime, text: str, now: datetime | None = None) -> str:
    age = _age_hours(timestamp, now)
    source_key = (source or "news").lower()
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
    engagement = replies * 4 + reposts * 3 + quotes * 3 + likes
    if views:
        engagement += min(25, math.log10(max(views, 1)) * 4)
    return round(engagement / max(age, 0.5), 2)


def signal_from_tweet(tweet: dict[str, Any], *, source: str = "twitter",
                      now: datetime | None = None) -> dict[str, Any]:
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
        "timestamp": timestamp.isoformat(timespec="seconds"),
        "age_hours": round(age, 2),
        "topic": ", ".join(ce.topic_tags(text)),
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
        "fact_confidence": min(10.0, _source_reliability(src) + (1.0 if url else 0.0)),
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
        "timestamp": ts.isoformat(timespec="seconds"),
        "age_hours": round(_age_hours(ts, now), 2),
        "topic": ", ".join(ce.topic_tags(clean)),
        "text": clean,
        "url": url,
        "author": "",
        "engagement": {},
        "velocity": 0.0,
        "entities": sorted(_tokens(clean) & _tokens(" ".join(PRIMARY_AUDIENCE_TERMS + SPORTS_TERMS)))[:12],
        "fact_confidence": min(10.0, _source_reliability(src) + (1.0 if url else 0.0)),
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
    for tweet in tweets or []:
        if isinstance(tweet, dict):
            text = ce.tweet_text(tweet)
            if not text or text.startswith("RT "):
                continue
            signals.append(signal_from_tweet(tweet, source="twitter", now=now))
    for item in headlines or []:
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
    if sports_context:
        for line in str(sports_context).splitlines():
            line = _text(line)
            if len(line) >= 24 and _contains_any(line, SPORTS_TERMS + PRIMARY_AUDIENCE_TERMS):
                signals.append(signal_from_text(line, source="sports_context", now=now))
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
    for tweet in tweets[:120]:
        if isinstance(tweet, dict):
            texts.append(ce.tweet_text(tweet))
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
    signals = cluster.get("signals", []) or []
    if not signals:
        return {}
    primary = signals[0]
    text = " ".join(s.get("text", "") for s in signals[:4])
    fresh_count = sum(1 for s in signals if s.get("freshness_status") in ("fresh", "usable"))
    best_age = min(float(s.get("age_hours") or 999) for s in signals)
    max_velocity = max(float(s.get("velocity") or 0) for s in signals)
    audience_fit = max(float(s.get("audience_fit") or 0) for s in signals)
    reply_tension = max(float(s.get("reply_tension") or 0) for s in signals)
    fact_confidence = min(10.0, max(float(s.get("fact_confidence") or 0) for s in signals) + (1.0 if len(signals) >= 2 else 0.0))
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
    urgency = 10.0 if _contains_any(text, LIVE_TERMS) else max(3.0, timeliness / 2.5)
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
    if fresh_count == 0:
        hard_blocks.append("stale_source")
    if fact_confidence < 5.5:
        hard_blocks.append("low_fact_confidence")
    if audience_fit < 4.0:
        hard_blocks.append("weak_audience_fit")
    if reply_tension < 4.0:
        hard_blocks.append("weak_reply_tension")
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
        "source_basis": [
            {
                "source": s.get("source", ""),
                "text": s.get("text", "")[:220],
                "url": s.get("url", ""),
                "freshness_status": s.get("freshness_status", ""),
                "age_hours": s.get("age_hours", 0),
            }
            for s in signals[:4]
        ],
        "score": score,
        "raw_score": round(raw_score, 2),
        "weighted_scores": {k: round(v, 2) for k, v in weighted.items()},
        "hard_blocks": hard_blocks,
        "risk_flags": list(dict.fromkeys(risk_flags)),
        "recommended_action": action,
        "recommended_lane": _recommended_lane(text, reply_tension, safety),
        "freshness_score": round(timeliness, 2),
        "confidence": round((score + fact_confidence * 10 + safety * 10) / 3.0, 2),
        "why_now": _why_now(signals, weighted),
    }


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
    return ce.DEFAULT_LANE


def _why_now(signals: list[dict[str, Any]], weighted: dict[str, float]) -> str:
    source_count = len({s.get("source") for s in signals})
    newest = min(float(s.get("age_hours") or 999) for s in signals)
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
    viable = [item for item in scored if item.get("score", 0) >= threshold and not item.get("hard_blocks")]
    best = viable[0] if viable else (scored[0] if scored else None)
    status = "ready" if viable else "no_op"
    if best and not viable and best.get("score", 0) >= SAVE_THRESHOLD and not any(
        block in best.get("hard_blocks", []) for block in ("stale_source", "low_fact_confidence", "monetization_risk", "duplicate_recent_angle")
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
        "search_depth": ["fast_check", "deep_hunt", "reply_hunt", "fallback_angle", "no_op"],
        "signals_checked": len(signals),
        "clusters_checked": len(clusters),
        "best": best,
        "top_rejected": scored[:5] if not viable else scored[1:5],
        "message": "No strong Pulse right now." if status == "no_op" else "Pulse found a viable moment.",
    }
    if best:
        decision["brief"] = build_pulse_brief(best, state)
    else:
        decision["brief"] = ""
    return decision


def build_pulse_brief(opportunity: dict[str, Any], state: dict[str, Any] | None = None) -> str:
    action = opportunity.get("recommended_action", "tweet")
    topic = opportunity.get("topic", "live opportunity")
    lane = opportunity.get("recommended_lane", ce.DEFAULT_LANE)
    source_lines = []
    for source in opportunity.get("source_basis", [])[:4]:
        source_lines.append(
            f"- {source.get('source', 'source')} | {source.get('freshness_status', '')} | "
            f"{source.get('text', '')}"
        )
    rules = ce.approved_rules_text(state)
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
