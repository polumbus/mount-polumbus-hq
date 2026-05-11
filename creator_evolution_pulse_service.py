"""Headless Creator Evolution Pulse service.

This module is intentionally Streamlit-free. It is used by the Discord/OpenClaw
adapter and can also be called from tests or cron jobs.
"""

from __future__ import annotations

import argparse
import email.utils
import hashlib
import json
import os
import re
import subprocess
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import creator_evolution as ce
import creator_evolution_pulse as pulse


HQ_ROOT = Path(__file__).resolve().parent
DEFAULT_STATE_PATH = Path("/home/polfam/.openclaw/workspace-omaha/data/creator_evolution_state.json")
DEFAULT_ARTIFACT_DIR = Path("/home/polfam/.openclaw/workspace-omaha/state/workflow/tweets/pulse")
DEFAULT_FORMAT = "Normal Tweet"
DEFAULT_LANE = "Witty Edge"
PULSE_SERVICE_VERSION = "discord-pulse-v1"
LOCAL_PROXY_URL = "http://127.0.0.1:7821"

OWNER_SEARCH_QUERIES = [
    "Denver Broncos OR Broncos OR Bo Nix OR Sean Payton -filter:retweets",
    "Denver Nuggets OR Nuggets OR Jokic OR Jamal Murray -filter:retweets",
    '"Nuggets" ("press conference" OR presser OR "media availability" OR "exit interviews" OR "end of season" OR "Josh Kroenke" OR "Calvin Booth" OR "Michael Malone") -filter:retweets',
    "Colorado Avalanche OR Avalanche OR Avs OR MacKinnon OR Makar -filter:retweets",
    "Colorado Buffaloes OR CU Buffs OR Coach Prime OR Deion Sanders -filter:retweets",
    "Colorado Rockies OR Rockies -filter:retweets",
    '"Denver sports" OR "Colorado sports" OR "Altitude Sports" -filter:retweets',
]

TOPIC_RSS_TEMPLATE = "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"

TRUSTED_LISTS = {
    "1294328608417177604": "Broncos Reporters",
    "1755985316752642285": "Nuggets",
    "2011987998699897046": "Morning Engagement",
}

OWNER_RSS_FEEDS = [
    "https://news.google.com/rss/search?q=Denver+Nuggets+OR+Nuggets+OR+Jokic+OR+Jamal+Murray+OR+Michael+Malone+press+conference+breaking+news&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=Nuggets+Josh+Kroenke+OR+Calvin+Booth+OR+Michael+Malone+OR+exit+interviews+OR+media+availability+OR+end+of+season&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=Denver+Broncos+OR+Broncos+OR+Bo+Nix+OR+Sean+Payton+breaking+news&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=Colorado+Avalanche+OR+Avs+NHL+breaking+news&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=Colorado+Rockies+OR+Rockies+MLB+breaking+news&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=Colorado+Buffaloes+OR+CU+Buffs+OR+Coach+Prime+breaking+news&hl=en-US&gl=US&ceid=US:en",
]

BLOCKED_DRAFT_TERMS = [
    "source basis",
    "recommended tweet",
    "recommended reply",
    "why now:",
    "score ",
    "confidence ",
    "creator evolution",
    "pulse",
    "bet slip",
    "parlay",
    "odds",
    "over/under",
    "o/u",
    " -140",
    " +100",
]


@dataclass
class PulseRequest:
    mode: str = "run"
    lane: str = DEFAULT_LANE
    fmt: str = DEFAULT_FORMAT
    request_id: str = ""
    state_path: Path = DEFAULT_STATE_PATH
    artifact_dir: Path = DEFAULT_ARTIFACT_DIR
    decision_path: Optional[Path] = None
    mock: str = ""
    force_refresh: bool = False
    generate_drafts: bool = True
    timeout_seconds: int = 55
    search_limit: int = 15
    list_limit: int = 20
    rss_limit: int = 12
    topic: str = ""
    tweet_url: str = ""
    created_at: str = field(default_factory=lambda: _utc_now().isoformat())


@dataclass(frozen=True)
class SubjectSpec:
    raw: str
    kind: str
    canonical: str
    required_terms: Tuple[str, ...] = ()
    optional_terms: Tuple[str, ...] = ()
    source_anchor_terms: Tuple[str, ...] = ()
    event_terms: Tuple[str, ...] = ()
    ambiguous: bool = False
    source_text: str = ""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _request_id(seed: str = "") -> str:
    base = f"{seed}:{time.time()}:{os.getpid()}"
    return "pulse_" + hashlib.sha1(base.encode("utf-8")).hexdigest()[:10]


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        pass
    try:
        parsed = email.utils.parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _age_hours(value: Any) -> Optional[float]:
    parsed = _parse_dt(value)
    if not parsed:
        return None
    return max(0.0, (_utc_now() - parsed).total_seconds() / 3600)


def _get_twitterapi_key() -> str:
    try:
        import sys

        helper_dir = Path("/home/polfam/.openclaw/scripts")
        if helper_dir.exists() and str(helper_dir) not in sys.path:
            sys.path.insert(0, str(helper_dir))
        from config_helper import get_twitterapi_io_key  # type: ignore

        return str(get_twitterapi_io_key() or "").strip()
    except Exception:
        return os.getenv("TWITTERAPI_IO_KEY", "").strip()


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and value and key not in os.environ:
                os.environ[key] = value
    except Exception:
        return


def _proxy_key_candidates() -> List[str]:
    _load_env_file(HQ_ROOT / ".env.local")
    _load_env_file(Path.home() / ".config" / "openclaw" / "secrets.env")
    keys: List[str] = []
    for env_name in ("HQ_PROXY_KEY", "CLAUDE_PROXY_KEY", "HQ_GITHUB_PAT", "GITHUB_PAT"):
        raw = os.environ.get(env_name, "")
        for part in str(raw or "").split(","):
            key = part.strip()
            if key and key not in keys:
                keys.append(key)
    return keys


def _http_json(url: str, headers: Dict[str, str], params: Dict[str, Any], timeout: int = 14) -> Dict[str, Any]:
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}?{query}", headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", "replace")
    data = json.loads(body)
    return data if isinstance(data, dict) else {}


def _tweet_id_from_url(value: str) -> str:
    match = re.search(r"(?:status|statuses)/(\d+)", value or "")
    return match.group(1) if match else ""


def _tweet_author_from_url(value: str) -> str:
    match = re.search(r"https?://(?:www\.)?(?:x|twitter)\.com/([^/\s]+)/status(?:es)?/\d+", value or "", re.I)
    return match.group(1) if match else ""


AMBIGUOUS_ONE_WORD_SUBJECTS = {
    "murray",
    "smith",
    "brown",
    "jones",
    "wilson",
    "johnson",
    "thomas",
    "miller",
    "williams",
    "allen",
    "moore",
    "young",
    "jackson",
    "kelly",
}

TEAM_SUBJECTS: Dict[str, SubjectSpec] = {
    "avalanche": SubjectSpec(
        raw="avalanche",
        kind="team",
        canonical="Colorado Avalanche",
        required_terms=("avalanche", "avs", "goavsgo"),
        optional_terms=("mackinnon", "makar", "wedgewood", "toews", "landeskog", "necas"),
    ),
    "avs": SubjectSpec(
        raw="avs",
        kind="team",
        canonical="Colorado Avalanche",
        required_terms=("avalanche", "avs", "goavsgo"),
        optional_terms=("mackinnon", "makar", "wedgewood", "toews", "landeskog", "necas"),
    ),
    "broncos": SubjectSpec(
        raw="broncos",
        kind="team",
        canonical="Denver Broncos",
        required_terms=("broncos",),
        optional_terms=("bo nix", "nix", "sean payton", "payton"),
    ),
    "nuggets": SubjectSpec(
        raw="nuggets",
        kind="team",
        canonical="Denver Nuggets",
        required_terms=("nuggets",),
        optional_terms=("jokic", "jamal murray"),
    ),
    "rockies": SubjectSpec(raw="rockies", kind="team", canonical="Colorado Rockies", required_terms=("rockies",)),
    "buffs": SubjectSpec(
        raw="buffs",
        kind="team",
        canonical="Colorado Buffaloes",
        required_terms=("buffs", "cu buffs", "colorado buffaloes"),
        optional_terms=("coach prime", "deion"),
    ),
    "wild": SubjectSpec(
        raw="wild",
        kind="team",
        canonical="Minnesota Wild",
        required_terms=("wild", "mnwild"),
        optional_terms=("kaprizov", "faber", "hughes", "boldy"),
    ),
}

