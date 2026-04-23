import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

import podcast_tracker

DEFAULT_GIST_ID = os.environ.get("HQ_GIST_ID", "15fb167bbbfdaa79d5ce11c266c3f652")
DEFAULT_GITHUB_PAT = os.environ.get("HQ_GITHUB_PAT", "")
DEFAULT_DATA_DIR = Path(os.environ.get("HQ_DATA_DIR", os.path.expanduser("~/.openclaw/workspace-omaha/data")))
DEFAULT_DATA_DIR.mkdir(parents=True, exist_ok=True)
PODCAST_STORE_FILENAME = "podcast_runs.json"
PODCAST_GIST_FILENAME = "hq_podcast_runs.json"
_EARLY_LOCAL_STATES = {"initialized", "transcribing", "blocked_manual_fix"}
_POST_GATE1_STATES = {
    "gate1_waiting",
    "gate1_approved",
    "metadata_ready",
    "gate2_waiting",
    "gate2_approved",
    "ready_to_publish",
    "publish_pending",
    "public_verified",
    "done",
}


def podcast_store_path(data_dir: Path | None = None) -> Path:
    root = Path(data_dir or DEFAULT_DATA_DIR)
    root.mkdir(parents=True, exist_ok=True)
    return root / PODCAST_STORE_FILENAME


def gist_headers(github_pat: str | None = None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "mount-polumbus-hq-podcast-sync",
    }
    token = str(github_pat if github_pat is not None else DEFAULT_GITHUB_PAT).strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


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


def artifact_has_content(run_data: dict[str, Any], artifact_id: str) -> bool:
    artifact = run_data.get("artifacts", {}).get(artifact_id, {})
    return bool(str(artifact.get("text", "")).strip() or str(artifact.get("path", "")).strip())


def filtered_clip_files(raw_clip_files: list[dict[str, Any]] | None, cached_clip_files: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    clip_candidates = list(raw_clip_files or [])
    if not clip_candidates and cached_clip_files:
        clip_candidates = list(cached_clip_files or [])
    normalized: list[dict[str, Any]] = []
    for item in clip_candidates:
        if not isinstance(item, dict):
            continue
        clip_name = str(item.get("name", "")).strip()
        clip_path = str(item.get("path", "")).strip()
        if not (clip_name and clip_path):
            continue
        normalized.append(
            {
                "name": clip_name,
                "path": clip_path,
                "size_bytes": int(item.get("size_bytes", 0) or 0),
                "modified_at": str(item.get("modified_at", "")).strip(),
                "duration_seconds": float(item.get("duration_seconds", 0.0) or 0.0),
                "is_final": bool(item.get("is_final", False)),
                "is_vertical": bool(item.get("is_vertical", False)),
                "group_key": str(item.get("group_key", "")).strip() or clip_name.lower(),
            }
        )
    if not normalized:
        return []
    preferred = [item for item in normalized if item.get("is_final")]
    source_items = preferred or normalized
    grouped: dict[str, dict[str, Any]] = {}
    for item in source_items:
        group_key = item.get("group_key") or item["name"].lower()
        existing = grouped.get(group_key)
        if not existing:
            grouped[group_key] = item
            continue
        existing_score = (
            1 if existing.get("is_final") else 0,
            existing.get("duration_seconds", 0.0),
            existing.get("size_bytes", 0),
        )
        candidate_score = (
            1 if item.get("is_final") else 0,
            item.get("duration_seconds", 0.0),
            item.get("size_bytes", 0),
        )
        if candidate_score > existing_score:
            grouped[group_key] = item
    return sorted(
        grouped.values(),
        key=lambda item: (
            0 if item.get("is_final") else 1,
            abs(float(item.get("duration_seconds", 0.0) or 0.0) - 45.0),
            -int(item.get("size_bytes", 0) or 0),
            item["name"].lower(),
        ),
    )


def load_local_store_raw(*, data_dir: Path | None = None) -> tuple[dict[str, Any], str]:
    path = podcast_store_path(data_dir)
    if not path.exists():
        return podcast_tracker.empty_podcast_store(), ""
    try:
        return json.loads(path.read_text(encoding="utf-8")), ""
    except Exception as exc:
        return podcast_tracker.empty_podcast_store(), f"Local podcast backup could not be parsed: {exc}"


def write_local_store(store: dict[str, Any], *, data_dir: Path | None = None) -> dict[str, Any]:
    normalized = podcast_tracker.normalize_podcast_store(store)
    path = podcast_store_path(data_dir)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(normalized, indent=2, default=str), encoding="utf-8")
    temp_path.replace(path)
    return normalized


