"""Gameday-specific fan reaction prompt helpers.

This module is intentionally separate from Creator Studio voice rules. Gameday
is a second-screen reaction tool, not a polished analysis writer.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Callable


GAMEDAY_LANES: tuple[str, ...] = (
    "Fan Pulse",
    "Fired Up",
    "Nervous",
    "Mad",
    "Petty",
    "Group Chat",
)

GAMEDAY_MOMENTS: tuple[str, ...] = (
    "Big Play",
    "Bad Possession",
    "Refs",
    "Star Player",
    "Bench",
    "Coach",
    "Collapse",
    "We're Back",
)

_LANE_GUIDES: dict[str, str] = {
    "Fan Pulse": "balanced live fan emotion: direct, human, fast, and replyable",
    "Fired Up": "joy, disbelief, celebration, Denver fans losing their minds together",
    "Nervous": "anxious fan dread, familiar scars, still watching because we care",
    "Mad": "blunt frustration, not a column, not a personal attack, just fed-up fan energy",
    "Petty": "rivalry, refs, opposing fans, media narratives, playful edge",
    "Group Chat": "shortest and most human; sounds like something Tyler would text during the game",
}

_ANALYTICAL_DRIFT = (
    "structural failure",
    "film-room observation",
    "what it means",
    "schematic",
    "scheme",
    "root cause",
    "diagnosis",
    "accountability",
    "coverage shell",
    "offensive process",
    "defensive process",
    "the film shows",
    "from an analytical standpoint",
)

_UNSUPPORTED_EVENT_CLAIMS = (
    "possession",
    "turnover",
    "missed call",
    "bad call",
    "refs",
    "ref ",
    "bench",
    "coach",
    "collapse",
    "big play",
    "foul",
    "flag",
    "interception",
    "fumble",
    "injury",
    "timeout",
    "three",
    "dunk",
    "save",
    "goal",
    "power play",
    "penalty",
    "review",
    "challenge",
    "overturned",
    "ejected",
    "hit that",
    "just happened",
    "momentum",
)

_LIVE_REACTION_MARKERS = (
    "we ",
    "us ",
    "our ",
    "this team",
    "i can't",
    "i hate",
    "i love",
    "not great",
    "god ",
    "come on",
    "here we go",
    "of course",
    "what are we doing",
    "doesn't make it easier",
    "can't afford",
    "lol",
    "hahaha",
)


def normalize_lane(lane: str | None) -> str:
    if lane in GAMEDAY_LANES:
        return str(lane)
    return "Fan Pulse"


def normalize_moment(moment: str | None) -> str:
    if moment in GAMEDAY_MOMENTS:
        return str(moment)
    return "Big Play"


def _tweet_text(tweet: dict[str, Any]) -> str:
    return str(tweet.get("text") or "").strip()


def _metric(tweet: dict[str, Any], *keys: str) -> int:
    for key in keys:
        try:
            value = int(tweet.get(key) or 0)
            if value:
                return value
        except Exception:
            continue
    return 0


def _tweet_datetime(tweet: dict[str, Any]) -> datetime | None:
    raw = str(tweet.get("createdAt") or tweet.get("created_at") or "").strip()
    if not raw:
        return None
    for fmt in ("%a %b %d %H:%M:%S %z %Y", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(raw.replace("Z", "+0000"), fmt)
        except Exception:
            pass
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def gameday_example_score(tweet: dict[str, Any], *, now: datetime | None = None) -> float:
    """Rank tweets for live-reaction usefulness, not polished authority."""
    text = _tweet_text(tweet)
    if not text or text.startswith("RT ") or "http" in text or len(text) > 260:
        return -1
    lower = text.lower()
    replies = _metric(tweet, "replyCount", "reply_count", "replies")
    likes = _metric(tweet, "likeCount", "like_count", "likes")
    rts = _metric(tweet, "retweetCount", "retweet_count", "retweets")
    views = _metric(tweet, "viewCount", "view_count", "views")
    reply_rate = replies / max(views, 1)
    score = replies * 8 + rts * 3 + likes
    score += reply_rate * 100000
    score += sum(18 for marker in _LIVE_REACTION_MARKERS if marker in lower)
    if "?" in text:
        score += 10
    if "!" in text:
        score += 8
    if len(text) <= 140:
        score += 20
    elif len(text) <= 180:
        score += 10
    created = _tweet_datetime(tweet)
    if created:
        now = now or datetime.now(timezone.utc)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        days_old = max((now - created.astimezone(timezone.utc)).days, 0)
        score += max(0, 40 - days_old)
    return score


def select_gameday_examples(tweets: list[dict[str, Any]], *, limit: int = 8) -> list[str]:
    ranked = sorted(
        (t for t in tweets if isinstance(t, dict)),
        key=gameday_example_score,
        reverse=True,
    )
    out: list[str] = []
    seen: set[str] = set()
    for tweet in ranked:
        if gameday_example_score(tweet) < 0:
            continue
        text = re.sub(r"\s+", " ", _tweet_text(tweet))
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        out.append(text[:240])
        if len(out) >= limit:
            break
    return out


def build_gameday_prompt(
    *,
    game: dict[str, Any],
    lane: str,
    moment: str,
    context: str = "",
    signal_tweet: dict[str, Any] | None = None,
    examples: list[str] | None = None,
    longer_take: bool = False,
) -> tuple[str, str]:
    lane = normalize_lane(lane)
    moment = normalize_moment(moment)
    examples = examples or []
    state = str(game.get("state") or "").strip()
    team = str(game.get("team") or "Denver").strip()
    opponent = str(game.get("opponent") or "the opponent").strip()
    score = str(game.get("score_line") or "").strip()
    status = str(game.get("status") or "").strip()
    source_text = str((signal_tweet or {}).get("text") or "").strip()
    source_author = str((signal_tweet or {}).get("author") or "").strip().lstrip("@")
    char_rule = "180 characters max" if not longer_take else "280 characters max"
    example_block = "\n".join(f'- "{ex}"' for ex in examples[:8]) or "- No examples available."
    verified_facts = [
        f"Team: {team}",
        f"Opponent: {opponent}",
        f"Score/status: {score} {status}".strip(),
        f"Game state: {state or 'live/near-live'}",
    ]
    if source_text:
        verified_facts.append(f'Live feed signal from @{source_author or "feed"}: "{source_text[:360]}"')
    if context.strip():
        verified_facts.append(f'Tyler-entered live note: "{context.strip()[:360]}"')
    facts_block = "\n".join(f"- {fact}" for fact in verified_facts if fact.strip())

    system = """You write live Gameday tweets for Tyler Polumbus.

