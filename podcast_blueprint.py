"""Structured content for the Post Ascend podcast workflow dashboard."""

from __future__ import annotations


DEFAULT_STATE = "initialized"

_PHASES = [
    {"id": "intake", "label": "Intake", "states": ["initialized", "transcribing"]},
    {"id": "gate1", "label": "Gate 1", "states": ["gate1_waiting", "gate1_approved"]},
    {
        "id": "packaging",
        "label": "Packaging",
        "states": ["metadata_ready", "tweet_waiting", "thumbnail_waiting"],
    },
    {
        "id": "gate2",
        "label": "Gate 2",
        "states": ["gate2_waiting", "gate2_approved", "ready_to_publish"],
    },
    {"id": "publish", "label": "Publish", "states": ["publish_pending", "release_retry"]},
    {"id": "verify", "label": "Verify", "states": ["public_verified", "blocked_manual_fix", "done"]},
]

_VALID_STATES = {state for phase in _PHASES for state in phase["states"]}

_STATE_LABELS = {
    "initialized": "Initialized",
    "transcribing": "Transcribing",
    "gate1_waiting": "Gate 1 Waiting",
    "gate1_approved": "Gate 1 Approved",
    "metadata_ready": "Metadata Ready",
    "tweet_waiting": "Tweet Waiting",
    "thumbnail_waiting": "Thumbnail Waiting",
    "gate2_waiting": "Gate 2 Waiting",
    "gate2_approved": "Gate 2 Approved",
    "ready_to_publish": "Ready To Publish",
    "publish_pending": "Publish Pending",
    "release_retry": "Release Retry",
    "public_verified": "Public Verified",
    "done": "Done",
    "blocked_manual_fix": "Blocked Manual Fix",
}

_NEXT_ACTIONS = {
    "initialized": [
        "Create the run record before any transcript, clip, or publish step starts.",
        "Capture the source episode path and intended publish window.",
        "Keep Discord as the live path while HQ mirrors the workflow state.",
    ],
    "transcribing": [
        "Wait for the transcript artifact and chapter candidates to land.",
        "Keep the latest transcript in one clearly named place so revisions do not get mixed up.",
        "Flag missing timestamps or low-confidence sections before Gate 1.",
    ],
    "gate1_waiting": [
        "Review transcript quality, candidate title angle, and clip-worthiness before moving on.",
        "Record the Gate 1 decision explicitly so reruns do not skip review.",
        "Keep Discord as source of truth for the live run while HQ tracks the same checkpoint.",
    ],
    "gate1_approved": [
        "Generate description, tags, tweet copy, and thumbnail text from the approved inputs.",
        "Keep each approved asset organized so retries use the right version later.",
        "Do not let packaging jobs publish anything yet.",
    ],
    "metadata_ready": [
        "Assemble the YouTube package and social package from approved assets only.",
        "Check every artifact is attached to the run as a saved file or saved text block.",
        "Prepare Gate 2 review rather than publishing immediately.",
    ],
    "tweet_waiting": [
        "Finalize tweet variants and note which one is approved for launch.",
        "Keep external post IDs empty until the publish step actually fires.",
        "Treat this as blocked packaging, not partial success.",
    ],
    "thumbnail_waiting": [
        "Approve thumbnail text and visual direction before upload.",
        "Store the chosen thumbnail path plus alternates for auditability.",
        "Do not mark the run publish-ready until the asset exists.",
    ],
    "gate2_waiting": [
        "Run the final package review across title, description, tags, tweet, and thumbnail together.",
        "Capture approval notes so later retries know what was approved.",
        "Confirm publish order and fallback plan before proceeding.",
    ],
    "gate2_approved": [
        "Set up publish steps with safe retry guardrails for YouTube and X.",
        "Promote the run to ready_to_publish only after approvals are stored.",
        "Keep verification expectations attached to the run before launch.",
    ],
    "ready_to_publish": [
        "Launch YouTube and social tasks from the approved package only.",
        "Write the platform IDs and confirmation details back to the run immediately.",
        "Prepare the verification checklist before calling the run done.",
    ],
    "publish_pending": [
        "Poll for platform processing status and capture external IDs.",
        "Do not treat upload acknowledgement as public verification.",
        "Escalate to release_retry only with the recorded error details.",
    ],
    "release_retry": [
        "Retry only the failed delivery leg using the saved assets and retry guardrails.",
        "Do not regenerate content unless the failure actually invalidated the artifact.",
        "Keep the run blocked until publish verification succeeds.",
    ],
    "public_verified": [
        "Check the public URL, processing state, transcript availability, and social post IDs.",
        "Record the verification timestamp and any residual issues.",
        "Only then promote the run to done.",
    ],
    "done": [
        "Archive the run with full artifact and delivery history intact.",
        "Keep the comparison with Discord for post-run evaluation.",
        "Use the next run to validate what HQ still misses versus Discord.",
    ],
    "blocked_manual_fix": [
        "Surface the blocker clearly with the exact failed step and missing artifact.",
        "Keep manual intervention explicit instead of silently falling through to done.",
        "Resume from the blocked step instead of restarting the whole workflow.",
    ],
}