def load_remote_store_raw(*, gist_id: str | None = None, github_pat: str | None = None) -> tuple[dict[str, Any], str]:
    token = str(github_pat if github_pat is not None else DEFAULT_GITHUB_PAT).strip()
    if not token:
        return podcast_tracker.empty_podcast_store(), "HQ_GITHUB_PAT is not configured."
    try:
        active_gist_id = str(gist_id or DEFAULT_GIST_ID).strip()
        req = urllib.request.Request(
            f"https://api.github.com/gists/{active_gist_id}",
            headers=gist_headers(token),
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        file_meta = data.get("files", {}).get(PODCAST_GIST_FILENAME, {})
        if file_meta.get("content") and not file_meta.get("truncated"):
            return json.loads(file_meta.get("content", "")), ""
        raw_url = str(file_meta.get("raw_url", "")).strip()
        if raw_url:
            raw_req = urllib.request.Request(raw_url, headers={"User-Agent": "mount-polumbus-hq-podcast-sync"})
            with urllib.request.urlopen(raw_req, timeout=8) as resp:
                return json.loads(resp.read().decode("utf-8")), ""
        return podcast_tracker.empty_podcast_store(), ""
    except Exception as exc:
        return podcast_tracker.empty_podcast_store(), f"Gist read failed: {exc}"


def save_remote_store(store: dict[str, Any], *, gist_id: str | None = None, github_pat: str | None = None) -> str:
    token = str(github_pat if github_pat is not None else DEFAULT_GITHUB_PAT).strip()
    if not token:
        return "HQ_GITHUB_PAT is not configured."
    normalized = podcast_tracker.normalize_podcast_store(store)
    active_gist_id = str(gist_id or DEFAULT_GIST_ID).strip()
    payload = json.dumps(
        {
            "files": {
                PODCAST_GIST_FILENAME: {
                    "content": json.dumps(normalized, indent=2, default=str),
                }
            }
        }
    ).encode("utf-8")
    try:
        req = urllib.request.Request(
            f"https://api.github.com/gists/{active_gist_id}",
            data=payload,
            headers=gist_headers(token),
            method="PATCH",
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            if int(getattr(resp, "status", 200) or 200) >= 300:
                return f"Gist write failed with HTTP {getattr(resp, 'status', 'unknown')}."
        return ""
    except urllib.error.HTTPError as exc:
        return f"Gist write failed with HTTP {exc.code}."
    except Exception as exc:
        return f"Gist write failed: {exc}"


def load_merged_store(*, data_dir: Path | None = None, gist_id: str | None = None, github_pat: str | None = None) -> tuple[dict[str, Any], dict[str, str]]:
    local_store, local_error = load_local_store_raw(data_dir=data_dir)
    remote_store, remote_error = load_remote_store_raw(gist_id=gist_id, github_pat=github_pat)
    if remote_error:
        merged = podcast_tracker.normalize_podcast_store(local_store)
        source = "local_backup"
    else:
        merged = podcast_tracker.merge_podcast_stores(local_store, remote_store)
        source = "gist"
    return merged, {
        "source": source,
        "local_error": local_error,
        "remote_error": remote_error,
    }


def save_merged_store(store: dict[str, Any], *, data_dir: Path | None = None, gist_id: str | None = None, github_pat: str | None = None) -> tuple[dict[str, Any], dict[str, str]]:
    normalized = podcast_tracker.normalize_podcast_store(store)
    remote_store, remote_error = load_remote_store_raw(gist_id=gist_id, github_pat=github_pat)
    merged = normalized if remote_error else podcast_tracker.merge_podcast_stores(normalized, remote_store)
    write_local_store(merged, data_dir=data_dir)
    remote_error = save_remote_store(merged, gist_id=gist_id, github_pat=github_pat)
    return merged, {"remote_error": remote_error}


def reconcile_proxy_jobs(
    store: dict[str, Any],
    *,
    actor: str,
    load_proxy_job: Callable[[str], dict[str, Any]],
    clip_filter: Callable[[list[dict[str, Any]] | None, list[dict[str, Any]] | None], list[dict[str, Any]]] = filtered_clip_files,
) -> tuple[dict[str, Any], bool, list[str]]:
    updated_store = podcast_tracker.deepcopy_store(store)
    changed = False
    notes: list[str] = []
    for run_data in list(updated_store.get("runs", [])):
        if run_mode(run_data) != "local" or not is_local_source_path(run_data.get("source_path", "")):
            continue
        proxy_job = load_proxy_job(str(run_data.get("id", "")).strip()) or {}
        if not proxy_job:
            continue
        run_id = str(run_data.get("id", "")).strip()
        proxy_status = str(proxy_job.get("status", "")).strip()
        clip_inventory = clip_filter(proxy_job.get("clips_files", []), run_data.get("cached_clip_files", []))
        if clip_inventory != run_data.get("cached_clip_files", []):
            podcast_tracker.cache_clip_inventory(updated_store, run_id=run_id, clip_files=clip_inventory)
            run_data = next(item for item in updated_store["runs"] if item["id"] == run_id)
            changed = True
            notes.append(f"{run_id}: refreshed clip inventory")
        transcript_text = str(proxy_job.get("transcript_text", "")).strip()
        transcript_path = str(proxy_job.get("transcript_path", "")).strip()
        chapters_text = str(proxy_job.get("chapters_text", "")).strip()
        chapters_path = str(proxy_job.get("chapters_path", "")).strip()
        clips_dir = str(proxy_job.get("clips_dir", "")).strip()
        if proxy_status == "completed":
            transcript_missing = not artifact_has_content(run_data, "transcript")
            chapters_missing = not artifact_has_content(run_data, "chapters")
            if transcript_text and transcript_missing:
                podcast_tracker.update_artifact(
                    updated_store,
                    run_id=run_id,
                    artifact_id="transcript",
                    actor=actor,
                    text=transcript_text,
                    path=transcript_path,
                    status="draft",
                    notes="Imported automatically from the local HQ podcast runner.",
                )
                run_data = next(item for item in updated_store["runs"] if item["id"] == run_id)
                changed = True
                notes.append(f"{run_id}: imported transcript")
            if (chapters_text or chapters_path) and chapters_missing:
                podcast_tracker.update_artifact(
                    updated_store,
                    run_id=run_id,
                    artifact_id="chapters",
                    actor=actor,
                    text=chapters_text,
                    path=chapters_path,
                    status="draft" if chapters_text else "missing",
                    notes="Imported automatically from the local HQ podcast runner.",
                )
                run_data = next(item for item in updated_store["runs"] if item["id"] == run_id)
                changed = True
                notes.append(f"{run_id}: imported chapters")
            if clips_dir and run_data["artifacts"]["clips"].get("path", "").strip() != clips_dir:
                podcast_tracker.update_artifact(
                    updated_store,
                    run_id=run_id,
                    artifact_id="clips",
                    actor=actor,
                    text=run_data["artifacts"]["clips"].get("text", ""),
                    path=clips_dir,
                    status=run_data["artifacts"]["clips"].get("status", "missing"),
                    notes=run_data["artifacts"]["clips"].get("notes", "") or "Reserved output directory from the local HQ podcast runner.",
                )
                run_data = next(item for item in updated_store["runs"] if item["id"] == run_id)
                changed = True
                notes.append(f"{run_id}: reserved clips directory")
            if transcript_text and run_data.get("current_state", "") in _EARLY_LOCAL_STATES:
                podcast_tracker.transition_run(
                    updated_store,
                    run_id=run_id,
                    actor=actor,
                    state="gate1_waiting",
                    blocker="",
                    note="Local HQ podcast runner completed transcript generation.",
                )
                changed = True
                notes.append(f"{run_id}: advanced to gate1_waiting")
            elif not transcript_text and run_data.get("current_state", "") in {"initialized", "transcribing"} and transcript_missing:
                podcast_tracker.transition_run(
                    updated_store,
                    run_id=run_id,
                    actor=actor,
                    state="blocked_manual_fix",
                    blocker="Local HQ podcast runner completed without a transcript.",
                    note="Runner completed but no transcript text was returned.",
                )
                changed = True
                notes.append(f"{run_id}: blocked because transcript was missing")
        elif proxy_status == "failed" and run_data.get("current_state", "") not in _POST_GATE1_STATES:
            podcast_tracker.transition_run(
                updated_store,
                run_id=run_id,
                actor=actor,
                state="blocked_manual_fix",
                blocker=f"Local HQ podcast runner failed: {proxy_job.get('error', 'Unknown error')}",
                note="Local HQ podcast runner failed during transcription.",
            )
            changed = True
            notes.append(f"{run_id}: marked blocked after proxy failure")
    return updated_store, changed, notes


def run_background_reconcile_pass(
    *,
    actor: str,
    load_proxy_job: Callable[[str], dict[str, Any]],
    clip_filter: Callable[[list[dict[str, Any]] | None, list[dict[str, Any]] | None], list[dict[str, Any]]] = filtered_clip_files,
    data_dir: Path | None = None,
    gist_id: str | None = None,
    github_pat: str | None = None,
) -> dict[str, Any]:
    started_at = time.time()
    merged_store, load_meta = load_merged_store(data_dir=data_dir, gist_id=gist_id, github_pat=github_pat)
    reconciled_store, changed, notes = reconcile_proxy_jobs(
        merged_store,
        actor=actor,
        load_proxy_job=load_proxy_job,
        clip_filter=clip_filter,
    )
    save_meta = {"remote_error": ""}
    if changed:
        _, save_meta = save_merged_store(reconciled_store, data_dir=data_dir, gist_id=gist_id, github_pat=github_pat)
    return {
        "changed": changed,
        "notes": notes,
        "source": load_meta.get("source", "local"),
        "local_error": load_meta.get("local_error", ""),
        "remote_error": save_meta.get("remote_error", "") or load_meta.get("remote_error", ""),
        "duration_ms": int((time.time() - started_at) * 1000),
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
