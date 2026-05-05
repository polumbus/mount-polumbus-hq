"""Pure Creator Evolution scoring and approval helpers.

The Streamlit app owns rendering and API calls. This module keeps scoring,
rule proposals, and prompt construction importable for tests without running
the app.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import math
import re
from typing import Any


STATE_FILENAME = "creator_evolution_state.json"
GIST_FILENAME = "hq_creator_evolution.json"
DEFAULT_LANE = "Witty Edge"
EMOTION_LANES = (
    "Witty Edge",
    "Amused",
    "Annoyed",
    "Fired-Up",
    "Skeptical",
    "Celebratory",
    "Deadpan",
)

RISK_TERMS = (
    "idiot",
    "moron",
    "clown",
    "trash",
    "garbage",
    "hate",
    "stupid",
    "fraud",
    "loser",
    "shut up",
    "dumb",
)

ANTI_AI_BANNED_PHRASES = (
    "here's the thing",
    "at the end of the day",
    "let's unpack",
    "that being said",
    "in today's landscape",
    "game-changer",
    "unlock",
    "elevate",
    "delve",
    "not just",
    "it's giving",
)


def utc_now(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def iso_now(now: datetime | None = None) -> str:
    return utc_now(now).isoformat(timespec="seconds")


def parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%a %b %d %H:%M:%S %z %Y", "%Y-%m-%d %H:%M:%S%z"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                parsed = None
        if parsed is None:
            return None
    return utc_now(parsed)


def metric(tweet: dict[str, Any], *names: str) -> int:
    for name in names:
        value = tweet.get(name)
        if value is None:
            continue
        try:
            return int(value)
        except (TypeError, ValueError):
            continue
    return 0


def tweet_text(tweet: dict[str, Any]) -> str:
    return str(tweet.get("text") or tweet.get("full_text") or "").strip()


def is_original_post(tweet: dict[str, Any]) -> bool:
    text = tweet_text(tweet)
    if not text:
        return False
    if text.startswith("RT ") or text.startswith("@"):
        return False
    if tweet.get("isRetweet") or tweet.get("retweeted"):
        return False
    return True


def classify_format(text: str) -> str:
    has_link = "http" in text.lower()
    length = len(text)
    if length <= 160 and not has_link:
        return "Punchy Tweet"
    if length <= 260:
        return "Normal Tweet"
    return "Long Tweet"


def post_hour_bucket(created_at: datetime | None) -> str:
    if not created_at:
        return "unknown"
    hour = created_at.hour
    if 5 <= hour < 11:
        return "morning"
    if 11 <= hour < 16:
        return "midday"
    if 16 <= hour < 21:
        return "evening"
    return "late"


def age_hours(tweet: dict[str, Any], now: datetime | None = None) -> float:
    created = parse_datetime(tweet.get("createdAt") or tweet.get("created_at"))
    if not created:
        return 9999.0
    return max(0.0, (utc_now(now) - created).total_seconds() / 3600.0)


def lifecycle_for_age(hours: float) -> str:
    if hours < 24:
        return "provisional"
    if hours < 72:
        return "maturing"
    if hours <= 24 * 30:
        return "mature"
    return "archived"


def age_bucket_for_hours(hours: float) -> str:
    if hours < 1:
        return "0-1h"
    if hours < 6:
        return "1-6h"
    if hours < 24:
        return "6-24h"
    if hours < 72:
        return "1-3d"
    if hours < 24 * 14:
        return "3-14d"
    return "14d+"


def topic_tags(text: str) -> list[str]:
    lower = text.lower()
    tags = []
    for tag, words in {
        "broncos": ("broncos", "bo nix", "sean payton", "paton"),
        "nuggets": ("nuggets", "jokic", "murray"),
        "avs": ("avs", "avalanche", "mackinnon", "makar"),
        "draft": ("draft", "pick ", "combine", "prospect"),
        "media": ("media", "espn", "grok", "reporter", "narrative"),
    }.items():
        if any(word in lower for word in words):
            tags.append(tag)
    return tags or ["general"]


def risky_language_score(text: str) -> int:
    lower = text.lower()
    return sum(1 for term in RISK_TERMS if term in lower)


def ai_sounding_hits(text: str) -> list[str]:
    lower = text.lower()
    return [phrase for phrase in ANTI_AI_BANNED_PHRASES if phrase in lower]


def score_tweet(tweet: dict[str, Any], now: datetime | None = None) -> dict[str, Any]:
    text = tweet_text(tweet)
    views = metric(tweet, "viewCount", "view_count", "views")
    likes = metric(tweet, "likeCount", "like_count", "likes")
    reposts = metric(tweet, "retweetCount", "retweet_count", "retweets", "rts")
    replies = metric(tweet, "replyCount", "reply_count", "replies")
    quotes = metric(tweet, "quoteCount", "quote_count", "quotes")
    bookmarks = metric(tweet, "bookmarkCount", "bookmark_count", "bookmarks")
    created = parse_datetime(tweet.get("createdAt") or tweet.get("created_at"))
    hours = age_hours(tweet, now)
    lifecycle = lifecycle_for_age(hours)
    denominator = max(views, 1)
    reply_per_1k = replies / denominator * 1000.0
    repost_per_1k = reposts / denominator * 1000.0
    like_per_1k = likes / denominator * 1000.0
    bookmark_per_1k = bookmarks / denominator * 1000.0

    reach_score = min(45.0, math.log10(max(views, 1)) * 10.0)
    reply_score = min(25.0, reply_per_1k * 2.6)
    share_score = min(18.0, repost_per_1k * 7.0 + quotes * 0.12)
    affinity_score = min(12.0, like_per_1k * 0.45 + bookmark_per_1k * 2.0)
    risk = risky_language_score(text)
    risk_penalty = min(16.0, risk * 4.0)
    link_penalty = 4.0 if "http" in text.lower() else 0.0
    score = max(0.0, reach_score + reply_score + share_score + affinity_score - risk_penalty - link_penalty)

    false_winner = bool(
        views >= 1000
        and replies >= 8
        and (risk > 0 or replies > max(likes, 1) * 0.9)
        and repost_per_1k < 1.2
    )

    return {
        "id": str(tweet.get("id") or tweet.get("tweet_id") or ""),
        "text": text,
        "created_at": created.isoformat(timespec="seconds") if created else "",
        "metrics": {
            "views": views,
            "likes": likes,
            "reposts": reposts,
            "replies": replies,
            "quotes": quotes,
            "bookmarks": bookmarks,
            "reply_per_1k": round(reply_per_1k, 2),
            "repost_per_1k": round(repost_per_1k, 2),
            "like_per_1k": round(like_per_1k, 2),
            "bookmark_per_1k": round(bookmark_per_1k, 2),
        },
        "cohort": {
            "format": classify_format(text),
            "age_bucket": age_bucket_for_hours(hours),
            "lifecycle": lifecycle,
            "has_link": "http" in text.lower(),
            "has_media": bool(tweet.get("media") or tweet.get("photos") or tweet.get("videos")),
            "post_hour": post_hour_bucket(created),
            "topics": topic_tags(text),
        },
        "scores": {
            "creator_evolution": round(score, 2),
            "reach": round(reach_score, 2),
            "reply_quality": round(reply_score, 2),
            "share": round(share_score, 2),
            "affinity": round(affinity_score, 2),
            "risk_penalty": round(risk_penalty + link_penalty, 2),
        },
        "flags": {
            "false_winner": false_winner,
            "risky_language": risk > 0,
            "ai_sounding_hits": ai_sounding_hits(text),
        },
    }


def _proposal_id(rule: str, evidence_ids: list[str]) -> str:
    raw = f"{rule}|{'|'.join(sorted(evidence_ids))}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _keep_existing_proposal_status(new_prop: dict[str, Any], existing: list[dict[str, Any]]) -> dict[str, Any]:
    for prop in existing:
        if prop.get("id") == new_prop["id"]:
            merged = dict(new_prop)
            merged["status"] = prop.get("status", new_prop["status"])
            merged["decided_at"] = prop.get("decided_at", "")
            merged["created_at"] = prop.get("created_at", new_prop["created_at"])
            return merged
    return new_prop


def summarize_scores(scores: list[dict[str, Any]]) -> dict[str, Any]:
    mature = [s for s in scores if s["cohort"]["lifecycle"] in ("mature", "archived")]
    provisional = [s for s in scores if s["cohort"]["lifecycle"] == "provisional"]
    pool = mature or scores
    ranked = sorted(pool, key=lambda s: s["scores"]["creator_evolution"], reverse=True)
    winners = ranked[:5]
    losers = ranked[-5:] if len(ranked) >= 5 else ranked[-len(ranked):]
    false_winners = [s for s in ranked if s["flags"].get("false_winner")]

    by_format: dict[str, list[dict[str, Any]]] = {}
    for score in pool:
        by_format.setdefault(score["cohort"]["format"], []).append(score)
    format_summary = []
    for fmt, items in by_format.items():
        avg = sum(i["scores"]["creator_evolution"] for i in items) / max(len(items), 1)
        format_summary.append({"format": fmt, "count": len(items), "avg_score": round(avg, 2)})
    format_summary.sort(key=lambda item: (item["avg_score"], item["count"]), reverse=True)

    return {
        "mature_count": len(mature),
        "provisional_count": len(provisional),
        "winner_ids": [s["id"] for s in winners if s["id"]],
        "loser_ids": [s["id"] for s in losers if s["id"]],
        "false_winner_ids": [s["id"] for s in false_winners[:5] if s["id"]],
        "format_summary": format_summary,
        "best_current_patterns": _pattern_lines(winners, positive=True),
        "worst_current_patterns": _pattern_lines(losers, positive=False),
    }


def _pattern_lines(items: list[dict[str, Any]], *, positive: bool) -> list[str]:
    lines = []
    for item in items[:5]:
        metrics = item["metrics"]
        cohort = item["cohort"]
        text = item["text"].replace("\n", " ")
        if positive:
            lines.append(
                f"{cohort['format']} | {metrics['views']:,} views | "
                f"{metrics['reply_per_1k']:.1f} replies/1k | {text[:110]}"
            )
        else:
            lines.append(
                f"{cohort['format']} | low score {item['scores']['creator_evolution']:.1f} | "
                f"{metrics['views']:,} views | {text[:110]}"
            )
    return lines


def propose_rules(scores: list[dict[str, Any]], existing: list[dict[str, Any]] | None = None,
                  now: datetime | None = None) -> list[dict[str, Any]]:
    existing = existing or []
    summary = summarize_scores(scores)
    mature = [s for s in scores if s["cohort"]["lifecycle"] in ("mature", "archived")]
    if len(mature) < 3:
        return [_keep_existing_proposal_status({
            "id": _proposal_id("Wait for at least 3 mature original posts before evolving generation rules.", []),
            "status": "pending",
            "created_at": iso_now(now),
            "rule": "Wait for at least 3 mature original posts before evolving generation rules.",
            "reason": "Performance learning needs mature posts so early-hour noise does not rewrite the voice.",
            "evidence_tweet_ids": [],
            "sample_size": len(mature),
            "before_after": {
                "before": "React to one fresh tweet immediately.",
                "after": "Hold rule changes until enough mature posts prove a pattern.",
            },
        }, existing)]

    proposals: list[dict[str, Any]] = []
    formats = summary.get("format_summary", [])
    if formats:
        best = formats[0]
        evidence = summary.get("winner_ids", [])[:4]
        rule = f"Start Creator Evolution drafts in {best['format']} unless the user's requested format says otherwise."
        proposals.append({
            "id": _proposal_id(rule, evidence),
            "status": "pending",
            "created_at": iso_now(now),
            "rule": rule,
            "reason": f"{best['format']} is currently the strongest mature cohort by normalized score.",
            "evidence_tweet_ids": evidence,
            "sample_size": best["count"],
            "before_after": {
                "before": "Default to old Creator Studio structure regardless of current performance.",
                "after": f"Open with {best['format']} pacing when no explicit format is chosen.",
            },
        })

    winners = [s for s in sorted(mature, key=lambda s: s["scores"]["creator_evolution"], reverse=True)[:5]]
    no_link_winners = [s for s in winners if not s["cohort"]["has_link"]]
    if len(no_link_winners) >= max(2, len(winners) // 2):
        evidence = [s["id"] for s in no_link_winners if s["id"]][:4]
        rule = "Favor text-only posts unless the link or media is the whole point."
        proposals.append({
            "id": _proposal_id(rule, evidence),
            "status": "pending",
            "created_at": iso_now(now),
            "rule": rule,
            "reason": "Current winners are mostly text-only, which protects reach and keeps the personality in the copy.",
            "evidence_tweet_ids": evidence,
            "sample_size": len(no_link_winners),
            "before_after": {
                "before": "Attach context or links to make a post feel complete.",
                "after": "Let the post stand on one sharp human observation when possible.",
            },
        })

    false_ids = summary.get("false_winner_ids", [])
    if false_ids:
        rule = "Do not learn from high-reply outrage unless it also wins on reach and repost quality."
        proposals.append({
            "id": _proposal_id(rule, false_ids),
            "status": "pending",
            "created_at": iso_now(now),
            "rule": rule,
            "reason": "Some posts can trigger replies while carrying monetization or reach risk.",
            "evidence_tweet_ids": false_ids[:4],
            "sample_size": len(false_ids),
            "before_after": {
                "before": "Treat every reply spike as a winning voice pattern.",
                "after": "Use witty edge without copying rage patterns that may limit monetization.",
            },
        })

    if winners:
        evidence = [s["id"] for s in winners if s["id"]][:4]
        rule = "End with a declarative open loop that leaves a specific tension unresolved."
        proposals.append({
            "id": _proposal_id(rule, evidence),
            "status": "pending",
            "created_at": iso_now(now),
            "rule": rule,
            "reason": "Top posts should drive replies through an unfinished thought, not generic question bait.",
            "evidence_tweet_ids": evidence,
            "sample_size": len(winners),
            "before_after": {
                "before": "What do you think?",
                "after": "The uncomfortable part is what the next move says about the whole plan...",
            },
        })

    return [_keep_existing_proposal_status(prop, existing) for prop in proposals]


def initial_state() -> dict[str, Any]:
    return {
        "version": 1,
        "tweets": [],
        "snapshots": [],
        "scores": [],
        "patterns": summarize_scores([]),
        "proposals": [],
        "approved_rules": [],
        "sync_status": {
            "status": "never_synced",
            "last_sync_at": "",
            "handle": "",
            "original_tweet_count": 0,
            "mature_tweet_count": 0,
            "estimated_spend_usd": 0.0,
        },
        "api_usage": {
            "provider": "twitterapi.io",
            "estimated_tweets_read": 0,
            "estimated_cost_usd": 0.0,
        },
    }


def slim_tweet(tweet: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(tweet.get("id") or tweet.get("tweet_id") or ""),
        "text": tweet_text(tweet),
        "createdAt": str(tweet.get("createdAt") or tweet.get("created_at") or ""),
        "likeCount": metric(tweet, "likeCount", "like_count", "likes"),
        "retweetCount": metric(tweet, "retweetCount", "retweet_count", "retweets", "rts"),
        "replyCount": metric(tweet, "replyCount", "reply_count", "replies"),
        "viewCount": metric(tweet, "viewCount", "view_count", "views"),
        "quoteCount": metric(tweet, "quoteCount", "quote_count", "quotes"),
        "bookmarkCount": metric(tweet, "bookmarkCount", "bookmark_count", "bookmarks"),
    }


def refresh_state(existing: dict[str, Any] | None, tweets: list[dict[str, Any]], *,
                  handle: str = "", now: datetime | None = None) -> dict[str, Any]:
    state = dict(initial_state())
    if isinstance(existing, dict):
        state.update(existing)
    current_time = iso_now(now)
    originals = [slim_tweet(t) for t in tweets if isinstance(t, dict) and is_original_post(t)]
    scores = [score_tweet(t, now) for t in originals]
    snapshots = list(state.get("snapshots", []))
    for tweet in originals:
        snapshots.append({
            "tweet_id": tweet["id"],
            "captured_at": current_time,
            "metrics": {
                "views": tweet["viewCount"],
                "likes": tweet["likeCount"],
                "reposts": tweet["retweetCount"],
                "replies": tweet["replyCount"],
                "quotes": tweet["quoteCount"],
                "bookmarks": tweet["bookmarkCount"],
            },
        })
    snapshots = snapshots[-2000:]
    patterns = summarize_scores(scores)
    api_reads = len(originals)
    estimated_cost = round(api_reads / 1000.0 * 0.15, 4)
    state.update({
        "version": 1,
        "tweets": originals[:500],
        "snapshots": snapshots,
        "scores": scores,
        "patterns": patterns,
        "proposals": propose_rules(scores, state.get("proposals", []), now),
        "sync_status": {
            "status": "ok",
            "last_sync_at": current_time,
            "handle": handle,
            "original_tweet_count": len(originals),
            "mature_tweet_count": patterns.get("mature_count", 0),
            "estimated_spend_usd": estimated_cost,
        },
        "api_usage": {
            "provider": "twitterapi.io",
            "estimated_tweets_read": api_reads,
            "estimated_cost_usd": estimated_cost,
        },
    })
    state["approved_rules"] = list(state.get("approved_rules", []))
    return state


def approve_proposal(state: dict[str, Any], proposal_id: str, now: datetime | None = None) -> dict[str, Any]:
    state = dict(state or initial_state())
    approved = list(state.get("approved_rules", []))
    proposals = []
    for proposal in state.get("proposals", []):
        proposal = dict(proposal)
        if proposal.get("id") == proposal_id:
            proposal["status"] = "approved"
            proposal["decided_at"] = iso_now(now)
            if not any(rule.get("proposal_id") == proposal_id for rule in approved):
                approved.append({
                    "proposal_id": proposal_id,
                    "rule": proposal.get("rule", ""),
                    "approved_at": proposal["decided_at"],
                    "evidence_tweet_ids": proposal.get("evidence_tweet_ids", []),
                })
        proposals.append(proposal)
    state["proposals"] = proposals
    state["approved_rules"] = approved
    return state


def reject_proposal(state: dict[str, Any], proposal_id: str, now: datetime | None = None) -> dict[str, Any]:
    state = dict(state or initial_state())
    proposals = []
    for proposal in state.get("proposals", []):
        proposal = dict(proposal)
        if proposal.get("id") == proposal_id:
            proposal["status"] = "rejected"
            proposal["decided_at"] = iso_now(now)
        proposals.append(proposal)
    state["proposals"] = proposals
    return state


def approved_rules_text(state: dict[str, Any] | None) -> str:
    rules = (state or {}).get("approved_rules", [])
    lines = [f"- {rule.get('rule', '')}" for rule in rules if rule.get("rule")]
    return "\n".join(lines)


def performance_context(state: dict[str, Any] | None) -> str:
    state = state or initial_state()
    patterns = state.get("patterns", {})
    best = patterns.get("best_current_patterns", [])
    worst = patterns.get("worst_current_patterns", [])
    rules = approved_rules_text(state)
    blocks = []
    if best:
        blocks.append("CURRENT WINNING PERFORMANCE PATTERNS:\n" + "\n".join(f"- {line}" for line in best[:5]))
    if worst:
        blocks.append("CURRENT LOSING PERFORMANCE PATTERNS:\n" + "\n".join(f"- {line}" for line in worst[:5]))
    if rules:
        blocks.append("APPROVED CREATOR EVOLUTION RULES:\n" + rules)
    return "\n\n".join(blocks)


def build_generation_prompt(seed: str, fmt: str, lane: str, state: dict[str, Any] | None,
                            *, action: str = "evolve",
                            live_stats_block: str = "", sports_ctx: str = "") -> str:
    lane = lane if lane in EMOTION_LANES else DEFAULT_LANE
    context = performance_context(state)
    action = (action or "evolve").strip().lower()
    is_build = action == "build"
    source_label = "SOURCE MATERIAL" if is_build else "CONCEPT"
    opening = (
        "Build 3 distinct, post-ready X drafts from this source material for Creator Evolution."
        if is_build
        else "Turn this concept into 3 post-ready X drafts for Creator Evolution."
    )
    build_rule = (
        "\nBUILD MODE:\n"
        "- If the source includes TOPIC, TENSION, KEY STATS, or ANGLE lines, treat them as a structured brief.\n"
        "- Extract the strongest take and write from scratch; do not simply rephrase the form fields.\n"
        "- Each option should be a different angle or structure, not three small edits of the same draft.\n"
    ) if is_build else ""
    return f"""{opening}

