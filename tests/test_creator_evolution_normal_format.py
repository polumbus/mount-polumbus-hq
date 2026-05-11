import creator_evolution as ce


def test_normal_tweet_prompt_blocks_old_stacked_template():
    prompt = ce.build_generation_prompt(
        "Switching goalies after one loss creates a playoff storyline.",
        "Normal Tweet",
        "Skeptical",
        ce.initial_state(),
    )

    assert "do not use the old three-stacked-line template" in prompt
    assert "one intentional break maximum" in prompt


def test_normal_tweet_warning_targets_repeated_blank_line_cadence():
    compact = (
        "Switching to Blackwood feels like solving a problem we didn't have. "
        "Wedgwood rattled off 6 straight playoff wins and one loss turned it into a goalie storyline..."
    )
    stacked = (
        "Switching to Blackwood feels like solving a problem we didn't have.\n\n"
        "Wedgwood rattled off 6 straight playoff wins and you bail after one loss.\n\n"
        "That's how you turn one bad goal into a goalie storyline..."
    )

    assert not any("Too many line breaks" in warning for warning in ce.draft_quality_report(compact, "Normal Tweet", "Skeptical")["warnings"])
    assert any("Too many line breaks" in warning for warning in ce.draft_quality_report(stacked, "Normal Tweet", "Skeptical")["warnings"])
