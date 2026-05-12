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
PROMPT_VERSION = "ce-prompt-v5-voice-profile"
SCORING_VERSION = "ce-score-v3-tracked-cohorts"
RULE_VERSION = "ce-rules-v2-approval-rollback"
API_ESTIMATED_COST_PER_1000_TWEETS = 0.15
DEFAULT_DAILY_API_BUDGET_USD = 0.75
DEFAULT_WEEKLY_API_BUDGET_USD = 3.00
DEFAULT_LANE = "Witty Edge"
EMOTION_LANES = (
    "Witty Edge",
    "Comedic",
    "Annoyed",
    "Fired-Up",
    "Skeptical",
    "Critical",
    "Promo",
    "Celebratory",
    "Deadpan",
    "Sarcastic",
)

LANE_RECIPES = {
    "Witty Edge": {
        "target": "A sharp sports read with one funny pressure point: confident, phone-written, and a little dangerous without getting mean.",
        "do": "Name the exact contradiction, add one human/sports detail, then land a punchline or open loop that makes people want to argue the premise.",
        "avoid": "Content-strategy phrasing, clean essay symmetry, fake questions, hot-take framing, and copied viral hooks.",
        "ending": "A declarative open loop or punchline with one unresolved consequence.",
    },
    "Comedic": {
        "target": "Grok-like sports comedy: funny first, sharp second, fearless without sounding mad. The joke comes from the exact sports contradiction, not profanity, rage, or random analogies.",
        "do": "Find the funniest true pressure point in the topic, then use one clear joke mechanic: literalize team spin, expose fan coping, flip the roster logic, mock-serious diagnosis, or make the sports consequence absurdly plain. Keep it specific and surprising.",
        "avoid": "Anger as the joke, profanity as the punchline, personal abuse, generic meme captions, random non-sports analogies, therapy language, fake-deep closers, and Witty Edge analysis with a cute ending.",
        "ending": "A short punchline that makes the sports situation feel ridiculous on first read. It should sting because it is accurate, not because it is mean.",
    },
    "Annoyed": {
        "target": "Controlled irritation at a repeat decision, excuse, or pattern, never a pile-on against a person.",
        "do": "Name the recurring behavior, explain why it keeps costing them, and keep the anger aimed at the pattern.",
        "avoid": "Personal insults, harassment, all-caps fury, vague 'everyone is stupid' framing, and doom spirals.",
        "ending": "A tight consequence line that makes the annoyance feel earned.",
    },
    "Fired-Up": {
        "target": "Fan-first heat with urgency, belief, and something real at stake.",
        "do": "Sound like you care, attach the energy to the next concrete test, and make the post feel like momentum, not noise.",
        "avoid": "Motivational-poster language, fake certainty, empty 'we are so back' hype, and generic rally cries.",
        "ending": "A strong declarative challenge that dares disagreement without begging for replies.",
    },
    "Skeptical": {
        "target": "Smart doubt that pressures the popular assumption without sounding like default negativity.",
        "do": "Expose the assumption everyone is skipping, ask what has to be true, and leave the optimism on trial.",
        "avoid": "Cynicism for its own sake, prediction cosplay, 'obviously/guaranteed' certainty, and generic contrarian framing.",
        "ending": "A quiet pressure point, not a dunk.",
    },
    "Critical": {
        "target": "Clear diagnosis with accountability: firm, specific, and useful without rage bait.",
        "do": "Name the decision/process failure, connect it to the consequence, and make the critique feel earned by evidence.",
        "avoid": "Personal insults, vague outrage, certainty cosplay, cheap dunking, 'fire everyone' energy, and generic 'this is bad' framing.",
        "ending": "A sharp consequence line that makes the diagnosis feel hard to dodge.",
    },
    "Promo": {
        "text": """PROMO VOICE - VIDEO CLICK TENSION MODE:
PROMO VOICE RULES:
- Sell the unresolved tension in the video, not the existence of the video.
- Make the video feel like the missing third act, not an upload announcement.
- Start from one specific sports contradiction, decision, stat, film tell, or fan assumption.
- Tease the turn without revealing the payoff. The post should stop one beat before the answer.
- Preserve Creator Evolution voice: funny, pointed, conversational, phone-written, and specific.
- Use declarative open loops, not direct engagement questions.
- No question bait.
- No fake urgency, no "you won't believe," no "watch until the end," no "link in bio," no hashtags, no generic CTA.
- If a link is supplied, treat it as attached distribution context. Do not beg for clicks or paste a naked URL unless explicitly requested.
- Punchy: one compact tension beat, no setup, no question closer.
- Normal: specific setup -> tension turn -> cliffhanger ending.
- Long: short setup, stakes, contrast, then stop before the reveal.
- Thread: each segment advances the tension; final segment points at the unresolved reveal without baiting replies.""",
        "target": "A human sports take that makes the video feel like the missing third act. The post should create curiosity around one unresolved tension, not advertise the upload.",
        "do": "Open with the exact pressure point from the video, name the contradiction or uncomfortable stake, tease the turn before the answer, and make the viewer feel the clip/video resolves what the post refuses to finish.",
        "avoid": "Generic marketing, 'new video is up', 'watch now', 'link below', 'you won't believe', fake urgency, hashtags, naked URLs, recap summaries, thumbnail-copy language, creator-speak, and giving away the final reveal.",
        "ending": "A declarative cliffhanger tied to the video subject. Stop one beat before the answer. No generic question closer.",
    },
    "Celebratory": {
        "target": "Specific joy that feels earned, not corporate hype or empty victory-lap energy.",
        "do": "Celebrate the exact detail that changed the mood and connect it to what it unlocks next.",
        "avoid": "Corporate hype words, victory-lap cliches, empty 'let's go' filler, 'massive/unreal/so back' defaults, and generic positivity.",
        "ending": "A specific emotional payoff or forward statement.",
    },
    "Deadpan": {
        "target": "Straight-faced, compact, and quietly ridiculous.",
        "do": "Say the absurd part as plainly as possible and stop before explaining it.",
        "avoid": "Exclamation marks, emojis, winking, 'lol', and punchline explanation.",
        "ending": "A hard stop or tiny unfinished thought that gets funnier because it is underplayed.",
    },
    "Sarcastic": {
        "text": """SARCASTIC VOICE — DRY HUMOR MODE:
SARCASTIC VOICE RULES:
- Two modes: Cultural Leap (positive moments) or Implied Real Story (negative moments)
- Cultural Leap: Jump to a completely unrelated world. Specific person in a specific human situation. Never explain.
- Implied Real Story: State the surface story as if neutral. Imply the real story underneath. Never state it directly.
- The sarcasm must reveal a sports truth, not just sound clever.
- Never use generic openers like "Oh interesting" "Sure" "Cool" "Oh great"
- Never copy old sarcastic examples, sentence frames, or punchline structures.
- Drop it and walk away. Never explain the joke.""",
        "target": "Dry sarcasm that reveals the real sports story through implication or a specific cultural leap, without copied examples.",
        "do": "Use Cultural Leap for positive moments or Implied Real Story for negative moments.",
        "avoid": "Generic sarcastic openers, joke explanation, copied examples, direct insults, and fallback default voice.",
        "ending": "Drop it and walk away. Never explain the joke.",
    },
}

FORMAT_RECIPES = {
    "Punchy Tweet": {
        "target": "70-160 characters. One sharp, complete reaction with a visible tension, joke, or contradiction.",
        "structure": "No setup paragraph. No line breaks. One or two sentences that land fast and feel typed on a phone, with varied openings and endings across options.",
        "must": "Every option must make one specific point, create curiosity without asking for engagement, and choose the punchy structure that fits the idea.",
        "avoid": "Explaining context, adding a second angle, soft qualifiers, generic hype, vague reaction-caption energy, or using the same punchline rhythm every time.",
    },
    "Normal Tweet": {
        "target": "161-260 preferred characters. Hard validator tolerance: 140-280.",
        "structure": "Preferred shape is two or three natural sentences, then one intentional line break, then one final statement that invites engagement without asking a direct question. Strong one-paragraph versions are allowed when they sound more natural.",
        "must": "Every option must choose the structure that fits the idea, vary the final line type, and avoid making all Normal Tweets look like the same AI formula. The final line must create response pressure through a dramatic ending, an alluded question without a question mark, a declarative argument statement, a consequence line, or quote-tweet bait. Ellipsis endings are allowed and often good, but rotate with hard-period tension lines.",
        "avoid": "Going over 280 characters, thread markers, repeated blank-line cadence, direct question closers, engagement bait, perfect essay punctuation, or ending every option with ellipsis.",
    },
    "Long Tweet": {
        "target": "261-700 preferred characters. Hard validator tolerance: 260-900.",
        "structure": "Opening take, 2-3 short evidence/contrast beats, then a memorable closing turn. Vary whether the final turn is consequence, irony, tension, or a clean walk-off.",
        "must": "Every option must reward the extra length with escalation, specificity, and a structure that fits the idea instead of a fixed long-tweet template.",
        "avoid": "Thread markers, article headings, recap paragraphs, filler transitions, stretching one normal tweet into a bloated post, or repeating the same final-turn formula.",
    },
    "Thread": {
        "target": "4-7 tweets. Each tweet must stand alone and stay under 280 characters.",
        "structure": "Separate tweets with ---TWEET---. Tweet 1 hooks the tension, middle tweets escalate or reframe, final tweet lands the takeaway, but the sequence should vary by topic.",
        "must": "Every option must contain at least 4 tweet segments, each segment must earn its slot with a new beat, and the thread arc must fit the idea.",
        "avoid": "One long paragraph, numbered article sections, repeated setup lines, a normal tweet chopped into pieces, or the same hook-middle-close pattern every time.",
    },
    "Article": {
        "target": "700-1,200 words per option. A real X Article/short column, not a tweet.",
        "structure": "Headline, sharp intro, 3-5 section headings, concrete examples or consequences, and a closing take worth remembering. Vary the section rhythm and argument path by topic.",
        "must": "Every option must read like a complete opinion column with a clear argument, no invented facts, and an article shape chosen for the idea.",
        "avoid": "Tweet-length output, thread markers, generic newsletter tone, filler sections, a headline attached to a caption, or a reusable article skeleton.",
    },
}


