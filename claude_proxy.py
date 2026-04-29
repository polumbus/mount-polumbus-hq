#!/usr/bin/env python3
"""Local Claude proxy server for Streamlit Cloud.

Runs on Tyler's machine, exposes a public URL via SSH tunnel.
Streamlit Cloud sends prompts here; this calls the local Claude CLI (sonnet).

Start: python3 /home/polfam/mount_polumbus_hq/claude_proxy.py
Then run: ssh -R 80:localhost:7821 nokey@localhost.run
"""
import hmac, json, os, subprocess, time, urllib.request, urllib.error, urllib.parse, re, hashlib, threading, sys, site, mimetypes
from datetime import datetime, timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from chatgpt_oauth import call_chatgpt_oauth
import podcast_sync
from anthropic_circuit import (
    DEFAULT_UNAVAILABLE_COOLDOWN,
    block_for as anthropic_block_for,
    get_state as get_anthropic_state,
    is_blocked as anthropic_is_blocked,
    mark_available as anthropic_mark_available,
    mark_probe_attempt as anthropic_mark_probe_attempt,
    mark_rate_limited as anthropic_mark_rate_limited,
    parse_retry_after as anthropic_parse_retry_after,
    should_probe as anthropic_should_probe,
)

_oauth_status = {
    "credentials_found": False,
    "credentials_path": "",
    "last_error": "",
    "last_loaded_at": "",
}


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _load_env_file(path: str) -> None:
    try:
        file_path = Path(path).expanduser()
        if not file_path.exists():
            return
        for raw_line in file_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("export "):
                line = line[7:].strip()
            if "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("\"'")
            if key and value and not os.environ.get(key):
                os.environ[key] = value
    except Exception:
        pass


def _bootstrap_proxy_env() -> None:
    for candidate in (
        "/home/polfam/mount_polumbus_hq/.env.local",
        "~/.config/openclaw/secrets.env",
    ):
        _load_env_file(candidate)


_bootstrap_proxy_env()

CLAUDE_CLI = "/home/polfam/mount_polumbus_hq/scripts/claude-cli"
XURL = "/home/linuxbrew/.linuxbrew/bin/xurl"
def _proxy_api_keys() -> list[str]:
    keys = []
    for env_name in ("HQ_PROXY_KEY", "CLAUDE_PROXY_KEY", "HQ_GITHUB_PAT", "GITHUB_PAT"):
        raw = os.environ.get(env_name, "")
        for part in str(raw or "").split(","):
            key = part.strip()
            if key and key not in keys:
                keys.append(key)
    return keys


PROXY_API_KEYS = _proxy_api_keys()
PROXY_API_KEY = PROXY_API_KEYS[0] if PROXY_API_KEYS else ""
PORT = 7821
CLAUDE_OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"

TWITTER_BEARER = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
GIST_ID = os.environ.get("HQ_GIST_ID", "15fb167bbbfdaa79d5ce11c266c3f652")
GITHUB_PAT = os.environ.get("HQ_GITHUB_PAT", "")
TWITTER_API_IO_KEY = os.environ.get("HQ_TWITTER_API_IO_KEY", "")
PODCAST_JOB_ROOT = Path(os.environ.get("HQ_PODCAST_JOB_ROOT", os.path.expanduser("~/.openclaw/workspace-omaha/data/podcast_jobs")))
PODCAST_JOB_ROOT.mkdir(parents=True, exist_ok=True)
PODCAST_DATA_DIR = Path(os.environ.get("HQ_DATA_DIR", os.path.expanduser("~/.openclaw/workspace-omaha/data")))
PODCAST_DATA_DIR.mkdir(parents=True, exist_ok=True)
PODCAST_WHISPER_MODEL = os.environ.get("HQ_PODCAST_WHISPER_MODEL", "base")
PODCAST_CLIPSAI_PYTHON = os.environ.get("HQ_PODCAST_CLIPSAI_PYTHON", "/home/polfam/.openclaw/clipsai-env/bin/python3")
PODCAST_CLIPSAI_SCRIPT = os.environ.get("HQ_PODCAST_CLIPSAI_SCRIPT", "/home/polfam/.openclaw/scripts/clipsai-pipeline.py")

try:
    _USER_SITE = site.getusersitepackages()
    if _USER_SITE and _USER_SITE not in sys.path:
        sys.path.append(_USER_SITE)
except Exception:
    pass

_cookie_cache = {"auth_token": "", "ct0": "", "fetched_at": 0}
_recovery_thread = None
_podcast_sync_thread = None
_podcast_job_lock = threading.Lock()
_podcast_sync_status_lock = threading.Lock()
_clip_probe_cache = {}
PODCAST_TRANSCRIPTION_STALE_SECONDS = int(os.environ.get("HQ_PODCAST_TRANSCRIPTION_STALE_SECONDS", "7200"))
PODCAST_CLIPS_STALE_SECONDS = int(os.environ.get("HQ_PODCAST_CLIPS_STALE_SECONDS", "5400"))
PODCAST_SYNC_ACTIVE_INTERVAL_SECONDS = int(os.environ.get("HQ_PODCAST_SYNC_ACTIVE_INTERVAL_SECONDS", "3"))
PODCAST_SYNC_IDLE_INTERVAL_SECONDS = int(os.environ.get("HQ_PODCAST_SYNC_IDLE_INTERVAL_SECONDS", "15"))
_podcast_sync_status = {
    "running": False,
    "last_checked_at": "",
    "last_changed_at": "",
    "last_duration_ms": 0,
    "last_error": "",
    "last_notes": [],
    "last_remote_error": "",
    "source": "local",
    "sleep_interval_seconds": PODCAST_SYNC_IDLE_INTERVAL_SECONDS,
}


def _podcast_job_file(run_id: str) -> Path:
    safe_run_id = re.sub(r"[^a-zA-Z0-9_-]", "_", run_id or "")
    return PODCAST_JOB_ROOT / f"{safe_run_id or 'unknown'}.json"


def _load_podcast_job(run_id: str) -> dict:
    job_file = _podcast_job_file(run_id)
    if not job_file.exists():
        return {}
    try:
        return _reap_stale_podcast_job(json.loads(job_file.read_text(encoding="utf-8")))
    except Exception:
        return {}


def _save_podcast_job(job: dict) -> None:
    run_id = str(job.get("run_id", "")).strip()
    if not run_id:
        return
    job_file = _podcast_job_file(run_id)
    temp_file = job_file.with_suffix(job_file.suffix + ".tmp")
    temp_file.write_text(json.dumps(job, indent=2), encoding="utf-8")
    temp_file.replace(job_file)


def _podcast_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _podcast_timestamp_seconds(value: str) -> float:
    raw = str(value or "").strip()
    if not raw:
        return 0.0
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).timestamp()
    except Exception:
        return 0.0


def _reap_stale_podcast_job(job: dict) -> dict:
    if not isinstance(job, dict) or not job.get("run_id"):
        return job or {}
    changed = False
    now_seconds = time.time()
    updated_seconds = _podcast_timestamp_seconds(job.get("updated_at", "")) or _podcast_timestamp_seconds(job.get("started_at", ""))
    clips_updated_seconds = _podcast_timestamp_seconds(job.get("clips_updated_at", "")) or _podcast_timestamp_seconds(job.get("clips_started_at", ""))
    if str(job.get("status", "")).strip() in {"queued", "running"} and updated_seconds and (now_seconds - updated_seconds) > PODCAST_TRANSCRIPTION_STALE_SECONDS:
        job["status"] = "failed"
        job["error"] = "Local HQ podcast runner timed out or was interrupted."
        job["updated_at"] = _podcast_now()
        changed = True
    if str(job.get("clips_status", "")).strip() in {"queued", "running"} and clips_updated_seconds and (now_seconds - clips_updated_seconds) > PODCAST_CLIPS_STALE_SECONDS:
        job["clips_status"] = "failed"
        job["clips_error"] = "Shorts clip generation timed out or was interrupted."
        job["clips_updated_at"] = _podcast_now()
        changed = True
    if changed:
        _save_podcast_job(job)
    return job


