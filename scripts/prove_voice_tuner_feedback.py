#!/usr/bin/env python3
"""Deterministic Voice Tuner feedback proof harness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import voice_tuner_feedback as vtf  # noqa: E402


def run_case(case: dict, iterations: int) -> dict:
    rules: list[dict] = []
    failures: list[str] = []
    candidates = [str(case["bad_candidate"]), str(case["good_candidate"])]
    for iteration in range(iterations):
        rules.extend(vtf.compile_voice_feedback(
            str(case["feedback"]),
            str(case["lane"]),
            str(case["format"]),
            str(case["id"]),
            "fixture",
            created_at=f"fixture-{iteration}",
        ))
        active_rules = vtf.rules_for_context(rules, str(case["lane"]), str(case["format"]), str(case["id"]))
        bad_report = vtf.evaluate_feedback_constraints(
            candidates[0],
            active_rules,
            str(case["format"]),
            str(case["lane"]),
            str(case["concept"]),
        )
        good_report = vtf.evaluate_feedback_constraints(
            candidates[1],
            active_rules,
            str(case["format"]),
            str(case["lane"]),
            str(case["concept"]),
        )
        hard_rules = [rule for rule in active_rules if rule.get("severity") == "hard"]
        if hard_rules and bad_report["ok"]:
            failures.append(f"iteration {iteration + 1}: bad candidate passed hard feedback")
        if not good_report["ok"]:
            failures.append(f"iteration {iteration + 1}: good candidate failed hard feedback")
        if len({rule["id"] for rule in active_rules}) != len(active_rules):
            failures.append(f"iteration {iteration + 1}: duplicate active rule ids")
    return {
        "id": case["id"],
        "lane": case["lane"],
        "format": case["format"],
        "rules": len(vtf.rules_for_context(rules, str(case["lane"]), str(case["format"]), str(case["id"]))),
        "passed": not failures,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", default=str(ROOT / "scripts" / "voice_tuner_feedback_cases.json"))
    parser.add_argument("--provider", default="mock", choices=["mock"])
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()

    cases = json.loads(Path(args.fixtures).read_text())
    results = [run_case(case, max(1, args.iterations)) for case in cases]
    payload = {
        "provider": args.provider,
        "iterations": args.iterations,
        "passed": all(result["passed"] for result in results),
        "results": results,
    }
    print(json.dumps(payload, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

