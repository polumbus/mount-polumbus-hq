"""Creator Evolution Pulse opportunity scoring.

Pulse is the "what should I post right now?" decision layer. It does not
generate tweets and it never posts. It normalizes live signals, clusters them
into moments, scores the opportunity, and returns either one recommended brief
or a no-op decision.
"""

from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import math
import re
from typing import Any

import creator_evolution_algorithm as cexa

import creator_evolution as ce


PULSE_VERSION = "ce-pulse-v10-public-x-opportunity"
DEFAULT_THRESHOLD = 68.0
SAVE_THRESHOLD = 58.0
BLOCKING_HARD_BLOCKS = {
    "stale_source",
    "low_fact_confidence",
    "monetization_risk",
    "betting_angle",
    "non_english_source",
    "out_of_market_context",
    "non_sports_avs_context",
    "promo_source",
    "commerce_source",
    "duplicate_recent_angle",
    "reply_fragment_context",
    "unresolved_pronoun_context",
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
    "denver", "den", "bo nix", "jokic", "murray", "mackinnon", "makar",
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
    "press conference", "press conferences", "presser", "media availability",
    "availability", "exit interview", "exit interviews", "end of season",
    "end-of-season",
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
    "denver", "den", "avalanche", "colorado avalanche", "avs", "rockies", "colorado rockies",
    "buffs", "cu buffs", "colorado buffaloes", "coach prime", "deion",
    "nikola jokic", "jokic", "jamal murray", "aaron gordon",
    "michael porter", "christian braun", "michael malone", "calvin booth",
    "nathan mackinnon", "mackinnon", "cale makar", "makar",
    "bo nix", "sean payton", "courtland sutton",
)
UNSAFE_MONETIZATION_TERMS = (
    "slur", "kill", "die", "crime", "arrested", "lawsuit", "gambling lock",
    "guaranteed bet", "free money", "medical", "diagnosis",
)
BETTING_SIGNAL_TERMS = (
    "betting lines", "moneyline", "money line", "spread:", "spread ",
    "over/under", "over under", "parlay", "odds", "sportsbook",
    "draftkings", "fanduel", "bet365", "betrivers", "prop", "props",
    "gambling", "bet slip", "best bet", "player prop",
)
CRYPTO_AVALANCHE_TERMS = (
    "$avax", "avax", "altcoin", "crypto", "token", "coin", "smart money",
    "trade alerts", "trading alert", "blockchain", "defi",
)
AVALANCHE_SPORTS_TERMS = (
    "colorado avalanche", "goavsgo", "nhl", "hockey", "puck", "goalie",
    "rink", "period", "wild", "stars", "jets", "macKinnon", "mackinnon",
    "makar", "landeskog",
)
NON_SPORTS_AVS_TERMS = (
    "avs encode", "avs encoding", "av sync", "audio video", "physicalmedia",
    "physical media", "cbhd", "hddvd", "blu-ray", "bluray", "warnerbros",
    "disc", "dvd", "4k transfer", "image is nice and sharp", "black levels",
)
PROMO_SOURCE_TERMS = (
    " is live!", " is live -", "watch live", "join us live", "subscribe",
    "podcast is live", "show is live", "stream is live", "presented by",
    "favorite memories", "top 5 favorite", "drafting things that are overrated",
    "things that are overrated", "coming up on", "live now:",
)
COMMERCE_SOURCE_TERMS = (
    "for dogs & cats", "for dogs and cats", "jersey for dogs", "pet jersey",
    "buy now", "shop now", "on sale", "sale ends", "use code", "promo code",
    "free shipping", "merch", "merchandise", "store link",
)
SPECULATIVE_REACTION_TERMS = (
    "safe to say", "hopefully", "smells like", "feels like", "i think",
    "i guess", "probably", "might be gone", "is gone", "are gone",
    "word salad", "bullshit", "pathetic", "nothing of value",
)
SUBSTANTIVE_SOURCE_TERMS = (
    "says", "said", "quote", "quotes", "comments", "availability",
    "press conference", "presser", "news conference", "exit interview",
    "exit interviews", "end of season", "end-of-season", "offseason",
    "front office", "ownership", "staff", "kroenke", "booth", "malone",
    "jokic", "murray", "renck", "haertl", "dnvr", "altitude",
)
FALLBACK_RISK_TERMS = (
    "idiot", "moron", "clown", "trash", "garbage", "hate", "stupid",
    "fraud", "loser", "shut up", "dumb",
)
NON_ENGLISH_MARKERS = (
    " je ", " pense ", " cet ", " été", " toutes ", " exception ", " propos ",
    " déform", " parce que ", " l'été", " le ", " la ", " les ", " des ",
    " une ", " dans ", " avec ", " pour ", " mais ", " cela ",
)
NON_ENGLISH_CHARS = "àâäçéèêëîïôöùûüÿœæñ¿¡"
OUT_OF_MARKET_MALONE_TERMS = (
    "north carolina", "unc", "tar heels", "college basketball",
    "finalize deal", "finalizing a deal", "hire michael malone",
    "michael malone as basketball coach", "basketball coach",
)
DENVER_MALONE_ANCHORS = (
    "denver nuggets", "nuggets owner", "josh kroenke", "calvin booth",
    "nikola jokic", "jamal murray", "nuggets roster", "nuggets offseason",
    "front office", "exit interview", "press conference", "presser",
)
LOCAL_TRUST_TERMS = (
    "dnvr", "denver post", "altitude", "troy renck", "renck", "katy winge",
    "harrison wind", "mike singer", "ryan blackburn", "vinny benedetto",
    "bennett durando", "chris dempsey", "vic lombardi", "haertl",
)
UNRESOLVED_PRONOUN_TERMS = (
    "he", "him", "his", "himself", "that guy", "this guy", "that dude",
    "this dude", "that kid", "this kid", "dude", "kid",
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
            parsed = parser(value)
            if parsed is not None:
                return parsed
        except Exception:
            pass
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
        try:
            parsed = parsedate_to_datetime(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (TypeError, ValueError):
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
    crypto_avalanche = (
        any(word in lower for word in ("$avax", "avax", "altcoin", "crypto", "smart money", "trade alerts"))
        and any(word in lower for word in ("avalanche", "avs"))
        and not any(word in lower for word in ("colorado avalanche", "goavsgo", "nhl", "hockey", "puck", "goalie", "mackinnon", "makar"))
    )

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
            if crypto_avalanche:
                tags = [tag for tag in tags if tag != "avs"]
            if "avs" in tags and not any(has_topic_word(word) for word in AVALANCHE_PULSE_TERMS + ("mackinnon", "makar")):
                tags = [tag for tag in tags if tag != "avs"]
            return tags or ["general"]
        except Exception:
            pass
    tags = []
    for tag, words in {
        "broncos": ("broncos", "bo nix", "sean payton", "paton"),
        "nuggets": ("nuggets", "jokic", "murray"),
        "avs": () if crypto_avalanche else ("avs", "avalanche", "mackinnon", "makar"),
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


def _term_in_text(text: str, term: str) -> bool:
    lower = text.lower()
    needle = str(term or "").strip().lower()
    if not needle:
        return False
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(needle)}(?![a-z0-9])", lower))


def _count_terms(text: str, terms: tuple[str, ...]) -> int:
    return sum(1 for term in terms if _term_in_text(text, term))


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
    return any(_term_in_text(text, term) for term in terms)


def _audience_fit(text: str) -> float:
    primary_hits = _count_terms(text, PRIMARY_AUDIENCE_TERMS)
    sports_hits = _count_terms(text, SPORTS_TERMS)
    if primary_hits:
        return min(10.0, 6.5 + primary_hits * 1.2 + min(sports_hits, 3) * 0.4)
    if sports_hits:
        return min(8.0, 3.5 + sports_hits * 0.8)
    return 2.0


def _reply_tension(text: str) -> float:
    lower = text.lower()
    if _is_colorado_current_context(lower):
        return 5.4
    hits = _count_terms(text, TENSION_TERMS)
    if hits:
        return min(10.0, 5.0 + hits * 1.1)
    if text.endswith("?"):
        return 4.0
    return 2.5


def _is_avalanche_pregame_or_news(text: str) -> bool:
    lower = text.lower()
    if _is_completed_game_context(lower):
        return False
    return _contains_any(lower, AVALANCHE_PULSE_TERMS) and _contains_any(lower, PREGAME_OR_BREAKING_TERMS)


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


def _is_crypto_avalanche_context(text: str) -> bool:
    lower = _text(text).lower()
    return (
        _contains_any(lower, CRYPTO_AVALANCHE_TERMS)
        and _contains_any(lower, AVALANCHE_PULSE_TERMS)
        and not _contains_any(lower, AVALANCHE_SPORTS_TERMS)
    )


def _is_non_sports_avs_context(text: str) -> bool:
    lower = _text(text).lower()
    if not re.search(r"\bavs\b", lower):
        return False
    if not _contains_any(lower, NON_SPORTS_AVS_TERMS):
        return False
    return not _contains_any(lower, AVALANCHE_SPORTS_TERMS)


def _is_promo_source_text(text: str) -> bool:
    lower = _text(text).lower()
    return _contains_any(lower, PROMO_SOURCE_TERMS)


def _is_commerce_source_text(text: str) -> bool:
    lower = _text(text).lower()
    return _contains_any(lower, COMMERCE_SOURCE_TERMS)


def _is_low_quality_source_text(text: str) -> bool:
    return (
        _is_non_sports_avs_context(text)
        or _is_promo_source_text(text)
        or _is_commerce_source_text(text)
    )


def _has_colorado_sports_entity(text: str) -> bool:
    lower = _text(text).lower()
    if _is_crypto_avalanche_context(lower):
        return False
    if _is_out_of_market_context(lower):
        return False
    if _is_low_quality_source_text(lower):
        return False
    return _contains_any(lower, COLORADO_TEAM_TERMS)


def _is_colorado_current_context(text: str) -> bool:
    lower = _text(text).lower()
    if _is_completed_game_context(lower):
        return False
    has_colorado = _has_colorado_sports_entity(lower)
    if not has_colorado:
        return False
    return (
        _is_live_game_context(lower)
        or _contains_any(lower, PREGAME_OR_BREAKING_TERMS)
        or _contains_any(lower, TENSION_TERMS)
        or _contains_any(lower, ("breaking", "just", "report", "rumor", "quote", "coach", "trade", "trading", "injury", "says", "comments", "offseason", "front office"))
    )


def _is_betting_signal_text(text: str) -> bool:
    lower = str(text or "").lower()
    return (
        _contains_any(lower, BETTING_SIGNAL_TERMS)
        or bool(re.search(r"\b[oOuU]\s?\d+(?:\.\d+)?\b", lower))
        or bool(re.search(r"\([+-]\d{2,4}\)", lower))
        or bool(re.search(r"\b[+-]\d{2,4}\b", lower) and _contains_any(lower, ("ks", "points", "rebounds", "assists", "yards")))
    )


def _is_out_of_market_context(text: str) -> bool:
    lower = _text(text).lower()
    if "michael malone" in lower and _contains_any(lower, OUT_OF_MARKET_MALONE_TERMS):
        if not _contains_any(lower, DENVER_MALONE_ANCHORS):
            return True
        if "north carolina" in lower or "unc" in lower or "tar heels" in lower:
            denver_hits = _count_terms(lower, DENVER_MALONE_ANCHORS)
            out_hits = _count_terms(lower, OUT_OF_MARKET_MALONE_TERMS)
            return out_hits > denver_hits
    return False


def _is_english_source_text(text: str) -> bool:
    clean = _text(text)
    if not clean:
        return False
    lower = f" {clean.lower()} "
    letters = re.findall(r"[A-Za-zÀ-ÿ]", clean)
    if not letters:
        return False
    marker_hits = sum(1 for marker in NON_ENGLISH_MARKERS if marker in lower)
    accented = sum(1 for ch in clean.lower() if ch in NON_ENGLISH_CHARS)
    if marker_hits >= 3:
        return False
    if accented >= 2 and marker_hits >= 1:
        return False
    ascii_letters = sum(1 for ch in letters if "a" <= ch.lower() <= "z")
    if len(letters) >= 80 and ascii_letters / max(len(letters), 1) < 0.9:
        return False
    return True


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


def _colorado_cluster_key(text: str) -> str:
    lower = _text(text).lower()
    if _is_crypto_avalanche_context(lower) or _is_out_of_market_context(lower) or _is_low_quality_source_text(lower):
        return ""
    team = ""
    if _contains_any(lower, ("nuggets", "denver nuggets", "nikola jokic", "jokic", "jamal murray", "aaron gordon", "michael malone", "calvin booth")):
        team = "nuggets"
    elif _contains_any(lower, ("broncos", "denver broncos", "bo nix", "sean payton", "courtland sutton")):
        team = "broncos"
    elif _contains_any(lower, ("avalanche", "colorado avalanche", "avs", "mackinnon", "nathan mackinnon", "makar", "cale makar")):
        team = "avalanche"
    elif _contains_any(lower, ("rockies", "colorado rockies")):
        team = "rockies"
    elif _contains_any(lower, ("buffs", "cu buffs", "colorado buffaloes", "coach prime", "deion")):
        team = "buffs"
    elif _contains_any(lower, ("denver sports", "colorado sports", "altitude sports")):
        team = "colorado-sports"
    if not team:
        return ""
    if _is_live_game_context(lower):
        return team
    if _contains_any(lower, ("press conference", "press conferences", "presser", "media availability", "availability", "exit interview", "exit interviews", "end of season", "end-of-season")):
        return f"{team}-press"
    if _contains_any(lower, ("injury", "report", "quote", "coach", "trade", "rumor", "breaking", "news")):
        return f"{team}-news"
    return ""


def _risk_flags(text: str) -> list[str]:
    flags = []
    lower = text.lower()
    if _is_betting_signal_text(text):
        flags.append("betting_angle")
    if not _is_english_source_text(text):
        flags.append("non_english_source")
    if _is_out_of_market_context(text):
        flags.append("out_of_market_context")
    if _is_non_sports_avs_context(text):
        flags.append("non_sports_avs_context")
    if _is_promo_source_text(text):
        flags.append("promo_source")
    if _is_commerce_source_text(text):
        flags.append("commerce_source")
    for term in UNSAFE_MONETIZATION_TERMS:
        if _term_in_text(lower, term):
            flags.append(f"unsafe:{term}")
    for term in _heated_risk_hits(text):
        flags.append(f"heated:{term}")
    if re.search(r"\b\d+(\.\d+)?\s*%\b", lower) and not ("source" in lower or "report" in lower):
        flags.append("unverified-stat")
    return list(dict.fromkeys(flags))


def _context_flags(text: str) -> list[str]:
    clean = _text(text)
    lower = clean.lower()
    flags = []
    if re.match(r"^@\w+", clean):
        flags.append("reply_fragment_context")
        if any(re.search(rf"\b{re.escape(term)}\b", lower) for term in UNRESOLVED_PRONOUN_TERMS):
            flags.append("unresolved_pronoun_context")
    elif any(re.search(rf"\b{re.escape(term)}\b", lower) for term in UNRESOLVED_PRONOUN_TERMS):
        has_named_context = bool(
            re.search(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}\b", clean)
            or re.search(r"\b(?:Broncos|Nuggets|Avalanche|Avs|Rockies|Buffs|CU|Coach Prime|Deion|Jokic|Murray|MacKinnon|Makar|Bo Nix|Sean Payton)\b", clean)
        )
        if not has_named_context:
            flags.append("unresolved_pronoun_context")
    return list(dict.fromkeys(flags))


def _source_reliability(source: str) -> float:
    return SOURCE_RELIABILITY.get((source or "").lower(), SOURCE_RELIABILITY["news"])


def _freshness_status(source: str, timestamp: datetime | None, text: str, now: datetime | None = None) -> str:
    source_key = (source or "news").lower()
    if timestamp is None:
        if source_key == "sports_context" and (_is_live_game_context(text) or _is_colorado_current_context(text)):
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
    context_flags = _context_flags(text)
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
        "context_flags": context_flags,
        "freshness_status": _freshness_status(src, timestamp, text, now),
        "is_reply_target": bool(author and not text.startswith("@")),
    }


def signal_from_text(text: str, *, source: str = "news", url: str = "",
                     now: datetime | None = None, timestamp: Any = None) -> dict[str, Any]:
    clean = _text(text)
    context_flags = _context_flags(clean)
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
        "context_flags": context_flags,
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
            if not _is_english_source_text(text):
                continue
            if _is_out_of_market_context(text):
                continue
            if _is_low_quality_source_text(text):
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
                if not _is_english_source_text(text):
                    continue
                if _is_out_of_market_context(text):
                    continue
                if _is_low_quality_source_text(text):
                    continue
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
                    timestamp = _now(now) if (_is_live_game_context(line) or _is_colorado_current_context(line)) else None
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
    colorado_key = _colorado_cluster_key(signal.get("text", ""))
    if colorado_key:
        return colorado_key
    topic = signal.get("topic") or "general"
    if topic != "general":
        return topic.split(",")[0].strip()
    tokens = [tok for tok in _tokens(signal.get("text", "")) if tok not in {"this", "that", "with", "from", "they", "have"}]
    return " ".join(tokens[:3]) or "general"


def _source_depth_score(signal: dict[str, Any]) -> float:
    text = _text(signal.get("text", ""))
    source_identity = " ".join([
        text,
        _text(signal.get("author", "")),
        _text(signal.get("url", "")),
    ])
    lower = source_identity.lower()
    if _is_low_quality_source_text(lower):
        return -10.0
    score = min(6.0, len(text) / 45.0)
    score += min(1.5, float(signal.get("source_reliability") or 0) / 4.0)
    score += min(3.0, _count_terms(text, COLORADO_TEAM_TERMS + PREGAME_OR_BREAKING_TERMS))
    if signal.get("url"):
        score += 0.5
    if _contains_any(lower, SUBSTANTIVE_SOURCE_TERMS):
        score += 2.0
    if re.search(r"\b(thank you for asking|genuine|transparent|ownership|staff)\b", lower):
        score += 1.0
    if _contains_any(lower, SPECULATIVE_REACTION_TERMS):
        score -= 4.5
    if _is_promo_source_text(lower) or _is_commerce_source_text(lower):
        score -= 7.0
    if lower.startswith("@"):
        score -= 1.0
    if lower.startswith(("me during", "me watching", "my reaction")):
        score -= 4.0
    if any(mark in text for mark in ("😒", "😂", "😭", "🤣")):
        score -= 1.5
    if " - " in text and re.search(r"\b(observer|gazette|post|sports|dnvr|altitude)\b", lower):
        score += 1.0
    if _contains_any(lower, LOCAL_TRUST_TERMS):
        score += 2.5
    if len(text) < 80:
        score -= 1.5
    return score


def _is_speculative_reaction_source(signal: dict[str, Any]) -> bool:
    text = _text((signal or {}).get("text", ""))
    lower = text.lower()
    return (
        _contains_any(lower, SPECULATIVE_REACTION_TERMS)
        or _is_low_quality_source_text(lower)
        or lower.startswith(("me during", "me watching", "my reaction"))
        or any(mark in text for mark in ("😒", "😂", "😭", "🤣"))
    )


def _topic_team(topic: str) -> str:
    topic = str(topic or "").lower()
    if topic.startswith("nuggets"):
        return "nuggets"
    if topic.startswith("broncos"):
        return "broncos"
    if topic.startswith(("avs", "avalanche")):
        return "avalanche"
    if topic.startswith("rockies"):
        return "rockies"
    if topic.startswith("buffs"):
        return "buffs"
    return ""


def _mentions_other_colorado_team(text: str, team: str) -> bool:
    lower = _text(text).lower()
    team_terms = {
        "nuggets": ("nuggets", "jokic", "murray", "malone", "booth", "kroenke"),
        "broncos": ("broncos", "bo nix", "payton", "paton", "sutton"),
        "avalanche": ("avalanche", "avs", "mackinnon", "makar", "landeskog"),
        "rockies": ("rockies",),
        "buffs": ("buffs", "cu buffs", "coach prime", "deion"),
    }
    for other_team, terms in team_terms.items():
        if other_team != team and _contains_any(lower, terms):
            return True
    return False


def _draft_basis_signals(signals: list[dict[str, Any]], topic: str = "") -> list[dict[str, Any]]:
    team = _topic_team(topic)
    clean_basis = [
        s for s in signals
        if not _is_speculative_reaction_source(s)
        and "unresolved_pronoun_context" not in set(s.get("context_flags", []) or [])
        and s.get("freshness_status") != "stale"
        and "non_english_source" not in set(s.get("risk_flags", []) or [])
        and "out_of_market_context" not in set(s.get("risk_flags", []) or [])
        and "non_sports_avs_context" not in set(s.get("risk_flags", []) or [])
        and "promo_source" not in set(s.get("risk_flags", []) or [])
        and "commerce_source" not in set(s.get("risk_flags", []) or [])
    ]
    if team:
        pure_basis = [s for s in clean_basis if not _mentions_other_colorado_team(s.get("text", ""), team)]
        if pure_basis:
            clean_basis = pure_basis
    if clean_basis:
        return clean_basis[:4]
    non_speculative = [s for s in signals if not _is_speculative_reaction_source(s)]
    return (non_speculative or signals)[:4]


def cluster_signals(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for signal in signals:
        grouped.setdefault(_cluster_key(signal), []).append(signal)
    clusters = []
    for key, items in grouped.items():
        sorted_items = sorted(
            items,
            key=lambda s: (
                bool(set(s.get("context_flags", []) or []) & {"reply_fragment_context", "unresolved_pronoun_context"}),
                s.get("freshness_status") == "stale",
                -_source_depth_score(s),
                -float(s.get("velocity") or 0),
            ),
        )
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
    draft_basis = _draft_basis_signals(signals, str(cluster.get("topic", "")))
    draft_primary = draft_basis[0] if draft_basis else primary
    text = " ".join(s.get("text", "") for s in signals[:4])
    colorado_now = _is_colorado_pregame_or_news(text)
    fresh_count = sum(1 for s in signals if s.get("freshness_status") in ("fresh", "usable"))
    source_count = len({str(s.get("source") or "") for s in signals if s.get("source")})
    independent_source_count = len({
        str(s.get("author") or s.get("url") or s.get("id") or "")
        for s in signals
        if s.get("author") or s.get("url") or s.get("id")
    })
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
    context_flags = []
    for signal in signals:
        for flag in signal.get("risk_flags", []) or []:
            if flag.startswith("unsafe:"):
                safety -= 5.0
            elif flag == "unverified-stat":
                safety -= 2.5
            else:
                safety -= 1.2
            risk_flags.append(flag)
        for flag in signal.get("context_flags", []) or []:
            context_flags.append(flag)
    safety = max(0.0, safety)
    timeliness = min(20.0, max(0.0, 20.0 - best_age * 1.7))
    if fresh_count >= 2:
        timeliness = min(20.0, timeliness + 2.0)
    velocity = min(15.0, max_velocity / 2.0 + len(signals) * 1.5)
    conversation_dominance = min(
        15.0,
        max(0.0, (len(signals) - 1) * 1.8 + max(0, source_count - 1) * 1.5 + max(0, independent_source_count - 1) * 1.4),
    )
    if colorado_now:
        timeliness = max(timeliness, 18.5)
        velocity = max(velocity, 6.0)
    urgency = 10.0 if _contains_any(text, LIVE_TERMS) else max(3.0, timeliness / 2.5)
    if colorado_now:
        urgency = 10.0
    voice_fit = min(10.0, 3.0 + reply_tension * 0.45 + audience_fit * 0.25)
    public_x = cexa.public_x_opportunity_report(text, source_basis=draft_basis, state=state)
    retrieval_fit = int(public_x.get("retrieval_fit", 0) or 0)
    oon_readability = int(public_x.get("oon_readability", 0) or 0)
    candidate_fit = int(public_x.get("candidate_fit", 0) or 0)
    positive_action_clarity = int(public_x.get("positive_action_fit", 0) or 0)
    negative_signal_risk = int(public_x.get("negative_signal_risk", 0) or 0)
    not_dwelled = int(public_x.get("not_dwelled_risk", 0) or 0)
    negative_signal_safety = max(0, 100 - negative_signal_risk)
    weighted = {
        "timeliness": timeliness,
        "velocity": velocity,
        "audience_fit": min(15.0, audience_fit * 1.5),
        "reply_tension": min(12.0, reply_tension * 1.2),
        "fact_confidence": fact_confidence,
        "novelty": novelty,
        "voice_fit": voice_fit,
        "monetization_safety": safety,
        "post_now_urgency": urgency,
        "conversation_dominance": conversation_dominance,
        "retrieval_fit": min(12.0, retrieval_fit * 0.12),
        "oon_readability": min(8.0, oon_readability * 0.08),
        "positive_action_clarity": min(10.0, positive_action_clarity * 0.10),
        "negative_signal_safety": min(10.0, negative_signal_safety * 0.10),
        "not_dwelled_safety": min(6.0, (100 - not_dwelled) * 0.06),
    }
    raw_score = sum(weighted.values())
    score = round(min(100.0, raw_score / 160.0 * 100.0), 2)
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
    if "betting_angle" in risk_flags:
        hard_blocks.append("betting_angle")
    if "non_english_source" in risk_flags:
        hard_blocks.append("non_english_source")
    if "out_of_market_context" in risk_flags:
        hard_blocks.append("out_of_market_context")
    if "non_sports_avs_context" in risk_flags:
        hard_blocks.append("non_sports_avs_context")
    if "promo_source" in risk_flags:
        hard_blocks.append("promo_source")
    if "commerce_source" in risk_flags:
        hard_blocks.append("commerce_source")
    if novelty_flag == "duplicate_recent_angle":
        hard_blocks.append("duplicate_recent_angle")
    if not_dwelled >= 70:
        hard_blocks.append("high_not_dwelled_risk")
    elif not_dwelled >= 45:
        soft_flags.append("medium_not_dwelled_risk")
    if candidate_fit < 40 and not colorado_now:
        hard_blocks.append("weak_candidate_anchor")
    elif candidate_fit < 55:
        soft_flags.append("weak_candidate_anchor")
    if oon_readability < 35 and not colorado_now:
        hard_blocks.append("weak_oon_readability")
    elif oon_readability < 55:
        soft_flags.append("weak_oon_readability")
    if positive_action_clarity < 45:
        soft_flags.append("unclear_action_path")
    primary_context_flags = set(primary.get("context_flags", []) or [])
    self_contained_sources = [
        s for s in signals
        if not (set(s.get("context_flags", []) or []) & {"reply_fragment_context", "unresolved_pronoun_context"})
    ]
    if not self_contained_sources:
        if "reply_fragment_context" in context_flags:
            hard_blocks.append("reply_fragment_context")
        if "unresolved_pronoun_context" in context_flags:
            hard_blocks.append("unresolved_pronoun_context")
    elif primary_context_flags & {"reply_fragment_context", "unresolved_pronoun_context"}:
        soft_flags.append("context_from_secondary_source")
    action_path = _recommended_action_path(text, weighted, draft_basis)
    action = "tweet"
    if score < DEFAULT_THRESHOLD and score >= SAVE_THRESHOLD:
        action = "save"
    return {
        "id": cluster.get("id", ""),
        "topic": cluster.get("topic", "general"),
        "summary_text": draft_primary.get("text", ""),
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
                "context_flags": list(s.get("context_flags", []) or []),
            }
            for s in draft_basis[:4]
        ],
        "score": score,
        "raw_score": round(raw_score, 2),
        "weighted_scores": {k: round(v, 2) for k, v in weighted.items()},
        "hard_blocks": hard_blocks,
        "soft_flags": soft_flags,
        "risk_flags": list(dict.fromkeys(risk_flags)),
        "context_flags": list(dict.fromkeys(context_flags)),
        "recommended_action": action,
        "recommended_action_path": action_path,
        "recommended_lane": _recommended_lane(text, reply_tension, safety),
        "target_action": public_x.get("target_action", action_path),
        "candidate_anchor": public_x.get("candidate_anchor", ""),
        "sports_mechanism": public_x.get("sports_mechanism", ""),
        "candidate_fit": candidate_fit,
        "retrieval_fit": retrieval_fit,
        "oon_readability": oon_readability,
        "negative_signal_risk": negative_signal_risk,
        "not_dwelled_risk": not_dwelled,
        "public_x_read": {
            "retrieval_fit": retrieval_fit,
            "positive_action_path": action_path,
            "negative_risk": negative_signal_risk,
            "why_this_can_rank": f"{public_x.get('candidate_anchor') or public_x.get('sports_mechanism') or 'source'} has {public_x.get('target_action', action_path)} potential with {public_x.get('negative_signal_reason', 'low risk')}.",
        },
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
    if (
        fresh_sources
        and float(item.get("candidate_fit", 0) or 0) >= 80
        and float(item.get("retrieval_fit", 0) or 0) >= 80
        and float(item.get("freshness_score", 0) or 0) >= 18
        and _contains_any(text, ("avalanche", "avs", "nuggets", "broncos", "rockies", "buffs"))
    ):
        return True
    if _is_colorado_current_context(text) and fresh_sources and _contains_any(
        text,
        (
            "breaking", "just", "report", "rumor", "quote", "coach", "trade",
            "injury", "press conference", "presser", "media availability",
            "availability", "exit interview", "end of season", "end-of-season",
        ),
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
    if _contains_any(lower, ("absurd", "weird", "funny")):
        return "Comedic"
    if _contains_any(lower, ("final", "win", "clutch")):
        return "Celebratory"
    if _contains_any(lower, ("refs", "excuse", "mistake", "problem")):
        return "Annoyed"
    if reply_tension >= 7:
        return "Witty Edge"
    return _ce_default_lane()


def _recommended_action_path(text: str, weighted: dict[str, float], source_basis: list[dict[str, Any]] | None = None) -> str:
    lower = str(text or "").lower()
    if any(term in lower for term in ("video", "youtube", "breakdown", "film")):
        return "click"
    if any(term in lower for term in ("absurd", "funny", "weird", "meme", "meltdown")):
        return "quote"
    if any(term in lower for term in ("win", "clutch", "signed", "extension", "positive momentum")):
        return "repost"
    if float(weighted.get("reply_tension", 0) or 0) >= 7:
        return "reply"
    if float(weighted.get("retrieval_fit", 0) or 0) >= 8:
        return "dwell"
    return "reply"


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
    live_usable = [item for item in colorado_usable if _is_live_game_context(_opportunity_text(item))]
    best = live_usable[0] if live_usable else colorado_usable[0] if colorado_usable else None
    status = "no_op"
    if best and not _blocking_blocks(best):
        _thin_room_signal = "thin_room_signal" in (best.get("soft_flags") or [])
        if _has_strong_now_signal(best) or any(_is_live_game_context(str((src or {}).get("text") or "")) for src in (best.get("source_basis") or []) if isinstance(src, dict)):
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
    decision_best = best if status != "no_op" else None
    decision = {
        "version": PULSE_VERSION,
        "status": status,
        "handle": handle,
        "threshold": threshold,
        "checked_at": _now(now).isoformat(timespec="seconds"),
        "search_depth": ["fast_check", "deep_hunt", "reply_hunt", "best_available_now", "safety_gate"],
        "signals_checked": len(signals),
        "clusters_checked": len(clusters),
        "best": decision_best,
        "top_rejected": [item for item in scored if item.get("id") != (decision_best or {}).get("id")][:5],
        "message": (
            "No safe Denver/Colorado Pulse source right now."
            if status == "no_op"
            else "Pulse found the best tweet available right now."
            if status == "ready"
            else "Pulse found the best available Colorado timeline angle right now."
        ),
    }
    if decision_best:
        decision["brief"] = build_pulse_brief(decision_best, state)
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
    action = "save" if opportunity.get("recommended_action") == "save" else "tweet"
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

PUBLIC X ALGORITHM READ:
- Candidate anchor: {opportunity.get('candidate_anchor') or 'unclear'}
- Recommended action path: {opportunity.get('recommended_action_path') or opportunity.get('target_action') or 'reply'}
- Retrieval fit: {opportunity.get('retrieval_fit', 0)}
- Out-of-network readability: {opportunity.get('oon_readability', 0)}
- Negative-signal risk: {opportunity.get('negative_signal_risk', 0)}
- Not-dwelled risk: {opportunity.get('not_dwelled_risk', 0)}
- Do not summarize the source. Convert it into one original Tyler observation with the anchor visible early.

SOURCE BASIS:
{chr(10).join(source_lines)}

CREATOR EVOLUTION LIVE RULES:
{rules or "- No approved rule changes yet. Use base Creator Evolution rules only."}

PULSE WRITING CONTRACT:
- Write only from the source basis above.
- Pulse writes original standalone tweets only. X/Twitter sources are room-reading signals, not reply targets.
- Do not address, mention, or prefix any source author handle from the source basis.
- Make it feel immediate without inventing facts.
- No Hall of Fame hooks, no Creator Studio calibration, no old What's Hot formulas.
- No fake engagement questions, no invented stats, no unsafe claims.
- Default to witty edge unless the recommended lane says otherwise."""
