from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Callable


AUDIT_CATEGORIES: tuple[dict[str, str], ...] = (
    {
        "name": "Maximizing Potential",
        "standard": "The feature clearly helps Tyler get more reach, replies, followers, monetizable impressions, or reusable content leverage.",
    },
    {
        "name": "Real-World Usefulness",
        "standard": "Tyler would use it in the real workflow, under time pressure, without babysitting the app.",
    },
    {
        "name": "Ease Of Use",
        "standard": "The core action is obvious, fast, and low-friction with a clear next step.",
    },
    {
        "name": "Simplicity",
        "standard": "The feature avoids unnecessary controls, visual noise, duplicate paths, and confusing choices.",
    },
    {
        "name": "Tweet Accuracy",
        "standard": "Claims, stats, timing, sources, and live-game facts are grounded, visible, and verifiable.",
    },
    {
        "name": "Voice Match",
        "standard": "Tweet output sounds like Tyler specifically, not a generic sports account, analyst, or AI copywriter.",
    },
    {
        "name": "Compelling Writing",
        "standard": "Output is clear, emotional, specific, scroll-stopping, and easy to post.",
    },
    {
        "name": "Reply-Bait Strength",
        "standard": "Output invites agreement, disagreement, pile-ons, tension, or fan participation without sounding fake.",
    },
    {
        "name": "Monetization Leverage",
        "standard": "The workflow increases odds of replies, dwell time, repeat usage, posting volume, and X payout value.",
    },
    {
        "name": "Trust And Control",
        "standard": "Tyler can see why a suggestion was made, what facts it used, and safely reject, regenerate, edit, copy, or post it.",
    },
)

AUDIT_AREAS: tuple[str, ...] = (
    "Whole App",
    "Creator Studio",
    "Gameday",
    "Reply Mode",
    "Algorithm Score",
    "Account Audit",
)

WORKFLOW_AREAS: tuple[str, ...] = (
    "Creator Studio",
    "Gameday",
    "Reply Mode",
    "Algorithm Score",
    "Account Audit",
)

WORKFLOW_DESCRIPTIONS: dict[str, str] = {
    "Whole App": "All major Post Ascend workflows: Creator Studio, Fan Pulse Gameday, Reply Mode, Algorithm Score, Account Audit, Idea Bank, navigation, shared voice, and trust layer.",
    "Creator Studio": "Build, rewrite, grades, verify, post, save, format controls, voice controls, and paste-ready grade fixes.",
    "Gameday": "Fan Pulse live-game workflow: score freshness, feed freshness, source grounding, emotional lanes, generated drafts, copy, post, and trust controls.",
    "Reply Mode": "Reply generation workflow: context awareness, Tyler voice, safe reply controls, and conversation quality.",
    "Algorithm Score": "Standalone algorithm scoring workflow upgraded to the shared 10/10 audit rubric.",
    "Account Audit": "Account-level audit workflow: recent tweets, health score, recommendations, flagged posts, and actionability.",
}

OWNER_AREAS: tuple[str, ...] = (
    "Creator Studio",
    "Gameday",
    "Reply Mode",
    "Account Audit",
    "Algorithm Score",
    "Idea Bank",
    "navigation",
    "shared voice",
    "data/trust layer",
)

PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}


@dataclass
class AuditSubject:
    area: str
    description: str
    content: str = ""
    metadata: dict[str, Any] | None = None


@dataclass
class AuditCategoryResult:
    name: str
    score: int
    reason: str
    evidence: str
    blocking_issue: str
    ten_out_of_ten_standard: str
    fix_plan: str
    priority: str
    owner_area: str


@dataclass
class RoadmapItem:
    feature_area: str
    failing_category: str
    current_score: int
    target_10_behavior: str
    exact_change: str
    files_likely_touched: str
    acceptance_test: str
    priority: str
    estimated_size: str


@dataclass
class AuditResult:
    subject: AuditSubject
    overall_score: int
    categories: list[AuditCategoryResult]
    roadmap: list[RoadmapItem]
    generated_at: str
    summary: str


@dataclass
class AuditRunRecord:
    run_id: str
    latest: AuditResult
    children: list[AuditResult]


