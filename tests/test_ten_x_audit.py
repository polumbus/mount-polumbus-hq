from ten_x_audit import (
    AUDIT_CATEGORIES,
    AuditSubject,
    apply_overall_caps,
    build_deterministic_audit,
    normalize_score,
    parse_ai_audit,
    run_audit,
    validate_category_result,
)


def test_rubric_contains_required_categories():
    names = [item["name"] for item in AUDIT_CATEGORIES]
    assert names == [
        "Maximizing Potential",
        "Real-World Usefulness",
        "Ease Of Use",
        "Simplicity",
        "Tweet Accuracy",
        "Voice Match",
        "Compelling Writing",
        "Reply-Bait Strength",
        "Monetization Leverage",
        "Trust And Control",
    ]


def test_scores_normalize_to_one_to_ten():
    assert normalize_score(0) == 1
    assert normalize_score(7.4) == 7
    assert normalize_score(85) == 8
    assert normalize_score("bad") == 1


def test_trust_caps_overall_score():
    result = build_deterministic_audit(
        AuditSubject(
            area="Gameday",
            description="Live game workflow",
            content="Halftime take with 12 points and no source.",
            metadata={"missing_timestamp": True},
        )
    )
    assert result.overall_score <= 7
    assert any(item.name == "Tweet Accuracy" and item.score < 7 for item in result.categories)


def test_sub_ten_categories_have_concrete_fix_plan():
    result = build_deterministic_audit(AuditSubject(area="Creator Studio", description="Draft workflow", content="Generic key takeaway."))
    for item in result.categories:
        if item.score < 10:
            assert len(item.fix_plan) >= 24
            assert item.fix_plan.lower() not in {"make it better", "improve ux", "improve quality"}


def test_parser_rejects_malformed_or_vague_output():
    try:
        parse_ai_audit("not json")
    except ValueError:
        pass
    else:
        raise AssertionError("parse_ai_audit should reject malformed output")

    assert not validate_category_result(
        {
            "name": "Ease Of Use",
            "score": 6,
            "reason": "Too much friction.",
            "evidence": "Button unclear.",
            "blocking_issue": "Unclear next action.",
            "ten_out_of_ten_standard": "Obvious and fast.",
            "fix_plan": "make it better",
            "priority": "P1",
            "owner_area": "Creator Studio",
        }
    )


def test_gameday_audit_flags_stale_and_missing_timestamp():
    result = build_deterministic_audit(
        AuditSubject(
            area="Gameday",
            description="Fan Pulse",
            content="Halftime and this still feels wrong.",
            metadata={"missing_timestamp": True},
        )
    )
    accuracy = next(item for item in result.categories if item.name == "Tweet Accuracy")
    assert accuracy.score < 7
    assert accuracy.priority == "P0"


def test_creator_studio_flags_generic_voice_and_weak_reply_bait():
    result = build_deterministic_audit(
        AuditSubject(
            area="Creator Studio",
            description="Tweet builder",
            content="Key takeaway: it is important to understand what it means for Denver.",
        )
    )
    voice = next(item for item in result.categories if item.name == "Voice Match")
    reply = next(item for item in result.categories if item.name == "Reply-Bait Strength")
    assert voice.score < 7
    assert reply.score < 8


def test_roadmap_sorts_p0_before_polish():
    result = build_deterministic_audit(
        AuditSubject(
            area="Gameday",
            description="Fan Pulse",
            content="Halftime take with 27 points and no source.",
            metadata={"missing_timestamp": True},
        )
    )
    assert result.roadmap
    assert result.roadmap[0].priority == "P0"


def test_ai_merge_preserves_strict_shape():
    raw = """
    {"summary":"Creator Studio has trust and usability gaps.","categories":[
      {"name":"Maximizing Potential","score":8,"reason":"Good leverage.","evidence":"Build flow exists.","blocking_issue":"No outcome loop.","ten_out_of_ten_standard":"Tracks performance.","fix_plan":"Add posted outcome feedback and reuse prompts from winners.","priority":"P3","owner_area":"Creator Studio"}
    ]}
    """
    result = run_audit(AuditSubject(area="Creator Studio", description="Draft workflow"), ai_call=lambda _prompt: raw)
    assert result.summary == "Creator Studio has trust and usability gaps."
    assert next(item for item in result.categories if item.name == "Maximizing Potential").score == 8
