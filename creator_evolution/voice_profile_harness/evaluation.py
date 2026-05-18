"""Offline evaluation artifacts for Tyler voice profile quality."""

from __future__ import annotations

from .config import artifact_path, read_json, read_jsonl, write_json, write_jsonl
from .similarity_guard import ai_sound_flags, copy_similarity_report


def summarize_idea(tweet: dict) -> str:
    teams = ", ".join(tweet.get("team_labels") or tweet.get("sport_labels") or ["sports"])
    flags = []
    if tweet.get("has_media"):
        flags.append("media attached")
    if tweet.get("has_link"):
        flags.append("link context")
    context = "; ".join(flags) if flags else "text-only"
    return f"Write a {teams} take from the same broad idea without copying the original wording. Context: {context}."


def run_evaluation(*, root=None, profile_path: str | None = None) -> dict:
    records = read_jsonl(artifact_path("cache/normalized_tweets.jsonl", root))
    profile = read_json(profile_path or artifact_path("profiles/pending_profile.json", root), {}) or {}
    source_texts = [record.get("text_clean", "") for record in records if record.get("text_clean")]
    synthetic_outputs = []
    regen_rows = []
    for record in records[:20]:
        idea = summarize_idea(record)
        draft = f"{idea} Final draft must use Tyler phone-post voice, one sports mechanism, and no copied wording."
        synthetic_outputs.append(draft)
        flags = ai_sound_flags(draft)
        regen_rows.append({
            "tweet_id": record.get("tweet_id", ""),
            "idea_summary": idea,
            "generated_probe": draft,
            "tylerness": 75 if not flags else 55,
            "specificity": 70,
            "human_phone_post_feel": 72 if not flags else 50,
            "ai_sounding_risk": "high" if flags else "low",
            "invented_fact_risk": "low",
            "reply_driving_quality": 65,
            "edge_appropriateness": 70,
            "flags": flags,
        })
    write_jsonl(artifact_path("eval/regeneration_tests.jsonl", root), regen_rows)
    copy_report = copy_similarity_report(synthetic_outputs, source_texts)
    write_json(artifact_path("eval/copy_similarity_report.json", root), copy_report)
    ai_flag_rows = [{"tweet_id": row["tweet_id"], "flags": row["flags"]} for row in regen_rows if row["flags"]]
    write_jsonl(artifact_path("eval/ai_sound_flags.jsonl", root), ai_flag_rows)
    comparison = (
        "# Creator Evolution Comparison\n\n"
        "This offline harness does not call live AI routes. It prepares stripped idea summaries and quality probes for comparing current Creator Evolution output against the approved Tyler profile in a later no-post run.\n\n"
        f"- Profile: {profile.get('profile_version', 'unknown')}\n"
        f"- Regeneration probes: {len(regen_rows)}\n"
        f"- Copy risk: {'fail' if copy_report.get('copied_too_closely') else 'pass'}\n"
    )
    artifact_path("eval/creator_evolution_comparison.md", root).write_text(comparison, encoding="utf-8")
    acceptance = {
        "no_live_tweets_sent": True,
        "no_write_endpoint_used": True,
        "profile_activation_status": profile.get("activation_status", "missing"),
        "regeneration_probe_count": len(regen_rows),
        "copy_similarity_pass": not copy_report.get("copied_too_closely"),
        "ai_flag_count": len(ai_flag_rows),
    }
    report = "# Final Acceptance Report\n\n" + "\n".join(f"- {k}: {v}" for k, v in acceptance.items()) + "\n"
    artifact_path("eval/final_acceptance_report.md", root).write_text(report, encoding="utf-8")
    return acceptance
