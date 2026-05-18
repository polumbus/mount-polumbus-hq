# Creator Evolution Voice Profile Harness

This is an offline, read-only harness for building an approval-gated Tyler Voice Profile Prompt from the last 12 months of X posts.

It belongs to Creator Evolution only. It does not import app posting functions and does not call write/post/like/repost/bookmark endpoints.

## Commands

```bash
python -m creator_evolution.voice_profile_harness.cli ingest --source twitterapiio --username tyler.polumbus --months 12
python -m creator_evolution.voice_profile_harness.cli ingest-archive --archive-path /path/to/x_archive.zip --months 12
python -m creator_evolution.voice_profile_harness.cli ingest-manual --path /path/to/tweets.jsonl
python -m creator_evolution.voice_profile_harness.cli normalize
python -m creator_evolution.voice_profile_harness.cli analyze
python -m creator_evolution.voice_profile_harness.cli build-profile
python -m creator_evolution.voice_profile_harness.cli evaluate
python -m creator_evolution.voice_profile_harness.cli approve --profile data/creator_evolution/voice_profile/profiles/pending_profile.json
python -m creator_evolution.voice_profile_harness.cli status
```

## Artifact Contract

Default root:

```text
data/creator_evolution/voice_profile/
```

Required outputs are written under `raw/`, `cache/`, `analysis/`, `profiles/`, and `eval/`.

## Activation Contract

`profiles/pending_profile.json` is never active.

Creator Evolution only uses `profiles/approved_profile.json` when it has:

```json
{"activation_status": "approved"}
```

If no approved profile exists, Creator Evolution keeps its existing behavior.
