import json
import tempfile
import unittest
from pathlib import Path

import podcast_store
import podcast_tracker
import podcast_workflow


STATE_LABELS = {
    "initialized": "Initialized",
    "transcribing": "Transcribing",
    "gate1_waiting": "Gate 1 Waiting",
    "gate1_approved": "Gate 1 Approved",
    "metadata_ready": "Metadata Ready",
    "gate2_waiting": "Gate 2 Waiting",
    "gate2_approved": "Gate 2 Approved",
    "ready_to_publish": "Ready To Publish",
    "publish_pending": "Publish Pending",
    "public_verified": "Public Verified",
    "done": "Done",
    "blocked_manual_fix": "Blocked",
}


def build_run(*, run_mode: str = "local", source_path: str = r"C:\video.mp4", state: str = "initialized") -> dict:
    store = podcast_tracker.empty_podcast_store()
    run = podcast_tracker.create_run(
        store,
        actor="tester",
        title="Test Run",
        source_path=source_path,
        run_mode=run_mode,
    )
    podcast_tracker.transition_run(store, run_id=run["id"], actor="tester", state=state)
    return next(item for item in store["runs"] if item["id"] == run["id"])


class PodcastWorkflowTests(unittest.TestCase):
    def test_local_initialized_action_starts_local_transcript(self):
        run = build_run()
        actions = podcast_workflow.guided_actions_for_run(run, STATE_LABELS)
        self.assertEqual(actions[0]["id"], "start_local_transcript")

    def test_non_local_initialized_requires_transcript(self):
        run = build_run(run_mode="url", source_path="https://youtu.be/test")
        actions = podcast_workflow.guided_actions_for_run(run, STATE_LABELS)
        self.assertEqual(actions[0]["id"], "transcript_ready")
        self.assertTrue(actions[0]["disabled"])

    def test_gate1_requires_saved_title_and_thumbnail(self):
        run = build_run(state="gate1_waiting")
        actions = podcast_workflow.guided_actions_for_run(run, STATE_LABELS)
        primary = actions[0]
        self.assertEqual(primary["id"], "approve_gate1")
        self.assertTrue(primary["disabled"])
        run["artifacts"]["title"]["text"] = "1. A title"
        run["artifacts"]["thumbnail_text"]["text"] = "1. Hook"
        actions = podcast_workflow.guided_actions_for_run(run, STATE_LABELS)
        self.assertFalse(actions[0]["disabled"])

    def test_gate2_requires_selected_clip_for_local_runs(self):
        run = build_run(state="gate2_waiting")
        actions = podcast_workflow.guided_actions_for_run(run, STATE_LABELS)
        self.assertTrue(actions[0]["disabled"])
        run["selected_clip_name"] = "clip1.mp4"
        actions = podcast_workflow.guided_actions_for_run(run, STATE_LABELS)
        self.assertFalse(actions[0]["disabled"])

    def test_publish_pending_requires_verification_and_receipt(self):
        run = build_run(state="publish_pending")
        actions = podcast_workflow.guided_actions_for_run(run, STATE_LABELS)
        self.assertTrue(actions[0]["disabled"])
        for key in ("public_url_checked", "processing_checked", "transcript_checked", "social_ids_checked"):
            run["verification"][key] = True
        run["deliveries"]["youtube"]["url"] = "https://youtube.com/watch?v=test"
        actions = podcast_workflow.guided_actions_for_run(run, STATE_LABELS)
        self.assertFalse(actions[0]["disabled"])

    def test_non_local_progress_is_compact(self):
        run = build_run(run_mode="url", source_path="https://youtu.be/test", state="publish_pending")
        steps, complete_count = podcast_workflow.progress_steps(run, {})
        self.assertEqual([step["label"] for step in steps], ["Prep", "Review", "Publish", "Done"])
        self.assertEqual(complete_count, 2)

    def test_blocked_local_packaging_resumes_with_clip_restart(self):
        run = build_run(state="blocked_manual_fix")
        run["blocked_from_state"] = "metadata_ready"
        actions = podcast_workflow.guided_actions_for_run(run, STATE_LABELS)
        self.assertEqual(actions[0]["id"], "restart_clip_step")

    def test_blocked_non_local_run_resumes_previous_state(self):
        run = build_run(run_mode="url", source_path="https://youtu.be/test", state="blocked_manual_fix")
        run["blocked_from_state"] = "gate2_waiting"
        actions = podcast_workflow.guided_actions_for_run(run, STATE_LABELS)
        self.assertEqual(actions[0]["id"], "resume_previous_state")


class PodcastStoreTests(unittest.TestCase):
    def test_per_run_store_round_trip(self):
        store = podcast_tracker.empty_podcast_store()
        first = podcast_tracker.create_run(store, actor="tester", title="One", source_path=r"C:\one.mp4", run_mode="local")
        second = podcast_tracker.create_run(store, actor="tester", title="Two", source_path="https://youtu.be/two", run_mode="url")
        store["active_run_id"] = second["id"]
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            podcast_store.write_local_store(store, data_dir)
            loaded, error = podcast_store.load_local_store_raw(data_dir)
            self.assertTrue((data_dir / podcast_store.RUNS_DIRNAME / podcast_store.RUNS_SUBDIRNAME).exists())
            self.assertTrue((data_dir / podcast_store.RUNS_DIRNAME / podcast_store.MANIFEST_FILENAME).exists())
            self.assertTrue((data_dir / podcast_store.LEGACY_STORE_FILENAME).exists())
        self.assertEqual(error, "")
        self.assertEqual(len(loaded["runs"]), 2)
        self.assertEqual(loaded["active_run_id"], second["id"])

    def test_load_falls_back_to_legacy_store_when_manifest_is_missing(self):
        store = podcast_tracker.empty_podcast_store()
        run = podcast_tracker.create_run(store, actor="tester", title="Legacy", source_path="https://youtu.be/legacy", run_mode="url")
        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp)
            (data_dir / podcast_store.LEGACY_STORE_FILENAME).write_text(
                json.dumps(store, indent=2, default=str),
                encoding="utf-8",
            )
            loaded, error = podcast_store.load_local_store_raw(data_dir)
        self.assertEqual(error, "")
        self.assertEqual(loaded["runs"][0]["id"], run["id"])


if __name__ == "__main__":
    unittest.main()
