"""Configuration and safe artifact helpers for the voice profile harness."""

from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


DEFAULT_ROOT = Path("data/creator_evolution/voice_profile")
TWITTER_API_IO_KEY_NAMES = ("TWITTER_API_IO_KEY", "TWITTERAPI_IO_KEY", "X_TWITTERAPI_IO_KEY")
SECRET_PATTERNS = (
    re.compile(r"(api[_-]?key|token|secret|cookie|authorization)\s*[:=]\s*['\"]?([^'\"\s,}]+)", re.I),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]+", re.I),
)
ARTIFACT_DIRS = (
    "raw",
    "cache",
    "analysis",
    "profiles",
    "eval",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def artifact_root(root: str | Path | None = None) -> Path:
    return Path(root or os.environ.get("CE_VOICE_PROFILE_ROOT", str(DEFAULT_ROOT)))


def ensure_artifact_dirs(root: str | Path | None = None) -> Path:
    base = artifact_root(root)
    for rel in ARTIFACT_DIRS:
        (base / rel).mkdir(parents=True, exist_ok=True)
    return base


def artifact_path(relative: str | Path, root: str | Path | None = None) -> Path:
    base = ensure_artifact_dirs(root)
    path = base / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_twitterapiio_key() -> str:
    for name in TWITTER_API_IO_KEY_NAMES:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    secrets_path = Path(".streamlit/secrets.toml")
    if secrets_path.exists():
        try:
            import tomli

            data = tomli.loads(secrets_path.read_text(encoding="utf-8"))
            for name in TWITTER_API_IO_KEY_NAMES:
                value = str(data.get(name, "") or "").strip()
                if value:
                    return value
        except Exception:
            return ""
    return ""


def redact_secrets(value: object) -> str:
    text = str(value)
    text = re.sub(r"Bearer\s+[A-Za-z0-9._\-]+", "Bearer [REDACTED]", text, flags=re.I)
    for pattern in SECRET_PATTERNS:
        if pattern.pattern.startswith("Bearer"):
            text = pattern.sub("Bearer [REDACTED]", text)
        else:
            text = pattern.sub(lambda m: f"{m.group(1)}=[REDACTED]", text)
    for name in TWITTER_API_IO_KEY_NAMES:
        secret = os.environ.get(name, "")
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def read_json(path: str | Path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: str | Path, data) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return path


def read_jsonl(path: str | Path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                rows.append(item)
        except Exception:
            continue
    return rows


def write_jsonl(path: str | Path, rows: Iterable[dict]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, default=str, separators=(",", ":")) + "\n")
    return path


def read_csv_rows(path: str | Path) -> list[dict]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as fh:
        return [dict(row) for row in csv.DictReader(fh)]