def description_for_area(area: str) -> str:
    return WORKFLOW_DESCRIPTIONS.get(area, WORKFLOW_DESCRIPTIONS["Whole App"])


def normalize_score(score: Any) -> int:
    try:
        value = float(score)
    except Exception:
        return 1
    if value > 10:
        value = value / 10.0
    return max(1, min(10, int(round(value))))


def _priority_for(category: str, score: int) -> str:
    if category in {"Tweet Accuracy", "Trust And Control"} and score < 10:
        return "P0" if score < 8 else "P1"
    if category in {"Ease Of Use", "Simplicity", "Real-World Usefulness"} and score < 8:
        return "P1"
    if category in {"Voice Match", "Compelling Writing", "Reply-Bait Strength"}:
        return "P2"
    if category == "Monetization Leverage":
        return "P3"
    return "P2"


def apply_overall_caps(overall: int, categories: list[AuditCategoryResult]) -> int:
    scores = {item.name: item.score for item in categories}
    capped = overall
    if min(scores.get("Tweet Accuracy", 10), scores.get("Trust And Control", 10)) < 7:
        capped = min(capped, 7)
    if scores.get("Ease Of Use", 10) < 6:
        capped = min(capped, 8)
    if scores.get("Voice Match", 10) < 7 and _is_tweet_producing_area(categories):
        capped = min(capped, 8)
    return max(1, min(10, capped))


def _is_tweet_producing_area(categories: list[AuditCategoryResult]) -> bool:
    return any(item.owner_area in {"Creator Studio", "Gameday", "Reply Mode", "Algorithm Score"} for item in categories)


def parse_ai_audit(raw: str) -> dict[str, Any]:
    clean = (raw or "").strip()
    clean = re.sub(r"```(?:json)?\s*", "", clean).strip().rstrip("`").strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if not match:
        raise ValueError("audit output did not contain JSON")
    data = json.loads(match.group())
    if not isinstance(data, dict) or "categories" not in data:
        raise ValueError("audit JSON missing categories")
    if not isinstance(data["categories"], list):
        raise ValueError("audit categories must be a list")
    return data


def validate_category_result(item: dict[str, Any]) -> bool:
    required = (
        "name",
        "score",
        "reason",
        "evidence",
        "blocking_issue",
        "ten_out_of_ten_standard",
        "fix_plan",
        "priority",
        "owner_area",
    )
    if not all(str(item.get(key, "")).strip() for key in required):
        return False
    vague = {"make it better", "improve ux", "improve quality", "needs work", "optimize it"}
    fix = str(item.get("fix_plan", "")).strip().lower()
    return fix not in vague and len(fix) >= 24


def build_deterministic_audit(subject: AuditSubject) -> AuditResult:
    area = subject.area if subject.area in AUDIT_AREAS else "Whole App"
    content = subject.content or ""
    checks = _deterministic_checks(area, content, subject.metadata or {})
    categories = [_category_from_checks(cat, area, checks) for cat in AUDIT_CATEGORIES]
    overall = int(round(sum(item.score for item in categories) / len(categories)))
    overall = apply_overall_caps(overall, categories)
    roadmap = build_roadmap(categories)
    return AuditResult(
        subject=subject,
        overall_score=overall,
        categories=categories,
        roadmap=roadmap,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        summary=f"{area} scores {overall}/10. Top blockers: {', '.join(item.failing_category for item in roadmap[:3]) or 'none'}.",
    )


def build_whole_app_audit(children: list[AuditResult], content: str = "") -> AuditResult:
    if not children:
        return build_deterministic_audit(AuditSubject("Whole App", description_for_area("Whole App"), content))
    category_results: list[AuditCategoryResult] = []
    for cat in AUDIT_CATEGORIES:
        same = [item for child in children for item in child.categories if item.name == cat["name"]]
        weakest = min(same, key=lambda item: item.score)
        avg = int(round(sum(item.score for item in same) / max(len(same), 1)))
        category_results.append(
            AuditCategoryResult(
                name=cat["name"],
                score=min(avg, weakest.score + 1),
                reason=f"Whole-app rollup. Weakest workflow: {weakest.owner_area} at {weakest.score}/10.",
                evidence=f"Aggregated {len(children)} workflow audits.",
                blocking_issue=weakest.blocking_issue,
                ten_out_of_ten_standard=cat["standard"],
                fix_plan=weakest.fix_plan,
                priority=weakest.priority,
                owner_area=weakest.owner_area,
            )
        )
    overall = int(round(sum(child.overall_score for child in children) / len(children)))
    overall = apply_overall_caps(overall, category_results)
    roadmap = build_roadmap(category_results)
    return AuditResult(
        subject=AuditSubject("Whole App", description_for_area("Whole App"), content, {"child_count": len(children)}),
        overall_score=overall,
        categories=category_results,
        roadmap=roadmap,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        summary=f"Whole App scores {overall}/10 across {len(children)} audited workflows. Top blockers: {', '.join(item.failing_category for item in roadmap[:3]) or 'none'}.",
    )


