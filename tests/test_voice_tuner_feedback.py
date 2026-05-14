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

    def test_rules_are_scoped_to_lane_format_and_concept(self):
        rules = vtf.compile_voice_feedback("less setup", "Comedic", "Normal Tweet", "comedic", "manual")
        self.assertEqual(len(vtf.rules_for_context(rules, "Comedic", "Normal Tweet", "comedic")), 1)
        self.assertEqual(vtf.rules_for_context(rules, "Promo", "Normal Tweet", "comedic"), [])
        self.assertEqual(vtf.rules_for_context(rules, "Comedic", "Thread", "comedic"), [])
        self.assertEqual(vtf.rules_for_context(rules, "Comedic", "Normal Tweet", "other"), [])


if __name__ == "__main__":
    unittest.main()