TEAM_SUBJECTS.update(
    {
        "colorado avalanche": TEAM_SUBJECTS["avalanche"],
        "denver broncos": TEAM_SUBJECTS["broncos"],
        "denver nuggets": TEAM_SUBJECTS["nuggets"],
        "colorado rockies": TEAM_SUBJECTS["rockies"],
        "colorado buffaloes": TEAM_SUBJECTS["buffs"],
        "minnesota wild": TEAM_SUBJECTS["wild"],
    }
)

SOURCE_HANDLE_SUBJECTS = {
    "mnwild": "wild",
    "mnwildpr": "wild",
    "coloradoavalanche": "avalanche",
    "avalanche": "avalanche",
    "broncos": "broncos",
    "nuggets": "nuggets",
    "rockies": "rockies",
    "cubuffs": "buffs",
}


def _token_terms(value: str) -> List[str]:
    terms: List[str] = []
    for word in re.findall(r"[A-Za-z][A-Za-z0-9'-]{1,}", value or ""):
        low = word.lower().strip("'")
        if low in {"the", "and", "for", "with", "news"}:
            continue
        if low not in terms:
            terms.append(low)
    return terms


def _tweet_link_subject_terms(source_text: str) -> Tuple[str, ...]:
    cleaned = re.sub(r"https?://\\S+", " ", source_text or "")
    cleaned = re.sub(r"[@#][A-Za-z0-9_]+", " ", cleaned)
    stop_names = {
        "here",
        "their",
        "this",
        "that",
        "they",
        "them",
        "look",
        "looked",
        "spend",
        "spent",
        "wondering",
        "counter",
        "punch",
        "desperate",
        "stars",
        "delivering",
        "goods",
        "far",
        "big",
        "way",
        "broncos",
        "avalanche",
        "nuggets",
        "rockies",
        "buffs",
        "colorado",
        "denver",
        "asked",
        "inside",
        "what",
        "play",
        "game",
        "rookie",
        "minicamp",
    }
    for match in re.finditer(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b", cleaned):
        words = [w.lower() for w in match.group(1).split()]
        if any(len(w) <= 2 for w in words):
            continue
        if any(w in stop_names for w in words):
            continue
        return tuple(words[:2])
    terms = [term for term in _token_terms(cleaned) if term not in stop_names]
    return tuple(terms[:2])


def _build_subject_spec(topic: str = "", source_text: str = "") -> Optional[SubjectSpec]:
    raw = _clean_text(topic)
    lower = raw.lower()
    if lower in TEAM_SUBJECTS:
        base = TEAM_SUBJECTS[lower]
        return SubjectSpec(
            raw=raw,
            kind=base.kind,
            canonical=base.canonical,
            required_terms=base.required_terms,
            optional_terms=base.optional_terms,
            event_terms=(),
            ambiguous=False,
            source_text=source_text,
        )
    if not raw and source_text:
        handles = [handle.lower() for handle in re.findall(r"@([A-Za-z0-9_]+)", source_text or "")]
        for handle in handles:
            team_key = SOURCE_HANDLE_SUBJECTS.get(handle)
            if team_key and team_key in TEAM_SUBJECTS:
                base = TEAM_SUBJECTS[team_key]
                source_terms = set(_token_terms(source_text))
                anchors = tuple(term for term in base.optional_terms if _term_in_text(term, source_text.lower()) or term in source_terms)
                return SubjectSpec(
                    raw="tweet link subject",
                    kind="tweet_link_team",
                    canonical=base.canonical,
                    required_terms=base.required_terms,
                    optional_terms=base.optional_terms,
                    source_anchor_terms=anchors[:4],
                    source_text=source_text,
                )
        subject_terms = _tweet_link_subject_terms(source_text)
        terms = tuple(_token_terms(source_text)[:8])
        return SubjectSpec(
            raw="tweet link subject",
            kind="tweet_link",
            canonical=" ".join(subject_terms) if subject_terms else "tweet link subject",
            required_terms=subject_terms or terms[:2],
            optional_terms=tuple(term for term in terms if term not in set(subject_terms))[:6],
            source_text=source_text,
        )
    terms = _token_terms(raw)
    if not terms:
        return None
    event_terms = tuple(term for term in terms if term in {"game", "presser", "press", "conference", "availability", "practice", "camp"})
    core_terms = tuple(term for term in terms if term not in event_terms)
    if len(core_terms) == 1 and core_terms[0] in AMBIGUOUS_ONE_WORD_SUBJECTS:
        return SubjectSpec(raw=raw, kind="ambiguous", canonical=raw, required_terms=core_terms, ambiguous=True)
    if event_terms and core_terms:
        return SubjectSpec(raw=raw, kind="event", canonical=raw, required_terms=core_terms, event_terms=event_terms)
    if len(core_terms) >= 2:
        return SubjectSpec(raw=raw, kind="person_or_phrase", canonical=raw, required_terms=core_terms)
    return SubjectSpec(raw=raw, kind="keyword", canonical=raw, required_terms=core_terms)


def _term_in_text(term: str, text: str) -> bool:
    term = (term or "").lower().strip()
    lower = (text or "").lower()
    if not term:
        return False
    if " " in term:
        return term in lower
    if len(term) <= 4:
        return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", lower) is not None
    return term in lower


def _focus_match_score(text: str, spec: Optional[SubjectSpec]) -> float:
    if not spec:
        return 1.0
    if spec.ambiguous:
        return 0.0
    lower_text = (text or "").lower()
    required_hits = sum(1 for term in spec.required_terms if _term_in_text(term, lower_text))
    optional_hits = sum(1 for term in spec.optional_terms if _term_in_text(term, lower_text))
    source_anchor_hits = sum(1 for term in spec.source_anchor_terms if _term_in_text(term, lower_text))
    event_hits = sum(1 for term in spec.event_terms if _term_in_text(term, lower_text))
    if spec.kind in {"team", "tweet_link_team"}:
        if spec.kind == "tweet_link_team" and spec.source_anchor_terms:
            if required_hits and source_anchor_hits:
                return 1.0 + min(optional_hits, 3) * 0.2
            return 0.0
        if required_hits:
            return 1.0 + min(optional_hits, 3) * 0.2
        return 0.45 if optional_hits >= 2 else 0.0
    if spec.kind == "event":
        if required_hits >= len(spec.required_terms) and event_hits:
            return 1.2 + optional_hits * 0.1
        return 0.0
    if spec.kind == "person_or_phrase":
        if required_hits < len(spec.required_terms):
            return 0.0
        return 1.0 + min(optional_hits, 2) * 0.35
    if spec.kind == "tweet_link":
        required_total = max(1, len(spec.required_terms))
        return 1.0 + min(optional_hits, 2) * 0.2 if required_hits >= required_total else 0.0
    return 1.0 if required_hits else 0.0


def _matches_spec(text: str, spec: Optional[SubjectSpec]) -> bool:
    return _focus_match_score(text, spec) >= 1.0


def _topic_queries_for_spec(spec: Optional[SubjectSpec]) -> List[str]:
    if not spec or spec.ambiguous:
        return []
    if spec.kind in {"team", "tweet_link_team"} and spec.canonical == "Colorado Avalanche":
        return [
            '("Colorado Avalanche" OR Avalanche OR "Avs" OR GoAvsGo) -filter:retweets',
            '(MacKinnon OR Makar OR Wedgewood OR Toews OR Landeskog) (Avalanche OR Avs OR GoAvsGo) -filter:retweets',
        ]
    if spec.kind in {"team", "tweet_link_team"} and spec.canonical == "Minnesota Wild":
        if spec.source_anchor_terms:
            anchors = " OR ".join(spec.source_anchor_terms)
            return [f'("Minnesota Wild" OR mnwild OR Wild) ({anchors}) -filter:retweets']
        return [
            '("Minnesota Wild" OR mnwild OR "Wild hockey") -filter:retweets',
            '(Kaprizov OR Faber OR Hughes OR Boldy) (Wild OR mnwild) -filter:retweets',
        ]
    if spec.kind in {"team", "tweet_link_team"} and spec.canonical == "Denver Broncos":
        return ['("Denver Broncos" OR Broncos OR "Bo Nix" OR "Sean Payton") -filter:retweets']
    if spec.kind in {"team", "tweet_link_team"} and spec.canonical == "Denver Nuggets":
        return ['("Denver Nuggets" OR Nuggets OR Jokic OR "Jamal Murray") -filter:retweets']
    if spec.kind == "event":
        core = " ".join(spec.required_terms)
        events = " OR ".join(spec.event_terms)
        return [f'("{spec.raw}" OR ({core} ({events}))) -filter:retweets']
    if spec.kind == "person_or_phrase":
        return [f'"{spec.raw}" -filter:retweets', f'({" OR ".join(spec.required_terms + spec.optional_terms)}) -filter:retweets']
    if spec.kind == "keyword":
        return [f'"{spec.raw}" OR ({spec.raw}) -filter:retweets']
    if spec.kind == "tweet_link" and spec.source_text:
        return [_subject_query_from_text(spec.source_text)]
    return []


def _subject_contract(topic: str, tweet_url: str, decision: Dict[str, Any]) -> Dict[str, Any]:
    spec = _build_subject_spec(topic)
    if not spec and tweet_url:
        basis = _source_basis(decision)
        source_item = next(
            (
                item
                for item in basis
                if isinstance(item, dict)
                and (item.get("source_type") == "source_tweet" or item.get("source_url") == tweet_url)
            ),
            None,
        )
        if not source_item and basis:
            source_item = basis[0]
        source_text = _source_tweet_context(source_item or {}, tweet_url) if source_item else ""
        spec = _build_subject_spec("", source_text=source_text)
    return {
        "topic_query": topic,
        "tweet_url": tweet_url,
        "kind": spec.kind if spec else "",
        "canonical": spec.canonical if spec else "",
        "required_terms": list(spec.required_terms) if spec else [],
        "optional_terms": list(spec.optional_terms) if spec else [],
        "source_anchor_terms": list(spec.source_anchor_terms) if spec else [],
        "event_terms": list(spec.event_terms) if spec else [],
        "ambiguous": bool(spec.ambiguous) if spec else False,
    }


def _topic_query(value: str) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    aliases = {
        "avalanche": '("Colorado Avalanche" OR Avalanche OR "Avs" OR GoAvsGo OR MacKinnon OR Makar OR Wedgewood OR "Game 3" OR Wild)',
        "avs": '("Colorado Avalanche" OR Avalanche OR "Avs" OR GoAvsGo OR MacKinnon OR Makar OR Wedgewood OR "Game 3" OR Wild)',
        "broncos": '(Denver Broncos OR Broncos OR Bo Nix OR Sean Payton)',
        "nuggets": '(Denver Nuggets OR Nuggets OR Jokic OR Jamal Murray)',
        "rockies": '(Colorado Rockies OR Rockies)',
        "buffs": '(Colorado Buffaloes OR CU Buffs OR Coach Prime OR Deion Sanders)',
    }
    alias = aliases.get(text.lower())
    if alias:
        return f"{alias} -filter:retweets"
    if re.search(r"\bOR\b|from:|filter:|\"", text, re.I):
        return text
    return f'"{text}" OR ({text}) -filter:retweets'


def _focus_terms(value: str) -> List[str]:
    lower_value = (value or "").strip().lower()
    aliases = {
        "avalanche": ["avalanche", "avs", "goavsgo", "mackinnon", "makar", "wedgewood"],
        "avs": ["avalanche", "avs", "goavsgo", "mackinnon", "makar", "wedgewood"],
        "broncos": ["broncos", "bo", "nix", "payton"],
        "nuggets": ["nuggets", "jokic", "jamal", "murray"],
    }
    if lower_value in aliases:
        return aliases[lower_value]
    terms = []
    for word in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", value or ""):
        low = word.lower().strip("'")
        if low in {"the", "and", "for", "with", "game", "presser", "press", "conference", "news"}:
            continue
        if low not in terms:
            terms.append(low)
    return terms


def _matches_focus(text: str, topic: str) -> bool:
    terms = _focus_terms(topic)
    if not terms:
        return True
    lower = (text or "").lower()
    def contains(term: str) -> bool:
        if len(term) <= 4:
            return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", lower) is not None
        return term in lower

    if (topic or "").strip().lower() in {"avalanche", "avs", "broncos", "nuggets"}:
        return any(contains(term) for term in terms)
    if len(terms) == 1:
        return contains(terms[0])
    # For named people, the rarest/surname-style token is usually the anchor.
    anchor = max(terms, key=len)
    return contains(anchor) or sum(1 for term in terms if contains(term)) >= min(2, len(terms))


def _focus_topic_label(topic: str) -> str:
    lower = (topic or "").strip().lower()
    if lower in {"avalanche", "avs"}:
        return "what Avs Twitter is talking about right now"
    return topic


def _subject_query_from_text(text: str) -> str:
    words = re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", text or "")
    stop = {
        "the",
        "and",
        "for",
        "with",
        "that",
        "this",
        "from",
        "have",
        "are",
        "was",
        "were",
        "but",
        "not",
        "you",
        "your",
        "they",
        "their",
        "http",
        "https",
        "com",
    }
    kept: List[str] = []
    for word in words:
        low = word.lower().strip("'")
        if low in stop or low.startswith("t.co"):
            continue
        if word not in kept:
            kept.append(word)
        if len(kept) >= 10:
            break
    if not kept:
        return ""
    return " OR ".join(f'"{word}"' if " " in word else word for word in kept) + " -filter:retweets"


def _embedded_tweet_text(raw: Dict[str, Any]) -> str:
    chunks: List[str] = []
    for key in ("quotedTweet", "quoted_tweet", "quoted_status", "retweetedTweet", "retweeted_status", "inReplyToTweet"):
        value = raw.get(key)
        if isinstance(value, dict):
            text = _clean_text(value.get("text") or value.get("full_text") or value.get("content"))
            if text:
                chunks.append(text)
    return " ".join(chunks)


def _normalize_tweet(raw: Dict[str, Any], source_name: str, source_type: str) -> Dict[str, Any]:
    created = raw.get("createdAt") or raw.get("created_at") or raw.get("time") or raw.get("date")
    author = raw.get("author") or {}
    if isinstance(author, dict):
        handle = author.get("userName") or author.get("username") or author.get("screen_name") or author.get("name")
    else:
        handle = ""
    text = _clean_text(raw.get("text") or raw.get("full_text") or raw.get("content"))
    embedded_text = _embedded_tweet_text(raw)
    return {
        "id": raw.get("id") or raw.get("tweetId") or raw.get("rest_id") or hashlib.sha1(_clean_text(raw).encode()).hexdigest()[:16],
        "text": text,
        "embedded_text": embedded_text,
        "createdAt": created,
        "created_at": created,
        "age_hours": _age_hours(created),
        "likeCount": raw.get("likeCount", raw.get("favorite_count", 0)) or 0,
        "retweetCount": raw.get("retweetCount", raw.get("retweet_count", 0)) or 0,
        "replyCount": raw.get("replyCount", raw.get("reply_count", 0)) or 0,
        "quoteCount": raw.get("quoteCount", raw.get("quote_count", 0)) or 0,
        "viewCount": raw.get("viewCount", raw.get("view_count", 0)) or 0,
        "url": raw.get("url") or raw.get("tweetUrl") or "",
        "author": handle or "",
        "source": source_name,
        "source_type": source_type,
    }


def _source_tweet_context(item: Dict[str, Any], tweet_url: str = "") -> str:
    return _clean_text(
        " ".join(
            part
            for part in [
                str(item.get("text") or ""),
                str(item.get("embedded_text") or ""),
                f"@{item.get('author')}" if item.get("author") else "",
                f"@{_tweet_author_from_url(tweet_url)}" if tweet_url else "",
            ]
            if part
        )
    )


def fetch_source_tweet(tweet_url: str) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    tweet_id = _tweet_id_from_url(tweet_url)
    if not tweet_id:
        return None, []
    key = _get_twitterapi_key()
    if not key:
        return None, ["missing TwitterAPI.io key for source tweet lookup"]
    headers = {"X-API-Key": key}
    errors: List[str] = []
    try:
        data = _http_json(
            "https://api.twitterapi.io/twitter/tweets",
            headers,
            {"tweet_ids": tweet_id},
            timeout=14,
        )
        tweets = data.get("tweets") or []
        if tweets:
            item = _normalize_tweet(tweets[0], "source_tweet", "source_tweet")
            item["source_url"] = tweet_url
            item["url_handle"] = _tweet_author_from_url(tweet_url)
            return item, errors
    except Exception as exc:
        errors.append(f"source tweet direct {tweet_id}: {exc}")
    try:
        data = _http_json(
            "https://api.twitterapi.io/twitter/tweet/advanced_search",
            headers,
            {"query": f"id:{tweet_id}", "queryType": "Latest"},
            timeout=14,
        )
        tweets = data.get("tweets") or []
        if tweets:
            item = _normalize_tweet(tweets[0], "source_tweet", "source_tweet")
            item["source_url"] = tweet_url
            item["url_handle"] = _tweet_author_from_url(tweet_url)
            return item, errors
    except Exception as exc:
        errors.append(f"source tweet {tweet_id}: {exc}")
    return None, errors


def fetch_twitter_signals(
    search_limit: int = 15,
    list_limit: int = 20,
    topic: str = "",
    tweet_url: str = "",
) -> Tuple[List[Dict[str, Any]], List[str]]:
    key = _get_twitterapi_key()
    if not key:
        return [], ["missing TwitterAPI.io key"]
    headers = {"X-API-Key": key}
    tweets: List[Dict[str, Any]] = []
    errors: List[str] = []
    cutoff = _utc_now() - timedelta(hours=24)
    extra_queries: List[str] = []

    source_tweet, source_errors = fetch_source_tweet(tweet_url)
    errors.extend(source_errors)
    source_text = ""
    if source_tweet and source_tweet.get("text"):
        source_text = _source_tweet_context(source_tweet, tweet_url)
        source_tweet["source_url"] = tweet_url
        tweets.append(source_tweet)
        subject_query = _subject_query_from_text(source_text)
        if subject_query:
            extra_queries.append(subject_query)
    spec = _build_subject_spec(topic, source_text=source_text if tweet_url and not topic else "")
    extra_queries.extend(_topic_queries_for_spec(spec))
    if tweet_url and not topic and not spec:
        return tweets, errors + ["source tweet could not be fetched; refusing broad Pulse for tweet link"]

    for list_id, name in TRUSTED_LISTS.items():
        try:
            data = _http_json(
                "https://api.twitterapi.io/twitter/list/tweets_timeline",
                headers,
                {"listId": list_id},
            )
            for raw in (data.get("tweets") or [])[:list_limit]:
                item = _normalize_tweet(raw, name, "trusted_list")
                created = _parse_dt(item.get("createdAt"))
                if item["text"] and (not spec or _matches_spec(item["text"], spec)) and (not created or created >= cutoff):
                    tweets.append(item)
        except Exception as exc:
            errors.append(f"list {name}: {exc}")

    queries = [q for q in extra_queries if q] or OWNER_SEARCH_QUERIES
    for query in queries:
        try:
            data = _http_json(
                "https://api.twitterapi.io/twitter/tweet/advanced_search",
                headers,
                {"query": query, "queryType": "Latest"},
            )
            for raw in (data.get("tweets") or [])[:search_limit]:
                item = _normalize_tweet(raw, "topic_search" if query in extra_queries else "owner_search", "search")
                created = _parse_dt(item.get("createdAt"))
                if item["text"] and (not spec or _matches_spec(item["text"], spec)) and (not created or created >= cutoff):
                    tweets.append(item)
        except Exception as exc:
            errors.append(f"search {query[:35]}: {exc}")

    seen = set()
    unique: List[Dict[str, Any]] = []
    for item in tweets:
        keyish = str(item.get("id") or item.get("text"))
        if keyish in seen:
            continue
        seen.add(keyish)
        unique.append(item)
    return unique, errors


def _colorado_relevant(text: str) -> bool:
    terms = set(getattr(pulse, "COLORADO_TEAM_TERMS", set()) or set())
    if not terms:
        terms = {
            "denver",
            "broncos",
            "nuggets",
            "avalanche",
            "avs",
            "rockies",
            "buffs",
            "colorado",
            "jokic",
            "bo nix",
            "sean payton",
        }
    lower = text.lower()
    return any(str(term).lower() in lower for term in terms)


def _tweet_heat(item: Dict[str, Any]) -> float:
    age = item.get("age_hours")
    age_hours = float(age) if isinstance(age, (int, float)) else 12.0
    engagement = (
        float(item.get("replyCount") or 0) * 3.0
        + float(item.get("retweetCount") or 0) * 2.0
        + float(item.get("quoteCount") or 0) * 2.0
        + float(item.get("likeCount") or 0) * 0.15
        + float(item.get("viewCount") or 0) * 0.002
    )
    return engagement + max(0.0, 24.0 - age_hours) * 2.0


def _source_identity(item: Dict[str, Any]) -> str:
    return str(item.get("author") or item.get("source") or item.get("url") or item.get("id") or "")


def _source_tweet_spec_from_decision(decision: Dict[str, Any]) -> Optional[SubjectSpec]:
    for item in _source_basis(decision):
        if not isinstance(item, dict):
            continue
        if item.get("source_type") != "source_tweet" and not item.get("source_url"):
            continue
        source_text = _source_tweet_context(item, str(item.get("source_url") or item.get("url") or ""))
        return _build_subject_spec("", source_text=source_text)
    return None


def _central_focus_hit(text: str, spec: Optional[SubjectSpec]) -> bool:
    if not spec:
        return False
    return _focus_match_score((text or "")[:220], spec) >= 1.0


def _focused_topic_decision(topic: str, tweets: List[Dict[str, Any]], headlines: List[Dict[str, Any]], spec: Optional[SubjectSpec]) -> Optional[Dict[str, Any]]:
    if not spec or spec.ambiguous:
        return None
    focused_tweets = [t for t in tweets if _matches_spec(str(t.get("text") or ""), spec)]
    focused_tweets = sorted(focused_tweets, key=_tweet_heat, reverse=True)
    if len(focused_tweets) < 2:
        return None
    identities = {_source_identity(t) for t in focused_tweets[:6] if _source_identity(t)}
    if len(identities) < 2:
        return None
    if not any(_central_focus_hit(str(t.get("text") or ""), spec) for t in focused_tweets[:6]):
        return None
    source_items = [t for t in focused_tweets if t.get("source_type") == "source_tweet" or t.get("source_url")]
    non_source_items = [t for t in focused_tweets if t not in source_items]
    basis = (source_items[:1] + non_source_items)[:6]
    headline_basis = [h for h in headlines if _matches_spec(str(h.get("text") or h.get("title") or ""), spec)][:2]
    source_basis = basis + headline_basis
    newest = min((b.get("age_hours") for b in basis if isinstance(b.get("age_hours"), (int, float))), default=None)
    label = topic or spec.canonical
    topic_label = _focus_topic_label(label)
    summary = " | ".join(_clean_text(b.get("text"))[:130] for b in basis[:3])
    score = min(96.0, 72.0 + len(basis) * 3.0 + (_tweet_heat(basis[0]) / 20.0))
    confidence = min(96.0, 78.0 + len(basis) * 2.5)
    age_text = f"{newest:.1f}h old" if isinstance(newest, (int, float)) else "fresh"
    return {
        "version": getattr(pulse, "PULSE_VERSION", "unknown"),
        "status": "ready",
        "message": f"Focused Pulse found what Twitter is saying about {label}.",
        "topic": label,
        "brief": (
            f"PULSE OPPORTUNITY:\n{topic_label}\n\n"
            f"WHAT TWITTER IS SAYING:\n{summary}\n\n"
            f"WHY NOW:\n{len(basis)} focused X signals; newest signal {age_text}.\n\n"
            "WRITING CONTRACT:\nWrite original standalone tweets that synthesize the live conversation. "
            "Do not produce generic evergreen analysis."
        ),
        "best": {
            "topic": label,
            "summary_text": summary,
            "sources": ["twitter"],
            "signal_count": len(basis),
            "source_basis": source_basis,
            "score": round(score, 2),
            "confidence": round(confidence, 2),
            "why_now": f"{len(basis)} focused X signals; newest signal {age_text}.",
            "recommended_lane": DEFAULT_LANE,
        },
        "source_basis": source_basis,
        "score": round(score, 2),
        "confidence": round(confidence, 2),
        "recommended_action": "tweet",
        "recommended_lane": DEFAULT_LANE,
        "top_rejected": [],
    }


def _focused_no_op_decision(topic: str, tweets: List[Dict[str, Any]], headlines: List[Dict[str, Any]], spec: Optional[SubjectSpec] = None) -> Dict[str, Any]:
    label = topic or (spec.canonical if spec else "tweet link subject")
    reason = "too ambiguous" if spec and spec.ambiguous else "not enough focused X conversation"
    return {
        "status": "no_op",
        "message": (
            f"Pulse could not find enough focused X conversation for `{label}` right now ({reason}). "
            "No broad/generic drafts were generated."
        ),
        "topic": label,
        "source_basis": [],
        "score": 0,
        "confidence": 0,
        "rejected": [],
        "focused_counts": {"tweets": len(tweets), "headlines": len(headlines)},
    }


def fetch_news_headlines(limit_per_feed: int = 12, topic: str = "", spec: Optional[SubjectSpec] = None) -> Tuple[List[Dict[str, Any]], List[str]]:
    headlines: List[Dict[str, Any]] = []
    errors: List[str] = []
    cutoff = _utc_now() - timedelta(hours=24)
    headers = {"User-Agent": "PostAscendPulse/1.0"}
    feeds = [] if topic else list(OWNER_RSS_FEEDS)
    if topic:
        feeds.insert(0, TOPIC_RSS_TEMPLATE.format(query=urllib.parse.quote_plus(topic)))

    for feed_url in feeds:
        try:
            req = urllib.request.Request(feed_url, headers=headers)
            with urllib.request.urlopen(req, timeout=12) as resp:
                xml_text = resp.read().decode("utf-8", "replace")
            root = ET.fromstring(xml_text)
            for item in root.findall(".//item")[:limit_per_feed]:
                title = _clean_text(item.findtext("title"))
                link = _clean_text(item.findtext("link"))
                pub_date = _clean_text(item.findtext("pubDate"))
                created = _parse_dt(pub_date)
                if not title or (created and created < cutoff):
                    continue
                if spec and not _matches_spec(title, spec):
                    continue
                if not topic and not _colorado_relevant(title):
                    continue
                headlines.append(
                    {
                        "title": title,
                        "text": title,
                        "url": link,
                        "published": pub_date,
                        "createdAt": pub_date,
                        "age_hours": _age_hours(pub_date),
                        "source": "google_news",
                        "source_type": "news",
                    }
                )
        except Exception as exc:
            errors.append(f"rss {feed_url[:55]}: {exc}")

    seen = set()
    unique: List[Dict[str, Any]] = []
    for item in headlines:
        keyish = item.get("title") or item.get("url")
        if keyish in seen:
            continue
        seen.add(keyish)
        unique.append(item)
    return unique, errors


def load_creator_evolution_state(state_path: Path = DEFAULT_STATE_PATH) -> Dict[str, Any]:
    state = ce.initial_state()
    if not state_path.exists():
        return state
    try:
        loaded = json.loads(state_path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            state.update(loaded)
    except Exception:
        return state
    return state


def _payload_from_artifact(path: Path) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _decision_from_artifact(path: Path) -> Optional[Dict[str, Any]]:
    data = _payload_from_artifact(path)
    if not data:
        return None
    decision = data.get("decision")
    return decision if isinstance(decision, dict) else None


def _latest_artifact(artifact_dir: Path) -> Optional[Path]:
    if not artifact_dir.exists():
        return None
    latest = artifact_dir / "latest.json"
    if latest.exists():
        return latest
    files = sorted(artifact_dir.glob("pulse_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def _mock_decision(status: str) -> Dict[str, Any]:
    if status == "error":
        return pulse.pulse_error_decision("mock pulse error")
    if status == "noop":
        return {
            "status": "no_op",
            "message": "No strong Colorado sports pulse found in the mock window.",
            "score": 0,
            "confidence": 0,
            "source_basis": [],
            "rejected": [],
        }
    return {
        "status": "ready",
        "score": 91.4,
        "confidence": 93.0,
        "topic": "Nuggets end-of-season press conference",
        "lane": DEFAULT_LANE,
        "format": DEFAULT_FORMAT,
        "brief": "Nuggets leadership is talking through roster flexibility after the season and the local conversation is focused on whether the same core has enough paths left.",
        "best": {
            "text": "Josh Kroenke says all options are on the table except trading Nikola Jokic.",
            "source": "mock",
            "source_type": "news",
            "age_hours": 0.2,
        },
        "source_basis": [
            {
                "text": "Josh Kroenke says all options are on the table except trading Nikola Jokic.",
                "source_type": "news",
                "age_hours": 0.2,
            }
        ],
        "rejected": [],
    }


def run_pulse_decision(request: PulseRequest, state: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if request.mock:
        decision = _mock_decision(request.mock)
        return decision, {"tweets": 3, "headlines": 2, "errors": []}

    if request.mode in {"drafts", "voice", "format"}:
        source_path = request.decision_path or _latest_artifact(request.artifact_dir)
        if source_path:
            payload = _payload_from_artifact(source_path)
            decision = (payload or {}).get("decision") if isinstance(payload, dict) else None
            if isinstance(decision, dict):
                contract = (payload or {}).get("subject_contract") or {}
                if isinstance(contract, dict):
                    request.topic = request.topic or str(contract.get("topic_query") or "")
                    request.tweet_url = request.tweet_url or str(contract.get("tweet_url") or "")
                    if (
                        not request.tweet_url
                        and not request.topic
                        and str(contract.get("canonical") or "")
                        and str(contract.get("canonical")) != "tweet link subject"
                    ):
                        request.topic = str(contract.get("canonical"))
                return decision, {"tweets": None, "headlines": None, "errors": [], "reused_artifact": str(source_path)}

    tweets, tweet_errors = fetch_twitter_signals(
        request.search_limit,
        request.list_limit,
        topic=request.topic,
        tweet_url=request.tweet_url,
    )
    source_text = ""
    for item in tweets:
        if item.get("source_type") == "source_tweet":
            source_text = _source_tweet_context(item, request.tweet_url)
            break
    spec = _build_subject_spec(request.topic, source_text=source_text if request.tweet_url and not request.topic else "")
    if request.tweet_url and not request.topic:
        headlines, news_errors = [], []
    else:
        headlines, news_errors = fetch_news_headlines(request.rss_limit, topic=request.topic, spec=spec)
    focused_decision = _focused_topic_decision(request.topic, tweets, headlines, spec)
    if focused_decision:
        counts = {"tweets": len(tweets), "headlines": len(headlines), "errors": tweet_errors + news_errors, "focused": True}
        return focused_decision, counts
    if request.topic or request.tweet_url:
        counts = {"tweets": len(tweets), "headlines": len(headlines), "errors": tweet_errors + news_errors, "focused": True}
        return _focused_no_op_decision(request.topic, tweets, headlines, spec), counts
    try:
        decision = pulse.safe_find_pulse(
            tweets=tweets,
            headlines=headlines,
            state=state,
            sports_context="",
            handle="tyler_polumbus",
        )
    except Exception as exc:
        decision = pulse.pulse_error_decision(str(exc))
    counts = {"tweets": len(tweets), "headlines": len(headlines), "errors": tweet_errors + news_errors}
    return decision, counts


def _source_basis(decision: Dict[str, Any], topic: str = "") -> List[Dict[str, Any]]:
    spec = _build_subject_spec(topic)
    basis = decision.get("source_basis")
    if isinstance(basis, list) and basis:
        items = [b for b in basis if isinstance(b, dict)]
        if spec:
            focused = [b for b in items if _matches_spec(str(b.get("text") or b.get("title") or b.get("summary_text") or ""), spec)]
            return focused or items
        return items
    best = decision.get("best")
    if isinstance(best, dict):
        nested = best.get("source_basis")
        if isinstance(nested, list) and nested:
            items = [b for b in nested if isinstance(b, dict)]
            if spec:
                focused = [b for b in items if _matches_spec(str(b.get("text") or b.get("title") or b.get("summary_text") or ""), spec)]
                return focused or items
            return items
        return [best]
    return []


def _decision_topic(decision: Dict[str, Any]) -> str:
    topic = _clean_text(decision.get("topic"))
    if topic:
        return topic
    best = decision.get("best")
    if isinstance(best, dict):
        return _clean_text(best.get("topic"))
    return ""


def _source_material(decision: Dict[str, Any], topic: str = "") -> str:
    parts = [
        "Creator Evolution Pulse source material.",
        "Write original standalone tweets only. Do not write a reply. Do not mention or address a source handle.",
        "Use the facts below as source material, not as text to copy.",
    ]
    if topic:
        parts.extend(
            [
                f"FOCUSED TOPIC: {topic}",
                f"Every draft must be centered on {topic}. Do not drift into adjacent players, lineups, opponents, or the broader game unless that detail directly explains the focused topic.",
            ]
        )
    for key in ("topic", "brief", "message"):
        value = _clean_text(decision.get(key))
        if value:
            parts.append(f"{key.title()}: {value}")
    for idx, item in enumerate(_source_basis(decision, topic=topic)[:5], 1):
        text = _clean_text(item.get("text") or item.get("title"))
        if not text:
            continue
        source = _clean_text(item.get("source") or item.get("source_type") or "source")
        age = item.get("age_hours")
        age_text = f", age {age:.1f}h" if isinstance(age, (int, float)) else ""
        parts.append(f"Source {idx} ({source}{age_text}): {text}")
    return "\n".join(parts)


def _extract_json(raw: str) -> Dict[str, Any]:
    raw = raw.strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    if fenced:
        try:
            data = json.loads(fenced.group(1))
            return data if isinstance(data, dict) else {}
        except Exception:
            pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(raw[start : end + 1])
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _call_local_proxy(prompt: str, system_prompt: str, timeout_seconds: int) -> Tuple[Optional[Dict[str, Any]], str]:
    body = json.dumps(
        {
            "prompt": prompt,
            "system": system_prompt,
            "model": "claude-sonnet-4-6",
            "max_tokens": 1800,
        }
    ).encode("utf-8")
    key_candidates = _proxy_key_candidates() or [""]
    last_error = "local proxy unavailable"
    for key in key_candidates:
        headers = {"Content-Type": "application/json"}
        if key:
            headers["X-Proxy-Key"] = key
        req = urllib.request.Request(f"{LOCAL_PROXY_URL}/call", data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
            text = _clean_text(data.get("text"))
            if text:
                parsed = _extract_json(text)
                if parsed:
                    return parsed, text[:600]
                last_error = text[:600]
        except Exception as exc:
            last_error = str(exc)[:600]
            continue
    return None, last_error


def _call_claude(prompt: str, system_prompt: str, timeout_seconds: int) -> Tuple[Optional[Dict[str, Any]], str]:
    proxy_data, proxy_preview = _call_local_proxy(prompt, system_prompt, min(timeout_seconds, 70))
    if proxy_data:
        return proxy_data, proxy_preview
    cli = HQ_ROOT / "scripts" / "claude-cli"
    if not cli.exists():
        return None, f"proxy: {proxy_preview} | claude-cli not found"
    env = os.environ.copy()
    env.pop("ANTHROPIC_API_KEY", None)
    full_prompt = f"{system_prompt}\n\n{prompt}".strip()
    try:
        proc = subprocess.run(
            [str(cli), "-p", "--model", "sonnet"],
            input=full_prompt,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            cwd=str(HQ_ROOT),
            env=env,
        )
    except Exception as exc:
        return None, f"proxy: {proxy_preview} | cli: {exc}"
    raw = (proc.stdout or "").strip()
    if proc.returncode != 0:
        return None, f"proxy: {proxy_preview} | cli: {(proc.stderr or raw or f'claude-cli exited {proc.returncode}')[:600]}"
    data = _extract_json(raw)
    if not data:
        return None, f"proxy: {proxy_preview} | cli non-json: {raw[:600] or 'model returned no JSON'}"
    return data, raw[:600]


def _first_sentence(text: str) -> str:
    text = _clean_text(text)
    if not text:
        return ""
    split = re.split(r"(?<=[.!?])\s+", text)
    return split[0].strip()


def _clean_source_sentence(text: str) -> str:
    text = re.sub(r"https?://\S+", "", _clean_text(text))
    text = re.sub(r"@([A-Za-z0-9_]+)", r"\1", text)
    text = re.sub(r"#([A-Za-z0-9_]+)", r"\1", text)
    text = re.sub(r"[•·]", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" |,-")
    return text


def _source_sentence_issues(text: str) -> List[str]:
    stripped = _clean_source_sentence(text)
    lower = stripped.lower()
    issues: List[str] = []
    if len(stripped) < 45:
        issues.append("source sentence too short")
    if lower.startswith(("begs the question", "check out ", "for sale", "rt ")):
        issues.append("source sentence is not a clean news/social signal")
    if re.search(r"\bwhy\s+(?:didn['’]?t|doesn['’]?t|wouldn['’]?t)\s+\w+", lower) and not re.search(
        r"\bwhy\s+\w+\s+(?:didn['’]?t|doesn['’]?t|wouldn['’]?t)\s+\w+",
        lower,
    ):
        issues.append("source sentence is missing the actor")
    if re.search(r"\bwhat\s+happe?$", lower):
        issues.append("source sentence appears truncated")
    if len(re.findall(r"[?!]", stripped)) > 2:
        issues.append("source sentence is too noisy")
    return issues


def _source_specific_terms(decision: Dict[str, Any], topic: str = "") -> List[str]:
    stop = {
        "about",
        "after",
        "available",
        "broncoscountry",
        "colorado",
        "denver",
        "first",
        "from",
        "game",
        "have",
        "into",
        "joining",
        "learn",
        "mindset",
        "more",
        "news",
        "right",
        "said",
        "setting",
        "source",
        "sports",
        "standard",
        "starts",
        "public",
        "answer",
        "moment",
        "offseason",
        "quietly",
        "actual",
        "signal",
        "that",
        "their",
        "there",
        "this",
        "tweet",
        "with",
    }
    terms: List[str] = []
    for item in _source_basis(decision, topic=topic)[:5]:
        text = _clean_source_sentence(str(item.get("text") or item.get("title") or item.get("summary_text") or ""))
        for phrase in re.findall(r"\b[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){1,2}\b", text):
            low = phrase.lower()
            if low not in terms:
                terms.append(low)
        for word in re.findall(r"[A-Za-z][A-Za-z0-9'-]{4,}", text):
            low = word.lower().strip("'")
            if low not in stop and low not in terms:
                terms.append(low)
        if len(terms) >= 18:
            break
    return terms[:18]


def _has_source_specificity(text: str, decision: Dict[str, Any], topic: str = "") -> bool:
    lower = (text or "").lower()
    if any(
        phrase in lower
        for phrase in (
            "this denver sports moment",
            "this sports moment",
            "the public answer",
            "the real offseason starts",
            "every move after it",
        )
    ):
        return False
    terms = _source_specific_terms(decision, topic=topic)
    if not terms:
        return True
    phrase_terms = [term for term in terms if " " in term]
    if any(_term_in_text(term, lower) for term in phrase_terms):
        return True
    hits = sum(1 for term in terms if _term_in_text(term, lower))
    return hits >= 2


def _fallback_drafts(decision: Dict[str, Any], lane: str, fmt: str) -> Dict[str, Any]:
    topic = _decision_topic(decision)
    basis = _source_basis(decision, topic=topic)
    clean_basis = [
        _clean_source_sentence(_first_sentence(item.get("text") or item.get("title") or item.get("summary_text") or ""))
        for item in basis
        if not _source_sentence_issues(str(item.get("text") or item.get("title") or item.get("summary_text") or ""))
    ]
    base = (clean_basis[0] if clean_basis else "") or _clean_text(decision.get("brief"))
    topic = topic or "Pulse"
    if not base:
        base = topic
    second = clean_basis[1] if len(clean_basis) > 1 else ""
    third = clean_basis[2] if len(clean_basis) > 2 else ""
    option1 = (
        f"{base}\n\n"
        "That matters because the clean public line usually hides the decision pressure sitting underneath it..."
    )
    option2 = (
        f"{second or base}\n\n"
        "That is not a throwaway note. It tells you which part of the room is carrying the pressure right now..."
    )
    option3 = (
        f"{third or base}\n\n"
        "The interesting part is not the headline. It is what this says about the next decision that has to be made..."
    )
    return {
        "option1": option1,
        "option1_pattern": f"{fmt} / {lane} fallback: source observation plus decision tension",
        "option2": option2,
        "option2_pattern": f"{fmt} / {lane} fallback: topic frame plus open consequence",
        "option3": option3,
        "option3_pattern": f"{fmt} / {lane} fallback: concrete fact plus unresolved implication",
        "pick": "1",
        "pick_reason": "Most specific to the selected Pulse source basis.",
        "fallback_used": True,
    }


def _contract_issues(text: str) -> List[str]:
    issues: List[str] = []
    stripped = text.strip()
    lower = stripped.lower()
    if stripped.startswith("@"):
        issues.append("starts with a handle/reply marker")
    if re.search(r"(^|\s)@\w+", stripped):
        issues.append("contains an unsupported handle")
    if "#" in stripped:
        issues.append("contains hashtag")
    if any(term in lower for term in BLOCKED_DRAFT_TERMS):
        issues.append("contains diagnostic, betting, or meta language")
    if "http://" in lower or "https://" in lower:
        issues.append("contains a source link instead of an original standalone tweet")
    if len(stripped) > 280 and "Thread" not in stripped:
        issues.append("exceeds normal tweet length")
    return issues


def _finalize_drafts(
    data: Dict[str, Any],
    decision: Dict[str, Any],
    lane: str,
    fmt: str,
    state: Dict[str, Any],
    topic: str = "",
    spec_override: Optional[SubjectSpec] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    quality: Dict[str, Any] = {"options": {}, "accepted": 0, "rejected": []}
    spec = spec_override or _build_subject_spec(topic)
    specificity_topic = topic or _decision_topic(decision)
    options_payload = {
        key: value
        for key, value in data.items()
        if key.startswith("option") or key in {"pick", "pick_reason"}
    }
    try:
        validation = ce.validate_generation_options(options_payload, fmt, lane)
    except Exception as exc:
        validation = {"valid": False, "error": str(exc)}
    quality["validation"] = validation

    drafts: List[Dict[str, Any]] = []
    for idx in range(1, 4):
        text = _clean_text(data.get(f"option{idx}"))
        if not text:
            continue
        issues = _contract_issues(text)
        if spec and not _matches_spec(text, spec):
            issues.append(f"drifts away from focused topic: {topic}")
        if not _has_source_specificity(text, decision, topic=specificity_topic):
            issues.append("too vague: missing concrete source detail from selected Pulse signal")
        try:
            report = ce.draft_quality_report(text, fmt, lane)
        except Exception as exc:
            report = {"error": str(exc)}
        quality["options"][str(idx)] = {"issues": issues, "report": report, "pattern": data.get(f"option{idx}_pattern", "")}
        if issues:
            quality["rejected"].append({"index": idx, "issues": issues})
            continue
        drafts.append(
            {
                "text": text,
                "type": "pulse",
                "lane": lane,
                "format": fmt,
                "source": "creator_evolution_pulse",
                "pattern": _clean_text(data.get(f"option{idx}_pattern")),
                "quality": report,
            }
        )

    if topic and len(drafts) < 2:
        quality["focused_topic_insufficient_valid_drafts"] = True
        quality["accepted"] = len(drafts)
        return drafts, quality

    if len(drafts) < 2:
        fallback = _fallback_drafts(decision, lane, fmt)
        for idx in range(1, 4):
            text = _clean_text(fallback.get(f"option{idx}"))
            issues = _contract_issues(text)
            if _source_sentence_issues(text.split("\n", 1)[0]):
                issues.append("fallback source sentence is not clean enough to post")
            if text and not issues and _has_source_specificity(text, decision, topic=specificity_topic):
                drafts.append(
                    {
                        "text": text,
                        "type": "pulse",
                        "lane": lane,
                        "format": fmt,
                        "source": "creator_evolution_pulse_fallback",
                        "pattern": _clean_text(fallback.get(f"option{idx}_pattern")),
                        "quality": {"fallback": True},
                    }
                )
            elif text:
                quality["rejected"].append({"index": f"fallback{idx}", "issues": issues or ["fallback failed specificity"]})
        quality["fallback_used"] = True

    unique: List[Dict[str, Any]] = []
    seen_texts = set()
    for draft in drafts:
        text = _clean_text(draft.get("text"))
        key = text.lower()
        if not text or key in seen_texts:
            continue
        seen_texts.add(key)
        unique.append(draft)
    quality["accepted"] = len(unique[:3])
    return unique[:3], quality


def generate_drafts(decision: Dict[str, Any], request: PulseRequest, state: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Dict[str, Any], str]:
    if decision.get("status") != "ready":
        return [], {"accepted": 0, "skipped": decision.get("status")}, ""
    lane = request.lane or decision.get("lane") or DEFAULT_LANE
    fmt = request.fmt or decision.get("format") or DEFAULT_FORMAT
    focus_topic = request.topic or (str(decision.get("topic") or "") if request.tweet_url else "")
    spec_override = _source_tweet_spec_from_decision(decision) if request.tweet_url else None
    if request.mock == "ready":
        data = _fallback_drafts(decision, lane, fmt)
        drafts, quality = _finalize_drafts(data, decision, lane, fmt, state, topic=focus_topic, spec_override=spec_override)
        quality["mock_ready"] = True
        return drafts, quality, json.dumps(data, ensure_ascii=False)
    source = _source_material(decision, topic=focus_topic)
    prompt = ce.build_generation_prompt(source, fmt, lane, state, action="build")
    prompt += (
        "\n\nPULSE DISCORD CONTRACT:\n"
        "- Write original standalone tweets only.\n"
        "- Do not write a reply, do not start with a handle, and do not include source links.\n"
        "- Do not include betting language, odds, parlay language, or diagnostic labels.\n"
        "- Return valid JSON only with option1, option1_pattern, option2, option2_pattern, option3, option3_pattern, pick, and pick_reason.\n"
    )
    system_prompt = "You are Creator Evolution Pulse. Use the shared Creator Evolution voice, format, and quality rules exactly."
    data, raw_preview = _call_claude(prompt, system_prompt, request.timeout_seconds)
    if not data:
        if request.topic or request.tweet_url:
            return [], {"accepted": 0, "ai_unavailable": True, "error": raw_preview}, f"ai_unavailable: {raw_preview}"
        data = _fallback_drafts(decision, lane, fmt)
        raw_preview = f"fallback: {raw_preview}"
    drafts, quality = _finalize_drafts(data, decision, lane, fmt, state, topic=focus_topic, spec_override=spec_override)
    if data.get("fallback_used"):
        quality["fallback_used"] = True
    return drafts, quality, raw_preview


def save_artifact(payload: Dict[str, Any], artifact_dir: Path = DEFAULT_ARTIFACT_DIR) -> Path:
    artifact_dir.mkdir(parents=True, exist_ok=True)
    request_id = payload.get("request_id") or _request_id()
    path = artifact_dir / f"{request_id}.json"
    payload["artifact_path"] = str(path)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    latest = artifact_dir / "latest.json"
    latest.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def run_pulse(request: PulseRequest) -> Dict[str, Any]:
    if not request.request_id:
        request.request_id = _request_id(request.mode)
    state = load_creator_evolution_state(request.state_path)
    decision, counts = run_pulse_decision(request, state)
    decision["selected_lane"] = request.lane
    decision["selected_format"] = request.fmt
    drafts: List[Dict[str, Any]] = []
    quality: Dict[str, Any] = {}
    raw_preview = ""
    focus_topic = request.topic or (str(decision.get("topic") or "") if request.tweet_url else "")
    if request.generate_drafts and decision.get("status") == "ready":
        drafts, quality, raw_preview = generate_drafts(decision, request, state)
        if not drafts and quality.get("ai_unavailable"):
            decision["status"] = "pulse_error"
            decision["message"] = "Pulse found focused sources, but AI drafting is unavailable. No generic fallback drafts were posted."
        elif focus_topic and len(drafts) < 2:
            decision["status"] = "pulse_error"
            decision["message"] = "Pulse found focused sources, but drafting did not produce enough focused tweets. No generic fallback drafts were posted."
            drafts = []
        elif len(drafts) < 2:
            decision["status"] = "no_op"
            decision["message"] = "Pulse found sources, but fewer than two clean, source-specific drafts survived quality gates. Nothing was posted."
            drafts = []
    payload = {
        "status": decision.get("status", "pulse_error"),
        "message": decision.get("message", ""),
        "request_id": request.request_id,
        "created_at": request.created_at,
        "selected_lane": request.lane,
        "selected_format": request.fmt,
        "topic_query": request.topic,
        "tweet_url": request.tweet_url,
        "subject_contract": _subject_contract(request.topic, request.tweet_url, decision),
        "versions": {
            "service": PULSE_SERVICE_VERSION,
            "pulse": getattr(pulse, "PULSE_VERSION", "unknown"),
            "creator_evolution": getattr(ce, "CREATOR_EVOLUTION_VERSION", "unknown"),
        },
        "counts": counts,
        "decision": decision,
        "source_basis": _source_basis(decision, topic=focus_topic),
        "drafts": drafts,
        "quality_reports": quality,
        "raw_preview": raw_preview,
    }
    save_artifact(payload, request.artifact_dir)
    return payload


def payload_for_status(artifact_dir: Path = DEFAULT_ARTIFACT_DIR) -> Dict[str, Any]:
    latest = _latest_artifact(artifact_dir)
    if not latest:
        return {"status": "no_op", "message": "No Pulse run artifact found yet.", "artifact": None}
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "pulse_error", "message": f"Could not read latest Pulse artifact: {exc}", "artifact": str(latest)}
    decision = data.get("decision") or {}
    best = decision.get("best") if isinstance(decision.get("best"), dict) else {}
    return {
        "status": "ready",
        "message": "Latest Pulse artifact loaded.",
        "artifact": str(latest),
        "request_id": data.get("request_id"),
        "created_at": data.get("created_at"),
        "selected_lane": data.get("selected_lane"),
        "selected_format": data.get("selected_format"),
        "draft_count": len(data.get("drafts") or []),
        "pulse_status": data.get("status"),
        "subject_contract": data.get("subject_contract") or {},
        "topic_query": data.get("topic_query"),
        "tweet_url": data.get("tweet_url"),
        "last_error": data.get("message") if data.get("status") == "pulse_error" else "",
        "score": decision.get("score") if decision.get("score") is not None else best.get("score"),
        "confidence": decision.get("confidence") if decision.get("confidence") is not None else best.get("confidence"),
    }


def payload_for_why(artifact_dir: Path = DEFAULT_ARTIFACT_DIR) -> Dict[str, Any]:
    latest = _latest_artifact(artifact_dir)
    if not latest:
        return {"status": "no_op", "message": "No Pulse run artifact found yet.", "artifact": None}
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "pulse_error", "message": f"Could not read latest Pulse artifact: {exc}", "artifact": str(latest)}
    decision = data.get("decision") or {}
    best = decision.get("best") if isinstance(decision.get("best"), dict) else {}
    return {
        "status": "ready",
        "message": "Pulse why loaded.",
        "artifact": str(latest),
        "request_id": data.get("request_id"),
        "counts": data.get("counts"),
        "score": decision.get("score") if decision.get("score") is not None else best.get("score"),
        "confidence": decision.get("confidence") if decision.get("confidence") is not None else best.get("confidence"),
        "source_basis": data.get("source_basis") or [],
        "rejected": decision.get("rejected") or decision.get("rejected_signals") or [],
        "quality_reports": data.get("quality_reports") or {},
    }


def payload_for_source(artifact_dir: Path = DEFAULT_ARTIFACT_DIR) -> Dict[str, Any]:
    latest = _latest_artifact(artifact_dir)
    if not latest:
        return {"status": "no_op", "message": "No Pulse run artifact found yet.", "artifact": None}
    try:
        data = json.loads(latest.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "pulse_error", "message": f"Could not read latest Pulse artifact: {exc}", "artifact": str(latest)}
    decision = data.get("decision") if isinstance(data.get("decision"), dict) else {}
    return {
        "status": "ready",
        "message": "Pulse source basis loaded.",
        "artifact": str(latest),
        "request_id": data.get("request_id"),
        "topic_query": data.get("topic_query"),
        "tweet_url": data.get("tweet_url"),
        "subject_contract": data.get("subject_contract") or {},
        "source_basis": data.get("source_basis") or [],
        "rejected": decision.get("rejected") or decision.get("rejected_signals") or [],
        "quality_reports": data.get("quality_reports") or {},
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run headless Creator Evolution Pulse.")
    parser.add_argument("--mode", default="run", choices=["run", "refresh", "drafts", "voice", "format", "why", "source", "status"])
    parser.add_argument("--lane", default=DEFAULT_LANE)
    parser.add_argument("--format", dest="fmt", default=DEFAULT_FORMAT)
    parser.add_argument("--request-id", default="")
    parser.add_argument("--state-path", default=str(DEFAULT_STATE_PATH))
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    parser.add_argument("--decision-file", default="")
    parser.add_argument("--topic", default="")
    parser.add_argument("--tweet-url", default="")
    parser.add_argument("--mock", choices=["", "ready", "noop", "error"], default="")
    parser.add_argument("--no-drafts", action="store_true")
    args = parser.parse_args(argv)

    artifact_dir = Path(args.artifact_dir)
    if args.mode == "status":
        print(json.dumps(payload_for_status(artifact_dir), ensure_ascii=False))
        return 0
    if args.mode == "why":
        print(json.dumps(payload_for_why(artifact_dir), ensure_ascii=False))
        return 0
    if args.mode == "source":
        print(json.dumps(payload_for_source(artifact_dir), ensure_ascii=False))
        return 0

    request = PulseRequest(
        mode=args.mode,
        lane=args.lane,
        fmt=args.fmt,
        request_id=args.request_id,
        state_path=Path(args.state_path),
        artifact_dir=artifact_dir,
        decision_path=Path(args.decision_file) if args.decision_file else None,
        topic=args.topic,
        tweet_url=args.tweet_url,
        mock=args.mock,
        force_refresh=args.mode == "refresh",
        generate_drafts=not args.no_drafts,
    )
    payload = run_pulse(request)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
