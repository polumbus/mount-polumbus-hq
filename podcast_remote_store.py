import json
from typing import Any, Callable

import podcast_store
import podcast_tracker


LEGACY_REMOTE_FILENAME = "hq_podcast_runs.json"
REMOTE_MANIFEST_FILENAME = "hq_podcast_runs_manifest.json"
REMOTE_SNAPSHOT_FILENAME = "hq_podcast_runs_snapshot.json"
REMOTE_RUN_PREFIX = "hq_podcast_run__"


def remote_manifest_filename() -> str:
    return REMOTE_MANIFEST_FILENAME


def remote_snapshot_filename() -> str:
    return REMOTE_SNAPSHOT_FILENAME


def remote_run_filename(run_id: str) -> str:
    return f"{REMOTE_RUN_PREFIX}{podcast_store.safe_run_id(run_id)}.json"


def has_remote_manifest(files: dict[str, Any]) -> bool:
    return bool(files.get(remote_manifest_filename()))


def remote_file_content(file_meta: dict[str, Any], fetch_text: Callable[[str], str]) -> str:
    inline_content = file_meta.get("content")
    if inline_content is not None and not file_meta.get("truncated"):
        return str(inline_content)
    raw_url = str(file_meta.get("raw_url", "")).strip()
    if raw_url:
        return fetch_text(raw_url)
    return ""


def load_remote_store_from_files(
    files: dict[str, Any],
    *,
    fetch_text: Callable[[str], str],
) -> tuple[dict[str, Any], str]:
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
            return podcast_tracker.normalize_podcast_store(store), ""
        except Exception as exc:
            return podcast_tracker.empty_podcast_store(), f"Remote per-run podcast store could not be parsed: {exc}"

    legacy_meta = files.get(LEGACY_REMOTE_FILENAME, {})
    if legacy_meta:
        try:
            return podcast_tracker.normalize_podcast_store(json.loads(remote_file_content(legacy_meta, fetch_text))), ""
        except Exception as exc:
            return podcast_tracker.empty_podcast_store(), f"Legacy remote podcast store could not be parsed: {exc}"

    return podcast_tracker.empty_podcast_store(), ""


def build_remote_files_payload(
    store: dict[str, Any],
    *,
    previous_store: dict[str, Any] | None = None,
    include_snapshot: bool = True,
    force_all_runs: bool = False,
) -> dict[str, Any]:
    normalized = podcast_tracker.normalize_podcast_store(store)
    previous = podcast_tracker.normalize_podcast_store(previous_store or podcast_tracker.empty_podcast_store())

    previous_runs = {
        str(run.get("id", "")).strip(): run
        for run in previous.get("runs", [])
        if str(run.get("id", "")).strip()
    }
    files: dict[str, Any] = {}
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