def _resolve_podcast_source_path(source_path: str) -> str:
    raw = (source_path or "").strip().strip("\"'")
    if not raw:
        return ""
    windows_drive = re.match(r"^([A-Za-z]):[\\/](.*)$", raw)
    if windows_drive:
        drive = windows_drive.group(1).lower()
        rest = windows_drive.group(2).replace("\\", "/")
        return f"/mnt/{drive}/{rest}"
    if raw.startswith("\\\\"):
        return raw
    if raw.startswith("~"):
        return os.path.expanduser(raw)
    if raw.startswith("/"):
        return raw
    return os.path.abspath(raw)


def _set_podcast_job_state(run_id: str, **updates) -> dict:
    with _podcast_job_lock:
        job = _load_podcast_job(run_id)
        job.update(updates)
        job["run_id"] = run_id
        job["updated_at"] = _podcast_now()
        _save_podcast_job(job)
        return job


def _probe_media_duration(media_path: Path) -> float:
    try:
        stat = media_path.stat()
        cache_key = (str(media_path), int(stat.st_size), int(stat.st_mtime))
        if cache_key in _clip_probe_cache:
            return _clip_probe_cache[cache_key]
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(media_path),
            ],
            capture_output=True,
            text=True,
            timeout=20,
        )
        if result.returncode != 0:
            return 0.0
        duration = round(float((result.stdout or "").strip() or 0.0), 3)
        _clip_probe_cache[cache_key] = duration
        return duration
    except Exception:
        return 0.0


def _podcast_list_clip_files(clips_dir: str) -> list[dict]:
    clips_root = Path(str(clips_dir or "").strip())
    if not clips_root.is_dir():
        return []
    items = []
    for candidate in sorted(
        clips_root.iterdir(),
        key=lambda path: (path.suffix.lower() not in {".mp4", ".mov", ".m4v", ".webm"}, path.name.lower()),
    ):
        if not candidate.is_file() or candidate.suffix.lower() not in {".mp4", ".mov", ".m4v", ".webm"}:
            continue
        try:
            stat = candidate.stat()
        except Exception:
            continue
        clip_stem = candidate.stem.lower()
        group_key = re.sub(r"(_final|_9x16|_vertical)+$", "", clip_stem)
        items.append(
            {
                "name": candidate.name,
                "path": str(candidate),
                "size_bytes": int(stat.st_size),
                "modified_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(stat.st_mtime)),
                "duration_seconds": _probe_media_duration(candidate),
                "is_final": "_final" in clip_stem,
                "is_vertical": "9x16" in clip_stem or "_vertical" in clip_stem,
                "group_key": group_key,
            }
        )
    return items


def _podcast_refresh_clip_index(run_id: str) -> dict:
    job = _load_podcast_job(run_id)
    if not job:
        return {}
    clip_files = _podcast_list_clip_files(str(job.get("clips_dir", "")).strip())
    with _podcast_job_lock:
        job = _load_podcast_job(run_id)
        if not job:
            return {}
        if job.get("clips_files") != clip_files:
            job["clips_files"] = clip_files
            job["clips_updated_at"] = _podcast_now()
            _save_podcast_job(job)
        return job