def merge_ai_audit(base: AuditResult, raw: str) -> AuditResult:
    data = parse_ai_audit(raw)
    by_name = {item.name: item for item in base.categories}
    merged: list[AuditCategoryResult] = []
    for cat in AUDIT_CATEGORIES:
        name = cat["name"]
        current = by_name[name]
        candidate = next((item for item in data.get("categories", []) if item.get("name") == name), None)
        if candidate and validate_category_result(candidate):
            merged.append(
                AuditCategoryResult(
                    name=name,
                    score=normalize_score(candidate.get("score")),
                    reason=str(candidate.get("reason", "")).strip(),
                    evidence=str(candidate.get("evidence", "")).strip(),
                    blocking_issue=str(candidate.get("blocking_issue", "")).strip(),
                    ten_out_of_ten_standard=str(candidate.get("ten_out_of_ten_standard", cat["standard"])).strip(),
                    fix_plan=str(candidate.get("fix_plan", "")).strip(),
                    priority=str(candidate.get("priority", current.priority)).strip() if str(candidate.get("priority", "")).strip() in PRIORITY_ORDER else current.priority,
                    owner_area=str(candidate.get("owner_area", current.owner_area)).strip() if str(candidate.get("owner_area", "")).strip() in OWNER_AREAS else current.owner_area,
                )
            )
        else:
            merged.append(current)
    overall = int(round(sum(item.score for item in merged) / len(merged)))
    overall = apply_overall_caps(overall, merged)
    roadmap = build_roadmap(merged)
    return AuditResult(
        subject=base.subject,
        overall_score=overall,
        categories=merged,
        roadmap=roadmap,
        generated_at=datetime.now().isoformat(timespec="seconds"),
        summary=str(data.get("summary") or f"{base.subject.area} scores {overall}/10.").strip(),
    )


def run_audit(subject: AuditSubject, ai_call: Callable[[str], str] | None = None) -> AuditResult:
    base = build_deterministic_audit(subject)
    if not ai_call:
        return base
    try:
        raw = ai_call(build_ai_prompt(subject, base))
        if raw:
            return merge_ai_audit(base, raw)
    except Exception:
        pass
    return base


def run_workflow_audits(
    area: str,
    *,
    content: str = "",
    metadata_by_area: dict[str, dict[str, Any]] | None = None,
    ai_call: Callable[[str], str] | None = None,
) -> AuditRunRecord:
    metadata_by_area = metadata_by_area or {}
    if area == "Whole App":
        children = [
            run_audit(
                AuditSubject(workflow, description_for_area(workflow), content, metadata_by_area.get(workflow, {})),
                ai_call=ai_call,
            )
            for workflow in WORKFLOW_AREAS
        ]
        latest = build_whole_app_audit(children, content)
    else:
        children = []
        latest = run_audit(
            AuditSubject(area, description_for_area(area), content, metadata_by_area.get(area, {})),
            ai_call=ai_call,
        )
    return AuditRunRecord(
        run_id=datetime.now().strftime("%Y%m%d%H%M%S"),
        latest=latest,
        children=children,
    )


