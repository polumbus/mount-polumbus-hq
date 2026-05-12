#!/usr/bin/env python3
"""Proof harness for Creator Evolution Comedic generation.

Runs the same generate -> quality gate -> repair flow used by the Streamlit app
and fails unless every required topic returns three passing Comedic drafts.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import app  # noqa: E402
import creator_evolution as ce  # noqa: E402


TOPICS = {
    "broncos": "The Broncos keep saying Bo Nix is on track for camp, but the next quarterback roster move will show whether they actually trust the ankle or are just trying to sound calm.",
    "nuggets": "The Nuggets say everything is on the table this summer, but nobody knows if that actually includes changing the non-Jokic minutes that keep wrecking games.",
    "avs": "The Avs are switching goalies after one loss even though the other goalie had been rolling.",
    "rockies": "The Rockies keep calling this a development year, but every road series turns into another reminder that the lineup cannot handle left-handed pitching.",
}


def _passing_ids(quality: dict) -> list[str]:
    passing = []
    for idx in (1, 2, 3):
        key = f"option{idx}"
        report = quality.get(key, {}) if isinstance(quality, dict) else {}
        if report.get("ok"):
            passing.append(key)
    return passing


def _sanitize_options(data: dict) -> dict:
    cleaned = dict(data or {})
    for option_key in ("option1", "option2", "option3"):
        if cleaned.get(option_key):
            cleaned[option_key] = app._sanitize_output(str(cleaned[option_key])).strip()
    return cleaned


def run_topic(name: str, concept: str, *, timeout: int) -> dict:
    fmt = "Normal Tweet"
    lane = "Comedic"
    prompt = ce.build_generation_prompt(concept, fmt, lane, ce.initial_state())
    raw = app._call_creator_evolution_ai(prompt, lane, 700, timeout_seconds=timeout)
    data = _sanitize_options(app._parse_banger_json(raw or "") or {})
    quality = app._ce_validate_generation_options(data, fmt, lane) if data else {}
    passing = _passing_ids(quality)
    repairs = []
    final_data = data
    final_quality = quality
    final_passing = passing
    passing_pool: list[tuple[str, str, str]] = []

    def collect(source_data: dict, source_passing: list[str]) -> None:
        seen = {text for _, text, _ in passing_pool}
        for source_idx in source_passing:
            key = f"option{source_idx}"
            text = str(source_data.get(key, "") or "").strip()
            if text and text not in seen:
                passing_pool.append((source_idx, text, str(source_data.get(f"{key}_pattern", "") or "")))
                seen.add(text)

    collect(data, passing)
    best_data = final_data
    best_quality = final_quality
    best_passing = final_passing
    for _attempt in range(5):
        if len(passing_pool) >= 3:
            break
        repaired, repaired_quality, repaired_passing = app._ce_repair_failed_generation(
            prompt,
            final_data,
            final_quality,
            fmt,
            lane,
            700,
            timeout_seconds=timeout,
        )
        if not repaired:
            break
        repairs.append({
            "drafts": {k: repaired.get(k, "") for k in ("option1", "option2", "option3")},
            "passing": repaired_passing,
            "quality": repaired_quality,
        })
        collect(repaired, repaired_passing or [])
        if len(passing_pool) >= 3:
            final_data = {}
            for target_idx, (_, text, pattern) in enumerate(passing_pool[:3], 1):
                final_data[f"option{target_idx}"] = text
                final_data[f"option{target_idx}_pattern"] = pattern or "Passed Creator Evolution Comedic quality gates."
            final_data["pick"] = "1"
            final_data["pick_reason"] = "Selected from passing Comedic drafts collected across repair attempts."
            final_quality = app._ce_validate_generation_options(final_data, fmt, lane)
            final_passing = _passing_ids(final_quality)
            break
        if len(repaired_passing or []) >= len(best_passing):
            best_data = repaired
            best_quality = repaired_quality or {}
            best_passing = repaired_passing or []
        final_data = best_data
        final_quality = best_quality
        final_passing = best_passing
    return {
        "topic": name,
        "concept": concept,
        "initial": {
            "drafts": {k: data.get(k, "") for k in ("option1", "option2", "option3")},
            "passing": passing,
            "quality": quality,
        },
        "repair_used": bool(repairs),
        "repairs": repairs,
        "repaired": repairs[-1] if repairs else None,
        "final": {
            "drafts": {k: final_data.get(k, "") for k in ("option1", "option2", "option3")},
            "passing": final_passing,
            "quality": final_quality,
        },
        "ok": len(final_passing) == 3,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--out", default="state/creator_evolution/comedic_proof_latest.json")
    args = parser.parse_args()
    results = [run_topic(name, concept, timeout=args.timeout) for name, concept in TOPICS.items()]
    payload = {
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "required_passing_per_topic": 3,
        "ok": all(item["ok"] for item in results),
        "results": results,
    }
    out_path = REPO / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
