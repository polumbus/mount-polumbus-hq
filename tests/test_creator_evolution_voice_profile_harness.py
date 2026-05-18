import json
import os
import tempfile
import unittest
from pathlib import Path

from creator_evolution.profile_loader import active_profile_version, approved_profile_prompt_insert, load_approved_profile
from creator_evolution.voice_profile_harness import HARNESS_VERSION
from creator_evolution.voice_profile_harness.approval_store import approve_profile
from creator_evolution.voice_profile_harness.config import artifact_path, redact_secrets, write_jsonl
from creator_evolution.voice_profile_harness.evaluation import run_evaluation
from creator_evolution.voice_profile_harness.feature_extractors import extract_voice_features
from creator_evolution.voice_profile_harness.normalize import normalize_tweet
from creator_evolution.voice_profile_harness.performance import score_snapshot
from creator_evolution.voice_profile_harness.prompt_builder import build_profile
from creator_evolution.voice_profile_harness.similarity_guard import ai_sound_flags, copy_similarity_report
from creator_evolution.voice_profile_harness.voice_analyzer import analyze_artifacts, normalize_artifacts


def _raw(tweet_id, text, **overrides):
    item = {
        "source_system": "manual_jsonl",
        "tweet": {
            "id": str(tweet_id),
            "text": text,
            "created_at": "2026-05-01T12:00:00+00:00",
            "author": {"userName": "tyler.polumbus"},
            "viewCount": overrides.pop("views", 5000),
            "likeCount": overrides.pop("likes", 100),
            "replyCount": overrides.pop("replies", 12),
            "retweetCount": overrides.pop("reposts", 8),
            "quoteCount": overrides.pop("quotes", 2),
            "bookmarkCount": overrides.pop("bookmarks", 1),
            **overrides,
        },
    }
    return item


class CreatorEvolutionVoiceProfileHarnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.old_root = os.environ.get("CE_VOICE_PROFILE_ROOT")
        os.environ["CE_VOICE_PROFILE_ROOT"] = str(self.root)

    def tearDown(self):
        if self.old_root is None:
            os.environ.pop("CE_VOICE_PROFILE_ROOT", None)
        else:
            os.environ["CE_VOICE_PROFILE_ROOT"] = self.old_root
        self.tmp.cleanup()

    def _seed_raw(self):
        rows = [
            _raw(1, "The Broncos keep calling this depth. Looks a lot more like insurance with a helmet.", views=18000, replies=40, reposts=30),
            _raw(2, "Avs fans pretending a 5-2 lead feels safe is the most dishonest thing in hockey.", views=12000, replies=32, reposts=18),
            _raw(3, "The Nuggets bench math gets real spiritual the second Jokic sits down.", views=9000, replies=30, reposts=14),
            _raw(4, "Here is the thing, this team needs to optimize engagement and build a content strategy.", views=500, replies=0, reposts=0),
            _raw(5, "@somebody this is a reply that should be filtered", views=99999),
            _raw(6, "RT somebody else's post", views=99999),
        ]
        write_jsonl(artifact_path("raw/manual_import.jsonl", self.root), rows)

    def test_harness_imports_under_creator_evolution_namespace(self):
        self.assertEqual(HARNESS_VERSION, "ce-voice-profile-harness-v1")

    def test_normalize_and_filter_pipeline(self):
        self._seed_raw()
        result = normalize_artifacts(root=self.root)
        self.assertEqual(result["raw_count"], 6)
        self.assertEqual(result["used_count"], 4)
        normalized = artifact_path("cache/normalized_tweets.jsonl", self.root).read_text()
        self.assertIn('"tweet_id":"1"', normalized)
        self.assertNotIn('"tweet_id":"5"', normalized)
        self.assertNotIn('"tweet_id":"6"', normalized)

    def test_metric_scoring_and_cohorts_and_prompt_artifacts(self):
        self._seed_raw()
        normalize_artifacts(root=self.root)
        analysis = analyze_artifacts(root=self.root)
        self.assertGreaterEqual(analysis["cohort_count"], 8)
        built = build_profile(root=self.root)
        self.assertTrue(Path(built["profile_path"]).exists())
        self.assertTrue(Path(built["prompt_path"]).exists())
        pending = json.loads(artifact_path("profiles/pending_profile.json", self.root).read_text())
        self.assertEqual(pending["activation_status"], "pending")
        self.assertIn("No corporate polish", artifact_path("profiles/pending_profile_prompt.md", self.root).read_text())

    def test_pending_profile_does_not_activate_until_approved(self):
        self._seed_raw()
        normalize_artifacts(root=self.root)
        analyze_artifacts(root=self.root)
        built = build_profile(root=self.root)
        self.assertEqual(load_approved_profile(self.root), {})
        self.assertEqual(active_profile_version(self.root), "")
        self.assertEqual(approved_profile_prompt_insert(self.root), "")
        approved = approve_profile(built["pending_profile_path"], root=self.root)
        self.assertTrue(approved["profile_version"])
        self.assertTrue(load_approved_profile(self.root))
        self.assertIn("APPROVED TYLER VOICE PROFILE", approved_profile_prompt_insert(self.root))

    def test_evaluation_flags_ai_and_copy_risk(self):
        flags = ai_sound_flags("Here is the thing, not only does this optimize engagement, but also it drives strategy.")
        self.assertIn("Here is the thing", flags)
        report = copy_similarity_report(
            ["The Broncos keep calling this depth. Looks a lot more like insurance with a helmet."],
            ["The Broncos keep calling this depth. Looks a lot more like insurance with a helmet."],
        )
        self.assertTrue(report["copied_too_closely"])

    def test_full_evaluation_writes_acceptance_artifacts(self):
        self._seed_raw()
        normalize_artifacts(root=self.root)
        analyze_artifacts(root=self.root)
        build_profile(root=self.root)
        acceptance = run_evaluation(root=self.root)
        self.assertTrue(acceptance["no_live_tweets_sent"])
        self.assertTrue(artifact_path("eval/final_acceptance_report.md", self.root).exists())
        self.assertTrue(artifact_path("eval/copy_similarity_report.json", self.root).exists())

    def test_no_live_posting_path_is_reachable_from_harness(self):
        package = Path("creator_evolution/voice_profile_harness")
        forbidden = [
            "from app import",
            "\nimport app\n",
            "\nimport app as ",
            "_post_tweet(",
            "tweet/post",
            "/2/tweets",
            "requests.post(",
            "urlopen(",
            "/tweet/like",
            "/tweet/repost",
            "/tweet/bookmark",
        ]
        for path in package.glob("*.py"):
            text = path.read_text(encoding="utf-8")
            for needle in forbidden:
                self.assertNotIn(needle, text, f"{needle} found in {path}")

    def test_creator_studio_is_not_wired_to_the_harness(self):
        app_text = Path("app.py").read_text(encoding="utf-8")
        self.assertNotIn("voice_profile_harness", app_text)
        self.assertNotIn("approved_profile_prompt_insert", app_text)

    def test_secret_redaction(self):
        os.environ["TWITTER_API_IO_KEY"] = "super-secret-value"
        redacted = redact_secrets("api_key=super-secret-value Authorization: Bearer abc.def")
        self.assertNotIn("super-secret-value", redacted)
        self.assertNotIn("abc.def", redacted)

    def test_single_record_feature_and_score_contract(self):
        raw = _raw(10, "Very normal sport when the Avs lead by three and nobody can unclench.", views=10000)
        normalized = normalize_tweet(raw, source_system="manual_jsonl")
        features = extract_voice_features(normalized)
        self.assertEqual(features["emotion_lane"], "Deadpan")
        score = score_snapshot({
            "tweet_id": "10",
            "age_hours_at_snapshot": 72,
            "views": 10000,
            "likes": 200,
            "replies": 20,
            "reposts": 10,
            "quotes": 3,
            "bookmarks": 5,
        })
        self.assertGreater(score["normalized_score"], 0)


if __name__ == "__main__":
    unittest.main()