def build_ai_prompt(subject: AuditSubject, base: AuditResult) -> str:
    category_shape = [
        {
            "name": item.name,
            "score": item.score,
            "reason": item.reason,
            "evidence": item.evidence,
            "blocking_issue": item.blocking_issue,
            "ten_out_of_ten_standard": item.ten_out_of_ten_standard,
            "fix_plan": item.fix_plan,
            "priority": item.priority,
            "owner_area": item.owner_area,
        }
        for item in base.categories
    ]
    return f"""Audit this Post Ascend workflow against the strict 10/10 product rubric.

AREA: {subject.area}
DESCRIPTION: {subject.description}
OPTIONAL CONTENT/OUTPUT:
{subject.content[:4000]}

DETERMINISTIC BASELINE:
{json.dumps(category_shape, indent=2)}

Rules:
- Keep scores strict. A 10 means no obvious product, trust, usage, or output-quality improvement remains.
- Accuracy and trust outrank engagement.
- Every sub-10 grade needs a concrete implementation fix, not advice.
- Fix plans must be directly implementable.
- Do not invent files. Use likely areas such as app.py, ten_x_audit.py, shared_voice/gameday.py, shared voice modules, tests.

Return ONLY valid JSON:
{{"summary":"one sentence","categories":[{{"name":"Maximizing Potential","score":1,"reason":"...","evidence":"...","blocking_issue":"...","ten_out_of_ten_standard":"...","fix_plan":"...","priority":"P0","owner_area":"Creator Studio"}}]}}"""


def _deterministic_checks(area: str, content: str, metadata: dict[str, Any]) -> dict[str, Any]:
    lower = content.lower()
    return {
        "has_content": bool(content.strip()),
        "links": "http://" in lower or "https://" in lower,
        "hashtags": "#" in content,
        "overlong": len(content) > 280 and area not in {"Account Audit", "Whole App"},
        "likely_stat_claim": bool(re.search(r"\b\d+(\.\d+)?\s*(%|points?|rebounds?|assists?|yards?|tds?|sacks?|rank|seed|straight|game)\b", lower)),
        "has_source": any(token in lower for token in ("source:", "grounded in", "espn", "verified", "per ", "according to")),
        "stale_signal": any(token in lower for token in ("halftime", "yesterday", "old", "stale", "outdated", "wrong quarter")),
        "generic_voice": any(token in lower for token in ("as an ai", "it is important", "key takeaway", "what it means", "analysis shows")),
        "reply_bait": "?" in content or "..." in content or any(token in lower for token in ("we ", "us ", "this team", "tell me", "i can't", "what are we doing")),
        "hidden_controls": bool(metadata.get("hidden_controls")),
        "duplicate_paths": bool(metadata.get("duplicate_paths")),
        "missing_timestamp": bool(metadata.get("missing_timestamp")),
        "has_post_path": bool(metadata.get("has_post_path")),
        "has_copy_path": bool(metadata.get("has_copy_path")),
        "has_grade_fixes": bool(metadata.get("has_grade_fixes")),
        "has_verify_path": bool(metadata.get("has_verify_path")),
        "has_history": bool(metadata.get("has_history")),
        "has_outcome_tracking": bool(metadata.get("has_outcome_tracking")),
        "recent_score": metadata.get("recent_score", 0),
    }


