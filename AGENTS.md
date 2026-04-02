# Mount Polumbus HQ Agent Instructions

## Product Mindset

- Treat Mount Polumbus HQ as a premium product, not just a codebase.
- Prefer changes that improve clarity, perceived value, onboarding, and conversion.
- Keep edits small, reversible, and safe by default.

## Workflow

1. Inspect before editing.
2. Explain what you found.
3. Propose a short plan.
4. Execute the smallest useful change.
5. Validate what changed.
6. Preserve user work and unrelated changes.

## App Load Time Rules

These rules are mandatory for `app.py`. Breaking any of them can cause 30+ second page loads on Streamlit Cloud.

### Environment Reality

- `app.py` is large and Streamlit re-executes the entire script top-to-bottom on every rerun.
- Streamlit Cloud containers sleep after idle and cold-start with empty caches.
- The browser sees nothing until the server finishes the current render pass.

### Rule 1: Zero API Calls On First Render

- No `requests.get()`, `requests.post()`, `fetch()`, `urllib.request.urlopen()`, or any network call may run during the first page render after login.
- If startup needs an API call, use the existing two-phase `session_state` pattern:
  - Render 1 sets a flag only.
  - Render 2 performs the API work.
- Current approved pattern:

```python
if st.session_state.get("_tweet_sync_ready"):
    if "_tweet_sync_done" not in st.session_state:
        st.session_state["_tweet_sync_done"] = True
        sync_tweet_history(quick=True)
else:
    st.session_state["_tweet_sync_ready"] = True
```

### Rule 2: Never Use `@st.cache_data` To Guard Startup API Calls

- `@st.cache_data` is cleared on Streamlit Cloud cold starts, deploys, and container restarts.
- Do not rely on it for “only run once per hour” behavior for network requests.
- `@st.cache_data` is fine for lightweight local work like:
  - JSON parsing
  - sorting
  - `get_voice_context()`
  - `analyze_personal_patterns()`
- For API calls, use `session_state` flags instead.

### Rule 3: API Timeouts Max 8 Seconds

- Any `requests.get()` or `requests.post()` in the app must use `timeout=8` or less.
- Timeout value equals worst-case blocking time when the dependency is slow or down.

### Rule 4: Tweet Sync Is Always `quick=True`

- `sync_tweet_history(quick=True)` is approved in the render path.
- Never use `quick=False` in the render path.
- Never add gist metadata checks just to count tweets.
- The owner account has a large history, and old gist-count checks caused severe startup delays.

### Rule 5: Login Uses `st.rerun()`, Never `st.stop()`

- After successful login, call `st.rerun()`.
- Never use `st.stop()` for the successful-login transition.
- `st.stop()` sends the login output first, then query params trigger another rerun, creating an unnecessary double render.

### Rule 6: Opacity Hide/Reveal Pattern Must Stay Intact

Three CSS injections in `app.py` control the login-to-app transition and prevent UI flash:

1. Top of script: hide sidebar and main content.
2. Login page section: reveal main content so the login form is visible.
3. Bottom of script: reveal the full app only after all DOM elements are ready.

Do not remove or bypass this pattern unless you are deliberately replacing it with an equivalent solution.

### Rule 7: One `components.html()` Call Maximum

- Each `streamlit.components.v1.html()` creates an iframe.
- The desktop flyout JS injection is the one allowed iframe.
- Do not add more `components.html()` calls without explicit approval.
- Cookie auth via `components.html()` is not allowed because it does not work reliably on Streamlit Cloud.

### How To Diagnose Load Regressions

1. Add timing right after `set_page_config()`:

```python
_T0 = time.time()
print(f"[TIMING] section_name: {time.time() - _T0:.2f}s", flush=True)
```

2. Check logs:
   - `journalctl --user -u mount-polumbus --since "2 minutes ago" | grep TIMING`
3. If Python timing is fast but the page still feels slow, suspect client-side DOM or JS issues.
4. If Python timing is slow, search for blocking I/O in the render path:
   - `requests.get`
   - `requests.post`
   - `urllib.request.urlopen`
   - any module-level network call

### Architecture Reference

- Lines `1-70`: imports, page config, opacity hide CSS, constants
- Lines `70-1230`: function definitions only
- Lines `1230-1400`: auth gate
- Lines `1400-1800`: function definitions and guest onboarding
- Lines `1800-2100`: sidebar HTML construction and rendering
- Lines `2100-2280`: desktop JS injection
- Lines `2280-2310`: mobile nav HTML
- Lines `2310-8800`: page function definitions
- Lines `8800-8840`: watermark, brand bar, `page_fn()` call, footer
- Lines `8840-8850`: opacity reveal CSS
- Lines `8850-8860`: tweet sync using the two-phase pattern

