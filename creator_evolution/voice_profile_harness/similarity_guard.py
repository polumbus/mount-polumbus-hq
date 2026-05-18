"""Copy and AI-sound guards for Tyler profile evaluation."""

from __future__ import annotations

import difflib
import re
from collections import Counter

from .feature_extractors import banned_ai_flags, sentences, words


def ngrams(text: str, n: int = 4) -> set[str]:
    toks = [w.lower() for w in words(text)]
    return {" ".join(toks[i:i + n]) for i in range(0, max(0, len(toks) - n + 1))}


def structure_signature(text: str) -> str:
    sent = sentences(text)
    lengths = [len(words(part)) for part in sent]
    marks = "".join(ch for ch in text if ch in "?!...")
    return f"s{len(sent)}-l{'-'.join(str(x) for x in lengths[:5])}-m{marks[:8]}"


def copy_similarity_report(generated: list[str], source_texts: list[str]) -> dict:
    source_grams = set()
    source_signatures = Counter(structure_signature(text) for text in source_texts)
    for text in source_texts:
        source_grams.update(ngrams(text, 4))
    items = []
    max_overlap = 0.0
    max_fuzzy = 0.0
    copied = []
    for text in generated:
        grams = ngrams(text, 4)
        overlap = len(grams & source_grams) / max(1, len(grams))
        fuzzy = max((difflib.SequenceMatcher(None, text.lower(), src.lower()).ratio() for src in source_texts), default=0.0)
        sig = structure_signature(text)
        max_overlap = max(max_overlap, overlap)
        max_fuzzy = max(max_fuzzy, fuzzy)
        flags = []
        if overlap >= 0.35:
            flags.append("high n-gram overlap")
        if fuzzy >= 0.78:
            flags.append("high fuzzy similarity")
        if source_signatures[sig] >= 3:
            flags.append("reused structure signature")
        if flags:
            copied.append(text)
        items.append({"text": text, "ngram_overlap": round(overlap, 3), "fuzzy_similarity": round(fuzzy, 3), "structure_signature": sig, "flags": flags})
    return {
        "max_ngram_overlap": round(max_overlap, 3),
        "max_fuzzy_similarity": round(max_fuzzy, 3),
        "copied_too_closely": bool(copied),
        "items": items,
    }


def ai_sound_flags(text: str) -> list[str]:
    flags = banned_ai_flags(text)
    low = text.lower()
    if re.search(r"\bnot only\b.*\bbut also\b", low):
        flags.append("balanced essay phrase")
    if len(sentences(text)) >= 4 and text.count(",") >= 5:
        flags.append("over-polished multi-clause cadence")
    if any(phrase in low for phrase in ("content strategy", "drive engagement", "optimize for")):
        flags.append("strategy voice")
    return sorted(set(flags))
