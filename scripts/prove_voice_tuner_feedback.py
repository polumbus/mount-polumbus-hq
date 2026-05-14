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


def _check_expectations(case: dict, active_rules: list[dict], bad_report: dict, good_report: dict, strict: bool) -> list[str]:
    failures: list[str] = []
    if strict and not active_rules:
        failures.append("strict: no active rules compiled")
    expected_kinds = set(case.get("expected_rule_kinds", []) or [])
    actual_kinds = {str(rule.get("kind")) for rule in active_rules}
    missing_kinds = sorted(expected_kinds - actual_kinds)
    if strict and missing_kinds:
        failures.append(f"strict: missing expected rule kinds {missing_kinds}")
    if case.get("bad_requires_hard_failure") and not bad_report.get("hard_failures"):
        failures.append("bad candidate did not produce required hard failure")
    if case.get("bad_requires_warning") and not bad_report.get("soft_warnings"):
        failures.append("bad candidate did not produce required soft warning")
    if "bad_max_feedback_score" in case and int(bad_report.get("feedback_score", 100)) > int(case["bad_max_feedback_score"]):
        failures.append("bad candidate feedback score too high")
    if not good_report.get("ok"):
        failures.append("good candidate failed hard feedback")
    if not case.get("good_allows_warnings", True) and good_report.get("soft_warnings"):
        failures.append("good candidate had soft warnings")
    if "good_min_feedback_score" in case and int(good_report.get("feedback_score", 0)) < int(case["good_min_feedback_score"]):
        failures.append("good candidate feedback score too low")
    if strict and bad_report == good_report:
        failures.append("strict: bad and good reports are identical")
    if strict and int(bad_report.get("feedback_score", 100)) >= int(good_report.get("feedback_score", 0)):
        failures.append("strict: bad candidate did not score below good candidate")
    return failures


def run_case(case: dict, iterations: int, strict: bool) -> dict:
    rules: list[dict] = []
    failures: list[str] = []
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
            str(case["bad_candidate"]),
            active_rules,
            str(case["format"]),
            str(case["lane"]),
            str(case["concept"]),
        )
        good_report = vtf.evaluate_feedback_constraints(
            str(case["good_candidate"]),
            active_rules,
            str(case["format"]),
            str(case["lane"]),
            str(case["concept"]),
        )
        if len({rule["id"] for rule in active_rules}) != len(active_rules):
            failures.append(f"iteration {iteration + 1}: duplicate active rule ids")
        for failure in _check_expectations(case, active_rules, bad_report, good_report, strict):
            failures.append(f"iteration {iteration + 1}: {failure}")
    active_rules = vtf.rules_for_context(rules, str(case["lane"]), str(case["format"]), str(case["id"]))
    return {
        "id": case["id"],
        "lane": case["lane"],
        "format": case["format"],
        "rules": len(active_rules),
        "rule_kinds": sorted({str(rule.get("kind")) for rule in active_rules}),
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
    results = [run_case(case, max(1, args.iterations), args.strict) for case in cases]
    payload = {
        "provider": args.provider,
        "iterations": args.iterations,
        "strict": bool(args.strict),
        "passed": all(result["passed"] for result in results),
        "results": results,
    }
    print(json.dumps(payload, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
