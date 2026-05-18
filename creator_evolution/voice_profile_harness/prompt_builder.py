"""Build approval-gated Tyler voice profile JSON and Markdown."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from .config import artifact_path, read_json, read_jsonl, utc_now_iso, write_json


def _top(values: list, limit: int = 8) -> list:
    return [value for value, _ in Counter(v for v in values if v).most_common(limit)]


def _dist(values: list) -> dict:
    counts = Counter(v for v in values if v)
    total = max(1, sum(counts.values()))
    return {key: {"count": count, "pct": round(count / total * 100, 1)} for key, count in counts.most_common()}


def _profile_version() -> str:
    return "tyler_voice_profile_v" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")


def build_profile(*, root=None) -> dict:
    records = read_jsonl(artifact_path("cache/normalized_tweets.jsonl", root))
    excluded = read_jsonl(artifact_path("cache/excluded_tweets.jsonl", root))
    voice = read_jsonl(artifact_path("cache/voice_features.jsonl", root))
    fmt = read_jsonl(artifact_path("cache/format_features.jsonl", root))
    cohorts = read_json(artifact_path("analysis/performance_cohorts.json", root), []) or []
    matrix = read_json(artifact_path("analysis/topic_voice_matrix.json", root), {}) or {}
    version = _profile_version()
    lanes = _top([item.get("emotion_lane") for item in voice])
    endings = _top([item.get("ending_type") for item in voice])
    joke = _top([item.get("joke_mechanic") for item in voice])
    formats = _top([item.get("format_type") for item in fmt])
    data_window = sorted([record.get("created_at_utc") for record in records if record.get("created_at_utc")])
    high = next((c for c in cohorts if c.get("cohort_id") == "high_performers"), {})
    low = next((c for c in cohorts if c.get("cohort_id") == "low_performers"), {})
    avg_sentence = round(sum(float(item.get("avg_sentence_length_words") or 0) for item in voice) / max(1, len(voice)), 2)
    one_line_pct = round(sum(1 for item in voice if int(item.get("line_count") or 0) == 1) / max(1, len(voice)) * 100, 1)
    multi_line_pct = round(100 - one_line_pct, 1)
    corpus_fingerprint = {
        "tweet_count_used": len(records),
        "average_sentence_length_words": avg_sentence,
        "one_line_posts_pct": one_line_pct,
        "multi_line_posts_pct": multi_line_pct,
        "format_distribution": _dist([item.get("format_type") for item in fmt]),
        "emotion_lane_distribution": _dist([item.get("emotion_lane") for item in voice]),
        "ending_type_distribution": _dist([item.get("ending_type") for item in voice]),
        "tension_mechanic_distribution": _dist([item.get("tension_mechanic") for item in voice]),
        "joke_mechanic_distribution": _dist([item.get("joke_mechanic") for item in voice]),
    }
    observed_format_mix = ", ".join(
        f"{key} {value['pct']}%" for key, value in corpus_fingerprint["format_distribution"].items()
    )
    profile = {
        "profile_version": version,
        "created_at_utc": utc_now_iso(),
        "data_window_start": data_window[0] if data_window else "",
        "data_window_end": data_window[-1] if data_window else "",
        "tweet_count_total": len(records) + len(excluded),
        "tweet_count_used": len(records),
        "tweet_count_excluded": len(excluded),
        "core_voice_identity": "Tyler sounds like a funny, blunt, sports-radio sharp former NFL lineman posting from his phone: specific, witty, sometimes annoyed, sometimes fired-up, usually less polished than an AI wants to be.",
        "sounds_like_tyler_rules": [
            "Start from the exact sports mechanism, not a generic reaction.",
            "Use compressed declarative tension and let the final beat do work.",
            "Prefer blunt human phrasing over clever metaphor.",
            "Let sarcasm come from fake calm or fake enthusiasm, not from explaining the joke.",
            "Keep the audience in the argument by leaving a consequence or contradiction hanging.",
            "Use phone-typed pacing: short sentences, fragments when natural, and minimal polished punctuation.",
            "Be specific enough that a fan knows the team, player, roster decision, or game state immediately.",
            f"Default length should feel compact: the corpus averaged {avg_sentence} words per sentence and was mostly Punchy/Normal.",
            f"Default shape should usually be one clean block: {one_line_pct}% of used posts were one-line posts, with multi-line posts used selectively.",
            f"Most natural endings are hard-period walkoffs or short punchlines, not constant questions or constant ellipses.",
        ],
        "never_tyler_rules": [
            "No corporate polish, LinkedIn cadence, or content strategy voice.",
            "No generic hot-take templates, fake questions, or engagement bait.",
            "No 'Here is the thing', stale hooks, or symmetrical three-part essay structure.",
            "No over-explained jokes or punchlines that need a second sentence of explanation.",
            "No fake certainty, invented facts, invented stats, or current-event claims not in the source.",
            "No copying old Tyler tweets, old punchlines, or uncommon phrases.",
        ],
        "format_rules": {
            "observed_formats": formats,
            "distribution": corpus_fingerprint["format_distribution"],
            "rule": "Make Punchy, Normal, Long, Thread, and Article visibly different. Default toward compact Punchy/Normal unless the source truly needs room. Do not force every Normal tweet into the same blank-line skeleton.",
        },
        "emotion_lane_rules": {
            "observed_lanes": lanes,
            "distribution": corpus_fingerprint["emotion_lane_distribution"],
            "rule": "Default to Witty Edge. Use Skeptical when the post is challenging a premise. Use Sarcastic for fake enthusiasm, Annoyed for real frustration, Celebratory for earned victory laps, Deadpan for flat absurdity, and Comedic only when there is an actual joke mechanic.",
        },
        "corpus_voice_fingerprint": corpus_fingerprint,
        "topic_voice_overrides": matrix,
        "reply_driving_mechanics": [
            "contradiction without a literal question",
            "unfinished consequence",
            "specific fan argument pressure",
            "sharp final beat that people want to quote or argue with",
        ],
        "banned_ai_patterns": [
            "corporate polish",
            "LinkedIn cadence",
            "generic hot-take templates",
            "fake questions",
            "Here is the thing",
            "symmetrical three-part AI structure",
            "over-explained jokes",
            "fake certainty",
            "invented facts",
            "stale hooks",
            "engagement bait",
        ],
        "approved_examples_abstracted": [
            f"High performers often use {', '.join(high.get('common_voice_features', {}).get('tension_mechanic', []) or ['declarative pressure'])} and end with {', '.join(endings[:3]) or 'a compact walkoff'}.",
            f"Strong joke mechanics observed: {', '.join(joke[:4]) or 'sports contradiction stated plainly'}.",
            f"Corpus rhythm: average sentence length {avg_sentence} words, one-line posts {one_line_pct}%, multi-line posts {multi_line_pct}%.",
            f"Observed format mix: {observed_format_mix}.",
        ],
        "do_not_copy_examples": [
            "Do not paste old tweet language into the generation prompt.",
            "Use tweet IDs and mechanics as evidence, not as text to imitate.",
        ],
        "self_check_rubric": {
            "sounds_posted_from_phone": "Would Tyler plausibly post this without editing it into an essay?",
            "specific_sports_mechanism": "Does it name or clearly imply the real team/player/decision/game mechanism?",
            "anti_ai": "Does it avoid corporate polish, fake balance, stale hooks, and direct engagement bait?",
            "copy_guard": "Does it avoid reusing old uncommon phrases or punchline structures?",
        },
        "activation_status": "pending",
        "approved_by": "",
        "approved_at_utc": "",
        "short_system_insert": "",
    }
    profile["short_system_insert"] = build_short_insert(profile)
    profile_path = artifact_path(f"profiles/{version}.json", root)
    pending_path = artifact_path("profiles/pending_profile.json", root)
    write_json(profile_path, profile)
    write_json(pending_path, profile)
    prompt = build_prompt_markdown(profile)
    prompt_path = artifact_path(f"profiles/{version.replace('tyler_voice_profile_', 'tyler_voice_profile_prompt_')}.md", root)
    pending_prompt_path = artifact_path("profiles/pending_profile_prompt.md", root)
    prompt_path.write_text(prompt, encoding="utf-8")
    pending_prompt_path.write_text(prompt, encoding="utf-8")
    prompt_ready = {
        "profile_version": version,
        "prompt_markdown": prompt,
        "short_system_insert": profile["short_system_insert"],
        "long_generation_context": prompt,
        "anti_ai_checklist": profile["banned_ai_patterns"],
        "rubric_json": profile["self_check_rubric"],
        "source_profile_json_path": str(profile_path),
        "activation_status": "pending",
    }
    write_json(artifact_path("profiles/prompt_ready_output.json", root), prompt_ready)
    return {"profile_path": str(profile_path), "prompt_path": str(prompt_path), "pending_profile_path": str(pending_path), "profile_version": version}


def build_short_insert(profile: dict) -> str:
    rules = "\n".join(f"- {item}" for item in profile.get("sounds_like_tyler_rules", [])[:8])
    never = "\n".join(f"- {item}" for item in profile.get("never_tyler_rules", [])[:8])
    fingerprint = profile.get("corpus_voice_fingerprint") or {}
    rhythm = (
        f"Corpus rhythm: avg sentence {fingerprint.get('average_sentence_length_words', 'n/a')} words, "
        f"one-line posts {fingerprint.get('one_line_posts_pct', 'n/a')}%, "
        f"multi-line posts {fingerprint.get('multi_line_posts_pct', 'n/a')}%."
    )
    return f"""TYLER VOICE PROFILE