def format_recipe(fmt: str) -> dict[str, str]:
    fmt = fmt if fmt in FORMAT_RECIPES else "Normal Tweet"
    return dict(FORMAT_RECIPES[fmt])


def format_recipe_text(fmt: str) -> str:
    fmt = fmt if fmt in FORMAT_RECIPES else "Normal Tweet"
    recipe = format_recipe(fmt)
    return "\n".join([
        f"{fmt}:",
        f"- Target: {recipe['target']}",
        f"- Structure: {recipe['structure']}",
        f"- Must: {recipe['must']}",
        f"- Avoid: {recipe['avoid']}",
    ])

SYNC_BUDGETS = {
    "history": {
        "label": "saved history refresh",
        "estimated_requests": 0,
        "estimated_tweets_read": 0,
        "estimated_cost_usd": 0.0,
        "needs_confirmation": False,
    },
    "latest": {
        "label": "latest tweet sync",
        "estimated_requests": 4,
        "estimated_tweets_read": 80,
        "estimated_cost_usd": round(80 / 1000 * API_ESTIMATED_COST_PER_1000_TWEETS, 4),
        "needs_confirmation": False,
    },
    "backfill": {
        "label": "deep tweet backfill",
        "estimated_requests": 120,
        "estimated_tweets_read": 3200,
        "estimated_cost_usd": round(3200 / 1000 * API_ESTIMATED_COST_PER_1000_TWEETS, 4),
        "needs_confirmation": True,
    },
}

BUDGET_POLICY = {
    "provider": "twitterapi.io",
    "daily_cap_usd": DEFAULT_DAILY_API_BUDGET_USD,
    "weekly_cap_usd": DEFAULT_WEEKLY_API_BUDGET_USD,
    "estimated_cost_per_1000_tweets": API_ESTIMATED_COST_PER_1000_TWEETS,
}

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

ENGAGEMENT_BAIT_PHRASES = (
    "thoughts?",
    "what do you think?",
    "agree?",
    "am i wrong?",
    "prove me wrong",
    "drop your",
    "reply with",
    "tell me why",
)

LINKEDIN_CADENCE_PHRASES = (
    "not only",
    "but also",
    "the reality is",
    "the truth is",
    "let that sink in",
    "read that again",
    "this matters because",
)


COMEDIC_FAKE_MARKERS = (
    "lol",
    "lmao",
    "it's giving",
    "so unserious",
    "very normal",
    "normal stuff",
    "normal little",
    "very calm stuff",
    "funny how that works",
    "cute",
    "very serious operation",
    "very brave loophole",
    "this is wild",
    "you can't make this up",
    "football for",
    "in football speak",
    "sounds like",
    "translates to",
    "feels like front office for",
)

COMEDIC_RANDOM_ANALOGY_TERMS = (
    "hr",
    "meeting",
    "email",
    "calendar invite",
    "performance review",
    "paperwork",
    "office",
    "group project",
    "kitchen",
    "raccoon",
    "bucket",
    "smoke alarm",
    "smoke detector",
    "ceiling leak",
    "lease",
    "restaurant",
    "menu",
    "tinder",
    "bad tinder date",
    "divorce papers",
    "side piece",
    "haunted",
    "basement",
    "house fire",
    "fire",
    "drunk friend",
    "passenger seat",
    "air freshener",
    "courtroom drama",
    "congressional hearing",
    "ted talk",
)

COMEDIC_PROFANITY_TERMS = (
    "fuck",
    "fucked",
    "fucking",
    "shit",
    "bullshit",
    "goddamn",
    "my ass",
)

COMEDIC_ANGRY_CLOSERS = (
    "bullshit ends",
    "bullshit with",
    "exposed",
    "got caught",
    "caught lying",
    "lying through",
    "dragged to hell",
    "eviscerate",
    "zero mercy",
    "pathetic",
    "cowards",
    "coward shit",
    "fragile little",
    "bums",
    "same scared shit",
    "nobody buys it",
    "they lied",
    "scam",
)

COMEDIC_ANALYSIS_DRIFT = (
    "the real tell is",
    "truth shows up",
    "public words are cheap",
    "talk is cheap",
    "backup reps tell the truth",
    "depth chart tells the truth",
    "depth chart truth hits different",
    "that tells you everything",
    "this is where it gets interesting",
    "where it gets interesting",
    "the conversation gets real",
    "conversation gets uncomfortable",
    "the plan gets exposed",
    "press conference with vibes",
    "real press conference",
    "this is where it gets real",
    "that is where this gets real",
    "the next qb decision will be the interesting part",
    "that part usually ruins the calm",
    "that transaction will tell the truth",
    "the actual injury report",
    "the real update",
    "the real translation",
)

COMEDIC_NONSENSE_PUNCHLINES = (
    "heard the same ankle",
    "clipboard will start singing",
    "clipboard starts singing",
    "clipboard is singing",
    "ankle starts talking",
    "ankle is talking",
    "ankle said",
    "knee said",
    "hamstring said",
    "shoulder said",
    "the injury spoke",
    "the injury talks",
    "shopping nervous",
    "football fluency",
)


LANE_ALIASES = {
    "Amused": "Comedic",
}


def normalize_lane(lane: str) -> str:
    lane = str(lane or "").strip()
    lane = LANE_ALIASES.get(lane, lane)
    return lane if lane in EMOTION_LANES else DEFAULT_LANE


def lane_recipe(lane: str) -> dict[str, str]:
    lane = normalize_lane(lane)
    return dict(LANE_RECIPES[lane])


def lane_recipe_text(lane: str) -> str:
    lane = normalize_lane(lane)
    recipe = lane_recipe(lane)
    if recipe.get("text"):
        return str(recipe["text"]).strip()
    return "\n".join([
        f"{lane}:",
        f"- Target: {recipe['target']}",
        f"- Do: {recipe['do']}",
        f"- Avoid: {recipe['avoid']}",
        f"- Ending: {recipe['ending']}",
    ])


def sync_budget_for_mode(mode: str) -> dict[str, Any]:
    key = mode if mode in SYNC_BUDGETS else "history"
    budget = dict(SYNC_BUDGETS[key])
    budget["mode"] = key
    budget["provider"] = BUDGET_POLICY["provider"]
    budget["daily_cap_usd"] = BUDGET_POLICY["daily_cap_usd"]
    budget["weekly_cap_usd"] = BUDGET_POLICY["weekly_cap_usd"]
    budget["blocked_by_budget"] = budget["estimated_cost_usd"] > BUDGET_POLICY["daily_cap_usd"]
    return budget


def api_cost_estimate(*, requests: int = 0, tweets_read: int = 0,
                      policy: dict[str, Any] | None = None) -> dict[str, Any]:
    policy = dict(BUDGET_POLICY if policy is None else policy)
    cost_per_1000 = float(policy.get("estimated_cost_per_1000_tweets", API_ESTIMATED_COST_PER_1000_TWEETS) or 0)
    estimated_cost = round(max(tweets_read, 0) / 1000.0 * cost_per_1000, 4)
    return {
        "provider": policy.get("provider", "twitterapi.io"),
        "estimated_requests": max(int(requests or 0), 0),
        "estimated_tweets_read": max(int(tweets_read or 0), 0),
        "estimated_cost_usd": estimated_cost,
        "daily_cap_usd": float(policy.get("daily_cap_usd", DEFAULT_DAILY_API_BUDGET_USD) or 0),
        "weekly_cap_usd": float(policy.get("weekly_cap_usd", DEFAULT_WEEKLY_API_BUDGET_USD) or 0),
        "blocked_by_daily_cap": estimated_cost > float(policy.get("daily_cap_usd", DEFAULT_DAILY_API_BUDGET_USD) or 0),
    }


def budget_preflight_for_mode(mode: str, policy: dict[str, Any] | None = None) -> dict[str, Any]:
    budget = sync_budget_for_mode(mode)
    estimate = api_cost_estimate(
        requests=budget.get("estimated_requests", 0),
        tweets_read=budget.get("estimated_tweets_read", 0),
        policy=policy,
    )
    estimate.update({
        "mode": budget["mode"],
        "label": budget["label"],
        "needs_confirmation": budget["needs_confirmation"],
        "blocked_by_budget": estimate["blocked_by_daily_cap"],
    })
    return estimate


def build_hot_signal_brief(topic: str, seed: str, source: str, why: str, lane: str, fmt: str) -> str:
    lane = normalize_lane(lane)
    topic = str(topic or "Trending angle").strip()
    seed = str(seed or topic).strip()
    source = str(source or "hot feed").strip()
    why = str(why or "Active conversation signal").strip()
    fmt = str(fmt or "Normal Tweet").strip()
    format_behavior = format_recipe_text(fmt)
    return f"""HOT SIGNAL:
{topic}

SOURCE MATERIAL:
{seed}

WHY THIS IS MOVING:
{why}

SOURCE:
{source}

FORMAT:
{fmt}

FORMAT BEHAVIOR:
{format_behavior}

PERSONALITY LANE:
{lane}

LANE BEHAVIOR:
{lane_recipe_text(lane)}

CREATOR EVOLUTION BUILD RULES:
- Treat this as source material, not as finished copy.
- Use the Creator Evolution lane behavior above, approved live-performance rules, and the current quality gate.
- Do not use Creator Studio voice modes, Creator Studio Hall of Fame calibration, or old What's Hot hook formulas.
- Do not invent stats, injuries, transactions, rankings, or current-event claims beyond the source material.
- Turn the hot signal into a post that sounds like a person reacting in real time, not a content calendar."""


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


def risk_hits(text: str) -> list[str]:
    lower = text.lower()
    return [term for term in RISK_TERMS if term in lower]


def ai_sounding_hits(text: str) -> list[str]:
    lower = text.lower()
    return [phrase for phrase in ANTI_AI_BANNED_PHRASES if phrase in lower]


def engagement_bait_hits(text: str) -> list[str]:
    lower = text.lower().strip()
    tail = lower[-100:]
    return [phrase for phrase in ENGAGEMENT_BAIT_PHRASES if phrase in tail]


