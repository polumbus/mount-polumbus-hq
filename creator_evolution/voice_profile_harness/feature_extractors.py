"""Deterministic voice and format feature extraction."""

from __future__ import annotations

import re
from collections import Counter

from .schemas import BANNED_AI_PATTERNS


TURN_WORDS = ("but", "except", "until", "somehow", "because", "which", "meanwhile")
SARCASTIC_MARKERS = ("sure", "totally", "normal", "great", "love that", "obviously", "very normal")
ANGER_MARKERS = ("ridiculous", "disaster", "insane", "awful", "terrible", "unacceptable", "stupid")
HYPE_MARKERS = ("let's go", "huge", "massive", "perfect", "elite", "special")
DEADPAN_MARKERS = ("very normal", "naturally", "apparently", "as one does")


def words(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9']+", str(text or ""))


def sentences(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"(?<=[.!?])\s+|\n+", str(text or "")) if p.strip()]
    return parts or ([str(text).strip()] if str(text).strip() else [])


def banned_ai_flags(text: str) -> list[str]:
    low = str(text or "").lower()
    flags = []
    for pattern in BANNED_AI_PATTERNS:
        if pattern.lower() in low:
            flags.append(pattern)
    if re.search(r"\b(first|second|third),\b", low):
        flags.append("numbered essay cadence")
    if low.count("?") and any(phrase in low for phrase in ("thoughts", "agree", "what do you think")):
        flags.append("fake engagement question")
    return flags


def emotion_lane(text: str) -> str:
    low = str(text or "").lower()
    if any(item in low for item in DEADPAN_MARKERS):
        return "Deadpan"
    if any(item in low for item in SARCASTIC_MARKERS):
        return "Sarcastic"
    if any(item in low for item in ANGER_MARKERS):
        return "Annoyed"
    if any(item in low for item in HYPE_MARKERS):
        return "Celebratory"
    if "?" in low:
        return "Skeptical"
    return "Witty Edge"


def joke_mechanic(text: str) -> str:
    low = str(text or "").lower()
    if any(marker in low for marker in SARCASTIC_MARKERS):
        return "fake enthusiasm or deadpan contrast"
    if any(word in low for word in ("somehow", "naturally", "of course")):
        return "sports absurdity stated plainly"
    if "but" in low or "except" in low:
        return "claim versus contradiction"
    if re.search(r"\b(one|two|three|first|last)\b", low):
        return "specific contrast"
    return "observation with turn"


def tension_mechanic(text: str) -> str:
    low = str(text or "").lower()
    if "?" in low:
        return "implicit challenge"
    if any(word in low for word in ("but", "except", "until")):
        return "contradiction"
    if low.endswith("..."):
        return "unfinished thought"
    if any(word in low for word in ("because", "means", "tells")):
        return "consequence"
    return "declarative pressure"


def ending_type(text: str) -> str:
    stripped = str(text or "").strip()
    if stripped.endswith("?"):
        return "question"
    if stripped.endswith("..."):
        return "ellipsis open loop"
    last = sentences(stripped)[-1] if sentences(stripped) else stripped
    if len(words(last)) <= 8:
        return "short punchline"
    if any(word in last.lower() for word in ("because", "means", "tells", "why")):
        return "consequence line"
    return "hard-period walkoff"


def recurring_phrase_candidates(text: str) -> list[str]:
    tokens = [w.lower() for w in words(text)]
    phrases = []
    for n in (2, 3):
        for i in range(0, max(0, len(tokens) - n + 1)):
            phrase = " ".join(tokens[i:i + n])
            if phrase not in {"this is", "that is", "it is", "the game", "the team"}:
                phrases.append(phrase)
    return [phrase for phrase, _ in Counter(phrases).most_common(5)]


def extract_voice_features(tweet: dict) -> dict:
    text = str(tweet.get("text_clean") or "")
    sent = sentences(text)
    token_count = len(words(text))
    avg_sentence = round(token_count / max(1, len(sent)), 2)
    line_count = max(1, str(tweet.get("text_raw") or text).count("\n") + 1)
    caps_words = re.findall(r"\b[A-Z]{3,}\b", text)
    flags = banned_ai_flags(text)
    edge = 1
    low = text.lower()
    if any(item in low for item in ANGER_MARKERS):
        edge += 2
    if any(item in low for item in SARCASTIC_MARKERS):
        edge += 1
    score = 78 - (len(flags) * 12)
    if avg_sentence <= 18:
        score += 7
    if ending_type(text) in {"short punchline", "ellipsis open loop", "hard-period walkoff"}:
        score += 6
    return {
        "tweet_id": tweet.get("tweet_id", ""),
        "sentence_count": len(sent),
        "avg_sentence_length_words": avg_sentence,
        "line_count": line_count,
        "uses_fragments": any(len(words(part)) <= 4 for part in sent),
        "uses_short_punchline": ending_type(text) == "short punchline",
        "uses_caps_emphasis": bool(caps_words),
        "question_count": text.count("?"),
        "exclamation_count": text.count("!"),
        "ellipsis_count": text.count("..."),
        "first_person_level": min(3, sum(1 for w in words(text.lower()) if w in {"i", "me", "my", "we", "us", "our"})),
        "direct_address_level": min(3, sum(1 for w in words(text.lower()) if w in {"you", "your", "yall"})),
        "emotion_lane": emotion_lane(text),
        "edge_level": min(5, edge),
        "sarcasm_markers": [m for m in SARCASTIC_MARKERS if m in low],
        "joke_mechanic": joke_mechanic(text),
        "tension_mechanic": tension_mechanic(text),
        "ending_type": ending_type(text),
        "recurring_phrases": recurring_phrase_candidates(text),
        "banned_ai_risk_flags": flags,
        "tylerness_score_initial": max(0, min(100, score)),
    }


def extract_format_features(tweet: dict) -> dict:
    text = str(tweet.get("text_clean") or "")
    token_count = len(words(text))
    char_count = len(text)
    if "\n" in str(tweet.get("text_raw") or "") and char_count > 280:
        fmt = "Thread"
    elif char_count <= 160:
        fmt = "Punchy Tweet"
    elif char_count <= 280:
        fmt = "Normal Tweet"
    elif char_count <= 900:
        fmt = "Long Tweet"
    else:
        fmt = "Article"
    low = text.lower()
    has_named = bool(tweet.get("team_labels") or re.search(r"\b[A-Z][a-z]+(?:\s[A-Z][a-z]+)?\b", text))
    hook = "question" if text.strip().endswith("?") else "declarative"
    if any(low.startswith(prefix) for prefix in ("if ", "when ", "the thing", "somebody")):
        hook = "conditional setup"
    ai_risk = "high" if banned_ai_flags(text) else ("medium" if token_count > 70 and text.count(",") >= 4 else "low")
    return {
        "tweet_id": tweet.get("tweet_id", ""),
        "format_type": fmt,
        "hook_type": hook,
        "has_setup": any(word in low for word in ("if ", "when ", "because", "before")),
        "has_turn": any(word in low for word in TURN_WORDS),
        "has_punchline": ending_type(text) in {"short punchline", "ellipsis open loop"},
        "has_specific_claim": has_named or bool(re.search(r"\d", text)),
        "has_named_entities": has_named,
        "has_stats": bool(re.search(r"\b\d+([.-]\d+)?%?\b", text)),
        "has_media_context": bool(tweet.get("has_media")),
        "reply_bait_type": "fake question" if "?" in text and any(x in low for x in ("thoughts", "agree")) else "none",
        "structure_ai_risk": ai_risk,
    }
