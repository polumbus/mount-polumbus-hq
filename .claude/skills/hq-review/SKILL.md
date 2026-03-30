---
name: hq-review
description: Run the HQ code quality checklist — diff analysis, bug pattern scan, syntax check, and dev-browser verification. This is NOT a PR review. This reviews local uncommitted changes against known HQ bug patterns.
user-invocable: true
---

# HQ Code Review Checklist

This is a LOCAL code quality review. Do NOT look for PRs. Do NOT use `gh`. Review the git diff of uncommitted changes against known bug patterns.

## Step 1 — Get the Diff

```bash
cd /home/polfam/mount_polumbus_hq && git diff HEAD
```

If the diff is empty, check for staged changes:
```bash
git diff --cached
```

If both are empty, tell the user "No changes to review" and stop.

## Step 2 — Scan for Known HQ Bug Patterns

Read through the diff line by line. Flag ANY of these:

### Streamlit State Bugs
- **Module-level mutable dicts for per-user state** — Module dicts persist across Streamlit Cloud workers but reset unpredictably. Must use `st.session_state`. Flag any new global dict that stores user selections, cursors, or results.
- **`st.rerun()` inside `@st.dialog`** — This closes the dialog. AI must run OUTSIDE the dialog, dialog is display-only. Flag any `st.rerun()` call inside a function decorated with `@st.dialog`.
- **Session state keys not cleaned up** — When setting new results, check that old keys are cleared: `ci_banger_data`, `ci_result`, `ci_viral_data`, `ci_grades`, `ci_preview`.
- **Widget key collisions** — Two widgets with the same `key=` string will crash Streamlit. Check that new widget keys are unique.

### API & Data Bugs
- **`datetime.fromisoformat()` on Twitter dates** — Twitter's `createdAt` format is `"Thu Nov 23 03:31:24 +0000 2023"`, NOT ISO. Must use `datetime.strptime(s, "%a %b %d %H:%M:%S %z %Y")`. Flag any `fromisoformat` on Twitter data.
- **Hardcoded API keys or secrets** — Flag any plaintext keys, tokens, or passwords.
- **Missing error handling on API calls** — External API calls (ESPN, Twitter, Perplexity) must have try/except.

### Voice & Prompt Bugs
- **"former NFL OL" in any prompt** — Must say "former professional athlete" to avoid Broncos bias on Nuggets/Avs content.
- **Sport detection using first-match** — Must be score-based (count matches per sport). Flag `if any(s in text for s in nba_signals):` without corresponding score counting.
- **Ambiguous player names without team qualifier** — "murray", "gordon" alone will false-match. Must use "jamal murray", "aaron gordon".

### Extension Bugs
- **Extension files changed but not synced** — If any file in `extension/` was modified, remind to run: `cp /home/polfam/mount_polumbus_hq/extension/* /mnt/c/Users/polfa/Downloads/polumbus-extension/`

## Step 3 — Syntax Check

```bash
cd /home/polfam/mount_polumbus_hq && python3 -c "import ast; ast.parse(open('app.py').read()); print('Syntax OK')"
```

## Step 4 — Dev Browser Verification

Load the live app and check for errors:

```bash
dev-browser <<'SCRIPT'
const page = await browser.getPage("hq-review");
await page.goto("https://polumbus-hq.streamlit.app/");
await page.waitForTimeout(12000);
const frames = page.frames();
let appFrame = null;
for (const f of frames) {
    if (f.url().includes('/~/+/')) { appFrame = f; break; }
}
if (appFrame) {
    const text = await appFrame.evaluate(() => document.body.innerText.substring(0, 300));
    console.log("APP LOADS:", text.substring(0, 200));
    const errors = await appFrame.evaluate(() => {
        const els = document.querySelectorAll('[data-testid="stException"]');
        return Array.from(els).map(e => e.innerText);
    });
    if (errors.length) console.log("ERRORS:", errors);
    else console.log("NO ERRORS");
} else {
    console.log("Could not find app frame");
}
const buf = await page.screenshot({ fullPage: true, type: 'png' });
saveScreenshot(buf, "hq-review.png");
SCRIPT
```

If the changes affect a specific page (not Creator Studio), also navigate to that page and check it.

## Step 5 — Report

Report findings as one of:

**PASS** — No issues found. Safe to commit.

**WARN** — Minor issues found (list each with file:line). Can commit but should fix soon.

**FAIL** — Blocking issues that will break production (list each with file:line). Do NOT commit until fixed.

Always show the screenshot from Step 4.