PROMO_CLICKBAIT_PHRASES = (
    "you won't believe",
    "you wont believe",
    "watch until the end",
    "must watch",
    "watch now",
    "new video is live",
    "new video",
    "new episode is live",
    "link below",
    "link in bio",
    "smash",
    "full breakdown here",
    "full breakdown",
    "full video",
    "go check it out",
    "like and subscribe",
    "subscribe",
    "comment below",
    "just dropped",
    "premiere",
    "shocking",
    "crazy reveal",
    "this changes everything",
    "insane ending",
    "will blow your mind",
    "click here",
)

PROMO_CLIFFHANGER_MARKERS = (
    "...",
    "…",
    "but",
    "until",
    "before",
    "right before",
    "the part nobody",
    "the part that changes",
    "what happens next",
    "where it gets interesting",
    "that's where",
    "the problem is",
    "the question is",
    "points somewhere else",
    "points somewhere more uncomfortable",
    "where the whole argument flips",
    "where the video gets weird",
    "missing third act",
)

PROMO_SPECIFIC_TENSION_TERMS = (
    "decision",
    "stat",
    "film",
    "clip",
    "qb",
    "ankle",
    "camp",
    "trust",
    "trusted",
    "ready",
    "box score",
    "sequence",
    "forced",
    "switch",
    "pressure",
    "contradiction",
    "assumption",
    "rotation",
    "bench",
    "protection",
    "scheme",
    "matchup",
    "roster",
    "goalie",
    "quarterback",
    "line",
    "series",
)

PROMO_GENERIC_FRAMES = (
    "this video is about",
    "there is a lot to talk about",
    "things are changing",
    "what happens next",
    "a lot going on",
    "you need to see",
)


def promo_clickbait_hits(text: str) -> list[str]:
    lower = text.lower()
    return [phrase for phrase in PROMO_CLICKBAIT_PHRASES if phrase in lower]


def has_promo_cliffhanger(text: str) -> bool:
    lower = text.lower().strip()
    tail = lower[-160:]
    return any(marker in tail for marker in PROMO_CLIFFHANGER_MARKERS)


def has_promo_specific_tension(text: str) -> bool:
    lower = text.lower()
    if any(frame in lower for frame in PROMO_GENERIC_FRAMES):
        return False
    hits = [
        term
        for term in PROMO_SPECIFIC_TENSION_TERMS
        if (
            term in lower
            if " " in term
            else re.search(rf"\b{re.escape(term)}\b", lower)
        )
    ]
    return len(hits) >= 2


def cadence_hits(text: str) -> list[str]:
    lower = text.lower()
    hits = [phrase for phrase in LINKEDIN_CADENCE_PHRASES if phrase in lower]
    if re.search(r"\bnot (just|only)\b.{0,80}\bbut\b", lower):
        hits.append("not-just-but cadence")
    if re.search(r"\bhere are \d+\b", lower):
        hits.append("numbered content cadence")
    return list(dict.fromkeys(hits))


GENERIC_OPTION_FRAMES = (
    "this denver sports moment",
    "where it gets interesting",
    "where it gets weird",
    "the uncomfortable part is",
    "that is where",
    "that's where",
    "it matters because",
    "the public answer matters less",
)

CONCRETE_SPORTS_TERMS = (
    "broncos", "nuggets", "avs", "avalanche", "buffs", "rockies", "rapids",
    "qb", "quarterback", "goalie", "coach", "roster", "draft", "trade", "camp",
    "ankle", "presser", "press conference", "lineup", "rotation", "bench", "series",
    "period", "quarter", "playoff", "offseason", "front office", "ownership",
    "payton", "nix", "jokic", "mackinnon", "wedgwood", "wedgewood", "blackwood",
)


def _has_emoji(text: str) -> bool:
    return bool(re.search(r"[\U0001F300-\U0001FAFF]", str(text or "")))