def _category_from_checks(cat: dict[str, str], area: str, checks: dict[str, Any]) -> AuditCategoryResult:
    name = cat["name"]
    score = 8
    reason = "Baseline audit found a usable workflow with specific 10/10 improvement opportunities."
    evidence = f"Area audited: {area}."
    blocking = "Needs stricter evidence and workflow proof before it can be called 10/10."
    fix = "Add concrete acceptance checks and remove the highest-friction or lowest-trust failure in this workflow."
    owner = _owner_for_area(area)

    if name == "Tweet Accuracy":
        score = 10
        if checks["likely_stat_claim"] and not checks["has_source"]:
            score = 5
            blocking = "The content appears to contain a factual/stat claim without visible grounding."
            fix = "Require visible source grounding or a verification result before the tweet can score above 7."
        if checks["stale_signal"] or checks["missing_timestamp"]:
            score = min(score, 6)
            blocking = "Timing-sensitive content can be stale or phase-wrong without a timestamp/source check."
            fix = "Add timestamp/source display and block stale live facts before generating or posting."
        reason = "Accuracy is strict: unsupported stats, stale timing, and missing source labels cap the grade."
    elif name == "Trust And Control":
        score = 7
        if not checks["has_source"]:
            score = 6
            blocking = "The workflow does not clearly show what facts or source the recommendation used."
            fix = "Show a 'Grounded in' source packet and require copy/post/regenerate controls beside every recommendation."
        if checks["has_verify_path"] and checks["has_copy_path"]:
            score = max(score, 8)
        reason = "Trust depends on visible source, editability, rejection, regeneration, and safe posting."
    elif name == "Ease Of Use":
        score = 7
        if checks["hidden_controls"]:
            score = 5
            blocking = "Hidden or indirect controls make the primary action harder to discover."
            fix = "Replace hidden dock-only triggers with visible primary buttons and one clear next action."
        if checks["has_post_path"] and checks["has_copy_path"]:
            score = max(score, 8)
        reason = "The grade reflects friction between intent and the next available action."
    elif name == "Simplicity":
        score = 7
        if checks["duplicate_paths"]:
            score = 5
            blocking = "Duplicate paths or legacy surfaces increase decision load."
            fix = "Quarantine or remove dead legacy flows and collapse duplicate choices into one primary path."
        reason = "Simplicity is lowered by duplicated routes, extra controls, or unclear workflow hierarchy."
    elif name == "Voice Match":
        score = 8
        if checks["generic_voice"]:
            score = 5
            blocking = "Output contains generic analyst or AI phrasing."
            fix = "Route output through Tyler-specific voice examples and reject generic analytical phrases."
        reason = "Voice is judged against Tyler-specific tone, not generic polish."
    elif name == "Reply-Bait Strength":
        score = 8 if checks["reply_bait"] else 6
        blocking = "The output does not create enough fan tension or response pressure." if score < 8 else "Reply mechanics can still be more intentional."
        fix = "Add a declarative tension closer, fan-sided 'we/us' language, or a clean disagreement hook without inventing facts."
        reason = "Reply bait should invite fan response without fake engagement farming."
    elif name == "Compelling Writing":
        score = 7 if checks["has_content"] else 5
        blocking = "The writing lacks enough concrete emotional specificity to be reliably postable."
        fix = "Tighten the opener, remove generic framing, and make the emotional judgment concrete in one sentence."
        reason = "Compelling writing needs clarity, specificity, and immediate emotional stakes."
    elif name == "Real-World Usefulness":
        score = 7
        if checks["has_history"] and checks["has_grade_fixes"]:
            score = 8
        blocking = "The workflow still needs proof it works under real posting pressure."
        fix = "Add a manual acceptance checklist: run the feature on a real moment and require 4 of 5 outputs to be postable without edits."
        reason = "Usefulness is measured by whether Tyler would actually use it during the job."
    elif name == "Maximizing Potential":
        score = 7
        blocking = "The workflow does not yet connect output quality to growth or monetizable engagement outcomes."
        fix = "Attach every recommendation to an expected reach/reply/dwell-time lever and track posted outcome feedback."
        reason = "Potential is about reach, replies, followers, monetizable impressions, and content leverage."
    elif name == "Monetization Leverage":
        score = 6
        if checks["has_outcome_tracking"]:
            score = 8
        blocking = "The workflow does not yet close the loop from suggestion to posted performance."
        fix = "Add post outcome tracking, suggested follow-up replies, and reuse prompts for high-performing posts."
        reason = "Monetization requires repeatable posting volume, replies, dwell time, and feedback loops."

    priority = _priority_for(name, score)
    return AuditCategoryResult(
        name=name,
        score=score,
        reason=reason,
        evidence=evidence,
        blocking_issue=blocking,
        ten_out_of_ten_standard=cat["standard"],
        fix_plan=fix,
        priority=priority,
        owner_area=owner,
    )


def _owner_for_area(area: str) -> str:
    mapping = {
        "Creator Studio": "Creator Studio",
        "Gameday": "Gameday",
        "Reply Mode": "Reply Mode",
        "Algorithm Score": "Algorithm Score",
        "Account Audit": "Account Audit",
        "Whole App": "navigation",
    }
    return mapping.get(area, "navigation")


