# Mount Polumbus HQ — Claude Code Instructions

## Mandatory Review Before Commit

EVERY time you finish making code changes and are about to commit, you MUST run `/hq-review` first. Do not commit without running the review skill. This is non-negotiable.

If the review returns FAIL, fix the issues before committing. If it returns WARN, mention the warnings to the user before committing.

## Post-Task Verification

After completing any task that modifies app.py or extension files, verify your work with dev-browser before telling the user you're done. Take a screenshot of the affected page and confirm it loads without errors.

## Streamlit Architecture Rules

- Never use module-level mutable dicts for per-user state. Always use `st.session_state`.
- Never run AI calls inside `@st.dialog` — run on the main page, dialog is display-only.
- Always clear stale result keys before setting new ones: `ci_banger_data`, `ci_result`, `ci_viral_data`, `ci_grades`, `ci_preview`.
- Twitter `createdAt` is NOT ISO format — use `strptime("%a %b %d %H:%M:%S %z %Y")`.

## Voice Rules

- Never say "former NFL OL" in prompts — use "former professional athlete".
- Sport detection must be score-based (count matches per sport), not first-match.
- Use full player names in detection: "jamal murray" not "murray", "aaron gordon" not "gordon".

## Extension Sync

After editing any file in `extension/`, always run:
```bash
cp /home/polfam/mount_polumbus_hq/extension/* /mnt/c/Users/polfa/Downloads/polumbus-extension/
```
Then remind the user to reload in chrome://extensions.

## Deployment

This app runs on Streamlit Cloud. Edits require `git push` to take effect. The repo is `github.com/polumbus/mount-polumbus-hq` on the `master` branch.
