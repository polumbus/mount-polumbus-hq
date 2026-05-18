"""Build fair performance and voice cohorts."""

from __future__ import annotations

from collections import Counter, defaultdict

from .performance import score_all


def _summarize_metrics(items: list[dict]) -> dict:
    if not items:
        return {}
    keys = ("normalized_score", "replies_per_1k_views", "reposts_per_1k_views", "likes_per_1k_views", "bookmarks_per_1k_views")
    return {key: round(sum(float(item.get(key) or 0) for item in items) / len(items), 3) for key in keys}


def _common(items: list[dict], key: str, limit: int = 5) -> list:
    counts = Counter()
    for item in items:
        value = item.get(key)
        if isinstance(value, list):
            counts.update(value)
        elif value:
            counts[value] += 1
    return [value for value, _ in counts.most_common(limit)]


def _cohort(cohort_id: str, cohort_type: str, tweet_ids: list[str], scores: dict, voice: dict, fmt: dict, warnings=None) -> dict:
    metric_items = [scores.get(tid, {}) for tid in tweet_ids]
    voice_items = [voice.get(tid, {}) for tid in tweet_ids]
    fmt_items = [fmt.get(tid, {}) for tid in tweet_ids]
    return {
        "cohort_id": cohort_id,
        "cohort_type": cohort_type,
        "tweet_ids": tweet_ids,
        "selection_method": cohort_type,
        "normalized_metrics_summary": _summarize_metrics(metric_items),
        "common_voice_features": {
            "emotion_lane": _common(voice_items, "emotion_lane"),
            "joke_mechanic": _common(voice_items, "joke_mechanic"),
            "tension_mechanic": _common(voice_items, "tension_mechanic"),
            "ending_type": _common(voice_items, "ending_type"),
        },
        "common_format_features": {
            "format_type": _common(fmt_items, "format_type"),
            "hook_type": _common(fmt_items, "hook_type"),
            "structure_ai_risk": _common(fmt_items, "structure_ai_risk"),
        },
        "warnings": warnings or [],
        "recommended_profile_rules": [],
    }


def build_cohorts(records: list[dict], snapshots: list[dict], voice_features: list[dict], format_features: list[dict]) -> list[dict]:
    scores = score_all(snapshots)
    voice = {item.get("tweet_id", ""): item for item in voice_features}
    fmt = {item.get("tweet_id", ""): item for item in format_features}
    ids = [str(item.get("tweet_id") or "") for item in records if item.get("tweet_id")]
    ranked = sorted(ids, key=lambda tid: scores.get(tid, {}).get("normalized_score", 0), reverse=True)
    high = ranked[: max(1, min(12, len(ranked) // 4 or len(ranked)))]
    low = ranked[-max(1, min(12, len(ranked) // 4 or len(ranked))):] if ranked else []
    by_reply = sorted(ids, key=lambda tid: scores.get(tid, {}).get("replies_per_1k_views", 0), reverse=True)
    by_repost = sorted(ids, key=lambda tid: scores.get(tid, {}).get("reposts_per_1k_views", 0), reverse=True)
    by_bookmark = sorted(ids, key=lambda tid: scores.get(tid, {}).get("bookmarks_per_1k_views", 0), reverse=True)
    high_voice_low_topic = [
        tid for tid in ids
        if voice.get(tid, {}).get("tylerness_score_initial", 0) >= 82 and scores.get(tid, {}).get("normalized_score", 0) < 35
    ][:12]
    high_topic_low_voice = [
        tid for tid in ranked
        if voice.get(tid, {}).get("tylerness_score_initial", 100) < 65
    ][:12]
    false_winners = [
        tid for tid in ranked
        if scores.get(tid, {}).get("replies_per_1k_views", 0) > 20 and voice.get(tid, {}).get("edge_level", 0) >= 4
    ][:12]
    ai_risk = [tid for tid in ids if voice.get(tid, {}).get("banned_ai_risk_flags") or fmt.get(tid, {}).get("structure_ai_risk") == "high"][:20]
    cohorts = [
        _cohort("high_performers", "high performers", high, scores, voice, fmt),
        _cohort("low_performers", "low performers", low, scores, voice, fmt, warnings=["Do not overfit low-performing structure."]),
        _cohort("false_winners", "false winners", false_winners, scores, voice, fmt, warnings=["High reply anger can be noisy or monetization-risky."]),
        _cohort("very_tyler_underperformed", "very Tyler but underperformed", high_voice_low_topic, scores, voice, fmt),
        _cohort("high_topic_low_voice", "high topic/low voice", high_topic_low_voice, scores, voice, fmt),
        _cohort("high_voice_low_topic", "high voice/low topic", high_voice_low_topic, scores, voice, fmt),
        _cohort("high_reply_rate", "high reply rate", by_reply[:12], scores, voice, fmt),
        _cohort("high_repost_rate", "high repost rate", by_repost[:12], scores, voice, fmt),
        _cohort("high_bookmark_rate", "high bookmark rate", by_bookmark[:12], scores, voice, fmt),
        _cohort("ai_risk_generic_posts", "AI-risk/generic posts", ai_risk, scores, voice, fmt, warnings=["These patterns should be banned or treated as negative examples."]),
    ]
    topic_matrix: dict[str, dict] = defaultdict(lambda: {"tweet_count": 0, "emotion_lanes": Counter(), "format_types": Counter()})
    for record in records:
        tid = str(record.get("tweet_id") or "")
        topics = record.get("topic_labels") or ["general sports"]
        for topic in topics:
            topic_matrix[topic]["tweet_count"] += 1
            topic_matrix[topic]["emotion_lanes"][voice.get(tid, {}).get("emotion_lane", "Witty Edge")] += 1
            topic_matrix[topic]["format_types"][fmt.get(tid, {}).get("format_type", "Normal Tweet")] += 1
    matrix = {
        topic: {
            "tweet_count": data["tweet_count"],
            "emotion_lanes": dict(data["emotion_lanes"].most_common()),
            "format_types": dict(data["format_types"].most_common()),
        }
        for topic, data in sorted(topic_matrix.items())
    }
    return cohorts, matrix