{source_label}:
\"{seed}\"

FORMAT:
{fmt}

PERSONALITY LANE:
{lane}

{context}
{live_stats_block}
{sports_ctx}
{build_rule}

CREATOR EVOLUTION VOICE CONTRACT:
- Default personality is witty edge: funny, pointed, sometimes annoyed, sometimes fired-up, but still human and monetization-safe.
- Sound like a real person posting from their phone, not a content strategy assistant.
- Use specific human reactions, tension, contradiction, and unfinished thoughts.
- Prefer declarative open loops over literal question bait.
- No hashtags, no links unless the user supplied them.
- No invented stats, rankings, injuries, roster facts, or current-event claims.
- No corporate polish, LinkedIn cadence, fake balance, symmetrical three-part essay structure, or over-explaining.
- Never use these phrases: {", ".join(ANTI_AI_BANNED_PHRASES)}.
- Never use Hall of Fame tweets, Hall of Fame examples, Hall of Fame hooks, or static HOF benchmark language.

HIDDEN SELF-CHECK BEFORE FINAL JSON:
Would this sound normal if posted directly from a phone by a funny, witty, sports-obsessed human? If not, rewrite it before returning.

Return ONLY JSON:
{{
  "option1": "post-ready draft",
  "option1_pattern": "short reason this should perform",
  "option2": "post-ready draft",
  "option2_pattern": "short reason this should perform",
  "option3": "post-ready draft",
  "option3_pattern": "short reason this should perform",
  "pick": "1, 2, or 3",
  "pick_reason": "one sentence"
}}"""
