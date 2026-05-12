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
import hashlib
import importlib.util
import json
import os
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
) -> str:
    lines = [
        "# Creator Evolution Old/New Preference Harness",
        "",
        f"Read-only: {output['read_only']}",
        f"Mutates app state: {output['mutates_app_state']}",
        f"Posts to X: {output['posts_to_x']}",
        f"Calls AI: {generate_examples}",
        f"Old ref: {output['old_ref']}",
        f"New ref: {output['new_ref']}",
        f"Format: {output['format']}",
        "",
        "How to use this:",
        "1. Read OLD A and NEW B for each card.",
        "2. Pick `old`, `new`, `mix`, or `neither`.",
        "3. Say which specific lines or rule changes you like or hate.",
        "",
        "Concept:",
        "```text",
        output["concept"],
        "```",
        "",
    ]
    for idx, record in enumerate(output["records"], 1):
        old = record["old"]
        new = record["new"]
        lines.extend(
            [
                f"## Card {idx}: {record['lane']} / {output['format']}",
                "",
                f"Old prompt hash: `{old['prompt_sha1']}`",
                f"New prompt hash: `{new['prompt_sha1']}`",
                "",
            ]
        )
        if include_rules:
            delta = _render_rule_delta(record)
            if delta:
                lines.append(delta)
                lines.append("")
        if generate_examples:
            for label, side in (("OLD A", old), ("NEW B", new)):
                lines.append(f"### {label} Examples")
                try:
                    used_provider, raw = _call_ai_for_examples(side["full_prompt"], timeout, provider, model)
                    examples = _extract_options(raw)
                    lines.append(f"_Generated by `{used_provider}` from the exact {label} prompt._")
                    lines.append("")
                    if examples:
                        for opt_idx, example in enumerate(examples, 1):
                            lines.append(f"{opt_idx}. {example}")
                    else:
                        lines.append("_No examples returned._")
                    side["example_raw"] = raw
                    side["examples"] = examples
                except Exception as exc:
                    lines.append(f"_Example generation failed: {exc}_")
                lines.append("")
        else:
            lines.extend(
                [
                    "### OLD A Prompt",
                    "```text",
                    old["full_prompt"],
                    "```",
                    "",
                    "### NEW B Prompt",
                    "```text",
                    new["full_prompt"],
                    "```",
                    "",
                ]
            )
        lines.extend(
            [
                "Preference question:",
                f"For {record['lane']}, choose `old`, `new`, `mix`, or `neither`, then name the exact line/rule/example that drove the choice.",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare old/new Creator Evolution prompt systems without mutating app state.")
    parser.add_argument("--repo", default=".", help="Repo root. Defaults to current directory.")
    parser.add_argument("--old-ref", default=DEFAULT_OLD_REF)
    parser.add_argument("--new-ref", default=DEFAULT_NEW_REF)
    parser.add_argument("--format", default=DEFAULT_FORMAT)
    parser.add_argument("--concept", default=DEFAULT_CONCEPT)
    parser.add_argument("--lane", action="append", dest="lanes", help="Lane to compare. Repeatable. Defaults to all lanes.")
    parser.add_argument("--include-full-prompts", action="store_true", help="Include full prompt text. Off by default to keep output readable.")
    parser.add_argument("--study-cards", action="store_true", help="Print human-readable Old/New preference cards instead of JSON.")
    parser.add_argument("--include-rules", action="store_true", help="Include exact changed rule sections in study-card output.")
    parser.add_argument("--generate-examples", action="store_true", help="Explicitly call an AI CLI to generate Old/New examples from exact prompts.")
    parser.add_argument("--ai-timeout", type=int, default=90, help="Timeout per example-generation call.")
    parser.add_argument("--ai-provider", choices=["auto", "claude", "codex"], default="auto", help="Read-only example backend.")
    parser.add_argument("--codex-model", default="gpt-5.4", help="Codex model for --ai-provider codex or auto fallback.")
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
        if not args.include_full_prompts and not args.study_cards and not args.generate_examples:
            old_record.pop("full_prompt", None)
            new_record.pop("full_prompt", None)
        records.append({"lane": new_lane, "old": old_record, "new": new_record})

    output = {
        "read_only": True,
        "mutates_app_state": False,
        "calls_ai": bool(args.generate_examples),
        "posts_to_x": False,
        "old_ref": args.old_ref,
        "new_ref": args.new_ref,
        "format": _normalize_format(new_module, args.format),
        "concept": args.concept,
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
            ),
            end="",
        )
    else:
        print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
