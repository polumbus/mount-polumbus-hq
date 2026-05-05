import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
        self.assertIn("ce.sync_budget_for_mode(\"backfill\")", app_text)
        self.assertIn("ce.budget_preflight_for_mode", app_text)
        self.assertIn("generated_lineage", app_text)
        self.assertIn("Creator Evolution rejected every generated draft", app_text)
        self.assertIn("Creator Evolution blocked this post", app_text)
        self.assertIn("ci_banger_data", app_text)

        ce_runner = app_text.split("def _run_ce_ai", 1)[1].split("def _ce_output_panel_impl", 1)[0]
        self.assertIn("ce.build_generation_prompt", ce_runner)
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
