"""Durable Podcast run tracker for the HQ side-by-side workflow."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from podcast_blueprint import PODCAST_STATES


STORE_VERSION = 1
MAX_EVENTS = 120
MAX_APPROVALS = 40

ARTIFACT_SPECS = [
    {"id": "transcript", "label": "Transcript", "kind": "text"},
    {"id": "chapters", "label": "Chapters", "kind": "text"},
    {"id": "title", "label": "Approved Title", "kind": "text"},
    {"id": "description", "label": "Description", "kind": "text"},
    {"id": "tags", "label": "Tags", "kind": "text"},
    {"id": "tweet", "label": "Approved Tweet", "kind": "text"},
    {"id": "thumbnail_text", "label": "Thumbnail Text", "kind": "text"},
    {"id": "thumbnail_asset", "label": "Thumbnail Asset", "kind": "path"},
    {"id": "clips", "label": "Shorts Clips", "kind": "text"},
]

APPROVAL_GATES = [
    {"id": "gate1", "label": "Gate 1"},
    {"id": "gate2", "label": "Gate 2"},
]

DELIVERY_SPECS = [
    {"id": "youtube", "label": "YouTube"},
    {"id": "x", "label": "X"},
]

VERIFICATION_CHECKS = [
    {"id": "public_url_checked", "label": "Public URL Checked"},
    {"id": "processing_checked", "label": "Processing Confirmed"},
    {"id": "transcript_checked", "label": "Transcript Available"},
    {"id": "social_ids_checked", "label": "Social IDs Confirmed"},
]

_ARTIFACT_IDS = {spec["id"] for spec in ARTIFACT_SPECS}
_GATE_IDS = {spec["id"] for spec in APPROVAL_GATES}
_DELIVERY_IDS = {spec["id"] for spec in DELIVERY_SPECS}
_VERIFICATION_IDS = {spec["id"] for spec in VERIFICATION_CHECKS}
_VALID_STATES = set(PODCAST_STATES)
_ARTIFACT_STATUSES = {"missing", "draft", "approved", "blocked"}
_DELIVERY_STATUSES = {"not_started", "pending", "posted", "verified", "retry", "failed"}
_APPROVAL_DECISIONS = {"approved", "changes_requested", "blocked"}
ARTIFACT_STATUSES = tuple(sorted(_ARTIFACT_STATUSES))
DELIVERY_STATUSES = tuple(sorted(_DELIVERY_STATUSES))
APPROVAL_DECISIONS = tuple(sorted(_APPROVAL_DECISIONS))
ALLOWED_APPROVAL_STATE_AFTER = {
    "gate1": {
        "approved": ("gate1_approved",),
        "changes_requested": ("initialized", "transcribing", "gate1_waiting"),
        "blocked": ("blocked_manual_fix",),
    },
    "gate2": {
        "approved": ("gate2_approved", "ready_to_publish"),
        "changes_requested": ("metadata_ready", "tweet_waiting", "thumbnail_waiting", "gate2_waiting"),
        "blocked": ("blocked_manual_fix",),
    },
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _timestamp_value(value: Any) -> datetime:
    raw = _sanitize_text(value)
    if not raw:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _artifact_template(spec: dict[str, str]) -> dict[str, Any]:
    return {
        "id": spec["id"],
        "label": spec["label"],
        "kind": spec["kind"],
        "status": "missing",
        "version": 0,
        "text": "",
        "path": "",
        "notes": "",
        "updated_at": "",
        "approved_at": "",
        "approved_by": "",
    }


def _delivery_template(spec: dict[str, str]) -> dict[str, Any]:
    return {
        "id": spec["id"],
        "label": spec["label"],
        "status": "not_started",
        "external_id": "",
        "url": "",
        "notes": "",
        "updated_at": "",
    }


def _verification_template() -> dict[str, Any]:
    checks = {spec["id"]: False for spec in VERIFICATION_CHECKS}
    checks.update({"notes": "", "updated_at": "", "verified_at": ""})
    return checks


def _sanitize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _normalize_local_source(source_path: str) -> str:
    clean = _sanitize_text(source_path).strip("\"'")
    return clean.replace("\\", "/").rstrip("/")


def _suggest_title_from_source(source_path: str) -> str:
    clean = _sanitize_text(source_path)
    if not clean:
        return f"Podcast Intake {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
    if "://" not in clean:
        local_source = _normalize_local_source(clean)
        local_name = local_source.rsplit("/", 1)[-1]
        if "." in local_name:
            local_name = local_name.rsplit(".", 1)[0]
        local_name = local_name.replace("-", " ").replace("_", " ").strip()
        local_name = " ".join(piece for piece in local_name.split() if piece)
        return local_name[:80] if local_name else f"Podcast Intake {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
    try:
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(clean)
        host = parsed.netloc.lower()
        query = parse_qs(parsed.query)
        youtube_id = ""
        if "youtube.com" in host:
            youtube_id = _sanitize_text((query.get("v") or [""])[0])
        elif "youtu.be" in host:
            youtube_id = parsed.path.strip("/").split("/", 1)[0]
        if youtube_id:
            return f"YouTube Intake {youtube_id[:8]} · {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
    except Exception:
        pass
    source_part = clean.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    stem = source_part.rsplit("/", 1)[-1].replace("-", " ").replace("_", " ").strip()
    stem = " ".join(piece for piece in stem.split() if piece)
    if stem.lower() in {"watch", "video", "videos", "shorts"}:
        return f"Podcast Intake {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
    if stem and len(stem) >= 6:
        return stem[:80]
    return f"Podcast Intake {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"


def canonical_source_key(source_path: str) -> str:
    clean = _sanitize_text(source_path)
    if not clean:
        return ""
    if "://" not in clean:
        return _normalize_local_source(clean).lower()
    try:
        from urllib.parse import parse_qs, urlencode, urlparse

        parsed = urlparse(clean)
        host = parsed.netloc.lower().removeprefix("www.")
        query = parse_qs(parsed.query)
        if "youtube.com" in host:
            video_id = _sanitize_text((query.get("v") or [""])[0])
            if video_id:
                return f"youtube:{video_id.lower()}"
        if "youtu.be" in host:
            video_id = parsed.path.strip("/").split("/", 1)[0]
            if video_id:
                return f"youtube:{video_id.lower()}"
        filtered_pairs = []
        for key in sorted(query):
            if key.lower().startswith("utm_") or key.lower() in {"feature", "si"}:
                continue
            for value in sorted(query.get(key, [])):
                filtered_pairs.append((key.lower(), value))
        normalized_query = urlencode(filtered_pairs, doseq=True)
        normalized_path = parsed.path.rstrip("/").lower()
        suffix = f"?{normalized_query}" if normalized_query else ""
        return f"{host}{normalized_path}{suffix}"
    except Exception:
        return clean.lower()


def empty_podcast_store() -> dict[str, Any]:
    return {
        "version": STORE_VERSION,
        "active_run_id": "",
        "updated_at": "",
        "runs": [],
    }


def _normalize_artifact(raw: Any, spec: dict[str, str]) -> dict[str, Any]:
    artifact = _artifact_template(spec)
    if isinstance(raw, dict):
        artifact["status"] = raw.get("status", artifact["status"])
        artifact["version"] = _safe_int(raw.get("version", 0) or 0, 0)
        artifact["text"] = _sanitize_text(raw.get("text", ""))
        artifact["path"] = _sanitize_text(raw.get("path", ""))
        artifact["notes"] = _sanitize_text(raw.get("notes", ""))
        artifact["updated_at"] = _sanitize_text(raw.get("updated_at", ""))
        artifact["approved_at"] = _sanitize_text(raw.get("approved_at", ""))
        artifact["approved_by"] = _sanitize_text(raw.get("approved_by", ""))
    if artifact["status"] not in _ARTIFACT_STATUSES:
        artifact["status"] = "missing"
    if artifact["status"] == "approved" and not artifact["approved_at"]:
        artifact["approved_at"] = artifact["updated_at"] or _now()
    return artifact


def _normalize_delivery(raw: Any, spec: dict[str, str]) -> dict[str, Any]:
    delivery = _delivery_template(spec)
    if isinstance(raw, dict):
        delivery["status"] = raw.get("status", delivery["status"])
        delivery["external_id"] = _sanitize_text(raw.get("external_id", ""))
        delivery["url"] = _sanitize_text(raw.get("url", ""))
        delivery["notes"] = _sanitize_text(raw.get("notes", ""))
        delivery["updated_at"] = _sanitize_text(raw.get("updated_at", ""))
    if delivery["status"] not in _DELIVERY_STATUSES:
        delivery["status"] = "not_started"
    return delivery


def _normalize_approval(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    gate = _sanitize_text(raw.get("gate", "")).lower()
    decision = _sanitize_text(raw.get("decision", "")).lower()
    if gate not in _GATE_IDS or decision not in _APPROVAL_DECISIONS:
        return None
    return {
        "id": _sanitize_text(raw.get("id", "")) or uuid4().hex[:12],
        "gate": gate,
        "decision": decision,
        "notes": _sanitize_text(raw.get("notes", "")),
        "actor": _sanitize_text(raw.get("actor", "")),
        "state_after": _sanitize_text(raw.get("state_after", "")),
        "created_at": _sanitize_text(raw.get("created_at", "")) or _now(),
    }


def _normalize_event(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    return {
        "id": _sanitize_text(raw.get("id", "")) or uuid4().hex[:12],
        "type": _sanitize_text(raw.get("type", "")) or "note",
        "summary": _sanitize_text(raw.get("summary", "")),
        "details": _sanitize_text(raw.get("details", "")),
        "actor": _sanitize_text(raw.get("actor", "")),
        "created_at": _sanitize_text(raw.get("created_at", "")) or _now(),
    }


def _normalize_verification(raw: Any) -> dict[str, Any]:
    verification = _verification_template()
    if isinstance(raw, dict):
        for check_id in _VERIFICATION_IDS:
            verification[check_id] = bool(raw.get(check_id, False))
        verification["notes"] = _sanitize_text(raw.get("notes", ""))
        verification["updated_at"] = _sanitize_text(raw.get("updated_at", ""))
        verification["verified_at"] = _sanitize_text(raw.get("verified_at", ""))
    return verification


def _default_run() -> dict[str, Any]:
    return {
        "id": "",
        "title": "",
        "episode_code": "",
        "source_path": "",
        "discord_reference": "",
        "publish_window": "",
        "source_of_truth": "hq",
        "last_synced_at": "",
        "sync_note": "",
        "blocked_from_state": "",
        "current_state": "initialized",
        "blocker": "",
        "notes": "",
        "created_at": "",
        "updated_at": "",
        "details_updated_at": "",
        "state_updated_at": "",
        "blocker_updated_at": "",
        "artifacts": {spec["id"]: _artifact_template(spec) for spec in ARTIFACT_SPECS},
        "approvals": [],
        "deliveries": {spec["id"]: _delivery_template(spec) for spec in DELIVERY_SPECS},
        "verification": _verification_template(),
        "events": [],
    }


def _sort_runs(store: dict[str, Any]) -> None:
    store["runs"] = sorted(
        store["runs"],
        key=lambda run: (
            _timestamp_value(run.get("updated_at", "")),
            _timestamp_value(run.get("created_at", "")),
        ),
        reverse=True,
    )


def _newer_timestamp(first: str, second: str) -> str:
    return first if _timestamp_value(first) >= _timestamp_value(second) else second


def _merge_records_by_timestamp(first: dict[str, Any], second: dict[str, Any], key: str = "updated_at") -> dict[str, Any]:
    first_ts = _sanitize_text(first.get(key, ""))
    second_ts = _sanitize_text(second.get(key, ""))
    if _timestamp_value(second_ts) > _timestamp_value(first_ts):
        return deepcopy(second)
    return deepcopy(first)


def _merge_run_fields_by_timestamp(
    merged: dict[str, Any],
    primary: dict[str, Any],
    secondary: dict[str, Any],
    *,
    fields: tuple[str, ...],
    timestamp_field: str,
) -> None:
    primary_ts = _sanitize_text(primary.get(timestamp_field, ""))
    secondary_ts = _sanitize_text(secondary.get(timestamp_field, ""))
    winner = secondary if _timestamp_value(secondary_ts) > _timestamp_value(primary_ts) else primary
    for field in fields:
        merged[field] = _sanitize_text(winner.get(field, merged.get(field, "")))
    merged[timestamp_field] = _newer_timestamp(primary_ts, secondary_ts)


def _merge_run_records(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    primary_updated = _sanitize_text(primary.get("updated_at", ""))
    secondary_updated = _sanitize_text(secondary.get("updated_at", ""))
    merged = deepcopy(primary if _timestamp_value(primary_updated) >= _timestamp_value(secondary_updated) else secondary)
    _merge_run_fields_by_timestamp(
        merged,
        primary,
        secondary,
        fields=("title", "episode_code", "source_path", "discord_reference", "publish_window", "notes"),
        timestamp_field="details_updated_at",
    )
    _merge_run_fields_by_timestamp(
        merged,
        primary,
        secondary,
        fields=("blocker", "blocked_from_state"),
        timestamp_field="blocker_updated_at",
    )

    primary_state_ts = _sanitize_text(primary.get("state_updated_at", ""))
    secondary_state_ts = _sanitize_text(secondary.get("state_updated_at", ""))
    if _timestamp_value(secondary_state_ts) > _timestamp_value(primary_state_ts):
        merged["current_state"] = secondary.get("current_state", merged["current_state"])
        merged["state_updated_at"] = secondary_state_ts
    elif primary_state_ts:
        merged["current_state"] = primary.get("current_state", merged["current_state"])
        merged["state_updated_at"] = primary_state_ts

    primary_sync_ts = _sanitize_text(primary.get("last_synced_at", ""))
    secondary_sync_ts = _sanitize_text(secondary.get("last_synced_at", ""))
    if _timestamp_value(secondary_sync_ts) > _timestamp_value(primary_sync_ts):
        merged["last_synced_at"] = secondary.get("last_synced_at", "")
        merged["sync_note"] = secondary.get("sync_note", "")
    elif primary_sync_ts:
        merged["last_synced_at"] = primary.get("last_synced_at", "")
        merged["sync_note"] = primary.get("sync_note", "")

    created_candidates = [ts for ts in (_sanitize_text(primary.get("created_at", "")), _sanitize_text(secondary.get("created_at", ""))) if ts]
    merged["created_at"] = min(created_candidates, key=_timestamp_value) if created_candidates else ""
    merged["updated_at"] = _newer_timestamp(
        _sanitize_text(primary.get("updated_at", "")),
        _sanitize_text(secondary.get("updated_at", "")),
    )
    merged["source_of_truth"] = "discord"

    merged["artifacts"] = {}
    for spec in ARTIFACT_SPECS:
        artifact_id = spec["id"]
        first_artifact = primary.get("artifacts", {}).get(artifact_id, _artifact_template(spec))
        second_artifact = secondary.get("artifacts", {}).get(artifact_id, _artifact_template(spec))
        merged["artifacts"][artifact_id] = _merge_records_by_timestamp(first_artifact, second_artifact, "updated_at")

    merged["deliveries"] = {}
    for spec in DELIVERY_SPECS:
        delivery_id = spec["id"]
        first_delivery = primary.get("deliveries", {}).get(delivery_id, _delivery_template(spec))
        second_delivery = secondary.get("deliveries", {}).get(delivery_id, _delivery_template(spec))
        merged["deliveries"][delivery_id] = _merge_records_by_timestamp(first_delivery, second_delivery, "updated_at")

    merged["verification"] = _merge_records_by_timestamp(
        primary.get("verification", _verification_template()),
        secondary.get("verification", _verification_template()),
        "updated_at",
    )

    approvals_by_id: dict[str, dict[str, Any]] = {}
    for approval in list(primary.get("approvals", [])) + list(secondary.get("approvals", [])):
        approvals_by_id[approval["id"]] = deepcopy(approval)
    merged["approvals"] = sorted(
        approvals_by_id.values(),
        key=lambda item: _timestamp_value(item.get("created_at", "")),
    )[-MAX_APPROVALS:]

    events_by_id: dict[str, dict[str, Any]] = {}
    for event in list(primary.get("events", [])) + list(secondary.get("events", [])):
        events_by_id[event["id"]] = deepcopy(event)
    merged["events"] = sorted(
        events_by_id.values(),
        key=lambda item: _timestamp_value(item.get("created_at", "")),
    )[-MAX_EVENTS:]
    return merged


def normalize_podcast_store(raw: Any) -> dict[str, Any]:
    store = empty_podcast_store()
    if isinstance(raw, dict):
        store["version"] = _safe_int(raw.get("version", STORE_VERSION) or STORE_VERSION, STORE_VERSION)
        store["active_run_id"] = _sanitize_text(raw.get("active_run_id", ""))
        store["updated_at"] = _sanitize_text(raw.get("updated_at", ""))
        raw_runs = raw.get("runs", [])
    else:
        raw_runs = []

    normalized_runs = []
    seen_ids: set[str] = set()
    for raw_run in raw_runs if isinstance(raw_runs, list) else []:
        if not isinstance(raw_run, dict):
            continue
        run = _default_run()
        run["id"] = _sanitize_text(raw_run.get("id", "")) or f"pod_{uuid4().hex[:10]}"
        if run["id"] in seen_ids:
            continue
        seen_ids.add(run["id"])
        for field in (
            "title",
            "episode_code",
            "source_path",
            "discord_reference",
            "publish_window",
            "source_of_truth",
            "last_synced_at",
            "sync_note",
            "blocked_from_state",
            "current_state",
            "blocker",
            "notes",
            "created_at",
            "updated_at",
            "details_updated_at",
            "state_updated_at",
            "blocker_updated_at",
        ):
            run[field] = _sanitize_text(raw_run.get(field, run[field]))
        if run["current_state"] not in _VALID_STATES:
            run["current_state"] = "initialized"
        raw_artifacts = raw_run.get("artifacts", {})
        if not isinstance(raw_artifacts, dict):
            raw_artifacts = {}
        for spec in ARTIFACT_SPECS:
            run["artifacts"][spec["id"]] = _normalize_artifact(
                raw_artifacts.get(spec["id"], {}),
                spec,
            )

        raw_deliveries = raw_run.get("deliveries", {})
        if not isinstance(raw_deliveries, dict):
            raw_deliveries = {}
        for spec in DELIVERY_SPECS:
            run["deliveries"][spec["id"]] = _normalize_delivery(
                raw_deliveries.get(spec["id"], {}),
                spec,
            )

        run["verification"] = _normalize_verification(raw_run.get("verification", {}))

        approvals = []
        for item in raw_run.get("approvals", []) if isinstance(raw_run.get("approvals", []), list) else []:
            approval = _normalize_approval(item)
            if approval:
                approvals.append(approval)
        run["approvals"] = approvals[-MAX_APPROVALS:]

        events = []
        for item in raw_run.get("events", []) if isinstance(raw_run.get("events", []), list) else []:
            event = _normalize_event(item)
            if event:
                events.append(event)
        run["events"] = events[-MAX_EVENTS:]
        if not run["details_updated_at"]:
            detail_events = [event["created_at"] for event in run["events"] if event.get("type") in {"run_created", "run_updated"}]
            run["details_updated_at"] = detail_events[-1] if detail_events else (run["created_at"] or "")
        if not run["blocker_updated_at"] and run["blocker"]:
            blocker_events = [event["created_at"] for event in run["events"] if event.get("type") == "state_changed"]
            run["blocker_updated_at"] = blocker_events[-1] if blocker_events else (run["state_updated_at"] or "")
        normalized_runs.append(run)

    store["runs"] = normalized_runs
    _sort_runs(store)
    if not any(run["id"] == store["active_run_id"] for run in store["runs"]):
        store["active_run_id"] = store["runs"][0]["id"] if store["runs"] else ""
    return store


def merge_podcast_stores(primary: Any, secondary: Any) -> dict[str, Any]:
    first = normalize_podcast_store(primary)
    second = normalize_podcast_store(secondary)
    merged = empty_podcast_store()
    runs_by_id: dict[str, dict[str, Any]] = {}

    for candidate_store in (second, first):
        for run in candidate_store["runs"]:
            existing = runs_by_id.get(run["id"])
            if not existing:
                runs_by_id[run["id"]] = deepcopy(run)
                continue
            runs_by_id[run["id"]] = _merge_run_records(run, existing)

    merged["runs"] = list(runs_by_id.values())
    _sort_runs(merged)
    preferred_active = first.get("active_run_id", "")
    fallback_active = second.get("active_run_id", "")
    if any(run["id"] == preferred_active for run in merged["runs"]):
        merged["active_run_id"] = preferred_active
    elif any(run["id"] == fallback_active for run in merged["runs"]):
        merged["active_run_id"] = fallback_active
    elif merged["runs"]:
        merged["active_run_id"] = merged["runs"][0]["id"]
    merged["updated_at"] = _newer_timestamp(
        _sanitize_text(first.get("updated_at", "")),
        _sanitize_text(second.get("updated_at", "")),
    )
    return merged


def _get_run(store: dict[str, Any], run_id: str) -> dict[str, Any]:
    for run in store["runs"]:
        if run["id"] == run_id:
            return run
    raise KeyError(f"Podcast run not found: {run_id}")


def _touch_run(run: dict[str, Any], at: str | None = None) -> str:
    ts = at or _now()
    run["updated_at"] = ts
    return ts


def _touch_store(store: dict[str, Any], at: str | None = None) -> str:
    ts = at or _now()
    store["updated_at"] = ts
    return ts


def add_event(run: dict[str, Any], actor: str, event_type: str, summary: str, details: str = "") -> None:
    run["events"].append(
        {
            "id": uuid4().hex[:12],
            "type": event_type,
            "summary": summary.strip(),
            "details": details.strip(),
            "actor": actor.strip(),
            "created_at": _now(),
        }
    )
    run["events"] = run["events"][-MAX_EVENTS:]


def create_run(
    store: dict[str, Any],
    *,
    actor: str,
    title: str,
    episode_code: str = "",
    source_path: str = "",
    discord_reference: str = "",
    publish_window: str = "",
    notes: str = "",
) -> dict[str, Any]:
    ts = _now()
    run = _default_run()
    run["id"] = f"pod_{uuid4().hex[:10]}"
    run["title"] = title.strip() or _suggest_title_from_source(source_path)
    run["episode_code"] = episode_code.strip()
    run["source_path"] = source_path.strip()
    run["discord_reference"] = discord_reference.strip()
    run["publish_window"] = publish_window.strip()
    run["notes"] = notes.strip()
    run["source_of_truth"] = "discord" if run["discord_reference"] else "hq"
    run["created_at"] = ts
    run["updated_at"] = ts
    run["details_updated_at"] = ts
    run["state_updated_at"] = ts
    run["blocker_updated_at"] = ts
    add_event(run, actor, "run_created", "Created podcast workflow run", run["title"])
    store["runs"].append(run)
    store["active_run_id"] = run["id"]
    _sort_runs(store)
    _touch_store(store, ts)
    return run


def set_active_run(store: dict[str, Any], run_id: str) -> dict[str, Any]:
    _get_run(store, run_id)
    store["active_run_id"] = run_id
    _touch_store(store)
    return store


def update_run_details(
    store: dict[str, Any],
    *,
    run_id: str,
    actor: str,
    title: str,
    episode_code: str,
    source_path: str,
    discord_reference: str,
    publish_window: str,
    blocker: str,
    notes: str,
) -> dict[str, Any]:
    run = _get_run(store, run_id)
    next_values = {
        "title": title.strip() or run["title"],
        "episode_code": episode_code.strip(),
        "source_path": source_path.strip(),
        "discord_reference": discord_reference.strip(),
        "publish_window": publish_window.strip(),
        "blocker": blocker.strip(),
        "notes": notes.strip(),
    }
    before = {key: run[key] for key in next_values}
    if before == next_values:
        return run
    details_changed = any(before[key] != next_values[key] for key in ("title", "episode_code", "source_path", "discord_reference", "publish_window", "notes"))
    blocker_changed = before["blocker"] != next_values["blocker"]
    run.update(next_values)
    run["source_of_truth"] = "discord" if next_values["discord_reference"] else "hq"
    ts = _touch_run(run)
    if details_changed:
        run["details_updated_at"] = ts
    if blocker_changed:
        run["blocker_updated_at"] = ts
    add_event(run, actor, "run_updated", "Updated HQ run details", run["title"])
    _touch_store(store, ts)
    _sort_runs(store)
    return run


def transition_run(
    store: dict[str, Any],
    *,
    run_id: str,
    actor: str,
    state: str,
    blocker: str = "",
    note: str = "",
) -> dict[str, Any]:
    run = _get_run(store, run_id)
    state = state.strip()
    if state not in _VALID_STATES:
        raise ValueError(f"Invalid podcast state: {state}")
    previous_state = run["current_state"]
    if previous_state == state and run["blocker"] == blocker.strip() and not note.strip():
        return run
    blocker_changed = run["blocker"] != blocker.strip()
    blocked_from_state_changed = False
    if state == "blocked_manual_fix" and previous_state != "blocked_manual_fix":
        run["blocked_from_state"] = previous_state
        blocked_from_state_changed = True
    run["current_state"] = state
    run["blocker"] = blocker.strip()
    ts = _touch_run(run)
    run["state_updated_at"] = ts
    if blocker_changed or blocked_from_state_changed:
        run["blocker_updated_at"] = ts
    add_event(
        run,
        actor,
        "state_changed",
        f"Moved podcast workflow state from {previous_state} to {state}",
        note.strip() or run["blocker"],
    )
    _touch_store(store, ts)
    _sort_runs(store)
    return run


def update_artifact(
    store: dict[str, Any],
    *,
    run_id: str,
    artifact_id: str,
    actor: str,
    text: str = "",
    path: str = "",
    status: str = "draft",
    notes: str = "",
) -> dict[str, Any]:
    if artifact_id not in _ARTIFACT_IDS:
        raise ValueError(f"Unknown artifact: {artifact_id}")
    if status not in _ARTIFACT_STATUSES:
        raise ValueError(f"Unknown artifact status: {status}")
    run = _get_run(store, run_id)
    artifact = run["artifacts"][artifact_id]
    content_changed = (
        artifact["text"] != text.strip()
        or artifact["path"] != path.strip()
        or artifact["notes"] != notes.strip()
        or artifact["status"] != status
    )
    if not content_changed:
        return artifact
    artifact["version"] = _safe_int(artifact.get("version", 0) or 0, 0) + 1
    artifact["text"] = text.strip()
    artifact["path"] = path.strip()
    artifact["notes"] = notes.strip()
    artifact["status"] = status
    artifact["updated_at"] = _now()
    if status == "approved":
        artifact["approved_at"] = artifact["updated_at"]
        artifact["approved_by"] = actor.strip()
    elif status != "approved":
        artifact["approved_at"] = ""
        artifact["approved_by"] = ""
    ts = _touch_run(run, artifact["updated_at"])
    add_event(
        run,
        actor,
        "artifact_saved",
        f"Updated {artifact['label']}",
        f"Status: {status}, version: {artifact['version']}",
    )
    _touch_store(store, ts)
    _sort_runs(store)
    return artifact


def record_approval(
    store: dict[str, Any],
    *,
    run_id: str,
    gate: str,
    decision: str,
    actor: str,
    notes: str = "",
    state_after: str = "",
) -> dict[str, Any]:
    gate = gate.strip().lower()
    decision = decision.strip().lower()
    if gate not in _GATE_IDS:
        raise ValueError(f"Unknown approval gate: {gate}")
    if decision not in _APPROVAL_DECISIONS:
        raise ValueError(f"Unknown approval decision: {decision}")
    allowed_state_after = set(ALLOWED_APPROVAL_STATE_AFTER.get(gate, {}).get(decision, ()))
    if state_after.strip() and state_after.strip() not in allowed_state_after:
        raise ValueError(f"Invalid state_after value for {gate}/{decision}: {state_after}")
    run = _get_run(store, run_id)
    approval = {
        "id": uuid4().hex[:12],
        "gate": gate,
        "decision": decision,
        "notes": notes.strip(),
        "actor": actor.strip(),
        "state_after": state_after.strip(),
        "created_at": _now(),
    }
    run["approvals"].append(approval)
    run["approvals"] = run["approvals"][-MAX_APPROVALS:]
    ts = _touch_run(run, approval["created_at"])
    add_event(
        run,
        actor,
        "approval_recorded",
        f"Recorded {gate.upper()} as {decision.replace('_', ' ')}",
        notes.strip(),
    )
    if state_after.strip():
        blocked_from_state_changed = False
        if state_after.strip() == "blocked_manual_fix" and run["current_state"] != "blocked_manual_fix":
            run["blocked_from_state"] = run["current_state"]
            blocked_from_state_changed = True
        run["current_state"] = state_after.strip()
        run["state_updated_at"] = approval["created_at"]
        if decision == "approved" and state_after.strip() != "blocked_manual_fix":
            run["blocker"] = ""
            run["blocker_updated_at"] = approval["created_at"]
        elif blocked_from_state_changed:
            run["blocker_updated_at"] = approval["created_at"]
    _touch_store(store, ts)
    _sort_runs(store)
    return approval


def update_delivery(
    store: dict[str, Any],
    *,
    run_id: str,
    channel: str,
    actor: str,
    status: str,
    external_id: str = "",
    url: str = "",
    notes: str = "",
) -> dict[str, Any]:
    channel = channel.strip().lower()
    status = status.strip().lower()
    if channel not in _DELIVERY_IDS:
        raise ValueError(f"Unknown delivery channel: {channel}")
    if status not in _DELIVERY_STATUSES:
        raise ValueError(f"Unknown delivery status: {status}")
    run = _get_run(store, run_id)
    delivery = run["deliveries"][channel]
    next_values = {
        "status": status,
        "external_id": external_id.strip(),
        "url": url.strip(),
        "notes": notes.strip(),
    }
    if all(delivery[key] == value for key, value in next_values.items()):
        return delivery
    delivery.update(next_values)
    delivery["updated_at"] = _now()
    ts = _touch_run(run, delivery["updated_at"])
    add_event(
        run,
        actor,
        "delivery_updated",
        f"Updated {delivery['label']} delivery to {status}",
        delivery["external_id"] or delivery["url"] or delivery["notes"],
    )
    _touch_store(store, ts)
    _sort_runs(store)
    return delivery


def update_verification(
    store: dict[str, Any],
    *,
    run_id: str,
    actor: str,
    checks: dict[str, bool],
    notes: str = "",
) -> dict[str, Any]:
    run = _get_run(store, run_id)
    verification = run["verification"]
    next_checks = {check_id: bool(checks.get(check_id, verification[check_id])) for check_id in _VERIFICATION_IDS}
    next_notes = notes.strip()
    if all(verification[check_id] == next_checks[check_id] for check_id in _VERIFICATION_IDS) and verification["notes"] == next_notes:
        return verification
    for check_id in _VERIFICATION_IDS:
        verification[check_id] = next_checks[check_id]
    verification["notes"] = next_notes
    verification["updated_at"] = _now()
    if all(bool(verification[check_id]) for check_id in _VERIFICATION_IDS):
        verification["verified_at"] = verification["updated_at"]
    else:
        verification["verified_at"] = ""
    ts = _touch_run(run, verification["updated_at"])
    add_event(
        run,
        actor,
        "verification_updated",
        "Updated verification checklist",
        verification["notes"],
    )
    _touch_store(store, ts)
    _sort_runs(store)
    return verification


def add_manual_note(store: dict[str, Any], *, run_id: str, actor: str, note: str) -> dict[str, Any]:
    run = _get_run(store, run_id)
    if not note.strip():
        return run
    ts = _touch_run(run)
    add_event(run, actor, "manual_note", "Added HQ operator note", note.strip())
    _touch_store(store, ts)
    _sort_runs(store)
    return run


def record_sync_checkpoint(store: dict[str, Any], *, run_id: str, actor: str, note: str = "") -> dict[str, Any]:
    run = _get_run(store, run_id)
    ts = _now()
    run["last_synced_at"] = ts
    run["sync_note"] = note.strip()
    _touch_run(run, ts)
    add_event(run, actor, "sync_checkpoint", "Recorded Discord sync checkpoint", run["sync_note"])
    _touch_store(store, ts)
    _sort_runs(store)
    return run


def latest_gate_decisions(run: dict[str, Any]) -> dict[str, dict[str, Any] | None]:
    latest = {gate["id"]: None for gate in APPROVAL_GATES}
    for approval in reversed(run.get("approvals", [])):
        gate = approval.get("gate", "")
        if gate in latest and latest[gate] is None:
            latest[gate] = approval
    return latest


def build_run_metrics(run: dict[str, Any]) -> dict[str, Any]:
    artifacts = list(run.get("artifacts", {}).values())
    populated = sum(1 for artifact in artifacts if artifact.get("text") or artifact.get("path"))
    approved = sum(1 for artifact in artifacts if artifact.get("status") == "approved")
    blocked = sum(1 for artifact in artifacts if artifact.get("status") == "blocked")
    deliveries = run.get("deliveries", {})
    verification = run.get("verification", {})
    latest = latest_gate_decisions(run)
    verified_checks = sum(1 for check_id in _VERIFICATION_IDS if verification.get(check_id))
    requires_sync = bool(_sanitize_text(run.get("discord_reference", ""))) or _sanitize_text(run.get("source_of_truth", "")) == "discord"
    sync_status = "hq_only" if not requires_sync else "unsynced"
    sync_age_hours = None
    if requires_sync and run.get("last_synced_at"):
        try:
            sync_dt = _timestamp_value(run["last_synced_at"])
            sync_age_hours = max(0.0, (datetime.now(timezone.utc) - sync_dt).total_seconds() / 3600)
            if sync_age_hours <= 2:
                sync_status = "fresh"
            elif sync_age_hours <= 12:
                sync_status = "aging"
            else:
                sync_status = "stale"
        except Exception:
            sync_status = "unknown"
    return {
        "artifact_total": len(artifacts),
        "artifact_populated": populated,
        "artifact_approved": approved,
        "artifact_blocked": blocked,
        "latest_gate_decisions": latest,
        "youtube_status": deliveries.get("youtube", {}).get("status", "not_started"),
        "x_status": deliveries.get("x", {}).get("status", "not_started"),
        "verified_checks": verified_checks,
        "verification_total": len(_VERIFICATION_IDS),
        "sync_status": sync_status,
        "sync_age_hours": sync_age_hours,
        "requires_sync": requires_sync,
        "last_event": run.get("events", [])[-1] if run.get("events") else None,
    }


def deepcopy_store(store: dict[str, Any]) -> dict[str, Any]:
    return deepcopy(store)