This is NOT Creator Studio. This is not ESPN. This is a fan instant-reaction device.
Sound like Tyler is watching the game with Denver fans in real time.
Use emotion first, basketball/football knowledge second.
The goal is connection and replies, not proving expertise.
No hashtags. No links. No generic recap. No press-conference voice.

TRUST RULE:
You may ONLY reference facts explicitly provided in the prompt.
Do not infer a turnover, missed shot, bad possession, referee mistake, injury, bench issue, coaching mistake, momentum swing, comeback, collapse, or big play unless that exact event is in the live feed signal or Tyler-entered live note.
If the only fact is the score/status, react only to the score/status."""

    prompt = f"""Build 5 ready-to-post Gameday reactions.

VERIFIED LIVE FACTS:
{facts_block}

- Button selected: {moment}
- Emotion lane: {lane} ({_LANE_GUIDES[lane]})

IMPORTANT:
- The selected button is a writing lens, NOT a source of truth.
- Do not claim the button's event happened unless it appears in VERIFIED LIVE FACTS.
- If facts only support a score/status reaction, write score/status reactions.

TYLER LIVE-REACTION EXAMPLES TO CALIBRATE ENERGY:
{example_block}

RULES:
- Return the actual tweet text only, not notes.
- Each option must be {char_rule}.
- Sound like an emotional fan talking to fans during the game.
- Prefer first person, "we", direct frustration, relief, disbelief, and baitable statements.
- Make people reply because they agree, disagree, are nervous, or want to pile on.
- Use numbers only if they appear in VERIFIED LIVE FACTS.
- Do not invent stats, rankings, shot charts, formations, or play analysis.
- Do not invent game events.
- Ban ESPN-style analysis: no "what it means", no schematic breakdown, no "film-room observation", no "structural failure".
- Avoid polished column language. Short, human, immediate.
- Match the selected lane and moment.

