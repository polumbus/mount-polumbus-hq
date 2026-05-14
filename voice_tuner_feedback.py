"""Structured Voice Tuner feedback rules.

This module keeps natural-language feedback out of the generation prompt until it
has been translated into scoped, typed rules.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any


FEEDBACK_RULE_VERSION = 2

WASTED_SETUP_FRAMES = (
    "the funny part is",
    "the funny part",
    "funny part is",
    "the whole thing is",
    "you can always tell",
    "the thing is",
    "here's the thing",
    "heres the thing",
    "the reality is",
    "what's interesting is",
    "whats interesting is",
    "what is interesting is",
)

STYLE_RULES = (
    ("avoid_style", "setup", "less", ("too much setup", "less setup", "wasted space", "throat clearing", "throat-clearing"), "Use less setup and start closer to the sports point."),
    ("avoid_style", "polish", "less", ("too polished", "less polished", "linkedin", "content strategy", "salesy", "sales", "corporate"), "Make it less polished and more natural."),
    ("avoid_style", "generic", "less", ("too generic", "generic", "not specific", "more specific"), "Make the sports detail more specific."),
    ("require_trait", "voice", "more", ("not enough voice", "more voice", "more tyler", "more human", "human"), "Make the voice more natural and human."),
    ("require_trait", "tension", "more", ("not enough tension", "more tension", "more consequence", "consequence-driven", "more consequence"), "Add a sharper consequence or tension beat."),
    ("compression", "length", "less", ("too long", "shorter", "compress", "compressed", "tighten"), "Make the draft tighter without losing the point."),
    ("ending_policy", "ending", "stronger", ("ending is weak", "stronger ending", "hit harder", "sharper ending", "sharper consequence"), "Make the ending sharper and more consequential."),
    ("ending_policy", "ellipsis", "avoid", ("avoid ellipsis", "no ellipsis", "without ellipsis"), "Do not rely on an ellipsis ending."),
    ("source_preservation", "source", "preserve", ("lost my point", "loses my original point", "keep my point", "preserve my point", "don't lose detail", "dont lose detail"), "Preserve the original point and source detail."),
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _rule_id(raw_text: str, lane: str, fmt: str, kind: str, value: str, source: str) -> str:
    digest = hashlib.sha1("|".join([raw_text, lane, fmt, kind, value, source]).encode()).hexdigest()[:12]
    return f"vtr_{digest}"


def _append_unique_rule(rules: list[dict[str, Any]], rule: dict[str, Any]) -> None:
    identity = (
        rule.get("kind"),
        rule.get("severity"),
        str(rule.get("dimension", "")),
        str(rule.get("direction", "")),
        tuple(rule.get("matcher", {}).get("values", []) or []),
    )
    for existing in rules:
        existing_identity = (
            existing.get("kind"),
            existing.get("severity"),
            str(existing.get("dimension", "")),
            str(existing.get("direction", "")),
            tuple(existing.get("matcher", {}).get("values", []) or []),
        )
        if identity == existing_identity:
            return
    rules.append(rule)


def _quoted_phrases(text: str) -> list[str]:
    phrases = []
    for phrase in re.findall(r"[\"'“”‘’]([^\"'“”‘’]{2,80})[\"'“”‘’]", text):
        clean = _norm(phrase).strip(" .,:;!?\"'“”‘’")
        if clean and clean not in phrases:
            phrases.append(clean)
    return phrases


def _example_phrase_bans(text: str) -> list[str]:
    lower = _norm(text)
    phrases: list[str] = []
    negation_markers = (
        "don't say", "dont say", "do not say", "not say", "never say", "stop saying",
        "avoid saying", "avoid", "no more", "without",
    )
    if not any(marker in lower for marker in negation_markers):
        return phrases
    for known in WASTED_SETUP_FRAMES:
        if re.search(rf"\b{re.escape(known)}\b", lower) and known not in phrases:
            phrases.append(known)
    for phrase in _quoted_phrases(text):
        if phrase not in phrases:
            phrases.append(phrase)
    tail = ""
    for marker in ("things like", "phrases like", "words like"):
        idx = lower.find(marker)
        if idx >= 0:
            tail = text[idx + len(marker):]
            break
    if not tail:
        return phrases
    tail = re.split(
        r"\b(?:and\s+let|and\s+make|and\s+have|and\s+then|and\s+the\s+tweet|"
        r"let\s+the\s+tweet|without\s+wasted|instead|because|so\s+that|"
        r"then\s+immediately|immediately\s+got)\b",
        tail,
        1,
        flags=re.I,
    )[0]
    for piece in re.split(r"\s*(?:,|;|/|\bor\b)\s*", tail, flags=re.I):
        clean = _norm(piece).strip(" .,:;!?\"'“”‘’")
        words = re.findall(r"[a-z0-9']+", clean)
        if 2 <= len(words) <= 6 and clean.startswith(("the ", "you ", "you can ", "here's ", "heres ", "what's ", "whats ")):
            if clean not in phrases:
                phrases.append(clean)
    return phrases


def compile_voice_feedback(
    raw_text: str,
    lane: str,
    fmt: str,
    concept_id: str = "",
    source: str = "manual",
    scope: str = "sandbox",
    created_at: str | None = None,
) -> list[dict[str, Any]]:
    """Compile natural feedback into typed Voice Tuner rules."""
    raw = str(raw_text or "").strip()
    if not raw:
        return []
    created = created_at or datetime.now().isoformat(timespec="seconds")
    rules: list[dict[str, Any]] = []
    for phrase in _example_phrase_bans(raw):
        _append_unique_rule(rules, {
            "id": _rule_id(raw, lane, fmt, "forbid_phrase", phrase, source),
            "version": FEEDBACK_RULE_VERSION,
            "lane": lane,
            "format": fmt,
            "concept_id": concept_id,
            "scope": scope,
            "source": source,
            "raw_text": raw,
            "kind": "forbid_phrase",
            "severity": "hard",
            "dimension": "surface_text",
            "direction": "avoid",
            "matcher": {"type": "exact_phrase", "values": [phrase]},
            "prompt_instruction": f"Do not use the exact phrase: {phrase}.",
            "score_weight": 35,
            "status": "active",
            "created_at": created,
        })
    lower = _norm(raw)
    for kind, dimension, direction, markers, instruction in STYLE_RULES:
        if any(marker in lower for marker in markers):
            _append_unique_rule(rules, {
                "id": _rule_id(raw, lane, fmt, kind, f"{dimension}:{direction}", source),
                "version": FEEDBACK_RULE_VERSION,
                "lane": lane,
                "format": fmt,
                "concept_id": concept_id,
                "scope": scope,
                "source": source,
                "raw_text": raw,
                "kind": kind,
                "severity": "soft",
                "dimension": dimension,
                "direction": direction,
                "matcher": {"type": "heuristic", "values": list(markers)},
                "prompt_instruction": instruction,
                "score_weight": 10,
                "status": "active",
                "created_at": created,
            })
    if not rules and len(re.findall(r"[a-zA-Z0-9']+", raw)) >= 3:
        _append_unique_rule(rules, {
            "id": _rule_id(raw, lane, fmt, "require_trait", "general", source),
            "version": FEEDBACK_RULE_VERSION,
            "lane": lane,
            "format": fmt,
            "concept_id": concept_id,
            "scope": scope,
            "source": source,
            "raw_text": raw,
            "kind": "require_trait",
            "severity": "soft",
            "dimension": "general",
            "direction": "more",
            "matcher": {"type": "none", "values": []},
            "prompt_instruction": f"Use this as taste guidance, not a hard ban: {raw}",
            "score_weight": 6,
            "status": "active",
            "created_at": created,
        })
    return rules


def normalize_rules(rules: list[dict[str, Any]] | None, lane: str = "", fmt: str = "", concept_id: str = "", scope: str = "sandbox") -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        clean = dict(rule)
        clean.setdefault("version", FEEDBACK_RULE_VERSION)
        clean.setdefault("lane", lane)
        clean.setdefault("format", fmt)
        clean.setdefault("concept_id", concept_id)
        clean.setdefault("scope", scope)
        clean.setdefault("status", "active")
        clean.setdefault("severity", "soft")
        clean.setdefault("matcher", {"type": "none", "values": []})
        clean.setdefault("prompt_instruction", clean.get("raw_text", ""))
        if not clean.get("id"):
            clean["id"] = _rule_id(str(clean.get("raw_text", "")), str(clean.get("lane", "")), str(clean.get("format", "")), str(clean.get("kind", "")), str(clean.get("prompt_instruction", "")), str(clean.get("source", "")))
        normalized.append(clean)
    return normalized


def rules_for_context(rules: list[dict[str, Any]] | None, lane: str, fmt: str, concept_id: str | None = None, scope: str = "sandbox") -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for rule in normalize_rules(rules):
        if rule.get("status", "active") != "active":
            continue
        if rule.get("scope", scope) != scope:
            continue
        if rule.get("lane") and rule.get("lane") != lane:
            continue
        if rule.get("format") and rule.get("format") != fmt:
            continue
        if concept_id and rule.get("concept_id") and rule.get("concept_id") != concept_id:
            continue
        rule_id = str(rule.get("id", ""))
        if rule_id and rule_id in seen_ids:
            continue
        if rule_id:
            seen_ids.add(rule_id)
        selected.append(rule)
    return selected[-40:]


def feedback_rules_hash(rules: list[dict[str, Any]] | None) -> str:
    payload = [
        {
            "id": rule.get("id"),
            "kind": rule.get("kind"),
            "severity": rule.get("severity"),
            "matcher": rule.get("matcher"),
            "instruction": rule.get("prompt_instruction"),
            "status": rule.get("status"),
        }
        for rule in normalize_rules(rules)
    ]
    return hashlib.sha1(repr(payload).encode()).hexdigest()[:10]


def feedback_prompt_text(rules: list[dict[str, Any]] | None) -> str:
    active = normalize_rules(rules)
    if not active:
        return "No structured Voice Tuner feedback rules are active."
    hard = [rule for rule in active if rule.get("severity") == "hard"]
    soft = [rule for rule in active if rule.get("severity") != "hard"]
    lines = ["STRUCTURED VOICE TUNER FEEDBACK:"]
    if hard:
        lines.append("Hard constraints:")
        lines.extend(f"- {rule.get('prompt_instruction', '')}" for rule in hard)
    if soft:
        lines.append("Soft taste guidance:")
        lines.extend(f"- {rule.get('prompt_instruction', '')}" for rule in soft)
    return "\n".join(lines)


def interpretation_summary(rules: list[dict[str, Any]] | None) -> str:
    active = normalize_rules(rules)
    if not active:
        return ""
    parts: list[str] = []
    bans = []
    for rule in active:
        if rule.get("kind") == "forbid_phrase":
            bans.extend(rule.get("matcher", {}).get("values", []) or [])
    if bans:
        parts.append("avoid " + ", ".join(bans[:4]))
    labels = {
        ("setup", "less"): "less setup",
        ("polish", "less"): "less polish",
        ("generic", "less"): "more specific",
        ("voice", "more"): "more natural voice",
        ("tension", "more"): "more tension",
        ("length", "less"): "more compressed",
        ("ending", "stronger"): "stronger ending",
        ("ellipsis", "avoid"): "avoid ellipsis",
        ("source", "preserve"): "preserve the original point",
    }
    for rule in active:
        label = labels.get((rule.get("dimension"), rule.get("direction")))
        if label and label not in parts:
            parts.append(label)
    if not parts:
        parts.append("use your note as taste guidance")
    return "I'll try: " + ", ".join(parts[:6]) + "."


def evaluate_feedback_constraints(
    text: str,
    rules: list[dict[str, Any]] | None,
    fmt: str = "",
    lane: str = "",
    source_text: str = "",
) -> dict[str, Any]:
    clean = str(text or "")
    lower = _norm(clean)
    hard_failures: list[dict[str, Any]] = []
    soft_warnings: list[dict[str, Any]] = []
    satisfied: list[str] = []
    not_applicable: list[str] = []
    active = normalize_rules(rules)
    for rule in active:
        kind = rule.get("kind")
        severity = rule.get("severity", "soft")
        values = rule.get("matcher", {}).get("values", []) or []
        failed = False
        if kind == "forbid_phrase":
            hits = [phrase for phrase in values if re.search(rf"\b{re.escape(_norm(phrase))}\b", lower)]
            if hits:
                failed = True
                payload = {"id": rule.get("id"), "kind": kind, "message": "Banned phrase used: " + ", ".join(hits), "hits": hits}
            else:
                payload = {"id": rule.get("id"), "kind": kind}
        elif kind == "avoid_style" and rule.get("dimension") == "setup":
            hits = [phrase for phrase in WASTED_SETUP_FRAMES if re.search(rf"\b{re.escape(phrase)}\b", lower)]
            failed = bool(hits)
            payload = {"id": rule.get("id"), "kind": kind, "message": "Still uses setup/throat-clearing: " + ", ".join(hits[:3]), "hits": hits}
        elif kind == "avoid_style" and rule.get("dimension") == "polish":
            hits = [phrase for phrase in ("content strategy", "at the end of the day", "the reality is", "here's why", "game-changer", "unlock") if phrase in lower]
            failed = bool(hits)
            payload = {"id": rule.get("id"), "kind": kind, "message": "Still sounds polished: " + ", ".join(hits[:3]), "hits": hits}
        elif kind == "avoid_style" and rule.get("dimension") == "generic":
            failed = not re.search(r"\b(broncos|nuggets|avs|avalanche|rockies|rapids|jokic|payton|nix|rotation|bench|qb|goalie|roster|lineup)\b", lower)
            payload = {"id": rule.get("id"), "kind": kind, "message": "Still needs a concrete sports detail."}
        elif kind == "compression":
            threshold = 190 if fmt == "Normal Tweet" else 130 if fmt == "Punchy Tweet" else None
            failed = bool(threshold and len(clean) > threshold)
            payload = {"id": rule.get("id"), "kind": kind, "message": f"Still too long for compressed feedback ({len(clean)} chars)."}
        elif kind == "ending_policy" and rule.get("dimension") == "ellipsis":
            failed = clean.rstrip().endswith(("...", "…"))
            payload = {"id": rule.get("id"), "kind": kind, "message": "Still ends with ellipsis."}
        elif kind == "ending_policy":
            final = re.split(r"[.!?]\s+", clean.strip())[-1]
            failed = len(re.findall(r"\b[\w']+\b", final)) > 22
            payload = {"id": rule.get("id"), "kind": kind, "message": "Ending is still too long or soft."}
        elif kind == "source_preservation":
            source_terms = {term for term in re.findall(r"\b[A-Za-z][A-Za-z0-9'-]{3,}\b", source_text.lower()) if term not in {"this", "that", "with", "from", "they", "have", "about", "says", "keep"}}
            if source_terms:
                kept = [term for term in source_terms if term in lower]
                failed = len(kept) < max(1, min(2, len(source_terms)))
                payload = {"id": rule.get("id"), "kind": kind, "message": "May be losing the original point.", "kept": kept[:6]}
            else:
                not_applicable.append(str(rule.get("id")))
                continue
        else:
            payload = {"id": rule.get("id"), "kind": kind}
        if failed and severity == "hard":
            hard_failures.append(payload)
        elif failed:
            soft_warnings.append(payload)
        else:
            satisfied.append(str(rule.get("id")))
    applicable = len(active) - len(not_applicable)
    feedback_score = 100 if applicable <= 0 else max(0, round((len(satisfied) / applicable) * 100) - len(soft_warnings) * 8 - len(hard_failures) * 40)
    return {
        "ok": not hard_failures,
        "feedback_score": feedback_score,
        "hard_failures": hard_failures,
        "soft_warnings": soft_warnings,
        "satisfied": satisfied,
        "not_applicable": not_applicable,
    }


def distill_live_rule_texts(rules: list[dict[str, Any]] | None) -> list[str]:
    texts: list[str] = []
    for rule in normalize_rules(rules):
        if rule.get("status") != "active":
            continue
        text = str(rule.get("prompt_instruction") or "").strip()
        if text and text not in texts:
            texts.append(text)
    return texts[-12:]
