from typing import Any

import podcast_tracker


PACKAGING_ARTIFACT_IDS = ("title", "description", "tags", "tweet", "thumbnail_text", "clips")


def is_local_source_path(value: str) -> bool:
    clean = str(value or "").strip().strip("\"'")
    return bool(clean) and "://" not in clean


def run_mode(run_data: dict[str, Any]) -> str:
    clean_mode = str(run_data.get("run_mode", "")).strip().lower()
    if clean_mode in {"local", "url", "discord"}:
        return clean_mode
    if is_local_source_path(run_data.get("source_path", "")):
        return "local"
    if str(run_data.get("source_path", "")).strip():
        return "url"
    if str(run_data.get("discord_reference", "")).strip():
        return "discord"
    return "local"


def is_local_run(run_data: dict[str, Any]) -> bool:
    return run_mode(run_data) == "local" and is_local_source_path(run_data.get("source_path", ""))


def artifact_has_content(run_data: dict[str, Any], artifact_id: str) -> bool:
    artifact = run_data.get("artifacts", {}).get(artifact_id, {})
    return bool(str(artifact.get("text", "")).strip() or str(artifact.get("path", "")).strip())


def packaging_ready(run_data: dict[str, Any]) -> bool:
    return all(artifact_has_content(run_data, artifact_id) for artifact_id in PACKAGING_ARTIFACT_IDS)


def gate1_ready(run_data: dict[str, Any]) -> bool:
    return artifact_has_content(run_data, "title") and artifact_has_content(run_data, "thumbnail_text")


def gate2_ready(run_data: dict[str, Any]) -> bool:
    if is_local_run(run_data):
        return bool(str(run_data.get("selected_clip_name", "")).strip())
    return artifact_has_content(run_data, "clips")


def has_delivery_receipt(run_data: dict[str, Any]) -> bool:
    return any(
        delivery.get("external_id") or delivery.get("url") or delivery.get("status") in {"posted", "verified"}
        for delivery in run_data.get("deliveries", {}).values()
    )


def progress_steps(run_data: dict[str, Any], proxy_job: dict[str, Any]) -> tuple[list[dict[str, str]], int]:
    state = run_data["current_state"]
    runner_status = str(proxy_job.get("status", "")).strip().lower()
    if not is_local_run(run_data):
        steps = [
            {"id": "prep", "label": "Prep", "status": "pending"},
            {"id": "review", "label": "Review", "status": "pending"},
            {"id": "publish", "label": "Publish", "status": "pending"},
            {"id": "done", "label": "Done", "status": "pending"},
        ]
        if state in {"initialized", "gate1_waiting", "gate1_approved", "metadata_ready"}:
            steps[0]["status"] = "active"
        elif state in {"gate2_waiting", "gate2_approved", "ready_to_publish", "publish_pending", "public_verified", "done"}:
            steps[0]["status"] = "complete"
        if state == "gate2_waiting":
            steps[1]["status"] = "active"
        elif state in {"gate2_approved", "ready_to_publish", "publish_pending", "public_verified", "done"}:
            steps[1]["status"] = "complete"
        if state in {"gate2_approved", "ready_to_publish", "publish_pending", "public_verified"}:
            steps[2]["status"] = "active"
        elif state == "done":
            steps[2]["status"] = "complete"
        if state == "done":
            steps[3]["status"] = "complete"
        complete_count = sum(1 for step in steps if step["status"] == "complete")
        if state == "done":
            complete_count = len(steps)
        return steps, complete_count

    steps = [
        {"id": "start", "label": "Start", "status": "pending"},
        {"id": "gate1", "label": "Gate 1", "status": "pending"},
        {"id": "package", "label": "Package", "status": "pending"},
        {"id": "clips", "label": "Clip", "status": "pending"},
        {"id": "publish", "label": "Publish", "status": "pending"},
        {"id": "done", "label": "Done", "status": "pending"},
    ]
    if state in {"initialized", "transcribing"} or runner_status in {"queued", "running"}:
        steps[0]["status"] = "active"
    else:
        steps[0]["status"] = "complete"
    if state == "gate1_waiting":
        steps[1]["status"] = "active"
    elif state not in {"initialized", "transcribing"}:
        steps[1]["status"] = "complete"
    if state in {"gate1_approved", "metadata_ready"}:
        steps[2]["status"] = "active"
    elif state in {"gate2_waiting", "gate2_approved", "ready_to_publish", "publish_pending", "public_verified", "done"}:
        steps[2]["status"] = "complete"
    if state == "gate2_waiting":
        steps[3]["status"] = "active"
    elif state in {"gate2_approved", "ready_to_publish", "publish_pending", "public_verified", "done"}:
        steps[3]["status"] = "complete"
    elif state in {"metadata_ready"}:
        steps[3]["status"] = "skipped"
    if state in {"gate2_approved", "ready_to_publish", "publish_pending", "public_verified"}:
        steps[4]["status"] = "active"
    elif state == "done":
        steps[4]["status"] = "complete"
    if state == "done":
        steps[5]["status"] = "complete"
    complete_count = sum(1 for step in steps if step["status"] == "complete")
    if state == "done":
        complete_count = len(steps)
    return steps, complete_count