def build_roadmap(categories: list[AuditCategoryResult]) -> list[RoadmapItem]:
    items = [
        RoadmapItem(
            feature_area=item.owner_area,
            failing_category=item.name,
            current_score=item.score,
            target_10_behavior=item.ten_out_of_ten_standard,
            exact_change=item.fix_plan,
            files_likely_touched=_files_for_owner(item.owner_area),
            acceptance_test=_acceptance_for(item),
            priority=item.priority,
            estimated_size=_size_for(item),
        )
        for item in categories
        if item.score < 10
    ]
    items.sort(key=lambda item: (PRIORITY_ORDER.get(item.priority, 9), item.current_score, item.feature_area))
    return items


def _files_for_owner(owner: str) -> str:
    if owner == "Gameday":
        return "app.py, shared_voice/gameday.py, tests/test_gameday.py"
    if owner in {"Creator Studio", "Algorithm Score", "Account Audit", "Reply Mode", "Idea Bank", "navigation"}:
        return "app.py, ten_x_audit.py, tests/test_ten_x_audit.py"
    if owner == "shared voice":
        return "shared_voice/*.py, app.py, tests"
    if owner == "data/trust layer":
        return "apis.py, app.py, ten_x_audit.py, tests"
    return "app.py, tests"


def _acceptance_for(item: AuditCategoryResult) -> str:
    return f"Re-run 10/10 Audit for {item.owner_area}; {item.name} must score 10 with evidence and no vague fix plan."


def _size_for(item: AuditCategoryResult) -> str:
    if item.priority == "P0":
        return "M"
    if item.priority == "P1":
        return "M"
    return "S"


def to_dict(result: AuditResult) -> dict[str, Any]:
    return asdict(result)


def from_dict(data: dict[str, Any]) -> AuditResult:
    subject_data = data.get("subject", {})
    return AuditResult(
        subject=AuditSubject(**subject_data),
        overall_score=int(data.get("overall_score", 0)),
        categories=[AuditCategoryResult(**item) for item in data.get("categories", [])],
        roadmap=[RoadmapItem(**item) for item in data.get("roadmap", [])],
        generated_at=str(data.get("generated_at", "")),
        summary=str(data.get("summary", "")),
    )


def run_record_to_dict(record: AuditRunRecord) -> dict[str, Any]:
    return {
        "run_id": record.run_id,
        "latest": to_dict(record.latest),
        "children": [to_dict(child) for child in record.children],
    }


def run_record_from_dict(data: dict[str, Any]) -> AuditRunRecord:
    return AuditRunRecord(
        run_id=str(data.get("run_id", "")),
        latest=from_dict(data.get("latest", {})),
        children=[from_dict(item) for item in data.get("children", [])],
    )


def append_history(history: list[dict[str, Any]], record: AuditRunRecord, *, limit: int = 20) -> list[dict[str, Any]]:
    updated = [run_record_to_dict(record)] + [item for item in history if isinstance(item, dict)]
    return updated[:limit]


def trend_rows(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in history:
        try:
            record = run_record_from_dict(item)
        except Exception:
            continue
        rows.append(
            {
                "Run": record.run_id,
                "Area": record.latest.subject.area,
                "Score": record.latest.overall_score,
                "P0": sum(1 for road in record.latest.roadmap if road.priority == "P0"),
                "P1": sum(1 for road in record.latest.roadmap if road.priority == "P1"),
            }
        )
    return rows


def markdown_summary(result: AuditResult) -> str:
    lines = [
        f"# 10/10 Audit: {result.subject.area}",
        "",
        f"Generated: {result.generated_at}",
        f"Overall Score: {result.overall_score}/10",
        "",
        f"Summary: {result.summary}",
        "",
        "## Category Grades",
    ]
    for item in result.categories:
        lines.extend(
            [
                f"- **{item.name}: {item.score}/10** [{item.priority}]",
                f"  - Reason: {item.reason}",
                f"  - Blocker: {item.blocking_issue}",
                f"  - Fix: {item.fix_plan}",
            ]
        )
    lines.append("")
    lines.append("## Path To 10/10")
    for item in result.roadmap:
        lines.extend(
            [
                f"- **{item.priority} | {item.feature_area} | {item.failing_category} ({item.current_score}/10)**",
                f"  - Change: {item.exact_change}",
                f"  - Acceptance: {item.acceptance_test}",
                f"  - Files: {item.files_likely_touched}",
            ]
        )
    return "\n".join(lines)
