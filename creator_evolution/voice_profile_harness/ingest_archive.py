"""X archive and manual import support for the voice profile harness."""

from __future__ import annotations

import json
import re
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .config import artifact_path, read_csv_rows, write_jsonl
from .normalize import parse_datetime


def _json_from_archive_js(text: str):
    stripped = text.strip()
    if stripped.startswith("["):
        return json.loads(stripped)
    match = re.search(r"=\s*(\[.*\])\s*;?\s*$", stripped, re.S)
    if not match:
        return []
    return json.loads(match.group(1))


def _within_months(raw: dict, months: int) -> bool:
    tweet = raw.get("tweet") if isinstance(raw.get("tweet"), dict) else raw
    created = parse_datetime(tweet.get("created_at") or tweet.get("createdAt") or tweet.get("created_at_utc"))
    if not created:
        return True
    return created >= datetime.now(timezone.utc) - timedelta(days=max(1, months) * 31)


def ingest_x_archive(archive_path: str | Path, *, months: int = 12, root=None) -> dict:
    archive_path = Path(archive_path)
    rows = []
    with zipfile.ZipFile(archive_path) as zf:
        names = [name for name in zf.namelist() if name.endswith(".js") and ("tweet" in name.lower())]
        for name in names:
            text = zf.read(name).decode("utf-8", errors="ignore")
            data = _json_from_archive_js(text)
            if not isinstance(data, list):
                continue
            for item in data:
                if isinstance(item, dict) and _within_months(item, months):
                    rows.append({"source_system": "x_archive", "archive_member": name, **item})
    path = artifact_path("raw/x_archive_import.jsonl", root)
    write_jsonl(path, rows)
    return {"raw_path": str(path), "tweet_count": len(rows)}


def ingest_manual(path: str | Path, *, root=None) -> dict:
    path = Path(path)
    rows = []
    if path.suffix.lower() == ".csv":
        rows = [{"source_system": "manual_csv", **row} for row in read_csv_rows(path)]
    else:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                if isinstance(item, dict):
                    rows.append({"source_system": "manual_jsonl", **item})
    out = artifact_path("raw/manual_import.jsonl", root)
    write_jsonl(out, rows)
    return {"raw_path": str(out), "tweet_count": len(rows)}