def guided_actions_for_run(run_data: dict[str, Any], state_labels: dict[str, str]) -> list[dict[str, Any]]:
    latest = podcast_tracker.latest_gate_decisions(run_data)
    state = run_data["current_state"]
    run_metrics = podcast_tracker.build_run_metrics(run_data)
    local_source = is_local_run(run_data)
    transcript_ready = artifact_has_content(run_data, "transcript")
    actions: list[dict[str, Any]] = []

    def add(
        action_id: str,
        label: str,
        help_text: str,
        section: str,
        button_type: str = "secondary",
        disabled: bool = False,
    ) -> None:
        actions.append(
            {
                "id": action_id,
                "label": label,
                "help": help_text,
                "section": section,
                "type": button_type,
                "disabled": disabled,
            }
        )

    if state == "initialized":
        if local_source:
            add("start_local_transcript", "1. Run Transcript Step", "Start the local runner and let background sync import the result.", "Overview", "primary")
        else:
            add("transcript_ready", "1. Transcript Ready", "Save the transcript artifact first, then use this to move to Gate 1.", "Artifacts", "primary", disabled=not transcript_ready)
    elif state == "transcribing":
        add("transcript_ready", "1. Transcript Ready", "Save the transcript artifact first, then use this to move to Gate 1.", "Artifacts", "primary", disabled=not transcript_ready)
        add("block_run", "Block Run", "Use only if the run hits a real manual blocker.", "Activity")
    elif state == "gate1_waiting":
        add("approve_gate1", "1. Approve Gate 1", "Approve Gate 1 after the title and thumbnail picks are saved.", "Approvals", "primary", disabled=not gate1_ready(run_data))
        add("gate1_changes", "Need Changes", "Keep the run in Gate 1 while fixes happen.", "Approvals")
        add("block_run", "Block Run", "Use if the run cannot continue without manual help.", "Activity")
    elif state == "gate1_approved":
        add("metadata_ready", "1. Metadata Ready", "All packaging inputs are ready for the next phase.", "Artifacts", "primary", disabled=not packaging_ready(run_data))
        add("tweet_waiting", "Waiting On Tweet", "Use if the tweet is the only missing packaging piece.", "Artifacts")
        add("thumbnail_waiting", "Waiting On Thumbnail", "Use if the thumbnail is the current blocker.", "Artifacts")
    elif state == "metadata_ready":
        add("start_gate2", "1. Start Gate 2 Review", "Move into the final package review.", "Approvals", "primary", disabled=not packaging_ready(run_data))
        add("block_run", "Block Run", "Use if packaging found a manual blocker.", "Activity")
    elif state == "tweet_waiting":
        add("tweet_ready", "1. Tweet Ready", "Clear the tweet blocker and return to packaging ready.", "Artifacts", "primary")
        add("block_run", "Block Run", "Use if tweet work is manually blocked.", "Activity")
    elif state == "thumbnail_waiting":
        add("thumbnail_ready", "1. Thumbnail Ready", "Clear the thumbnail blocker and return to packaging ready.", "Artifacts", "primary")
        add("block_run", "Block Run", "Use if thumbnail work is manually blocked.", "Activity")
    elif state == "gate2_waiting":
        gate2_help = "Pick and save a local clip first before approving Gate 2." if local_source else "Save reviewed clip notes first before approving Gate 2."
        add("approve_gate2", "1. Approve Gate 2", gate2_help if not gate2_ready(run_data) else "Record final approval before publish prep.", "Approvals", "primary", disabled=not gate2_ready(run_data))
        add("gate2_changes", "Kick Back To Packaging", "Send the run back for packaging fixes.", "Approvals")
        add("block_run", "Block Run", "Use if Gate 2 found a hard blocker.", "Activity")
    elif state == "gate2_approved":
        add("mark_ready_to_publish", "1. Ready To Publish", "The package is approved and can move to publish prep.", "Delivery & Verify", "primary")
    elif state == "ready_to_publish":
        add("start_publish", "1. Start Publish", "Use when the publish step begins.", "Delivery & Verify", "primary")
    elif state == "publish_pending":
        add(
            "mark_public_verified",
            "1. Public Checks Passed",
            "Complete the verification checklist and record at least one delivery receipt before using this.",
            "Delivery & Verify",
            "primary",
            disabled=not (run_metrics["verified_checks"] == run_metrics["verification_total"] and has_delivery_receipt(run_data)),
        )
        add("mark_retry", "Needs Retry", "Use if the release hit a publish problem.", "Delivery & Verify")
        add("block_run", "Block Run", "Use if the publish issue needs manual intervention.", "Activity")
    elif state == "release_retry":
        add("retry_running", "1. Retry Running", "Move back into publish pending when the retry starts.", "Delivery & Verify", "primary")
        add("block_run", "Block Run", "Use if the retry is blocked manually.", "Activity")
    elif state == "public_verified":
        done_ready = run_metrics["verified_checks"] == run_metrics["verification_total"] and (not run_metrics["requires_sync"] or run_metrics["sync_status"] == "fresh")
        done_help = "This only unlocks after verification is complete."
        if run_metrics["requires_sync"]:
            done_help = "This only unlocks after verification is complete and Discord sync is fresh."
        add("mark_done", "1. Mark Done", done_help, "Delivery & Verify", "primary", disabled=not done_ready)
    elif state == "blocked_manual_fix":
        blocked_from_state = run_data.get("blocked_from_state", "").strip()
        if local_source and blocked_from_state in {"initialized", "transcribing"}:
            add("restart_transcript_step", "1. Run Transcript Step", "Rerun the transcript step after the blocker is fixed.", "Overview", "primary")
        elif local_source and blocked_from_state in {"metadata_ready", "gate2_waiting"}:
            add("restart_clip_step", "1. Run Clip Step", "Rerun the clip step after the blocker is fixed.", "Overview", "primary")
        elif blocked_from_state and blocked_from_state != "blocked_manual_fix":
            resume_section = {
                "gate1_waiting": "Approvals",
                "metadata_ready": "Artifacts",
                "tweet_waiting": "Artifacts",
                "thumbnail_waiting": "Artifacts",
                "gate2_waiting": "Approvals",
                "publish_pending": "Delivery & Verify",
                "release_retry": "Delivery & Verify",
            }.get(blocked_from_state, "Overview")
            resume_label = state_labels.get(blocked_from_state, blocked_from_state).replace("Waiting", "Review")
            add("resume_previous_state", f"1. Resume {resume_label}", "Return HQ to the exact state that was blocked.", resume_section, "primary")
        elif latest.get("gate2") and latest["gate2"]["decision"] == "approved":
            add("resume_publish_retry", "1. Resume Publish Retry", "Use after the blocker is fixed and publish work can continue.", "Delivery & Verify", "primary")
        elif latest.get("gate1") and latest["gate1"]["decision"] == "approved":
            add("resume_packaging", "1. Resume Packaging", "Go back to packaging after the blocker is fixed.", "Artifacts", "primary")
            add("resume_gate2", "Resume Gate 2 Review", "Use if you are ready to re-open Gate 2.", "Approvals")
        else:
            add("resume_gate1", "1. Resume Gate 1 Review", "Go back to Gate 1 after the blocker is fixed.", "Approvals", "primary")
    elif state == "done":
        add("sync_now", "Sync Checkpoint", "Record one last HQ sync note if you need it.", "Activity", "primary")

    return actions
