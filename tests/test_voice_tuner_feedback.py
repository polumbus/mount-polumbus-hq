import unittest

import voice_tuner_feedback as vtf


class VoiceTunerFeedbackTests(unittest.TestCase):
    def test_compiles_exact_bans_and_soft_style_guidance(self):
        rules = vtf.compile_voice_feedback(
            "do not say things like you can always tell, the whole thing is, the funny part is and let the tweet do its own work without wasted space",
            "Comedic",
            "Normal Tweet",
            "comedic",
            "manual",
        )
        bans = [
            value
            for rule in rules
            if rule["kind"] == "forbid_phrase"
            for value in rule["matcher"]["values"]
        ]
        self.assertIn("you can always tell", bans)
        self.assertIn("the whole thing is", bans)
        self.assertIn("the funny part is", bans)
        self.assertNotIn("t say things like", bans)
        self.assertNotIn("everything on the table this summer", bans)
        self.assertTrue(any(rule["kind"] == "avoid_style" and rule["dimension"] == "setup" for rule in rules))

    def test_vague_feedback_is_soft_only(self):
        rules = vtf.compile_voice_feedback("make it better and more like my voice", "Witty Edge", "Normal Tweet", "witty", "manual")
        self.assertTrue(rules)
        self.assertTrue(all(rule["severity"] == "soft" for rule in rules))

    def test_hard_phrase_ban_fails_but_soft_feedback_only_warns(self):
        rules = vtf.compile_voice_feedback(
            "do not say 'the whole thing is' and less setup",
            "Comedic",
            "Normal Tweet",
            "comedic",
            "manual",
        )
        bad = vtf.evaluate_feedback_constraints(
            "The whole thing is the Nuggets bench still needs a witness.",
            rules,
            "Normal Tweet",
            "Comedic",
            "The Nuggets bench keeps wrecking leads.",
        )
        self.assertFalse(bad["ok"])
        self.assertTrue(bad["hard_failures"])

        soft_only = [rule for rule in rules if rule["severity"] == "soft"]
        warned = vtf.evaluate_feedback_constraints(
            "The funny part is the Nuggets bench keeps turning leads into a problem.",
            soft_only,
            "Normal Tweet",
            "Comedic",
            "The Nuggets bench keeps wrecking leads.",
        )
        self.assertTrue(warned["ok"])
        self.assertTrue(warned["soft_warnings"])


    def test_evaluator_filters_inactive_wrong_context_and_duplicates(self):
        base = vtf.compile_voice_feedback("do not say 'the whole thing is' and less setup", "Comedic", "Normal Tweet", "comedic", "manual")
        duplicate = dict(base[0])
        inactive = dict(base[0], id="inactive_rule", status="inactive")
        wrong_lane = dict(base[0], id="wrong_lane", lane="Promo")
        report = vtf.evaluate_feedback_constraints(
            "The whole thing is the Nuggets bench keeps wobbling.",
            [*base, duplicate, inactive, wrong_lane],
            "Normal Tweet",
            "Comedic",
            "The Nuggets bench keeps wobbling.",
        )

        self.assertEqual(len(report["hard_failures"]), 1)
        self.assertEqual(len(report["soft_warnings"]), 1)

    def test_quoted_source_detail_is_not_banned_unless_attached_to_say_ban(self):
        rules = vtf.compile_voice_feedback(
            'avoid losing the point from "Bo Nix looked rushed"',
            "Promo",
            "Normal Tweet",
            "promo",
            "manual",
        )
        bans = [rule for rule in rules if rule["kind"] == "forbid_phrase"]
        self.assertFalse(bans)

    def test_soft_style_feedback_creates_measurable_candidate_separation(self):
        rules = vtf.compile_voice_feedback(
            "less salesy and make the ending create more tension",
            "Promo",
            "Normal Tweet",
            "promo",
            "manual",
        )
        bad = vtf.evaluate_feedback_constraints(
            "This new video is live and you need to watch now because Bo Nix changes everything.",
            rules,
            "Normal Tweet",
            "Promo",
            "Bo Nix may be on track for training camp, but one QB decision will show how much Denver trusts the ankle.",
        )
        good = vtf.evaluate_feedback_constraints(
            "The Broncos can say Bo Nix is on track, but the next QB decision shows how much Denver actually trusts the ankle.",
            rules,
            "Normal Tweet",
            "Promo",
            "Bo Nix may be on track for training camp, but one QB decision will show how much Denver trusts the ankle.",
        )

        self.assertTrue(bad["soft_warnings"])
        self.assertLess(bad["feedback_score"], good["feedback_score"])
        self.assertGreaterEqual(good["feedback_score"], 85)

    def test_keep_the_point_compiles_source_preservation(self):
        rules = vtf.compile_voice_feedback(
            "keep the point about the road series and make it less polished",
            "Deadpan",
            "Normal Tweet",
            "deadpan",
            "manual",
        )
        self.assertTrue(any(rule["kind"] == "source_preservation" for rule in rules))

    def test_rules_are_scoped_to_lane_format_and_concept(self):
        rules = vtf.compile_voice_feedback("less setup", "Comedic", "Normal Tweet", "comedic", "manual")
        self.assertEqual(len(vtf.rules_for_context(rules, "Comedic", "Normal Tweet", "comedic")), 1)
        self.assertEqual(vtf.rules_for_context(rules, "Promo", "Normal Tweet", "comedic"), [])
        self.assertEqual(vtf.rules_for_context(rules, "Comedic", "Thread", "comedic"), [])
        self.assertEqual(vtf.rules_for_context(rules, "Comedic", "Normal Tweet", "other"), [])


if __name__ == "__main__":
    unittest.main()