def _ordered_states() -> list[str]:
    return [state for phase in _PHASES for state in phase["states"]]


PODCAST_STATES = tuple(_ordered_states())


def _validate_blueprint() -> None:
    duplicate_states = sorted({state for state in PODCAST_STATES if PODCAST_STATES.count(state) > 1})
    if duplicate_states:
        raise ValueError(f"Podcast state order contains duplicates: {duplicate_states}")
    label_states = set(_STATE_LABELS)
    action_states = set(_NEXT_ACTIONS)
    if label_states != _VALID_STATES:
        missing = sorted(_VALID_STATES - label_states)
        extra = sorted(label_states - _VALID_STATES)
        raise ValueError(f"Podcast state labels are out of sync. Missing={missing}, Extra={extra}")
    if action_states != _VALID_STATES:
        missing = sorted(_VALID_STATES - action_states)
        extra = sorted(action_states - _VALID_STATES)
        raise ValueError(f"Podcast next actions are out of sync. Missing={missing}, Extra={extra}")


def resolve_podcast_state(current_state: str | None) -> dict[str, str | bool | None]:
    if not current_state:
        return {"state": DEFAULT_STATE, "unknown_input": None, "used_default": True}
    normalized = current_state.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in _STATE_LABELS:
        return {"state": normalized, "unknown_input": None, "used_default": False}
    return {
        "state": DEFAULT_STATE,
        "unknown_input": current_state,
        "used_default": False,
    }


def _phase_statuses(current_state: str) -> list[dict]:
    active_index = 0
    terminal_state = current_state == _PHASES[-1]["states"][-1]
    for index, phase in enumerate(_PHASES):
        if current_state in phase["states"]:
            active_index = index
            break

    statuses = []
    for index, phase in enumerate(_PHASES):
        if terminal_state:
            status = "complete"
        elif index < active_index:
            status = "complete"
        elif index == active_index:
            status = "active"
        else:
            status = "upcoming"
        statuses.append({"label": phase["label"], "status": status})
    return statuses


def get_suggested_next_actions(current_state: str | None = None) -> list[str]:
    state = resolve_podcast_state(current_state)["state"]
    return list(_NEXT_ACTIONS[state])


def get_podcast_dashboard_content(current_state: str | None = None) -> dict:
    resolution = resolve_podcast_state(current_state)
    state = resolution["state"]
    return {
        "current_state": state,
        "current_state_label": _STATE_LABELS[state],
        "unknown_state_input": resolution["unknown_input"],
        "used_default_state": resolution["used_default"],
        "state_options": [
            {"id": state_id, "label": _STATE_LABELS[state_id]}
            for state_id in PODCAST_STATES
        ],
        "phases": _phase_statuses(state),
        "next_actions": get_suggested_next_actions(state),
        "states": list(PODCAST_STATES),
    }


_validate_blueprint()
