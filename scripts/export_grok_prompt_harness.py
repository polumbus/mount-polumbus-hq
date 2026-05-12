#!/usr/bin/env python3
"""Export paste-ready Grok.com cards for the Creator Evolution prompt lab.

This is intentionally manual. It does not call Grok, mutate app state, post to
X, or write app profiles. It builds the same old/new/evolving prompts as the
Codex harness so the user can paste the matching card into grok.com while
running the Codex harness locally.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parents[0]
sys.path.insert(0, str(SCRIPT_DIR))

import compare_creator_evolution_prompts as lab  # noqa: E402


CONCEPTS_PATH = SCRIPT_DIR / "creator_evolution_harness_concepts.json"


def _load_concepts() -> dict:
    try:
        return json.loads(CONCEPTS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"voice_concepts": {}, "format_concepts": {}, "control_concepts": {}}


def _concept_for(args: argparse.Namespace, lane: str, fmt: str) -> str:
    if args.concept:
        return args.concept
    concepts = _load_concepts()
    if args.concept_key:
        for section in ("voice_concepts", "format_concepts", "control_concepts"):
            value = (concepts.get(section) or {}).get(args.concept_key)
            if value:
                return str(value)
    if args.test_axis == "format":
        return str((concepts.get("format_concepts") or {}).get(fmt) or lab.DEFAULT_CONCEPT)
    return str((concepts.get("voice_concepts") or {}).get(lane) or lab.DEFAULT_CONCEPT)


def _build_records(repo: Path, args: argparse.Namespace, lane: str, fmt: str, concept: str) -> dict:
    overlay = lab._load_overlay(repo, args.session)
    old_source = lab._git_show(repo, args.old_ref, "creator_evolution.py")
    new_source = lab._git_show(repo, args.new_ref, "creator_evolution.py")
    old_module = lab._load_module_from_source(old_source, "creator_evolution_old_grok_export")
    new_module = lab._load_module_from_source(new_source, "creator_evolution_new_grok_export")
    old_lane = lab._normalize_lane(old_module, lane)
    new_lane = lab._normalize_lane(new_module, lane)
    old_format = lab._normalize_format(old_module, fmt)
    new_format = lab._normalize_format(new_module, fmt)
    return {
        "old": lab._prompt_record("old", args.old_ref, old_module, concept, old_format, old_lane),
        "new": lab._prompt_record("new", args.new_ref, new_module, concept, new_format, new_lane),
        "evolving": lab._prompt_record(
            "evolving",
            f"{args.new_ref}+harness-overlay:{args.session}",
            new_module,
            concept,
            new_format,
            new_lane,
            overlay=overlay,
        ),
        "overlay": overlay,
        "lane": new_lane,
        "format": new_format,
        "concept": concept,
    }


def _paste_card(records: dict, args: argparse.Namespace) -> str:
    example_index = max(1, min(3, int(args.example_index or 1)))
    variants = [("OLD A", records["old"]), ("NEW B", records["new"]), ("EVOLVING C", records["evolving"])]
    selected = [item for item in variants if args.variant == "all" or item[0].lower().startswith(args.variant)]
    lines = [
        "RUN THIS CREATOR EVOLUTION TEST NOW",
        "",
        "You are not setting up a harness. You are running the test immediately.",
        "Generate the Grok side of the same Creator Evolution test Codex is running.",
        "Execution rules:",
        "- Run each exact prompt section below now.",
        "- Do not explain your reasoning.",
        "- For each section, return only the JSON object requested by that section's prompt.",
        "- Do not merge OLD, NEW, and EVOLVING rules together.",
        "- Do not say you are ready.",
        "- Do not ask for the next concept.",
        "- Do not add setup commentary.",
        "- Output exactly three labeled JSON objects unless this card only contains one section.",
        "- Use labels exactly: OLD A, NEW B, EVOLVING C.",
        "",
        f"Voice: {records['lane']}",
        f"Format: {records['format']}",
        f"Example index for user display after generation: {example_index}",
        f"Concept: {records['concept']}",
        "",
        f"After you generate all sections, the user will compare option{example_index} from each JSON against the Codex card.",
        "The Codex harness will track two choices after the round: which prompt option won and which model won.",
        "Do not ask the user for those choices. Just generate the JSON so the user can compare.",
        "",
    ]
    feedback = records.get("overlay", {}).get("feedback", [])
    if feedback:
        lines.append("Active Evolving feedback already applied to EVOLVING C:")
        for item in feedback:
            lines.append(f"- [{item.get('scope', 'general')}] {item.get('text', '')}")
        lines.append("")
    else:
        lines.append("Active Evolving feedback: none. EVOLVING C starts identical to NEW B.")
        lines.append("")
    for label, record in selected:
        lines.extend(
            [
                "=" * 72,
                label,
                f"Prompt hash: {record['prompt_sha1']}",
                "=" * 72,
                record["full_prompt"],
                "",
            ]
        )
    lines.extend(
        [
            "=" * 72,
            "FINAL OUTPUT INSTRUCTION",
            "=" * 72,
            "Run the sections above now.",
            "Return only the labeled JSON objects.",
            "Do not say the harness is ready.",
            "Do not wait for another message.",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _summary_card(records: dict, args: argparse.Namespace) -> str:
    lines = [
        "Grok matching harness ready.",
        f"Session: {args.session}",
        f"Voice: {records['lane']}",
        f"Format: {records['format']}",
        f"Concept: {records['concept']}",
        f"OLD hash: {records['old']['prompt_sha1']}",
        f"NEW hash: {records['new']['prompt_sha1']}",
        f"EVOLVING hash: {records['evolving']['prompt_sha1']}",
        "",
        "Run with --paste-card to print the full Grok.com prompt.",
    ]
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a paste-ready Grok.com companion card for Creator Evolution prompt testing.")
    parser.add_argument("--repo", default=".", help="Repo root. Defaults to current directory.")
    parser.add_argument("--old-ref", default=lab.DEFAULT_OLD_REF)
    parser.add_argument("--new-ref", default=lab.DEFAULT_NEW_REF)
    parser.add_argument("--lane", default="Witty Edge")
    parser.add_argument("--format", default=lab.DEFAULT_FORMAT)
    parser.add_argument("--session", default="grok-manual")
    parser.add_argument("--concept", default="")
    parser.add_argument("--concept-key", default="", help="Key from creator_evolution_harness_concepts.json.")
    parser.add_argument("--test-axis", choices=["voice", "format"], default="voice")
    parser.add_argument("--example-index", type=int, default=1, choices=[1, 2, 3])
    parser.add_argument("--variant", choices=["all", "old", "new", "evolving"], default="all")
    parser.add_argument("--paste-card", action="store_true", help="Print full paste-ready Grok.com prompt card.")
    parser.add_argument("--out", default="", help="Optional file path to write the exported card.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo = Path(args.repo).resolve()
    lane = args.lane
    fmt = args.format
    concept = _concept_for(args, lane, fmt)
    records = _build_records(repo, args, lane, fmt, concept)
    text = _paste_card(records, args) if args.paste_card else _summary_card(records, args)
    if args.out:
        out = Path(args.out)
        if not out.is_absolute():
            out = repo / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(str(out))
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
