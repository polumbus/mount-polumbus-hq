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
    signal_block = (
        f'\nLIVE SIGNAL FROM @{source_author or "feed"}: "{source_text[:360]}"'
        if source_text
        else ""
    )
    context_block = f'\nWHAT TYLER SAW: "{context.strip()[:360]}"' if context.strip() else ""

    system = """You write live Gameday tweets for Tyler Polumbus.

This is NOT Creator Studio. This is not ESPN. This is a fan instant-reaction device.
Sound like Tyler is watching the game with Denver fans in real time.
Use emotion first, basketball/football knowledge second.
The goal is connection and replies, not proving expertise.
No hashtags. No links. No generic recap. No press-conference voice."""

    prompt = f"""Build 5 ready-to-post Gameday reactions.

GAME:
- Team: {team}
- Opponent: {opponent}
- Score/status: {score} {status}
- Game state: {state or "live/near-live"}
- Moment button: {moment}
- Emotion lane: {lane} ({_LANE_GUIDES[lane]})
{signal_block}{context_block}

TYLER LIVE-REACTION EXAMPLES TO CALIBRATE ENERGY:
{example_block}

RULES:
- Return the actual tweet text only, not notes.
- Each option must be {char_rule}.
- Sound like an emotional fan talking to fans during the game.
- Prefer first person, "we", direct frustration, relief, disbelief, and baitable statements.
- Make people reply because they agree, disagree, are nervous, or want to pile on.
- Use stats only when the score or a specific number is the emotional trigger.
- Do not invent stats, rankings, shot charts, formations, or play analysis.
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


def fallback_gameday_drafts(*, game: dict[str, Any], lane: str, moment: str) -> list[str]:
    lane = normalize_lane(lane)
    moment = normalize_moment(moment)
    team = str(game.get("team") or "Denver")
    opponent = str(game.get("opponent") or "them")
    score = str(game.get("score_line") or f"{team} vs {opponent}")
    if lane == "Fired Up":
        return [
            f"This is the version of {team} I keep talking myself into.",
            "I am trying very hard to act normal right now.",
            f"{score}. I have seen enough. We are allowed to be loud.",
            "That whole possession felt like the building remembered who we are.",
            "I need the next five minutes to look exactly like that.",
        ]
    if lane == "Nervous":
        return [
            "I hate how familiar this feeling is.",
            "We are officially in the part of the game where every possession feels illegal.",
            f"{team} cannot keep making this harder than it needs to be.",
            "This is where Denver sports has trained me to stop breathing.",
            "I do not enjoy how much this game still feels open.",
        ]
    if lane == "Mad":
        return [
            "What are we doing.",
            "That cannot happen in this spot. It just cannot.",
            f"{team} is making the easy part look impossible right now.",
            "Somebody has to calm this down before the whole game turns stupid.",
            "I am begging for one normal possession.",
        ]
    if lane == "Petty":
        return [
            "Funny how quiet it gets when Denver punches back.",
            "The other fanbase had tweets ready five minutes ago. Tough scene.",
            "Refs saw the momentum and immediately wanted camera time.",
            f"{opponent} fans were a lot louder before that possession.",
            "Please keep explaining how Denver is lucky. This is going great.",
        ]
    if lane == "Group Chat":
        return [
            "I cannot believe that worked.",
            "Not great Bob.",
            "We are so back until further notice.",
            "That was disgusting. I loved it.",
            "Please do not make me regret believing again.",
        ]
    if moment == "Collapse":
        return [
            "I know this movie and I hate the ending.",
            "We are really doing this again.",
            "This game was comfortable about six bad decisions ago.",
            "Denver sports cannot just let a person relax.",
            "Somebody stop the bleeding before this gets ridiculous.",
        ]
    return [
        "I am reacting completely normally to this game.",
        f"{team} is making me feel things I was not emotionally prepared for.",
        "This is exactly why we watch and exactly why we age.",
        "The group chat is not surviving this fourth quarter.",
        "I need everyone to pick a side right now.",
    ]


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
        ok, _reason = validate_gameday_draft(clean, longer_take=longer_take)
        if ok and clean.lower() not in seen:
            seen.add(clean.lower())
            valid.append(clean)
        if len(valid) >= 5:
            break
    if len(valid) < 5:
        for fallback in fallback_gameday_drafts(game=game, lane=lane, moment=moment):
            ok, _reason = validate_gameday_draft(fallback, longer_take=longer_take)
            if ok and fallback.lower() not in seen:
                seen.add(fallback.lower())
                valid.append(fallback)
            if len(valid) >= 5:
                break
    return valid[:5], raw