Return ONLY this JSON:
{{
  "drafts": [
    {{"text": "tweet 1", "lane": "{lane}", "moment": "{moment}"}},
    {{"text": "tweet 2", "lane": "{lane}", "moment": "{moment}"}},
    {{"text": "tweet 3", "lane": "{lane}", "moment": "{moment}"}},
    {{"text": "tweet 4", "lane": "{lane}", "moment": "{moment}"}},
    {{"text": "tweet 5", "lane": "{lane}", "moment": "{moment}"}}
  ]
}}"""
    return prompt, system


def has_actionable_gameday_context(*, game: dict[str, Any], context: str = "", signal_tweet: dict[str, Any] | None = None) -> tuple[bool, str]:
    """Return whether we have enough truth to draft without making things up."""
    score = str(game.get("score_line") or "").strip()
    status = str(game.get("status") or "").strip()
    source_text = str((signal_tweet or {}).get("text") or "").strip()
    if source_text:
        return True, ""
    if context.strip():
        return True, ""
    if score and status and not any(word in score.lower() for word in (" vs ", "unknown")):
        return True, ""
    return False, "Need live score/status, a feed tweet, or a typed note about what actually happened."


def parse_gameday_drafts(raw: str) -> list[str]:
    clean = (raw or "").strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        data = json.loads(clean)
    except Exception:
        data = None
    if isinstance(data, dict):
        drafts = data.get("drafts") or []
        out = []
        for item in drafts:
            if isinstance(item, dict):
                text = str(item.get("text") or "").strip()
            else:
                text = str(item or "").strip()
            if text:
                out.append(text)
        return out
    matches = re.findall(r'"text"\s*:\s*"((?:[^"\\]|\\.)*)"', clean, flags=re.DOTALL)
    return [m.encode("utf-8").decode("unicode_escape").strip() for m in matches if m.strip()]


def validate_gameday_draft(text: str, *, longer_take: bool = False) -> tuple[bool, str]:
    clean = (text or "").strip()
    if not clean:
        return False, "empty"
    limit = 280 if longer_take else 180
    if len(clean) > limit:
        return False, f"over {limit} chars"
    lower = clean.lower()
    for phrase in _ANALYTICAL_DRIFT:
        if phrase in lower:
            return False, f"analytical drift: {phrase}"
    if lower.startswith(("breaking:", "final:", "analysis:", "takeaway:")):
        return False, "recap opener"
    if "#" in clean or "http" in lower:
        return False, "hashtag/link"
    return True, ""


def validate_gameday_draft_against_facts(
    text: str,
    *,
    game: dict[str, Any],
    context: str = "",
    signal_tweet: dict[str, Any] | None = None,
    longer_take: bool = False,
) -> tuple[bool, str]:
    ok, reason = validate_gameday_draft(text, longer_take=longer_take)
    if not ok:
        return ok, reason
    facts_text = " ".join(
        [
            str(game.get("team") or ""),
            str(game.get("opponent") or ""),
            str(game.get("score_line") or ""),
            str(game.get("status") or ""),
            str(game.get("state") or ""),
            str(context or ""),
            str((signal_tweet or {}).get("text") or ""),
        ]
    ).lower()
    lower = (text or "").lower()
    unsupported = [
        claim
        for claim in _UNSUPPORTED_EVENT_CLAIMS
        if claim in lower and claim not in facts_text
    ]
    if unsupported:
        return False, f"unsupported live event claim: {unsupported[0]}"
    return True, ""


def generate_gameday_drafts(
    *,
    game: dict[str, Any],
    lane: str,
    moment: str,
    context: str,
    signal_tweet: dict[str, Any] | None,
    examples: list[str],
    ai_call: Callable[[str, str, int], str],
    longer_take: bool = False,
) -> tuple[list[str], str]:
    has_context, reason = has_actionable_gameday_context(
        game=game,
        context=context,
        signal_tweet=signal_tweet,
    )
    if not has_context:
        return [], f"NEEDS_CONTEXT: {reason}"
    prompt, system = build_gameday_prompt(
        game=game,
        lane=lane,
        moment=moment,
        context=context,
        signal_tweet=signal_tweet,
        examples=examples,
        longer_take=longer_take,
    )
    raw = ai_call(prompt, system, 900)
    parsed = parse_gameday_drafts(raw)
    valid: list[str] = []
    seen: set[str] = set()
    for draft in parsed:
        clean = re.sub(r"\s+", " ", draft).strip()
        ok, _reason = validate_gameday_draft_against_facts(
            clean,
            game=game,
            context=context,
            signal_tweet=signal_tweet,
            longer_take=longer_take,
        )
        if ok and clean.lower() not in seen:
            seen.add(clean.lower())
            valid.append(clean)
        if len(valid) >= 5:
            break
    return valid[:5], raw
