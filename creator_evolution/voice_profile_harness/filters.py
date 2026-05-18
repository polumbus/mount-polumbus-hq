"""Filtering rules for the read-only Tyler voice profile corpus."""

from __future__ import annotations


def exclusion_reason(tweet: dict) -> str:
    text = str(tweet.get("text_clean") or "").strip()
    if not text:
        return "empty_text"
    if tweet.get("is_repost"):
        return "repost"
    if tweet.get("is_reply"):
        return "reply"
    if len(text) < 12:
        return "too_short"
    if tweet.get("has_link") and len(text.split()) <= 3:
        return "link_only"
    return ""


def split_used_excluded(records: list[dict], *, include_replies: bool = False) -> tuple[list[dict], list[dict]]:
    used = []
    excluded = []
    for record in records:
        reason = exclusion_reason(record)
        if include_replies and reason == "reply":
            reason = ""
        if reason:
            item = dict(record)
            item["excluded_reason"] = reason
            excluded.append(item)
        else:
            used.append(record)
    return used, excluded
