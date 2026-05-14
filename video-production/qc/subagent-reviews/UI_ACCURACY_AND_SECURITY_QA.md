# UI_ACCURACY_AND_SECURITY_QA Review Packet

Current grade: blocked pending VIDEO_DEMO_MODE enforcement.

Finding:
Final recording must not call real AI, posting, OAuth, Twitter/X, proxy, podcast workers, Gists, or real data stores. Current production app does not yet enforce an app-wide demo boundary.

Required before 10/10:
- VIDEO_DEMO_MODE fixtures only.
- No secrets, real emails, tokens, cookies, private logs, webhook URLs, or real account data in scripts/captions/frames.
- Debug Console and Podcast demos must use fake safe data only.