def _specificity_signal_count(text: str) -> int:
    lower = str(text or "").lower()
    term_hits = 0
    for term in CONCRETE_SPORTS_TERMS:
        if (
            term in lower
            if " " in term
            else re.search(rf"\b{re.escape(term)}\b", lower)
        ):
            term_hits += 1
    name_hits = len(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b", str(text or "")))
    numeric_hits = len(re.findall(r"\b\d+(?:[-.]\d+)?\b", str(text or "")))
    return term_hits + min(name_hits, 4) + min(numeric_hits, 3)


def polished_punctuation_hits(text: str) -> list[str]:
    clean = str(text or "").replace("---TWEET---", "")
    checks = (
        ("hyphen/dash", r"[-–—]"),
        ("semicolon", r";"),
        ("colon", r":"),
        ("parentheses", r"[()]"),
        ("brackets", r"[\[\]{}]"),
    )
    return [label for label, pattern in checks if re.search(pattern, clean)]


def _final_sentence(text: str) -> str:
    clean = str(text or "").replace("---TWEET---", " ").strip()
    parts = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", clean) if part.strip()]
    return parts[-1] if parts else clean


def _phrase_hits(lower: str, phrases: tuple[str, ...]) -> list[str]:
    hits = []
    for phrase in phrases:
        phrase_lower = phrase.lower()
        if re.fullmatch(r"[a-z0-9']+", phrase_lower):
            if re.search(rf"\b{re.escape(phrase_lower)}\b", lower):
                hits.append(phrase)
        elif phrase_lower in lower:
            hits.append(phrase)
    return hits


def draft_quality_report(text: str, fmt: str = "Normal Tweet", lane: str = DEFAULT_LANE) -> dict[str, Any]:
    text = str(text or "").strip()
    fmt = fmt or "Normal Tweet"
    lane = normalize_lane(lane)
    lower = text.lower()
    issues: list[str] = []
    warnings: list[str] = []
    ai_hits = ai_sounding_hits(text)
    risky = risk_hits(text)
    bait = engagement_bait_hits(text)
    cadence = cadence_hits(text)
    polished_punctuation = polished_punctuation_hits(text)
    char_count = len(text)
    sentence_count = len([part for part in re.split(r"[.!?]+", text) if part.strip()])
    paragraph_breaks = len(re.findall(r"\n\s*\n", text))
    non_empty_lines = [line.strip() for line in text.splitlines() if line.strip()]

    if not text:
        issues.append("Empty draft.")
    if fmt == "Punchy Tweet":
        if char_count > 160:
            issues.append("Punchy Tweet must stay under 160 characters.")
        if sentence_count > 2:
            issues.append("Punchy Tweet must be one or two sentences maximum.")
        if "\n" in text:
            warnings.append("Punchy Tweet should not use line breaks.")
    elif fmt == "Normal Tweet":
        if char_count < 140:
            issues.append("Normal Tweet is too short; use the 161-260 character format space.")
        if char_count > 280:
            issues.append("Normal Tweet must stay under 280 characters.")
        if paragraph_breaks > 1:
            issues.append("Normal Tweet should not use multiple blank-line breaks.")
        if paragraph_breaks == 1:
            parts = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
            final_part = parts[-1] if parts else ""
            first_part = parts[0] if parts else ""
            first_sentence_count = len([part for part in re.split(r"[.!?]+", first_part) if part.strip()])
            final_sentence_count = len([part for part in re.split(r"[.!?]+", final_part) if part.strip()])
            if first_sentence_count < 2 or first_sentence_count > 3:
                warnings.append("Normal Tweet usually works best when the first paragraph is two or three sentences.")
            if final_sentence_count != 1:
                warnings.append("Normal Tweet final line usually works best as one final statement.")
            if final_part.rstrip().endswith("?"):
                issues.append("Normal Tweet final line should invite replies without a direct question.")
        elif text.rstrip().endswith("?"):
            issues.append("Normal Tweet should invite replies without a direct question closer.")
    elif fmt == "Long Tweet":
        if char_count < 260:
            issues.append("Long Tweet is too short; it should be a real long-form single post.")
        if char_count > 900:
            issues.append("Long Tweet is too long; keep it under 900 characters.")
        if "---TWEET---" in text:
            issues.append("Long Tweet should be one post, not a thread.")
    elif fmt == "Thread":
        segments = [seg.strip() for seg in text.split("---TWEET---") if seg.strip()]
        if len(segments) < 4:
            issues.append("Thread format must include at least 4 tweet segments separated by ---TWEET---.")
        if any(len(seg) > 280 for seg in segments):
            issues.append("Every thread segment must stay under 280 characters.")
    elif fmt == "Article":
        if char_count < 1800:
            issues.append("Article format is too short; it should be a real article draft, not a tweet.")
        if "---TWEET---" in text:
            issues.append("Article format should not use thread separators.")
        if len(re.findall(r"\n[A-Z][A-Za-z0-9 ,'/-]{4,80}\n", f"\n{text}\n")) < 2:
            warnings.append("Article should include visible section headings.")
    if ai_hits:
        issues.append("Contains banned AI/content-strategy wording: " + ", ".join(ai_hits[:4]))
    if bait:
        issues.append("Ends like engagement bait instead of a human open loop: " + ", ".join(bait[:3]))
    if cadence:
        warnings.append("Sounds polished or LinkedIn-ish: " + ", ".join(cadence[:4]))
    if polished_punctuation:
        issues.append("Uses polished punctuation that does not sound like Tyler: " + ", ".join(polished_punctuation[:4]))
    if text.rstrip().endswith("?"):
        warnings.append("Direct question closer. Prefer declarative tension unless the question is truly the joke.")
    if fmt == "Punchy Tweet" and "\n" in text:
        warnings.append("Too many line breaks for this format; it may read like a template.")
    elif fmt == "Normal Tweet" and (paragraph_breaks >= 2 or len(non_empty_lines) > 3):
        warnings.append("Too many line breaks for this format; it may read like a template.")
    if re.search(r"\b(i think|honestly|maybe|kind of|sort of)\b", lower):
        warnings.append("Hedging weakens the human read; make the take cleaner or funnier.")

    if fmt in ("Normal Tweet", "Long Tweet", "Thread", "Article", "Punchy Tweet") and _specificity_signal_count(text) == 0:
        issues.append("Needs a concrete sports/source detail so it does not read like generic strategy copy.")

    if risky and lane in ("Annoyed", "Fired-Up"):
        issues.append("Heated lane is targeting people instead of the decision/pattern: " + ", ".join(risky[:4]))
    elif len(risky) >= 2:
        issues.append("Risky language stack may hurt monetization safety: " + ", ".join(risky[:4]))
    elif risky:
        warnings.append("Risky language detected; keep the target on the take, not the person: " + ", ".join(risky))

    if lane == "Deadpan" and ("!" in text or "lol" in lower):
        issues.append("Deadpan should stay straight-faced: no exclamation marks or lol.")
    if lane == "Deadpan" and _has_emoji(text):
        issues.append("Deadpan should stay straight-faced: no emojis.")
    if lane == "Witty Edge" and any(phrase in lower for phrase in ("hot take", "unpopular opinion", "hear me out")):
        issues.append("Witty Edge should not lean on hot-take or stock engagement framing.")
    if lane == "Fired-Up" and any(phrase in lower for phrase in ("we are so back", "we're so back", "let's go", "nobody wants us")):
        issues.append("Fired-Up needs specific stakes, not generic rally-cry hype.")
    if lane == "Critical":
        if any(phrase in lower for phrase in ("fire everyone", "trash", "garbage", "clown show")):
            issues.append("Critical should diagnose the failure without cheap rage-bait language.")
        if text.rstrip().endswith("?"):
            issues.append("Critical should end with a consequence line, not a direct question closer.")
    if lane == "Sarcastic":
        if any(phrase in lower for phrase in ("turns out", "bold of", "needs to call someone", "starting to feel like")):
            issues.append("Sarcastic lane cannot copy old example frames or familiar sarcastic templates.")
        if lower.startswith(("sure", "cool", "oh great", "oh interesting")):
            issues.append("Sarcastic lane should not use generic sarcastic openers.")
        if risky:
            issues.append("Sarcastic lane should imply the real story without direct insults: " + ", ".join(risky[:4]))
    if lane == "Comedic":
        fake_markers = _phrase_hits(lower, COMEDIC_FAKE_MARKERS)
        random_terms = _phrase_hits(lower, COMEDIC_RANDOM_ANALOGY_TERMS)
        angry_terms = _phrase_hits(lower, COMEDIC_ANGRY_CLOSERS)
        analysis_terms = _phrase_hits(lower, COMEDIC_ANALYSIS_DRIFT)
        nonsense_terms = _phrase_hits(lower, COMEDIC_NONSENSE_PUNCHLINES)
        profanity_terms = _phrase_hits(lower, COMEDIC_PROFANITY_TERMS)
        final_words = len(re.findall(r"\b[\w']+\b", _final_sentence(text)))
        if fake_markers or _has_emoji(text):
            issues.append("Comedic should be funny through the topic, not meme-caption energy: " + ", ".join(fake_markers[:4] or ["emoji"]))
        if random_terms:
            issues.append("Comedic joke drifted into random analogy instead of topic reality: " + ", ".join(random_terms[:4]))
        if angry_terms:
            issues.append("Comedic should be funny first, not angry or accusatory: " + ", ".join(angry_terms[:4]))
        if analysis_terms:
            issues.append("Comedic should not collapse into Witty Edge analysis: " + ", ".join(analysis_terms[:4]))
        if nonsense_terms:
            issues.append("Comedic punchline is confusing or surreal instead of funny: " + ", ".join(nonsense_terms[:4]))
        if profanity_terms:
            specificity_count = _specificity_signal_count(text)
            if len(profanity_terms) > 1 or specificity_count <= 3:
                issues.append("Comedic profanity is replacing the joke instead of seasoning a sports-specific punchline: " + ", ".join(profanity_terms[:4]))
        if fmt == "Normal Tweet" and len(non_empty_lines) > 1 and final_words > 12:
            issues.append("Comedic final beat should be a short punchline, not an explained closer.")
    if lane == "Celebratory" and any(phrase in lower for phrase in ("let's go", "massive", "unreal", "so back")):
        issues.append("Celebratory works better when the joy is specific instead of generic hype.")
    if lane == "Skeptical" and any(phrase in lower for phrase in ("everyone knows", "obviously", "clearly", "guaranteed", "book it")):
        issues.append("Skeptical should feel like doubt, not certainty or prediction cosplay.")
    if lane == "Promo":
        clickbait = promo_clickbait_hits(text)
        if clickbait:
            issues.append("Promo cannot use cheap clickbait phrasing: " + ", ".join(clickbait[:3]))
        if "http://" in lower or "https://" in lower:
            issues.append("Promo should treat video links as attached distribution context, not naked prose.")
        if text.rstrip().endswith("?"):
            issues.append("Promo should end with a declarative cliffhanger, not a direct question.")
        if not has_promo_specific_tension(text):
            issues.append("Promo needs a specific sports tension, contradiction, decision, stat, film tell, or fan assumption.")
        if not has_promo_cliffhanger(text):
            warnings.append("Promo should end with a real video-tension cliffhanger or open loop.")

    penalty = len(issues) * 25 + len(warnings) * 8
    score = max(0, min(100, 100 - penalty))
    return {
        "ok": not issues,
        "score": score,
        "issues": issues,
        "warnings": warnings,
        "ai_sounding_hits": ai_hits,
        "risk_hits": risky,
        "engagement_bait_hits": bait,
        "cadence_hits": cadence,
        "polished_punctuation_hits": polished_punctuation,
        "char_count": char_count,
        "prompt_version": PROMPT_VERSION,
    }


def _option_signature(text: str) -> tuple[str, str, str]:
    clean = str(text or "").strip()
    first_line = clean.splitlines()[0].strip().lower() if clean else ""
    first_words = " ".join(re.findall(r"[a-z0-9']+", first_line)[:3])
    line_skeleton = "-".join("x" for line in clean.splitlines() if line.strip())
    lower = clean.lower()
    frame = ""
    for phrase in GENERIC_OPTION_FRAMES:
        if phrase in lower:
            frame = phrase
            break
    return first_words, line_skeleton, frame


def _option_set_findings(data: dict[str, Any], fmt: str | None = None) -> dict[str, list[str]]:
    options = {
        option_key: str(data.get(option_key) or "").strip()
        for option_key in ("option1", "option2", "option3")
        if str(data.get(option_key) or "").strip()
    }
    findings = {key: [] for key in options}
    if len(options) < 2:
        return findings

    signatures = {key: _option_signature(text) for key, text in options.items()}
    first_word_counts: dict[str, int] = {}
    skeleton_counts: dict[str, int] = {}
    frame_counts: dict[str, int] = {}
    for first_words, skeleton, frame in signatures.values():
        if first_words:
            first_word_counts[first_words] = first_word_counts.get(first_words, 0) + 1
        if skeleton:
            skeleton_counts[skeleton] = skeleton_counts.get(skeleton, 0) + 1
        if frame:
            frame_counts[frame] = frame_counts.get(frame, 0) + 1

    for key, (first_words, skeleton, frame) in signatures.items():
        if first_words and first_word_counts.get(first_words, 0) >= 2:
            findings[key].append("Generated options repeat the same opener; each option needs a distinct first move.")
        skeleton_line_count = len(skeleton.split("-")) if skeleton else 0
        if (
            fmt == "Normal Tweet"
            and skeleton
            and skeleton_line_count >= 2
            and skeleton_counts.get(skeleton, 0) == len(options)
            and len(options) >= 3
        ):
            findings[key].append("Generated options repeat the same line-break skeleton; vary the structure across options.")
        if frame and frame_counts.get(frame, 0) >= 2:
            findings[key].append(f"Generated options repeat generic frame '{frame}'; replace it with source-specific wording.")
    ellipsis_endings = [
        key
        for key, text in options.items()
        if text.rstrip().endswith(("...", "…"))
    ]
    if len(options) >= 3 and len(ellipsis_endings) == len(options):
        for key in ellipsis_endings:
            findings[key].append("Generated options all end with ellipsis; keep ellipsis available but vary at least one ending type.")
    return findings


def validate_generation_options(data: dict[str, Any], fmt: str, lane: str) -> dict[str, dict[str, Any]]:
    reports: dict[str, dict[str, Any]] = {}
    option_set_findings = _option_set_findings(data, fmt)
    for option_key in ("option1", "option2", "option3"):
        if data.get(option_key):
            report = draft_quality_report(str(data[option_key]), fmt, lane)
            set_issues = option_set_findings.get(option_key, [])
            if set_issues:
                report = dict(report)
                report["issues"] = list(dict.fromkeys(list(report.get("issues", []) or []) + set_issues))
                report["ok"] = False
                report["score"] = max(0, min(100, int(report.get("score", 100) or 100) - len(set_issues) * 25))
            reports[option_key] = report
    return reports


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
    ai_hits = ai_sounding_hits(text)
    risk_penalty = min(16.0, risk * 4.0)
    link_penalty = 4.0 if "http" in text.lower() else 0.0
    score = max(0.0, reach_score + reply_score + share_score + affinity_score - risk_penalty - link_penalty)

    false_winner = bool(
        views >= 1000
        and replies >= 8
        and (risk > 0 or replies > max(likes, 1) * 0.9)
        and repost_per_1k < 1.2
    )
    false_loser = bool(
        lifecycle in ("mature", "archived")
        and views < 2500
        and replies >= 4
        and reply_per_1k >= 5.0
        and risk == 0
        and not ai_hits
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
            "false_loser": false_loser,
            "risky_language": risk > 0,
            "ai_sounding_hits": ai_hits,
        },
    }


def _proposal_id(rule: str, evidence_ids: list[str]) -> str:
    raw = f"{rule}|{'|'.join(sorted(evidence_ids))}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _ending_style(text: str) -> str:
    clean = str(text or "").strip()
    if not clean:
        return "none"
    if clean.endswith("?"):
        return "question"
    if clean.endswith("...") or clean.endswith("…"):
        return "ellipsis"
    if clean.endswith("!"):
        return "exclamation"
    if clean.endswith("."):
        return "period"
    return "open"


def _format_features(text: str) -> dict[str, Any]:
    clean = str(text or "").strip()
    sentences = [part for part in re.split(r"[.!?]+", clean) if part.strip()]
    lines = [line for line in clean.splitlines() if line.strip()]
    thread_segments = [seg.strip() for seg in clean.split("---TWEET---") if seg.strip()]
    return {
        "char_count": len(clean),
        "sentence_count": len(sentences),
        "line_breaks": max(len(lines) - 1, 0),
        "ending": _ending_style(clean),
        "thread_segments": len(thread_segments) if "---TWEET---" in clean else 0,
        "has_question": "?" in clean,
        "has_ellipsis": "..." in clean or "…" in clean,
    }


