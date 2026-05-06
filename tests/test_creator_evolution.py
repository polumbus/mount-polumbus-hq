import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import apis
import creator_evolution as ce
import creator_evolution_pulse as pulse


NOW = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)


def _tweet(tweet_id, text, *, hours_ago, views=1000, likes=20, replies=4, reposts=2, quotes=0, bookmarks=0):
    return {
        "id": str(tweet_id),
        "text": text,
        "createdAt": (NOW - timedelta(hours=hours_ago)).isoformat(),
        "viewCount": views,
        "likeCount": likes,
        "replyCount": replies,
        "retweetCount": reposts,
        "quoteCount": quotes,
        "bookmarkCount": bookmarks,
    }


class CreatorEvolutionTests(unittest.TestCase):
    def test_prompt_excludes_hall_of_fame_blocks(self):
        state = ce.refresh_state(None, [
            _tweet(1, "Bo Nix getting better every week is becoming a pretty annoying problem for the division...", hours_ago=90, views=9000, likes=180, replies=30, reposts=18),
            _tweet(2, "The Nuggets keep finding new ways to make a normal night feel weirdly stressful...", hours_ago=96, views=4200, likes=70, replies=12, reposts=8),
            _tweet(3, "At some point the Broncos plan has to stop being a theory and start looking like one on Sundays...", hours_ago=110, views=7000, likes=110, replies=22, reposts=13),
        ], handle="polfam", now=NOW)
        prompt = ce.build_generation_prompt(
            "Broncos fans are talking themselves into the roster again",
            "Normal Tweet",
            "Witty Edge",
            state,
        )

        self.assertNotIn("HALL OF FAME REFERENCE TWEETS", prompt)
        self.assertNotIn("HALL OF FAME TWEET BENCHMARKS", prompt)
        self.assertNotIn("TYLER'S HALL OF FAME DATA", prompt)
        self.assertIn("Never use Hall of Fame tweets", prompt)

    def test_build_prompt_uses_structured_source_material_without_hof(self):
        state = ce.refresh_state(None, [
            _tweet(1, "The best Broncos posts lately all leave the uncomfortable part hanging...", hours_ago=90, views=9000, likes=180, replies=30, reposts=18),
            _tweet(2, "The funny part is the plan makes sense right until you say it out loud...", hours_ago=110, views=7000, likes=110, replies=22, reposts=13),
        ], handle="polfam", now=NOW)

        prompt = ce.build_generation_prompt(
            "TOPIC: Broncos draft needs\nTENSION: fans want the fun pick\nANGLE: the boring pick might be the tell",
            "Normal Tweet",
            "Witty Edge",
            state,
            action="build",
        )

        self.assertIn("Build 3 distinct", prompt)
        self.assertIn("SOURCE MATERIAL", prompt)
        self.assertIn("BUILD MODE", prompt)
        self.assertIn("LANE BEHAVIOR", prompt)
        self.assertIn("Witty Edge:", prompt)
        self.assertIn("TOPIC:", prompt)
        self.assertNotIn("HALL OF FAME REFERENCE TWEETS", prompt)
        self.assertIn("Never use Hall of Fame tweets", prompt)

    def test_refresh_state_filters_originals_scores_and_estimates_twitterapi_cost(self):
        tweets = [
            _tweet(1, "A text-only Broncos take with a little tension at the end...", hours_ago=90, views=8000, likes=140, replies=28, reposts=16),
            _tweet(2, "A mature Nuggets post that did fine but did not travel very far", hours_ago=100, views=1100, likes=16, replies=2, reposts=1),
            _tweet(3, "A mature Avs post that got replies but not enough reach", hours_ago=120, views=900, likes=12, replies=8, reposts=0),
            _tweet(4, "A fresh Broncos thought that should stay provisional", hours_ago=3, views=600, likes=12, replies=2, reposts=1),
            _tweet(5, "RT somebody else's post", hours_ago=90, views=9999),
            _tweet(6, "@someone a reply that should not teach Creator Evolution", hours_ago=90, views=9999),
        ]

        state = ce.refresh_state(None, tweets, handle="polfam", now=NOW)

        self.assertEqual(state["sync_status"]["handle"], "polfam")
        self.assertEqual(state["sync_status"]["original_tweet_count"], 4)
        self.assertEqual(state["patterns"]["mature_count"], 3)
        self.assertEqual(state["patterns"]["provisional_count"], 1)
        self.assertEqual(len(state["snapshots"]), 4)
        self.assertEqual(state["api_usage"]["provider"], "twitterapi.io")
        self.assertEqual(state["api_usage"]["estimated_cost_usd"], round(4 / 1000 * 0.15, 4))
        self.assertTrue(all(not item["text"].startswith(("RT ", "@")) for item in state["tweets"]))

    def test_rule_proposals_are_inert_until_approved(self):
        state = ce.refresh_state(None, [
            _tweet(1, "The best Broncos posts lately all leave the uncomfortable part hanging...", hours_ago=90, views=9000, likes=180, replies=30, reposts=18),
            _tweet(2, "Text-only Nuggets tension is doing more than another link ever would...", hours_ago=96, views=4200, likes=70, replies=12, reposts=8),
            _tweet(3, "The funny part is the plan makes sense right until you say it out loud...", hours_ago=110, views=7000, likes=110, replies=22, reposts=13),
        ], handle="polfam", now=NOW)

        pending = [p for p in state["proposals"] if p["status"] == "pending"]
        self.assertTrue(pending)
        self.assertEqual(ce.approved_rules_text(state), "")
        self.assertNotIn(pending[0]["rule"], ce.performance_context(state))

        approved = ce.approve_proposal(state, pending[0]["id"], now=NOW)

        self.assertEqual(approved["approved_rules"][0]["proposal_id"], pending[0]["id"])
        self.assertIn(pending[0]["rule"], ce.approved_rules_text(approved))
        self.assertIn(pending[0]["rule"], ce.performance_context(approved))

    def test_has_separate_state_and_route_contract(self):
        self.assertEqual(ce.STATE_FILENAME, "creator_evolution_state.json")
        self.assertEqual(ce.GIST_FILENAME, "hq_creator_evolution.json")

        app_text = Path("app.py").read_text()
        self.assertIn('"Creator Evolution"', app_text)
        self.assertIn("page_creator_evolution", app_text)
        self.assertIn("_ce_build_dialog", app_text)
        self.assertIn("_ce_show_build_dialog", app_text)
        self.assertIn("_ce_inspiration_dialog", app_text)
        self.assertIn("_ce_show_inspiration", app_text)
        self.assertIn("_ce_pulse_dialog", app_text)
        self.assertIn("_ce_show_pulse", app_text)
        self.assertIn("ce_pulse", app_text)
        self.assertIn("ce_whats_hot", app_text)
        self.assertIn("CE_COMPAT_DEFAULTS", app_text)
        self.assertIn("ce_banger_data", app_text)
        self.assertIn("ce_quality_report", app_text)
        self.assertIn("_ce_sync_budget_for_mode(\"backfill\")", app_text)
        self.assertIn("_ce_budget_preflight_for_mode", app_text)
        self.assertIn("generated_lineage", app_text)
        self.assertIn("Creator Evolution rejected every generated draft", app_text)
        self.assertIn("Creator Evolution blocked this post", app_text)
        self.assertIn("ci_banger_data", app_text)

        ce_runner = app_text.split("def _run_ce_ai", 1)[1].split("def _ce_output_panel_impl", 1)[0]
        self.assertIn("_ce_build_generation_prompt", ce_runner)
        self.assertNotIn("ce.build_generation_prompt(", ce_runner)
        self.assertNotIn("_generate_build_data", ce_runner)
        self.assertNotIn("_hall_of_fame_reference_block", ce_runner)
        self.assertNotIn("analyze_personal_patterns", ce_runner)
        self.assertNotIn("get_system_for_voice", ce_runner)

        ce_hot = app_text.split("def _ce_inspiration_dialog", 1)[1].split('@st.dialog("Creator Studio"', 1)[0]
        self.assertIn("_run_creator_evolution_hot_signals", ce_hot)
        self.assertIn("_ce_pending", ce_hot)
        self.assertNotIn("_run_ci_ai", ce_hot)
        self.assertNotIn("_build_wh_hook_cached", ce_hot)

    def test_ai_sounding_phrase_detector_catches_generic_content_language(self):
        hits = ce.ai_sounding_hits("Here's the thing: at the end of the day this is a game-changer.")

        self.assertIn("here's the thing", hits)
        self.assertIn("at the end of the day", hits)
        self.assertIn("game-changer", hits)

    def test_lane_recipe_changes_prompt_behavior(self):
        prompt = ce.build_generation_prompt(
            "Nuggets fans are trying to stay normal about this bench rotation",
            "Punchy Tweet",
            "Deadpan",
            ce.initial_state(),
        )

        self.assertIn("Deadpan:", prompt)
        self.assertIn("Straight-faced", prompt)
        self.assertIn("No exclamation points", prompt)

    def test_sarcastic_lane_matches_creator_studio_voice_block(self):
        self.assertIn("Sarcastic", ce.EMOTION_LANES)

        prompt = ce.build_generation_prompt(
            "Broncos fans are watching the offense explain itself again",
            "Punchy Tweet",
            "Sarcastic",
            ce.initial_state(),
        )

        self.assertIn("SARCASTIC VOICE — DRY HUMOR MODE:", prompt)
        self.assertIn("Turns out the Patriots offense doesn't suck because of a snow storm.", prompt)
        self.assertIn("That cornerback needs to call someone he trusts right now. Not about football.", prompt)
        self.assertIn("Two modes: Cultural Leap (positive moments) or Implied Real Story (negative moments)", prompt)
        self.assertIn('Never use generic openers like "Oh interesting" "Sure" "Cool" "Oh great"', prompt)
        self.assertIn("Drop it and walk away. Never explain the joke.", prompt)

    def test_app_creator_evolution_exposes_creator_studio_sarcastic_lane(self):
        app_text = Path("app.py").read_text()
        ce_defaults = app_text.split("CE_COMPAT_DEFAULTS", 1)[1].split("BUDGET_POLICY", 1)[0]
        ce_system_prompt = app_text.split("def _creator_evolution_system_prompt", 1)[1].split("def _ce_capture_ai_error", 1)[0]

        self.assertIn('"Sarcastic"', ce_defaults)
        self.assertIn('get_system_for_voice("Sarcastic", "") if lane == "Sarcastic"', ce_system_prompt)

    def test_quality_gate_flags_ai_bait_and_deadpan_drift(self):
        report = ce.draft_quality_report(
            "Here's the thing: this is not just a game-changer but also a moment. Thoughts?!",
            "Normal Tweet",
            "Deadpan",
        )

        self.assertFalse(report["ok"])
        self.assertTrue(report["issues"])
        self.assertIn("here's the thing", report["ai_sounding_hits"])
        self.assertTrue(report["engagement_bait_hits"])

    def test_false_loser_keeps_high_reply_low_reach_posts_from_being_discarded(self):
        state = ce.refresh_state(None, [
            _tweet(1, "Low reach but every Broncos fan who saw this had something to say...", hours_ago=100, views=900, likes=12, replies=9, reposts=1),
            _tweet(2, "A regular mature post that traveled normally", hours_ago=100, views=6000, likes=120, replies=20, reposts=10),
            _tweet(3, "Another normal mature post with enough sample size", hours_ago=100, views=5000, likes=90, replies=15, reposts=7),
        ], handle="polfam", now=NOW)

        self.assertIn("1", state["patterns"]["false_loser_ids"])
        self.assertTrue(any("low-reach posts" in prop["rule"] for prop in state["proposals"]))

    def test_sync_budget_requires_confirmation_for_deep_backfill(self):
        latest = ce.sync_budget_for_mode("latest")
        backfill = ce.sync_budget_for_mode("backfill")

        self.assertFalse(latest["needs_confirmation"])
        self.assertTrue(backfill["needs_confirmation"])
        self.assertGreater(backfill["estimated_requests"], latest["estimated_requests"])

    def test_hot_signal_brief_uses_creator_evolution_lane_rules_without_hof(self):
        brief = ce.build_hot_signal_brief(
            "Broncos draft",
            "Denver is suddenly tied to another first-round tight end.",
            "timeline",
            "active debate in mentions",
            "Annoyed",
            "Normal Tweet",
        )

        self.assertIn("HOT SIGNAL", brief)
        self.assertIn("Annoyed:", brief)
        self.assertIn("Do not use Creator Studio voice modes", brief)
        self.assertNotIn("HALL OF FAME REFERENCE TWEETS", brief)
        self.assertNotIn("TYLER'S HALL OF FAME DATA", brief)

    def test_refresh_state_tracks_lineage_and_metric_deltas(self):
        first = ce.refresh_state(None, [
            _tweet(1, "The Broncos pressure is getting weird enough that fans are arguing about the boring answer...", hours_ago=90, views=1000, likes=20, replies=4, reposts=2),
        ], handle="polfam", now=NOW)
        second = ce.refresh_state(first, [
            _tweet(1, "The Broncos pressure is getting weird enough that fans are arguing about the boring answer...", hours_ago=91, views=1300, likes=26, replies=7, reposts=3),
        ], handle="polfam", now=NOW)

        self.assertEqual(second["tracked_tweets"][0]["id"], "1")
        self.assertIn("metric_delta", second["snapshots"][-1])
        self.assertEqual(second["snapshots"][-1]["metric_delta"]["views"], 300)
        self.assertEqual(second["tracked_tweets"][0]["rule_version"], ce.RULE_VERSION)

    def test_budget_preflight_blocks_when_policy_cap_is_too_low(self):
        estimate = ce.budget_preflight_for_mode("backfill", {
            "provider": "twitterapi.io",
            "daily_cap_usd": 0.01,
            "weekly_cap_usd": 1.0,
            "estimated_cost_per_1000_tweets": ce.API_ESTIMATED_COST_PER_1000_TWEETS,
        })

        self.assertTrue(estimate["blocked_by_budget"])
        self.assertTrue(estimate["needs_confirmation"])

    def test_rule_rollback_removes_approved_rule_from_active_context(self):
        state = ce.refresh_state(None, [
            _tweet(1, "The best Broncos posts lately all leave the uncomfortable part hanging...", hours_ago=90, views=9000, likes=180, replies=30, reposts=18),
            _tweet(2, "Text-only Nuggets tension is doing more than another link ever would...", hours_ago=96, views=4200, likes=70, replies=12, reposts=8),
            _tweet(3, "The funny part is the plan makes sense right until you say it out loud...", hours_ago=110, views=7000, likes=110, replies=22, reposts=13),
        ], handle="polfam", now=NOW)
        prop_id = next(p["id"] for p in state["proposals"] if p["status"] == "pending")
        approved = ce.approve_proposal(state, prop_id, now=NOW)
        rolled_back = ce.rollback_rule(approved, prop_id, now=NOW)

        self.assertNotIn(approved["approved_rules"][0]["rule"], ce.approved_rules_text(rolled_back))
        self.assertTrue(any(v["status"] == "rolled_back" for v in rolled_back["rule_versions"]))

    def test_pulse_finds_timely_sports_opportunity(self):
        tweets = [
            _tweet(10, "Broncos fans are melting down now because Sean Payton just hinted the boring draft pick might be the plan", hours_ago=1, views=9000, likes=200, replies=80, reposts=35),
        ]

        decision = pulse.find_pulse(tweets, [], ce.initial_state(), handle="polfam", now=NOW)

        self.assertEqual(decision["status"], "ready")
        self.assertIn(decision["best"]["recommended_action"], {"tweet", "reply"})
        self.assertGreaterEqual(decision["best"]["score"], pulse.DEFAULT_THRESHOLD)
        self.assertIn("PULSE OPPORTUNITY", decision["brief"])
        self.assertNotIn("Hall of Fame examples", decision["brief"])

    def test_pulse_returns_no_op_for_stale_or_weak_signal(self):
        tweets = [
            _tweet(11, "General reminder that sports are interesting", hours_ago=30, views=200, likes=2, replies=0, reposts=0),
        ]

        decision = pulse.find_pulse(tweets, [], ce.initial_state(), handle="polfam", now=NOW)

        self.assertEqual(decision["status"], "no_op")
        self.assertIn("stale_source", decision["best"]["hard_blocks"])

    def test_pulse_finds_avalanche_pregame_from_sports_context(self):
        self.assertEqual(pulse.PULSE_VERSION, "ce-pulse-v5-room-reader")

        sports_context = (
            "AVALANCHE GAME: Minnesota Wild @ Colorado Avalanche "
            "(Scheduled, puck drop tonight in 30 minutes on ESPN)"
        )

        decision = pulse.find_pulse([], [], ce.initial_state(), sports_context=sports_context, handle="polfam", now=NOW)

        self.assertEqual(decision["status"], "ready")
        self.assertGreaterEqual(decision["best"]["score"], pulse.DEFAULT_THRESHOLD)
        self.assertEqual(decision["best"]["hard_blocks"], [])
        self.assertIn("sports_context", decision["best"]["sources"])
        self.assertIn("newest signal 0.0h old", decision["best"]["why_now"])
        self.assertIn("AVALANCHE GAME", decision["brief"])

        news_decision = pulse.find_pulse(
            [],
            [],
            ce.initial_state(),
            sports_context="AVALANCHE NEWS: Colorado Avalanche coach quote sparks debate today",
            handle="polfam",
            now=NOW,
        )
        self.assertEqual(news_decision["status"], "no_op")
        self.assertIn("stale_source", news_decision["best"]["hard_blocks"])

    def test_pulse_ignores_final_avalanche_game_from_sports_context(self):
        sports_context = (
            "TODAY (Wed May 06, 2026):\n"
            "AVALANCHE GAME: Minnesota Wild 2-5 Colorado Avalanche (F)"
        )

        signals = pulse.build_signals([], [], sports_context=sports_context, now=NOW)
        decision = pulse.find_pulse([], [], ce.initial_state(), sports_context=sports_context, handle="polfam", now=NOW)

        self.assertEqual(signals, [])
        self.assertEqual(decision["status"], "no_op")
        self.assertIsNone(decision["best"])

    def test_sports_context_formats_live_avalanche_score_clock_and_period(self):
        game = {
            "state": "in",
            "period": 2,
            "clock": "2:00",
            "status_detail": "2:00 - 2nd Period",
            "completed": False,
            "away": {"name": "Minnesota Wild", "abbr": "MIN", "score": "1"},
            "home": {"name": "Colorado Avalanche", "abbr": "COL", "score": "3"},
        }

        line = apis._format_game_line(game, full_names=True)

        self.assertIn("Minnesota Wild 1 @ Colorado Avalanche 3", line)
        self.assertIn("2nd Period", line)
        self.assertIn("2:00", line)

    def test_old_completed_games_are_filtered_from_live_sports_context(self):
        old_final = {
            "date": (NOW - timedelta(hours=24)).isoformat(),
            "completed": True,
        }
        recent_final = {
            "date": (NOW - timedelta(hours=2)).isoformat(),
            "completed": True,
        }
        live_game = {
            "date": NOW.isoformat(),
            "state": "in",
            "completed": False,
        }

        self.assertFalse(apis._include_game_in_live_context(old_final, now=NOW))
        self.assertTrue(apis._include_game_in_live_context(recent_final, now=NOW))
        self.assertTrue(apis._include_game_in_live_context(live_game, now=NOW))

    def test_pulse_prioritizes_ready_avalanche_moment_over_generic_noise(self):
        tweets = [
            _tweet(
                14,
                "NHL draft debate is exploding now because the lottery result made every fan base angry",
                hours_ago=0.2,
                views=120000,
                likes=2600,
                replies=850,
                reposts=420,
                quotes=120,
            ),
        ]
        sports_context = (
            "AVALANCHE GAME: Minnesota Wild @ Colorado Avalanche "
            "(Scheduled, puck drop tonight in 30 minutes on ESPN)"
        )

        decision = pulse.find_pulse(tweets, [], ce.initial_state(), sports_context=sports_context, handle="polfam", now=NOW)

        self.assertEqual(decision["status"], "ready")
        self.assertIn("AVALANCHE GAME", decision["best"]["summary_text"])
        self.assertTrue(any("draft" in item.get("topic", "") for item in decision["top_rejected"]))

    def test_pulse_ignores_betting_lines_as_opportunities(self):
        sports_context = (
            "BETTING LINES (BetRivers):\n"
            "Moneyline: Colorado Avalanche -205 / Minnesota Wild +165\n"
            "Spread: Colorado Avalanche -1.5\n"
            "Over/Under: 6.5"
        )

        signals = pulse.build_signals([], [], sports_context=sports_context, now=NOW)

        self.assertEqual(signals, [])

    def test_pulse_returns_best_tweet_now_for_live_avalanche_game_even_above_threshold(self):
        sports_context = (
            "TODAY (Tue May 05, 2026):\n"
            "AVALANCHE GAME: Minnesota Wild @ Colorado Avalanche (12:06 - 2nd Period, 12:06)\n"
            "AVALANCHE NEWS: Wild tab Gustavsson as goalie for Game 2 against Avalanche\n"
            "BETTING LINES (MyBookie.ag):\n"
            "  Moneyline: Colorado Avalanche -1111 / Minnesota Wild +625"
        )

        decision = pulse.find_pulse([], [], {}, sports_context=sports_context, handle="polfam", now=NOW, threshold=99)

        self.assertEqual(decision["status"], "ready")
        self.assertEqual(decision["best"]["topic"], "avs")
        self.assertEqual(decision["best"]["hard_blocks"], [])
        self.assertIn("best tweet available right now", decision["message"])
        self.assertIn("newest signal 0.0h old", decision["best"]["why_now"])

    def test_pulse_reads_colorado_timeline_when_no_game_is_live(self):
        tweets = [
            _tweet(
                16,
                "Nuggets fans are arguing now because the front office keeps acting like the bench problem is a weather pattern",
                hours_ago=0.4,
                views=24000,
                likes=520,
                replies=180,
                reposts=75,
                quotes=24,
            ),
        ]

        decision = pulse.find_pulse(tweets, [], ce.initial_state(), handle="polfam", now=NOW)

        self.assertEqual(decision["status"], "ready")
        self.assertEqual(decision["best"]["topic"], "nuggets")
        self.assertIn("twitter", decision["brief"].lower())

    def test_pulse_does_not_call_bland_fresh_timeline_noise_ready(self):
        tweets = [
            _tweet(
                17,
                "Denver sports are kind of interesting today",
                hours_ago=0.2,
                views=9000,
                likes=8,
                replies=0,
                reposts=0,
                quotes=0,
            ),
        ]

        decision = pulse.find_pulse(tweets, [], ce.initial_state(), handle="polfam", now=NOW)

        self.assertNotEqual(decision["status"], "ready")
        self.assertIn("thin_room_signal", decision["best"]["soft_flags"])

    def test_cavs_does_not_get_tagged_as_avs(self):
        self.assertNotIn("avs", pulse._ce_topic_tags("Allen going out will help Cavs offense tonight"))

    def test_live_sports_context_prioritizes_avalanche_games_and_news(self):
        apis_text = Path("apis.py").read_text()
        app_text = Path("app.py").read_text()

        self.assertIn('espn_scores("nhl"', apis_text)
        self.assertIn("AVALANCHE GAME", apis_text)
        self.assertIn("AVALANCHE NEWS", apis_text)
        self.assertIn('espn_team("nhl", "COL")', apis_text)
        self.assertIn("Colorado+Avalanche+OR+Avs+NHL+breaking+news", app_text)
        self.assertIn("def _ce_avalanche_pulse_decision", app_text)
        self.assertIn("def _ce_extract_avalanche_context", app_text)
        self.assertIn("def _ce_is_completed_game_context", app_text)
        self.assertIn("def _ce_avalanche_why_now", app_text)
        self.assertIn("def _ce_pulse_cached_decision_valid", app_text)
        self.assertIn("def _ce_clear_pulse_state", app_text)
        self.assertIn("ce_pulse_decision", app_text)
        self.assertIn("st.session_state.pop(key, None)", app_text)
        self.assertIn("get_sports_context(force=True)", app_text)
        self.assertIn("_fetch_inspiration_feed.clear()", app_text)
        self.assertIn("_ce_clear_pulse_state(clear_nonce=True)", app_text)
        self.assertIn('decision.get("status") in ("pulse_error", "no_op")', app_text)
        self.assertIn("total_seconds() > 120", app_text)
        self.assertIn("Recovered detail:", app_text)
        self.assertIn("def _run_ce_pulse_drafts", app_text)
        self.assertIn("def _ce_pulse_finalize_drafts", app_text)
        self.assertIn("def _ce_draft_quality_report", app_text)
        self.assertIn('getattr(ce, "draft_quality_report", None)', app_text)
        self.assertNotIn("ce.draft_quality_report(", app_text)
        self.assertIn("def _ce_lane_recipe_text", app_text)
        self.assertIn("def _ce_install_lane_recipe_text_compat", app_text)
        self.assertIn('getattr(ce, "lane_recipe_text", None)', app_text)
        self.assertIn('setattr(ce, "lane_recipe_text", _ce_lane_recipe_text)', app_text)
        self.assertNotIn("ce.lane_recipe_text(", app_text)
        self.assertIn("def _ce_validate_generation_options", app_text)
        self.assertNotIn("ce.validate_generation_options(", app_text)
        self.assertIn("def _ce_initial_state", app_text)
        self.assertIn("def _ce_refresh_state", app_text)
        self.assertIn("def _ce_approve_proposal", app_text)
        fragile_ce_calls = [
            "ce.initial_state(",
            "ce.summarize_scores(",
            "ce.budget_preflight_for_mode(",
            "ce.refresh_state(",
            "ce.approved_rules_text(",
            "ce.sync_budget_for_mode(",
            "ce.rollback_rule(",
            "ce.approve_proposal(",
            "ce.reject_proposal(",
            "ce.build_generation_prompt(",
            "ce.build_hot_signal_brief(",
        ]
        for call in fragile_ce_calls:
            self.assertNotIn(call, app_text)
        fragile_ce_attrs = [
            "ce.DEFAULT_LANE",
            "ce.EMOTION_LANES",
            "ce.PROMPT_VERSION",
            "ce.SCORING_VERSION",
            "ce.RULE_VERSION",
            "ce.BUDGET_POLICY",
            "ce.STATE_FILENAME",
            "ce.GIST_FILENAME",
        ]
        for attr in fragile_ce_attrs:
            self.assertNotIn(attr, app_text)
        self.assertIn("_ce_pulse_source_material", app_text)
        self.assertIn("Refresh Tweets", app_text)
        self.assertIn("Use Tweet", app_text)
        self.assertIn("No gambling language", app_text)
        self.assertIn("def _ce_build_generation_prompt", app_text)
        self.assertIn("def _ce_build_hot_signal_brief", app_text)
        self.assertIn("def _ce_avs_live_state", app_text)
        self.assertIn("def _ce_avs_live_fallback_options", app_text)
        self.assertIn("def _ce_avs_no_score_fallback_options", app_text)
        self.assertIn("def _ce_pulse_meta_language", app_text)
        self.assertIn("write about that exact game state", app_text)
        self.assertIn("Avs up {score}", app_text)
        self.assertIn("_best_is_live_avs_game", app_text)
        self.assertNotIn("or not _best_is_live_avs_game", app_text)
        self.assertIn("required_score and required_score not in draft", app_text)
        self.assertIn("or _ce_pulse_meta_language(draft)", app_text)
        fallback_block = app_text.split("def _ce_pulse_local_fallback_drafts", 1)[1].split("def _ce_pulse_finalize_drafts", 1)[0]
        self.assertNotIn("Avs game nights are funny", fallback_block)
        self.assertNotIn("Pulse cannot see", fallback_block)
        self.assertNotIn("fake-timely sludge", fallback_block)
        self.assertNotIn("only useful tweet", fallback_block)
        self.assertNotIn("Anything less is just a schedule report", fallback_block)
        self.assertNotIn("the first five minutes decide everyone's emotional health", fallback_block)
        pulse_dialog = app_text.split('def _ce_pulse_dialog', 1)[1].split('@st.dialog("What', 1)[0]
        self.assertIn('st.selectbox(\n        "Pulse Voice"', pulse_dialog)
        self.assertIn('key=_lane_widget_key', pulse_dialog)
        self.assertIn('"ce_lane_pulse_select"', pulse_dialog)
        self.assertIn("ce_pulse_lane", pulse_dialog)
        self.assertIn("_lane_options = list(_ce_emotion_lanes())", pulse_dialog)
        self.assertIn('st.session_state["ce_lane"] = _lane', pulse_dialog)
        self.assertNotIn('key="ce_pulse_lane"', pulse_dialog)
        self.assertIn("NO SAFE SOURCE", pulse_dialog)
        pulse_text = Path("creator_evolution_pulse.py").read_text()
        self.assertIn("best tweet available right now", pulse_text)
        self.assertIn("ce-pulse-v5-room-reader", pulse_text)
        self.assertIn("def _is_completed_game_context", pulse_text)
        self.assertIn("if _is_completed_game_context(line):", pulse_text)
        self.assertIn("if _ce_is_completed_game_context(line):", app_text)
        self.assertNotIn("Avalanche game/news is active in live sports context; newest signal 0.0h old", app_text)
        self.assertNotIn("_run_ci_ai", pulse_dialog)

    def test_creator_evolution_dock_actions_reset_stale_dialog_state(self):
        app_text = Path("app.py").read_text()
        ce_editor = app_text.split("def _ce_reset_main_action_state", 1)[1].split("def page_creator_evolution", 1)[0]
        global_js = app_text.split("function clickStreamlitButtonByText", 1)[1].split("function processDOM", 1)[0]

        self.assertIn("function clickStreamlitButtonByText", app_text)
        self.assertIn("var liveBtns=doc.querySelectorAll('button');", global_js)
        self.assertIn("clickStreamlitButtonByText(d.dataset.dock,'dock_');", app_text)
        self.assertIn("clickStreamlitButtonByText(b.dataset.bot,'bot_');", app_text)
        self.assertIn("def _ce_reset_main_action_state", app_text)
        self.assertIn("_ce_reset_main_action_state(keep=\"_ce_pending\")", ce_editor)
        self.assertIn("_ce_reset_main_action_state(keep=\"_ce_show_build_dialog\")", ce_editor)
        self.assertIn("_ce_reset_main_action_state(keep=\"_ce_show_pulse\")", ce_editor)
        self.assertIn("_ce_clear_pulse_state(clear_nonce=True)", ce_editor)
        self.assertIn("_ce_reset_main_action_state(keep=\"_ce_show_inspiration\")", ce_editor)
        self.assertNotIn("var prefixed='dock_'+raw", app_text)
        self.assertNotIn("var prefixed='bot_'+raw", app_text)

    def test_pulse_risk_flags_do_not_require_creator_evolution_risk_helper(self):
        had_terms = hasattr(ce, "RISK_TERMS")
        old_terms = getattr(ce, "RISK_TERMS", None)
        if had_terms:
            delattr(ce, "RISK_TERMS")
        try:
            self.assertIn("heated:trash", pulse._risk_flags("That take is trash."))
        finally:
            if had_terms:
                setattr(ce, "RISK_TERMS", old_terms)

    def test_pulse_tolerates_wrapped_string_and_mixed_signal_shapes(self):
        mixed_tweets = {
            "tweets": [
                "Broncos fans are arguing now because the boring roster answer might be the whole point",
                object(),
                _tweet(13, "Nuggets fans are melting down tonight because the bench problem got weird again", hours_ago=1, views=6000, likes=120, replies=35, reposts=12),
            ]
        }
        mixed_headlines = {
            "articles": [
                {"title": "ESPN: Broncos coach quote sparks fresh debate today", "source": "espn"},
                object(),
            ]
        }
        state = {"tweets": ["A recent plain-string state item should not crash novelty scoring"]}

        decision = pulse.find_pulse(mixed_tweets, mixed_headlines, state, handle="polfam", now=NOW)

        self.assertIn(decision["status"], {"ready", "save_for_later", "no_op"})
        self.assertGreaterEqual(decision["signals_checked"], 3)

    def test_safe_pulse_returns_error_decision_instead_of_crashing(self):
        class BadString:
            def __str__(self):
                raise AttributeError("bad provider object")

        decision = pulse.safe_find_pulse({"tweets": [BadString()]}, {"articles": [BadString()]}, {}, handle="polfam", now=NOW)

        self.assertIn(decision["status"], {"no_op", "pulse_error"})
        self.assertIn("brief", decision)

    def test_app_pulse_dialog_has_fail_closed_boundary(self):
        app_text = Path("app.py").read_text()

        self.assertIn("def _ce_pulse_error_decision", app_text)
        self.assertIn("ce-pulse-import-fallback", app_text)
        self.assertIn("def _ce_pulse_debug_event", app_text)
        self.assertIn("def _safe_find_creator_evolution_pulse", app_text)
        self.assertIn('getattr(pulse, "safe_find_pulse"', app_text)
        self.assertIn('getattr(pulse, "find_pulse"', app_text)
        self.assertIn("except TypeError as exc", app_text)
        self.assertNotIn("pulse.pulse_error_decision", app_text)
        self.assertNotIn("pulse.safe_find_pulse(", app_text)
        self.assertEqual(app_text.count('_append_debug_event("creator_evolution_pulse"'), 1)

    def test_pulse_suppresses_duplicate_recent_angle(self):
        state = ce.refresh_state(None, [
            _tweet(1, "Broncos fans are melting down now because Sean Payton just hinted the boring draft pick might be the plan", hours_ago=10, views=3000, likes=80, replies=20, reposts=5),
        ], handle="polfam", now=NOW)
        tweets = [
            _tweet(12, "Broncos fans are melting down now because Sean Payton hinted the boring draft pick might be the plan", hours_ago=1, views=12000, likes=220, replies=90, reposts=40),
        ]

        decision = pulse.find_pulse(tweets, [], state, handle="polfam", now=NOW)

        self.assertEqual(decision["status"], "no_op")
        self.assertIn("duplicate_recent_angle", decision["best"]["hard_blocks"])


if __name__ == "__main__":
    unittest.main()
