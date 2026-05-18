"""Approval store for Tyler voice profiles."""

from __future__ import annotations

import json
from pathlib import Path

from .config import artifact_path, read_json, utc_now_iso, write_json


def pending_profile_path(root=None) -> Path:
    return artifact_path("profiles/pending_profile.json", root)


def approved_profile_path(root=None) -> Path:
    return artifact_path("profiles/approved_profile.json", root)


def approve_profile(profile: str | Path | None = None, *, root=None, approved_by: str = "owner") -> dict:
    path = Path(profile) if profile else pending_profile_path(root)
    data = read_json(path, {}) or {}
    if not data:
        raise RuntimeError(f"profile not found: {path}")
    data["activation_status"] = "approved"
    data["approved_by"] = approved_by
    data["approved_at_utc"] = utc_now_iso()
    out = approved_profile_path(root)
    write_json(out, data)
    return {"approved_profile_path": str(out), "profile_version": data.get("profile_version", "")}


def reject_pending(*, root=None) -> dict:
    path = pending_profile_path(root)
    if path.exists():
        data = read_json(path, {}) or {}
        data["activation_status"] = "rejected"
        data["rejected_at_utc"] = utc_now_iso()
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return {"rejected_profile_path": str(path), "profile_version": data.get("profile_version", "")}
    return {"rejected_profile_path": "", "profile_version": ""}
