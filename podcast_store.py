import json
import re
from pathlib import Path
from typing import Any

import podcast_event_log
import podcast_tracker


LEGACY_STORE_FILENAME = "podcast_runs.json"
RUNS_DIRNAME = "podcast_runs"
MANIFEST_FILENAME = "manifest.json"
RUNS_SUBDIRNAME = "runs"
SNAPSHOT_FILENAME = "store_snapshot.json"


def safe_run_id(run_id: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "_", str(run_id or "").strip()) or "unknown"


def legacy_store_path(data_dir: Path) -> Path:
    return data_dir / LEGACY_STORE_FILENAME


def runs_root(data_dir: Path) -> Path:
    return data_dir / RUNS_DIRNAME


def manifest_path(data_dir: Path) -> Path:
    return runs_root(data_dir) / MANIFEST_FILENAME


def snapshot_path(data_dir: Path) -> Path:
    return runs_root(data_dir) / SNAPSHOT_FILENAME


def run_file_path(data_dir: Path, run_id: str) -> Path:
    return runs_root(data_dir) / RUNS_SUBDIRNAME / f"{safe_run_id(run_id)}.json"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    temp_path.replace(path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_local_store_raw(data_dir: Path) -> tuple[dict[str, Any], str]:
    event_store, event_error, _batch_ids = podcast_event_log.load_local_store_from_event_log(data_dir)
    if _batch_ids and not event_error:
        return event_store, ""

    manifest = manifest_path(data_dir)
    if manifest.exists():
        try:
            manifest_data = _read_json(manifest)
            run_ids = [str(item).strip() for item in manifest_data.get("run_ids", []) if str(item).strip()]
            runs = []
            for run_id in run_ids:
                run_path = run_file_path(data_dir, run_id)
                if run_path.exists():
                    runs.append(_read_json(run_path))
            store = {
                "runs": runs,
                "active_run_id": str(manifest_data.get("active_run_id", "")).strip(),
                "updated_at": str(manifest_data.get("updated_at", "")).strip(),
            }
            normalized = podcast_tracker.normalize_podcast_store(store)
            if event_error:
                return normalized, event_error
            return normalized, ""
        except Exception as exc:
            return podcast_tracker.empty_podcast_store(), f"Local per-run podcast store could not be parsed: {exc}"

    legacy_path = legacy_store_path(data_dir)
    if not legacy_path.exists():
        return podcast_tracker.empty_podcast_store(), event_error
    try:
        normalized = podcast_tracker.normalize_podcast_store(_read_json(legacy_path))
        if event_error:
            return normalized, event_error
        return normalized, ""
    except Exception as exc:
        return podcast_tracker.empty_podcast_store(), f"Local podcast backup could not be parsed: {exc}"


def write_local_store(store: dict[str, Any], data_dir: Path) -> dict[str, Any]:
    normalized = podcast_tracker.normalize_podcast_store(store)
    previous_store, _previous_error, previous_batch_ids = podcast_event_log.load_local_store_from_event_log(data_dir)
    force_full_snapshot = not previous_batch_ids
    batch = podcast_event_log.build_event_batch(normalized, previous_store, force_full_snapshot=force_full_snapshot)
    if batch:
        podcast_event_log.append_local_event_batch(
            data_dir,
            batch=batch,
            previous_batch_ids=previous_batch_ids,
            active_run_id=normalized.get("active_run_id", ""),
            updated_at=normalized.get("updated_at", ""),
        )

    root = runs_root(data_dir)
    runs_dir = root / RUNS_SUBDIRNAME
    runs_dir.mkdir(parents=True, exist_ok=True)
    expected_files = set()
    run_ids = []
    for run_data in normalized.get("runs", []):
        run_id = str(run_data.get("id", "")).strip()
        if not run_id:
            continue
        run_ids.append(run_id)
        path = run_file_path(data_dir, run_id)
        expected_files.add(path.name)
        _write_json(path, run_data)

    for existing in runs_dir.glob("*.json"):
        if existing.name not in expected_files:
            existing.unlink(missing_ok=True)

    manifest = {
        "version": 2,
        "active_run_id": normalized.get("active_run_id", ""),
        "updated_at": normalized.get("updated_at", ""),
        "run_ids": run_ids,
    }
    _write_json(manifest_path(data_dir), manifest)
    _write_json(snapshot_path(data_dir), normalized)
    _write_json(legacy_store_path(data_dir), normalized)
    return normalized
