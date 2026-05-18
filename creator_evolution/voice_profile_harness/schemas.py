"""Schema contracts for Creator Evolution voice profile artifacts."""

from __future__ import annotations

NORMALIZED_TWEET_FIELDS = (
    "tweet_id",
    "source_system",
    "author_username",
    "author_id",
    "created_at_utc",
    "text_raw",
    "text_clean",
    "lang",
    "url",
    "is_original",
    "is_reply",
    "is_repost",
    "is_quote",
    "is_thread_part",
    "conversation_id",
    "in_reply_to_tweet_id",
    "quoted_tweet_id",
    "retweeted_tweet_id",
    "has_media",
    "media_types",
    "has_link",
    "expanded_urls",
    "mentions",
    "hashtags",
    "source_app",
    "topic_labels",
    "sport_labels",
    "team_labels",
    "player_labels",
    "ingested_at_utc",
    "raw_ref",
)

METRIC_SNAPSHOT_FIELDS = (
    "tweet_id",
    "snapshot_at_utc",
    "age_hours_at_snapshot",
    "views",
    "impressions",
    "likes",
    "replies",
    "reposts",
    "quotes",
    "bookmarks",
    "profile_clicks",
    "url_clicks",
    "engagements",
    "metric_source",
    "is_partial",
    "notes",
)

VOICE_FEATURE_FIELDS = (
    "tweet_id",
    "sentence_count",
    "avg_sentence_length_words",
    "line_count",
    "uses_fragments",
    "uses_short_punchline",
    "uses_caps_emphasis",
    "question_count",
    "exclamation_count",
    "ellipsis_count",
    "first_person_level",
    "direct_address_level",
    "emotion_lane",
    "edge_level",
    "sarcasm_markers",
    "joke_mechanic",
    "tension_mechanic",
    "ending_type",
    "recurring_phrases",
    "banned_ai_risk_flags",
    "tylerness_score_initial",
)

FORMAT_FEATURE_FIELDS = (
    "tweet_id",
    "format_type",
    "hook_type",
    "has_setup",
    "has_turn",
    "has_punchline",
    "has_specific_claim",
    "has_named_entities",
    "has_stats",
    "has_media_context",
    "reply_bait_type",
    "structure_ai_risk",
)

BANNED_AI_PATTERNS = (
    "Here is the thing",
    "Here's the thing",
    "Let that sink in",
    "Not enough people are talking about",
    "Unpopular opinion",
    "Thoughts?",
    "What do you think?",
    "Agree or disagree",
    "At the end of the day",
)


def missing_fields(item: dict, fields: tuple[str, ...]) -> list[str]:
    return [field for field in fields if field not in item]


def assert_has_fields(item: dict, fields: tuple[str, ...]) -> None:
    missing = missing_fields(item, fields)
    if missing:
        raise ValueError("missing fields: " + ", ".join(missing))
