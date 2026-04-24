import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import podcast_tracker


LOCAL_EVENT_LOG_DIRNAME = "podcast_event_log"
LOCAL_EVENT_MANIFEST_FILENAME = "manifest.json"
LOCAL_EVENT_BATCHES_SUBDIRNAME = "batches"
EVENT_BATCH_PREFIX = "event_batch__"
EVENT_LOG_VERSION = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def event_batch_filename(batch_id: str, *, prefix: str = EVENT_BATCH_PREFIX) -> str:
    return f"{prefix}{str(batch_id or '').strip()}.json"


def local_event_root(data_dir: Path) -> Path:
    return data_dir / LOCAL_EVENT_LOG_DIRNAME


def local_event_manifest_path(data_dir: Path) -> Path:
    return local_event_root(data_dir) / LOCAL_EVENT_MANIFEST_FILENAME


def local_event_batch_path(data_dir: Path, batch_id: str) -> Path:
    return local_event_root(data_dir) / LOCAL_EVENT_BATCHES_SUBDIRNAME / event_batch_filename(batch_id)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    temp_path.replace(path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def event_manifest_payload(*, batch_ids: list[str], active_run_id: str, updated_at: str) -> dict[str, Any]:
    return {
        "version": EVENT_LOG_VERSION,
        "active_run_id": str(active_run_id or "").strip(),
        "updated_at": str(updated_at or "").strip(),
        "batch_ids": [str(batch_id).strip() for batch_id in batch_ids if str(batch_id).strip()],
    }


def build_store_from_batches(
    batches: list[dict[str, Any]],
    *,
    active_run_id: str = "",
    updated_at: str = "",
) -> dict[str, Any]:
    runs_by_id: dict[str, dict[str, Any]] = {}
    active = str(active_run_id or "").strip()
    latest_updated_at = str(updated_at or "").strip()

    for batch in batches:
        batch_created_at = str(batch.get("created_at", "")).strip()
        if batch_created_at:
            latest_updated_at = batch_created_at
        for event in batch.get("events", []) if isinstance(batch.get("events", []), list) else []:
            if not isinstance(event, dict):
                continue
            kind = str(event.get("kind", "")).strip()
            if kind == "upsert_run":
                run_snapshot = event.get("run", {})
                normalized = podcast_tracker.normalize_podcast_store({"runs": [run_snapshot]})
                if normalized["runs"]:
                    run = normalized["runs"][0]
                    runs_by_id[run["id"]] = run
            elif kind == "delete_run":
                run_id = str(event.get("run_id", "")).strip()
                if run_id:
                    runs_by_id.pop(run_id, None)
            elif kind == "set_active_run":
                active = str(event.get("active_run_id", "")).strip()

    return podcast_tracker.normalize_podcast_store(
        {
            "runs": list(runs_by_id.values()),
            "active_run_id": active,
            "updated_at": latest_updated_at,
        }
    )


def build_event_batch(
    current_store: dict[str, Any],
    previous_store: dict[str, Any] | None = None,
    *,
    force_full_snapshot: bool = False,
) -> dict[str, Any] | None:
    current = podcast_tracker.normalize_podcast_store(current_store)
    previous = podcast_tracker.normalize_podcast_store(previous_store or podcast_tracker.empty_podcast_store())

    previous_runs = {
        str(run.get("id", "")).strip(): run
        for run in previous.get("runs", [])
        if str(run.get("id", "")).strip()
    }
    current_runs = {
        str(run.get("id", "")).strip(): run
        for run in current.get("runs", [])
        if str(run.get("id", "")).strip()
    }

    events: list[dict[str, Any]] = []
    for run_id in sorted(set(previous_runs) - set(current_runs)):
        events.append({"kind": "delete_run", "run_id": run_id})
    for run_id in sorted(current_runs):
        run_snapshot = current_runs[run_id]
        if force_full_snapshot or previous_runs.get(run_id) != run_snapshot:
            events.append({"kind": "upsert_run", "run_id": run_id, "run": run_snapshot})
    if force_full_snapshot or current.get("active_run_id", "") != previous.get("active_run_id", ""):
        events.append({"kind": "set_active_run", "active_run_id": current.get("active_run_id", "")})

    if not events:
        return None
    return {
        "id": f"evt_{uuid4().hex[:12]}",
        "created_at": str(current.get("updated_at", "")).strip() or _now(),
        "event_count": len(events),
        "events": events,
    }


def load_store_from_event_files(
    files: dict[str, Any],
    *,
    manifest_filename: str,
    batch_prefix: str,
    fetch_text: Callable[[str], str],
) -> tuple[dict[str, Any], str, list[str]]:
    manifest_meta = files.get(manifest_filename, {})
    if not manifest_meta:
        return podcast_tracker.empty_podcast_store(), "", []
    try:
        inline_content = manifest_meta.get("content")
        if inline_content is not None and not manifest_meta.get("truncated"):
            manifest = json.loads(str(inline_content) or "{}")
        else:
            raw_url = str(manifest_meta.get("raw_url", "")).strip()
            manifest = json.loads(fetch_text(raw_url) or "{}") if raw_url else {}
        batch_ids = [str(item).strip() for item in manifest.get("batch_ids", []) if str(item).strip()]
        batches: list[dict[str, Any]] = []
        for batch_id in batch_ids:
            batch_meta = files.get(event_batch_filename(batch_id, prefix=batch_prefix), {})
            if not batch_meta:
                continue
            inline_batch = batch_meta.get("content")
            if inline_batch is not None and not batch_meta.get("truncated"):
                batch = json.loads(str(inline_batch) or "{}")
            else:
                raw_url = str(batch_meta.get("raw_url", "")).strip()
                batch = json.loads(fetch_text(raw_url) or "{}") if raw_url else {}
            batches.append(batch)
        store = build_store_from_batches(
            batches,
            active_run_id=str(manifest.get("active_run_id", "")).strip(),
            updated_at=str(manifest.get("updated_at", "")).strip(),
        )
        return store, "", batch_ids
    except Exception as exc:
        return podcast_tracker.empty_podcast_store(), f"Podcast event log could not be parsed: {exc}", []


def load_local_store_from_event_log(data_dir: Path) -> tuple[dict[str, Any], str, list[str]]:
    manifest_path = local_event_manifest_path(data_dir)
    if not manifest_path.exists():
        return podcast_tracker.empty_podcast_store(), "", []
    try:
        manifest = _read_json(manifest_path)
        batch_ids = [str(item).strip() for item in manifest.get("batch_ids", []) if str(item).strip()]
        batches = []
        for batch_id in batch_ids:
            batch_path = local_event_batch_path(data_dir, batch_id)
            if batch_path.exists():
                batches.append(_read_json(batch_path))
        store = build_store_from_batches(
            batches,
            active_run_id=str(manifest.get("active_run_id", "")).strip(),
            updated_at=str(manifest.get("updated_at", "")).strip(),
        )
        return store, "", batch_ids
    except Exception as exc:
        return podcast_tracker.empty_podcast_store(), f"Local podcast event log could not be parsed: {exc}", []


def append_local_event_batch(
    data_dir: Path,
    *,
    batch: dict[str, Any],
    previous_batch_ids: list[str] | None = None,
    active_run_id: str,
    updated_at: str,
) -> list[str]:
    prior_ids = [str(item).strip() for item in (previous_batch_ids or []) if str(item).strip()]
    batch_id = str(batch.get("id", "")).strip()
    if not batch_id:
        raise ValueError("Event batch is missing an id.")
    if batch_id not in prior_ids:
        prior_ids.append(batch_id)
    _write_json(local_event_batch_path(data_dir, batch_id), batch)
    _write_json(
        local_event_manifest_path(data_dir),
        event_manifest_payload(batch_ids=prior_ids, active_run_id=active_run_id, updated_at=updated_at),
    )
    return prior_ids
