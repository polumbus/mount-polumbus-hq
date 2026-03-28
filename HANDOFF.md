# Mount Polumbus HQ — 48-Hour Session Handoff
*March 28, 2026 — for seamless Claude Code session transfer*

---

## Who Tyler Is

Tyler Polumbus — former NFL OL (8 seasons, Super Bowl 50 champion), radio host on Altitude 92.5 (PhD Show, noon–3 PM MST Mon–Fri). Runs Mount Polumbus YouTube/podcast. 42K+ X followers (@tyler_polumbus), 3.4K+ YouTube subs. Covers Denver Broncos (~80%), Nuggets, Avs, CU Buffs. Goal: grow X, produce content faster, monetize.

---

## The Two Systems

**Mount Polumbus HQ** — Streamlit web app at `/home/polfam/mount_polumbus_hq/app.py` (single file, ~6150 lines). Live at polumbus-hq.streamlit.app, local at localhost:8501, phone via Tailscale at 100.68.77.18:8501.

**OpenClaw** — 10 Discord agents at `~/.openclaw/`. Gateway on port 18789. Automates content workflow.

---

## Setup & Connectivity

- WSL2 Ubuntu-24.04, hostname DesktopTP, user `polfam`
- Connect via `\\wsl.localhost\Ubuntu-24.04\home\polfam\mount_polumbus_hq`
- OpenClaw at `\\wsl.localhost\Ubuntu-24.04\home\polfam\.openclaw`
- Service: `systemctl --user restart mount-polumbus`
- Gateway: `systemctl --user restart openclaw-gateway`

---

## API Integrations (NEW — March 27-28, 2026)

### API Modules (`~/.openclaw/apis/`)
- `espn.py` — scores, standings, news, team info (FREE, no key)
- `sleeper.py` — NFL players, injuries, depth charts, trending (FREE, no key)
- `perplexity.py` — fact-check, search, research (key at `~/.openclaw/apis/.keys/perplexity.key`)
- `odds.py` — betting lines (NOT YET CONNECTED — needs free key from the-odds-api.com)

### Where APIs Are Integrated

| Agent/Feature | Script | ESPN | Sleeper | Perplexity |
|---------------|--------|------|---------|------------|
| Tempo | game_preview.py | Scores, broadcast | Injuries, depth chart | — |
| Tempo | game_recap.py | (existing) | Injuries both teams | — |
| Blitz | draft_tweets.py | NBA scores, NFL news | Trending, injuries | — |
| Blitz | reply_sniper.py | Scores, headlines | Trending, NFL state | — |
| Cadence | rd_council.py | Scores, news, team info | Injuries, trending | — |
| Scout | overnight_competitor_report.py | Headlines | Trending players | — |
| Redzone | gameday_watcher.py | Scores (primary) | — | — |
| Booth | competitor_title_scanner.py | Headlines | — | — |
| HQ App | Creator Studio | Scores, news, teams | Injuries, trending | Verify button |
| HQ App | What's Hot | Headlines | Trending | — |
| HQ App | Content Advisor | Full context | Full context | — |
| HQ App | Article Writer | Sports context | — | Research button |

---

## AI Architecture — How Claude Calls Work

### Three API Paths (tried in order)
1. **`_call_claude_direct`** — OAuth bearer token → `api.anthropic.com/v1/messages` (WORKS for Sonnet+Haiku)
2. **CLI fallback** — `claude -p --system-prompt "..." --model claude-sonnet-4-6` (local only)
3. **Proxy fallback** — `_call_claude_proxy` → local `claude_proxy.py` on port 7821

### OAuth Setup
- Token: `~/.claude/.credentials.json` → `claudeAiOauth.accessToken`
- Billing header hack in system prompt array enables Sonnet access via Max OAuth
- Both Sonnet and Haiku confirmed working (tested March 28)
- `--system-prompt` flag used for CLI path (fixed this session — was concatenating system+user before)

### System Prompt Architecture
- `get_system_for_voice(voice, voice_mod)` builds the full system prompt
- **Default voice:** TYLER_CONTEXT + top 15 tweets + "match this voice" + Film Room Mode rules
- **Non-default voices:** TYLER_CONTEXT + voice-specific examples + voice_mod + "IMPORTANT: Write ONLY in this voice"
- Non-default voices do NOT include top tweet examples (they were overriding voice)

---

## Voice System (MAJOR REWORK — March 28, 2026)

### `_build_voice_mod(voice)` — Complete Rewrite
All 4 voices completely rewritten with detailed rules:

**Default (Film Room Mode):**
- Observation → Context → Open Door (ellipsis)
- INPUT REFRAMING RULE: strips opinion words, rebuilds from facts only
- BANNED WORDS: "no-brainer", "obvious", "clearly", "definitely", "unpopular opinion", "hot take"
- Never editorialize — the observation IS the take

**Critical (Diagnosis Mode):**
- Symptom (specific stat) → Diagnosis (structural cause) → Challenge (name the person)
- AI PICK PREFERENCE: period-ending > question-ending
- Never ends with ellipsis — period only
- Authority implied through specificity, never stated ("I played 8 years")

**Homer (Don't Sleep On Us Mode):**
- Signal → Why It Matters → Forward Statement (opponent already reacting)
- PUNCHY FORMAT COMPRESSION RULE: sentence 1 = signal, sentence 2 = outside party already acted
- DRAFT AND ROSTER SITUATIONS: outside party is always other teams/draft rooms
- Never state confidence directly — show opposition worried

**Sarcastic (Layered Reference Mode):**
- Two tools: Cultural Leap (positive) vs Implied Real Story (negative)
- No generic openers ("Oh interesting", "Sure", "Cool")
- React to the FEELING not the event
- Drop it and walk away — never explain the joke

### BANNED OPENERS (all voices + all format types)
- "Someone help me understand"
- "Nobody is talking about"
- "Not enough people are talking about"
- "Unpopular opinion"
- "Let that sink in"
- "This is your reminder"
- "Connect the dots"

### `_build_format_mod(fmt, pp, voice)` — Voice-Aware
- Now accepts `voice` parameter
- When voice != Default: omits Tyler's top hook examples, skips format patterns injection
- Adds `VOICE: You MUST write in {voice} voice` override in user prompt
- Punchy/Normal/Long/Thread all have BANNED OPENERS block
- Normal Tweet structure changed to fact-first: `[Factual observation] + [Context/consequence]`

### Voice Examples in `get_system_for_voice()`
Updated to match new rules:
- Critical examples end with named accountability ("Paton owns this one.")
- Homer examples end with opponent reaction ("Other draft rooms already know it.")
- Sarcastic examples use Cultural Leap / Implied Real Story (no "Oh cool" openers)

### `_WHATS_HOT_VOICE_GUIDE`
Updated to match all voice rules. Includes Homer ENDING RULE with WRONG/RIGHT examples.

---

## Creator Studio — Go Viral Flow (MAJOR FIX — March 28)

### The Dialog Caching Problem (FIXED)
`@st.dialog` runs as a Streamlit fragment. When `_run_ci_ai` ran INSIDE the dialog, the fragment cached its render and served stale AI results for different tweet inputs.

### Current Architecture
1. User clicks Go Viral → `on_click` callback stores `_ci_pending = (action, text, fmt, voice)`
2. On rerun, `_ci_pending` is popped
3. **`_run_ci_ai` runs OUTSIDE the dialog** with `st.spinner` on the main page
4. Results stored in `st.session_state["ci_banger_data"]`
5. Dialog opens (with unique `time.time()` nonce) and ONLY DISPLAYS results
6. Dialog never calls `_run_ci_ai` — it's purely display

### Cache Removal (Complete)
- `ci_ai_cache` dict: **REMOVED** (was MD5-keyed, blocked voice changes)
- `_cache_key` / `hashlib.md5` in banger/build/rewrite: **REMOVED**
- `force_regen` parameter: **REMOVED** (dead after cache removal)
- `_ci_force_regen` session state: **REMOVED**
- Grades cache (`ci_grades_cache`): **KEPT** — separate, only caches same tweet text

### Auto-Populate Fix
AI results no longer auto-stage into the concept text box. Only the "Use" button inside the popup writes to `_ci_text_stage`. User can close popup, change format/voice, re-run without losing their concept.

### Force Clear on Every Call
`_run_ci_ai` clears all 11 result keys at the top of every call:
`ci_banger_data, ci_result, ci_repurposed, ci_preview, ci_grades, ci_banger_opt_1/2/3, _verify_1/2/3`

---

## What's Hot / Inspiration

### Architecture
- `_fetch_inspiration_feed()` — cached 1hr, pulls from 4 Twitter lists + 2 searches + ESPN + Sleeper + RSS
- `_run_inspiration_claude()` — cached 30min, generates 14 ideas with voice tags
- Dialog shows 7 at a time, "New Ideas" rotates through cached pool
- Gist-backed cache (`hq_inspo_cache.json`) with 2hr TTL

### Known Issue: New Ideas Button
Multiple fix attempts (fragment rerun, on_click callback, dialog flag). Still intermittently broken. The `@st.dialog` fragment caching makes button state management unreliable.

---

## Pending / Known Issues

### #1 Priority — Go Viral Stale Output (PARTIALLY FIXED)
Moved AI outside dialog. Nonce forces new dialog. But user reported 3rd tweet still reproduced 2nd tweet's output in one test. Debug line added showing input text + hash in dialog subtitle. May need further investigation.

### Other Open Items
- **Speed optimization** — Go Viral takes ~8 seconds. Could trim to ~4-5s by reducing max_tokens (400→250) and trimming duplicate rules from user prompt
- **New Ideas button** — intermittently broken in What's Hot dialog
- **Idea Bank "Use in Creator Studio"** — navigation fix deployed but not confirmed working
- **Background gradient** — 4 HTML mockups, Tyler hasn't picked
- **Command Center + Content Calendar** — specs discussed, not built
- **Performance Feedback Loop** — not discussed with Tyler
- **Site audit bugs** — My Stats follower "—", Algorithm Score truncation, etc.
- **Odds API** — key not yet obtained (free at the-odds-api.com)
- **R&D Council dashboard** — backend script exists, HQ dashboard page not built

---

## Technical Context

| Key | Value |
|-----|-------|
| App file | `/home/polfam/mount_polumbus_hq/app.py` (~6150 lines) |
| Deployment | polumbus-hq.streamlit.app (Streamlit Cloud) |
| Local | localhost:8501 (systemd mount-polumbus.service) |
| Phone | Tailscale 100.68.77.18:8501 |
| AI Model | claude-sonnet-4-6 (via OAuth direct API — confirmed working) |
| OAuth refresh | platform.claude.com/v1/oauth/token |
| Client ID | 9d1c250a-e61b-44d9-88ed-5944d1962f5e |
| Credentials | ~/.claude/.credentials.json |
| Gist ID | 15fb167bbbfdaa79d5ce11c266c3f652 |
| GITHUB_PAT | .streamlit/secrets.toml |
| Repo | github.com/polumbus/mount-polumbus-hq (private, branch: master) |
| API modules | ~/.openclaw/apis/ (espn.py, sleeper.py, perplexity.py, odds.py) |
| Perplexity key | ~/.openclaw/apis/.keys/perplexity.key |
| Current HEAD | `108104c` on master |

---

## Design System

- Background: `#0B0E14`, Card: `#161B22`, Teal: `#00F5FF`, Gold: `#C49E3C`
- Fonts: Bebas Neue (headers), Inter (UI), JetBrains Mono (stats)
- Teal for all labels (gold rejected site-wide, kept only in sidebar INTERACT)
- Gradient buttons: `linear-gradient(135deg, #00C8E8 → #00F5FF → #7DFAFF)`

---

## Tyler's Preferences

- Always create rollback points before changes
- Hates emojis in agent output — text quick codes only
- Wants concise responses — no agent reasoning shown
- All times MST, 12-hour format
- Never use Haiku — always Sonnet (quality loss not worth speed)
- Gets frustrated when changes break things or go in circles
- Wants speed above all in the app
- Widget pending-key pattern: store in `f"{key}_p"`, flush before render
- Must commit and push to deploy — Streamlit Cloud pulls from GitHub

---

## Rollback Points

| Tag | Commit | What It Covers |
|-----|--------|----------------|
| `rollback-before-format-patterns` | `cbda90a` | Before format pattern analysis |
| `rollback-before-format-patterns-v2` | `cbda90a` | Before format patterns + Go Viral |

---

## Quick Reference Commands

```bash
# Restart HQ
systemctl --user restart mount-polumbus

# Restart OpenClaw gateway
systemctl --user restart openclaw-gateway

# Push HQ changes
cd /home/polfam/mount_polumbus_hq && git add app.py && git commit -m "msg" && git push

# Test OAuth API
python3 -c "from app import _call_claude_direct; print(_call_claude_direct('hello', '', 50))"

# Check Perplexity
python3 -c "from apis.perplexity import pplx; print(pplx.quick('Broncos record 2025'))"

# Check ESPN
python3 -c "from apis.espn import espn; print(espn.scores('nba'))"

# Check Sleeper
python3 -c "from apis.sleeper import sleeper; print(sleeper.trending('add')[:3])"

# View crons
crontab -l

# Force clear Streamlit cache (nuclear option)
rm -rf ~/.streamlit/cache /tmp/streamlit_cache
```

---

*Current HEAD: `108104c` on master*
*Working directory: `/home/polfam/mount_polumbus_hq/`*
*App file: `app.py` (single file, all pages)*