VOICE_TENSION_TERMS = (
    "uncomfortable", "weird", "boring", "pressure", "plan", "window",
    "actual", "real", "funny", "annoying", "stress", "chaos", "tell",
    "problem", "mistake", "thing", "move", "roster",
)


def _opening_style(text: str) -> str:
    clean = str(text or "").strip()
    first = clean.splitlines()[0].strip() if clean else ""
    lower = first.lower()
    if not first:
        return "none"
    if first.endswith("?"):
        return "direct question"
    if lower.startswith(("breaking", "report", "sources")):
        return "news beat"
    if re.match(r"^[-•]?\s*[A-Z][A-Za-z]+(?:/[A-Z][A-Za-z]+)*\s*:", first):
        return "label setup"
    if re.search(r"\b(i'm|i am|i was|i can|i don't|i do not|my)\b", lower):
        return "first-person reaction"
    if re.search(r"\b(the|this|that|these|those)\b", lower[:20]):
        return "declarative observation"
    return "compact statement"


def _target_frame(text: str) -> str:
    lower = str(text or "").lower()
    if any(term in lower for term in ("roster", "front office", "gm", "draft", "trade", "free agency", "offseason")):
        return "roster/decision tension"
    if any(term in lower for term in ("coach", "payton", "malone", "adelman", "booth", "paton", "kroenke")):
        return "coach/front-office read"
    if any(term in lower for term in ("fans", "everyone", "timeline", "discourse", "arguing")):
        return "fan conversation tension"
    if any(term in lower for term in ("media", "reporter", "narrative", "press conference", "presser")):
        return "media/narrative read"
    if any(term in lower for term in ("game", "quarter", "period", "bench", "starter", "lineup")):
        return "game/usage read"
    return "general sports observation"


