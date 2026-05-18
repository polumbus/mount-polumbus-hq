"""Pipeline analysis orchestration for voice profile artifacts."""

from __future__ import annotations

from collections import Counter

from .cohorts import build_cohorts
from .config import artifact_path, read_jsonl, write_json, write_jsonl
from .feature_extractors import extract_format_features, extract_voice_features
from .filters import split_used_excluded
from .normalize import metric_snapshot, normalize_tweet
from .performance import score_all


RAW_FILES = (
    "raw/twitterapiio_last_12_months.jsonl",
    "raw/x_archive_import.jsonl",
    "raw/manual_import.jsonl",
)


def normalize_artifacts(*, root=None, include_replies: bool = False) -> dict:
    raw_rows = []
    for rel in RAW_FILES:
        raw_rows.extend(read_jsonl(artifact_path(rel, root)))
    normalized = []
    snapshots = []
    seen = set()
    for idx, raw in enumerate(raw_rows):
        source = str(raw.get("source_system") or raw.get("source") or "unknown")
        record = normalize_tweet(raw, source_system=source, raw_ref=f"{source}:{idx}")
        tid = record.get("tweet_id") or f"missing-{idx}"
        if tid in seen:
            continue
        seen.add(tid)
        normalized.append(record)
        snapshots.append(metric_snapshot(raw, record, metric_source=source))
    used, excluded = split_used_excluded(normalized, include_replies=include_replies)
    write_jsonl(artifact_path("cache/normalized_tweets.jsonl", root), used)
    write_jsonl(artifact_path("cache/excluded_tweets.jsonl", root), excluded)
    write_jsonl(artifact_path("cache/metric_snapshots.jsonl", root), snapshots)
    return {"raw_count": len(raw_rows), "normalized_count": len(normalized), "used_count": len(used), "excluded_count": len(excluded)}


def _markdown_list(title: str, lines: list[str]) -> str:
    body = "\n".join(f"- {line}" for line in lines) if lines else "- No confident pattern yet."
    return f"# {title}\n\n{body}\n"


def analyze_artifacts(*, root=None) -> dict:
    records = read_jsonl(artifact_path("cache/normalized_tweets.jsonl", root))
    snapshots = read_jsonl(artifact_path("cache/metric_snapshots.jsonl", root))
    voice_features = [extract_voice_features(record) for record in records]
    format_features = [extract_format_features(record) for record in records]
    write_jsonl(artifact_path("cache/voice_features.jsonl", root), voice_features)
    write_jsonl(artifact_path("cache/format_features.jsonl", root), format_features)
    cohorts, topic_matrix = build_cohorts(records, snapshots, voice_features, format_features)
    write_json(artifact_path("analysis/performance_cohorts.json", root), cohorts)
    write_json(artifact_path("analysis/topic_voice_matrix.json", root), topic_matrix)
    scores = score_all(snapshots)
    high_ids = set(next((c["tweet_ids"] for c in cohorts if c["cohort_id"] == "high_performers"), []))
    low_ids = set(next((c["tweet_ids"] for c in cohorts if c["cohort_id"] == "low_performers"), []))
    by_id = {record.get("tweet_id"): record for record in records}
    vf_by_id = {item.get("tweet_id"): item for item in voice_features}
    high_lines = [
        f"{tid}: {vf_by_id.get(tid, {}).get('emotion_lane', 'Witty Edge')} / {vf_by_id.get(tid, {}).get('ending_type', '')} / score {scores.get(tid, {}).get('normalized_score', 0)}"
        for tid in high_ids
    ]
    low_lines = [
        f"{tid}: avoid {vf_by_id.get(tid, {}).get('banned_ai_risk_flags') or vf_by_id.get(tid, {}).get('ending_type', '')}"
        for tid in low_ids
    ]
    very_tyler = [
        f"{item.get('tweet_id')}: Tylerness {item.get('tylerness_score_initial')} but low normalized score"
        for item in voice_features
        if item.get("tylerness_score_initial", 0) >= 82 and scores.get(item.get("tweet_id"), {}).get("normalized_score", 0) < 35
    ]
    ai_flags = Counter(flag for item in voice_features for flag in item.get("banned_ai_risk_flags", []))
    write = lambda rel, text: artifact_path(rel, root).write_text(text, encoding="utf-8")
    write("analysis/high_performer_patterns.md", _markdown_list("High Performer Patterns", high_lines))
    write("analysis/low_performer_warnings.md", _markdown_list("Low Performer Warnings", low_lines))
    write("analysis/very_tyler_underperformed.md", _markdown_list("Very Tyler But Underperformed", very_tyler))
    write("analysis/anti_ai_voice_rules.md", _markdown_list("Anti-AI Voice Rules", [f"Ban {k}" for k, _ in ai_flags.most_common()] or ["Ban corporate polish, LinkedIn cadence, fake questions, and symmetrical essay structure."]))
    return {
        "tweet_count": len(records),
        "voice_feature_count": len(voice_features),
        "format_feature_count": len(format_features),
        "cohort_count": len(cohorts),
        "top_topics": list(topic_matrix.keys())[:12],
    }
