import re
import unittest
import contextlib
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

import apis
import creator_evolution as ce
import creator_evolution_algorithm as cexa
import creator_evolution_pulse as pulse


NOW = datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)


def _tweet(tweet_id, text, *, hours_ago, views=1000, likes=20, replies=4, reposts=2, quotes=0, bookmarks=0, author=""):
    item = {
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
    if author:
        item["author"] = author
    return item


class CreatorEvolutionTests(unittest.TestCase):
    def test_public_x_draft_report_rewards_clear_nuggets_anchor(self):
        report = cexa.public_x_draft_report(
            "The Nuggets rotation problem keeps surviving every clean explanation because the non Jokic minutes still decide the ceiling.",
            "Normal Tweet",
            "Witty Edge",
        )

        self.assertGreaterEqual(report["candidate_fit"], 60)
        self.assertIn("nuggets", report["candidate_anchor"])
        self.assertEqual(report["target_action"], "reply")

    def test_public_x_draft_report_penalizes_vague_pronoun_opener(self):
        report = cexa.public_x_draft_report(
            "This is where it gets interesting because the whole thing has pressure now.",
            "Normal Tweet",
            "Witty Edge",
        )

        self.assertLess(report["candidate_fit"], 60)
        self.assertGreaterEqual(report["not_dwelled_risk"], 45)

    def test_negative_signal_risk_penalizes_heated_direct_insults(self):
        risk, reason = cexa.negative_signal_risk("The Broncos process is run by idiots.", "Critical")

        self.assertGreaterEqual(risk, 70)
        self.assertIn(reason, {"direct insult language", "heated lane plus personal wording"})

    def test_not_dwelled_risk_penalizes_safe_generic_text(self):
        risk, reason = cexa.not_dwelled_risk("The important part is not the headline. That is where it matters.", "Normal Tweet")

        self.assertGreaterEqual(risk, 70)
        self.assertTrue(reason)

    def test_select_best_option_by_public_x_does_not_default_to_option1(self):
        data = {
            "option1": "This is where it gets interesting because the whole thing has pressure now.",
            "option2": "The Nuggets rotation problem keeps surviving every clean explanation because the non Jokic minutes still decide the ceiling.",
            "option3": "That is a thing now.",
            "pick": "1",
        }
        quality = {f"option{i}": {"ok": True} for i in (1, 2, 3)}

        pick, report = cexa.select_best_option_by_public_x(data, quality, "Normal Tweet", "Witty Edge")

        self.assertEqual(pick, "2")
        self.assertGreaterEqual(report["candidate_fit"], 60)

    def test_prompt_versions_are_public_x_action_profile(self):
        self.assertEqual(ce.PROMPT_VERSION, "ce-prompt-v10-public-x-action-profile")
        self.assertEqual(ce.SCORING_VERSION, "ce-score-v4-public-x-action-profile")

    def test_build_generation_prompt_includes_public_x_contract_and_schema(self):
        prompt = ce.build_generation_prompt("The Nuggets rotation is still the pressure point.", "Normal Tweet", "Witty Edge", None)

        self.assertIn("PUBLIC X ALGORITHM CONTRACT", prompt)
        self.assertIn("option1_candidate_anchor", prompt)
        self.assertIn("option1_target_action", prompt)

    def test_draft_quality_report_includes_public_x_diagnostics(self):
        report = ce.draft_quality_report(
            "The Nuggets rotation problem keeps surviving every clean explanation because the non Jokic minutes still decide the ceiling.",
            "Normal Tweet",
            "Witty Edge",
        )

        self.assertIn("public_x", report)
        self.assertIn("candidate_fit", report)
        self.assertIn("target_action", report)

    def test_score_tweet_includes_algorithm_profile_and_new_score_keys(self):
        score = ce.score_tweet(_tweet(
            101,
            "The Nuggets rotation problem keeps surviving every clean explanation because the non Jokic minutes still decide the ceiling.",
            hours_ago=96,
            views=9000,
            likes=100,
            replies=18,
            reposts=8,
        ), NOW)

        self.assertIn("algorithm_profile", score)
        self.assertIn("candidate_fit", score["scores"])
        self.assertIn("positive_action_fit", score["scores"])
        self.assertIn("actual_action_winner", score["flags"])

    def test_build_format_profiles_include_action_profile_fields(self):
        scores = [
            ce.score_tweet(_tweet(201, "The Nuggets rotation problem keeps deciding the non Jokic minutes.", hours_ago=96, views=9000, likes=120, replies=22, reposts=12), NOW),
            ce.score_tweet(_tweet(202, "The Broncos roster math gets real when camp reps stop protecting the clean public line.", hours_ago=100, views=8000, likes=90, replies=18, reposts=10), NOW),
            ce.score_tweet(_tweet(203, "The Avs goalie decision is where one rough start can reopen the entire crease conversation.", hours_ago=104, views=7000, likes=80, replies=14, reposts=8), NOW),
        ]
        profiles = ce.build_format_profiles(scores)
        profile = next(iter(profiles.values()))

        self.assertIn("winning_target_action_distribution", profile)
        self.assertIn("action_diversity", profile)
        self.assertIn("avg_winner_oon_readability", profile)

    def test_propose_rules_can_produce_action_aware_rules(self):
        scores = [
            ce.score_tweet(_tweet(301, "The Nuggets rotation problem keeps deciding the non Jokic minutes.", hours_ago=96, views=9000, likes=120, replies=22, reposts=12), NOW),
            ce.score_tweet(_tweet(302, "The Broncos roster math gets real when camp reps stop protecting the clean public line.", hours_ago=100, views=8000, likes=90, replies=18, reposts=10), NOW),
            ce.score_tweet(_tweet(303, "The Avs goalie decision is where one rough start can reopen the entire crease conversation.", hours_ago=104, views=7000, likes=80, replies=14, reposts=8), NOW),
        ]
        proposals = ce.propose_rules(scores, now=NOW)

        self.assertTrue(any("target" in proposal["rule"] and "candidate anchor" in proposal["rule"] for proposal in proposals), proposals)

    def test_pulse_score_cluster_includes_public_x_fields(self):
        cluster = {
            "id": "pulse-test",
            "topic": "Nuggets rotation",
            "sources": ["twitter"],
            "signals": [{
                "source": "twitter",
                "text": "The Nuggets rotation problem is back because the non Jokic minutes are deciding the series.",
                "freshness_status": "fresh",
                "age_hours": 0.2,
                "velocity": 15,
                "audience_fit": 9,
                "reply_tension": 8,
                "fact_confidence": 8,
            }],
        }

        report = pulse.score_cluster(cluster, {}, now=NOW)

        self.assertIn("retrieval_fit", report)
        self.assertIn("oon_readability", report)
        self.assertIn("recommended_action_path", report)
        self.assertIn("public_x_read", report)

    def test_pulse_brief_includes_public_x_algorithm_read(self):
        brief = pulse.build_pulse_brief({
            "topic": "Nuggets rotation",
            "recommended_action": "tweet",
            "recommended_lane": "Witty Edge",
            "summary_text": "The Nuggets rotation problem is back.",
            "why_now": "fresh source",
            "score": 80,
            "freshness_score": 90,
            "candidate_anchor": "nuggets",
            "recommended_action_path": "reply",
            "retrieval_fit": 80,
            "oon_readability": 75,
            "negative_signal_risk": 10,
            "not_dwelled_risk": 20,
            "source_basis": [{"source": "twitter", "freshness_status": "fresh", "text": "The Nuggets rotation problem is back."}],
        }, {})

        self.assertIn("PUBLIC X ALGORITHM READ", brief)
        self.assertIn("Candidate anchor", brief)

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


    def test_voice_tuner_test_prompts_rotate_and_match_lane_style(self):
        comedic = ce.voice_tuner_test_prompt("Comedic", "Normal Tweet", 0)
        sarcastic = ce.voice_tuner_test_prompt("Sarcastic", "Normal Tweet", 0)
        skeptical = ce.voice_tuner_test_prompt("Skeptical", "Normal Tweet", 0)
        next_comedic = ce.voice_tuner_test_prompt("Comedic", "Normal Tweet", 1)

        self.assertIn("group project", comedic)
        self.assertIn("which is always comforting", sarcastic)
        self.assertIn("but camp is where we find out", skeptical)
        self.assertNotEqual(comedic, next_comedic)
        self.assertIn("one or two sentences", ce.voice_tuner_test_prompt("Comedic", "Punchy Tweet", 0))

    def test_source_preservation_relaxes_for_transformational_lanes(self):
        standard = ce.build_generation_prompt(
            "The Broncos keep saying this roster is deeper, but camp will show if that is real.",
            "Normal Tweet",
            "Witty Edge",
            None,
        )
        comedic = ce.build_generation_prompt(
            "The Nuggets say everything is on the table, but the non-Jokic minutes keep wrecking games.",
            "Normal Tweet",
            "Comedic",
            None,
        )
        critical = ce.build_generation_prompt(
            "Sean Payton keeps saying competition matters, but camp will show who actually responds.",
            "Normal Tweet",
            "Critical",
            None,
        )
        sarcastic = ce.build_generation_prompt(
            "The Broncos say every job is open, which sounds comfortable for veterans.",
            "Normal Tweet",
            "Sarcastic",
            None,
        )

        self.assertIn("line-break skeleton", standard)
        self.assertIn("EDGY GROUP-CHAT SPORTS COMEDY", comedic)
        self.assertIn("Clear diagnosis with accountability", critical)
        self.assertIn("SARCASTIC VOICE", sarcastic)
        self.assertIn("Source freedom for this lane", comedic)

    def test_comedic_quality_rejects_wasted_setup_frames(self):
        for phrase in ("The funny part is", "The whole thing is", "You can always tell"):
            report = ce.draft_quality_report(
                f"{phrase} the Nuggets rotation problem gets explained like the bench did not just move the furniture again.",
                "Normal Tweet",
                "Comedic",
            )
            self.assertFalse(report["ok"])
            self.assertTrue(
                any("meme-caption energy" in issue for issue in report["issues"]),
                report["issues"],
            )

    def test_score_records_do_not_count_as_polished_hyphens(self):
        report = ce.draft_quality_report(
            "The Broncos can go 4-4 early and 7-2 late. That is how 11 or 12 wins gets on the table.",
            "Normal Tweet",
            "Witty Edge",
        )

        self.assertNotIn("hyphen/dash", report["polished_punctuation_hits"])

    def test_app_lane_fallback_preserves_broncos_schedule_math_without_metadata(self):
        with contextlib.redirect_stderr(io.StringIO()):
            import app

        source = (
            "The 2026 Broncos formula...\n"
            "Survive the first 8 games - Thrive in the next 9 games\n\n"
            "If Broncos can go 4-4 to start the season it is very realistic to go 7-2 in the back half. "
            "#1 Seed will be extremely difficult this year but an 11-12 win season is very much on the table."
        )
        data, _quality, passing = app._ce_force_safe_lane_fallback(source, "Normal Tweet", "Witty Edge")

        self.assertEqual(["1", "2", "3"], passing)
        for idx in (1, 2, 3):
            text = data[f"option{idx}"]
            self.assertIn("4-4", text)
            self.assertIn("7-2", text)
            self.assertTrue("11" in text or "12" in text or "1 seed" in text.lower())
            self.assertNotIn("Witty Edge fallback", text)
            self.assertNotIn("Normal Tweet usually works best", text)
            self.assertNotIn("Watch  Normal Tweet", text)
        self.assertTrue(all((_quality[f"option{idx}"].get("score", 0) <= 82) for idx in (1, 2, 3)))
        self.assertTrue(all(_quality[f"option{idx}"].get("fallback_repaired") for idx in (1, 2, 3)))

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
        self.assertIn('"PROMPT_VERSION": getattr(ce, "PROMPT_VERSION", "ce-prompt-v10-public-x-action-profile")', app_text)
        self.assertIn('"Creator Evolution"', app_text)
        self.assertIn("page_creator_evolution", app_text)
        self.assertIn('CE_AI_PROVIDER_DEFAULT = "Grok"', app_text)
        self.assertIn("creator_evolution_direct_xai", app_text)
        self.assertIn("creator_evolution_direct_openai", app_text)
        self.assertIn("direct xAI key missing", app_text)
        self.assertIn("Direct ChatGPT/OpenAI only", app_text)
        self.assertIn("proxy disabled", app_text)
        self.assertIn("Proxy fallback is disabled", app_text)
        ce_provider_body = app_text[
            app_text.index("def _call_creator_evolution_ai_for_provider") :
            app_text.index("def _call_creator_evolution_ai(", app_text.index("def _call_creator_evolution_ai_for_provider"))
        ]
        self.assertNotIn("_call_grok_proxy(prompt", ce_provider_body)
        self.assertNotIn("raw = call_claude(", ce_provider_body)
        self.assertNotIn("creator_evolution_proxy", ce_provider_body)
        self.assertIn('"Voice Tuner"', app_text)
        self.assertIn("page_voice_tuner", app_text)
        self.assertIn("page_testing", app_text)
        self.assertIn("CE_TESTING_STATE_FILENAME", app_text)
        self.assertIn("CREATOR EVOLUTION OPTION B SANDBOX OVERRIDES", app_text)
        self.assertIn("### Target", app_text)
        self.assertIn('"Tune"', app_text)
        self.assertIn('"Voice"', app_text)
        self.assertIn('"Format"', app_text)
        self.assertIn("New idea", app_text)
        self.assertIn("Voice only", app_text)
        self.assertIn("Format only", app_text)
        self.assertIn("Voice + format", app_text)
        self.assertIn("Generate Preview", app_text)
        self.assertIn("Preview", app_text)
        self.assertIn("Feedback", app_text)
        self.assertIn("Apply", app_text)
        self.assertIn("Current voice", app_text)
        self.assertIn("Tuned voice", app_text)
        self.assertIn("Advanced", app_text)
        self.assertIn("Save Feedback And Regenerate", app_text)
        self.assertIn("def _ce_voice_tuner_chip_feedback_text", app_text)
        self.assertIn('state["active_generation_key"] = gen_key', app_text)
        self.assertIn('state.get("active_generation_key") == gen_key', app_text)
        self.assertIn("def _ce_selected_tuning_rules", app_text)
        self.assertIn("def _ce_testing_generate_pair", app_text)
        self.assertIn("ThreadPoolExecutor(max_workers=2)", app_text)
        self.assertIn("_ce_testing_generate_pair(item, provider, state)", app_text)
        self.assertIn("_ce_testing_overlay_text(lab_state, lane, fmt, concept_id=concept_id)", app_text)
        self.assertIn("_ce_voice_learning_text(state, lane)", app_text)
        self.assertNotIn("CE_MONETIZATION_OPTIMIZED_AB_RULES =", app_text)
        self.assertIn("elif str(item).strip() and not selected_lane", app_text)
        self.assertIn('st.session_state["_ce_testing_state_cache"]', app_text)
        self.assertIn('if report.get("ok"):', app_text)
        self.assertIn("disabled=not live_entries or not confirm_live", app_text)
        self.assertIn("prompt_preferences", app_text)
        self.assertNotIn('"ok": True,\n            "issues": [],\n            "warnings": [],', app_text)
        self.assertNotIn("Generate ChatGPT vs Grok", app_text)
        self.assertIn("_ce_build_dialog", app_text)
        self.assertIn("_ce_show_build_dialog", app_text)
        self.assertIn("_ce_inspiration_dialog", app_text)
        self.assertIn("_ce_show_inspiration", app_text)
        self.assertIn("_ce_pulse_dialog", app_text)
        self.assertIn("_ce_show_pulse", app_text)
        self.assertIn("ce_pulse", app_text)
        self.assertIn("ce_whats_hot", app_text)
        self.assertIn("CE_AI_PROVIDER_OPTIONS", app_text)
        self.assertIn('"Grok"', app_text)
        self.assertIn("def _call_grok_api_key", app_text)
        self.assertIn("XAI_API_KEY", app_text)
        self.assertIn("creator_evolution_direct_xai", app_text)
        self.assertIn("creator_evolution_direct_chatgpt_oauth", app_text)
        self.assertIn("CE_COMPAT_DEFAULTS", app_text)
        self.assertIn("ce_banger_data", app_text)
        self.assertIn("ce_quality_report", app_text)
        self.assertIn("_ce_sync_budget_for_mode(\"backfill\")", app_text)
        self.assertIn("_ce_budget_preflight_for_mode", app_text)
        self.assertIn("generated_lineage", app_text)
        self.assertIn("Creator Evolution rejected every generated draft", app_text)
        self.assertNotIn("Creator Evolution blocked this post", app_text)
        self.assertIn("X_OAUTH2_AUTHORIZE_URL", app_text)
        self.assertIn("https://x.com/i/oauth2/authorize", app_text)
        self.assertIn("X_OAUTH2_TOKEN_URL", app_text)
        self.assertIn("https://api.x.com/2/oauth2/token", app_text)
        self.assertIn("tweet.write tweet.read users.read offline.access", app_text)
        self.assertIn("code_challenge_method", app_text)
        self.assertIn("S256", app_text)
        self.assertIn("X_OAUTH_TOKEN_KEY", app_text)
        self.assertIn("_post_tweet_native_x_oauth2(clean_text)", app_text)
        self.assertIn("_post_tweet_native_x_oauth1(clean_text)", app_text)
        self.assertIn("official native X auth only", app_text)
        self.assertIn("Legacy helper/proxy posting is disabled", app_text)
        self.assertLess(
            app_text.index("_post_tweet_native_x_oauth2(clean_text)"),
            app_text.index("_post_tweet_native_x_oauth1(clean_text)"),
        )
        post_body = app_text[app_text.index("def _post_tweet(text: str)") : app_text.index("def _xurl_helper_app_name", app_text.index("def _post_tweet(text: str)"))]
        self.assertNotIn("_post_tweet_xurl_helper(clean_text)", post_body)
        self.assertNotIn("/tweet/post", post_body)
        self.assertIn("Connect X Securely", app_text)
        self.assertIn("Connected OAuth token", app_text)
        self.assertIn("Creator Evolution note only. Posting anyway because you control what goes to X.", app_text)
        self.assertIn('clean_text = (text or "").strip()', app_text)
        self.assertNotIn('clean_text = (text or "").strip()[:280]', app_text)
        self.assertIn("Why direct posting failed", app_text)
        self.assertIn("Open x.com in Chrome while logged in", app_text)
        proxy_text = Path("claude_proxy.py").read_text()
        background_text = Path("extension/background.js").read_text()
        popup_text = Path("extension/popup.html").read_text() + Path("extension/popup.js").read_text()
        manifest_text = Path("extension/manifest.json").read_text()
        self.assertIn("HQ_EXTENSION_PROXY_KEY", proxy_text)
        self.assertIn("polumbus_hq_proxy_2026", proxy_text)
        self.assertIn("twitter_cookie_status", proxy_text)
        self.assertIn("sync-cookies-now", background_text)
        self.assertIn("chrome.tabs.onUpdated", background_text)
        self.assertIn("periodInMinutes: 5", background_text)
        self.assertIn("Sync X Login", popup_text)
        self.assertIn('"tabs"', manifest_text)
        self.assertIn("ci_banger_data", app_text)
        self.assertIn('return "Creator Evolution" if is_owner() else "Creator Studio"', app_text)
        self.assertIn("st.session_state.current_page = _default_landing_page()", app_text)

        ce_runner = app_text.split("def _run_ce_ai", 1)[1].split("def _ce_output_panel_impl", 1)[0]
        self.assertIn("_ce_build_generation_prompt", ce_runner)

    def test_voice_tuner_generates_voice_and_format_specific_test_prompts(self):
        for lane in ce.EMOTION_LANES:
            normal = ce.voice_tuner_test_prompt(lane, "Normal Tweet", 0)
            punchy = ce.voice_tuner_test_prompt(lane, "Punchy Tweet", 1)
            thread = ce.voice_tuner_test_prompt(lane, "Thread", 2)

            self.assertGreater(len(normal), 60, lane)
            self.assertIn("Keep it tight", punchy)
            self.assertIn("short thread", thread)
            self.assertNotIn("write a tweet about", normal.lower())
            self.assertNotIn("make this funny", normal.lower())

        self.assertIn("one qb decision", ce.voice_tuner_test_prompt("Promo", "Long Tweet", 0).lower())
        self.assertIn("group project", ce.voice_tuner_test_prompt("Comedic", "Normal Tweet", 0).lower())
        self.assertIn("quietly submitting evidence", ce.voice_tuner_test_prompt("Deadpan", "Normal Tweet", 0).lower())

    def test_voice_tuner_guided_feedback_builds_plain_english_note(self):
        app_text = Path("app.py").read_text()
        namespace = {}
        helper_source = app_text.split("def _ce_guided_feedback_text", 1)[1].split("def _render_ce_testing_output_card", 1)[0]
        exec("def _ce_guided_feedback_text" + helper_source, namespace)
        text = namespace["_ce_guided_feedback_text"](
            "Promo",
            "Too much setup",
            "compressed",
            "use an open loop",
            "Keep the YouTube reason to watch.",
        )

        self.assertIn("For Promo, tune Option B", text)
        self.assertIn("too much setup", text)
        self.assertIn("make it compressed", text)
        self.assertIn("use an open loop", text)
        self.assertIn("Keep the YouTube reason to watch.", text)

        app_text = Path("app.py").read_text()
        ce_runner = app_text.split("def _run_ce_ai", 1)[1].split("def _ce_output_panel_impl", 1)[0]
        ce_ai = app_text.split("def _call_creator_evolution_ai", 1)[1].split("def _run_ce_ai", 1)[0]
        self.assertIn("_ce_selected_ai_provider", ce_ai)
        self.assertIn("_call_grok_api_key", ce_ai)
        self.assertIn("_call_openai_api_key", ce_ai)
        self.assertIn("call_chatgpt_oauth", ce_ai)
        self.assertNotIn("raw = call_claude(", ce_ai)
        self.assertIn('st.session_state["_ai_last_route"] = "grok_api_key"', ce_ai)
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

    def test_voice_learning_is_lane_scoped_calibration(self):
        state = ce.initial_state()
        state["patterns"]["voice_profile"] = {
            "status": "mature",
            "sample_size": 12,
            "confidence_active": True,
            "traits": ["short final line"],
            "avoid_traits": ["generic opener"],
        }

        text = ce.voice_learning_text(state, "Promo")

        self.assertIn("selected lane (Promo)", text)
        self.assertIn("selected lane behavior remains the source of truth", text)

    def test_creator_evolution_build_dialog_uses_form_and_persistent_result_panel(self):
        app_text = Path("app.py").read_text()
        build_dialog = app_text.split("def _ce_build_dialog", 1)[1].split("def _ce_output_panel_impl", 1)[0]

        self.assertIn('st.form("ce_build_form"', build_dialog)
        self.assertIn("st.form_submit_button", build_dialog)
        self.assertIn('st.session_state["_ce_build_result_ready"] = True', build_dialog)
        self.assertIn('if st.session_state.get("_ce_build_result_ready"):', build_dialog)
        result_panel = build_dialog.split('if st.session_state.get("_ce_build_result_ready"):', 1)[1]
        self.assertIn('st.session_state.get("ce_banger_data")', result_panel)
        self.assertIn("Your Options", result_panel)

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
        self.assertIn("AGGRESSIVE DRY HUMOR MODE", prompt)
        self.assertIn("No exclamation points", prompt)

    def test_format_recipe_changes_prompt_behavior(self):
        base = "Broncos fans are trying to decide if the boring roster answer is the actual tell"
        cases = {
            "Punchy Tweet": "One sharp, complete reaction",
            "Normal Tweet": "Preferred shape is two or three natural sentences",
            "Long Tweet": "261-700 preferred characters",
            "Thread": "---TWEET---",
            "Article": "700-1,200 words",
        }

        for fmt, expected in cases.items():
            with self.subTest(fmt=fmt):
                prompt = ce.build_generation_prompt(base, fmt, "Witty Edge", ce.initial_state())
                self.assertIn("FORMAT BEHAVIOR:", prompt)
                self.assertIn(expected, prompt)

    def test_format_quality_gate_enforces_selected_length_and_structure(self):
        self.assertFalse(ce.draft_quality_report("This normal tweet is too short.", "Normal Tweet", "Witty Edge")["ok"])
        self.assertFalse(ce.draft_quality_report("This is short.", "Long Tweet", "Witty Edge")["ok"])
        self.assertFalse(ce.draft_quality_report("Tweet one\nTweet two\nTweet three", "Thread", "Witty Edge")["ok"])
        self.assertFalse(ce.draft_quality_report("Headline\n\nShort article body.", "Article", "Witty Edge")["ok"])
        valid_normal = (
            "The Broncos keep saying the roster is close. That sounds good until the next few depth chart decisions show whether they actually believe it.\n\n"
            "The protection tells the story..."
        )
        valid_one_paragraph_normal = "The Broncos keep saying the roster is close. The next few depth chart decisions will tell us if they actually believe it, because cautious teams always leave fingerprints..."
        invalid_normal = "The Broncos keep saying the roster is close.\n\nThe next few depth chart decisions will tell us if they actually believe it.\n\nThe protection tells the story..."
        self.assertTrue(ce.draft_quality_report(valid_normal, "Normal Tweet", "Witty Edge")["ok"])
        self.assertTrue(ce.draft_quality_report(valid_one_paragraph_normal, "Normal Tweet", "Witty Edge")["ok"])
        self.assertFalse(ce.draft_quality_report(invalid_normal, "Normal Tweet", "Witty Edge")["ok"])

        punchy_too_long = "The Broncos offense keeps explaining itself like the answer is hiding in a footnote, and somehow every offseason turns into the same group project with worse handwriting."
        self.assertFalse(ce.draft_quality_report(punchy_too_long, "Punchy Tweet", "Witty Edge")["ok"])

        thread = "---TWEET---".join([
            "The Broncos keep telling us the boring roster answer might be the plan.",
            "That is not automatically bad. It is just less fun than the version everyone wants.",
            "The real tell is whether Payton is building around stability or hiding from risk.",
            "That is where this offseason gets uncomfortable.",
        ])
        self.assertTrue(ce.draft_quality_report(thread, "Thread", "Witty Edge")["ok"])

    def test_generated_text_repair_fixes_normal_tweet_blank_lines_before_gates(self):
        raw = (
            "The Broncos keep saying this roster is deeper than last year.\n\n\n"
            "Training camp is where that stops being a slogan and starts turning into real decisions about who actually belongs.\n\n\n"
            "The depth chart gets honest fast..."
        )
        repaired = ce.repair_generated_text_for_format(raw, "Normal Tweet", "Witty Edge")
        self.assertLessEqual(len(re.findall(r"\n\s*\n", repaired)), 1)
        self.assertNotIn("multiple blank-line", " ".join(ce.draft_quality_report(repaired, "Normal Tweet", "Witty Edge")["issues"]))

    def test_generated_text_repair_fixes_punchy_line_breaks_before_gates(self):
        raw = "Payton is not handing out comfort reps anymore.\nCamp just got a lot less ceremonial."
        repaired = ce.repair_generated_text_for_format(raw, "Punchy Tweet", "Witty Edge")
        self.assertNotIn("\n", repaired)
        self.assertNotIn("  ", repaired)

    def test_option_set_structure_repetition_warns_without_blocking_all_drafts(self):
        data = {
            "option1": "The Broncos keep saying the roster is deeper than last year. Camp is where that stops being theory and starts deciding which safe names actually survive.\n\nThe cut line will tell on them...",
            "option2": "The Avs keep saying the crease is settled for this run. The next tough start is where that stops being a talking point and starts changing the room.\n\nThe bench will answer fast...",
            "option3": "The Nuggets keep saying everything is on the table this summer. Those bench minutes are still the pressure point that turns every plan into damage control.\n\nThat is where summer gets honest...",
        }
        report = ce.validate_generation_options(data, "Normal Tweet", "Witty Edge")
        self.assertTrue(all(item["ok"] for item in report.values()))
        self.assertTrue(any("line-break skeleton" in " ".join(item["warnings"]) for item in report.values()))

    def test_format_evolution_learns_profiles_from_mature_tweets(self):
        tweets = [
            _tweet(20, "The Broncos keep acting like the boring roster answer is a side quest, but every real signal keeps pointing back to the same uncomfortable plan. That is usually where this league tells on itself...", hours_ago=90, views=14000, likes=320, replies=80, reposts=45),
            _tweet(21, "Nuggets bench discourse is funny because everyone wants a clean answer, and the actual answer keeps looking like another weird compromise. Very normal way to spend a title window...", hours_ago=96, views=12000, likes=260, replies=72, reposts=36),
            _tweet(22, "The Buffs argument always turns into Coach Prime theater, but the development conversation is sitting right there making people uncomfortable. Almost like both things can be true...", hours_ago=110, views=16000, likes=350, replies=95, reposts=50),
        ]

        state = ce.refresh_state(None, tweets, handle="polfam", now=NOW)
        profile = state["patterns"]["format_profiles"]["Normal Tweet"]
        prompt = ce.build_generation_prompt(
            "Broncos fans are trying to decide whether boring is actually the plan",
            "Normal Tweet",
            "Witty Edge",
            state,
        )

        self.assertEqual(profile["sample_size"], 3)
        self.assertEqual(profile["status"], "mature")
        self.assertEqual(len(profile["winner_ids"]), 2)
        self.assertEqual(len(profile["loser_ids"]), 2)
        self.assertNotEqual(profile["winner_ids"], profile["loser_ids"])
        self.assertTrue(profile["traits"])
        self.assertIn("LEARNED FORMAT PROFILE:", prompt)
        self.assertIn("Normal Tweet learned profile", prompt)
        self.assertIn("Winning trait:", prompt)
        self.assertEqual(profile["examples"], [])

    def test_voice_evolution_learns_profile_from_mature_tweets(self):
        tweets = [
            _tweet(120, "The Broncos plan looks boring until the roster math starts telling on it. That is where the offseason gets uncomfortable...", hours_ago=90, views=15000, likes=320, replies=80, reposts=46),
            _tweet(121, "Nuggets fans want a clean bench answer, which is adorable because this team keeps choosing stress as a roster philosophy...", hours_ago=96, views=14000, likes=300, replies=78, reposts=42),
            _tweet(122, "The Avs usage conversation is weird because the simple answer keeps hiding behind the same uncomfortable lineup question...", hours_ago=100, views=13000, likes=280, replies=70, reposts=39),
            _tweet(123, "This Broncos offseason keeps coming back to the same pressure point. The fun answer and the real answer might not be friends...", hours_ago=104, views=16000, likes=340, replies=88, reposts=50),
            _tweet(124, "The Nuggets window is still alive because Jokic is Jokic. The uncomfortable part is everything that has to be true around him...", hours_ago=108, views=17000, likes=360, replies=92, reposts=55),
            _tweet(125, "CU discourse is funny because everyone wants one clean villain and the actual player development story refuses to cooperate...", hours_ago=112, views=15500, likes=330, replies=86, reposts=48),
            _tweet(126, "The Broncos keep selling patience like it is a plan. Eventually the roster has to say the quiet part out loud...", hours_ago=116, views=14500, likes=310, replies=82, reposts=44),
            _tweet(127, "The Nuggets can explain the injuries all day. The real pressure is what the next move says about how they see the window...", hours_ago=120, views=16500, likes=350, replies=90, reposts=52),
        ]

        state = ce.refresh_state(None, tweets, handle="polfam", now=NOW)
        profile = state["patterns"]["voice_profile"]
        prompt = ce.build_generation_prompt(
            "Broncos fans are arguing about whether the boring roster answer is the tell",
            "Normal Tweet",
            "Witty Edge",
            state,
        )

        self.assertEqual(profile["status"], "mature")
        self.assertEqual(profile["sample_size"], 8)
        self.assertTrue(profile["traits"])
        self.assertIn("common_opening_style", profile)
        self.assertIn("LEARNED VOICE PROFILE:", prompt)
        self.assertIn("Winning voice trait:", prompt)
        self.assertIn("Use this as influence, not a hook library", prompt)
        self.assertTrue(any("Creator Evolution voice" in prop["rule"] for prop in state["proposals"]))
        self.assertNotIn(tweets[0]["text"][:80], prompt)
        self.assertEqual(profile["examples"], [])

    def test_provisional_profiles_do_not_influence_generation_prompt(self):
        tweets = [
            _tweet(130, "The Broncos roster plan is getting weird enough that everyone wants to skip the uncomfortable part...", hours_ago=3, views=9000, likes=180, replies=40, reposts=20),
            _tweet(131, "The Nuggets bench answer is still hiding inside the same pressure point...", hours_ago=4, views=8000, likes=160, replies=35, reposts=18),
        ]

        state = ce.refresh_state(None, tweets, handle="polfam", now=NOW)
        prompt = ce.build_generation_prompt(
            "Broncos fans are arguing about the roster plan",
            "Normal Tweet",
            "Witty Edge",
            state,
        )

        self.assertEqual(state["patterns"]["mature_count"], 0)
        self.assertIn("No mature learned profile for this selected format yet", prompt)
        self.assertIn("No mature learned voice profile yet", prompt)
        self.assertNotIn("Winning examples:", prompt)
        self.assertNotIn("Winning voice trait:", prompt)
        self.assertNotIn("CURRENT WINNING PERFORMANCE PATTERNS:", prompt)
        self.assertFalse(any("Creator Evolution voice" in prop["rule"] for prop in state["proposals"]))

    def test_tiny_mature_samples_do_not_influence_generation_prompt(self):
        tweets = [
            _tweet(132, "The Broncos roster plan is getting weird enough that everyone wants to skip the uncomfortable part...", hours_ago=90, views=9000, likes=180, replies=40, reposts=20),
            _tweet(133, "The Nuggets bench answer is still hiding inside the same pressure point...", hours_ago=96, views=8000, likes=160, replies=35, reposts=18),
            _tweet(134, "Fresh Broncos thought with huge early numbers should not teach the model yet...", hours_ago=2, views=90000, likes=900, replies=300, reposts=150),
        ]

        state = ce.refresh_state(None, tweets, handle="polfam", now=NOW)
        prompt = ce.build_generation_prompt(
            "Broncos fans are arguing about the roster plan",
            "Punchy Tweet",
            "Witty Edge",
            state,
        )

        self.assertEqual(state["patterns"]["mature_count"], 2)
        self.assertIn("No mature learned profile for this selected format yet", prompt)
        self.assertIn("No mature learned voice profile yet", prompt)
        self.assertNotIn("Fresh Broncos thought with huge early numbers", prompt)
        self.assertNotIn("CURRENT WINNING PERFORMANCE PATTERNS:", prompt)

    def test_seven_mature_voice_samples_do_not_create_voice_rule_or_prompt_profile(self):
        tweets = [
            _tweet(150 + i, f"The Broncos roster plan keeps hiding the uncomfortable part in plain sight number {i}...", hours_ago=90 + i, views=9000 + i, likes=180, replies=40, reposts=20)
            for i in range(7)
        ]

        state = ce.refresh_state(None, tweets, handle="polfam", now=NOW)
        prompt = ce.build_generation_prompt("Broncos roster plan", "Punchy Tweet", "Witty Edge", state)

        self.assertEqual(state["patterns"]["voice_profile"]["sample_size"], 7)
        self.assertIn("No mature learned voice profile yet", prompt)
        self.assertFalse(any("Creator Evolution voice" in prop["rule"] for prop in state["proposals"]))

    def test_mixed_mature_and_fresh_uses_mature_only_for_profiles(self):
        mature_tweets = [
            _tweet(170, "The Broncos plan looks boring until the roster math starts telling on it...", hours_ago=90, views=15000, likes=320, replies=80, reposts=46),
            _tweet(171, "Nuggets fans want a clean bench answer because the window math keeps getting uncomfortable...", hours_ago=96, views=14000, likes=300, replies=78, reposts=42),
            _tweet(172, "The Avs usage conversation keeps hiding behind the same uncomfortable lineup question...", hours_ago=100, views=13000, likes=280, replies=70, reposts=39),
        ]
        fresh_tweet = _tweet(173, "Fresh viral sentence that should not become a learned profile trait yet.", hours_ago=1, views=999999, likes=9999, replies=999, reposts=999)

        state = ce.refresh_state(None, mature_tweets + [fresh_tweet], handle="polfam", now=NOW)
        prompt = ce.build_generation_prompt("Broncos roster plan", "Punchy Tweet", "Witty Edge", state)

        self.assertEqual(state["patterns"]["mature_count"], 3)
        self.assertNotIn("Fresh viral sentence", prompt)
        self.assertNotIn("Fresh viral sentence", " ".join(state["patterns"]["best_current_patterns"]))
        self.assertNotIn(fresh_tweet["id"], state["patterns"]["format_profiles"]["Punchy Tweet"]["winner_ids"])
        self.assertEqual(state["patterns"]["voice_profile"]["examples"], [])

    def test_format_examples_are_marked_calibration_only(self):
        tweets = [
            _tweet(140, "The Broncos plan looks boring until the roster math starts telling on it. That is where the offseason gets uncomfortable...", hours_ago=90, views=15000, likes=320, replies=80, reposts=46),
            _tweet(141, "Nuggets fans want a clean bench answer, which is adorable because this team keeps choosing stress as a roster philosophy...", hours_ago=96, views=14000, likes=300, replies=78, reposts=42),
            _tweet(142, "The Avs usage conversation is weird because the simple answer keeps hiding behind the same uncomfortable lineup question...", hours_ago=100, views=13000, likes=280, replies=70, reposts=39),
        ]

        state = ce.refresh_state(None, tweets, handle="polfam", now=NOW)
        text = ce.format_learning_text(state, "Punchy Tweet")

        self.assertIn("Calibration is abstract only", text)
        self.assertIn("raw winner text is intentionally withheld", text)
        self.assertNotIn(tweets[0]["text"][:80], text)
        self.assertEqual(state["patterns"]["format_profiles"]["Punchy Tweet"]["examples"], [])

    def test_pattern_summaries_do_not_store_raw_tweet_text(self):
        unique = "UNIQUE_RAW_COPY_RISK_SENTENCE"
        state = ce.refresh_state(None, [
            _tweet(145, f"{unique} Broncos roster pressure keeps hiding in plain sight...", hours_ago=90, views=16000, likes=320, replies=80, reposts=46),
            _tweet(146, "Nuggets window math keeps getting uncomfortable in the same exact spot...", hours_ago=96, views=15000, likes=300, replies=78, reposts=42),
            _tweet(147, "The Avs lineup question keeps refusing to become a clean answer...", hours_ago=100, views=14000, likes=280, replies=70, reposts=39),
        ], handle="polfam", now=NOW)
        joined_patterns = "\n".join(state["patterns"]["best_current_patterns"] + state["patterns"]["worst_current_patterns"])
        prompt = ce.build_generation_prompt("Broncos roster pressure", "Punchy Tweet", "Witty Edge", state)

        self.assertNotIn(unique, joined_patterns)
        self.assertNotIn(unique, prompt)

    def test_malformed_legacy_profiles_fail_closed_without_leaking_examples(self):
        state = ce.initial_state()
        state["patterns"] = {
            "mature_count": "bad",
            "format_profiles": {
                "Punchy Tweet": {
                    "status": "mature",
                    "sample_size": "bad",
                    "traits": ["safe abstract trait"],
                    "examples": ["RAW_FORMAT_LEAK"],
                }
            },
            "voice_profile": {
                "status": "mature",
                "sample_size": "bad",
                "traits": ["safe voice trait"],
                "examples": ["RAW_VOICE_LEAK"],
            },
            "best_current_patterns": ["RAW_PATTERN_LEAK"],
            "worst_current_patterns": ["RAW_PATTERN_LEAK"],
        }

        prompt = ce.build_generation_prompt("Broncos roster pressure", "Punchy Tweet", "Witty Edge", state)

        self.assertIn("No mature learned profile for this selected format yet", prompt)
        self.assertIn("No mature learned voice profile yet", prompt)
        self.assertNotIn("RAW_FORMAT_LEAK", prompt)
        self.assertNotIn("RAW_VOICE_LEAK", prompt)
        self.assertNotIn("RAW_PATTERN_LEAK", prompt)

    def test_legacy_missing_voice_profile_is_safe(self):
        state = ce.initial_state()
        state["patterns"] = {"format_profiles": {}}

        prompt = ce.build_generation_prompt(
            "Broncos fans are trying to read the next roster move",
            "Normal Tweet",
            "Witty Edge",
            state,
        )

        self.assertIn("No mature learned voice profile yet", prompt)
        self.assertNotIn("Traceback", prompt)

    def test_app_creator_evolution_long_tweet_gate_matches_core_range(self):
        app_text = Path("app.py").read_text()
        app_gate = app_text.split("def _ce_format_quality_findings", 1)[1].split("def _ce_draft_quality_report", 1)[0]

        self.assertIn("if char_count < 260:", app_gate)
        self.assertIn("if char_count > 900:", app_gate)
        self.assertNotIn("if char_count < 360:", app_gate)
        self.assertNotIn("if char_count > 1300:", app_gate)

    def test_app_generation_validator_merges_stale_helper_with_local_gate(self):
        app_text = Path("app.py").read_text()
        validator = app_text.split("def _ce_validate_generation_options", 1)[1].split("def _ce_pulse_meta_language", 1)[0]

        self.assertIn("local_report = _ce_draft_quality_report", validator)
        self.assertIn('merged["ok"] = bool(helper_report.get("ok", True)) and bool(local_report.get("ok"))', validator)
        self.assertNotIn("return report\n", validator)

    def test_app_draft_quality_report_rechecks_lane_gates_after_helper_report(self):
        app_text = Path("app.py").read_text()
        wasted_space_source = (
            "CE_WASTED_SPACE_FRAMES"
            + app_text.split("CE_WASTED_SPACE_FRAMES", 1)[1].split("def _ce_prepare_generated_option", 1)[0]
        )
        source = (
            wasted_space_source
            + "\ndef _ce_format_quality_findings"
            + app_text.split("def _ce_format_quality_findings", 1)[1].split("def _ce_validate_generation_options", 1)[0]
        )

        class StaleCe:
            RISK_TERMS = ("loser", "trash")

            @staticmethod
            def draft_quality_report(text, fmt, lane):
                return {
                    "ok": True,
                    "score": 100,
                    "issues": [],
                    "warnings": [],
                    "ai_sounding_hits": [],
                    "risk_hits": [],
                    "engagement_bait_hits": [],
                    "cadence_hits": [],
                    "char_count": len(text),
                }

        namespace = {
            "re": re,
            "ce": StaleCe(),
            "_ce_pulse_meta_language": lambda clean: False,
            "_ce_text_has_betting_angle": lambda clean: False,
            "_ce_prompt_version": lambda: "test",
            "_ce_pulse_debug_event": lambda *args, **kwargs: None,
            "_normalize_tweet_format": lambda fmt: fmt,
        }
        exec(source, namespace)

        report = namespace["_ce_draft_quality_report"](
            "Turns out that guy is a total loser.",
            "Punchy Tweet",
            "Sarcastic",
        )

        self.assertFalse(report["ok"])
        self.assertLess(report["score"], 100)
        self.assertTrue(any("cannot copy old example frames" in issue for issue in report["issues"]))
        self.assertTrue(any("without direct insults" in issue for issue in report["issues"]))

    def test_long_tweet_core_boundary_documents_preferred_vs_hard_bounds(self):
        at_260 = "Broncos " + ("x" * 252)
        at_900 = "Broncos " + ("x" * 892)
        self.assertFalse(ce.draft_quality_report("x" * 259, "Long Tweet", "Witty Edge")["ok"])
        self.assertTrue(ce.draft_quality_report(at_260, "Long Tweet", "Witty Edge")["ok"])
        self.assertTrue(ce.draft_quality_report(at_900, "Long Tweet", "Witty Edge")["ok"])
        self.assertFalse(ce.draft_quality_report("x" * 901, "Long Tweet", "Witty Edge")["ok"])

    def test_lane_specific_quality_gates_block_drift(self):
        sarcastic = ce.draft_quality_report("Turns out that guy is a total loser.", "Punchy Tweet", "Sarcastic")
        amused = ce.draft_quality_report("This lineup is so unserious lol 😂", "Punchy Tweet", "Comedic")
        skeptical = ce.draft_quality_report("Obviously this is guaranteed to fail. Book it.", "Punchy Tweet", "Skeptical")
        random_comedy = ce.draft_quality_report("The Nuggets bench turned into a group project with HR paperwork.", "Punchy Tweet", "Comedic")
        angry_comedy = ce.draft_quality_report("The public line was cute. That is where the bullshit ends.", "Punchy Tweet", "Comedic")
        analysis_comedy = ce.draft_quality_report("Bo Nix looks fine now. The real tell is when backup reps tell the truth.", "Punchy Tweet", "Comedic")
        fake_deep_comedy = ce.draft_quality_report("The Nuggets keep saying everything is on the table. Otherwise this is just a press conference with vibes.", "Punchy Tweet", "Comedic")
        nonsense_comedy = ce.draft_quality_report("Bo Nix is on track, sure. If a random camp arm appears by lunch, we all heard the same ankle.", "Punchy Tweet", "Comedic")
        label_comedy = ce.draft_quality_report("The Broncos added a quarterback after saying Bo is fine. Football fluency.", "Punchy Tweet", "Comedic")
        cute_comedy = ce.draft_quality_report("The Broncos keep saying Bo is fine. Funny how that works.", "Punchy Tweet", "Comedic")
        creepy_comedy = ce.draft_quality_report("Broncos treating Bo Nix like the side piece just in case he ghosts them.", "Punchy Tweet", "Comedic")
        truth_comedy = ce.draft_quality_report("The Broncos added a quarterback after saying Bo is fine. That transaction will tell the truth.", "Punchy Tweet", "Comedic")
        football_for_comedy = ce.draft_quality_report("The Broncos saying Bo is fine is football for stop asking.", "Punchy Tweet", "Comedic")
        haunted_comedy = ce.draft_quality_report("The Nuggets bench is the same haunted basement again.", "Punchy Tweet", "Comedic")
        rage_comedy = ce.draft_quality_report("The Broncos said Bo is fine. Bullshit. Coward shit.", "Punchy Tweet", "Comedic")
        profanity_only_comedy = ce.draft_quality_report("The Nuggets bench is a fucking disaster.", "Punchy Tweet", "Comedic")
        announcement_comedy = ce.draft_quality_report("The Nuggets saying everything is on the table is very funny because the bench is still weird.", "Punchy Tweet", "Comedic")
        copied_comedy = ce.draft_quality_report("If another arm shows up, that ankle just held its own press conference.", "Punchy Tweet", "Comedic")
        table_comedy = ce.draft_quality_report("The Nuggets table has a velvet rope around the non Jokic minutes. Great table though.", "Punchy Tweet", "Comedic")
        press_release_comedy = ce.draft_quality_report("If another arm walks in, that ankle filed its own press release.", "Punchy Tweet", "Comedic")
        transaction_wire_comedy = ce.draft_quality_report("Teams that feel great about QB1 do not go backup shopping in May. The transaction wire talks.", "Punchy Tweet", "Comedic")
        qb3_honesty_comedy = ce.draft_quality_report("The Broncos say Bo is fine. QB3 is where the honesty lives.", "Punchy Tweet", "Comedic")
        bench_math_comedy = ce.draft_quality_report("If those minutes survive untouched, nothing actually changed. Bench math stays employed.", "Punchy Tweet", "Comedic")
        cover_reps_comedy = ce.draft_quality_report("If another arm shows up, that calm was doing a lot of work. That is cover your reps football.", "Normal Tweet", "Comedic")
        reporting_early_comedy = ce.draft_quality_report("If the next move is another quarterback, that calm update just put on shoulder pads. That is the backup plan reporting early.", "Normal Tweet", "Comedic")
        goalie_gear_comedy = ce.draft_quality_report("The Avs can call it matchup stuff all they want, but that is not staying steady. That is panic in goalie gear.", "Normal Tweet", "Comedic")
        split_card_comedy = ce.draft_quality_report("Very peaceful rebuild stuff. That split keeps writing the card.", "Normal Tweet", "Comedic")
        batting_order_comedy = ce.draft_quality_report("When the same script hits every trip, that is not growth. That is batting order denial.", "Normal Tweet", "Comedic")
        joke_is_comedy = ce.draft_quality_report("If the Broncos add another quarterback after saying Bo is fine, the joke is not the signing. It is pretending everyone is relaxed while buying insurance.", "Punchy Tweet", "Comedic")
        clean_analysis_comedy = ce.draft_quality_report("The Avs changing goalies after one loss creates pressure. That changes the whole conversation.", "Punchy Tweet", "Comedic")
        loud_calm_comedy = ce.draft_quality_report("Extra quarterback is a very loud kind of calm.", "Punchy Tweet", "Comedic")
        answering_questions_comedy = ce.draft_quality_report("The next QB signing walks in and starts answering questions for them.", "Punchy Tweet", "Comedic")
        group_text_comedy = ce.draft_quality_report("This is a group text where nobody knows who is driving.", "Punchy Tweet", "Comedic")
        stock_analogy_comedy = ce.draft_quality_report("The Avs crease is a rental car with a return policy after one loss.", "Punchy Tweet", "Comedic")
        homework_comedy = ce.draft_quality_report("The Rockies lineup forgot its homework against another road lefty.", "Punchy Tweet", "Comedic")
        improv_comedy = ce.draft_quality_report("Jokic sits and the offense becomes improv comedy.", "Punchy Tweet", "Comedic")
        non_actor_ankle_sentence = ce.draft_quality_report("The Broncos say Bo Nix is on track, but the next QB move decides how much they trust the ankle.", "Punchy Tweet", "Comedic")

        self.assertFalse(sarcastic["ok"])
        self.assertFalse(amused["ok"])
        self.assertFalse(skeptical["ok"])
        self.assertFalse(random_comedy["ok"])
        self.assertFalse(angry_comedy["ok"])
        self.assertFalse(analysis_comedy["ok"])
        self.assertFalse(fake_deep_comedy["ok"])
        self.assertFalse(nonsense_comedy["ok"])
        self.assertFalse(label_comedy["ok"])
        self.assertFalse(cute_comedy["ok"])
        self.assertFalse(creepy_comedy["ok"])
        self.assertFalse(truth_comedy["ok"])
        self.assertFalse(football_for_comedy["ok"])
        self.assertFalse(haunted_comedy["ok"])
        self.assertFalse(rage_comedy["ok"])
        self.assertFalse(profanity_only_comedy["ok"])
        self.assertFalse(announcement_comedy["ok"])
        self.assertFalse(copied_comedy["ok"])
        self.assertFalse(table_comedy["ok"])
        self.assertFalse(press_release_comedy["ok"])
        self.assertFalse(transaction_wire_comedy["ok"])
        self.assertFalse(qb3_honesty_comedy["ok"])
        self.assertFalse(bench_math_comedy["ok"])
        self.assertFalse(cover_reps_comedy["ok"])
        self.assertFalse(reporting_early_comedy["ok"])
        self.assertFalse(goalie_gear_comedy["ok"])
        self.assertFalse(split_card_comedy["ok"])
        self.assertFalse(batting_order_comedy["ok"])
        self.assertFalse(joke_is_comedy["ok"])
        self.assertFalse(clean_analysis_comedy["ok"])
        self.assertFalse(loud_calm_comedy["ok"])
        self.assertFalse(answering_questions_comedy["ok"])
        self.assertFalse(group_text_comedy["ok"])
        self.assertFalse(stock_analogy_comedy["ok"])
        self.assertFalse(homework_comedy["ok"])
        self.assertFalse(improv_comedy["ok"])
        self.assertNotIn("object-agency", " ".join(non_actor_ankle_sentence["issues"]).lower())
        self.assertTrue(any("copy old example" in issue.lower() for issue in sarcastic["issues"]))
        self.assertTrue(any("random analogy" in issue.lower() for issue in random_comedy["issues"]))
        self.assertTrue(any("angry" in issue.lower() for issue in angry_comedy["issues"]))
        self.assertTrue(any("witty edge analysis" in issue.lower() for issue in analysis_comedy["issues"]))
        self.assertTrue(any("witty edge analysis" in issue.lower() for issue in fake_deep_comedy["issues"]))
        self.assertTrue(any("confusing or surreal" in issue.lower() for issue in nonsense_comedy["issues"]))
        self.assertTrue(any("confusing or surreal" in issue.lower() for issue in label_comedy["issues"]))
        self.assertTrue(any("meme-caption" in issue.lower() for issue in cute_comedy["issues"]))
        self.assertTrue(any("random analogy" in issue.lower() for issue in creepy_comedy["issues"]))
        self.assertTrue(any("witty edge analysis" in issue.lower() for issue in truth_comedy["issues"]))
        self.assertTrue(any("meme-caption" in issue.lower() for issue in football_for_comedy["issues"]))
        self.assertTrue(any("random analogy" in issue.lower() for issue in haunted_comedy["issues"]))
        self.assertTrue(any("angry" in issue.lower() for issue in rage_comedy["issues"]))
        self.assertTrue(any("profanity is replacing the joke" in issue.lower() for issue in profanity_only_comedy["issues"]))
        self.assertTrue(any("meme-caption" in issue.lower() for issue in announcement_comedy["issues"]))
        self.assertTrue(any("confusing or surreal" in issue.lower() for issue in copied_comedy["issues"]))
        self.assertTrue(any("random analogy" in issue.lower() for issue in table_comedy["issues"]))
        self.assertTrue(any("confusing or surreal" in issue.lower() for issue in press_release_comedy["issues"]))
        self.assertTrue(any("confusing or surreal" in issue.lower() for issue in transaction_wire_comedy["issues"]))
        self.assertTrue(any("witty edge analysis" in issue.lower() or "confusing or surreal" in issue.lower() for issue in qb3_honesty_comedy["issues"]))
        self.assertTrue(any("confusing or surreal" in issue.lower() for issue in bench_math_comedy["issues"]))
        self.assertTrue(any("slogan/tagline" in issue.lower() or "confusing or surreal" in issue.lower() for issue in cover_reps_comedy["issues"]))
        self.assertTrue(any("object-agency" in issue.lower() or "confusing or surreal" in issue.lower() for issue in reporting_early_comedy["issues"]))
        self.assertTrue(any("slogan/tagline" in issue.lower() or "confusing or surreal" in issue.lower() for issue in goalie_gear_comedy["issues"]))
        self.assertTrue(any("object-agency" in issue.lower() or "confusing or surreal" in issue.lower() for issue in split_card_comedy["issues"]))
        self.assertTrue(any("slogan/tagline" in issue.lower() or "confusing or surreal" in issue.lower() for issue in batting_order_comedy["issues"]))
        self.assertTrue(any("meme-caption" in issue.lower() for issue in joke_is_comedy["issues"]))
        self.assertTrue(any("witty edge analysis" in issue.lower() for issue in clean_analysis_comedy["issues"]))
        self.assertTrue(any("witty edge analysis" in issue.lower() for issue in loud_calm_comedy["issues"]))
        self.assertTrue(any("confusing or surreal" in issue.lower() for issue in answering_questions_comedy["issues"]))
        self.assertTrue(any("random analogy" in issue.lower() for issue in group_text_comedy["issues"]))
        self.assertTrue(any("random analogy" in issue.lower() for issue in stock_analogy_comedy["issues"]))
        self.assertTrue(any("random analogy" in issue.lower() for issue in homework_comedy["issues"]))
        self.assertTrue(any("confusing or surreal" in issue.lower() for issue in improv_comedy["issues"]))

    def test_comedic_lane_is_canonical_with_amused_alias(self):
        self.assertIn("Comedic", ce.EMOTION_LANES)
        self.assertNotIn("Amused", ce.EMOTION_LANES)
        self.assertEqual(ce.normalize_lane("Amused"), "Comedic")
        prompt = ce.build_generation_prompt("The Nuggets bench turned a lead into panic.", "Normal Tweet", "Comedic", ce.initial_state())
        self.assertIn("EDGY GROUP-CHAT SPORTS COMEDY", prompt)
        self.assertIn("real laugh beat", prompt)
        self.assertIn("funniest sports guy", prompt)
        self.assertIn("line-break skeleton", prompt)
        self.assertIn("COMEDIC LANE HARD RULES", prompt)
        self.assertIn("COMEDIC OVERRIDE", prompt)
        self.assertIn("joke engine", prompt)

    def test_comedic_lane_accepts_sports_specific_jokes(self):
        examples = [
            "If the Broncos add another quarterback after saying Bo is fine, nobody is calling that a camp body with a straight face.",
            "The Nuggets can call everything open for debate, but Jokic sitting still turns into the part where the offense needs an adult.",
            "Changing goalies after one loss is how the Avs turn a hot hand into a full team trust exercise.",
        ]
        for text in examples:
            with self.subTest(text=text):
                self.assertTrue(ce.draft_quality_report(text, "Punchy Tweet", "Comedic")["ok"])

    def test_critical_lane_is_distinct_from_skeptical(self):
        self.assertIn("Critical", ce.EMOTION_LANES)
        critical = ce.lane_recipe("Critical")
        skeptical = ce.lane_recipe("Skeptical")

        self.assertIn("diagnosis", critical["target"].lower())
        self.assertIn("accountability", critical["target"].lower())
        self.assertNotEqual(critical["target"], skeptical["target"])

    def test_promo_lane_is_video_cliffhanger_mode(self):
        self.assertIn("Promo", ce.EMOTION_LANES)
        recipe = ce.lane_recipe("Promo")
        prompt = ce.build_generation_prompt(
            "Video title: Why the Avs goalie switch changes the whole series.",
            "Normal Tweet",
            "Promo",
            ce.initial_state(),
        )

        self.assertIn("missing third act", recipe["target"])
        self.assertIn("unresolved click tension", recipe["target"])
        self.assertIn("MONETIZATION-OPTIMIZED CLICK TENSION MODE", prompt)
        self.assertIn("PROMO VOICE - MONETIZATION-OPTIMIZED CLICK TENSION MODE", prompt)
        self.assertIn("LEARNED FORMAT PROFILE", prompt)
        self.assertIn("LEARNED VOICE PROFILE", prompt)

    def test_promo_quality_gate_blocks_youtube_clickbait(self):
        bad = "New video is live. You won't believe what I found. Watch until the end: https://youtu.be/test"
        report = ce.draft_quality_report(bad, "Normal Tweet", "Promo")

        self.assertFalse(report["ok"])
        self.assertTrue(any("clickbait" in issue.lower() for issue in report["issues"]))
        self.assertTrue(any("attached distribution context" in issue for issue in report["issues"]))

    def test_promo_quality_gate_blocks_generic_video_tease(self):
        generic = (
            "This video is about the Broncos offense and how things are changing for next season. "
            "There is a lot to talk about and the most interesting part is what happens next..."
        )
        report = ce.draft_quality_report(generic, "Normal Tweet", "Promo")

        self.assertFalse(report["ok"])
        self.assertTrue(any("specific sports tension" in issue for issue in report["issues"]))

    def test_promo_specificity_does_not_match_substrings(self):
        vague = (
            "The online state of the Broncos conversation looks simple until the whole timeline "
            "starts treating the same vague offseason mood like the answer everyone missed..."
        )
        report = ce.draft_quality_report(vague, "Normal Tweet", "Promo")

        self.assertFalse(report["ok"])
        self.assertTrue(any("specific sports tension" in issue for issue in report["issues"]))

    def test_promo_quality_gate_accepts_honest_video_tension(self):
        good = (
            "The Avs goalie switch looks like a simple matchup call until you isolate the one sequence "
            "that forced the bench into it. The box score points one direction.\n\nThe film points somewhere more uncomfortable..."
        )
        report = ce.draft_quality_report(good, "Normal Tweet", "Promo")

        self.assertTrue(report["ok"], report)
        self.assertFalse(any("cliffhanger" in warning.lower() for warning in report["warnings"]))

    def test_promo_quality_gate_accepts_qb_ankle_cliffhanger(self):
        good = (
            "Bo Nix may be trending toward camp, but ankle ready and ankle trusted are two different things. "
            "One more QB decision is coming that tells the truth.\n\nThe roster will say it out loud…"
        )
        report = ce.draft_quality_report(good, "Normal Tweet", "Promo")

        self.assertTrue(report["ok"], report)

    def test_promo_fallback_examples_pass_quality_gate(self):
        examples = [
            (
                "Bo Nix is the headline, but ankle ready and ankle trusted are two different Broncos conversations. "
                "The next QB decision is where the roster says how much trust is actually there.\n\n"
                "That is the part worth watching before camp..."
            ),
            (
                "The clean version is Bo Nix. The useful version is that ankle ready and ankle trusted are two different "
                "Broncos conversations. The next QB decision is where the roster says how much trust is actually there "
                "before the answer gets obvious."
            ),
            (
                "Bo Nix only looks settled from a distance. Up close, ankle ready and ankle trusted are two different "
                "Broncos conversations, and the next QB decision is where the roster says how much trust is actually there.\n\n"
                "That is the tension the video is built around..."
            ),
        ]

        for text in examples:
            with self.subTest(text=text):
                self.assertTrue(ce.draft_quality_report(text, "Normal Tweet", "Promo")["ok"])

    def test_validate_generation_options_identifies_all_rejected_promo_drafts(self):
        data = {
            "option1": "New video is live. You won't believe what I found. Watch until the end.",
            "option2": "This video is about the Broncos offense and there is a lot to talk about. What happens next...",
            "option3": "Full breakdown here. Like and subscribe. https://youtu.be/test",
        }
        report = ce.validate_generation_options(data, "Normal Tweet", "Promo")

        self.assertFalse(any(item.get("ok") for item in report.values()))
        self.assertTrue(any("clickbait" in " ".join(item.get("issues", [])).lower() for item in report.values()))
        self.assertTrue(any("specific sports tension" in " ".join(item.get("issues", [])) for item in report.values()))

    def test_format_evolution_rule_updates_are_approval_gated(self):
        tweets = [
            _tweet(23, "The Broncos plan looks boring until you remember boring is usually how this league hides the thing it actually believes. The fun version is rarely the one front offices choose...", hours_ago=90, views=15000, likes=300, replies=85, reposts=44),
            _tweet(24, "Nuggets fans keep asking for a clean bench answer, which is adorable because this team has chosen stress as a roster philosophy. At some point the chaos becomes the plan...", hours_ago=96, views=13000, likes=280, replies=76, reposts=38),
            _tweet(25, "CU development discourse would be a lot easier if people admitted Coach Prime can be annoying and still have a real player story. The internet hates holding both thoughts...", hours_ago=110, views=17000, likes=370, replies=100, reposts=52),
        ]

        state = ce.refresh_state(None, tweets, handle="polfam", now=NOW)
        format_props = [
            prop for prop in state["proposals"]
            if prop["rule"].startswith("For Normal Tweet, follow the learned winning format profile")
        ]

        self.assertTrue(format_props)
        self.assertNotIn(format_props[0]["rule"], ce.approved_rules_text(state))

        approved = ce.approve_proposal(state, format_props[0]["id"], now=NOW)

        self.assertIn(format_props[0]["rule"], ce.approved_rules_text(approved))
        self.assertIn(format_props[0]["rule"], ce.performance_context(approved))

    def test_sarcastic_lane_is_creator_evolution_owned_and_example_free(self):
        self.assertIn("Sarcastic", ce.EMOTION_LANES)

        prompt = ce.build_generation_prompt(
            "Broncos fans are watching the offense explain itself again",
            "Punchy Tweet",
            "Sarcastic",
            ce.initial_state(),
        )

        self.assertIn("SARCASTIC VOICE", prompt)
        self.assertIn("FAKE ENTHUSIASM MODE", prompt)
        self.assertIn("Cultural Leap", prompt)
        self.assertIn("brutal exaggeration", prompt)
        self.assertIn("No generic sarcastic openers", prompt)
        self.assertIn("zero chill", prompt)
        self.assertNotIn("Turns out the Patriots offense", prompt)
        self.assertNotIn("That cornerback needs to call someone", prompt)
        self.assertNotIn("copy this exact energy", prompt)

    def test_app_creator_evolution_uses_ce_owned_sarcastic_lane(self):
        app_text = Path("app.py").read_text()
        ce_defaults = app_text.split("CE_COMPAT_DEFAULTS", 1)[1].split("BUDGET_POLICY", 1)[0]
        ce_system_prompt = app_text.split("def _creator_evolution_system_prompt", 1)[1].split("def _ce_capture_ai_error", 1)[0]

        self.assertIn('"Sarcastic"', ce_defaults)
        self.assertIn("base_system = build_user_context()", ce_system_prompt)
        self.assertNotIn('get_system_for_voice("Sarcastic", "")', ce_system_prompt)

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
        self.assertIn("PERSONALITY LANE:\nAnnoyed", brief)
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
        self.assertEqual(decision["best"]["recommended_action"], "tweet")
        self.assertGreaterEqual(decision["best"]["score"], pulse.DEFAULT_THRESHOLD)
        self.assertIn("PULSE OPPORTUNITY", decision["brief"])
        self.assertNotIn("Hall of Fame examples", decision["brief"])
        self.assertIn("original standalone tweets only", decision["brief"])

    def test_pulse_returns_no_op_for_stale_or_weak_signal(self):
        tweets = [
            _tweet(11, "General reminder that sports are interesting", hours_ago=30, views=200, likes=2, replies=0, reposts=0),
        ]

        decision = pulse.find_pulse(tweets, [], ce.initial_state(), handle="polfam", now=NOW)

        self.assertEqual(decision["status"], "no_op")
        self.assertIsNone(decision["best"])

    def test_pulse_finds_avalanche_pregame_from_sports_context(self):
        self.assertEqual(pulse.PULSE_VERSION, "ce-pulse-v10-public-x-opportunity")

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
        self.assertEqual(news_decision["status"], "ready")
        self.assertEqual(news_decision["best"]["hard_blocks"], [])
        self.assertIn("newest signal 0.0h old", news_decision["best"]["why_now"])

    def test_pulse_rejects_cavs_false_avs_and_prefers_nuggets_presser(self):
        tweets = [
            _tweet(
                91,
                "Cavs on/offs vs. Pistons through two games. For the love. Of GOD. Play Jaylon Tyson.",
                hours_ago=1,
                views=30000,
                likes=800,
                replies=140,
                reposts=50,
                quotes=25,
            ),
        ]
        headlines = [
            {
                "title": "Nuggets hold end of season press conference with Michael Malone, Nikola Jokic, and Jamal Murray today",
                "source": "news",
                "publishedAt": "Mon, 04 May 2026 11:45:00 GMT",
            },
        ]

        decision = pulse.find_pulse(tweets, headlines, ce.initial_state(), handle="polfam", now=NOW)

        self.assertEqual(decision["status"], "ready")
        self.assertIn("Nuggets", decision["best"]["summary_text"])
        self.assertNotIn("Cavs", decision["best"]["summary_text"])
        self.assertTrue(pulse._is_colorado_current_context(decision["best"]["summary_text"]))
        self.assertFalse(pulse._is_colorado_current_context(tweets[0]["text"]))

    def test_pulse_rejects_non_sports_avs_encode_source(self):
        tweets = [
            _tweet(
                901,
                "I’ve always enjoyed this sequence in the movie. I was looking forward to see how the AVS encode on the CBHD disc would be. Black levels looks pretty good. #PhysicalMedia #HDDVD",
                hours_ago=0.1,
                views=90000,
                likes=1200,
                replies=260,
                reposts=100,
                quotes=50,
            ),
            _tweet(
                902,
                "Josh Kroenke said everything is on the table for the Nuggets this offseason except trading Nikola Jokic.",
                hours_ago=0.2,
                views=7000,
                likes=130,
                replies=25,
                reposts=14,
                quotes=7,
                author="TroyRenck",
            ),
        ]

        decision = pulse.find_pulse(tweets, [], ce.initial_state(), handle="polfam", now=NOW)

        self.assertEqual(decision["status"], "ready")
        self.assertIn("Nuggets", decision["best"]["summary_text"])
        self.assertNotIn("CBHD", decision["best"]["summary_text"])
        self.assertTrue(pulse._is_non_sports_avs_context(tweets[0]["text"]))
        self.assertFalse(pulse._is_colorado_current_context(tweets[0]["text"]))

    def test_pulse_rejects_live_show_promo_listicle_source(self):
        tweets = [
            _tweet(
                903,
                "DNVR Buffs Primetime is live! - are the Cleveland Browns setting Shedeur Sanders up for success in year 2? - Andre shares his top 5 favorite Buffs memories - drafting things that are OVERRATED",
                hours_ago=0.4,
                views=85000,
                likes=1000,
                replies=200,
                reposts=95,
                quotes=40,
                author="DNVR_Buffs",
            ),
            _tweet(
                904,
                "Nuggets ownership press conference keeps coming back to the same pressure point: Jokic is still the window and the roster has to match it.",
                hours_ago=0.2,
                views=7000,
                likes=140,
                replies=30,
                reposts=15,
                quotes=8,
                author="DNVR_Nuggets",
            ),
        ]

        decision = pulse.find_pulse(tweets, [], ce.initial_state(), handle="polfam", now=NOW)

        self.assertEqual(decision["status"], "ready")
        self.assertTrue(decision["best"]["topic"].startswith("nuggets"))
        self.assertNotIn("Primetime", decision["best"]["summary_text"])
        self.assertTrue(pulse._is_promo_source_text(tweets[0]["text"]))

    def test_pulse_rejects_merchandise_source(self):
        tweets = [
            _tweet(
                905,
                "NHL Colorado Avalanche Jersey for Dogs & Cats. Let your pet rep the Avs today. Buy now and use code.",
                hours_ago=0.2,
                views=60000,
                likes=700,
                replies=90,
                reposts=80,
                quotes=25,
            ),
            _tweet(
                906,
                "Colorado Avalanche coach quote sparks debate today about the playoff lineup and who actually starts tonight.",
                hours_ago=0.3,
                views=6000,
                likes=100,
                replies=20,
                reposts=12,
                quotes=4,
                author="AltitudeTV",
            ),
        ]

        decision = pulse.find_pulse(tweets, [], ce.initial_state(), handle="polfam", now=NOW)

        self.assertEqual(decision["status"], "ready")
        self.assertNotIn("Dogs", decision["best"]["summary_text"])
        self.assertTrue(pulse._is_commerce_source_text(tweets[0]["text"]))

    def test_pulse_blocks_betting_pick_and_prefers_dominant_nuggets_conversation(self):
        tweets = [
            _tweet(
                92,
                "03. Jesus Luzardo o7.5 Ks (-140) Has cleared 8+ Ks in back to back starts. Facing road Rockies who rank 1st in K% vs. LHP Great spot.",
                hours_ago=0.2,
                views=50000,
                likes=900,
                replies=160,
                reposts=60,
                quotes=30,
            ),
            _tweet(93, "Nuggets end of season press conference is the whole Denver sports conversation today.", hours_ago=0.3, views=3000, likes=40, replies=8, reposts=3, quotes=2),
            _tweet(94, "Michael Malone press conference with Nuggets media availability has everyone talking about what changes now.", hours_ago=0.4, views=3000, likes=40, replies=8, reposts=3, quotes=2),
            _tweet(95, "Jokic and Jamal Murray availability after the Nuggets season is clearly the story in Denver right now.", hours_ago=0.5, views=3000, likes=40, replies=8, reposts=3, quotes=2),
            _tweet(96, "Calvin Booth and Michael Malone comments at Nuggets press conferences are all over the timeline.", hours_ago=0.6, views=3000, likes=40, replies=8, reposts=3, quotes=2),
        ]

        decision = pulse.find_pulse(tweets, [], ce.initial_state(), handle="polfam", now=NOW)

        self.assertEqual(decision["status"], "ready")
        self.assertIn("Nuggets", decision["best"]["summary_text"])
        self.assertNotIn("Luzardo", decision["best"]["summary_text"])
        rejected_betting = [
            item for item in decision["top_rejected"]
            if "Luzardo" in item.get("summary_text", "")
        ]
        self.assertTrue(rejected_betting)
        self.assertIn("betting_angle", rejected_betting[0]["hard_blocks"])

    def test_pulse_does_not_treat_avax_crypto_as_avalanche_hockey(self):
        tweets = [
            _tweet(
                97,
                "Another swing trade long on an altcoin like Avalanche $AVAX played out for a 9.15% gain in Smart Money crypto.",
                hours_ago=0.2,
                views=60000,
                likes=1000,
                replies=160,
                reposts=60,
                quotes=30,
            ),
            _tweet(
                98,
                "Josh Kroenke says everything is on the table for the Nuggets this offseason, outside of trading Nikola Jokic.",
                hours_ago=0.5,
                views=3000,
                likes=60,
                replies=12,
                reposts=5,
                quotes=3,
            ),
        ]

        decision = pulse.find_pulse(tweets, [], ce.initial_state(), handle="polfam", now=NOW)

        self.assertEqual(decision["status"], "ready")
        self.assertIn("Nuggets", decision["best"]["summary_text"])
        self.assertNotIn("AVAX", decision["best"]["summary_text"])
        self.assertFalse(pulse._is_colorado_current_context(tweets[0]["text"]))

    def test_pulse_rejects_non_english_nuggets_sources(self):
        tweets = [
            _tweet(
                102,
                "« Je pense que cet été, toutes les options seront mises sur la table, à l’exception d’un trade de Nikola…je le précise, parce que mes propos ont sympathiquement été déformés l’été dernier… » Josh Kroenke, big boss des Denver Nuggets !",
                hours_ago=0.1,
                views=90000,
                likes=1200,
                replies=200,
                reposts=80,
                quotes=40,
            ),
            _tweet(
                103,
                "Josh Kroenke says everything is on the table for the Nuggets this offseason except trading Nikola Jokic.",
                hours_ago=0.4,
                views=5000,
                likes=90,
                replies=20,
                reposts=8,
                quotes=4,
            ),
        ]

        decision = pulse.find_pulse(tweets, [], ce.initial_state(), handle="polfam", now=NOW)

        self.assertEqual(decision["status"], "ready")
        self.assertIn("Nuggets", decision["best"]["summary_text"])
        self.assertNotIn("Je pense", decision["best"]["summary_text"])
        self.assertTrue(pulse._is_english_source_text(tweets[1]["text"]))
        self.assertFalse(pulse._is_english_source_text(tweets[0]["text"]))

    def test_pulse_returns_no_op_for_french_only_sources(self):
        tweets = [
            _tweet(
                104,
                "« Je pense que cet été, toutes les options seront mises sur la table, à l’exception d’un trade de Nikola… » Josh Kroenke, big boss des Denver Nuggets !",
                hours_ago=0.1,
                views=120000,
                likes=1800,
                replies=400,
                reposts=120,
                quotes=70,
            ),
        ]

        decision = pulse.find_pulse(tweets, [], ce.initial_state(), handle="polfam", now=NOW)

        self.assertEqual(decision["status"], "no_op")
        self.assertIsNone(decision["best"])

    def test_pulse_rejects_out_of_market_malone_unc_story(self):
        headlines = [
            {
                "title": "North Carolina working to finalize deal to hire Michael Malone as basketball coach, AP source says - AP News",
                "source": "news",
                "publishedAt": (NOW - timedelta(hours=0.1)).isoformat(),
                "url": "https://example.com/unc-malone",
            },
            {
                "title": "Denver Nuggets boss Josh Kroenke says everything is on the table this offseason except trading Nikola Jokic",
                "source": "news",
                "publishedAt": (NOW - timedelta(hours=0.4)).isoformat(),
                "url": "https://example.com/nuggets-kroenke",
            },
        ]

        decision = pulse.find_pulse([], headlines, ce.initial_state(), handle="polfam", now=NOW)

        self.assertEqual(decision["status"], "ready")
        self.assertIn("Nuggets", decision["best"]["summary_text"])
        self.assertIn("Kroenke", decision["best"]["summary_text"])
        self.assertNotIn("North Carolina", decision["best"]["summary_text"])
        self.assertTrue(pulse._is_out_of_market_context(headlines[0]["title"]))
        self.assertFalse(pulse._is_out_of_market_context(headlines[1]["title"]))

    def test_pulse_prefers_multi_source_denver_conversation_over_single_viral_tangent(self):
        tweets = [
            _tweet(
                110,
                "Bo Nix discourse is going nuclear because everyone is mad about one offseason clip from practice.",
                hours_ago=0.1,
                views=120000,
                likes=2200,
                replies=500,
                reposts=240,
                quotes=100,
                author="random_broncos_fan",
            ),
            _tweet(
                111,
                "Josh Kroenke said everything is on the table for the Nuggets this offseason except trading Nikola Jokic.",
                hours_ago=0.2,
                views=9000,
                likes=180,
                replies=38,
                reposts=20,
                quotes=8,
                author="TroyRenck",
            ),
            _tweet(
                112,
                "Nuggets ownership keeps coming back to the same pressure point: Jokic is still the window and the roster has to match it.",
                hours_ago=0.3,
                views=7000,
                likes=140,
                replies=25,
                reposts=16,
                quotes=6,
                author="DNVR_Nuggets",
            ),
            _tweet(
                113,
                "David Adelman and Josh Kroenke both talked about leadership, roster urgency, and not wasting the Nuggets' championship window.",
                hours_ago=0.4,
                views=6000,
                likes=130,
                replies=22,
                reposts=11,
                quotes=5,
                author="HarrisonWind",
            ),
            _tweet(
                114,
                "The Nuggets press conference kept circling back to complacency, injuries, and what this front office does around Jokic next.",
                hours_ago=0.5,
                views=5000,
                likes=100,
                replies=18,
                reposts=8,
                quotes=3,
                author="AltitudeTV",
            ),
        ]

        decision = pulse.find_pulse(tweets, [], ce.initial_state(), handle="polfam", now=NOW)

        self.assertEqual(decision["status"], "ready")
        self.assertTrue(decision["best"]["topic"].startswith("nuggets"))
        self.assertIn("Nuggets", decision["best"]["summary_text"])
        self.assertNotIn("Bo Nix", decision["best"]["summary_text"])

    def test_pulse_does_not_flag_die_inside_diehard_as_unsafe(self):
        flags = pulse._risk_flags("PLAYOFFS DIEHARD SPECIAL is live for Nuggets fans.")

        self.assertNotIn("unsafe:die", flags)

    def test_pulse_ranks_highest_scored_colorado_topic_before_strong_now_shortcut(self):
        tweets = [
            _tweet(
                99,
                "Another swing trade long on an altcoin like Avalanche $AVAX played out for a 9.15% gain in Smart Money crypto.",
                hours_ago=0.2,
                views=60000,
                likes=1000,
                replies=160,
                reposts=60,
                quotes=30,
            ),
            _tweet(
                100,
                "Josh Kroenke says everything is on the table for the Nuggets this offseason, except trading Nikola Jokic.",
                hours_ago=0.5,
                views=12000,
                likes=500,
                replies=90,
                reposts=30,
                quotes=20,
            ),
            _tweet(
                101,
                "Nuggets end of season press conference with Michael Malone and Calvin Booth is still dominating Denver sports today.",
                hours_ago=0.6,
                views=7000,
                likes=140,
                replies=25,
                reposts=8,
                quotes=5,
            ),
        ]

        decision = pulse.find_pulse(tweets, [], ce.initial_state(), handle="polfam", now=NOW)

        self.assertEqual(decision["status"], "ready")
        self.assertIn("Nuggets", decision["best"]["summary_text"])
        self.assertNotIn("Avalanche $AVAX", decision["best"]["summary_text"])

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
        self.assertEqual(decision["best"]["topic"], "avalanche")
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
        self.assertIsNone(decision["best"])

    def test_pulse_blocks_contextless_reply_fragments_with_unresolved_he(self):
        tweets = [
            _tweet(
                18,
                "@dalvinthetruth 100%. When he got to CU he was a nobody, he was like a 1 star or something. CU was like his only offer and coach Prime made him into an elite OT...",
                hours_ago=0.5,
                views=50000,
                likes=1200,
                replies=300,
                reposts=140,
                quotes=45,
            ),
        ]

        decision = pulse.find_pulse(tweets, [], ce.initial_state(), handle="polfam", now=NOW)

        self.assertEqual(decision["status"], "no_op")
        self.assertIsNone(decision["best"])
        self.assertIn("reply_fragment_context", decision["top_rejected"][0]["hard_blocks"])
        self.assertIn("unresolved_pronoun_context", decision["top_rejected"][0]["hard_blocks"])

    def test_pulse_allows_self_contained_named_timeline_context(self):
        tweets = [
            _tweet(
                19,
                "Jordan Seaton becoming a real CU development story is exactly the kind of Coach Prime argument people pretend does not count",
                hours_ago=0.5,
                views=50000,
                likes=1200,
                replies=300,
                reposts=140,
                quotes=45,
            ),
        ]

        decision = pulse.find_pulse(tweets, [], ce.initial_state(), handle="polfam", now=NOW)

        self.assertEqual(decision["status"], "ready")
        self.assertEqual(decision["best"]["hard_blocks"], [])

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
        self.assertIn("def _ce_format_recipe_text", app_text)
        self.assertIn("def _ce_format_learning_text", app_text)
        self.assertIn("def _ce_install_lane_recipe_text_compat", app_text)
        self.assertIn('getattr(ce, "lane_recipe_text", None)', app_text)
        self.assertIn('setattr(ce, "lane_recipe_text", _ce_lane_recipe_text)', app_text)
        self.assertNotIn("ce.lane_recipe_text(", app_text)
        self.assertIn("def _ce_validate_generation_options", app_text)
        self.assertIn("def _ce_prepare_generated_option", app_text)
        self.assertIn("def _ce_promo_fallback_generation", app_text)
        self.assertIn("def _ce_force_safe_promo_fallback", app_text)
        self.assertIn("def _ce_force_safe_lane_fallback", app_text)
        self.assertIn("fallback_data, fallback_quality, fallback_passing = _ce_promo_fallback_generation", app_text)
        self.assertIn("fallback_data, fallback_quality, fallback_passing = _ce_force_safe_promo_fallback", app_text)
        self.assertIn("fallback_data, fallback_quality, fallback_passing = _ce_force_safe_lane_fallback", app_text)
        self.assertIn('getattr(ce, "repair_generated_text_for_format", None)', app_text)
        self.assertIn("data[option_key] = _ce_prepare_generated_option", app_text)
        self.assertIn("repaired[option_key] = _ce_prepare_generated_option", app_text)
        self.assertIn("required_passing = 3", app_text)
        self.assertIn('repair_attempts = 12 if lane == "Comedic" else 4', app_text)
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
        self.assertIn("CREATOR EVOLUTION FORMAT CONTRACT", app_text)
        self.assertIn("LEARNED FORMAT PROFILE", app_text)
        self.assertIn("Format Evolution", app_text)
        self.assertIn("_ce_format_quality_findings", app_text)
        self.assertIn('max_tokens = 3500 if fmt == "Article" else 2200 if fmt == "Thread" else 1400 if fmt == "Long Tweet" else 700', app_text)
        self.assertIn("Refresh Tweets", app_text)
        self.assertNotIn("Refresh Replies", app_text)
        self.assertIn("PULSE RECOMMENDED ACTION", app_text)
        self.assertIn('draft_label_plural = "tweets"', app_text)
        self.assertIn("original standalone tweets", app_text)
        self.assertIn("Use Tweet", app_text)
        self.assertNotIn("Use Reply", app_text)
        self.assertIn("No gambling language", app_text)
        self.assertIn("def _ce_build_generation_prompt", app_text)
        self.assertIn("def _ce_build_hot_signal_brief", app_text)
        self.assertIn("def _ce_avs_live_state", app_text)
        self.assertIn("def _ce_avs_live_fallback_options", app_text)
        self.assertIn("def _ce_avs_no_score_fallback_options", app_text)
        self.assertIn("def _ce_pulse_meta_language", app_text)
        self.assertIn("write about that exact game state", app_text)
        self.assertIn("Avs up {score}", app_text)
        self.assertNotIn("_best_is_live_avs_game", app_text)
        self.assertNotIn("Avalanche Pulse fallback selected", app_text)
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
        self.assertIn('if _status == "no_op":', pulse_dialog)
        self.assertIn("_best = {}", pulse_dialog)
        self.assertIn("NO SAFE SOURCE", pulse_dialog)
        pulse_text = Path("creator_evolution_pulse.py").read_text()
        self.assertIn("best tweet available right now", pulse_text)
        self.assertIn("ce-pulse-v10-public-x-opportunity", pulse_text)
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

    def test_pulse_ui_hides_internal_debug_language_from_main_cards(self):
        app_text = Path("app.py").read_text()
        pulse_dialog = app_text.split('def _ce_pulse_dialog', 1)[1].split('@st.dialog("What', 1)[0]

        self.assertIn("_ce_pulse_display_signal", pulse_dialog)
        self.assertIn("Best signal for a", pulse_dialog)
        self.assertNotIn("Recommended {_action}", pulse_dialog)
        self.assertNotIn("Risk flags:", pulse_dialog)
        self.assertNotIn("Candidate fit", pulse_dialog)
        self.assertNotIn("Anchor {html.escape", pulse_dialog)

    def test_pulse_broncos_fallback_is_source_specific_not_generic(self):
        app_text = Path("app.py").read_text()
        fallback_block = app_text.split("def _ce_pulse_local_fallback_drafts", 1)[1].split("def _ce_pulse_finalize_drafts", 1)[0]

        self.assertIn("Illinois", fallback_block)
        self.assertIn("scouting tell", fallback_block)
        self.assertIn("Sean Payton", fallback_block)
        self.assertNotIn("words matter less than the next roster decision", fallback_block)
        self.assertNotIn("sell patience for only so long", fallback_block)

    def test_pulse_jokic_mvp_fallback_stays_on_mvp_signal(self):
        app_text = Path("app.py").read_text()
        fallback_block = app_text.split("def _ce_pulse_local_fallback_drafts", 1)[1].split("def _ce_pulse_finalize_drafts", 1)[0]
        mvp_block = fallback_block.split('if "mvp" in text', 1)[1].split('elif "adelman" in text', 1)[0]

        self.assertIn("SGA, Jokic and Wemby", mvp_block)
        self.assertIn("MVP finalist", mvp_block)
        self.assertNotIn("championship window", mvp_block)
        self.assertNotIn("roster math", mvp_block)

    def test_pulse_contract_blocks_selected_signal_drift_generically(self):
        app_text = Path("app.py").read_text()
        contract_block = app_text.split("def _ce_pulse_draft_contract_issues", 1)[1].split("def _ce_pulse_cached_decision_valid", 1)[0]

        self.assertIn("_ce_pulse_required_signal_terms(best)", contract_block)
        self.assertIn("Pulse draft drifted away from the selected signal", contract_block)
        self.assertIn("def _ce_pulse_required_signal_terms", app_text)
        self.assertIn("_ce_pulse_display_signal(best)", app_text)
        self.assertIn("CE_PULSE_BROAD_ANCHOR_TERMS", app_text)
        self.assertIn("CE_PULSE_SOURCE_STOP_TERMS", app_text)
        self.assertIn('"icymi"', app_text)
        self.assertIn('"youtube"', app_text)

    def test_pulse_blocks_crypto_ai_agent_sources_before_drafting(self):
        app_text = Path("app.py").read_text()
        source_block = app_text.split("def _ce_pulse_source_text_blocked", 1)[1].split("def _ce_pulse_draft_contract_issues", 1)[0]
        runner_block = app_text.split("def _run_creator_evolution_pulse", 1)[1].split('@st.dialog("Build a Tweet"', 1)[0]

        self.assertIn("def _ce_text_has_crypto_or_ai_trading_angle", app_text)
        self.assertIn("_ce_text_has_crypto_or_ai_trading_angle(clean)", source_block)
        self.assertIn("on-chain", app_text)
        self.assertIn("ai fund", app_text)
        self.assertIn("zk-trade", app_text)
        self.assertIn("_ce_pulse_cached_decision_valid(_decision, _ce_pulse_version())", runner_block)
        self.assertIn("def _ce_starter_pulse_decision", app_text)
        self.assertIn("_ce_starter_pulse_decision(lane=lane, fmt=fmt", runner_block)
        self.assertIn("blocked_source_recovery", app_text)
        self.assertIn('"starter_fallback"', app_text)
        self.assertIn("camp pressure", app_text)
        self.assertIn("Matches the Makar practice-update signal.", app_text)

    def test_creator_evolution_hot_feed_uses_source_backed_cards_before_fallback(self):
        app_text = Path("app.py").read_text()
        hot_block = app_text.split("def _run_creator_evolution_hot_signals", 1)[1].split("def _ce_pulse_error_decision", 1)[0]
        ui_block = app_text.split("def _ce_inspiration_dialog", 1)[1].split('@st.dialog("Creator Studio"', 1)[0]

        self.assertIn("def _creator_evolution_starter_hot_ideas", app_text)
        self.assertIn("def _ce_hot_signal_card_from_idea", app_text)
        self.assertIn("def _ce_hot_cards_from_pulse_feed", app_text)
        self.assertIn("_ce_hot_cards_from_pulse_feed(_all_tweets, _rss_headlines, _lane, _fmt)", hot_block)
        self.assertIn("return _pulse_cards, len(_all_tweets), len(_rss_headlines)", hot_block)
        self.assertIn('if str((idea or {}).get("source") or "").strip().lower() != "starter fallback"', hot_block)
        self.assertNotIn("_creator_evolution_starter_hot_ideas()", hot_block)
        self.assertNotIn("_ce_hot_signal_card_from_idea(_idea, _lane, _fmt)", hot_block)
        self.assertIn("starter fallback", app_text)
        self.assertIn('"creator_relevant"', hot_block)
        self.assertIn('and item.get("creator_relevant")', hot_block)
        self.assertIn('if not _pool:', hot_block)
        self.assertIn('_ideas = []', hot_block)
        self.assertIn("Source proof:", ui_block)
        self.assertIn("Source-backed grade", ui_block)
        self.assertIn("_ce_hot_quality_scores", app_text)

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
        self.assertIsNone(decision["best"])
        self.assertIn("duplicate_recent_angle", decision["top_rejected"][0]["hard_blocks"])

    def test_voice_and_format_recipes_are_engagement_focused_without_replacing_learning(self):
        self.assertIn("MONETIZATION-OPTIMIZED MIC DROP MODE", ce.lane_recipe_text("Witty Edge"))
        self.assertIn("QUIET DOUBT MODE", ce.lane_recipe_text("Skeptical"))
        self.assertIn("accountability", ce.lane_recipe_text("Critical"))
        self.assertIn("specific sports contradiction", ce.lane_recipe_text("Promo"))
        self.assertIn("source-specific wording", str(ce.validate_generation_options({
            "option1": "This Denver sports moment is where it gets interesting. The roster will tell us what matters next...",
            "option2": "This Denver sports moment is where it gets weird. The roster will tell us what matters next...",
            "option3": "This Denver sports moment is where the whole thing shifts. The roster will tell us what matters next...",
        }, "Normal Tweet", "Witty Edge")))
        self.assertIn("Preferred shape is two or three natural sentences", ce.format_recipe_text("Normal Tweet"))
        self.assertIn("One sharp, complete reaction", ce.format_recipe_text("Punchy Tweet"))
        self.assertIn("memorable closing turn", ce.format_recipe_text("Long Tweet"))
        self.assertIn("Separate tweets with ---TWEET---", ce.format_recipe_text("Thread"))
        self.assertIn("reusable article skeleton", ce.format_recipe_text("Article"))
        self.assertIn("at least 4 tweet segments", ce.format_recipe_text("Thread"))

    def test_lane_quality_gates_block_stock_engagement_and_generic_hype(self):
        witty = ce.draft_quality_report("Hot take: Broncos camp is where this roster gets interesting.", "Punchy Tweet", "Witty Edge")
        witty_metaphor = ce.draft_quality_report(
            "The Avs goalie spot sounds settled until the next ugly start hits like a smoke alarm.",
            "Punchy Tweet",
            "Witty Edge",
        )
        witty_reaction = ce.draft_quality_report(
            "The Avs goalie spot sounds settled until one ugly start and the whole room gets real quiet.",
            "Punchy Tweet",
            "Witty Edge",
        )
        witty_direct = ce.draft_quality_report(
            "The Avs goalie spot sounds settled until the next ugly start forces an actual decision.",
            "Punchy Tweet",
            "Witty Edge",
        )
        fired = ce.draft_quality_report("Let's go. The Avs are so back and nobody wants us now.", "Punchy Tweet", "Fired-Up")
        critical = ce.draft_quality_report("Fire everyone. This Broncos plan is trash?", "Punchy Tweet", "Critical")
        celebratory = ce.draft_quality_report("Let's go. Massive Nuggets win. We are so back.", "Punchy Tweet", "Celebratory")
        deadpan = ce.draft_quality_report("The Avs changed goalies again 😂", "Punchy Tweet", "Deadpan")

        self.assertFalse(witty["ok"])
        self.assertFalse(witty_metaphor["ok"])
        self.assertFalse(witty_reaction["ok"])
        self.assertTrue(witty_direct["ok"])
        self.assertFalse(fired["ok"])
        self.assertFalse(critical["ok"])
        self.assertFalse(celebratory["ok"])
        self.assertFalse(deadpan["ok"])

    def test_polished_punctuation_is_rejected_from_tweet_copy(self):
        bad = ce.draft_quality_report(
            "Broncos camp is simple: Bo Nix looks ready - but the QB room says otherwise.",
            "Punchy Tweet",
            "Witty Edge",
        )
        thread = ce.draft_quality_report(
            "Broncos camp will tell us what the QB room really believes.\n---TWEET---\nBo Nix can look ready and still force one more roster decision.\n---TWEET---\nThat is the part that usually tells on a team.\n---TWEET---\nThe room will say it before the press conference does...",
            "Thread",
            "Witty Edge",
        )

        self.assertFalse(bad["ok"])
        self.assertIn("polished punctuation", " ".join(bad["issues"]))
        self.assertTrue(thread["ok"])

    def test_each_voice_has_a_passing_engagement_fixture(self):
        fixtures = {
            "Witty Edge": "Broncos roster math is doing that thing where the boring answer starts looking like the dangerous one...",
            "Comedic": "Jokic dragged the bench through another shift and nobody even offered him babysitting money.",
            "Annoyed": "The Nuggets keep treating the bench problem like it is weather. At some point the pattern becomes the plan...",
            "Fired-Up": "MacKinnon shifts change the whole temperature of a series. Colorado has the lever sitting right there...",
            "Skeptical": "Bo Nix being ready for camp and being trusted at camp are two different Broncos conversations...",
            "Critical": "The Broncos process keeps creating the same roster pressure. That is a decision problem, not a luck problem...",
            "Promo": "Bo Nix ankle ready and ankle trusted are different Broncos decisions. Camp will say the quiet part...",
            "Celebratory": "The Nuggets finally got a bench stretch that felt like oxygen. That changes the whole math of the night...",
            "Deadpan": "The Avs changed goalies and immediately turned warmups into a congressional hearing.",
            "Sarcastic": "The Broncos calling this patience is generous. The roster is doing a full TED Talk on pressure management.",
        }

        for lane, text in fixtures.items():
            with self.subTest(lane=lane):
                self.assertTrue(ce.draft_quality_report(text, "Punchy Tweet", lane)["ok"])

    def test_each_format_has_a_passing_engagement_fixture(self):
        article_body = (
            "Broncos Roster Pressure\n\n"
            "The Broncos keep trying to make the quiet roster answer sound simple, but the football part keeps getting louder. "
            "Bo Nix can be on track for camp and still leave the staff with a real trust decision once the practice script gets uncomfortable. "
            "That is the part fans usually feel before anyone says it publicly.\n\n"
            "The Camp Tell\n\n"
            "The tell is not the headline about health. It is the way the quarterback work gets split when the team has to protect rhythm, timing, and the install at the same time. "
            "A normal rep plan says one thing. A protected rep plan says something else. Coaches can dress that up, but the field usually leaks the truth first.\n\n"
            "The Roster Consequence\n\n"
            "That matters because every extra insurance decision costs a roster spot somewhere else. The Broncos do not get to carry every comfort blanket and still pretend the rest of the depth chart is untouched. "
            "If the ankle is fully trusted, the room can stay lean. If it is only medically ready, the room starts asking for protection.\n\n"
            "The Fan Argument\n\n"
            "This is why the conversation keeps turning sideways. Fans hear progress and want to move on. The roster hears uncertainty and starts preparing for the expensive version. "
            "Both can be true, which is usually where the most honest football argument lives.\n\n"
            "The Bottom Line\n\n"
            "Training camp will tell us whether Bo Nix is healthy. It will also tell us whether the Broncos are willing to build the room like they believe it. "
            "That is where the next quarterback decision gets louder than the public update...\n\n"
        )
        article = article_body + ("The roster spot math keeps turning a medical update into a football decision. " * 12)
        fixtures = {
            "Punchy Tweet": "Broncos camp is about to turn one ankle update into a full roster truth serum.",
            "Normal Tweet": "Bo Nix can be on track for camp and still force a real Broncos decision. Healthy enough to practice and trusted enough to shape the QB room are not the same thing.\n\nThat roster spot will tell on them...",
            "Long Tweet": "Bo Nix being on track for camp is the easy part of the Broncos conversation. The harder part is what they do with the rest of the quarterback room once the reps get real. If the ankle is fully trusted, the roster can stay aggressive elsewhere. If it is only medically ready, the insurance plan starts costing them somewhere else...",
            "Thread": "Bo Nix being on track for camp is the headline.\n---TWEET---\nThe real Broncos tell is how they build the QB room around him once reps start getting protected.\n---TWEET---\nHealthy enough to practice and trusted enough to shape the roster are not the same thing.\n---TWEET---\nThat last quarterback decision is where the ankle update becomes a roster truth serum...",
            "Article": article,
        }

        for fmt, text in fixtures.items():
            with self.subTest(fmt=fmt):
                self.assertTrue(ce.draft_quality_report(text, fmt, "Witty Edge")["ok"])

    def test_option_set_validation_blocks_repeated_template_structure(self):
        data = {
            "option1": "The Broncos roster math keeps pointing at the same problem.\n\nThat is where this gets uncomfortable...",
            "option2": "The Broncos roster math keeps pointing at the same problem.\n\nThat is where this gets expensive...",
            "option3": "The Broncos roster math keeps pointing at the same problem.\n\nThat is where this gets real...",
        }
        report = ce.validate_generation_options(data, "Normal Tweet", "Witty Edge")

        self.assertTrue(report)
        joined = " ".join(" ".join(item.get("issues", []) + item.get("warnings", [])) for item in report.values())
        self.assertIn("same opener", joined)

    def test_option_set_validation_blocks_repeated_normal_tweet_line_skeleton(self):
        data = {
            "option1": "Bo Nix being ready for camp is the easy headline. The harder Broncos tell is how much protection they still build into the quarterback room.\n\nThe roster math will say it first.",
            "option2": "The Nuggets bench problem keeps getting treated like weather. But the rotation choices are starting to make that excuse look way too comfortable.\n\nThe minutes usually tell on the plan.",
            "option3": "The Avs goalie answer can sound settled in a press conference. One rough period is usually enough to show whether the room believes it.\n\nThat is where calm gets expensive.",
        }
        report = ce.validate_generation_options(data, "Normal Tweet", "Witty Edge")

        joined = " ".join(" ".join(item.get("issues", []) + item.get("warnings", [])) for item in report.values())
        self.assertIn("line-break skeleton", joined)

    def test_option_set_validation_allows_single_line_punchy_options(self):
        data = {
            "option1": "Broncos camp keeps making the quiet roster answer feel loud.",
            "option2": "Bo Nix being ready is not the same as the team acting relaxed.",
            "option3": "That quarterback room is about to say the part nobody will.",
        }
        report = ce.validate_generation_options(data, "Punchy Tweet", "Witty Edge")

        self.assertTrue(all(item["ok"] for item in report.values()))

    def test_option_set_validation_keeps_ellipsis_from_being_the_only_ending(self):
        data = {
            "option1": "The Broncos keep saying the roster is close. The next depth chart move will show whether they mean it.\n\nThe protection tells the story...",
            "option2": "The Nuggets keep saying they trust the bench. The next playoff rotation is where that gets tested.\n\nTrust looks different when the game tightens...",
            "option3": "The Avs keep calling the goalie situation settled. One tough start usually tells you if that is belief or hope.\n\nThat is when the noise gets loud...",
        }
        report = ce.validate_generation_options(data, "Normal Tweet", "Witty Edge")

        joined = " ".join(" ".join(item.get("issues", []) + item.get("warnings", [])) for item in report.values())
        self.assertIn("all end with ellipsis", joined)

    def test_learning_profiles_require_confidence_before_prompt_influence(self):
        tweets = [
            _tweet(700 + idx, f"The Broncos roster plan keeps pointing at the same pressure point number {idx}. That is where the offseason gets uncomfortable...", hours_ago=90 + idx, views=12000 + idx, likes=250 + idx, replies=60, reposts=30)
            for idx in range(3)
        ]
        state = ce.refresh_state(None, tweets, handle="polfam", now=NOW)
        profile = next(iter(state["patterns"]["format_profiles"].values()))
        prompt = ce.build_generation_prompt("Broncos roster plan", "Normal Tweet", "Witty Edge", state)

        self.assertEqual(profile["status"], "mature")
        self.assertFalse(profile["confidence_active"])
        self.assertIn("needs winning evidence across at least 2 topic/team buckets", profile["confidence_notes"])
        self.assertNotIn("Winning trait:", prompt)
        self.assertFalse(any("Start Creator Evolution drafts" in prop["rule"] for prop in state["proposals"]))
        self.assertFalse(any("learned winning format profile" in prop["rule"] for prop in state["proposals"]))

    def test_voice_learning_confidence_blocks_single_topic_formula(self):
        tweets = [
            _tweet(800 + idx, f"The Broncos roster plan keeps pointing at the same pressure point number {idx}. That is where the offseason gets uncomfortable...", hours_ago=90 + idx, views=15000 + idx, likes=320 + idx, replies=80, reposts=40)
            for idx in range(8)
        ]
        state = ce.refresh_state(None, tweets, handle="polfam", now=NOW)
        profile = state["patterns"]["voice_profile"]
        prompt = ce.build_generation_prompt("Broncos roster plan", "Normal Tweet", "Witty Edge", state)

        self.assertEqual(profile["status"], "mature")
        self.assertFalse(profile["confidence_active"])
        self.assertNotIn("Winning voice trait:", prompt)
        self.assertFalse(any("learned winning voice profile" in prop["rule"] for prop in state["proposals"]))

    def test_legacy_profiles_without_confidence_fail_closed(self):
        state = {
            "patterns": {
                "format_profiles": {
                    "Normal Tweet": {
                        "status": "mature",
                        "sample_size": 10,
                        "traits": ["LEGACY_TRAIT"],
                        "weak_traits": [],
                    }
                },
                "voice_profile": {
                    "status": "mature",
                    "sample_size": 10,
                    "traits": ["LEGACY_VOICE"],
                    "avoid_traits": [],
                },
            },
            "proposals": ce.propose_rules([
                ce.score_tweet(_tweet(900 + idx, f"The Broncos roster pressure keeps showing up in the same place number {idx}.", hours_ago=90 + idx, views=12000, likes=220, replies=40, reposts=20), NOW)
                for idx in range(3)
            ]),
        }

        self.assertEqual(ce.format_learning_text(state, "Normal Tweet"), "")
        self.assertEqual(ce.voice_learning_text(state), "")

    def test_app_fallback_recipes_include_current_creator_evolution_language(self):
        app_text = Path("app.py").read_text()

        self.assertIn("One sharp, complete reaction", app_text)
        self.assertIn("Preferred shape is two or three natural sentences", app_text)
        self.assertIn("line-break skeleton", app_text)
        self.assertIn("Headline, sharp intro, 3-5 section headings", app_text)
        self.assertIn("same hook-middle-close pattern", app_text)
        self.assertIn("Generated options all end with ellipsis", app_text)
        self.assertIn("Witty Edge should not lean on hot-take", app_text)
        self.assertIn("Generated options repeat the same opener", app_text)
        self.assertIn('profile.get("confidence_active") is not True', app_text)
        self.assertNotIn("overrides the static target range", app_text)
        self.assertIn("ACTIVE CALIBRATION", app_text)
        self.assertIn("TRACKED ONLY - not used in generation yet", app_text)
        self.assertIn("Needs a concrete sports/source detail so it does not read like generic strategy copy.", app_text)
        self.assertIn("Uses polished punctuation that does not sound like Tyler", app_text)


if __name__ == "__main__":
    unittest.main()