### Safe Mental Model

- Between the auth gate and the bottom of the script, only fast string output should execute by default.
- Treat all network I/O in the render path as suspicious until proven safe.
- If a change touches startup, auth, sidebar rendering, nav JS, or tweet sync, validate load time explicitly before shipping.

## Tutorial Video Workflow

Use this workflow for all future app tutorial videos.

### Goal

Make clear product demos that teach users how to use the app.

The visual target is:
- crisp, true-to-app footage
- no bounce
- no zoom drift
- no dark cinematic overlay
- no greyed-out UI
- minimal annotations only if they do not dim the product

Do not turn product tutorials into moody promo edits.

### Source Of Truth

- Queue: [tutorials/tutorial_index.json](tutorials/tutorial_index.json)
- Main renderer: [scripts/render_tutorial.py](scripts/render_tutorial.py)
- Wrapper: [scripts/make_tutorial_video](scripts/make_tutorial_video)
- Queue runner: [scripts/tutorial_pipeline.py](scripts/tutorial_pipeline.py)
- Walkthrough configs:
  - [tutorials/creator_studio_walkthrough.json](tutorials/creator_studio_walkthrough.json)
  - [tutorials/configs/](tutorials/configs/)
- Outputs: [tutorials/output/](tutorials/output/)

### Required Production Rules

- Always browser-test app changes when the environment allows it.
- Validate the real page flow before mass-producing videos.
- Prefer cached-capture rebuilds for polish changes.
- Use fresh recapture only when the live flow itself changed or the old capture is wrong.
- If timing drifts, fix the scene config and clear stale edited-scene caches before rebuilding.
- If a visual treatment makes the app darker, remove the treatment rather than trying to “stylize through it.”

### Approved Visual Style

- Default screenshot scenes should be static and sharp.
- Motion is opt-in, not default.
- Any annotation should be light-touch and must not reduce app readability.
- If the app looks too dark in video, brighten the export rather than adding overlays.
- The app itself should remain the hero.

### Rendering Process

1. Pick the next page from [tutorials/tutorial_index.json](tutorials/tutorial_index.json).
2. Create or update the page walkthrough config in [tutorials/configs/](tutorials/configs/) or [tutorials/creator_studio_walkthrough.json](tutorials/creator_studio_walkthrough.json).
3. Browser-validate the live page.
4. Render a draft if needed:
   - `./scripts/make_tutorial_video <config> --owner-password "$POST_ASCEND_OWNER_PASSWORD" --draft --force-record`
5. For polish-only changes, reuse the existing capture:
   - `./scripts/make_tutorial_video <config> --owner-password "$POST_ASCEND_OWNER_PASSWORD" --assemble-only`
6. Review frames and timing.
7. Produce the final export.
8. Copy deliverables where the user needs them.

### Timing And Cache Rules

- Long static holds can make narration feel out of sync even when timestamps are technically correct.
- Prefer real motion clips for action-heavy tutorials like Creator Studio.
- If old styling or timing keeps showing up after code changes, clear stale caches under:
  - `tutorials/build/<output_name>/edited_scenes/`
  - `tutorials/build/<output_name>/styled_stills/`
  - `tutorials/build/<output_name>/edited_screen_capture.mp4`
  - `tutorials/build/<output_name>/stitched.mp4`

### Delivery Rules

- Put finished `.mp4` and `.srt` files in [tutorials/output/](tutorials/output/).
- Always copy finished tutorial `.mp4` and `.srt` files into the user's Windows Downloads folder.
- If a tutorial should live inside the app, add it as a stable asset under `static/` and wire it into the relevant page.

### Creator Studio Help Pattern

- The Creator Studio walkthrough lives at [static/creator-studio-walkthrough.mp4](static/creator-studio-walkthrough.mp4).
- The in-app help entry is wired in [app.py](app.py).
- Reuse this same pattern for future page-level help videos:
  - local static asset
  - small inline help entry
  - easy playback without leaving the tool

### What To Avoid

- Don’t dim the whole screen for style.
- Don’t default to animated zooms on screenshots.
- Don’t assume a rebuild changed the output if stale intermediate caches still exist.
- Don’t ship tutorial UI that is harder to access than the feature it explains.
