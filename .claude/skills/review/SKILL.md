---
name: review
description: Review code changes for bugs, Streamlit issues, and HQ-specific patterns before committing
user-invocable: true
---

# HQ Code Review

You are reviewing changes to Mount Polumbus HQ (a Streamlit app at app.py ~7000+ lines). Run this review before every commit.

## Step 1 — Diff Analysis

Run `git diff app.py` (and any other changed files) to see what changed. If nothing is staged, check `git diff HEAD` for unstaged changes.

## Step 2 — Check for Known HQ Bug Patterns

These are bugs we've hit repeatedly. Flag ANY occurrence:

### Streamlit State Bugs
- **Module-level mutable dicts used for per-user state** — Must use `st.session_state` instead. Module dicts reset between Streamlit Cloud workers. Look for: global dicts that store user-specific data (caches with timestamps, cursors, selections).
- **`st.rerun()` inside `@st.dialog`** — This closes the dialog. AI must run OUTSIDE the dialog on the main page, dialog is display-only. Check any new dialog functions.
- **Session state keys not cleaned up** — When setting new results, old result keys (ci_banger_data, ci_result, ci_viral_data, ci_grades, ci_preview) must be cleared first.
- **`st.text_area` with `value=` that reads from session state directly** — Use a staging key pattern (`_ci_text_stage`) consumed once via `pop()`.

### API & Data Bugs
- **TwitterAPI.io `from:` queries returning stale data** — The API sometimes returns cached old results for specific handles. If adding new `from:` queries, note this risk.
- **`datetime.fromisoformat()` on Twitter dates** — Twitter's `createdAt` is `"Thu Nov 23 03:31:24 +0000 2023"` format, NOT ISO. Must use `strptime` with `"%a %b %d %H:%M:%S %z %Y"`.
- **Freshness filters too tight** — Beat reporters: 48h is fine. National accounts: need 168h (they tweet about Denver rarely).

### Voice & Prompt Bugs
- **"former NFL OL" in prompts** — Use "former professional athlete" instead. NFL-specific framing biases Nuggets/Avs tweets toward Broncos content.
- **Sport detection first-match vs score-based** — Must count matches per sport and pick highest. Never use `if any(...)` chain where NFL is the fallback.
- **Ambiguous player names** — "murray" matches both Jamal Murray (NBA) and unrelated. Use full names: "jamal murray", "aaron gordon".

### Extension Bugs
- **Extension files not synced to Windows** — After editing `/home/polfam/mount_polumbus_hq/extension/*`, must copy to `/mnt/c/Users/polfa/Downloads/polumbus-extension/`.
- **Proxy `/call` endpoint needs both `prompt` and `system`** — Extension calls without `system` param lose Tyler's voice context.

## Step 3 — Syntax Check

Run: `python3 -c "import ast; ast.parse(open('app.py').read()); print('Syntax OK')"`

## Step 4 — Dev Browser Verification

After confirming no issues above, verify the live app with dev-browser:

```
dev-browser <<'SCRIPT'
const page = await browser.getPage("review-check");
await page.goto("https://polumbus-hq.streamlit.app/");
await page.waitForTimeout(10000);
const frames = page.frames();
let appFrame = null;
for (const f of frames) {
    if (f.url().includes('/~/+/')) { appFrame = f; break; }
}
if (appFrame) {
    const text = await appFrame.evaluate(() => document.body.innerText.substring(0, 500));
    console.log("APP LOADS:", text.substring(0, 200));
    const errors = await appFrame.evaluate(() => {
        const els = document.querySelectorAll('[data-testid="stException"]');
        return Array.from(els).map(e => e.innerText);
    });
    if (errors.length) console.log("ERRORS:", errors);
    else console.log("NO ERRORS DETECTED");
} else {
    console.log("Could not find app frame");
}
const buf = await page.screenshot({ fullPage: true, type: 'png' });
saveScreenshot(buf, "review-check.png");
SCRIPT
```

If the page being changed is not the default landing page, navigate to the specific page being modified.

## Step 5 — Report

Summarize findings as:
- **PASS** — no issues found, safe to commit
- **WARN** — minor issues flagged (list them), can commit but should fix soon
- **FAIL** — blocking issues that will break production (list them), do NOT commit

Always show the dev-browser screenshot result.
