import json
from typing import Any, Callable

import podcast_event_log
import podcast_store
import podcast_tracker


LEGACY_REMOTE_FILENAME = "hq_podcast_runs.json"
REMOTE_EVENT_MANIFEST_FILENAME = "hq_podcast_event_manifest.json"
REMOTE_EVENT_BATCH_PREFIX = "hq_podcast_event__"
REMOTE_MANIFEST_FILENAME = "hq_podcast_runs_manifest.json"
REMOTE_SNAPSHOT_FILENAME = "hq_podcast_runs_snapshot.json"
REMOTE_RUN_PREFIX = "hq_podcast_run__"


def remote_event_manifest_filename() -> str:
    return REMOTE_EVENT_MANIFEST_FILENAME


def remote_event_batch_filename(batch_id: str) -> str:
    return podcast_event_log.event_batch_filename(batch_id, prefix=REMOTE_EVENT_BATCH_PREFIX)


def remote_manifest_filename() -> str:
    return REMOTE_MANIFEST_FILENAME


def remote_snapshot_filename() -> str:
    return REMOTE_SNAPSHOT_FILENAME


def remote_run_filename(run_id: str) -> str:
    return f"{REMOTE_RUN_PREFIX}{podcast_store.safe_run_id(run_id)}.json"


def has_remote_manifest(files: dict[str, Any]) -> bool:
    return bool(files.get(remote_manifest_filename()))


def has_remote_event_manifest(files: dict[str, Any]) -> bool:
    return bool(files.get(remote_event_manifest_filename()))


def remote_file_content(file_meta: dict[str, Any], fetch_text: Callable[[str], str]) -> str:
    inline_content = file_meta.get("content")
    if inline_content is not None and not file_meta.get("truncated"):
        return str(inline_content)
    raw_url = str(file_meta.get("raw_url", "")).strip()
    if raw_url:
        return fetch_text(raw_url)
    return ""


def load_remote_store_bundle_from_files(
    files: dict[str, Any],
    *,
    fetch_text: Callable[[str], str],
) -> tuple[dict[str, Any], str, dict[str, Any]]:
    event_store, event_error, event_batch_ids = podcast_event_log.load_store_from_event_files(
        files,
        manifest_filename=remote_event_manifest_filename(),
        batch_prefix=REMOTE_EVENT_BATCH_PREFIX,
        fetch_text=fetch_text,
    )
    if event_batch_ids and not event_error:
        return event_store, "", {
            "has_event_manifest": True,
            "event_batch_ids": event_batch_ids,
            "has_run_manifest": has_remote_manifest(files),
        }

    manifest_meta = files.get(remote_manifest_filename(), {})
    if manifest_meta:
        try:
            manifest = json.loads(remote_file_content(manifest_meta, fetch_text) or "{}")
            run_ids = [str(item).strip() for item in manifest.get("run_ids", []) if str(item).strip()]
            runs: list[dict[str, Any]] = []
            for run_id in run_ids:
                run_meta = files.get(remote_run_filename(run_id), {})
                if not run_meta:
                    continue
                run_text = remote_file_content(run_meta, fetch_text)
                if run_text:
                    runs.append(json.loads(run_text))
            store = {
                "runs": runs,
                "active_run_id": str(manifest.get("active_run_id", "")).strip(),
                "updated_at": str(manifest.get("updated_at", "")).strip(),
            }
            normalized = podcast_tracker.normalize_podcast_store(store)
            return normalized, event_error, {
                "has_event_manifest": bool(event_batch_ids),
                "event_batch_ids": event_batch_ids,
                "has_run_manifest": True,
            }
        except Exception as exc:
            return podcast_tracker.empty_podcast_store(), f"Remote per-run podcast store could not be parsed: {exc}", {
                "has_event_manifest": bool(event_batch_ids),
                "event_batch_ids": event_batch_ids,
                "has_run_manifest": True,
            }

    legacy_meta = files.get(LEGACY_REMOTE_FILENAME, {})
    if legacy_meta:
        try:
            normalized = podcast_tracker.normalize_podcast_store(json.loads(remote_file_content(legacy_meta, fetch_text)))
            return normalized, event_error, {
                "has_event_manifest": bool(event_batch_ids),
                "event_batch_ids": event_batch_ids,
                "has_run_manifest": False,
            }
        except Exception as exc:
            return podcast_tracker.empty_podcast_store(), f"Legacy remote podcast store could not be parsed: {exc}", {
                "has_event_manifest": bool(event_batch_ids),
                "event_batch_ids": event_batch_ids,
                "has_run_manifest": False,
            }

    return podcast_tracker.empty_podcast_store(), event_error, {
        "has_event_manifest": bool(event_batch_ids),
        "event_batch_ids": event_batch_ids,
        "has_run_manifest": False,
    }


def load_remote_store_from_files(
    files: dict[str, Any],
    *,
    fetch_text: Callable[[str], str],
) -> tuple[dict[str, Any], str]:
    store, error, _meta = load_remote_store_bundle_from_files(files, fetch_text=fetch_text)
    return store, error


def build_remote_files_payload(
    store: dict[str, Any],
    *,
    previous_store: dict[str, Any] | None = None,
    previous_event_batch_ids: list[str] | None = None,
    include_snapshot: bool = True,
    force_all_runs: bool = False,
) -> dict[str, Any]:
    normalized = podcast_tracker.normalize_podcast_store(store)
    previous = podcast_tracker.normalize_podcast_store(previous_store or podcast_tracker.empty_podcast_store())
    batch_ids = [str(item).strip() for item in (previous_event_batch_ids or []) if str(item).strip()]
    force_full_snapshot = force_all_runs or not batch_ids
    batch = podcast_event_log.build_event_batch(normalized, previous, force_full_snapshot=force_full_snapshot)

    previous_runs = {
        str(run.get("id", "")).strip(): run
        for run in previous.get("runs", [])
        if str(run.get("id", "")).strip()
    }
    files: dict[str, Any] = {}
    if batch:
        files[remote_event_batch_filename(batch["id"])] = {"content": json.dumps(batch, indent=2, default=str)}
        batch_ids = batch_ids + [batch["id"]]
    if batch_ids:
        files[remote_event_manifest_filename()] = {
            "content": json.dumps(
                podcast_event_log.event_manifest_payload(
                    batch_ids=batch_ids,
                    active_run_id=normalized.get("active_run_id", ""),
                    updated_at=normalized.get("updated_at", ""),
                ),
                indent=2,
                default=str,
            )
        }

    run_ids: list[str] = []
    for run in normalized.get("runs", []):
        run_id = str(run.get("id", "")).strip()
        if not run_id:
            continue
        run_ids.append(run_id)
        if not force_all_runs and previous_runs.get(run_id) == run:
            continue
        files[remote_run_filename(run_id)] = {"content": json.dumps(run, indent=2, default=str)}

    manifest = {
        "version": 2,
        "active_run_id": normalized.get("active_run_id", ""),
        "updated_at": normalized.get("updated_at", ""),
        "run_ids": run_ids,
    }
    files[remote_manifest_filename()] = {"content": json.dumps(manifest, indent=2, default=str)}
    if include_snapshot:
        files[remote_snapshot_filename()] = {"content": json.dumps(normalized, indent=2, default=str)}
    return files
