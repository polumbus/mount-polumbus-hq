#!/usr/bin/env python3
"""Read-only old/new Creator Evolution prompt comparison harness.

This script imports creator_evolution.py from two git refs, builds prompts for
the same concept/format/voice, and prints comparable prompt evidence. It does
not write app state, sync tweets, post, or mutate profiles. By default it also
does not call AI providers. Use --generate-examples to make an explicit,
read-only AI call for side-by-side preference testing.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
import re
import shutil
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
DEFAULT_SESSION = "default"
HARNESS_STATE_ROOT = ".harness/prompt_evolution"
DEFAULT_LANES = [
    "Witty Edge",
    "Comedic",
    "Annoyed",
    "Fired-Up",
    "Skeptical",
    "Critical",
    "Promo",
    "Celebratory",
    "Deadpan",
    "Sarcastic",
]


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_.-]+", "-", str(value or "").strip()).strip("-").lower()
    return slug or DEFAULT_SESSION


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _state_paths(repo: Path, session: str) -> dict[str, Path]:
    root = repo / HARNESS_STATE_ROOT / _slug(session)
    return {
        "root": root,
        "overlay": root / "evolving_overlay.json",
        "feedback": root / "feedback_rounds.jsonl",
        "generations": root / "generations.jsonl",
        "export_md": root / "final_export.md",
        "export_json": root / "final_export.json",
    }


def _empty_overlay(session: str) -> dict[str, Any]:
    return {
        "version": 1,
        "session": _slug(session),
        "read_only_live_app": True,
        "not_applied_live": True,
        "created_at": _utc_now(),
        "updated_at": _utc_now(),
        "feedback": [],
    }


def _load_overlay(repo: Path, session: str) -> dict[str, Any]:
    path = _state_paths(repo, session)["overlay"]
    if not path.exists():
        return _empty_overlay(session)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = _empty_overlay(session)
    data.setdefault("version", 1)
    data.setdefault("session", _slug(session))
    data.setdefault("read_only_live_app", True)
    data.setdefault("not_applied_live", True)
    data.setdefault("feedback", [])
    return data


def _save_overlay(repo: Path, session: str, overlay: dict[str, Any]) -> None:
    paths = _state_paths(repo, session)
    paths["root"].mkdir(parents=True, exist_ok=True)
    overlay["updated_at"] = _utc_now()
    paths["overlay"].write_text(json.dumps(overlay, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _append_feedback(repo: Path, session: str, text: str, scope: str) -> dict[str, Any]:
    overlay = _load_overlay(repo, session)
    item = {
        "id": f"fb_{len(overlay.get('feedback', [])) + 1:03d}",
        "created_at": _utc_now(),
        "scope": scope,
        "text": str(text or "").strip(),
    }
    if not item["text"]:
        return overlay
    overlay.setdefault("feedback", []).append(item)
    _save_overlay(repo, session, overlay)
    paths = _state_paths(repo, session)
    paths["root"].mkdir(parents=True, exist_ok=True)
    with paths["feedback"].open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")
    return overlay


def _reset_overlay(repo: Path, session: str) -> dict[str, Any]:
    paths = _state_paths(repo, session)
    paths["root"].mkdir(parents=True, exist_ok=True)
    overlay = _empty_overlay(session)
    paths["overlay"].write_text(json.dumps(overlay, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    paths["feedback"].write_text("", encoding="utf-8")
    paths["generations"].write_text("", encoding="utf-8")
    return overlay


def _feedback_lines(overlay: dict[str, Any], scope: str | None = None) -> list[str]:
    lines = []
    for item in overlay.get("feedback", []):
        if scope and item.get("scope") not in {scope, "general"}:
            continue
        text = str(item.get("text", "")).strip()
        if text:
            lines.append(text)
    return lines


def _overlay_text(overlay: dict[str, Any]) -> str:
    if not _feedback_lines(overlay):
        return ""
    sections = [
        ("GENERAL", _feedback_lines(overlay, "general")),
        ("FORMAT", _feedback_lines(overlay, "format")),
        ("VOICE", _feedback_lines(overlay, "voice")),
        ("QUALITY", _feedback_lines(overlay, "quality")),
    ]
    lines = [
        "EVOLVING HARNESS SANDBOX OVERRIDES:",
        "These temporary rules apply only to the Evolving C candidate in this harness.",
        "They are not approved Creator Evolution rules and are not applied live.",
    ]
    for title, values in sections:
        if not values:
            continue
        lines.append(f"{title} FEEDBACK:")
        lines.extend(f"- {value}" for value in values)
    return "\n".join(lines)


def _apply_evolving_overlay(prompt: str, overlay: dict[str, Any]) -> str:
    block = _overlay_text(overlay)
    if not block:
        return prompt
    marker = "\nHIDDEN SELF-CHECK BEFORE FINAL JSON:"
    if marker in prompt:
        return prompt.replace(marker, f"\n{block}\n{marker}", 1)
    return f"{prompt.rstrip()}\n\n{block}\n"


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
    if clean.lower() == "comedic" and "Comedic" not in lanes and "Amused" in lanes:
        return "Amused"
    if clean.lower() == "amused" and "Amused" not in lanes and "Comedic" in lanes:
        return "Comedic"
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


def _prompt_record(
    label: str,
    ref: str,
    module: Any,
    concept: str,
    fmt: str,
    lane: str,
    *,
    overlay: dict[str, Any] | None = None,
) -> dict[str, Any]:
    lane = _normalize_lane(module, lane)
    fmt = _normalize_format(module, fmt)
    prompt = _build_prompt(module, concept, fmt, lane)
    if overlay is not None:
        prompt = _apply_evolving_overlay(prompt, overlay)
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
        "evolving_overlay": _overlay_text(overlay or {}),
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


def _prompt_for_example(prompt: str) -> str:
    return (
        "Use the exact prompt below. Do not explain. Return only the JSON object "
        "requested by the prompt.\n\n"
        f"{prompt}"
    )


def _call_claude_for_examples(prompt: str, timeout: int) -> str:
    env = dict(os.environ)
    # Keep the harness outside the app runtime and avoid accidental tool use.
    env["CLAUDE_CODE_SIMPLE"] = "1"
    claude_bin = shutil.which("claude") or "/home/polfam/.npm-global/bin/claude"
    result = subprocess.run(
        [
            claude_bin,
            "--print",
            "--no-session-persistence",
            "--permission-mode",
            "dontAsk",
            "--tools",
            "",
            "--max-budget-usd",
            "0.25",
            _prompt_for_example(prompt),
        ],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        env=env,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"claude example generation failed: {detail[:500]}")
    return result.stdout.strip()


def _call_codex_for_examples(prompt: str, timeout: int, model: str) -> str:
    codex_bin = shutil.which("codex") or "/home/polfam/.npm-global/bin/codex"
    result = subprocess.run(
        [
            codex_bin,
            "-a",
            "never",
            "-m",
            model,
            "exec",
            "--ephemeral",
            "--sandbox",
            "read-only",
            "-C",
            str(Path.cwd()),
            "-",
        ],
        input=_prompt_for_example(prompt),
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"codex example generation failed: {detail[:500]}")
    return result.stdout.strip()


def _call_ai_for_examples(prompt: str, timeout: int, provider: str, model: str) -> tuple[str, str]:
    provider = (provider or "auto").strip().lower()
    errors = []
    if provider in {"auto", "claude"}:
        try:
            return "claude", _call_claude_for_examples(prompt, timeout)
        except Exception as exc:
            errors.append(str(exc))
            if provider == "claude":
                raise
    if provider in {"auto", "codex"}:
        try:
            return "codex", _call_codex_for_examples(prompt, timeout, model)
        except Exception as exc:
            errors.append(str(exc))
            if provider == "codex":
                raise
    raise RuntimeError(" | ".join(errors) or f"Unsupported AI provider: {provider}")


def _extract_options(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            options = []
            for key in ("option1", "option2", "option3"):
                value = str(data.get(key, "")).strip()
                if value:
                    options.append(value)
            return options
        except Exception:
            pass
    return [text]


def _render_rule_delta(record: dict[str, Any]) -> str:
    old = record["old"]
    new = record["new"]
    lines = []
    sections = [
        ("Format rules", "format_recipe_text"),
        ("Lane rules", "lane_recipe_text"),
        ("Voice contract", "voice_contract"),
        ("Quality gate", "quality_gate"),
    ]
    for title, key in sections:
        if old.get(key) == new.get(key):
            continue
        lines.append(f"### {title}")
        lines.append("")
        lines.append("OLD")
        lines.append("```text")
        lines.append(str(old.get(key, "")).strip())
        lines.append("```")
        lines.append("")
        lines.append("NEW")
        lines.append("```text")
        lines.append(str(new.get(key, "")).strip())
        lines.append("```")
        lines.append("")
    return "\n".join(lines).strip()


def _render_study_cards(
    output: dict[str, Any],
    *,
    include_rules: bool,
    generate_examples: bool,
    timeout: int,
    provider: str,
    model: str,
    example_index: int,
    show_all_examples: bool,
) -> str:
    example_index = max(1, min(3, int(example_index or 1)))
    lines = [
        "# Creator Evolution Prompt Lab",
        "",
        f"Read-only: {output['read_only']}",
        f"Mutates app state: {output['mutates_app_state']}",
        f"Posts to X: {output['posts_to_x']}",
        f"Calls AI: {generate_examples}",
        f"Session: {output.get('session', DEFAULT_SESSION)}",
        f"Old ref: {output['old_ref']}",
        f"New ref: {output['new_ref']}",
        f"Format: {output['format']}",
        "",
        "How to use this:",
        f"1. Compare one tweet at a time: example {example_index} of 3.",
        "2. Pick `old`, `new`, `evolving`, `mix`, or `neither`.",
        "3. Give one short feedback note to improve Evolving C, then rerun this example or move to the next one.",
        "",
        "Concept:",
        "```text",
        output["concept"],
        "```",
        "",
    ]
    overlay = output.get("evolving_overlay", {})
    feedback = overlay.get("feedback", []) if isinstance(overlay, dict) else []
    if feedback:
        lines.append("Active Evolving feedback:")
        for item in feedback:
            lines.append(f"- [{item.get('scope', 'general')}] {item.get('text', '')}")
        lines.append("")
    else:
        lines.append("Active Evolving feedback: none. Evolving C starts identical to New B.")
        lines.append("")
    for idx, record in enumerate(output["records"], 1):
        old = record["old"]
        new = record["new"]
        evolving = record.get("evolving")
        lines.extend(
            [
                f"## Card {idx}: {record['lane']} / {output['format']}",
                "",
                f"Old prompt hash: `{old['prompt_sha1']}`",
                f"New prompt hash: `{new['prompt_sha1']}`",
                f"Evolving prompt hash: `{evolving['prompt_sha1'] if evolving else 'not built'}`",
                "",
            ]
        )
        if include_rules:
            delta = _render_rule_delta(record)
            if delta:
                lines.append(delta)
                lines.append("")
        if generate_examples:
            variants = [("OLD A", old), ("NEW B", new)]
            if evolving:
                variants.append(("EVOLVING C", evolving))
            for label, side in variants:
                lines.append(f"### {label}")
                try:
                    used_provider, raw = _call_ai_for_examples(side["full_prompt"], timeout, provider, model)
                    examples = _extract_options(raw)
                    lines.append(f"_Generated by `{used_provider}` from the exact {label} prompt. Showing example {example_index} of 3._")
                    lines.append("")
                    if examples:
                        if show_all_examples:
                            for opt_idx, example in enumerate(examples, 1):
                                lines.append(f"{opt_idx}. {example}")
                        else:
                            selected = examples[min(example_index, len(examples)) - 1]
                            lines.append(selected)
                    else:
                        lines.append("_No examples returned._")
                    side["example_raw"] = raw
                    side["examples"] = examples
                except Exception as exc:
                    lines.append(f"_Example generation failed: {exc}_")
                lines.append("")
        else:
            lines.extend(["Prompt examples were not generated. Use `--generate-examples` to compare tweets.", ""])
            if include_rules:
                lines.extend(
                    [
                        "### Evolving C Sandbox Overlay",
                        "```text",
                        evolving.get("evolving_overlay", "") if evolving else "",
                        "```",
                        "",
                    ]
                )
        lines.extend(
            [
                "Preference question:",
                f"For {record['lane']}, choose `old`, `new`, `evolving`, `mix`, or `neither`, then give one short feedback note for Evolving C.",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _write_generation_log(repo: Path, session: str, output: dict[str, Any]) -> None:
    paths = _state_paths(repo, session)
    paths["root"].mkdir(parents=True, exist_ok=True)
    event = {
        "created_at": _utc_now(),
        "concept": output.get("concept"),
        "format": output.get("format"),
        "old_ref": output.get("old_ref"),
        "new_ref": output.get("new_ref"),
        "records": [
            {
                "lane": record.get("lane"),
                "old_prompt_sha1": record.get("old", {}).get("prompt_sha1"),
                "new_prompt_sha1": record.get("new", {}).get("prompt_sha1"),
                "evolving_prompt_sha1": record.get("evolving", {}).get("prompt_sha1"),
                "old_examples": record.get("old", {}).get("examples", []),
                "new_examples": record.get("new", {}).get("examples", []),
                "evolving_examples": record.get("evolving", {}).get("examples", []),
            }
            for record in output.get("records", [])
        ],
    }
    with paths["generations"].open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False) + "\n")


def _export_proposal(repo: Path, session: str, output: dict[str, Any]) -> dict[str, str]:
    paths = _state_paths(repo, session)
    paths["root"].mkdir(parents=True, exist_ok=True)
    overlay = output.get("evolving_overlay", {})
    feedback = overlay.get("feedback", []) if isinstance(overlay, dict) else []
    proposal = {
        "version": 1,
        "created_at": _utc_now(),
        "session": _slug(session),
        "not_applied_live": True,
        "read_only_live_app": True,
        "old_ref": output.get("old_ref"),
        "new_ref": output.get("new_ref"),
        "format": output.get("format"),
        "concept": output.get("concept"),
        "feedback": feedback,
        "prompt_hashes": [
            {
                "lane": record.get("lane"),
                "old": record.get("old", {}).get("prompt_sha1"),
                "new": record.get("new", {}).get("prompt_sha1"),
                "evolving": record.get("evolving", {}).get("prompt_sha1"),
            }
            for record in output.get("records", [])
        ],
        "proposed_overlay_text": _overlay_text(overlay if isinstance(overlay, dict) else {}),
    }
    paths["export_json"].write_text(json.dumps(proposal, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    md = [
        "# Creator Evolution Prompt Lab Export",
        "",
        "Status: proposal only. Not applied live.",
        f"Session: `{_slug(session)}`",
        f"Old ref: `{output.get('old_ref')}`",
        f"New ref: `{output.get('new_ref')}`",
        f"Format: `{output.get('format')}`",
        "",
        "## Feedback",
    ]
    if feedback:
        for item in feedback:
            md.append(f"- `{item.get('scope', 'general')}`: {item.get('text', '')}")
    else:
        md.append("- No Evolving feedback yet.")
    md.extend(["", "## Proposed Harness Overlay", "```text", proposal["proposed_overlay_text"], "```", ""])
    md.append("## Prompt Hashes")
    for item in proposal["prompt_hashes"]:
        md.append(f"- {item['lane']}: old `{item['old']}`, new `{item['new']}`, evolving `{item['evolving']}`")
    paths["export_md"].write_text("\n".join(md).rstrip() + "\n", encoding="utf-8")
    return {"json": str(paths["export_json"]), "markdown": str(paths["export_md"])}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare old/new Creator Evolution prompt systems without mutating app state.")
    parser.add_argument("--repo", default=".", help="Repo root. Defaults to current directory.")
    parser.add_argument("--old-ref", default=DEFAULT_OLD_REF)
    parser.add_argument("--new-ref", default=DEFAULT_NEW_REF)
    parser.add_argument("--format", default=DEFAULT_FORMAT)
    parser.add_argument("--concept", default=DEFAULT_CONCEPT)
    parser.add_argument("--lane", action="append", dest="lanes", help="Lane to compare. Repeatable. Defaults to all lanes.")
    parser.add_argument("--session", default=DEFAULT_SESSION, help="Harness-only Evolving session name.")
    parser.add_argument("--feedback", action="append", default=[], help="Add a harness-only feedback note to Evolving C before running.")
    parser.add_argument("--feedback-scope", choices=["general", "format", "voice", "quality"], default="general")
    parser.add_argument("--reset-evolving", action="store_true", help="Clear harness-only Evolving feedback for this session before running.")
    parser.add_argument("--export-proposal", action="store_true", help="Write final_export.md/json proposal files for this harness session.")
    parser.add_argument("--include-full-prompts", action="store_true", help="Include full prompt text. Off by default to keep output readable.")
    parser.add_argument("--study-cards", action="store_true", help="Print human-readable Old/New preference cards instead of JSON.")
    parser.add_argument("--include-rules", action="store_true", help="Include exact changed rule sections in study-card output.")
    parser.add_argument("--generate-examples", action="store_true", help="Explicitly call an AI CLI to generate Old/New examples from exact prompts.")
    parser.add_argument("--example-index", type=int, default=1, choices=[1, 2, 3], help="Show only this example number from each Old/New/Evolving batch.")
    parser.add_argument("--show-all-examples", action="store_true", help="Show all three examples per category instead of one at a time.")
    parser.add_argument("--ai-timeout", type=int, default=90, help="Timeout per example-generation call.")
    parser.add_argument("--ai-provider", choices=["auto", "claude", "codex"], default="auto", help="Read-only example backend.")
    parser.add_argument("--codex-model", default="gpt-5.4", help="Codex model for --ai-provider codex or auto fallback.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.repo).resolve()
    lanes = args.lanes or DEFAULT_LANES
    session = _slug(args.session)
    if args.reset_evolving:
        overlay = _reset_overlay(repo, session)
    else:
        overlay = _load_overlay(repo, session)
    for feedback in args.feedback:
        overlay = _append_feedback(repo, session, feedback, args.feedback_scope)
    old_source = _git_show(repo, args.old_ref, "creator_evolution.py")
    new_source = _git_show(repo, args.new_ref, "creator_evolution.py")
    old_module = _load_module_from_source(old_source, "creator_evolution_old_compare")
    new_module = _load_module_from_source(new_source, "creator_evolution_new_compare")

    comparisons = []
    records = []
    for lane in lanes:
        old_lane = _normalize_lane(old_module, lane)
        new_lane = _normalize_lane(new_module, lane)
        alias_match = {old_lane, new_lane} == {"Amused", "Comedic"}
        if old_lane != new_lane and not alias_match:
            raise RuntimeError(f"Lane resolves differently between refs: {lane!r} -> old={old_lane!r}, new={new_lane!r}")
        old_format = _normalize_format(old_module, args.format)
        new_format = _normalize_format(new_module, args.format)
        if old_format != new_format:
            raise RuntimeError(f"Format resolves differently between refs: {args.format!r} -> old={old_format!r}, new={new_format!r}")
        old_record = _prompt_record("old", args.old_ref, old_module, args.concept, old_format, old_lane)
        new_record = _prompt_record("new", args.new_ref, new_module, args.concept, new_format, new_lane)
        evolving_record = _prompt_record(
            "evolving",
            f"{args.new_ref}+harness-overlay:{session}",
            new_module,
            args.concept,
            new_format,
            new_lane,
            overlay=overlay,
        )
        comparisons.append(_compare_records(old_record, new_record))
        if not args.include_full_prompts and not args.study_cards and not args.generate_examples:
            old_record.pop("full_prompt", None)
            new_record.pop("full_prompt", None)
            evolving_record.pop("full_prompt", None)
        records.append({"lane": new_lane, "old": old_record, "new": new_record, "evolving": evolving_record})

    output = {
        "read_only": True,
        "mutates_app_state": False,
        "calls_ai": bool(args.generate_examples),
        "posts_to_x": False,
        "session": session,
        "harness_state_root": str(_state_paths(repo, session)["root"]),
        "old_ref": args.old_ref,
        "new_ref": args.new_ref,
        "format": _normalize_format(new_module, args.format),
        "concept": args.concept,
        "evolving_overlay": overlay,
        "comparisons": comparisons,
        "records": records,
    }
    if args.study_cards:
        print(
            _render_study_cards(
                output,
                include_rules=args.include_rules,
                generate_examples=args.generate_examples,
                timeout=args.ai_timeout,
                provider=args.ai_provider,
                model=args.codex_model,
                example_index=args.example_index,
                show_all_examples=args.show_all_examples,
            ),
            end="",
        )
    else:
        print(json.dumps(output, indent=2, ensure_ascii=False))
    if args.generate_examples:
        _write_generation_log(repo, session, output)
    if args.export_proposal:
        paths = _export_proposal(repo, session, output)
        print(f"\nExported proposal: {paths['markdown']} and {paths['json']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
