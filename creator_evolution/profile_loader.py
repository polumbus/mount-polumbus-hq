"""Approval-gated Tyler voice profile loader for Creator Evolution only."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_PROFILE_ROOT = Path("data/creator_evolution/voice_profile")
APPROVED_PROFILE_RELATIVE = Path("profiles/approved_profile.json")


def artifact_root() -> Path:
    return Path(os.environ.get("CE_VOICE_PROFILE_ROOT", str(DEFAULT_PROFILE_ROOT)))


def approved_profile_path(root: str | Path | None = None) -> Path:
    base = Path(root) if root else artifact_root()
    return base / APPROVED_PROFILE_RELATIVE


def load_approved_profile(root: str | Path | None = None) -> dict[str, Any]:
    path = approved_profile_path(root)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    if data.get("activation_status") != "approved":
        return {}
    return data


def active_profile_version(root: str | Path | None = None) -> str:
    profile = load_approved_profile(root)
    return str(profile.get("profile_version") or "")


def approved_profile_prompt_insert(root: str | Path | None = None) -> str:
    profile = load_approved_profile(root)
    if not profile:
        return ""
    short_insert = str(profile.get("short_system_insert") or "").strip()
    if not short_insert:
        rules = profile.get("sounds_like_tyler_rules") or []
        never = profile.get("never_tyler_rules") or []
        rules_text = "\n".join(f"- {item}" for item in rules[:10])
        never_text = "\n".join(f"- {item}" for item in never[:10])
        short_insert = (
            "APPROVED TYLER VOICE PROFILE:\n"
            f"{profile.get('core_voice_identity', '')}\n\n"
            "Sounds like Tyler:\n"
            f"{rules_text}\n\n"
            "Never Tyler:\n"
            f"{never_text}"
        )
    return (
        "\nAPPROVED TYLER VOICE PROFILE INSERT:\n"
        f"Profile version: {profile.get('profile_version', 'unknown')}\n"
        "Use this profile only for Creator Evolution. It is approval-gated and must not affect Creator Studio.\n"
        f"{short_insert.strip()}\n"
    )