Core identity: {profile.get('core_voice_identity', '')}
{rhythm}

Sounds like Tyler:
{rules}

Never Tyler:
{never}

Self-check: would this sound normal if Tyler posted it from his phone? If not, rewrite."""


def build_prompt_markdown(profile: dict) -> str:
    def section(title: str, body) -> str:
        if isinstance(body, dict):
            lines = [f"- {k}: {v}" for k, v in body.items()]
        elif isinstance(body, list):
            lines = [f"- {item}" for item in body]
        else:
            lines = [str(body)]
        return f"## {title}\n" + "\n".join(lines) + "\n"

    parts = [
        f"# Tyler Voice Profile Prompt\n\nProfile version: `{profile.get('profile_version')}`\nActivation status: `{profile.get('activation_status')}`\n",
        section("Core Voice Identity", profile.get("core_voice_identity", "")),
        section("Sounds Like Tyler Rules", profile.get("sounds_like_tyler_rules", [])),
        section("Never Tyler Rules", profile.get("never_tyler_rules", [])),
        section("Format-Specific Rules", profile.get("format_rules", {})),
        section("Emotional Lane Rules", profile.get("emotion_lane_rules", {})),
        section("Corpus Voice Fingerprint", profile.get("corpus_voice_fingerprint", {})),
        section("Example Abstractions Without Copying", profile.get("approved_examples_abstracted", [])),
        section("Reply-Driving Mechanics", profile.get("reply_driving_mechanics", [])),
        section("Banned AI Patterns", profile.get("banned_ai_patterns", [])),
        section("Self-Check Rubric", profile.get("self_check_rubric", {})),
        "## How Creator Evolution Should Use This\n- Use only if this profile is approved.\n- Combine with existing Creator Evolution approved rules and mature learning.\n- Never affect Creator Studio.\n- Never copy old tweets verbatim.\n",
    ]
    return "\n".join(parts)
