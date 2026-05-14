#!/usr/bin/env python3
"""Static contract proof for Voice Tuner route/live metadata.

This complements the deterministic feedback proof. It intentionally fails if
the app regresses to raw repair notes, generic passing gates, or lane-wide
unscoped live overrides.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app.py"
VTF = ROOT / "voice_tuner_feedback.py"


def require(name: str, condition: bool, failures: list[str]) -> None:
    if not condition:
        failures.append(name)


def main() -> int:
    app = APP.read_text()
    vtf = VTF.read_text()
    failures: list[str] = []
    repair = app[app.index("def _ce_repair_voice_tuner_feedback_generation") : app.index("def _ce_testing_concepts")]
    generate = app[app.index("def _ce_testing_generate(") : app.index("def _ce_testing_generate_pair")]
    live = app[app.index("def _ce_live_voice_override_text") : app.index("def _ce_prompt_version")]
    route = app[app.index("def _ce_ai_route_snapshot") : app.index("def _ce_local_route_snapshot")]

    require("repair excludes raw saved feedback block", "Saved sandbox feedback:" not in repair, failures)
    require("repair explicitly forbids raw notes", "do not use raw sandbox notes" in repair, failures)
    require("repair uses structured contract", "vtf.feedback_prompt_text(feedback_rules)" in repair, failures)
    require("generation repair uses clean ids", "feedback_rules and len(clean_ids) < 3" in generate, failures)
    require("repaired output requires clean ids", "repaired_clean = _ce_clean_feedback_option_ids" in generate, failures)
    require("fallback output requires clean ids", "fallback_clean = _ce_clean_feedback_option_ids" in generate, failures)
    require("route marks requested grok fallback", '"grok" not in actual_provider.lower()' in route, failures)
    require("live override accepts format", "def _ce_live_voice_override_text(lane: str, fmt:" in live, failures)
    require("live override filters format", "entry_fmt != selected_fmt" in live, failures)
    require("live override stores provenance", "Approval provenance" in live, failures)
    require("live apply stores rules hash", '"rules_hash": active_rules_hash' in app, failures)
    require("live apply stores structured rule entries", "distill_live_rule_entries(active_rules)" in app, failures)
    require("rule ids include concept and scope", "concept_id, scope" in vtf and "def rule_identity_key" in vtf, failures)

    payload = {"passed": not failures, "failures": failures}
    print(json.dumps(payload, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
