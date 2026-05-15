"""Import-safe Creator Evolution public X action-profile heuristics.

The live X ranking weights are not public. This module models public ranking
shape as retrieval, candidate clarity, multi-action intent, safety, dwell, and
voice fit without claiming fixed production multipliers.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import re
from typing import Any


PUBLIC_X_POSITIVE_ACTIONS = (
    "reply", "quote", "repost", "share", "dwell",
    "profile_click", "follow", "click", "photo_expand", "video_view",
)
PUBLIC_X_NEGATIVE_ACTIONS = ("not_interested", "block_author", "mute_author", "report", "not_dwelled")

DENVER_ENTITY_TERMS = (
    "broncos", "denver broncos", "bo nix", "sean payton", "courtland sutton", "pat surtain",
    "nuggets", "denver nuggets", "jokic", "nikola jokic", "jamal murray", "aaron gordon",
    "christian braun", "michael porter", "calvin booth", "josh kroenke",
    "avalanche", "colorado avalanche", "avs", "mackinnon", "nathan mackinnon", "makar",
    "cale makar", "blackwood", "wedgwood", "wedgewood", "rockies", "colorado rockies",
    "buffs", "cu buffs", "colorado buffaloes", "coach prime", "deion", "deion sanders",
    "denver sports", "colorado sports", "altitude sports",
)
SPORTS_MECHANISM_TERMS = (
    "roster", "rotation", "bench", "starter", "lineup", "goalie", "quarterback", "qb",
    "camp", "draft", "trade", "contract", "extension", "injury", "press conference",
    "presser", "series", "playoff", "scheme", "front office", "ownership", "reps",
    "minutes", "matchup", "depth chart", "practice", "timeout", "substitution",
    "possession", "crease", "offensive line", "defense", "play calling",
    "non-jokic minutes", "non jokic minutes", "second unit",
)
TENSION_TERMS = (
    "why", "because", "means", "shows", "changes", "forces", "tests", "decides",
    "pressure", "trust", "problem", "choice", "answer", "proof", "leverage",
    "gap", "tension", "risk", "consequence",
)
GENERIC_AI_FRAMES = (
    "the important part is not the headline", "where it gets interesting", "where it gets weird",
    "the first reaction is easy", "the sharper read is", "that is where", "this is where",
    "the useful read is", "the surface version is simple",
)
ENGAGEMENT_BAIT_FRAMES = (
    "thoughts?", "what do you think?", "agree?", "am i wrong?", "prove me wrong",
    "drop your", "reply with", "tell me why", "comment below",
)
DIRECT_INSULT_TERMS = ("idiot", "idiots", "moron", "morons", "clown", "clowns", "trash", "garbage", "stupid", "fraud", "frauds", "loser", "losers", "bum", "bums", "coward", "cowards", "pathetic")
_HEATED_LANES = {"annoyed", "fired-up", "fired up", "critical", "sarcastic"}


def _clamp(value: float | int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, int(round(float(value)))))


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").replace("\r", " ").strip())


def _contains_term(text: str, term: str) -> bool:
    term = normalize_text(term).lower()
    hay = normalize_text(text).lower()
    if not term:
        return False
    if " " in term or "-" in term:
        return term in hay or term.replace("-", " ") in hay
    return bool(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", hay))


def _first_hit(text: str, terms: tuple[str, ...]) -> str:
    hits = [term for term in terms if _contains_term(text, term)]
    return max(hits, key=lambda term: (len(term.split()), len(term))) if hits else ""


def candidate_anchor(text: str) -> str:
    clean = normalize_text(text)
    for scope in (clean[:180], clean):
        entity = _first_hit(scope, DENVER_ENTITY_TERMS)
        if entity:
            return entity
        proper = [p for p in re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b", scope) if p.lower() not in {"the", "this", "that"}]
        if proper:
            return proper[0].strip()
        mechanism = _first_hit(scope, SPORTS_MECHANISM_TERMS)
        if mechanism:
            return mechanism
    return ""


def primary_sports_mechanism(text: str) -> str:
    return _first_hit(normalize_text(text)[:220], SPORTS_MECHANISM_TERMS)


def _has_tension(text: str) -> bool:
    return bool(_first_hit(normalize_text(text)[:220], TENSION_TERMS))


def _generic_frame_hit(text: str) -> str:
    return _first_hit(text, GENERIC_AI_FRAMES)


def _engagement_bait_hit(text: str) -> str:
    return _first_hit(text, ENGAGEMENT_BAIT_FRAMES)


def _insult_hit(text: str) -> str:
    return _first_hit(text, DIRECT_INSULT_TERMS)


def retrieval_anchor_fit(text: str) -> int:
    clean = normalize_text(text)
    score = 30
    anchor = candidate_anchor(clean)
    mechanism = primary_sports_mechanism(clean)
    if anchor:
        score += 35
    if mechanism:
        score += 20
    if _has_tension(clean[:220]):
        score += 10
    if anchor and mechanism:
        score += 5
    if re.match(r"^(this|that|it|they)\b", clean, flags=re.I) and not anchor:
        score -= 20
    if _generic_frame_hit(clean[:120]):
        score -= 10
    return _clamp(score)


def out_of_network_readability(text: str) -> int:
    clean = normalize_text(text)
    first = clean[:180]
    score = 42
    anchor = candidate_anchor(first)
    mechanism = primary_sports_mechanism(first)
    if anchor:
        score += 24
    if mechanism:
        score += 18
    if _has_tension(first):
        score += 12
    if re.match(r"^(this|that|it|they)\b", clean, flags=re.I) and not anchor:
        score -= 22
    if _generic_frame_hit(first) or "this matters" in first.lower():
        score -= 14
    if len(first) < 55:
        score -= 8
    if not anchor and not mechanism:
        score -= 25
    if _contains_term(first, "avs") and not any(_contains_term(first, t) for t in ("avalanche", "hockey", "goalie", "crease", "mackinnon", "makar")):
        score -= 10
    return _clamp(score)


def infer_target_action(text: str, lane: str, fmt: str, source_type: str = "") -> str:
    lower = normalize_text(" ".join([text, lane, fmt, source_type])).lower()
    lane_l = normalize_text(lane).lower()
    fmt_l = normalize_text(fmt).lower()
    if "promo" in lane_l or any(term in lower for term in ("video", "youtube", "breakdown", "watch")):
        return "click"
    if "article" in fmt_l or "article companion" in lower:
        return "click" if any(term in lower for term in ("click", "profile", "read", "video")) else "dwell"
    if lane_l in {"comedic", "sarcastic", "deadpan"}:
        return "quote"
    if lane_l in {"celebratory", "fired-up", "fired up"}:
        return "repost"
    if "long tweet" in fmt_l:
        return "dwell"
    if "thread" in fmt_l:
        return "reply" if _engagement_bait_hit(text) else "dwell"
    if lane_l in {"witty edge", "skeptical", "critical", "annoyed"}:
        if any(_contains_term(lower, term) for term in ("decision", "pressure", "trust", "problem", "choice", "process")):
            return "reply"
        return "dwell"
    return "dwell"


def positive_action_fit(text: str, lane: str, fmt: str, target_action: str) -> int:
    score = 55
    lane_l = normalize_text(lane).lower()
    fmt_l = normalize_text(fmt).lower()
    target = target_action if target_action in PUBLIC_X_POSITIVE_ACTIONS else infer_target_action(text, lane, fmt)
    if target == "quote" and lane_l in {"comedic", "sarcastic", "deadpan"}:
        score += 15
    if target == "repost" and lane_l in {"celebratory", "fired-up", "fired up"}:
        score += 15
    if target in {"reply", "dwell"} and lane_l in {"witty edge", "skeptical", "critical", "annoyed"}:
        score += 12
    if target == "click" and lane_l == "promo":
        score += 18
    if target == "dwell" and any(x in fmt_l for x in ("long", "thread", "article")):
        score += 14
    if candidate_anchor(text):
        score += 8
    if _has_tension(text):
        score += 8
    if _engagement_bait_hit(text):
        score -= 12
    if len(set(a for a in PUBLIC_X_POSITIVE_ACTIONS if a in normalize_text(text).lower())) >= 3:
        score -= 10
    return _clamp(score)


def negative_signal_risk(text: str, lane: str = "") -> tuple[int, str]:
    clean = normalize_text(text)
    lower = clean.lower()
    risk = 8
    reasons: list[str] = []
    insult = _insult_hit(clean)
    if insult:
        risk += 34
        reasons.append("direct insult language")
    if _engagement_bait_hit(clean):
        risk += 18
        reasons.append("engagement bait")
    if not candidate_anchor(clean):
        risk += 16
        reasons.append("weak candidate anchor")
    if out_of_network_readability(clean) < 45:
        risk += 14
        reasons.append("weak out-of-network readability")
    if _generic_frame_hit(clean):
        risk += 16
        reasons.append("generic AI frame")
    if normalize_text(lane).lower() in _HEATED_LANES and insult:
        risk += 28
        reasons.append("heated lane plus personal wording")
    if any(term in lower for term in ("kill yourself", "die", "cripple", "family")):
        risk += 40
        reasons.append("cruelty")
    if any(term in lower for term in ("everyone knows", "if you know you know", "iykyk")):
        risk += 10
        reasons.append("insider-only wording")
    if re.search(r"\b\d{2,3}%\b", clean) and not re.search(r"\b(source|reported|espn|nba|nfl|nhl|mlb)\b", lower):
        risk += 8
        reasons.append("invented-looking specificity")
    return _clamp(risk), (reasons[0] if reasons else "low risk")


def not_dwelled_risk(text: str, fmt: str = "Normal Tweet") -> tuple[int, str]:
    clean = normalize_text(text)
    risk = 18
    reason = "low risk"
    if not candidate_anchor(clean):
        risk += 22
        reason = "no candidate anchor"
    if not primary_sports_mechanism(clean) and not _has_tension(clean):
        risk += 18
        reason = "no tension or mechanism"
    if _generic_frame_hit(clean):
        risk += 18
        reason = "generic setup phrase dominates"
    if len(clean) < 70 and fmt != "Punchy Tweet":
        risk += 16
        reason = "too short for selected format"
    first_sentence = re.split(r"[.!?]\s+", clean, 1)[0]
    if first_sentence and not candidate_anchor(first_sentence) and not primary_sports_mechanism(first_sentence):
        risk += 12
        reason = "first sentence gives no reason to continue"
    if fmt == "Long Tweet" and len(clean) > 320 and len(re.findall(r"\b(because|but|then|means|forces|changes)\b", clean.lower())) < 2:
        risk += 12
        reason = "long tweet lacks escalation"
    if fmt == "Thread" and retrieval_anchor_fit(clean.split("---TWEET---", 1)[0]) < 55:
        risk += 18
        reason = "thread root is weak"
    return _clamp(risk), reason


def voice_fit_proxy(text: str, lane: str, fmt: str = "Normal Tweet") -> int:
    score = 58
    if primary_sports_mechanism(text):
        score += 14
    target = infer_target_action(text, lane, fmt)
    score += max(0, positive_action_fit(text, lane, fmt, target) - 60) // 3
    if _generic_frame_hit(text):
        score -= 14
    if _engagement_bait_hit(text):
        score -= 12
    if _insult_hit(text):
        score -= 10
    if re.search(r"[;:()\[\]{}]", text):
        score -= 8
    return _clamp(score)


def _risk_label(risk: int) -> str:
    return "high" if risk >= 70 else "medium" if risk >= 45 else "low"


def public_x_draft_report(text: str, fmt: str = "Normal Tweet", lane: str = "Witty Edge", source_text: str = "") -> dict[str, Any]:
    clean = normalize_text(text)
    retrieval = retrieval_anchor_fit(clean)
    oon = out_of_network_readability(clean)
    target = infer_target_action(clean, lane, fmt, source_text)
    action_fit = positive_action_fit(clean, lane, fmt, target)
    negative_risk, negative_reason = negative_signal_risk(clean, lane)
    dwell_risk, dwell_reason = not_dwelled_risk(clean, fmt)
    voice = voice_fit_proxy(clean, lane, fmt)
    candidate_fit = _clamp((retrieval * 0.58) + (oon * 0.28) + (action_fit * 0.14))
    total = _clamp(retrieval * 0.28 + action_fit * 0.24 + (100 - negative_risk) * 0.22 + oon * 0.14 + (100 - dwell_risk) * 0.08 + voice * 0.04)
    return {
        "total": total,
        "candidate_anchor": candidate_anchor(clean),
        "sports_mechanism": primary_sports_mechanism(clean),
        "candidate_fit": candidate_fit,
        "retrieval_fit": retrieval,
        "oon_readability": oon,
        "out_of_network_readability": oon,
        "target_action": target,
        "positive_action_fit": action_fit,
        "negative_signal_risk": negative_risk,
        "negative_signal_reason": negative_reason,
        "not_dwelled_risk": dwell_risk,
        "not_dwelled_reason": dwell_reason,
        "voice_fit_proxy": voice,
        "negative_risk_label": _risk_label(negative_risk),
    }


def source_confidence_from_basis(source_basis: list | None) -> int:
    basis = [b for b in (source_basis or []) if isinstance(b, dict)]
    if not basis:
        return 20
    score = 35 + min(30, len(basis) * 8)
    source_blob = " ".join(str(b.get("source", "")) for b in basis).lower()
    if any(s in source_blob for s in ("espn", "news", "ap", "the athletic", "denver post")):
        score += 16
    if "sports_context" in source_blob:
        score += 12
    if any(s in source_blob for s in ("twitter", "x", "trusted_list")):
        score += 8
    if len(basis) == 1 and len(normalize_text(basis[0].get("text", ""))) < 80:
        score -= 18
    return _clamp(score)


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def source_freshness_from_basis(source_basis: list | None) -> int:
    basis = [b for b in (source_basis or []) if isinstance(b, dict)]
    if not basis:
        return 30
    statuses = " ".join(str(b.get("freshness_status", "")) for b in basis).lower()
    if "fresh" in statuses:
        return 88
    if "usable" in statuses:
        return 72
    ages = []
    now = datetime.now(timezone.utc)
    for b in basis:
        if isinstance(b.get("age_hours"), (int, float)):
            ages.append(float(b.get("age_hours")))
            continue
        dt = _parse_dt(b.get("createdAt") or b.get("created_at") or b.get("publishedAt") or b.get("published_at"))
        if dt:
            ages.append(max(0.0, (now - (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc))).total_seconds() / 3600.0))
    return _clamp(95 - min(ages) * 3.5) if ages else 55


def source_triangulation_bonus(source_basis: list | None) -> int:
    basis = [b for b in (source_basis or []) if isinstance(b, dict)]
    source_blob = " ".join(str(b.get("source", "")) for b in basis).lower()
    has_x = any(s in source_blob for s in ("twitter", "x", "trusted_list"))
    has_news = any(s in source_blob for s in ("news", "rss", "ap", "denver post", "the athletic"))
    has_espn = "espn" in source_blob
    has_sports = "sports_context" in source_blob
    if len({str(b.get("source") or b.get("url") or b.get("id") or i) for i, b in enumerate(basis)}) >= 3:
        return 16
    if has_x and has_espn:
        return 12
    if has_x and has_news:
        return 10
    if has_news and has_sports:
        return 8
    return 0


def opportunity_moment_key(text: str) -> str:
    terms = re.findall(r"[a-z0-9]+", normalize_text(text).lower())[:16]
    base = "|".join([candidate_anchor(text), primary_sports_mechanism(text), " ".join(terms)])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16]


def recommended_lane_for_opportunity(text: str, current_lane: str = "Witty Edge") -> str:
    lower = normalize_text(text).lower()
    risk, _ = negative_signal_risk(text, current_lane)
    if any(term in lower for term in ("video", "youtube", "watch", "breakdown")):
        return "Promo"
    if any(term in lower for term in ("absurd", "funny", "weird", "meme", "meltdown")) and risk < 70:
        return "Comedic"
    if any(term in lower for term in ("win", "clutch", "extension", "signed", "momentum", "positive")):
        return "Celebratory" if risk < 55 else "Fired-Up"
    if any(term in lower for term in ("failure", "excuse", "accountability", "bad process")) and risk < 55:
        return "Critical"
    if any(term in lower for term in ("decision", "process", "pressure", "trust", "problem")):
        return "Witty Edge" if risk < 60 else "Skeptical"
    return current_lane if current_lane else "Witty Edge"


def recommended_format_for_opportunity(text: str, current_fmt: str = "Normal Tweet") -> str:
    clean = normalize_text(text)
    lower = clean.lower()
    if any(term in lower for term in ("video", "youtube", "column", "deep dive")):
        return "Article"
    if re.search(r"\b(1\.|first|second|third|three reasons|sequence|timeline)\b", lower):
        return "Thread"
    if len(clean) > 260 or len(re.findall(r"\b(because|then|but|also|meanwhile)\b", lower)) >= 3:
        return "Long Tweet"
    if any(term in lower for term in ("joke", "absurd", "funny")) and len(clean) < 180:
        return "Punchy Tweet"
    return current_fmt if current_fmt in {"Punchy Tweet", "Normal Tweet", "Long Tweet", "Thread", "Article"} else "Normal Tweet"


def public_x_opportunity_report(text: str, source_basis: list | None = None, state: dict | None = None, lane: str = "Witty Edge", fmt: str = "Normal Tweet") -> dict[str, Any]:
    basis = [b for b in (source_basis or []) if isinstance(b, dict)]
    draft = public_x_draft_report(text, fmt, lane)
    freshness = source_freshness_from_basis(basis)
    confidence = source_confidence_from_basis(basis)
    triangulation = source_triangulation_bonus(basis)
    audience_fit = _clamp((draft["oon_readability"] * 0.55) + (draft["retrieval_fit"] * 0.25) + (confidence * 0.20))
    novelty = 72
    if isinstance(state, dict) and opportunity_moment_key(text) in normalize_text(" ".join(str(x) for x in state.get("recent_moment_keys", []) or [])):
        novelty = 25
    total = _clamp(freshness * 0.14 + confidence * 0.12 + audience_fit * 0.16 + draft["retrieval_fit"] * 0.16 + draft["positive_action_fit"] * 0.12 + draft["oon_readability"] * 0.10 + (100 - draft["negative_signal_risk"]) * 0.12 + novelty * 0.06 + min(8, triangulation))
    return {
        "freshness": freshness,
        "source_confidence": confidence,
        "source_count": len(basis),
        "independent_source_count": len({str(b.get("author") or b.get("url") or b.get("id") or i) for i, b in enumerate(basis)}),
        "source_triangulation_bonus": triangulation,
        "candidate_anchor": draft["candidate_anchor"],
        "sports_mechanism": draft["sports_mechanism"],
        "candidate_fit": draft["candidate_fit"],
        "retrieval_fit": draft["retrieval_fit"],
        "audience_fit": audience_fit,
        "oon_readability": draft["oon_readability"],
        "out_of_network_readability": draft["oon_readability"],
        "target_action": draft["target_action"],
        "positive_action_fit": draft["positive_action_fit"],
        "negative_signal_risk": draft["negative_signal_risk"],
        "negative_signal_reason": draft["negative_signal_reason"],
        "not_dwelled_risk": draft["not_dwelled_risk"],
        "novelty": novelty,
        "total": total,
        "recommended_lane": recommended_lane_for_opportunity(text, lane),
        "recommended_format": recommended_format_for_opportunity(text, fmt),
        "moment_key": opportunity_moment_key(text),
    }


def algorithm_profile_for_post(text: str, fmt: str, lane: str, source_text: str = "") -> dict[str, Any]:
    report = public_x_draft_report(text, fmt, lane, source_text)
    report["profile_version"] = "ce-public-x-action-profile-v1"
    return report


def infer_actual_action_winner(metrics: dict) -> str:
    views = max(float(metrics.get("views") or metrics.get("viewCount") or 0), 1.0)
    reply = float(metrics.get("reply_per_1k") or (float(metrics.get("replies") or metrics.get("replyCount") or 0) / views * 1000.0))
    repost = float(metrics.get("repost_per_1k") or (float(metrics.get("reposts") or metrics.get("retweetCount") or 0) / views * 1000.0))
    quotes = float(metrics.get("quotes") or metrics.get("quoteCount") or 0)
    likes = float(metrics.get("likes") or metrics.get("likeCount") or 0)
    bookmarks = float(metrics.get("bookmarks") or metrics.get("bookmarkCount") or 0)
    if reply >= max(repost * 1.8, 6.0) and repost < 1.2:
        return "false_winner"
    if reply >= max(repost, 4.0):
        return "reply"
    if repost >= max(reply, 2.0):
        return "repost"
    if quotes >= 3 and quotes >= repost:
        return "quote"
    if likes + bookmarks >= max(10.0, views * 0.015):
        return "affinity"
    if views >= 5000:
        return "reach_only"
    return "dwell"


def select_best_option_by_public_x(data: dict, quality: dict, fmt: str, lane: str, source_text: str = "") -> tuple[str, dict]:
    candidates: list[tuple[tuple[int, int, int, int, int], str, dict]] = []
    for idx in ("1", "2", "3"):
        key = f"option{idx}"
        text = str((data or {}).get(key) or "").strip()
        q = (quality or {}).get(key, {}) if isinstance(quality, dict) else {}
        if not text or not bool(q.get("ok")):
            continue
        report = q.get("public_x") if isinstance(q.get("public_x"), dict) else public_x_draft_report(text, fmt, lane, source_text)
        candidates.append(((
            int(report.get("total", 0) or 0),
            int(report.get("candidate_fit", 0) or 0),
            int(report.get("positive_action_fit", 0) or 0),
            -int(report.get("negative_signal_risk", 100) or 100),
            int(report.get("oon_readability", report.get("out_of_network_readability", 0)) or 0),
        ), idx, report))
    if not candidates:
        pick = str((data or {}).get("pick") or "1").strip()
        return pick if pick in {"1", "2", "3"} else "1", {}
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1], candidates[0][2]
