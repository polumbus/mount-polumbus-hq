from shared_voice.gameday import (
    GAMEDAY_LANES,
    GAMEDAY_MOMENTS,
    build_gameday_prompt,
    generate_gameday_drafts,
    select_gameday_examples,
    validate_gameday_draft,
)


def _game():
    return {
        "team": "Nuggets",
        "opponent": "Blazers",
        "score_line": "Nuggets 92 - Blazers 106",
        "status": "4th Quarter",
        "state": "live",
        "sport": "NBA",
    }


def test_prompt_covers_every_lane_without_creator_studio_language():
    for lane in GAMEDAY_LANES:
        prompt, system = build_gameday_prompt(
            game=_game(),
            lane=lane,
            moment="Bad Possession",
            context="Nuggets are giving the ball away again.",
            examples=["Nuggets are down 14 to Portland chasing the three seed. This team can't afford soft nights in April."],
        )
        combined = f"{system}\n{prompt}"
        assert "This is NOT Creator Studio" in combined
        assert "fan instant-reaction" in combined
        assert "Ban ESPN-style analysis" in combined
        assert lane in combined
        assert "180 characters max" in combined


def test_prompt_covers_every_moment():
    for moment in GAMEDAY_MOMENTS:
        prompt, _system = build_gameday_prompt(
            game=_game(),
            lane="Fan Pulse",
            moment=moment,
            context="",
            examples=[],
        )
        assert f"Moment button: {moment}" in prompt


def test_validator_rejects_analytical_drift():
    bad_lines = [
        "The structural failure is obvious after that possession.",
        "This is a film-room observation more than a fan reaction.",
        "Here is what it means for Denver going forward.",
    ]
    for text in bad_lines:
        ok, reason = validate_gameday_draft(text)
        assert not ok
        assert reason


def test_select_examples_prefers_reply_heavy_live_reactions():
    tweets = [
        {
            "text": "The Nuggets adjusted the weak-side action and changed the coverage math.",
            "replyCount": 0,
            "likeCount": 100,
            "retweetCount": 2,
            "viewCount": 10000,
        },
        {
            "text": "I hate how familiar this feels. This team can't afford soft nights in April.",
            "replyCount": 35,
            "likeCount": 40,
            "retweetCount": 4,
            "viewCount": 2000,
        },
    ]
    examples = select_gameday_examples(tweets, limit=1)
    assert examples == ["I hate how familiar this feels. This team can't afford soft nights in April."]


def test_generate_filters_bad_ai_and_fills_fallbacks():
    def fake_ai(_prompt, _system, _max_tokens):
        return """
        {"drafts":[
          {"text":"The structural failure is obvious after that possession."},
          {"text":"What are we doing."}
        ]}
        """

    drafts, _raw = generate_gameday_drafts(
        game=_game(),
        lane="Mad",
        moment="Bad Possession",
        context="",
        signal_tweet=None,
        examples=[],
        ai_call=fake_ai,
    )
    assert len(drafts) == 5
    assert "What are we doing." in drafts
    assert all(validate_gameday_draft(draft)[0] for draft in drafts)
