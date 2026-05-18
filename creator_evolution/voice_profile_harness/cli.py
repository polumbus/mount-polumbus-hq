"""CLI for the read-only Creator Evolution Tyler voice profile harness."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .approval_store import approve_profile, reject_pending
from .config import artifact_path, ensure_artifact_dirs, read_json, read_jsonl, redact_secrets
from .evaluation import run_evaluation
from .ingest_archive import ingest_manual, ingest_x_archive
from .ingest_x import ingest_twitterapiio
from .prompt_builder import build_profile
from .voice_analyzer import analyze_artifacts, normalize_artifacts


def _print(data: dict) -> None:
    print(redact_secrets(json.dumps(data, indent=2, default=str)))


def cmd_ingest(args) -> dict:
    if args.source != "twitterapiio":
        raise RuntimeError(f"unsupported source: {args.source}")
    return ingest_twitterapiio(
        args.username,
        months=args.months,
        root=args.root,
        window_days=args.window_days,
        max_pages_per_window=args.max_pages_per_window,
    )


def cmd_ingest_archive(args) -> dict:
    return ingest_x_archive(args.archive_path, months=args.months, root=args.root)


def cmd_ingest_manual(args) -> dict:
    return ingest_manual(args.path, root=args.root)


def cmd_normalize(args) -> dict:
    return normalize_artifacts(root=args.root, include_replies=args.include_replies)


def cmd_analyze(args) -> dict:
    return analyze_artifacts(root=args.root)


def cmd_build_profile(args) -> dict:
    return build_profile(root=args.root)


def cmd_evaluate(args) -> dict:
    return run_evaluation(root=args.root, profile_path=args.profile)


def cmd_approve(args) -> dict:
    return approve_profile(args.profile, root=args.root, approved_by=args.approved_by)


def cmd_reject(args) -> dict:
    return reject_pending(root=args.root)


def cmd_status(args) -> dict:
    ensure_artifact_dirs(args.root)
    pending = read_json(artifact_path("profiles/pending_profile.json", args.root), {}) or {}
    approved = read_json(artifact_path("profiles/approved_profile.json", args.root), {}) or {}
    return {
        "root": str(artifact_path(".", args.root).resolve()),
        "normalized_tweets": len(read_jsonl(artifact_path("cache/normalized_tweets.jsonl", args.root))),
        "metric_snapshots": len(read_jsonl(artifact_path("cache/metric_snapshots.jsonl", args.root))),
        "voice_features": len(read_jsonl(artifact_path("cache/voice_features.jsonl", args.root))),
        "format_features": len(read_jsonl(artifact_path("cache/format_features.jsonl", args.root))),
        "pending_profile_version": pending.get("profile_version", ""),
        "pending_activation_status": pending.get("activation_status", ""),
        "approved_profile_version": approved.get("profile_version", ""),
        "approved_activation_status": approved.get("activation_status", ""),
        "read_only": True,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Creator Evolution Tyler voice profile harness")
    parser.add_argument("--root", default=None, help="Artifact root. Defaults to data/creator_evolution/voice_profile.")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest")
    ingest.add_argument("--source", required=True, choices=["twitterapiio"])
    ingest.add_argument("--username", required=True)
    ingest.add_argument("--months", type=int, default=12)
    ingest.add_argument("--window-days", type=int, default=7)
    ingest.add_argument("--max-pages-per-window", type=int, default=5)
    ingest.set_defaults(func=cmd_ingest)

    archive = sub.add_parser("ingest-archive")
    archive.add_argument("--archive-path", required=True)
    archive.add_argument("--months", type=int, default=12)
    archive.set_defaults(func=cmd_ingest_archive)

    manual = sub.add_parser("ingest-manual")
    manual.add_argument("--path", required=True)
    manual.set_defaults(func=cmd_ingest_manual)

    normalize = sub.add_parser("normalize")
    normalize.add_argument("--include-replies", action="store_true")
    normalize.set_defaults(func=cmd_normalize)

    analyze = sub.add_parser("analyze")
    analyze.set_defaults(func=cmd_analyze)

    profile = sub.add_parser("build-profile")
    profile.set_defaults(func=cmd_build_profile)

    evaluate = sub.add_parser("evaluate")
    evaluate.add_argument("--profile", default=None)
    evaluate.set_defaults(func=cmd_evaluate)

    approve = sub.add_parser("approve")
    approve.add_argument("--profile", default=None)
    approve.add_argument("--approved-by", default="owner")
    approve.set_defaults(func=cmd_approve)

    reject = sub.add_parser("reject")
    reject.set_defaults(func=cmd_reject)

    status = sub.add_parser("status")
    status.set_defaults(func=cmd_status)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.func(args)
    except Exception as exc:
        _print({"ok": False, "error": redact_secrets(exc)})
        return 1
    _print({"ok": True, **(result or {})})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