def _build_chapters_from_segments(segments: list[dict]) -> str:
    if not segments:
        return ""
    chapters = []
    bucket_start = None
    bucket_text = []
    for segment in segments:
        start = float(segment.get("start", 0.0) or 0.0)
        text = str(segment.get("text", "")).strip()
        if bucket_start is None:
            bucket_start = start
        if start - bucket_start >= 300 and bucket_text:
            label = " ".join(bucket_text)[:80].strip() or "Chapter"
            minutes = int(bucket_start // 60)
            seconds = int(bucket_start % 60)
            chapters.append(f"{minutes:02d}:{seconds:02d} {label}")
            bucket_start = start
            bucket_text = []
        if text:
            bucket_text.append(text)
    if bucket_text:
        label = " ".join(bucket_text)[:80].strip() or "Chapter"
        minutes = int((bucket_start or 0) // 60)
        seconds = int((bucket_start or 0) % 60)
        chapters.append(f"{minutes:02d}:{seconds:02d} {label}")
    return "\n".join(chapters[:12])


def _run_podcast_transcription(job_seed: dict) -> None:
    run_id = str(job_seed.get("run_id", "")).strip()
    source_path = str(job_seed.get("source_path", "")).strip()
    resolved_source_path = str(job_seed.get("resolved_source_path", "")).strip()
    if not run_id or not resolved_source_path:
        return
    try:
        from faster_whisper import WhisperModel

        output_dir = PODCAST_JOB_ROOT / run_id
        clips_dir = output_dir / "clips"
        output_dir.mkdir(parents=True, exist_ok=True)
        clips_dir.mkdir(parents=True, exist_ok=True)
        _set_podcast_job_state(
            run_id,
            status="running",
            started_at=job_seed.get("started_at") or _podcast_now(),
            source_path=source_path,
            resolved_source_path=resolved_source_path,
            output_dir=str(output_dir),
            clips_dir=str(clips_dir),
            clips_status=job_seed.get("clips_status", "not_started") or "not_started",
            clips_error=job_seed.get("clips_error", "") or "",
            clips_files=job_seed.get("clips_files", []) or [],
            clips_started_at=job_seed.get("clips_started_at", "") or "",
            clips_updated_at=job_seed.get("clips_updated_at", "") or "",
            clips_log_path=str(output_dir / "clips_pipeline.log"),
            model=PODCAST_WHISPER_MODEL,
            error="",
        )

        model = WhisperModel(PODCAST_WHISPER_MODEL, device="cpu", compute_type="int8")
        segments, info = model.transcribe(
            resolved_source_path,
            vad_filter=True,
            beam_size=5,
        )
        collected_segments = []
        transcript_lines = []
        for seg in segments:
            text = (seg.text or "").strip()
            if not text:
                continue
            item = {
                "start": float(seg.start),
                "end": float(seg.end),
                "text": text,
            }
            collected_segments.append(item)
            transcript_lines.append(text)
        transcript_text = "\n\n".join(transcript_lines).strip()
        chapters_text = _build_chapters_from_segments(collected_segments)

        transcript_path = output_dir / "transcript.txt"
        transcript_path.write_text(transcript_text, encoding="utf-8")
        segments_path = output_dir / "segments.json"
        segments_path.write_text(json.dumps(collected_segments, indent=2), encoding="utf-8")
        chapters_path = output_dir / "chapters.txt"
        chapters_path.write_text(chapters_text, encoding="utf-8")

        _set_podcast_job_state(
            run_id,
            status="completed",
            completed_at=_podcast_now(),
            transcript_text=transcript_text,
            transcript_path=str(transcript_path),
            chapters_text=chapters_text,
            chapters_path=str(chapters_path),
            segments_path=str(segments_path),
            language=getattr(info, "language", "") or "",
            duration=getattr(info, "duration", 0.0) or 0.0,
            segments_count=len(collected_segments),
            clips_status=job_seed.get("clips_status", "not_started") or "not_started",
            clips_error=job_seed.get("clips_error", "") or "",
            clips_files=_podcast_list_clip_files(str(clips_dir)),
            clips_updated_at=_podcast_now(),
        )
    except Exception as exc:
        _set_podcast_job_state(
            run_id,
            status="failed",
            error=str(exc),
        )


def _run_podcast_clip_generation(job_seed: dict) -> None:
    run_id = str(job_seed.get("run_id", "")).strip()
    resolved_source_path = str(job_seed.get("resolved_source_path", "")).strip()
    output_dir = Path(str(job_seed.get("output_dir", "")).strip() or (PODCAST_JOB_ROOT / run_id))
    clips_dir = Path(str(job_seed.get("clips_dir", "")).strip() or (output_dir / "clips"))
    clips_dir.mkdir(parents=True, exist_ok=True)
    log_path = Path(str(job_seed.get("clips_log_path", "")).strip() or (output_dir / "clips_pipeline.log"))
    if not run_id or not resolved_source_path:
        return
    try:
        if not os.path.exists(PODCAST_CLIPSAI_PYTHON):
            raise FileNotFoundError(f"ClipsAI Python not found: {PODCAST_CLIPSAI_PYTHON}")
        if not os.path.exists(PODCAST_CLIPSAI_SCRIPT):
            raise FileNotFoundError(f"ClipsAI script not found: {PODCAST_CLIPSAI_SCRIPT}")
        _set_podcast_job_state(
            run_id,
            clips_status="running",
            clips_error="",
            clips_started_at=_podcast_now(),
            clips_updated_at=_podcast_now(),
            clips_log_path=str(log_path),
        )
        cmd = [
            PODCAST_CLIPSAI_PYTHON,
            PODCAST_CLIPSAI_SCRIPT,
            resolved_source_path,
            "--output-dir",
            str(clips_dir),
            "--max-clips",
            "5",
            "--min-duration",
            "30",
            "--max-duration",
            "80",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
        log_path.write_text(
            (result.stdout or "") + ("\n\n--- STDERR ---\n\n" + result.stderr if result.stderr else ""),
            encoding="utf-8",
        )
        if result.returncode != 0:
            raise RuntimeError((result.stderr or result.stdout or "Clip generation failed").strip())
        clip_files = _podcast_list_clip_files(str(clips_dir))
        if not clip_files:
            raise RuntimeError("Clip generation completed but no video clips were created.")
        _set_podcast_job_state(
            run_id,
            clips_status="completed",
            clips_error="",
            clips_files=clip_files,
            clips_updated_at=_podcast_now(),
        )
    except Exception as exc:
        _set_podcast_job_state(
            run_id,
            clips_status="failed",
            clips_error=str(exc),
            clips_updated_at=_podcast_now(),
        )


def _set_oauth_status(**updates):
    _oauth_status.update({k: v for k, v in updates.items() if v is not None})


def _oauth_credentials_candidates():
    raw_candidates = [
        os.environ.get("CLAUDE_CREDENTIALS_PATH", ""),
        os.environ.get("CLAUDE_CONFIG_DIR", "") and os.path.join(os.environ.get("CLAUDE_CONFIG_DIR", ""), ".credentials.json"),
        os.environ.get("CLAUDE_HOME", "") and os.path.join(os.environ.get("CLAUDE_HOME", ""), ".credentials.json"),
        os.path.expanduser("~/.claude/.credentials.json"),
        "/home/polfam/.claude/.credentials.json",
        "/home/appuser/.claude/.credentials.json",
    ]
    seen = set()
    for candidate in raw_candidates:
        path = str(candidate or "").strip()
        if not path:
            continue
        expanded = os.path.abspath(os.path.expanduser(path))
        if expanded not in seen:
            seen.add(expanded)
            yield expanded


def _safe_oauth_error(exc):
    text = str(exc or "").strip()
    text = re.sub(r"(access[_-]?token|refresh[_-]?token|authorization|bearer)[^\s,;]*", r"\1=[redacted]", text, flags=re.I)
    return text[:240] or exc.__class__.__name__


def _load_oauth_access_token():
    """Read Claude OAuth access token from local credentials file and refresh if needed."""
    searched = []
    try:
        creds_path = ""
        for candidate in _oauth_credentials_candidates():
            searched.append(candidate)
            if os.path.exists(candidate):
                creds_path = candidate
                break
        if not creds_path:
            _set_oauth_status(
                credentials_found=False,
                credentials_path="",
                last_error=f"credentials file not found; searched {', '.join(searched[:4])}",
                last_loaded_at="",
            )
            return ""
        with open(creds_path, "r", encoding="utf-8") as f:
            creds = json.load(f)
        _set_oauth_status(
            credentials_found=True,
            credentials_path=creds_path,
            last_error="",
            last_loaded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        oauth = creds.get("claudeAiOauth", creds)
        access_token = oauth.get("accessToken", "")
        expires_at = oauth.get("expiresAt", 0) or 0
        refresh_token = oauth.get("refreshToken", "")
        if access_token and expires_at and (time.time() * 1000) < (int(expires_at) - 300000):
            return access_token
        if not refresh_token:
            if not access_token:
                _set_oauth_status(last_error="credentials loaded but no accessToken or refreshToken found")
            return access_token

        body = json.dumps({
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CLAUDE_OAUTH_CLIENT_ID,
        }).encode()
        req = urllib.request.Request(
            "https://platform.claude.com/v1/oauth/token",
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "claude-code/2.1.90"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            fresh = json.loads(resp.read())

        fresh_access = fresh.get("access_token") or fresh.get("accessToken") or access_token
        if not fresh_access:
            return access_token

        oauth["accessToken"] = fresh_access
        if fresh.get("refresh_token"):
            oauth["refreshToken"] = fresh["refresh_token"]
        elif fresh.get("refreshToken"):
            oauth["refreshToken"] = fresh["refreshToken"]

        expires_in = fresh.get("expires_in")
        if fresh.get("expiresAt"):
            oauth["expiresAt"] = fresh["expiresAt"]
        elif expires_in:
            oauth["expiresAt"] = int((time.time() + float(expires_in)) * 1000)

        creds["claudeAiOauth"] = oauth
        with open(creds_path, "w", encoding="utf-8") as f:
            json.dump(creds, f, indent=2)
        _set_oauth_status(last_error="", last_loaded_at=datetime.now(timezone.utc).isoformat(timespec="seconds"))
        return fresh_access
    except Exception as exc:
        _set_oauth_status(last_error=_safe_oauth_error(exc))
        return ""


def _call_claude_oauth(prompt, system, max_tokens, model):
    """Direct Claude API fallback using OAuth bearer token."""
    token = _load_oauth_access_token()
    if not token:
        raise Exception("No OAuth token available")

    version = "2.1.86"
    salt = "59cf53e54c78"
    chars = [prompt[p] if p < len(prompt) else "0" for p in [4, 7, 20]]
    short_hash = hashlib.sha256((salt + "".join(chars) + version).encode()).hexdigest()[:3]
    billing_line = f"x-anthropic-billing-header: cc_version={version}.{short_hash}; cc_entrypoint=claude-code; cch=00000;"

    system_array = [{"type": "text", "text": billing_line}]
    if system:
        system_array.append({"type": "text", "text": system, "cache_control": {"type": "ephemeral"}})

    body = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "system": system_array,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages?beta=true",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "claude-code-20250219,oauth-2025-04-20,interleaved-thinking-2025-05-14,context-management-2025-06-27,prompt-caching-scope-2026-01-05,advanced-tool-use-2025-11-20,effort-2025-11-24",
            "User-Agent": f"claude-cli/{version}",
            "x-app": "cli",
            "anthropic-dangerous-direct-browser-access": "true",
            "x-stainless-lang": "js",
            "x-stainless-os": "Linux",
            "x-stainless-arch": "x64",
            "x-stainless-runtime": "node",
            "x-stainless-package-version": "0.74.0",
            "x-stainless-retry-count": "0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            anthropic_mark_rate_limited(
                anthropic_parse_retry_after(getattr(e, "headers", None)),
                source="proxy_oauth",
                error=f"HTTP {e.code}",
            )
        raise
    if data.get("content"):
        anthropic_mark_available("proxy_oauth")
        return data["content"][0].get("text", "").strip()
    raise Exception(f"API error: {data.get('error', data)}")


def _maybe_restore_anthropic():
    if not anthropic_should_probe():
        return
    anthropic_mark_probe_attempt()
    try:
        probe = _call_claude_oauth("Reply with OK only.", "", 8, "claude-sonnet-4-6")
        if probe:
            anthropic_mark_available("proxy_probe")
    except urllib.error.HTTPError as e:
        if e.code == 429:
            anthropic_mark_rate_limited(
                anthropic_parse_retry_after(getattr(e, "headers", None)),
                source="proxy_probe",
                error=f"HTTP {e.code}",
            )
        else:
            anthropic_block_for(DEFAULT_UNAVAILABLE_COOLDOWN, source="proxy_probe", error=str(e))
    except Exception as e:
        anthropic_block_for(DEFAULT_UNAVAILABLE_COOLDOWN, source="proxy_probe", error=str(e))


def _anthropic_recovery_loop():
    while True:
        try:
            _maybe_restore_anthropic()
        except Exception:
            pass
        time.sleep(5)


def _ensure_recovery_thread():
    global _recovery_thread
    if _recovery_thread and _recovery_thread.is_alive():
        return
    _recovery_thread = threading.Thread(
        target=_anthropic_recovery_loop,
        name="anthropic-recovery",
        daemon=True,
    )
    _recovery_thread.start()


def _podcast_sync_status_snapshot() -> dict:
    with _podcast_sync_status_lock:
        return dict(_podcast_sync_status)


def _update_podcast_sync_status(**updates) -> None:
    with _podcast_sync_status_lock:
        _podcast_sync_status.update(updates)


def _podcast_background_sync_once() -> None:
    _update_podcast_sync_status(running=True)
    result = podcast_sync.run_background_reconcile_pass(
        actor="hq_background_sync",
        load_proxy_job=_load_podcast_job,
        clip_filter=podcast_sync.filtered_clip_files,
        data_dir=PODCAST_DATA_DIR,
        gist_id=GIST_ID,
        github_pat=GITHUB_PAT,
    )
    status_updates = {
        "running": False,
        "last_checked_at": result.get("checked_at", ""),
        "last_duration_ms": int(result.get("duration_ms", 0) or 0),
        "last_error": "",
        "last_notes": list(result.get("notes", []))[-8:],
        "last_remote_error": result.get("remote_error", ""),
        "source": result.get("source", "local"),
    }
    if result.get("changed"):
        status_updates["last_changed_at"] = result.get("checked_at", "")
    _update_podcast_sync_status(**status_updates)
    if result.get("notes") or result.get("remote_error"):
        print(
            "[podcast-sync]",
            json.dumps(
                {
                    "changed": bool(result.get("changed")),
                    "notes": result.get("notes", []),
                    "remote_error": result.get("remote_error", ""),
                    "duration_ms": result.get("duration_ms", 0),
                }
            ),
        )


def _podcast_has_active_work() -> bool:
    try:
        for job_file in PODCAST_JOB_ROOT.glob("*.json"):
            try:
                job = _load_podcast_job(job_file.stem)
            except Exception:
                continue
            if str(job.get("status", "")).strip() in {"queued", "running"}:
                return True
            if str(job.get("clips_status", "")).strip() in {"queued", "running"}:
                return True
    except Exception:
        return False
    return False


def _podcast_reconciliation_loop():
    while True:
        try:
            _podcast_background_sync_once()
        except Exception as exc:
            _update_podcast_sync_status(
                running=False,
                last_checked_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                last_error=str(exc),
            )
            print(f"[podcast-sync] background reconciliation failed: {exc}")
        sleep_interval = max(
            2,
            PODCAST_SYNC_ACTIVE_INTERVAL_SECONDS if _podcast_has_active_work() else PODCAST_SYNC_IDLE_INTERVAL_SECONDS,
        )
        _update_podcast_sync_status(sleep_interval_seconds=sleep_interval)
        time.sleep(sleep_interval)


def _ensure_podcast_sync_thread():
    global _podcast_sync_thread
    if _podcast_sync_thread and _podcast_sync_thread.is_alive():
        return
    _podcast_sync_thread = threading.Thread(
        target=_podcast_reconciliation_loop,
        name="podcast-background-sync",
        daemon=True,
    )
    _podcast_sync_thread.start()

def _get_twitter_cookies():
    """Fetch latest Twitter cookies from Gist (synced by Chrome extension)."""
    global _cookie_cache
    if time.time() - _cookie_cache["fetched_at"] < 300 and _cookie_cache["auth_token"]:
        return _cookie_cache["auth_token"], _cookie_cache["ct0"]
    try:
        req = urllib.request.Request(f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {GITHUB_PAT}", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        cookies = json.loads(data["files"]["hq_twitter_cookies.json"]["content"])
        _cookie_cache = {"auth_token": cookies["auth_token"], "ct0": cookies["ct0"], "fetched_at": time.time()}
        return _cookie_cache["auth_token"], _cookie_cache["ct0"]
    except Exception as e:
        print(f"Cookie fetch failed: {e}")
        return _cookie_cache["auth_token"], _cookie_cache["ct0"]

_JS_BUNDLE_URL = None
_QUERY_ID_CACHE = {}

def _get_js_bundle_url():
    global _JS_BUNDLE_URL
    if _JS_BUNDLE_URL:
        return _JS_BUNDLE_URL
    try:
        req = urllib.request.Request("https://x.com/", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode()
        match = re.search(r'src="(https://abs\.twimg\.com/responsive-web/client-web/main\.[^"]+\.js)"', html)
        if match:
            _JS_BUNDLE_URL = match.group(1)
    except Exception:
        pass
    return _JS_BUNDLE_URL

def _get_twitter_queryid(operation):
    try:
        url = _get_js_bundle_url()
        if not url:
            return None
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            js = r.read().decode()
        match = re.search(rf'queryId:"([^"]+)",operationName:"{operation}"', js)
        return match.group(1) if match else None
    except Exception:
        return None

def _twitter_graphql(operation, variables, features=None):
    """Make authenticated Twitter GraphQL call using fresh cookies from Gist."""
    auth_token, ct0 = _get_twitter_cookies()
    if not auth_token or not ct0:
        return False, "No Twitter cookies available — open x.com in Chrome to sync"

    qid = _QUERY_ID_CACHE.get(operation) or _get_twitter_queryid(operation)
    if not qid:
        return False, f"Could not find queryId for {operation}"
    _QUERY_ID_CACHE[operation] = qid

    headers = {
        "Authorization": f"Bearer {TWITTER_BEARER}",
        "x-csrf-token": ct0,
        "Cookie": f"auth_token={auth_token}; ct0={ct0}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
        "Origin": "https://x.com",
        "Referer": "https://x.com/",
    }
    payload = {"variables": variables, "queryId": qid}
    if features:
        payload["features"] = features

    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"https://twitter.com/i/api/graphql/{qid}/{operation}",
        data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return True, r.read().decode()
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as ex:
        return False, str(ex)


def _get_nested(node, *path):
    cur = node
    for key in path:
        if isinstance(cur, dict) and key in cur:
            cur = cur[key]
        else:
            return None
    return cur


def _looks_like_tweet_node(node):
    if not isinstance(node, dict):
        return False
    rest_id = node.get("rest_id")
    if not isinstance(rest_id, str) or not rest_id.isdigit():
        return False
    typename = node.get("__typename", "")
    if isinstance(typename, str) and "Tweet" in typename:
        return True
    legacy = node.get("legacy")
    if isinstance(legacy, dict) and ("full_text" in legacy or "conversation_id_str" in legacy):
        return True
    return False


def _find_first_tweet_node(node):
    """Walk a GraphQL payload and return the first plausible tweet result dict."""
    if isinstance(node, dict):
        if _looks_like_tweet_node(node):
            return node
        for value in node.values():
            found = _find_first_tweet_node(value)
            if found:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_first_tweet_node(item)
            if found:
                return found
    return None


def _extract_screen_name(node):
    if not isinstance(node, dict):
        return ""
    for path in (
        ("core", "user_results", "result", "legacy", "screen_name"),
        ("core", "user_results", "result", "core", "screen_name"),
        ("legacy", "screen_name"),
        ("core", "screen_name"),
    ):
        cur = node
        ok = True
        for key in path:
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                ok = False
                break
        if ok and isinstance(cur, str) and cur:
            return cur
    return ""


def _extract_graphql_error(payload):
    if not isinstance(payload, dict):
        return ""
    errors = payload.get("errors")
    if isinstance(errors, list):
        messages = []
        for item in errors:
            if isinstance(item, dict):
                msg = item.get("message") or item.get("detail")
                if msg:
                    messages.append(str(msg))
            elif item:
                messages.append(str(item))
        if messages:
            return "; ".join(messages[:3])
    return ""


def _extract_created_tweet(payload):
    """Parse CreateTweet/Reply payload into a concrete published tweet result."""
    if not isinstance(payload, dict):
        return {}
    data = payload.get("data", {})
    create = data.get("create_tweet") or data.get("notetweet_create")
    if not isinstance(create, dict):
        return {}
    tweet_node = None
    for path in (
        ("tweet_results", "result"),
        ("tweet_result", "result"),
        ("tweet_results",),
        ("tweet_result",),
        ("tweet",),
    ):
        candidate = _get_nested(create, *path)
        if _looks_like_tweet_node(candidate):
            tweet_node = candidate
            break
    if not tweet_node:
        tweet_node = _find_first_tweet_node(create)
    if not isinstance(tweet_node, dict):
        return {}

    tweet_id = tweet_node.get("rest_id", "")
    screen_name = _extract_screen_name(tweet_node)
    if not screen_name:
        viewer = payload.get("data", {}).get("viewer")
        screen_name = _extract_screen_name(viewer)

    tweet_url = ""
    if tweet_id:
        if screen_name:
            tweet_url = f"https://x.com/{screen_name}/status/{tweet_id}"
        else:
            tweet_url = f"https://x.com/i/web/status/{tweet_id}"

    return {
        "tweet_id": tweet_id,
        "screen_name": screen_name,
        "tweet_url": tweet_url,
    }


def _is_tweet_too_long_error(error_text):
    text = (error_text or "").lower()
    return "bit shorter" in text or "too long" in text or "(186)" in text


def _send_tweet_creation(variables, features):
    """
    Use the same split X web uses: standard posts go through CreateTweet,
    while premium/longform posts go through CreateNoteTweet.
    """
    tweet_text = variables.get("tweet_text", "") or ""
    attempts = []
    if len(tweet_text) > 280:
        attempts.append("CreateNoteTweet")
    attempts.append("CreateTweet")

    tried = set()
    last_error = "Unknown X posting error."
    for operation in attempts:
        if operation in tried:
            continue
        tried.add(operation)
        ok, resp = _twitter_graphql(operation, variables, features)
        if not ok:
            last_error = resp[:200]
            if operation == "CreateTweet" and _is_tweet_too_long_error(last_error) and "CreateNoteTweet" not in tried:
                attempts.append("CreateNoteTweet")
            continue
        try:
            payload = json.loads(resp)
        except Exception:
            return False, "X returned invalid JSON while posting.", operation, None

        created = _extract_created_tweet(payload)
        if created.get("tweet_id"):
            return True, created, operation, payload

        last_error = _extract_graphql_error(payload) or "X did not return a published tweet."
        if operation == "CreateTweet" and _is_tweet_too_long_error(last_error) and "CreateNoteTweet" not in tried:
            attempts.append("CreateNoteTweet")
            continue
    return False, last_error, None, None


def _get_twitter_viewer_identity():
    ok, resp = _twitter_graphql("Viewer", {})
    if not ok:
        return {}
    try:
        payload = json.loads(resp)
    except Exception:
        return {}
    viewer = payload.get("data", {}).get("viewer", {})
    user = viewer.get("user_results", {}).get("result", {})
    screen_name = _extract_screen_name(user) or _extract_screen_name(viewer)
    user_id = ""
    if isinstance(user, dict):
        user_id = user.get("rest_id") or user.get("id") or ""
    return {"screen_name": screen_name, "user_id": user_id}


def _twitterapi_get(path, params):
    """Relay a read request to twitterapi.io from the trusted proxy host."""
    if not TWITTER_API_IO_KEY:
        return False, "HQ_TWITTER_API_IO_KEY is not configured on the proxy host."

    url = f"https://api.twitterapi.io{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    req = urllib.request.Request(
        url,
        headers={"X-API-Key": TWITTER_API_IO_KEY, "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return True, r.read().decode()
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode()[:300]}"
    except Exception as ex:
        return False, str(ex)


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {format % args}")

    def send_json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Proxy-Key, ngrok-skip-browser-warning")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def send_bytes(self, code, body: bytes, content_type: str):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(body))
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Proxy-Key, ngrok-skip-browser-warning")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Proxy-Key, ngrok-skip-browser-warning")
        self.end_headers()

    def _check_auth(self):
        auth = self.headers.get("X-Proxy-Key", "")
        if PROXY_API_KEYS and not any(hmac.compare_digest(auth, key) for key in PROXY_API_KEYS):
            print(f"[auth] forbidden path={self.path} has_key={bool(auth)} configured_keys={len(PROXY_API_KEYS)}")
            self.send_json(403, {"error": "forbidden: proxy key mismatch"})
            return False
        return True

    def do_POST(self):
        if not self._check_auth():
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))

        if self.path == "/sync-cookies":
            auth_token = body.get("auth_token", "")
            ct0 = body.get("ct0", "")
            if auth_token and ct0:
                _cookie_cache["auth_token"] = auth_token
                _cookie_cache["ct0"] = ct0
                _cookie_cache["fetched_at"] = time.time()
                # Persist to Gist
                try:
                    cookie_data = json.dumps({"auth_token": auth_token, "ct0": ct0,
                                              "synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")}).encode()
                    patch_req = urllib.request.Request(
                        f"https://api.github.com/gists/{GIST_ID}",
                        data=json.dumps({"files": {"hq_twitter_cookies.json": {"content": cookie_data.decode()}}}).encode(),
                        headers={"Authorization": f"Bearer {GITHUB_PAT}", "Accept": "application/vnd.github+json",
                                 "Content-Type": "application/json"},
                        method="PATCH"
                    )
                    with urllib.request.urlopen(patch_req, timeout=10):
                        pass
                except Exception as e:
                    print(f"Gist write failed: {e}")
                self.send_json(200, {"ok": True})
            else:
                self.send_json(400, {"error": "missing cookies"})

        elif self.path == "/save-tweet":
            tweet_type = body.get("type", "inspiration")  # inspiration or repurpose
            tweet = body.get("tweet", {})
            tweet["saved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            tweet["source"] = "chrome_extension"
            filename = "hq_inspiration.json" if tweet_type == "inspiration" else "hq_repurpose.json"
            try:
                get_req = urllib.request.Request(f"https://api.github.com/gists/{GIST_ID}",
                    headers={"Authorization": f"Bearer {GITHUB_PAT}", "Accept": "application/vnd.github+json"})
                with urllib.request.urlopen(get_req, timeout=10) as r:
                    gist_data = json.loads(r.read())
                items = []
                if filename in gist_data.get("files", {}):
                    try:
                        items = json.loads(gist_data["files"][filename]["content"])
                    except Exception:
                        pass
                items.append(tweet)
                patch_data = json.dumps({"files": {filename: {"content": json.dumps(items, indent=2)}}}).encode()
                patch_req = urllib.request.Request(f"https://api.github.com/gists/{GIST_ID}",
                    data=patch_data, method="PATCH",
                    headers={"Authorization": f"Bearer {GITHUB_PAT}", "Accept": "application/vnd.github+json",
                             "Content-Type": "application/json"})
                with urllib.request.urlopen(patch_req, timeout=10):
                    pass
                self.send_json(200, {"ok": True})
            except Exception as e:
                self.send_json(500, {"error": str(e)})

        elif self.path == "/tweet/post":
            text = body.get("text", "")
            features = {
                "tweetypie_unmention_optimization_enabled": True,
                "responsive_web_edit_tweet_api_enabled": True,
                "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
                "view_counts_everywhere_api_enabled": True,
                "longform_notetweets_consumption_enabled": True,
                "tweet_awards_web_tipping_enabled": False,
                "longform_notetweets_rich_text_read_enabled": True,
                "longform_notetweets_inline_media_enabled": True,
                "responsive_web_graphql_exclude_directive_enabled": True,
                "verified_phone_label_enabled": False,
                "freedom_of_speech_not_reach_fetch_enabled": True,
                "standardized_nudges_misinfo": True,
                "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
                "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
                "responsive_web_graphql_timeline_navigation_enabled": True,
                "interactive_text_enabled": True,
                "responsive_web_enhance_cards_enabled": False,
            }
            variables = {
                "tweet_text": text,
                "dark_request": False,
                "media": {"media_entities": [], "possibly_sensitive": False},
                "semantic_annotation_ids": [],
            }
            ok, result, operation, _payload = _send_tweet_creation(variables, features)
            if not ok:
                print(f"[tweet/post] failed operation={operation or 'none'} error={str(result)[:200]}")
                self.send_json(500, {"error": str(result)[:200]})
                return

            created = result
            if created.get("tweet_id"):
                if not created.get("screen_name"):
                    created.update(_get_twitter_viewer_identity())
                    tweet_id = created.get("tweet_id", "")
                    screen_name = created.get("screen_name", "")
                    if tweet_id and screen_name:
                        created["tweet_url"] = f"https://x.com/{screen_name}/status/{tweet_id}"
                print(f"[tweet/post] success operation={operation} tweet_id={created.get('tweet_id')} screen_name={created.get('screen_name')}")
                self.send_json(200, {"ok": True, **created})
            else:
                error = "X did not return a published tweet."
                print(f"[tweet/post] publish_missing operation={operation} error={error}")
                self.send_json(500, {"error": error})

        elif self.path == "/tweet/reply":
            tweet_id = body.get("tweet_id", "")
            text = body.get("text", "")
            features = {
                "tweetypie_unmention_optimization_enabled": True,
                "responsive_web_edit_tweet_api_enabled": True,
                "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
                "view_counts_everywhere_api_enabled": True,
                "longform_notetweets_consumption_enabled": True,
                "tweet_awards_web_tipping_enabled": False,
                "longform_notetweets_rich_text_read_enabled": True,
                "longform_notetweets_inline_media_enabled": True,
                "responsive_web_graphql_exclude_directive_enabled": True,
                "verified_phone_label_enabled": False,
                "freedom_of_speech_not_reach_fetch_enabled": True,
                "standardized_nudges_misinfo": True,
                "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
                "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
                "responsive_web_graphql_timeline_navigation_enabled": True,
                "interactive_text_enabled": True,
                "responsive_web_enhance_cards_enabled": False,
            }
            variables = {
                "tweet_text": text,
                "reply": {"in_reply_to_tweet_id": tweet_id, "exclude_reply_user_ids": []},
                "dark_request": False,
                "media": {"media_entities": [], "possibly_sensitive": False},
                "semantic_annotation_ids": [],
            }
            ok, result, operation, _payload = _send_tweet_creation(variables, features)
            if not ok:
                print(f"[tweet/reply] failed operation={operation or 'none'} error={str(result)[:200]}")
                self.send_json(500, {"error": str(result)[:200]})
                return

            created = result
            if created.get("tweet_id"):
                if not created.get("screen_name"):
                    created.update(_get_twitter_viewer_identity())
                    tweet_id = created.get("tweet_id", "")
                    screen_name = created.get("screen_name", "")
                    if tweet_id and screen_name:
                        created["tweet_url"] = f"https://x.com/{screen_name}/status/{tweet_id}"
                print(f"[tweet/reply] success operation={operation} tweet_id={created.get('tweet_id')} screen_name={created.get('screen_name')}")
                self.send_json(200, {"ok": True, **created})
            else:
                error = "X did not return a published reply."
                print(f"[tweet/reply] publish_missing operation={operation} error={error}")
                self.send_json(500, {"error": error})

        elif self.path == "/tweet/like":
            # FavoriteTweet GraphQL requires x-client-transaction-id we can't generate
            # Return ok=True so HQ tracks it locally; user can like directly on X
            self.send_json(200, {"ok": True})

        elif self.path == "/call":
            prompt = body.get("prompt", "")
            system = body.get("system", "")
            model = body.get("model", "claude-sonnet-4-6")
            preliminary_cli_error = ""
            try:
                clean_env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
                cmd = [CLAUDE_CLI, "-p", "--model", model]
                if system:
                    cmd += ["--system-prompt", system]
                result = subprocess.run(
                    cmd,
                    input=prompt, capture_output=True, text=True, timeout=120, env=clean_env,
                )
                if result.returncode == 0 and result.stdout.strip():
                    anthropic_mark_available("proxy_cli")
                    self.send_json(200, {"text": result.stdout.strip(), "route": "proxy_cli"})
                    return
                preliminary_cli_error = result.stderr.strip() or "empty response"
                if "Credit balance is too low" in preliminary_cli_error:
                    anthropic_block_for(DEFAULT_UNAVAILABLE_COOLDOWN, source="proxy_cli", error=preliminary_cli_error)
            except Exception as exc:
                preliminary_cli_error = str(exc)
            _maybe_restore_anthropic()
            if anthropic_is_blocked():
                try:
                    chatgpt_text = call_chatgpt_oauth(prompt, system)
                    self.send_json(200, {"text": chatgpt_text, "fallback": "chatgpt_oauth", "anthropic_state": get_anthropic_state()})
                    return
                except Exception as chatgpt_error:
                    self.send_json(500, {"error": f"CLI: {preliminary_cli_error or 'not available'} | Anthropic blocked | ChatGPT: {str(chatgpt_error)}", "anthropic_state": get_anthropic_state(), "oauth": dict(_oauth_status)})
                    return
            try:
                clean_env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
                cmd = [CLAUDE_CLI, "-p", "--model", model]
                if system:
                    cmd += ["--system-prompt", system]
                result = subprocess.run(
                    cmd,
                    input=prompt, capture_output=True, text=True, timeout=120, env=clean_env,
                )
                if result.returncode == 0 and result.stdout.strip():
                    anthropic_mark_available("proxy_cli")
                    self.send_json(200, {"text": result.stdout.strip()})
                else:
                    cli_error = result.stderr.strip() or "empty response"
                    if "Credit balance is too low" in cli_error:
                        anthropic_block_for(DEFAULT_UNAVAILABLE_COOLDOWN, source="proxy_cli", error=cli_error)
                    try:
                        fallback_text = _call_claude_oauth(prompt, system, 1200, model)
                        if fallback_text:
                            self.send_json(200, {"text": fallback_text, "fallback": "oauth"})
                            return
                    except Exception as oauth_error:
                        try:
                            chatgpt_text = call_chatgpt_oauth(prompt, system)
                            if chatgpt_text:
                                self.send_json(200, {"text": chatgpt_text, "fallback": "chatgpt_oauth"})
                                return
                        except Exception as chatgpt_error:
                            cli_error = f"CLI: {cli_error} | OAuth: {str(oauth_error)} | ChatGPT: {str(chatgpt_error)}"
                    self.send_json(500, {"error": cli_error})
            except subprocess.TimeoutExpired:
                self.send_json(504, {"error": "timeout"})
            except Exception as e:
                try:
                    fallback_text = _call_claude_oauth(prompt, system, 1200, model)
                    if fallback_text:
                        self.send_json(200, {"text": fallback_text, "fallback": "oauth"})
                        return
                except Exception as oauth_error:
                    try:
                        chatgpt_text = call_chatgpt_oauth(prompt, system)
                        if chatgpt_text:
                            self.send_json(200, {"text": chatgpt_text, "fallback": "chatgpt_oauth"})
                            return
                    except Exception as chatgpt_error:
                        self.send_json(500, {"error": f"{str(e)} | OAuth: {str(oauth_error)} | ChatGPT: {str(chatgpt_error)}"})
                        return
                self.send_json(500, {"error": str(e)})

        elif self.path == "/save-tweet-url":
            # iOS Shortcut sends tweet URL → fetch content → save to inspiration Gist
            url = body.get("url", "").strip()
            tweet_type = body.get("type", "inspiration")
            match = re.search(r'/status/(\d+)', url)
            if not match:
                self.send_json(400, {"error": "no tweet ID in URL"})
                return
            tweet_id = match.group(1)
            tweet_data = {"tweet_url": url, "tweet_id": tweet_id, "text": "", "author": "", "handle": ""}

            # Fetch tweet content from twitterapi.io
            if TWITTER_API_IO_KEY:
                try:
                    api_req = urllib.request.Request(
                        f"https://api.twitterapi.io/twitter/tweets?tweet_ids={tweet_id}",
                        headers={"X-API-Key": TWITTER_API_IO_KEY}
                    )
                    with urllib.request.urlopen(api_req, timeout=15) as r:
                        api_data = json.loads(r.read())
                    tweets = api_data.get("data", [])
                    if tweets:
                        t = tweets[0]
                        author = t.get("author", {})
                        tweet_data["text"] = t.get("text", "")
                        tweet_data["author"] = author.get("name", "")
                        tweet_data["handle"] = "@" + author.get("userName", "")
                        tweet_data["likes"] = t.get("likeCount", 0)
                        tweet_data["retweets"] = t.get("retweetCount", 0)
                except Exception as e:
                    print(f"Tweet fetch failed: {e}")

            tweet_data["saved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            tweet_data["source"] = "ios_shortcut"
            filename = "hq_inspiration.json" if tweet_type == "inspiration" else "hq_repurpose.json"
            try:
                get_req = urllib.request.Request(f"https://api.github.com/gists/{GIST_ID}",
                    headers={"Authorization": f"Bearer {GITHUB_PAT}", "Accept": "application/vnd.github+json"})
                with urllib.request.urlopen(get_req, timeout=10) as r:
                    gist_data = json.loads(r.read())
                items = []
                if filename in gist_data.get("files", {}):
                    try:
                        items = json.loads(gist_data["files"][filename]["content"])
                    except Exception:
                        pass
                items.append(tweet_data)
                patch_data = json.dumps({"files": {filename: {"content": json.dumps(items, indent=2)}}}).encode()
                patch_req = urllib.request.Request(f"https://api.github.com/gists/{GIST_ID}",
                    data=patch_data, method="PATCH",
                    headers={"Authorization": f"Bearer {GITHUB_PAT}", "Accept": "application/vnd.github+json",
                             "Content-Type": "application/json"})
                with urllib.request.urlopen(patch_req, timeout=10):
                    pass
                author_str = tweet_data.get("handle") or "tweet"
                self.send_json(200, {"ok": True, "saved": author_str, "text": tweet_data["text"][:80]})
            except Exception as e:
                self.send_json(500, {"error": str(e)})

        elif self.path == "/podcast/start":
            run_id = str(body.get("run_id", "")).strip()
            source_path = str(body.get("source_path", "")).strip()
            title = str(body.get("title", "")).strip()
            force = bool(body.get("force", False))
            if not run_id or not source_path:
                self.send_json(400, {"error": "run_id and source_path are required"})
                return
            resolved_source_path = _resolve_podcast_source_path(source_path)
            if not resolved_source_path or not os.path.exists(resolved_source_path):
                self.send_json(404, {"error": f"Source file not found on proxy host: {resolved_source_path or source_path}"})
                return
            with _podcast_job_lock:
                existing = _load_podcast_job(run_id)
                if existing and existing.get("status") in {"queued", "running"}:
                    message = "Job already running"
                    if force:
                        message = "Job is already running and cannot be restarted until it finishes"
                    self.send_json(200, {"ok": True, "job": existing, "accepted": False, "message": message})
                    return
                if existing and existing.get("clips_status") in {"queued", "running"}:
                    message = "Shorts clip generation is still running for this run"
                    self.send_json(200, {"ok": True, "job": existing, "accepted": False, "message": message})
                    return
                job = {
                    "run_id": run_id,
                    "title": title,
                    "source_path": source_path,
                    "resolved_source_path": resolved_source_path,
                    "status": "queued",
                    "created_at": existing.get("created_at") if existing else _podcast_now(),
                    "started_at": "",
                    "updated_at": _podcast_now(),
                    "error": "",
                    "clips_status": existing.get("clips_status", "not_started") if existing else "not_started",
                    "clips_error": existing.get("clips_error", "") if existing else "",
                    "clips_files": existing.get("clips_files", []) if existing else [],
                    "clips_started_at": existing.get("clips_started_at", "") if existing else "",
                    "clips_updated_at": existing.get("clips_updated_at", "") if existing else "",
                    "clips_log_path": str((PODCAST_JOB_ROOT / run_id / "clips_pipeline.log")),
                }
                _save_podcast_job(job)
            worker = threading.Thread(
                target=_run_podcast_transcription,
                args=(job,),
                name=f"podcast-{run_id}",
                daemon=True,
            )
            worker.start()
            self.send_json(200, {"ok": True, "accepted": True, "job": _podcast_refresh_clip_index(run_id) or _load_podcast_job(run_id)})

        elif self.path == "/podcast/generate-clips":
            run_id = str(body.get("run_id", "")).strip()
            force = bool(body.get("force", False))
            if not run_id:
                self.send_json(400, {"error": "run_id is required"})
                return
            with _podcast_job_lock:
                job = _load_podcast_job(run_id)
                if not job:
                    self.send_json(404, {"error": "Podcast job not found"})
                    return
                if str(job.get("status", "")).strip() != "completed":
                    self.send_json(409, {"error": "Transcription must complete before clips can be generated"})
                    return
                existing_status = str(job.get("clips_status", "")).strip()
                if existing_status in {"queued", "running"}:
                    message = "Clip generation already running"
                    if force:
                        message = "Clip generation is already running and cannot be restarted until it finishes"
                    self.send_json(200, {"ok": True, "accepted": False, "job": _podcast_refresh_clip_index(run_id) or job, "message": message})
                    return
                clips_dir = Path(str(job.get("clips_dir", "")).strip() or (PODCAST_JOB_ROOT / run_id / "clips"))
                clips_dir.mkdir(parents=True, exist_ok=True)
                job = _set_podcast_job_state(
                    run_id,
                    clips_status="queued",
                    clips_error="",
                    clips_files=job.get("clips_files", []),
                    clips_started_at="",
                    clips_updated_at=_podcast_now(),
                )
            worker = threading.Thread(
                target=_run_podcast_clip_generation,
                args=(job,),
                name=f"podcast-clips-{run_id}",
                daemon=True,
            )
            worker.start()
            self.send_json(200, {"ok": True, "accepted": True, "job": _podcast_refresh_clip_index(run_id) or _load_podcast_job(run_id)})

        else:
            self.send_json(404, {"error": "not found"})

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/health":
            if not self._check_auth():
                return
            _maybe_restore_anthropic()
            self.send_json(
                200,
                {
                    "status": "ok",
                    "anthropic_state": get_anthropic_state(),
                    "oauth": dict(_oauth_status),
                    "podcast_sync": _podcast_sync_status_snapshot(),
                },
            )
        elif parsed.path in {
            "/twitter/user/info",
            "/twitter/tweet/advanced_search",
            "/twitter/list/tweets_timeline",
            "/twitter/tweets",
        }:
            if not self._check_auth():
                return

            query = {
                key: values[-1]
                for key, values in urllib.parse.parse_qs(parsed.query, keep_blank_values=False).items()
                if values
            }
            ok, resp = _twitterapi_get(parsed.path, query)
            if not ok:
                self.send_json(503, {"error": resp})
                return

            try:
                payload = json.loads(resp)
            except Exception:
                self.send_json(500, {"error": "Proxy upstream returned invalid JSON."})
                return

            self.send_json(200, payload)
        elif parsed.path == "/podcast/status":
            if not self._check_auth():
                return
            query = urllib.parse.parse_qs(parsed.query, keep_blank_values=False)
            run_id = (query.get("run_id") or [""])[-1].strip()
            if not run_id:
                self.send_json(400, {"error": "run_id is required"})
                return
            job = _podcast_refresh_clip_index(run_id) or _load_podcast_job(run_id)
            if not job:
                self.send_json(404, {"error": "Podcast job not found"})
                return
            self.send_json(200, {"ok": True, "job": job})
        elif parsed.path == "/podcast/status-batch":
            if not self._check_auth():
                return
            query = urllib.parse.parse_qs(parsed.query, keep_blank_values=False)
            run_ids = [str(item).strip() for item in (query.get("run_id") or []) if str(item).strip()]
            if not run_ids:
                self.send_json(400, {"error": "run_id is required"})
                return
            jobs = {}
            for run_id in run_ids[:25]:
                job = _podcast_refresh_clip_index(run_id) or _load_podcast_job(run_id)
                if job:
                    jobs[run_id] = job
            self.send_json(200, {"ok": True, "jobs": jobs})
        elif parsed.path == "/podcast/reconcile-status":
            if not self._check_auth():
                return
            self.send_json(200, {"ok": True, "sync": _podcast_sync_status_snapshot()})
        elif parsed.path == "/podcast/clips":
            if not self._check_auth():
                return
            query = urllib.parse.parse_qs(parsed.query, keep_blank_values=False)
            run_id = (query.get("run_id") or [""])[-1].strip()
            if not run_id:
                self.send_json(400, {"error": "run_id is required"})
                return
            job = _podcast_refresh_clip_index(run_id) or _load_podcast_job(run_id)
            if not job:
                self.send_json(404, {"error": "Podcast job not found"})
                return
            self.send_json(
                200,
                {
                    "ok": True,
                    "run_id": run_id,
                    "clips_status": job.get("clips_status", "not_started"),
                    "clips_error": job.get("clips_error", ""),
                    "clips_dir": job.get("clips_dir", ""),
                    "clips": job.get("clips_files", []),
                },
            )
        elif parsed.path == "/podcast/clip":
            if not self._check_auth():
                return
            query = urllib.parse.parse_qs(parsed.query, keep_blank_values=False)
            run_id = (query.get("run_id") or [""])[-1].strip()
            clip_name = (query.get("clip_name") or [""])[-1].strip()
            if not run_id or not clip_name:
                self.send_json(400, {"error": "run_id and clip_name are required"})
                return
            job = _podcast_refresh_clip_index(run_id) or _load_podcast_job(run_id)
            if not job:
                self.send_json(404, {"error": "Podcast job not found"})
                return
            target = next((item for item in job.get("clips_files", []) if item.get("name") == clip_name), None)
            if not target:
                self.send_json(404, {"error": "Clip not found"})
                return
            clip_path = Path(str(target.get("path", "")).strip())
            if not clip_path.is_file():
                self.send_json(404, {"error": "Clip file is missing on the proxy host"})
                return
            try:
                body = clip_path.read_bytes()
            except Exception as exc:
                self.send_json(500, {"error": str(exc)})
                return
            content_type = mimetypes.guess_type(str(clip_path))[0] or "video/mp4"
            self.send_bytes(200, body, content_type)
        else:
            self.send_json(404, {"error": "not found"})


if __name__ == "__main__":
    if not PROXY_API_KEYS:
        print("WARNING: HQ_PROXY_KEY not set — proxy is unprotected!")
    elif len(PROXY_API_KEYS) > 1:
        print(f"Proxy auth loaded {len(PROXY_API_KEYS)} accepted keys")
    _ensure_recovery_thread()
    _ensure_podcast_sync_thread()
    server = ThreadedHTTPServer(("0.0.0.0", PORT), ProxyHandler)
    print(f"Claude proxy listening on port {PORT}")
    print("To expose publicly: ssh -R 80:localhost:7821 nokey@localhost.run")
    server.serve_forever()
