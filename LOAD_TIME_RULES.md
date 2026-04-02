# Post Ascend (HQ) — Load Time Rules

**These rules are MANDATORY. Violating ANY of them causes 30+ second page loads.**

App: `app.py` (~8800 lines). Streamlit re-executes the ENTIRE script top-to-bottom on every rerun (button click, widget change, navigation). Deployed on Streamlit Cloud where containers sleep after idle and cold-start with empty caches.

---

## Rule 1: ZERO API calls on first render

No `requests.get()`, `requests.post()`, `fetch()`, or any network call may execute during the first page render after login. Streamlit buffers ALL output and sends it to the browser only after the entire script completes. A 10-second API call = 10-second blank screen.

**Current pattern:** Tweet sync uses a two-phase session_state flag:
```python
# Render 1: just set the flag, no API call
# Render 2 (any widget click): sync runs
if st.session_state.get("_tweet_sync_ready"):
    if "_tweet_sync_done" not in st.session_state:
        st.session_state["_tweet_sync_done"] = True
        sync_tweet_history(quick=True)
else:
    st.session_state["_tweet_sync_ready"] = True
```

**If you need to add a new API call at startup, use this same two-phase pattern.**

---

## Rule 2: NEVER use @st.cache_data to guard startup API calls

`@st.cache_data` cache clears on every Streamlit Cloud cold start (container sleep, restart, deploy). Code that relies on it to "only run once per hour" will run on EVERY cold start, blocking the page.

- `@st.cache_data` is fine for lightweight functions (JSON parse, sorting, `get_voice_context()`, `analyze_personal_patterns()`)
- For API calls, use `session_state` flags instead

---

## Rule 3: API timeouts max 8 seconds

Any `requests.get/post()` in the app must use `timeout=8` or less. The timeout IS the worst-case load time if the API is slow or down.

Current: `sync_tweet_history` fetch window uses `timeout=8`.

---

## Rule 4: Tweet sync is always quick=True

`sync_tweet_history(quick=True)` fetches ~10 latest tweets with 1 API call. Never use `quick=False` in the render path (that's 104 API calls over 2 years of sliding windows).

Never check gist metadata to count tweets. Owner has 500+ tweets. The gist check was 2 API calls with 30s combined timeout — this was the original cause of the 30-second loads.

---

## Rule 5: Login uses st.rerun(), NEVER st.stop()

After successful login, call `st.rerun()`. Never `st.stop()`.

`st.stop()` sends the current output (login form) to the client, then query_params trigger ANOTHER rerun — creating a double-render that adds seconds of overhead.

---

## Rule 6: Opacity hide/reveal pattern must stay intact

Three CSS injections in app.py control the login→app transition:

1. **TOP of script (line ~43):** Hides sidebar and main content
```css
[data-testid="stSidebar"]{opacity:0;pointer-events:none}
.stApp [data-testid="stAppViewContainer"]{opacity:0}
```

2. **LOGIN page (line ~1313):** Shows main content so login form is visible
```css
.stApp [data-testid="stAppViewContainer"] { opacity: 1 !important; }
```

3. **BOTTOM of script (last output):** Reveals everything after all DOM elements are in place
```css
[data-testid="stSidebar"]{opacity:1!important;pointer-events:auto!important}
.stApp [data-testid="stAppViewContainer"]{opacity:1!important}
```

Removing any of these causes the sidebar to flash alongside the login form during the st.rerun() transition. The login form will also stay visible for the duration of the app render.

---

## Rule 7: One components.html() call maximum

Each `streamlit.components.v1.html()` creates an iframe. The desktop flyout JS injection (~1100 lines) is the ONE allowed iframe. Don't add more.

The cookie auth approach using `components.html()` was removed because cookies don't work on Streamlit Cloud (iframe sandbox isolation).

---

## How to diagnose if load time breaks again

1. Add timing instrumentation:
```python
_T0 = time.time()  # after set_page_config
# ... at key points:
print(f"[TIMING] section_name: {time.time()-_T0:.2f}s", flush=True)
```

2. Check logs: `journalctl --user -u mount-polumbus --since "2 minutes ago" | grep TIMING`

3. If Python execution is <0.1s but load is still slow → problem is client-side (DOM rendering, JS)

4. If Python execution is slow → find the API call or file I/O blocking the render path. Search for `requests.get`, `requests.post`, `urllib.request.urlopen` calls that run at module level (not inside function definitions or button handlers)

---

## Architecture reference

- Lines 1-70: imports, page config, opacity hide CSS, constants
- Lines 70-1230: function definitions (fast, no execution)
- Lines 1230-1400: auth gate (login form or st.stop)
- Lines 1400-1800: more function definitions, guest onboarding
- Lines 1800-2100: sidebar HTML construction + rendering
- Lines 2100-2280: desktop JS injection (the one allowed components.html)
- Lines 2280-2310: mobile nav HTML
- Lines 2310-8800: page function definitions (no execution until called)
- Lines 8800-8840: watermark, brand bar, page_fn() call, footer
- Lines 8840-8850: opacity reveal CSS (LAST output element)
- Lines 8850-8860: tweet sync (two-phase, skipped on first render)

**The only module-level code that EXECUTES between auth gate and the bottom is:** sidebar HTML rendering, desktop JS injection, mobile nav HTML, watermark/brand bar, the active page function, footer, and reveal CSS. All of these are fast (string output, no I/O).