def _voice_features(text: str) -> dict[str, Any]:
    clean = str(text or "").strip()
    lower = clean.lower()
    tension_hits = [term for term in VOICE_TENSION_TERMS if re.search(rf"\b{re.escape(term)}\b", lower)]
    return {
        "opening_style": _opening_style(clean),
        "target_frame": _target_frame(clean),
        "ending": _ending_style(clean),
        "has_question": "?" in clean,
        "has_ellipsis": "..." in clean or "…" in clean,
        "first_person": bool(re.search(r"\b(i'm|i am|i was|i can|i don't|i do not|my)\b", lower)),
        "tension_terms": tension_hits[:5],
        "specificity_hits": len(topic_tags(clean)) + len(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?\b", clean)),
    }


def _avg(values: list[float]) -> float:
    return sum(values) / max(len(values), 1)


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _pct(values: list[bool]) -> int:
    if not values:
        return 0
    return round(sum(1 for value in values if value) / len(values) * 100)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _most_common(values: list[str]) -> str:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    if not counts:
        return ""
    return sorted(counts.items(), key=lambda item: (item[1], item[0]), reverse=True)[0][0]


def _char_band(values: list[int]) -> tuple[int, int]:
    if not values:
        return 0, 0
    ordered = sorted(values)
    if len(ordered) < 4:
        return min(ordered), max(ordered)
    lo_idx = max(0, round((len(ordered) - 1) * 0.25))
    hi_idx = min(len(ordered) - 1, round((len(ordered) - 1) * 0.75))
    return ordered[lo_idx], ordered[hi_idx]


def _topic_diversity(items: list[dict[str, Any]]) -> int:
    topics: set[str] = set()
    for item in items:
        cohort = item.get("cohort", {}) if isinstance(item, dict) else {}
        for topic in cohort.get("topics", []) or []:
            clean = str(topic or "").strip().lower()
            if clean:
                topics.add(clean)
    return len(topics)


def _topic_list(items: list[dict[str, Any]]) -> list[str]:
    topics: set[str] = set()
    for item in items:
        cohort = item.get("cohort", {}) if isinstance(item, dict) else {}
        for topic in cohort.get("topics", []) or []:
            clean = str(topic or "").strip().lower()
            if clean:
                topics.add(clean)
    return sorted(topics)


def _first_words(text: str, count: int = 3) -> str:
    clean = str(text or "").strip().lower()
    return " ".join(re.findall(r"[a-z0-9']+", clean)[:count])


def _dominant_first_words(items: list[dict[str, Any]], count: int = 3) -> tuple[str, int]:
    values = [_first_words(item.get("text", ""), count) for item in items]
    values = [value for value in values if value]
    if not values:
        return "", 0
    winner = _most_common(values)
    return winner, values.count(winner)


def _keep_existing_proposal_status(new_prop: dict[str, Any], existing: list[dict[str, Any]]) -> dict[str, Any]:
    for prop in existing:
        if prop.get("id") == new_prop["id"]:
            merged = dict(new_prop)
            merged["status"] = prop.get("status", new_prop["status"])
            merged["decided_at"] = prop.get("decided_at", "")
            merged["created_at"] = prop.get("created_at", new_prop["created_at"])
            return merged
    return new_prop


def _format_profile(fmt: str, items: list[dict[str, Any]], *, mature_only: bool) -> dict[str, Any]:
    ranked = sorted(items, key=lambda s: s["scores"]["creator_evolution"], reverse=True)
    edge_count = max(2 if len(ranked) >= 3 else 1, min(5, (len(ranked) + 3) // 4))
    winners = ranked[:edge_count]
    losers = ranked[-edge_count:] if len(ranked) > edge_count else []
    winner_features = [_format_features(item["text"]) for item in winners]
    loser_features = [_format_features(item["text"]) for item in losers]
    winner_chars = [int(f["char_count"]) for f in winner_features]
    loser_chars = [int(f["char_count"]) for f in loser_features]
    char_lo, char_hi = _char_band(winner_chars)
    sentence_median = round(_median([float(f["sentence_count"]) for f in winner_features]), 1)
    line_break_median = round(_median([float(f["line_breaks"]) for f in winner_features]), 1)
    ending = _most_common([str(f["ending"]) for f in winner_features])
    question_pct = _pct([bool(f["has_question"]) for f in winner_features])
    ellipsis_pct = _pct([bool(f["has_ellipsis"]) for f in winner_features])
    avg_score = round(_avg([float(i["scores"]["creator_evolution"]) for i in items]), 2)
    winner_avg_score = round(_avg([float(i["scores"]["creator_evolution"]) for i in winners]), 2)
    loser_avg_score = round(_avg([float(i["scores"]["creator_evolution"]) for i in losers]), 2)
    score_delta = round(winner_avg_score - loser_avg_score, 2)
    topic_diversity = _topic_diversity(items)
    winner_topic_diversity = _topic_diversity(winners)
    confidence_notes: list[str] = []
    if not mature_only:
        confidence_notes.append("provisional tweets only")
    if len(items) < 3:
        confidence_notes.append("needs at least 3 mature examples")
    if topic_diversity < 2 or winner_topic_diversity < 2:
        confidence_notes.append("needs winning evidence across at least 2 topic/team buckets")
    if score_delta < 0.35:
        confidence_notes.append("winner/loser score gap is too small")
    confidence_active = mature_only and len(items) >= 3 and topic_diversity >= 2 and winner_topic_diversity >= 2 and score_delta >= 0.35
    traits = [
        f"{char_lo}-{char_hi} chars among current {fmt} winners" if char_lo and char_hi else "",
        f"median {sentence_median:g} sentence(s)" if sentence_median else "",
        f"median {line_break_median:g} line break(s)" if line_break_median else "",
        f"most common ending: {ending}" if ending else "",
    ]
    if question_pct:
        traits.append(f"{question_pct}% of winners include a question mark")
    if ellipsis_pct:
        traits.append(f"{ellipsis_pct}% of winners include ellipsis")
    weak_traits = []
    if loser_chars:
        weak_traits.append(f"weak {fmt} examples average {round(_avg([float(v) for v in loser_chars]))} chars")
    if loser_chars:
        weak_traits.append(f"weak sample avg score {loser_avg_score}")
    return {
        "format": fmt,
        "status": "mature" if mature_only else "provisional",
        "sample_size": len(items),
        "avg_score": avg_score,
        "winner_avg_score": winner_avg_score,
        "loser_avg_score": loser_avg_score,
        "score_delta": score_delta,
        "topic_diversity": topic_diversity,
        "winner_topic_diversity": winner_topic_diversity,
        "winner_topics": _topic_list(winners),
        "confidence_active": confidence_active,
        "confidence_notes": confidence_notes,
        "learned_char_range": [char_lo, char_hi],
        "median_sentence_count": sentence_median,
        "median_line_breaks": line_break_median,
        "common_ending": ending,
        "question_pct": question_pct,
        "ellipsis_pct": ellipsis_pct,
        "traits": [trait for trait in traits if trait],
        "weak_traits": weak_traits,
        "winner_ids": [item["id"] for item in winners if item["id"]],
        "loser_ids": [item["id"] for item in losers if item["id"]],
        "examples": [],
    }


def build_format_profiles(scores: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    mature = [s for s in scores if s["cohort"]["lifecycle"] in ("mature", "archived")]
    pool = mature or scores
    mature_only = bool(mature)
    by_format: dict[str, list[dict[str, Any]]] = {}
    for score in pool:
        by_format.setdefault(score["cohort"]["format"], []).append(score)
    profiles = {
        fmt: _format_profile(fmt, items, mature_only=mature_only)
        for fmt, items in by_format.items()
        if items
    }
    return dict(sorted(profiles.items(), key=lambda item: (item[1]["avg_score"], item[1]["sample_size"]), reverse=True))


def build_voice_profile(scores: list[dict[str, Any]]) -> dict[str, Any]:
    mature = [s for s in scores if s["cohort"]["lifecycle"] in ("mature", "archived")]
    pool = mature or scores
    if not pool:
        return {
            "status": "empty",
            "sample_size": 0,
            "confidence_active": False,
            "confidence_notes": ["no scored tweets available"],
            "traits": [],
            "avoid_traits": [],
            "winner_ids": [],
            "loser_ids": [],
        }
    ranked = sorted(pool, key=lambda s: s["scores"]["creator_evolution"], reverse=True)
    edge_count = max(2 if len(ranked) >= 8 else 1, min(8, (len(ranked) + 3) // 4))
    winners = ranked[:edge_count]
    losers = ranked[-edge_count:] if len(ranked) > edge_count else []
    winner_features = [_voice_features(item["text"]) for item in winners]
    loser_features = [_voice_features(item["text"]) for item in losers]
    winner_tension_terms: list[str] = []
    loser_tension_terms: list[str] = []
    for feature in winner_features:
        winner_tension_terms.extend(feature.get("tension_terms", []))
    for feature in loser_features:
        loser_tension_terms.extend(feature.get("tension_terms", []))
    opening = _most_common([str(f["opening_style"]) for f in winner_features])
    target = _most_common([str(f["target_frame"]) for f in winner_features])
    ending = _most_common([str(f["ending"]) for f in winner_features])
    loser_opening = _most_common([str(f["opening_style"]) for f in loser_features])
    loser_target = _most_common([str(f["target_frame"]) for f in loser_features])
    question_pct = _pct([bool(f["has_question"]) for f in winner_features])
    ellipsis_pct = _pct([bool(f["has_ellipsis"]) for f in winner_features])
    first_person_pct = _pct([bool(f["first_person"]) for f in winner_features])
    specificity = round(_avg([float(f["specificity_hits"]) for f in winner_features]), 1)
    top_tension = []
    for term in sorted(set(winner_tension_terms), key=lambda t: (winner_tension_terms.count(t), t), reverse=True):
        if term not in top_tension:
            top_tension.append(term)
        if len(top_tension) >= 5:
            break
    traits = [
        f"open with {opening}" if opening else "",
        f"aim the take at {target}" if target else "",
        f"close with {ending} ending" if ending else "",
        f"{question_pct}% of winners use a question mark",
        f"{ellipsis_pct}% of winners use ellipsis",
        f"{first_person_pct}% of winners use first-person reaction",
        f"average specificity signal {specificity:g}",
    ]
    if top_tension:
        traits.append("recurring tension language: " + ", ".join(top_tension))
    avoid_traits = []
    if loser_opening:
        avoid_traits.append(f"weak posts often open with {loser_opening}")
    if loser_target:
        avoid_traits.append(f"weak posts often aim at {loser_target}")
    if loser_tension_terms:
        weak_terms = []
        for term in sorted(set(loser_tension_terms), key=lambda t: (loser_tension_terms.count(t), t), reverse=True):
            weak_terms.append(term)
            if len(weak_terms) >= 4:
                break
        avoid_traits.append("weak recurring language: " + ", ".join(weak_terms))
    winner_avg_score = round(_avg([float(i["scores"]["creator_evolution"]) for i in winners]), 2)
    loser_avg_score = round(_avg([float(i["scores"]["creator_evolution"]) for i in losers]), 2)
    score_delta = round(winner_avg_score - loser_avg_score, 2)
    topic_diversity = _topic_diversity(pool)
    winner_topic_diversity = _topic_diversity(winners)
    dominant_opening, dominant_opening_count = _dominant_first_words(winners)
    dominance_pct = round(dominant_opening_count / max(len(winners), 1) * 100)
    confidence_notes: list[str] = []
    if not mature:
        confidence_notes.append("provisional tweets only")
    if len(pool) < 8:
        confidence_notes.append("needs at least 8 mature examples")
    if topic_diversity < 2 or winner_topic_diversity < 2:
        confidence_notes.append("needs winning evidence across at least 2 topic/team buckets")
    if score_delta < 0.35:
        confidence_notes.append("winner/loser score gap is too small")
    if dominance_pct >= 70 and len(winners) >= 3:
        confidence_notes.append(f"winner openers over-repeat '{dominant_opening}'")
    confidence_active = bool(mature) and len(pool) >= 8 and topic_diversity >= 2 and winner_topic_diversity >= 2 and score_delta >= 0.35 and not (dominance_pct >= 70 and len(winners) >= 3)
    return {
        "status": "mature" if mature else "provisional",
        "sample_size": len(pool),
        "winner_avg_score": winner_avg_score,
        "loser_avg_score": loser_avg_score,
        "score_delta": score_delta,
        "topic_diversity": topic_diversity,
        "winner_topic_diversity": winner_topic_diversity,
        "winner_topics": _topic_list(winners),
        "dominant_winner_opening": dominant_opening,
        "dominant_winner_opening_pct": dominance_pct,
        "confidence_active": confidence_active,
        "confidence_notes": confidence_notes,
        "common_opening_style": opening,
        "common_target_frame": target,
        "common_ending": ending,
        "question_pct": question_pct,
        "ellipsis_pct": ellipsis_pct,
        "first_person_pct": first_person_pct,
        "avg_specificity_signal": specificity,
        "top_tension_terms": top_tension,
        "traits": [trait for trait in traits if trait],
        "avoid_traits": avoid_traits,
        "winner_ids": [item["id"] for item in winners if item["id"]],
        "loser_ids": [item["id"] for item in losers if item["id"]],
        "examples": [],
    }


def summarize_scores(scores: list[dict[str, Any]]) -> dict[str, Any]:
    mature = [s for s in scores if s["cohort"]["lifecycle"] in ("mature", "archived")]
    provisional = [s for s in scores if s["cohort"]["lifecycle"] == "provisional"]
    pool = mature or scores
    ranked = sorted(pool, key=lambda s: s["scores"]["creator_evolution"], reverse=True)
    winners = ranked[:5]
    losers = ranked[-5:] if len(ranked) >= 5 else ranked[-len(ranked):]
    false_winners = [s for s in ranked if s["flags"].get("false_winner")]
    false_losers = [s for s in ranked if s["flags"].get("false_loser")]

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
        "false_loser_ids": [s["id"] for s in false_losers[:5] if s["id"]],
        "format_summary": format_summary,
        "format_profiles": build_format_profiles(scores),
        "voice_profile": build_voice_profile(scores),
        "best_current_patterns": _pattern_lines(winners, positive=True),
        "worst_current_patterns": _pattern_lines(losers, positive=False),
    }


def _pattern_lines(items: list[dict[str, Any]], *, positive: bool) -> list[str]:
    lines = []
    for item in items[:5]:
        metrics = item["metrics"]
        cohort = item["cohort"]
        if positive:
            lines.append(
                f"{cohort['format']} | {metrics['views']:,} views | "
                f"{metrics['reply_per_1k']:.1f} replies/1k | "
                f"{metrics['repost_per_1k']:.1f} reposts/1k | topics: {', '.join(cohort.get('topics', [])[:3])}"
            )
        else:
            lines.append(
                f"{cohort['format']} | low score {item['scores']['creator_evolution']:.1f} | "
                f"{metrics['views']:,} views | topics: {', '.join(cohort.get('topics', [])[:3])}"
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
    format_profiles = summary.get("format_profiles", {}) or {}
    if formats:
        best = formats[0]
        best_profile = format_profiles.get(best.get("format", "")) if isinstance(format_profiles, dict) else None
        if isinstance(best_profile, dict) and best_profile.get("confidence_active") is True:
            evidence = summary.get("winner_ids", [])[:4]
            rule = f"Start Creator Evolution drafts in {best['format']} unless the user's requested format says otherwise."
            proposals.append({
                "id": _proposal_id(rule, evidence),
                "status": "pending",
                "created_at": iso_now(now),
                "rule": rule,
                "reason": f"{best['format']} is currently the strongest mature cohort by normalized score with confident/diverse evidence.",
                "evidence_tweet_ids": evidence,
                "sample_size": best["count"],
                "before_after": {
                    "before": "Default to old Creator Studio structure regardless of current performance.",
                    "after": f"Open with {best['format']} pacing when no explicit format is chosen.",
                },
            })

    for fmt, profile in format_profiles.items():
        sample_size = int(profile.get("sample_size", 0) or 0)
        if sample_size < 3:
            continue
        if profile.get("confidence_active") is not True:
            continue
        char_range = profile.get("learned_char_range", [0, 0])
        try:
            char_lo, char_hi = int(char_range[0] or 0), int(char_range[1] or 0)
        except Exception:
            char_lo, char_hi = 0, 0
        traits = [str(t) for t in profile.get("traits", []) if str(t).strip()]
        if not traits:
            continue
        evidence = list(profile.get("winner_ids", []) or [])[:4]
        learned_summary = "; ".join(traits[:4])
        rule = f"For {fmt}, follow the learned winning format profile: {learned_summary}."
        proposals.append({
            "id": _proposal_id(rule, evidence),
            "status": "pending",
            "created_at": iso_now(now),
            "rule": rule,
            "reason": (
                f"{fmt} has {sample_size} {'mature' if profile.get('status') == 'mature' else 'tracked'} "
                f"examples; current winner avg score {profile.get('winner_avg_score', 0)}."
            ),
            "evidence_tweet_ids": evidence,
            "sample_size": sample_size,
            "before_after": {
                "before": f"Use the static {fmt} format guardrail.",
                "after": (
                    f"Use {fmt} with {char_lo}-{char_hi} chars, "
                    f"median {profile.get('median_sentence_count', 0)} sentence(s), "
                    f"median {profile.get('median_line_breaks', 0)} line break(s), "
                    f"and {profile.get('common_ending', 'the learned')} ending."
                ),
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

    false_loser_ids = summary.get("false_loser_ids", [])
    if false_loser_ids:
        rule = "Do not punish low-reach posts that earn strong reply rates; test timing and topic before killing the format."
        proposals.append({
            "id": _proposal_id(rule, false_loser_ids),
            "status": "pending",
            "created_at": iso_now(now),
            "rule": rule,
            "reason": "Some posts can be strong conversation starters even when the first reach cohort is small.",
            "evidence_tweet_ids": false_loser_ids[:4],
            "sample_size": len(false_loser_ids),
            "before_after": {
                "before": "Treat every low-impression post as a bad writing pattern.",
                "after": "Separate weak distribution from strong audience reaction before changing the voice.",
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

    voice_profile = summary.get("voice_profile", {}) or {}
    voice_traits = [str(t) for t in voice_profile.get("traits", []) if str(t).strip()]
    if int(voice_profile.get("sample_size", 0) or 0) >= 8 and voice_traits and voice_profile.get("confidence_active") is True:
        evidence = list(voice_profile.get("winner_ids", []) or [])[:4]
        learned_summary = "; ".join(voice_traits[:4])
        rule = f"For Creator Evolution voice, follow the learned winning voice profile: {learned_summary}."
        proposals.append({
            "id": _proposal_id(rule, evidence),
            "status": "pending",
            "created_at": iso_now(now),
            "rule": rule,
            "reason": (
                f"Voice profile has {voice_profile.get('sample_size', 0)} "
                f"{voice_profile.get('status', 'tracked')} examples; winner avg score "
                f"{voice_profile.get('winner_avg_score', 0)}."
            ),
            "evidence_tweet_ids": evidence,
            "sample_size": int(voice_profile.get("sample_size", 0) or 0),
            "before_after": {
                "before": "Use only static lane instructions for voice.",
                "after": learned_summary,
            },
        })

    return [_keep_existing_proposal_status(prop, existing) for prop in proposals]


def initial_state() -> dict[str, Any]:
    return {
        "version": 1,
        "prompt_version": PROMPT_VERSION,
        "scoring_version": SCORING_VERSION,
        "rule_version": RULE_VERSION,
        "tweets": [],
        "tracked_tweets": [],
        "snapshots": [],
        "scores": [],
        "patterns": summarize_scores([]),
        "proposals": [],
        "approved_rules": [],
        "rule_versions": [],
        "generated_lineage": [],
        "budget_policy": dict(BUDGET_POLICY),
        "sync_status": {
            "status": "never_synced",
            "last_sync_at": "",
            "last_failed_sync_at": "",
            "handle": "",
            "original_tweet_count": 0,
            "mature_tweet_count": 0,
            "estimated_spend_usd": 0.0,
            "persisted": "unknown",
            "last_persisted_at": "",
            "persist_error": "",
            "partial_ingestion": False,
            "stale_snapshot_count": 0,
        },
        "api_usage": {
            "provider": "twitterapi.io",
            "estimated_tweets_read": 0,
            "estimated_requests": 0,
            "estimated_cost_usd": 0.0,
            "ledger": [],
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


def tweet_url(tweet: dict[str, Any]) -> str:
    direct = str(tweet.get("url") or tweet.get("twitterUrl") or "").strip()
    if direct:
        return direct
    author = str(tweet.get("author") or tweet.get("userName") or tweet.get("username") or tweet.get("screen_name") or "").strip()
    tid = str(tweet.get("id") or tweet.get("tweet_id") or "").strip()
    if author and tid:
        return f"https://x.com/{author.lstrip('@')}/status/{tid}"
    return ""


def build_tracked_tweet(tweet: dict[str, Any], *, source: str = "manual_or_imported",
                        now: datetime | None = None) -> dict[str, Any]:
    text = tweet_text(tweet)
    created = parse_datetime(tweet.get("createdAt") or tweet.get("created_at"))
    hours = age_hours(tweet, now)
    lower = text.lower()
    return {
        "id": str(tweet.get("id") or tweet.get("tweet_id") or ""),
        "text": text,
        "url": tweet_url(tweet),
        "source": str(tweet.get("source") or source),
        "posted_at": created.isoformat(timespec="seconds") if created else "",
        "format": classify_format(text),
        "lane": str(tweet.get("lane") or tweet.get("voice_lane") or ""),
        "topic": topic_tags(text),
        "has_media": bool(tweet.get("media") or tweet.get("photos") or tweet.get("videos")),
        "has_link": "http" in lower,
        "is_reply": text.startswith("@") or bool(tweet.get("inReplyToId") or tweet.get("in_reply_to_status_id")),
        "is_quote": bool(tweet.get("quotedTweet") or tweet.get("quoted_status") or tweet.get("isQuote")),
        "is_thread": bool(tweet.get("thread_id") or tweet.get("conversationId")),
        "metrics": {
            "views": metric(tweet, "viewCount", "view_count", "views"),
            "likes": metric(tweet, "likeCount", "like_count", "likes"),
            "reposts": metric(tweet, "retweetCount", "retweet_count", "retweets", "rts"),
            "replies": metric(tweet, "replyCount", "reply_count", "replies"),
            "quotes": metric(tweet, "quoteCount", "quote_count", "quotes"),
            "bookmarks": metric(tweet, "bookmarkCount", "bookmark_count", "bookmarks"),
        },
        "lifecycle": lifecycle_for_age(hours),
        "scoring_version": SCORING_VERSION,
        "prompt_version": PROMPT_VERSION,
        "rule_version": RULE_VERSION,
    }


def _latest_snapshot_by_tweet(snapshots: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for snap in snapshots:
        tid = str(snap.get("tweet_id") or "")
        if tid:
            latest[tid] = snap
    return latest


def metric_delta(previous: dict[str, Any] | None, current: dict[str, int]) -> dict[str, int]:
    previous_metrics = (previous or {}).get("metrics", {}) or {}
    delta = {}
    for key, value in current.items():
        try:
            delta[key] = int(value or 0) - int(previous_metrics.get(key, 0) or 0)
        except (TypeError, ValueError):
            delta[key] = 0
    return delta


def refresh_state(existing: dict[str, Any] | None, tweets: list[dict[str, Any]], *,
                  handle: str = "", now: datetime | None = None) -> dict[str, Any]:
    state = dict(initial_state())
    if isinstance(existing, dict):
        state.update(existing)
    current_time = iso_now(now)
    original_raw = [t for t in tweets if isinstance(t, dict) and is_original_post(t)]
    originals = [slim_tweet(t) for t in original_raw]
    tracked_tweets = [build_tracked_tweet(t, now=now) for t in original_raw]
    scores = [score_tweet(t, now) for t in originals]
    snapshots = list(state.get("snapshots", []))
    previous_by_tweet = _latest_snapshot_by_tweet(snapshots)
    for tweet in originals:
        metrics = {
            "views": tweet["viewCount"],
            "likes": tweet["likeCount"],
            "reposts": tweet["retweetCount"],
            "replies": tweet["replyCount"],
            "quotes": tweet["quoteCount"],
            "bookmarks": tweet["bookmarkCount"],
        }
        snapshots.append({
            "tweet_id": tweet["id"],
            "captured_at": current_time,
            "metrics": metrics,
            "metric_delta": metric_delta(previous_by_tweet.get(tweet["id"]), metrics),
            "scoring_version": SCORING_VERSION,
        })
    snapshots = snapshots[-2000:]
    patterns = summarize_scores(scores)
    api_reads = len(originals)
    estimated_cost = round(api_reads / 1000.0 * API_ESTIMATED_COST_PER_1000_TWEETS, 4)
    prev_status = dict(state.get("sync_status", {}) or {})
    state.update({
        "version": 1,
        "prompt_version": PROMPT_VERSION,
        "scoring_version": SCORING_VERSION,
        "rule_version": RULE_VERSION,
        "tweets": originals[:500],
        "tracked_tweets": tracked_tweets[:500],
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
            "persisted": prev_status.get("persisted", "unknown"),
            "last_persisted_at": prev_status.get("last_persisted_at", ""),
            "persist_error": prev_status.get("persist_error", ""),
        },
        "api_usage": {
            "provider": "twitterapi.io",
            "estimated_tweets_read": api_reads,
            "estimated_requests": int(prev_status.get("estimated_requests", 0) or 0),
            "estimated_cost_usd": estimated_cost,
            "ledger": list((state.get("api_usage", {}) or {}).get("ledger", []))[-200:],
        },
    })
    state["approved_rules"] = list(state.get("approved_rules", []))
    state["rule_versions"] = list(state.get("rule_versions", []))
    state["budget_policy"] = dict(state.get("budget_policy", BUDGET_POLICY) or BUDGET_POLICY)
    return state


def approve_proposal(state: dict[str, Any], proposal_id: str, now: datetime | None = None) -> dict[str, Any]:
    state = dict(state or initial_state())
    approved = list(state.get("approved_rules", []))
    rule_versions = list(state.get("rule_versions", []))
    proposals = []
    for proposal in state.get("proposals", []):
        proposal = dict(proposal)
        if proposal.get("id") == proposal_id:
            proposal["status"] = "approved"
            proposal["decided_at"] = iso_now(now)
            revision = len([r for r in rule_versions if r.get("status") == "active"]) + 1
            if not any(rule.get("proposal_id") == proposal_id for rule in approved):
                approved_rule = {
                    "proposal_id": proposal_id,
                    "rule": proposal.get("rule", ""),
                    "approved_at": proposal["decided_at"],
                    "evidence_tweet_ids": proposal.get("evidence_tweet_ids", []),
                    "rule_version": RULE_VERSION,
                    "revision": revision,
                    "status": "active",
                }
                approved.append(approved_rule)
                rule_versions.append({
                    **approved_rule,
                    "reason": proposal.get("reason", ""),
                    "sample_size": proposal.get("sample_size", 0),
                    "before_after": proposal.get("before_after", {}),
                    "evidence_snapshot": proposal.get("evidence_tweet_ids", []),
                })
        proposals.append(proposal)
    state["proposals"] = proposals
    state["approved_rules"] = approved
    state["rule_versions"] = rule_versions
    return state


def rollback_rule(state: dict[str, Any], proposal_id: str, now: datetime | None = None) -> dict[str, Any]:
    state = dict(state or initial_state())
    decided_at = iso_now(now)
    approved = []
    for rule in state.get("approved_rules", []):
        rule = dict(rule)
        if rule.get("proposal_id") == proposal_id:
            rule["status"] = "rolled_back"
            rule["rolled_back_at"] = decided_at
        else:
            approved.append(rule)
    versions = []
    for version in state.get("rule_versions", []):
        version = dict(version)
        if version.get("proposal_id") == proposal_id and version.get("status") == "active":
            version["status"] = "rolled_back"
            version["rolled_back_at"] = decided_at
        versions.append(version)
    state["approved_rules"] = approved
    state["rule_versions"] = versions
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


def format_learning_text(state: dict[str, Any] | None, fmt: str) -> str:
    patterns = (state or {}).get("patterns", {}) if isinstance(state, dict) else {}
    profiles = patterns.get("format_profiles", {}) if isinstance(patterns, dict) else {}
    profile = profiles.get(fmt) if isinstance(profiles, dict) else None
    if not isinstance(profile, dict):
        return ""
    if str(profile.get("status", "")).lower() != "mature":
        return ""
    if _safe_int(profile.get("sample_size", 0)) < 3:
        return ""
    if profile.get("confidence_active") is not True:
        return ""
    traits = [str(t) for t in profile.get("traits", []) if str(t).strip()]
    weak_traits = [str(t) for t in profile.get("weak_traits", []) if str(t).strip()]
    lines = [
        f"{fmt} learned profile ({profile.get('status', 'tracked')} sample, n={profile.get('sample_size', 0)}):",
        "- Calibration is abstract only; raw winner text is intentionally withheld from generation prompts to prevent copying.",
    ]
    lines.extend(f"- Winning trait: {trait}" for trait in traits[:5])
    lines.extend(f"- Avoid: {trait}" for trait in weak_traits[:3])
    return "\n".join(lines)


def voice_learning_text(state: dict[str, Any] | None) -> str:
    patterns = (state or {}).get("patterns", {}) if isinstance(state, dict) else {}
    profile = patterns.get("voice_profile") if isinstance(patterns, dict) else None
    if not isinstance(profile, dict) or not _safe_int(profile.get("sample_size", 0)):
        return ""
    if str(profile.get("status", "")).lower() != "mature":
        return ""
    if _safe_int(profile.get("sample_size", 0)) < 8:
        return ""
    if profile.get("confidence_active") is not True:
        return ""
    traits = [str(t) for t in profile.get("traits", []) if str(t).strip()]
    avoid_traits = [str(t) for t in profile.get("avoid_traits", []) if str(t).strip()]
    lines = [
        f"Creator Evolution learned voice profile ({profile.get('status', 'tracked')} sample, n={profile.get('sample_size', 0)}):",
        "- Use this as influence, not a hook library. Raw winner text is intentionally withheld from generation prompts.",
    ]
    lines.extend(f"- Winning voice trait: {trait}" for trait in traits[:7])
    lines.extend(f"- Avoid voice drift: {trait}" for trait in avoid_traits[:3])
    return "\n".join(lines)


def performance_context(state: dict[str, Any] | None) -> str:
    state = state or initial_state()
    patterns = state.get("patterns", {})
    mature_count = _safe_int(patterns.get("mature_count", 0)) if isinstance(patterns, dict) else 0
    rules = approved_rules_text(state)
    blocks = []
    if mature_count >= 3:
        blocks.append(
            "CURRENT PERFORMANCE SUMMARY:\n"
            f"- Mature original posts analyzed: {mature_count}\n"
            "- Raw winning and losing tweet text is withheld from generation prompts to prevent copying."
        )
    if rules:
        blocks.append("APPROVED CREATOR EVOLUTION RULES:\n" + rules)
    return "\n\n".join(blocks)


def build_generation_prompt(seed: str, fmt: str, lane: str, state: dict[str, Any] | None,
                            *, action: str = "evolve",
                            live_stats_block: str = "", sports_ctx: str = "") -> str:
    fmt = fmt if fmt in FORMAT_RECIPES else "Normal Tweet"
    lane = normalize_lane(lane)
    context = performance_context(state)
    lane_behavior = lane_recipe_text(lane)
    format_behavior = format_recipe_text(fmt)
    format_learning = format_learning_text(state, fmt)
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
    comedic_contract = (
        "\nCOMEDIC LANE HARD RULES:\n"
        "- These Comedic rules override the generic response-pressure, consequence-line, and debate-bait rules below.\n"
        "- Comedic means funny first. Sharp, surprising, sports-specific, and fearless, but not angry cosplay.\n"
        "- The joke must come from the exact sports absurdity in the source: injury trust, QB room behavior, rotation math, non-Jokic minutes, fan coping, coach logic, roster incentives, public messaging, or media framing.\n"
        "- Use one visible joke mechanic per option: option 1 literalize the team spin, option 2 roast the fan coping, option 3 flip the sports logic into a blunt punchline.\n"
        "- Profanity is optional seasoning, never the joke. If removing the swear word kills the line, rewrite it.\n"
        "- Edge means sharper comic timing and more specific absurdity, not yelling louder.\n"
        "- No random analogies unless they are tightly sports-adjacent. No office, dating, haunted house, fire, basement, drunk friend, passenger seat, air freshener, side piece, or Tinder crutches.\n"
        "- Do not attack private life, protected traits, or a person as a person. Roast the decision, pattern, excuse, rotation, roster math, public messaging, fan coping, or media framing.\n"
        "- Do not invent crowd counts, percentages, records, timelines, injuries, workouts, trades, or exact minutes. If the source says 'minutes,' do not turn that into 'five minutes' or any exact duration.\n"
        "- The final beat is the punchline, not a lesson, summary, threat, accusation, or rage closer.\n"
        "- Reject anything that sounds like Witty Edge analysis with one joke word added. The reader should know why it is funny without needing the joke explained.\n"
        "- Ban anger-only closers: 'coward shit,' 'bullshit,' 'goddamn disaster,' 'they lied,' 'got exposed,' 'nobody buys it,' 'same scared shit,' 'zero mercy,' 'eviscerate,' and 'On track my ass.'\n"
        "- Positive shape examples: 'The next QB move is the part with subtitles. If another arm shows up, that ankle just held its own press conference.' / 'The Broncos telling everyone the ankle is fine while building the QB room like the ankle has its own burner account.' / 'The non-Jokic minutes are not a rotation problem anymore. They are a recurring guest star.' / 'The Nuggets bench discourse always starts with new names and ends with Jokic returning like tech support.'\n"
    ) if lane == "Comedic" else ""
    comedic_voice_contract = (
        "\nCOMEDIC OVERRIDE:\n"
        "- Because the selected lane is Comedic, ignore any generic instruction below that asks for response pressure, debate bait, consequence framing, or a dramatic analytical ending.\n"
        "- The final beat must be the joke. If the last sentence sounds like a lesson, summary, roster diagnosis, or open-loop analysis, rewrite it.\n"
        "- The final beat must make sense on first read. If a normal sports fan would ask 'what does that even mean,' rewrite it.\n"
        "- Prefer 1-2 compact sentences for Punchy and 2-3 compact sentences for Normal. Cut any sentence that explains the joke after it lands.\n"
    ) if lane == "Comedic" else ""
    return f"""{opening}

{source_label}:
\"{seed}\"

FORMAT:
{fmt}

FORMAT BEHAVIOR:
{format_behavior}

LEARNED FORMAT PROFILE:
{format_learning or "- No mature learned profile for this selected format yet. Use the static format behavior until enough real posts mature."}
Mature metric-derived profiles are allowed input alongside approved rules as calibration only. When a confident learned format profile exists, use it to tune pacing inside the selected format while the static guardrails and hard validator bounds still apply.

PERSONALITY LANE:
{lane}

LANE BEHAVIOR:
{lane_behavior}

LEARNED VOICE PROFILE:
{voice_learning_text(state) or "- No mature learned voice profile yet. Use the selected lane behavior and approved rules."}

{context}
{live_stats_block}
{sports_ctx}
{build_rule}
{comedic_contract}

CREATOR EVOLUTION VOICE CONTRACT:
- The selected format is mandatory. Length, structure, separators, and article/thread behavior must visibly change when the format changes.
- Every format has flexibility inside its shape. Pick the structure, opening, and ending that fit the idea instead of forcing the same formula every time.
- Across the 3 options, vary the visible structure when the selected format allows it. For Normal Tweet, do not make all 3 options use the same line-break skeleton: use a mix such as one clean paragraph, one two-block final-line version, and one compact stepped version only if it sounds natural.
- Use approved rules plus mature metric-derived profiles; ignore provisional or maturing profile data for generation.
- If the selected format is Normal Tweet, prefer two or three natural sentences, then one line break, then one final statement that invites engagement without a direct question. Vary the ending type and allow a strong one-paragraph version when it sounds more natural.
- The final line must create response pressure. Use a dramatic ending, an alluded question without a question mark, a declarative argument statement, a consequence line, or quote-tweet bait.
- Ellipsis is a strong Tyler ending, but it must not be the only ending. Mix ellipsis with hard-period tension lines, contrast lines, prediction lines, and understated walk-offs.
- If the selected lane is Promo, treat supplied YouTube/video links as attached distribution context, not prose. Do not include a naked URL unless explicitly requested.
- Default personality is witty edge: funny, pointed, sometimes annoyed, sometimes fired-up, but still human and monetization-safe.
- If the selected lane is Comedic, default personality becomes joke-first sports comedy, not Witty Edge.
- Sound like a real person posting from their phone, not a content strategy assistant.
- Use specific human reactions, tension, contradiction, and unfinished thoughts.
- Prefer declarative open loops over literal question bait.
- No hashtags, no links unless the user supplied them.
- No invented stats, rankings, injuries, roster facts, or current-event claims.
- No corporate polish, LinkedIn cadence, fake balance, symmetrical three-part essay structure, or over-explaining.
- No polished punctuation in tweet copy. Never use hyphens, dashes, semicolons, colons, parentheses, or bracket-style punctuation. Use plain commas, periods, ellipses, and natural sentence breaks so it sounds like Tyler.
- Never use these phrases: {", ".join(ANTI_AI_BANNED_PHRASES)}.
- Never use Hall of Fame tweets, Hall of Fame examples, Hall of Fame hooks, or static HOF benchmark language.

QUALITY GATE:
- Reject any draft that does not obey the selected FORMAT BEHAVIOR above.
- Reject any draft that sounds like content strategy instead of something posted from a phone.
- Reject any draft that uses polished punctuation Tyler would not naturally type, especially hyphens, dashes, semicolons, colons, parentheses, or brackets.
- Reject generic engagement bait endings like "thoughts?" or "what do you think?"
- Heated lanes can attack a decision, excuse, pattern, or media narrative; they cannot harass a person.
- If the lane is Deadpan, underplay it. No exclamation points, no winking, no explanation.
- If the lane is Comedic, reject any draft that is mainly Witty Edge analysis with a cute ending. It needs a visible joke mechanic and a real punchline.

HIDDEN SELF-CHECK BEFORE FINAL JSON:
Would this sound normal if posted directly from a phone by a funny, witty, sports-obsessed human? If not, rewrite it before returning.
{comedic_voice_contract}

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
