#!/usr/bin/env python3
"""Read-only old/new Creator Evolution prompt comparison harness.

This script imports creator_evolution.py from two git refs, builds prompts for
the same concept/format/voice, and prints comparable prompt evidence. It does
not call AI providers, write app state, sync tweets, post, or mutate profiles.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_OLD_REF = "restore/pre-voice-format-audit-20260511-141836"
DEFAULT_NEW_REF = "HEAD"
DEFAULT_CONCEPT = (
    "The Avs keep acting like the goalie situation is settled, but the next "
    "tough start will show whether they actually believe that or are just "
    "hoping it settles itself."
)
DEFAULT_FORMAT = "Normal Tweet"
DEFAULT_LANES = [
    "Witty Edge",
    "Amused",
    "Annoyed",
    "Fired-Up",
    "Skeptical",
    "Critical",
    "Promo",
    "Celebratory",
    "Deadpan",
    "Sarcastic",
]


def _git_show(repo: Path, ref: str, file_path: str) -> str:
    result = subprocess.run(
        ["git", "show", f"{ref}:{file_path}"],
        cwd=repo,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.stdout


def _load_module_from_source(source: str, module_name: str) -> Any:
    with tempfile.TemporaryDirectory(prefix="ce_prompt_compare_") as tmp:
        path = Path(tmp) / f"{module_name}.py"
        path.write_text(source, encoding="utf-8")
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Could not load module spec for {module_name}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module


def _section(prompt: str, header: str, next_headers: list[str]) -> str:
    marker = f"{header}:"
    start = prompt.find(marker)
    if start < 0:
        return ""
    start += len(marker)
    end = len(prompt)
    for next_header in next_headers:
        next_marker = f"\n{next_header}:"
        idx = prompt.find(next_marker, start)
        if idx >= 0:
            end = min(end, idx)
    return prompt[start:end].strip()


def _build_prompt(module: Any, concept: str, fmt: str, lane: str) -> str:
    state = module.initial_state() if hasattr(module, "initial_state") else {}
    return module.build_generation_prompt(concept, fmt, lane, state)


def _normalize_lane(module: Any, lane: str) -> str:
    lanes = list(getattr(module, "EMOTION_LANES", []) or [])
    if not lanes:
        return lane
    clean = str(lane or "").strip()
    for candidate in lanes:
        if candidate.lower() == clean.lower():
            return candidate
    matches = [candidate for candidate in lanes if candidate.lower().startswith(clean.lower())]
    if len(matches) == 1:
        return matches[0]
    return clean


def _normalize_format(module: Any, fmt: str) -> str:
    formats = list(getattr(module, "FORMAT_RECIPES", {}) or {})
    if not formats:
        return fmt
    clean = str(fmt or "").strip()
    for candidate in formats:
        if candidate.lower() == clean.lower():
            return candidate
    matches = [candidate for candidate in formats if candidate.lower().startswith(clean.lower())]
    if len(matches) == 1:
        return matches[0]
    return clean


def _prompt_record(label: str, ref: str, module: Any, concept: str, fmt: str, lane: str) -> dict[str, Any]:
    lane = _normalize_lane(module, lane)
    fmt = _normalize_format(module, fmt)
    prompt = _build_prompt(module, concept, fmt, lane)
    lane_recipe_text = ""
    if hasattr(module, "lane_recipe_text"):
        lane_recipe_text = str(module.lane_recipe_text(lane))
    format_recipe_text = ""
    if hasattr(module, "format_recipe_text"):
        format_recipe_text = str(module.format_recipe_text(fmt))
    return {
        "label": label,
        "ref": ref,
        "prompt_sha1": hashlib.sha1(prompt.encode("utf-8")).hexdigest(),
        "prompt_length": len(prompt),
        "prompt_version": getattr(module, "PROMPT_VERSION", ""),
        "format": fmt,
        "lane": lane,
        "concept": concept,
        "format_recipe_text": format_recipe_text,
        "lane_recipe_text": lane_recipe_text,
        "format_behavior": _section(prompt, "FORMAT BEHAVIOR", ["LEARNED FORMAT PROFILE", "PERSONALITY LANE"]),
        "lane_behavior": _section(prompt, "LANE BEHAVIOR", ["LEARNED VOICE PROFILE", "CURRENT PERFORMANCE SUMMARY"]),
        "voice_contract": _section(prompt, "CREATOR EVOLUTION VOICE CONTRACT", ["QUALITY GATE"]),
        "quality_gate": _section(prompt, "QUALITY GATE", ["HIDDEN SELF-CHECK BEFORE FINAL JSON"]),
        "full_prompt": prompt,
    }


def _compare_records(old: dict[str, Any], new: dict[str, Any]) -> dict[str, Any]:
    keys = ["format_recipe_text", "lane_recipe_text", "format_behavior", "lane_behavior", "voice_contract", "quality_gate"]
    return {
        "lane": old["lane"],
        "format": old["format"],
        "old_prompt_sha1": old["prompt_sha1"],
        "new_prompt_sha1": new["prompt_sha1"],
        "changed_sections": [key for key in keys if old.get(key) != new.get(key)],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare old/new Creator Evolution prompt systems without mutating app state.")
    parser.add_argument("--repo", default=".", help="Repo root. Defaults to current directory.")
    parser.add_argument("--old-ref", default=DEFAULT_OLD_REF)
    parser.add_argument("--new-ref", default=DEFAULT_NEW_REF)
    parser.add_argument("--format", default=DEFAULT_FORMAT)
    parser.add_argument("--concept", default=DEFAULT_CONCEPT)
    parser.add_argument("--lane", action="append", dest="lanes", help="Lane to compare. Repeatable. Defaults to all lanes.")
    parser.add_argument("--include-full-prompts", action="store_true", help="Include full prompt text. Off by default to keep output readable.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.repo).resolve()
    lanes = args.lanes or DEFAULT_LANES
    old_source = _git_show(repo, args.old_ref, "creator_evolution.py")
    new_source = _git_show(repo, args.new_ref, "creator_evolution.py")
    old_module = _load_module_from_source(old_source, "creator_evolution_old_compare")
    new_module = _load_module_from_source(new_source, "creator_evolution_new_compare")

    comparisons = []
    records = []
    for lane in lanes:
        old_lane = _normalize_lane(old_module, lane)
        new_lane = _normalize_lane(new_module, lane)
        if old_lane != new_lane:
            raise RuntimeError(f"Lane resolves differently between refs: {lane!r} -> old={old_lane!r}, new={new_lane!r}")
        old_format = _normalize_format(old_module, args.format)
        new_format = _normalize_format(new_module, args.format)
        if old_format != new_format:
            raise RuntimeError(f"Format resolves differently between refs: {args.format!r} -> old={old_format!r}, new={new_format!r}")
        old_record = _prompt_record("old", args.old_ref, old_module, args.concept, old_format, old_lane)
        new_record = _prompt_record("new", args.new_ref, new_module, args.concept, new_format, new_lane)
        comparisons.append(_compare_records(old_record, new_record))
        if not args.include_full_prompts:
            old_record.pop("full_prompt", None)
            new_record.pop("full_prompt", None)
        records.append({"lane": new_lane, "old": old_record, "new": new_record})

    output = {
        "read_only": True,
        "mutates_app_state": False,
        "calls_ai": False,
        "posts_to_x": False,
        "old_ref": args.old_ref,
        "new_ref": args.new_ref,
        "format": _normalize_format(new_module, args.format),
        "concept": args.concept,
        "comparisons": comparisons,
        "records": records,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
