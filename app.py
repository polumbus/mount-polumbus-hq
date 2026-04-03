import streamlit as st
import subprocess
import json
import re
import os
import time
import uuid
import hashlib
import concurrent.futures
import requests
import tomli
import urllib.error
from datetime import datetime, timedelta, date
from pathlib import Path
from apis import (get_sports_context, pplx_fact_check, pplx_research, pplx_available,
                  get_espn_headlines_for_inspo, get_sleeper_trending_for_inspo, espn_scores,
                  odds_available, odds_format_block,
                  get_google_trends, get_reddit_trending, get_newsapi_headlines,
                  get_coingecko_trending)
from config import (TYLER_HANDLE, TYLER_CONTEXT, AMPLIFIER_AVATAR_URL, AMPLIFIER_IMG,
                    _VOICE_LABELS, _FORMAT_GUIDES, _WHATS_HOT_VOICE_GUIDE)
from chatgpt_oauth import call_chatgpt_oauth
from anthropic_circuit import (
    DEFAULT_UNAVAILABLE_COOLDOWN,
    block_for as anthropic_block_for,
    get_state as anthropic_get_state,
    is_blocked as anthropic_is_blocked,
    mark_available as anthropic_mark_available,
    mark_rate_limited as anthropic_mark_rate_limited,
    parse_retry_after as anthropic_parse_retry_after,
)

# ─── Page Config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Post Ascend",
    page_icon="mountain",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Hide everything during rerun; revealed at end of script after all content is ready.
# Prevents sidebar flash + stale login form showing during login→app transition.
st.markdown("""<style>
[data-testid="stSidebar"]{opacity:0;pointer-events:none}
.stApp [data-testid="stAppViewContainer"]{opacity:0}
</style>""", unsafe_allow_html=True)

# ─── Constants ──────────────────────────────────────────────────────────────
CLAUDE_CLI = "/home/polfam/.npm-global/bin/claude"
XURL = "/home/linuxbrew/.linuxbrew/bin/xurl"
DATA_DIR = Path(os.path.expanduser("~/.openclaw/workspace-omaha/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
STATIC_DIR = Path(__file__).resolve().parent / "static"

try:
    TWITTER_API_IO_KEY = st.secrets["TWITTER_API_IO_KEY"]
except Exception:
    SECRETS_PATH = "/home/polfam/.openclaw/workspace-redzone/.streamlit/secrets.toml"
    try:
        with open(SECRETS_PATH, "rb") as f:
            _secrets = tomli.load(f)
        TWITTER_API_IO_KEY = _secrets.get("TWITTER_API_IO_KEY", "")
    except Exception:
        TWITTER_API_IO_KEY = ""

# TYLER_HANDLE, TYLER_CONTEXT, _WHATS_HOT_VOICE_GUIDE -> config.py

# ─── Tyler's Voice System Prompt ─────────────────────────────────────────────
# ─── Styles (extracted to styles.py) ──────────────────────────────────────────
from styles import inject_css
inject_css()



# ─── Helpers ────────────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def _load_local_video_bytes(filename: str) -> bytes | None:
    video_path = STATIC_DIR / filename
    if not video_path.exists():
        return None
    return video_path.read_bytes()


def _analyze_voice_fingerprint(tweets: list) -> dict:
    """Analyze a user's tweets to build a voice fingerprint — language level,
    tone markers, sentence patterns. Used to make AI output actually sound
    like the user, not a sanitized version of them."""
    if not tweets:
        return {}

    originals = [t.get("text", "") for t in tweets
                 if not t.get("text", "").startswith("RT ") and len(t.get("text", "")) > 20]
    if not originals:
        return {}

    all_text = " ".join(originals).lower()
    total = len(originals)

    # Profanity / strong language detection
    _profanity = ["fuck", "shit", "damn", "hell", "ass ", "bitch", "crap", "piss", "bastard", "bullshit"]
    _strong_opinion = ["idiots", "moron", "clown", "joke", "pathetic", "garbage", "trash", "scam", "fraud", "corrupt", "pansy", "coward"]
    _casual = ["lol", "lmao", "bruh", "bro ", "dude", "ngl", "tbh", "imo", "fr ", "smh", "wtf"]

    profanity_count = sum(1 for t in originals if any(w in t.lower() for w in _profanity))
    strong_count = sum(1 for t in originals if any(w in t.lower() for w in _strong_opinion))
    casual_count = sum(1 for t in originals if any(w in t.lower() for w in _casual))

    profanity_pct = round(profanity_count / total * 100)
    strong_pct = round(strong_count / total * 100)
    casual_pct = round(casual_count / total * 100)

    # Determine language level
    if profanity_pct >= 10:
        lang_level = "raw"  # regularly uses profanity
    elif profanity_pct >= 3 or strong_pct >= 15:
        lang_level = "unfiltered"  # occasional profanity, frequent strong opinions
    elif strong_pct >= 5 or casual_pct >= 15:
        lang_level = "blunt"  # strong opinions, casual tone
    else:
        lang_level = "clean"  # professional, no profanity

    # Detect tone patterns
    question_pct = round(sum(1 for t in originals if "?" in t) / total * 100)
    exclaim_pct = round(sum(1 for t in originals if "!" in t) / total * 100)
    avg_len = sum(len(t) for t in originals) // total

    return {
        "lang_level": lang_level,
        "profanity_pct": profanity_pct,
        "strong_opinion_pct": strong_pct,
        "casual_pct": casual_pct,
        "question_pct": question_pct,
        "exclaim_pct": exclaim_pct,
        "avg_length": avg_len,
    }


def build_user_context() -> str:
    """Return the base system prompt for the current user.
    Owner: returns TYLER_CONTEXT (unchanged).
    Guest: builds a generic creator context from their profile + tweet data,
    including their actual language level and tone."""
    if not is_guest():
        return TYLER_CONTEXT

    profile = load_json("profile.json", {})
    topics = load_json("topics.json", {})
    handle = profile.get("handle", get_current_handle())
    name = profile.get("name", handle)
    bio = profile.get("bio", "")
    followers = profile.get("followers", 0)
    niche = topics.get("niche", "General")
    topic_list = topics.get("topics", [])
    topics_str = ", ".join(topic_list) if topic_list else niche

    # Analyze voice fingerprint from tweet history
    tweets = load_json("tweet_history.json", [])
    vfp = _analyze_voice_fingerprint(tweets)

    # Build language level instruction
    lang = vfp.get("lang_level", "clean")
    if lang == "raw":
        lang_instruction = f"""- @{handle} uses raw, unfiltered language including profanity. This is CENTRAL to their voice.
- You MUST match this language level. Sanitizing their voice is a failure. If they say "fuck" you say "fuck."
- Do NOT tone down, soften, or clean up the language. Write exactly how they write."""
    elif lang == "unfiltered":
        lang_instruction = f"""- @{handle} is blunt and uses strong language. Occasional profanity is part of the voice.
- Do NOT sanitize or soften. If the moment calls for strong language, use it. This person does not hedge."""
    elif lang == "blunt":
        lang_instruction = f"""- @{handle} is direct and opinionated. No corporate polish, no diplomatic hedging.
- Strong opinions stated plainly. Doesn't sugarcoat."""
    else:
        lang_instruction = f"""- @{handle} keeps it professional but direct. No corporate fluff."""

    # Tone details
    tone_notes = []
    if vfp.get("question_pct", 0) > 25:
        tone_notes.append(f"- Uses questions frequently ({vfp['question_pct']}% of tweets) — rhetorical questions are a signature")
    if vfp.get("casual_pct", 0) > 10:
        tone_notes.append("- Casual/internet-speak tone (lol, bruh, ngl, etc.) — keep it conversational")
    if vfp.get("exclaim_pct", 0) > 20:
        tone_notes.append("- High energy — exclamation marks are part of the voice")
    tone_block = "\n".join(tone_notes)

    return f"""You are a content assistant for @{handle} ({name}) — a content creator focused on {niche.lower()}.

Profile:
- {followers:,} followers on X (@{handle})
- Niche: {niche}
- Key topics: {topics_str}
{f'- Bio: {bio}' if bio else ''}

Voice on X — CRITICAL (read their actual tweets below and MATCH their exact tone):
{lang_instruction}
- Short punchy sentences. Never sound like a press release or corporate account.
- Write in first person as @{handle}
- The tweets below show EXACTLY how this person writes. Match that energy, vocabulary, and attitude.
{tone_block}

Format rules:
- Keep tweets under 280 characters. Under 200 when possible for max punch.
- No hashtags unless specifically requested
- No emojis in output. Write plain text only.

VOICE MATCHING IS THE #1 PRIORITY. A tweet that sounds like @{handle} actually wrote it is always better than a "well-crafted" tweet that sounds like an AI."""


@st.cache_data(ttl=3600)
def get_voice_context():
    """Build voice context from actual tweet history (default voice only)."""
    tweets = load_json("tweet_history.json", [])
    _base = build_user_context()
    if not tweets:
        return _base

    # Get top 15 tweets by engagement as voice examples
    top = sorted(tweets, key=lambda t: t.get("likeCount", 0) + t.get("retweetCount", 0) * 3, reverse=True)[:15]
    examples = "\n".join([f"- {t.get('text', '')}" for t in top if not t.get("text", "").startswith("RT ")])

    _label = "YOUR" if is_guest() else "TYLER'S"
    return _base + f"""

{_label} ACTUAL TOP-PERFORMING TWEETS (use these as voice/style reference):
{examples}

Match this exact voice, tone, sentence structure, and style in everything you write.

Note: Format-specific rules (character limits, structure, thread formatting, article layout) will be provided separately. Follow those format rules for structure while maintaining this voice."""


def get_system_for_voice(voice_name: str, voice_mod: str) -> str:
    """Return the right system prompt for the selected voice mode.

    For Default: uses user's actual top-tweet examples (anchors to natural style).
    For Critical/Hype/Sarcastic: uses user's background + mode-specific rules.
    Owner gets Tyler-specific examples. Guests get universal rules only
    (their own tweet examples are injected via patterns context).
    """
    _base = build_user_context()
    _handle = get_current_handle()
    _is_g = is_guest()

    if voice_name == "Default":
        return get_voice_context()

    # Voice mode rules — universal structure guidance
    # Owner gets Tyler's sports examples. Guests get their own top tweets as examples.
    if _is_g:
        # Pull guest's top tweets as voice examples
        _pp = analyze_personal_patterns()
        _guest_top = _pp.get("top_examples", [])[:3] if _pp else []
        if _guest_top:
            _guest_ex_block = "YOUR TOP-PERFORMING TWEETS (use as voice/energy reference):\n" + "\n".join([f'- "{ex["text"][:200]}"' for ex in _guest_top]) + "\n"
        else:
            _guest_ex_block = ""
        _owner_critical_examples = _guest_ex_block
        _owner_homer_examples = _guest_ex_block
        _owner_sarcastic_examples = _guest_ex_block
    else:
        _owner_critical_examples = """EXAMPLES (copy this exact energy):
- "We passed on 52% of third downs last year and went 8-9. Meanwhile Kansas City ran on 3rd-and-short 74% of the time and won the Super Bowl. That gap is a choice. Who owns it?"
- "The Broncos have had 5 different offensive coordinators in 8 years. And we keep wondering why the offense looks confused. That's on the front office. Connect the dots."
- "Bo Nix threw for 3,000 yards last season. Good. But 18 of those touchdowns came against bottom-10 defenses. Payton needs to answer for that schedule construction."
"""
        _owner_homer_examples = """EXAMPLES (copy this exact energy):
- "Jokic dropped 30, 12, and 10 last night. On a Tuesday. The team drawing Denver in round 2 just changed their entire defensive game plan."
- "Bo Nix's third down completion rate jumped 12% in the second half. Every defensive coordinator in the AFC pulled up that film tonight."
- "MacKinnon and Makar both locked in at the same time in April for the first time in three years. The rest of the West is recalculating everything."
"""
        _owner_sarcastic_examples = """EXAMPLES (copy this exact energy):
- "Turns out the Patriots offense doesn't suck because of a snow storm."
- "That cornerback needs to call someone he trusts right now. Not about football."
- "Starting to feel like Bo Nix really should have played with a broken ankle."
- "Bold of Skip to finally come out and say it."
"""

    voice_blocks = {
        "Critical": f"""CRITICAL VOICE — DIRECT MODE:
{_owner_critical_examples}
CRITICAL VOICE RULES:
- Always open with a SPECIFIC number, stat, or named failure — never a vague complaint
- Identify the structural cause — not "they need to be better"
- End by naming the specific person or entity who owns it. Period. Full stop. Never ellipsis.
- Authority IMPLIED through specificity — never stated
- Tone: disappointed not angry. Calm, credible, constructive.""",

        "Hype": f"""HOMER VOICE — HYPE MODE:
{_owner_homer_examples}
HOMER VOICE RULES:
- Ground optimism in something SPECIFIC — a person, a stat, a moment
- End by showing the OPPOSITION'S reaction — their worry is the proof
- Authority IMPLIED through specificity — never stated
- Tone: infectious, grounded confidence. Earned optimism, not blind cheerleading.""",

        "Sarcastic": f"""SARCASTIC VOICE — DRY HUMOR MODE:
{_owner_sarcastic_examples}
SARCASTIC VOICE RULES:
- Two modes: Cultural Leap (positive moments) or Implied Real Story (negative moments)
- Cultural Leap: Jump to a completely unrelated world. Specific person in a specific human situation. Never explain.
- Implied Real Story: State the surface story as if neutral. Imply the real story underneath. Never state it directly.
- Never use generic openers like "Oh interesting" "Sure" "Cool" "Oh great"
- Drop it and walk away. Never explain the joke.""",
    }

    block = voice_blocks.get(voice_name, "")
    if block:
        return _base + f"""

{block}

{voice_mod}

IMPORTANT: Write ONLY in the voice mode above. Do NOT fall back to the default voice."""

    # Custom account voice style
    custom_styles = load_json("voice_styles.json", [])
    for style in custom_styles:
        if style.get("name") == voice_name:
            s_handle = style.get("handle", "")
            summary = style.get("summary", "")
            s_tweets = style.get("tweets", [])
            tweet_block = "\n".join([f'- "{t}"' for t in s_tweets[:10]])
            return _base + f"""

You are writing AS @{_handle} but in the STYLE of @{s_handle}.

THEIR VOICE PROFILE:
{summary}

EXAMPLE TWEETS FROM @{s_handle} (match this energy, not your default voice):
{tweet_block}

STYLE RULES:
- Adopt @{s_handle}'s tone, rhythm, and formatting approach
- Keep @{_handle}'s authority and topic focus
- Write about @{_handle}'s topics in @{s_handle}'s voice
- Do NOT copy their exact tweets — channel the style

{voice_mod}

IMPORTANT: Write in @{s_handle}'s STYLE as described above."""

    return _base


@st.cache_data(ttl=3600)
def analyze_personal_patterns():
    """Analyze Tyler's tweet history to build personal scoring benchmarks. Cached per session."""
    if "_pp_cache" in st.session_state:
        return st.session_state["_pp_cache"]
    tweets = load_json("tweet_history.json", [])
    if len(tweets) < 20:
        return None

    # Filter: exclude RTs, @-replies, and URL tweets (different engagement dynamics)
    originals = [
        t for t in tweets
        if not t.get("text", "").startswith("RT ")
        and not t.get("text", "").startswith("@")
        and "http" not in t.get("text", "")
    ]
    if len(originals) < 10:
        return None

    # Field-safe getters — API returns likeCount or like_count depending on endpoint
    def _likes(t): return t.get("likeCount", t.get("like_count", 0))
    def _rts(t):   return t.get("retweetCount", t.get("retweet_count", 0))
    def _reps(t):  return t.get("replyCount", t.get("reply_count", 0))
    def _views(t): return t.get("viewCount", t.get("view_count", 0))

    # Engagement score: 70% raw (reach) + 30% rate (efficiency vs views)
    def _eng(t):
        raw = _likes(t) + _rts(t) * 3 + _reps(t) * 2
        rate_bonus = (raw / max(_views(t), 1)) * 10000
        return raw * 0.7 + rate_bonus * 0.3

    for t in originals:
        t["_eng"] = _eng(t)

    sorted_tweets = sorted(originals, key=lambda t: t["_eng"], reverse=True)
    n = len(sorted_tweets)
    top_n = max(5, n // 5)
    top_20pct  = sorted_tweets[:top_n]
    bottom_20pct = sorted_tweets[-top_n:]

    patterns = {}

    # Percentile-based char range — 25th to 75th of top performers (not min-max)
    top_lengths = sorted(len(t.get("text", "")) for t in top_20pct)
    p25 = top_lengths[max(0, len(top_lengths) // 4)]
    p75 = top_lengths[min(len(top_lengths) - 1, 3 * len(top_lengths) // 4)]
    patterns["optimal_char_range"] = (p25, p75)
    patterns["top_avg_chars"] = sum(top_lengths) // len(top_lengths)
    patterns["bottom_avg_chars"] = sum(len(t.get("text", "")) for t in bottom_20pct) // len(bottom_20pct)

    # Style patterns
    patterns["top_ellipsis_pct"]    = round(sum(1 for t in top_20pct if "..." in t.get("text", "")) / len(top_20pct) * 100)
    patterns["bottom_ellipsis_pct"] = round(sum(1 for t in bottom_20pct if "..." in t.get("text", "")) / len(bottom_20pct) * 100)
    patterns["top_question_pct"]    = round(sum(1 for t in top_20pct if "?" in t.get("text", "")) / len(top_20pct) * 100)
    patterns["bottom_question_pct"] = round(sum(1 for t in bottom_20pct if "?" in t.get("text", "")) / len(bottom_20pct) * 100)
    patterns["top_linebreaks_avg"]  = round(sum(t.get("text", "").count("\n") for t in top_20pct) / len(top_20pct), 1)

    # Engagement averages
    patterns["avg_likes"]  = sum(_likes(t)  for t in originals) // len(originals)
    patterns["avg_rts"]    = sum(_rts(t)    for t in originals) // len(originals)
    patterns["avg_replies"]= sum(_reps(t)   for t in originals) // len(originals)
    patterns["avg_views"]  = sum(_views(t)  for t in originals) // len(originals)

    # Format-split top examples so short formats get short examples, long gets long
    def _ex(t):
        return {"text": t.get("text", ""), "likes": _likes(t), "rts": _rts(t),
                "replies": _reps(t), "score": round(t["_eng"])}

    punchy_tops = [t for t in top_20pct if len(t.get("text", "")) <= 160]
    normal_tops = [t for t in top_20pct if 160 < len(t.get("text", "")) <= 260]
    long_tops   = [t for t in top_20pct if len(t.get("text", "")) > 260]
    patterns["top_examples"]        = [_ex(t) for t in top_20pct[:10]]
    patterns["top_examples_punchy"] = [_ex(t) for t in punchy_tops[:8]]
    patterns["top_examples_normal"] = [_ex(t) for t in normal_tops[:8]]
    patterns["top_examples_long"]   = [_ex(t) for t in long_tops[:8]]
    patterns["bottom_examples"]    = [{"text": t.get("text", ""), "likes": _likes(t)} for t in bottom_20pct[:5]]

    patterns["top_first_words"] = [
        t.get("text", "").split()[0].lower() for t in top_20pct if t.get("text", "").split()
    ]

    reply_sorted = sorted(originals, key=lambda t: _reps(t), reverse=True)[:5]
    patterns["top_reply_examples"] = [
        {"text": t.get("text", ""), "replies": _reps(t), "likes": _likes(t)} for t in reply_sorted
    ]

    st.session_state["_pp_cache"] = patterns
    return patterns


def build_patterns_context(patterns, fmt=""):
    """Build a string context block from personal patterns for prompt injection.
    fmt: pass the current format so examples are filtered to matching length."""
    if not patterns:
        return ""

    _long_fmt = fmt in ("Long Tweet", "Thread", "Article")

    if fmt == "Punchy Tweet" and patterns.get("top_examples_punchy"):
        top_pool = patterns["top_examples_punchy"]
        pool_label = "Top Performing PUNCHY Tweets ≤160 chars (model these — 2 sentences max)"
    elif fmt == "Normal Tweet" and patterns.get("top_examples_normal"):
        top_pool = patterns["top_examples_normal"]
        pool_label = "Top Performing NORMAL Tweets 161-260 chars (model these)"
    elif _long_fmt and patterns.get("top_examples_long"):
        top_pool = patterns["top_examples_long"]
        pool_label = "Top Performing LONG Tweets (model these)"
    else:
        top_pool = patterns.get("top_examples", [])
        pool_label = "Top Performing Tweets"

    top_ex    = "\n".join([f'  - "{ex["text"][:120]}"' for ex in top_pool[:2]])
    first_words = ", ".join(patterns.get("top_first_words", [])[:10])
    opt_range = patterns.get("optimal_char_range", (0, 280))

    _owner_label = "TYLER'S PERSONAL" if not is_guest() else "YOUR PERSONAL"
    _poss = "his" if not is_guest() else "your"
    _sig = f"- {patterns.get('top_ellipsis_pct', 0)}% use ellipsis (...) — {_poss} signature\n" if patterns.get("top_ellipsis_pct", 0) > 10 else ""
    return f"""
{_owner_label} TWEET BENCHMARKS (from actual tweet history):

Character Length:
- Sweet spot: {opt_range[0]}–{opt_range[1]} characters

Style Patterns (top performers):
{_sig}- {patterns.get("top_question_pct", 0)}% end with a question
- Average {patterns.get("top_linebreaks_avg", 0)} line breaks per top tweet
- Common first words: {first_words}

{pool_label}:
{top_ex}
"""


def auto_height(text, min_h=80, chars_per_line=55, line_h=22):
    """Calculate text_area height based on content length."""
    if not text:
        return min_h
    lines = text.count('\n') + 1
    char_lines = max(1, len(text) // chars_per_line)
    total = max(lines, char_lines) + 4  # +4 lines of padding so text isn't flush with bottom
    return max(min_h, total * line_h)


# _VOICE_LABELS -> config.py


def render_thread_cards(thread_text: str, voice: str = "Default") -> str:
    """Render thread text as X-native tweet cards HTML."""
    # Split on ---TWEET--- (raw) or ── TWEET N ── (display) variants
    tweets = re.split(r'(?:---TWEET---|[-\u2500-\u257F\u2014]+\s*TWEET\s*\d*\s*[-\u2500-\u257F\u2014]*)', thread_text, flags=re.IGNORECASE)
    tweets = [t.strip() for t in tweets if t.strip()]
    if not tweets:
        return ""
    total = len(tweets)
    voice_label = _VOICE_LABELS.get(voice, voice)
    cards = []
    for i, tweet in enumerate(tweets):
        # Separate text lines from [IMAGE: ...] lines
        text_parts = []
        image_tags = []
        for line in tweet.split('\n'):
            m = re.match(r'\[IMAGE:\s*(.+?)\]', line.strip(), re.IGNORECASE)
            if m:
                image_tags.append(m.group(1).strip())
            else:
                text_parts.append(line)
        tweet_body = '\n'.join(text_parts).strip()
        char_count = len(tweet_body)
        # Escape HTML in tweet body
        tweet_body_html = tweet_body.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        # Build image placeholders
        image_html = ""
        for img_desc in image_tags:
            image_html += f'''<div style="margin-top:10px;height:52px;border-radius:8px;background:rgba(255,255,255,0.04);border:0.5px dashed rgba(255,255,255,0.15);display:flex;align-items:center;justify-content:center;gap:8px;"><div style="width:16px;height:16px;background:rgba(255,255,255,0.1);border-radius:3px;flex-shrink:0;"></div><span style="font-size:11px;color:rgba(255,255,255,0.35);">{img_desc}</span></div>'''
        _display_name = st.session_state.get("user_display_name") or (f"@{get_current_handle()}" if get_current_handle() else "Post Ascend User")
        _initial_source = _display_name.replace("@", "").strip() or "PA"
        _initial_parts = [p for p in re.split(r'[\s._-]+', _initial_source) if p]
        _initials = "".join(p[0].upper() for p in _initial_parts[:2])[:2] or _initial_source[:2].upper() or "PA"
        card = f'''<div style="background:rgba(255,255,255,0.04);border:0.5px solid rgba(255,255,255,0.1);border-radius:10px;padding:14px 16px;margin-bottom:0;">
<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
<div style="width:32px;height:32px;border-radius:50%;background:#0C1630;border:1.5px solid #2DD4BF;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:600;color:#2DD4BF;flex-shrink:0;">{_initials}</div>
<div style="flex:1;"><div style="font-size:13px;font-weight:600;color:rgba(255,255,255,0.9);">{_display_name}</div><div style="font-size:11px;color:rgba(255,255,255,0.4);">@{get_current_handle()}</div></div>
<div style="font-size:10px;padding:3px 8px;border-radius:10px;background:rgba(45,212,191,0.12);color:#2DD4BF;border:0.5px solid rgba(45,212,191,0.25);white-space:nowrap;">{i+1}/{total} · {voice_label}</div>
</div>
<div style="font-size:13px;color:rgba(255,255,255,0.82);line-height:1.65;white-space:pre-wrap;">{tweet_body_html}</div>
{image_html}
<div style="display:flex;align-items:center;gap:16px;margin-top:10px;border-top:0.5px solid rgba(255,255,255,0.06);padding-top:8px;">
<span style="font-size:11px;color:rgba(255,255,255,0.3);">{char_count} chars</span>
</div>
</div>'''
        cards.append(card)
    connector = '<div style="text-align:center;color:rgba(255,255,255,0.12);font-size:18px;line-height:1;margin:2px 0 4px;">·</div>'
    return f'<div style="font-family:sans-serif;">{connector.join(cards)}</div>'


OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
OAUTH_TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
CREDENTIALS_PATH = os.path.expanduser("~/.claude/.credentials.json")


def _load_oauth_credentials():
    """Load OAuth credentials from local credentials file."""
    try:
        with open(CREDENTIALS_PATH) as f:
            creds = json.load(f)
        oauth = creds.get("claudeAiOauth", {})
        return oauth.get("accessToken"), oauth.get("refreshToken"), oauth.get("expiresAt", 0)
    except Exception:
        return None, None, 0


def _save_oauth_credentials(access_token, refresh_token, expires_at):
    """Persist refreshed tokens back to credentials file."""
    try:
        with open(CREDENTIALS_PATH) as f:
            creds = json.load(f)
        creds["claudeAiOauth"]["accessToken"] = access_token
        creds["claudeAiOauth"]["refreshToken"] = refresh_token
        creds["claudeAiOauth"]["expiresAt"] = expires_at
        with open(CREDENTIALS_PATH, "w") as f:
            json.dump(creds, f, indent=2)
    except Exception:
        pass


def _refresh_oauth_token(refresh_token):
    """Exchange refresh token for a fresh access token."""
    import urllib.request, urllib.parse
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": OAUTH_CLIENT_ID,
    }).encode()
    req = urllib.request.Request(
        OAUTH_TOKEN_URL,
        data=body,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "claude-code/2.1.78",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    return data["access_token"], data.get("refresh_token", refresh_token), data["expires_in"]


def _get_access_token_from_gist(gist_id: str, github_pat: str):
    """Read access token from GitHub Gist (synced every 7h by local cron)."""
    import urllib.request
    req = urllib.request.Request(
        f"https://api.github.com/gists/{gist_id}",
        headers={
            "Authorization": f"Bearer {github_pat}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    content = data["files"]["hq_token.json"]["content"]
    token_data = json.loads(content)
    return token_data["access_token"], token_data["expires_at"]


def _get_access_token():
    """Return a valid OAuth access token."""
    # Check session cache first
    cached = st.session_state.get("_oauth_access_token")
    cached_exp = st.session_state.get("_oauth_expires_at", 0)
    if cached and time.time() < cached_exp - 300:
        return cached

    # Try GitHub Gist (cloud deployment — synced every 7h by local cron)
    try:
        gist_id = st.secrets["GIST_ID"]
        github_pat = st.secrets["GITHUB_PAT"]
        access_token, expires_at = _get_access_token_from_gist(gist_id, github_pat)
        if time.time() < expires_at - 300:
            st.session_state["_oauth_access_token"] = access_token
            st.session_state["_oauth_expires_at"] = expires_at
            return access_token
        else:
            st.session_state["_oauth_last_error"] = "Gist token expired — local machine needs to sync"
            return None
    except Exception as e:
        pass  # Fall through to local credentials

    # Fall back to local credentials file (when running locally)
    local_access, local_refresh, local_exp = _load_oauth_credentials()
    if local_access and time.time() < (local_exp / 1000) - 300:
        st.session_state["_oauth_access_token"] = local_access
        st.session_state["_oauth_expires_at"] = local_exp / 1000
        return local_access

    # Try refreshing with local refresh token
    if local_refresh:
        try:
            access_token, new_refresh, expires_in = _refresh_oauth_token(local_refresh)
            expires_at = time.time() + expires_in
            st.session_state["_oauth_access_token"] = access_token
            st.session_state["_oauth_expires_at"] = expires_at
            _save_oauth_credentials(access_token, new_refresh, int(expires_at * 1000))
            return access_token
        except Exception as e:
            st.session_state["_oauth_last_error"] = f"Refresh failed: {e}"

    # Last resort: use CLAUDE_REFRESH_TOKEN from Streamlit secrets (Streamlit Cloud deployment)
    secrets_refresh = ""
    try:
        secrets_refresh = st.secrets.get("CLAUDE_REFRESH_TOKEN", "")
    except Exception:
        pass
    if secrets_refresh:
        try:
            access_token, new_refresh, expires_in = _refresh_oauth_token(secrets_refresh)
            expires_at = time.time() + expires_in
            st.session_state["_oauth_access_token"] = access_token
            st.session_state["_oauth_expires_at"] = expires_at
            return access_token
        except Exception as e:
            st.session_state["_oauth_last_error"] = f"Token refresh failed: {e}"

    st.session_state["_oauth_last_error"] = "No valid token source found"
    return None


def _call_claude_oauth(prompt: str, system: str, max_tokens: int) -> str:
    """Call Claude API directly using OAuth bearer token."""
    import urllib.request, urllib.error
    access_token = _get_access_token()
    if not access_token:
        err = st.session_state.get("_oauth_last_error", "unknown reason")
        return f"Error: No OAuth token — {err}"

    messages = [{"role": "user", "content": prompt}]
    body = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": max_tokens,
        "system": system,
        "messages": messages,
    }).encode()
    req = urllib.request.Request(
        ANTHROPIC_API_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {access_token}",
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "oauth-2025-04-20",
            "User-Agent": "claude-code/2.1.78",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return data["content"][0]["text"].strip()
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise Exception(f"HTTP {e.code}: {body}")


def _get_proxy_url() -> str:
    """Get proxy URL — from Gist (auto-updated by watchdog) or fall back to secret."""
    # Try Gist first (self-healing: watchdog updates this when tunnel URL changes)
    try:
        gist_id = st.secrets["GIST_ID"]
        github_pat = st.secrets["GITHUB_PAT"]
        import urllib.request as _ur
        req = _ur.Request(
            f"https://api.github.com/gists/{gist_id}",
            headers={"Authorization": f"Bearer {github_pat}", "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28"}
        )
        cached = st.session_state.get("_proxy_url_cached_at", 0)
        if time.time() - cached > 300:  # re-fetch every 5 min
            with _ur.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            url_file = data["files"].get("hq_proxy_url.json", {}).get("content")
            if url_file:
                proxy_url = json.loads(url_file)["proxy_url"]
                st.session_state["_proxy_url"] = proxy_url
                st.session_state["_proxy_url_cached_at"] = time.time()
        cached_url = st.session_state.get("_proxy_url")
        if cached_url:
            return cached_url
    except Exception:
        pass
    # Fall back to static secret
    return st.secrets.get("CLAUDE_PROXY_URL", "")


def _get_oauth_token() -> str:
    """Get valid OAuth access token from ~/.claude/.credentials.json, refreshing if expired."""
    import urllib.request
    creds_path = os.path.expanduser("~/.claude/.credentials.json")
    if not os.path.exists(creds_path):
        return ""
    try:
        with open(creds_path) as f:
            creds = json.load(f)
        # Credentials are nested under claudeAiOauth key
        oauth = creds.get("claudeAiOauth", creds)
        access_token = oauth.get("accessToken", "")
        expires_at = oauth.get("expiresAt", 0)
        # Refresh if expiring within 5 minutes
        if time.time() * 1000 > expires_at - 300000:
            refresh_token = oauth.get("refreshToken", "")
            if not refresh_token:
                return access_token
            body = json.dumps({
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": "9d1c250a-e61b-44d9-88ed-5944d1962f5e",
            }).encode()
            req = urllib.request.Request(
                "https://platform.claude.com/v1/oauth/token",
                data=body,
                headers={"Content-Type": "application/json", "User-Agent": "claude-code/2.1.78"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                new_creds = json.loads(resp.read())
            access_token = new_creds.get("access_token") or new_creds.get("accessToken", access_token)
            oauth.update(new_creds)
            creds["claudeAiOauth"] = oauth
            with open(creds_path, "w") as f:
                json.dump(creds, f, indent=2)
        return access_token
    except Exception:
        return ""


def _call_claude_direct(prompt: str, system: str, max_tokens: int, model: str = "claude-sonnet-4-6", _token: str = None) -> str:
    """Call Claude API directly via OAuth bearer token — fastest path, no subprocess."""
    import urllib.request
    import hashlib
    token = _token or _get_oauth_token() or _get_access_token()
    if not token:
        raise Exception("No OAuth token available")

    # Billing header required in system prompt for Sonnet/Opus access via OAuth
    _salt = "59cf53e54c78"
    _ver = "2.1.90"
    _chars = [prompt[p] if p < len(prompt) else "0" for p in [4, 7, 20]]
    _hash = hashlib.sha256((_salt + "".join(_chars) + _ver).encode()).hexdigest()[:3]
    billing_line = f"x-anthropic-billing-header: cc_version={_ver}.{_hash}; cc_entrypoint=claude-code; cch=00000;"

    system_array = [{"type": "text", "text": billing_line}]
    if system:
        system_array.append({"type": "text", "text": system, "cache_control": {"type": "ephemeral"}})

    body = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "system": system_array,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages?beta=true",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "claude-code-20250219,oauth-2025-04-20,interleaved-thinking-2025-05-14,context-management-2025-06-27,prompt-caching-scope-2026-01-05,advanced-tool-use-2025-11-20,effort-2025-11-24",
            "User-Agent": f"AnthropicCLI/{_ver}",
            "x-app": "cli",
            "anthropic-dangerous-direct-browser-access": "true",
            "x-stainless-lang": "js",
            "x-stainless-os": "Linux",
            "x-stainless-arch": "x64",
            "x-stainless-runtime": "node",
            "x-stainless-package-version": "0.74.0",
            "x-stainless-retry-count": "0",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    if "content" in data and data["content"]:
        return data["content"][0].get("text", "")
    raise Exception(f"API error: {data.get('error', data)}")


def _call_with_token(token: str, prompt: str, system: str, max_tokens: int, model: str = "claude-sonnet-4-6") -> str:
    """Thread-safe direct API call — token passed in, no session state access."""
    import urllib.request, hashlib as _hl
    _salt = "59cf53e54c78"
    _ver = "2.1.90"
    _chars = [prompt[p] if p < len(prompt) else "0" for p in [4, 7, 20]]
    _hash = _hl.sha256((_salt + "".join(_chars) + _ver).encode()).hexdigest()[:3]
    billing_line = f"x-anthropic-billing-header: cc_version={_ver}.{_hash}; cc_entrypoint=claude-code; cch=ece3b;"
    system_array = [{"type": "text", "text": billing_line}]
    if system:
        system_array.append({"type": "text", "text": system, "cache_control": {"type": "ephemeral"}})
    body = json.dumps({
        "model": model, "max_tokens": max_tokens,
        "system": system_array,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages?beta=true", data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "claude-code-20250219,oauth-2025-04-20,interleaved-thinking-2025-05-14,context-management-2025-06-27,prompt-caching-scope-2026-01-05,advanced-tool-use-2025-11-20,effort-2025-11-24",
            "User-Agent": f"AnthropicCLI/{_ver}", "x-app": "cli",
            "anthropic-dangerous-direct-browser-access": "true",
            "x-stainless-lang": "js", "x-stainless-os": "Linux",
            "x-stainless-arch": "x64", "x-stainless-runtime": "node",
            "x-stainless-package-version": "0.74.0", "x-stainless-retry-count": "0",
        }, method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    if "content" in data and data["content"]:
        return data["content"][0].get("text", "")
    raise Exception(f"API error: {data.get('error', data)}")


def _call_claude_proxy(prompt: str, system: str, max_tokens: int, model: str = "claude-sonnet-4-6") -> str:
    """Call local Claude proxy server (for Streamlit Cloud — uses CLI on Tyler's machine)."""
    import urllib.request, urllib.error
    proxy_url = _get_proxy_url()
    if not proxy_url:
        raise Exception("No proxy configured")
    try:
        proxy_key = st.secrets.get("CLAUDE_PROXY_KEY", "")
    except Exception:
        proxy_key = ""

    body = json.dumps({"prompt": prompt, "system": system, "max_tokens": max_tokens, "model": model}).encode()
    headers = {"Content-Type": "application/json", "ngrok-skip-browser-warning": "1"}
    if proxy_key:
        headers["X-Proxy-Key"] = proxy_key
    req = urllib.request.Request(f"{proxy_url.rstrip('/')}/call", data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    if "error" in data:
        raise Exception(data["error"])
    return data["text"]


def _post_tweet(text: str) -> tuple[bool, str]:
    """Post a new tweet via proxy or local xurl. Returns (success, error_msg)."""
    import urllib.request
    proxy_url = _get_proxy_url()
    if proxy_url:
        try:
            proxy_key = st.secrets.get("CLAUDE_PROXY_KEY", "")
        except Exception:
            proxy_key = ""
        body = json.dumps({"text": text}).encode()
        headers = {"Content-Type": "application/json", "ngrok-skip-browser-warning": "1"}
        if proxy_key:
            headers["X-Proxy-Key"] = proxy_key
        try:
            req = urllib.request.Request(f"{proxy_url.rstrip('/')}/tweet/post", data=body, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            if data.get("ok", False):
                return True, ""
            return False, data.get("error", "Proxy returned not ok")
        except urllib.request.HTTPError as e:
            _err = e.read().decode("utf-8", errors="replace")[:200]
            return False, f"Proxy HTTP {e.code}: {_err}"
        except Exception as e:
            return False, f"Proxy error: {e}"
    if os.path.exists(XURL):
        result = subprocess.run([XURL, "post", text], capture_output=True, text=True, timeout=8)
        if result.returncode == 0:
            return True, ""
        return False, result.stderr.strip() or result.stdout.strip() or "xurl failed"
    return False, "No proxy available and xurl not found"


def _proxy_tweet_action(action: str, tweet_id: str, text: str = "") -> bool:
    """Route like/reply through local proxy. Returns True on success."""
    import urllib.request, urllib.error
    proxy_url = _get_proxy_url()
    try:
        proxy_key = st.secrets.get("CLAUDE_PROXY_KEY", "")
    except Exception:
        proxy_key = ""
    body = json.dumps({"tweet_id": tweet_id, "text": text}).encode()
    headers = {"Content-Type": "application/json", "ngrok-skip-browser-warning": "1"}
    if proxy_key:
        headers["X-Proxy-Key"] = proxy_key
    try:
        req = urllib.request.Request(f"{proxy_url.rstrip('/')}/tweet/{action}", data=body, headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return data.get("ok", False)
    except Exception:
        # Fall back to local xurl if available
        if os.path.exists(XURL):
            cmd = [XURL, action, tweet_id] + ([text] if text else [])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
            return result.returncode == 0
        return False


def call_claude(prompt: str, system: str = None, max_tokens: int = 1500, model: str = "claude-sonnet-4-6") -> str:
    if system is None:
        system = get_voice_context()

    st.session_state["_ai_last_model"] = model

    # 1. Direct OAuth HTTP — fastest, no subprocess overhead
    if not anthropic_is_blocked():
        try:
            result = _call_claude_direct(prompt, system or "", max_tokens, model)
            anthropic_mark_available("streamlit_direct")
            st.session_state["_ai_last_route"] = "anthropic_direct"
            st.session_state["_ai_last_provider"] = "anthropic"
            st.session_state["_ai_last_source"] = "streamlit_direct"
            st.session_state["_ai_last_at"] = datetime.now().isoformat(timespec="seconds")
            _append_debug_event("ai_call", "ok", "anthropic_direct", {"model": model})
            return result
        except urllib.error.HTTPError as e:
            if e.code == 429:
                anthropic_mark_rate_limited(
                    anthropic_parse_retry_after(getattr(e, "headers", None)),
                    source="streamlit_direct",
                    error=f"HTTP {e.code}",
                )
                st.session_state["_ai_last_error"] = f"anthropic_direct HTTP {e.code}"
                _append_debug_event("ai_call", "error", f"anthropic_direct HTTP {e.code}", {"model": model})
        except Exception as e:
            if "Credit balance is too low" in str(e):
                anthropic_block_for(DEFAULT_UNAVAILABLE_COOLDOWN, source="streamlit_direct", error=str(e))
            st.session_state["_ai_last_error"] = f"anthropic_direct {e}"
            _append_debug_event("ai_call", "error", f"anthropic_direct {e}", {"model": model})

    # 2. Local CLI fallback
    if not anthropic_is_blocked() and os.path.exists(CLAUDE_CLI):
        try:
            clean_env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
            cmd = [CLAUDE_CLI, "-p", "--model", model]
            if system:
                cmd += ["--system-prompt", system]
            result = subprocess.run(
                cmd,
                input=prompt, capture_output=True, text=True, timeout=20, env=clean_env,
            )
            if result.returncode == 0 and result.stdout.strip():
                anthropic_mark_available("streamlit_cli")
                st.session_state["_ai_last_route"] = "anthropic_cli"
                st.session_state["_ai_last_provider"] = "anthropic"
                st.session_state["_ai_last_source"] = "streamlit_cli"
                st.session_state["_ai_last_at"] = datetime.now().isoformat(timespec="seconds")
                _append_debug_event("ai_call", "ok", "anthropic_cli", {"model": model})
                return result.stdout.strip()
            if "Credit balance is too low" in (result.stderr or ""):
                anthropic_block_for(DEFAULT_UNAVAILABLE_COOLDOWN, source="streamlit_cli", error=result.stderr.strip())
            if result.stderr:
                st.session_state["_ai_last_error"] = f"anthropic_cli {result.stderr.strip()}"
                _append_debug_event("ai_call", "error", f"anthropic_cli {result.stderr.strip()}", {"model": model})
        except Exception:
            pass

    # 3. Proxy server (Streamlit Cloud path — ngrok to Tyler's local machine)
    try:
        proxy_text = _call_claude_proxy(prompt, system or "", max_tokens, model)
        st.session_state["_ai_last_route"] = "proxy"
        st.session_state["_ai_last_provider"] = "proxy"
        st.session_state["_ai_last_source"] = "streamlit_proxy"
        st.session_state["_ai_last_at"] = datetime.now().isoformat(timespec="seconds")
        _append_debug_event("ai_call", "ok", "proxy", {"model": model})
        return proxy_text
    except Exception as e:
        st.session_state["_ai_last_error"] = f"proxy {e}"
        _append_debug_event("ai_call", "error", f"proxy {e}", {"model": model})
        pass

    # 4. ChatGPT OAuth fallback via local Codex login
    try:
        chatgpt_text = call_chatgpt_oauth(prompt, system or "")
        st.session_state["_ai_last_route"] = "chatgpt_oauth"
        st.session_state["_ai_last_provider"] = "chatgpt"
        st.session_state["_ai_last_source"] = "local_codex_oauth"
        st.session_state["_ai_last_at"] = datetime.now().isoformat(timespec="seconds")
        _append_debug_event("ai_call", "ok", "chatgpt_oauth", {"model": model})
        return chatgpt_text
    except Exception as e:
        st.session_state["_ai_last_error"] = f"chatgpt_oauth {e}"
        _append_debug_event("ai_call", "error", f"chatgpt_oauth {e}", {"model": model})
        pass

    return "AI unavailable — check Anthropic and ChatGPT credentials."


def _gist_headers():
    pat = st.secrets.get("GITHUB_PAT", "") or os.environ.get("HQ_GITHUB_PAT", "")
    return {"Authorization": f"Bearer {pat}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"}

def _load_bank_items(kind: str) -> list:
    if kind == "repurpose":
        local_name = "repurpose_queue.json"
        gist_name = "hq_repurpose.json"
    else:
        local_name = "inspiration_vault.json"
        gist_name = "hq_inspiration.json"
    if is_guest():
        return load_json(local_name, [])
    try:
        gist_id = st.secrets.get("GIST_ID", "15fb167bbbfdaa79d5ce11c266c3f652")
        resp = requests.get(f"https://api.github.com/gists/{gist_id}", headers=_gist_headers(), timeout=8)
        data = resp.json()
        if gist_name in data.get("files", {}):
            return json.loads(data["files"][gist_name]["content"])
    except Exception:
        pass
    return []


def _save_bank_items(kind: str, items: list):
    if kind == "repurpose":
        local_name = "repurpose_queue.json"
        gist_name = "hq_repurpose.json"
    else:
        local_name = "inspiration_vault.json"
        gist_name = "hq_inspiration.json"
    if is_guest():
        save_json(local_name, items)
        return
    try:
        gist_id = st.secrets.get("GIST_ID", "15fb167bbbfdaa79d5ce11c266c3f652")
        payload = json.dumps({"files": {gist_name: {"content": json.dumps(items, indent=2, default=str)}}})
        requests.patch(f"https://api.github.com/gists/{gist_id}", data=payload, headers=_gist_headers(), timeout=8)
    except Exception:
        pass


def load_inspiration_gist() -> list:
    return _load_bank_items("inspiration")

def save_inspiration_gist(items: list):
    _save_bank_items("inspiration", items)


def _load_actions_gist() -> dict:
    """Load liked/replied tweet IDs. Guests use local isolated storage; owner uses Gist."""
    _handle = get_current_handle()
    if st.session_state.get("_actions_cache_handle") == _handle and "_actions_cache" in st.session_state:
        return st.session_state["_actions_cache"]
    if is_guest():
        result = load_json("actions.json", {})
        result.setdefault("liked", [])
        result.setdefault("replied", [])
        st.session_state["_actions_cache"] = result
        st.session_state["_actions_cache_handle"] = _handle
        return result
    try:
        gist_id = st.secrets.get("GIST_ID", "15fb167bbbfdaa79d5ce11c266c3f652")
        resp = requests.get(f"https://api.github.com/gists/{gist_id}", headers=_gist_headers(), timeout=8)
        data = resp.json()
        content = data.get("files", {}).get("hq_actions.json", {}).get("content", "{}")
        result = json.loads(content)
    except Exception:
        result = {}
    result.setdefault("liked", [])
    result.setdefault("replied", [])
    st.session_state["_actions_cache"] = result
    st.session_state["_actions_cache_handle"] = _handle
    return result


def _save_actions_gist(actions: dict):
    """Persist liked/replied IDs. Guests use local isolated storage; owner uses Gist."""
    st.session_state["_actions_cache"] = actions
    st.session_state["_actions_cache_handle"] = get_current_handle()
    if is_guest():
        save_json("actions.json", actions)
        return
    try:
        gist_id = st.secrets.get("GIST_ID", "15fb167bbbfdaa79d5ce11c266c3f652")
        payload = json.dumps({"files": {"hq_actions.json": {"content": json.dumps(actions, indent=2)}}})
        requests.patch(f"https://api.github.com/gists/{gist_id}", data=payload, headers=_gist_headers(), timeout=5)
    except Exception:
        pass


def load_json(filename: str, default=None):
    path = get_data_dir() / filename
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return default if default is not None else []


def save_json(filename: str, data):
    path = get_data_dir() / filename
    path.write_text(json.dumps(data, indent=2, default=str))


def _get_engagement_lists_path():
    return get_data_dir() / 'engagement_lists.json'

_ENGAGEMENT_DEFAULTS = {
    'Broncos Reporters': {'list_id': '1294328608417177604'},
    'Nuggets':           {'list_id': '1755985316752642285'},
    'Morning Engagement':{'list_id': '2011987998699897046'},
    'Work':              {'list_id': '1182699241329721344'},
}

def load_engagement_lists() -> dict:
    _path = _get_engagement_lists_path()
    if _path.exists():
        try:
            loaded = json.loads(_path.read_text())
            # Guests: return their lists as-is, no Tyler defaults backfilled
            if is_guest():
                return loaded
            migrated = {}
            for k, v in loaded.items():
                if isinstance(v, str):
                    # Restore known list_id from defaults when migrating old handle-string format
                    migrated[k] = {'list_id': _ENGAGEMENT_DEFAULTS.get(k, {}).get('list_id', ''), 'legacy_handles': v}
                else:
                    entry = dict(v)
                    # Restore list_id from defaults if entry exists but list_id is empty
                    if not entry.get('list_id') and k in _ENGAGEMENT_DEFAULTS:
                        entry['list_id'] = _ENGAGEMENT_DEFAULTS[k]['list_id']
                    migrated[k] = entry
            for k, v in _ENGAGEMENT_DEFAULTS.items():
                if k not in migrated:
                    migrated[k] = dict(v)
            return migrated
        except Exception:
            pass
    # Guests with no file: empty lists (onboarding creates the file)
    if is_guest():
        return {}
    return {k: dict(v) for k, v in _ENGAGEMENT_DEFAULTS.items()}

def save_engagement_lists(lists: dict):
    _get_engagement_lists_path().write_text(json.dumps(lists, indent=2))


def fetch_tweets_from_list(list_id: str, count: int = 100) -> list:
    """Fetch recent tweets from a Twitter List via twitterapi.io."""
    if not TWITTER_API_IO_KEY or not list_id:
        return []
    # Strip full URL to bare numeric ID (e.g. https://x.com/i/lists/1234567890)
    if '/' in list_id:
        import re as _re
        _m = _re.search(r'(\d{10,})', list_id)
        list_id = _m.group(1) if _m else list_id
    try:
        resp = requests.get(
            "https://api.twitterapi.io/twitter/list/tweets_timeline",
            headers={"X-API-Key": TWITTER_API_IO_KEY},
            params={"listId": list_id},
            timeout=8,
        )
        if resp.status_code == 200:
            return resp.json().get("tweets", [])
    except Exception:
        pass
    return []


def fetch_tweets(query: str, count: int = 50) -> list:
    if not TWITTER_API_IO_KEY:
        return []
    try:
        resp = requests.get(
            "https://api.twitterapi.io/twitter/tweet/advanced_search",
            headers={"X-API-Key": TWITTER_API_IO_KEY},
            params={"query": query, "queryType": "Latest", "count": min(count, 100), "cursor": ""},
            timeout=8,
        )
        if resp.status_code == 200:
            data = resp.json()
            tweets = data.get("tweets", [])
            return tweets[:count]
    except Exception:
        pass
    return []


def fetch_user_info(handle: str) -> dict:
    if not TWITTER_API_IO_KEY:
        return {}
    try:
        resp = requests.get(
            "https://api.twitterapi.io/twitter/user/info",
            headers={"X-API-Key": TWITTER_API_IO_KEY},
            params={"userName": handle},
            timeout=8,
        )
        if resp.status_code == 200:
            return resp.json().get("data", {})
    except Exception:
        pass
    return {}


def render_tweet_card(tweet: dict, idx: int = 0):
    text = tweet.get("text", "")
    likes = tweet.get("likeCount", 0)
    rts = tweet.get("retweetCount", 0)
    replies = tweet.get("replyCount", 0)
    views = tweet.get("viewCount", 0)
    created = tweet.get("createdAt", "")
    author = tweet.get("author", {})
    name = author.get("name", "") if author else ""
    handle = author.get("userName", "") if author else ""
    st.markdown(f"""
    <div class="tweet-card">
        <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
            <span class="tweet-num">{name} @{handle}</span>
            <span style="font-size:11px; color:#444466;">{created[:16] if created else ''}</span>
        </div>
        <div style="color:#d8d8e8; font-size:14px; margin-bottom:10px; line-height:1.6;">{text}</div>
        <div style="display:flex; gap:20px; font-size:12px; color:#666688;">
            <span>Likes: {likes:,}</span>
            <span>RTs: {rts:,}</span>
            <span>Replies: {replies:,}</span>
            <span>Views: {views:,}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ─── Authentication Gate ───────────────────────────────────────────────────
import hashlib as _hl

try:
    _OWNER_PW = st.secrets["OWNER_PASSWORD"]
except (KeyError, FileNotFoundError):
    _OWNER_PW = ""

_ACCOUNTS_PATH = Path(os.path.expanduser("~/.openclaw/guests/accounts.json"))

def _load_accounts() -> dict:
    if _ACCOUNTS_PATH.exists():
        try:
            return json.loads(_ACCOUNTS_PATH.read_text())
        except Exception:
            pass
    return {}

def _save_accounts(data: dict):
    _ACCOUNTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ACCOUNTS_PATH.write_text(json.dumps(data, indent=2, default=str))

def _hash_pw(username: str, password: str) -> str:
    return _hl.sha256(f"mp_{username}_{password}".encode()).hexdigest()


_OWNER_TOKEN = _hl.sha256(f"mp_owner_{_OWNER_PW}".encode()).hexdigest()[:16] if _OWNER_PW else ""

if "auth_role" not in st.session_state:
    st.session_state["auth_role"] = None

# Restore session: 1) query params, 2) cookie (via st.context.cookies)
if not st.session_state["auth_role"]:
    _tok = st.query_params.get("token", "")
    _tok_user = st.query_params.get("user", "")
    if _tok and _tok == _OWNER_TOKEN:
        st.session_state["auth_role"] = "owner"
    elif _tok and _tok_user:
        _accts = _load_accounts()
        if _tok_user in _accts and _accts[_tok_user].get("token") == _tok:
            st.session_state["auth_role"] = "guest"
            st.session_state["auth_username"] = _tok_user
            _gid = _accts[_tok_user].get("guest_id", "")
            if _gid:
                st.query_params["guest_id"] = _gid

    # Fallback: read cookie directly (survives browser close, no JS needed)
    if not st.session_state["auth_role"]:
        try:
            _cookie_raw = st.context.cookies.get("mp_auth", "")
            if _cookie_raw:
                _cookie_data = json.loads(_auth_urlp.unquote(_cookie_raw))
                _c_role = _cookie_data.get("role", "")
                _c_token = _cookie_data.get("token", "")
                _c_user = _cookie_data.get("user", "")
                if _c_role == "owner" and _c_token == _OWNER_TOKEN:
                    st.session_state["auth_role"] = "owner"
                    st.query_params["token"] = _c_token
                elif _c_role == "guest" and _c_user:
                    _accts = _load_accounts()
                    if _c_user in _accts and _accts[_c_user].get("token") == _c_token:
                        st.session_state["auth_role"] = "guest"
                        st.session_state["auth_username"] = _c_user
                        st.query_params["token"] = _c_token
                        st.query_params["user"] = _c_user
                        _gid = _accts[_c_user].get("guest_id", "")
                        if _gid:
                            st.query_params["guest_id"] = _gid
        except Exception:
            pass

if not st.session_state["auth_role"]:
    st.markdown("""<style>
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="stToolbar"] { display: none !important; }
    .stApp [data-testid="stAppViewContainer"] { opacity: 1 !important; }
    </style>""", unsafe_allow_html=True)
    st.markdown("""<div style="display:flex;justify-content:center;align-items:center;min-height:50vh;">
    <div style="text-align:center;max-width:360px;">
    <div style="margin:0 auto 16px;">
      <svg width="80" height="70" viewBox="0 0 100 88" fill="none">
        <polygon points="18,82 42,40 50,54 30,82" fill="#2DD4BF"/>
        <polygon points="42,40 50,54 58,40" fill="#0D1E36"/>
        <polygon points="58,40 70,82 50,54 82,82" fill="#2DD4BF" opacity="0.75"/>
        <polygon points="42,40 50,26 58,40" fill="#C49E3C"/>
      </svg>
    </div>
    <div style="font-family:'Bebas Neue',sans-serif;font-size:36px;color:#2DD4BF;letter-spacing:3px;margin-bottom:4px;">POST ASCEND</div>
    <div style="font-size:11px;color:#4a5160;letter-spacing:2px;text-transform:uppercase;margin-bottom:40px;">AI-POWERED CONTENT CREATION</div>
    </div></div>""", unsafe_allow_html=True)

    _auth_tab = st.radio("", ["Sign In", "Create Account"], horizontal=True, key="auth_tab", label_visibility="collapsed")

    if _auth_tab == "Sign In":
        _login_user = st.text_input("Username", key="login_user", placeholder="Username", label_visibility="collapsed")
        _login_pw = st.text_input("Password", type="password", key="login_pw", placeholder="Password", label_visibility="collapsed")
        if st.button("Sign In", type="primary", use_container_width=True, key="btn_signin"):
            if not _login_user or not _login_pw:
                st.error("Enter both username and password.")
            elif _login_user.lower().strip() == "owner" and _OWNER_PW and _login_pw == _OWNER_PW:
                st.session_state["auth_role"] = "owner"
                st.query_params["token"] = _OWNER_TOKEN
                st.rerun()
            else:
                _accts = _load_accounts()
                _lu = _login_user.lower().strip()
                if _lu in _accts and _accts[_lu]["password_hash"] == _hash_pw(_lu, _login_pw):
                    _token = _hl.sha256(f"mp_guest_{_lu}_{_login_pw}".encode()).hexdigest()[:16]
                    _accts[_lu]["token"] = _token
                    _accts[_lu]["last_login"] = datetime.now().isoformat()
                    _save_accounts(_accts)
                    st.session_state["auth_role"] = "guest"
                    st.session_state["auth_username"] = _lu
                    st.query_params["token"] = _token
                    st.query_params["user"] = _lu
                    _gid = _accts[_lu].get("guest_id", "")
                    if _gid:
                        st.query_params["guest_id"] = _gid
                    st.rerun()
                else:
                    st.error("Invalid username or password.")

    else:  # Create Account
        _new_user = st.text_input("Choose a username", key="signup_user", placeholder="Username (letters, numbers, underscores)", label_visibility="collapsed")
        _new_pw = st.text_input("Choose a password", type="password", key="signup_pw", placeholder="Password (6+ characters)", label_visibility="collapsed")
        _new_pw2 = st.text_input("Confirm password", type="password", key="signup_pw2", placeholder="Confirm password", label_visibility="collapsed")
        if st.button("Create Account", type="primary", use_container_width=True, key="btn_signup"):
            import re as _re_signup
            _nu = (_new_user or "").lower().strip()
            if not _nu or not _new_pw:
                st.error("Fill in all fields.")
            elif not _re_signup.match(r'^[a-z0-9_]{3,20}$', _nu):
                st.error("Username must be 3-20 characters: letters, numbers, underscores only.")
            elif _nu == "owner":
                st.error("That username is reserved.")
            elif _new_pw != _new_pw2:
                st.error("Passwords don't match.")
            elif len(_new_pw) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                _accts = _load_accounts()
                if _nu in _accts:
                    st.error("Username already taken. Try another.")
                else:
                    _token = _hl.sha256(f"mp_guest_{_nu}_{_new_pw}".encode()).hexdigest()[:16]
                    _accts[_nu] = {
                        "password_hash": _hash_pw(_nu, _new_pw),
                        "token": _token,
                        "created_at": datetime.now().isoformat(),
                        "guest_id": "",
                    }
                    _save_accounts(_accts)
                    st.session_state["auth_role"] = "guest"
                    st.session_state["auth_username"] = _nu
                    st.query_params["token"] = _token
                    st.query_params["user"] = _nu
                    st.rerun()
    st.stop()



def is_guest() -> bool:
    """Returns True if current user is a guest (beta tester)."""
    return st.session_state.get("auth_role") == "guest"


def is_owner() -> bool:
    """Returns True if current user is the owner account."""
    return st.session_state.get("auth_role") == "owner"


def get_current_handle() -> str:
    """Returns the Twitter handle for the current user."""
    if is_guest():
        return st.session_state.get("user_handle", "")
    return TYLER_HANDLE


def get_data_dir() -> Path:
    """Returns the data directory for the current user. Guests get isolated storage."""
    if is_guest():
        handle = get_current_handle()
        if handle:
            guest_dir = Path(os.path.expanduser(f"~/.openclaw/guests/{handle}/data"))
            guest_dir.mkdir(parents=True, exist_ok=True)
            return guest_dir
    return DATA_DIR


# ─── Guest Registry ───────────────────────────────────────────────────────
_GUEST_REGISTRY_PATH = Path(os.path.expanduser("~/.openclaw/guests/registry.json"))

def _load_guest_registry() -> dict:
    if _GUEST_REGISTRY_PATH.exists():
        try:
            return json.loads(_GUEST_REGISTRY_PATH.read_text())
        except Exception:
            pass
    return {}

def _save_guest_registry(data: dict):
    _GUEST_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _GUEST_REGISTRY_PATH.write_text(json.dumps(data, indent=2, default=str))


# ─── Guest Onboarding (multi-step: connect → sync → analyze → unlock) ────
if is_guest():
    # Initialize onboarding state
    if "onboarding_step" not in st.session_state:
        st.session_state["onboarding_step"] = "check_registry"
    if "onboarding_complete" not in st.session_state:
        st.session_state["onboarding_complete"] = False

    # --- Returning guest: restore from registry and check if data exists ---
    if st.session_state["onboarding_step"] == "check_registry":
        _reg = _load_guest_registry()
        _guest_id = st.query_params.get("guest_id", "")
        if _guest_id and _guest_id in _reg:
            _entry = _reg[_guest_id]
            st.session_state["user_handle"] = _entry["handle"]
            st.session_state["user_display_name"] = _entry.get("name", "")
            st.session_state["user_avatar"] = _entry.get("avatar", "")
            # Check if this returning guest already has all required data
            _guest_data = Path(os.path.expanduser(f"~/.openclaw/guests/{_entry['handle']}/data"))
            _has_history = (_guest_data / "tweet_history.json").exists()
            _has_benchmarks = (_guest_data / "benchmarks.json").exists()
            _has_topics = (_guest_data / "topics.json").exists()
            if _has_history and _has_benchmarks and _has_topics:
                st.session_state["onboarding_complete"] = True
                st.session_state["onboarding_step"] = "done"
            elif _has_history and _has_topics:
                st.session_state["onboarding_step"] = "analyzing"
            elif _has_topics:
                st.session_state["onboarding_step"] = "syncing"
            else:
                st.session_state["onboarding_step"] = "niche"
        else:
            st.session_state["onboarding_step"] = "connect"

    # --- Gate: block app access until onboarding is complete ---
    if not st.session_state["onboarding_complete"]:
        st.markdown("""<style>
        [data-testid="stSidebar"] { display: none !important; }
        [data-testid="stToolbar"] { display: none !important; }
        </style>""", unsafe_allow_html=True)

        _step = st.session_state["onboarding_step"]

        # ── Step 1a: Enter X Handle ──
        if _step == "connect":
            st.markdown("""<div style="display:flex;justify-content:center;align-items:center;min-height:50vh;">
            <div style="text-align:center;max-width:420px;">
            <div style="font-family:'Bebas Neue',sans-serif;font-size:28px;color:#2DD4BF;letter-spacing:2px;margin-bottom:4px;">STEP 1 OF 4</div>
            <div style="font-family:'Bebas Neue',sans-serif;font-size:22px;color:#E2E8F0;letter-spacing:1px;margin-bottom:8px;">CONNECT YOUR X ACCOUNT</div>
            <div style="font-size:12px;color:#6E7681;margin-bottom:30px;line-height:1.6;">
            Enter your X handle so we can pull your tweet history and personalize everything to your style.</div>
            </div></div>""", unsafe_allow_html=True)
            _handle_input = st.text_input("Your X handle", key="onboard_handle", placeholder="@yourhandle", label_visibility="collapsed")
            if _handle_input:
                _clean_handle = _handle_input.strip().lstrip("@")
                if st.button("Look Up Account", type="primary", use_container_width=True, key="onboard_connect"):
                    with st.spinner(f"Looking up @{_clean_handle}..."):
                        _user_data = fetch_user_info(_clean_handle)
                    if not _user_data or not _user_data.get("userName"):
                        st.error(f"Could not find @{_clean_handle}. Check the handle and try again.")
                    elif _user_data.get("protected"):
                        st.error("This account is private. We need a public account to pull your tweet history. Change your account to public in X settings, then try again.")
                    elif (_user_data.get("statusesCount") or 0) < 20:
                        _sc = _user_data.get("statusesCount", 0)
                        st.error(f"This account only has {_sc} posts. We need at least 20 to build your profile. Post more and come back!")
                    else:
                        # Passed all checks — store data and move to confirmation
                        st.session_state["_onboard_user_data"] = _user_data
                        st.session_state["onboarding_step"] = "confirm"
                        st.rerun()
            st.stop()

        # ── Step 1b: Confirm Identity ──
        elif _step == "confirm":
            _user_data = st.session_state.get("_onboard_user_data", {})
            _name = _user_data.get("name", "")
            _handle = _user_data.get("userName", "")
            _avatar = _user_data.get("profilePicture", "")
            _bio = _user_data.get("description", "")
            _followers = _user_data.get("followers", 0)
            _tweets = _user_data.get("statusesCount", 0)
            st.markdown(f"""<div style="display:flex;justify-content:center;align-items:center;min-height:40vh;">
            <div style="text-align:center;max-width:420px;">
            <div style="font-family:'Bebas Neue',sans-serif;font-size:28px;color:#2DD4BF;letter-spacing:2px;margin-bottom:4px;">STEP 1 OF 4</div>
            <div style="font-family:'Bebas Neue',sans-serif;font-size:22px;color:#E2E8F0;letter-spacing:1px;margin-bottom:12px;">IS THIS YOU?</div>
            <div style="margin:20px auto;width:fit-content;">
                <img src="{_avatar}" style="width:80px;height:80px;border-radius:50%;border:2px solid #2DD4BF;" />
            </div>
            <div style="font-size:18px;color:#E2E8F0;font-weight:600;">{_name}</div>
            <div style="font-size:14px;color:#2DD4BF;margin-bottom:8px;">@{_handle}</div>
            <div style="font-size:12px;color:#8B949E;margin-bottom:12px;line-height:1.5;max-width:360px;margin-left:auto;margin-right:auto;">{_bio}</div>
            <div style="font-size:12px;color:#6E7681;">{_followers:,} followers &middot; {_tweets:,} posts</div>
            </div></div>""", unsafe_allow_html=True)
            _c1, _c2 = st.columns(2)
            with _c1:
                if st.button("That's not me", use_container_width=True, key="onboard_not_me"):
                    st.session_state.pop("_onboard_user_data", None)
                    st.session_state["onboarding_step"] = "connect"
                    st.rerun()
            with _c2:
                if st.button("Yes, continue", type="primary", use_container_width=True, key="onboard_confirm"):
                    _gid = _hl.sha256(f"guest_{_handle}".encode()).hexdigest()[:12]
                    st.session_state["user_handle"] = _handle
                    st.session_state["user_display_name"] = _name
                    st.session_state["user_avatar"] = _avatar
                    st.session_state["user_bio"] = _bio
                    st.session_state["user_followers"] = _followers
                    # Save to registry
                    _reg = _load_guest_registry()
                    _reg[_gid] = {
                        "handle": _handle,
                        "name": _name,
                        "avatar": _avatar,
                        "bio": _bio,
                        "followers": _followers,
                        "connected_at": datetime.now().isoformat(),
                    }
                    _save_guest_registry(_reg)
                    st.query_params["guest_id"] = _gid
                    # Link guest_id back to user account
                    _auth_user = st.session_state.get("auth_username", "")
                    if _auth_user:
                        _accts = _load_accounts()
                        if _auth_user in _accts:
                            _accts[_auth_user]["guest_id"] = _gid
                            _save_accounts(_accts)
                    # Save profile to guest data dir
                    _gdir = Path(os.path.expanduser(f"~/.openclaw/guests/{_handle}/data"))
                    _gdir.mkdir(parents=True, exist_ok=True)
                    (_gdir / "profile.json").write_text(json.dumps({
                        "handle": _handle,
                        "name": _name,
                        "avatar": _avatar,
                        "bio": _bio,
                        "followers": _followers,
                    }, indent=2))
                    st.session_state.pop("_onboard_user_data", None)
                    st.session_state["onboarding_step"] = "niche"
                    st.rerun()
            st.stop()

        # ── Step 2: Pick Your Niche ──
        elif _step == "niche":
            st.markdown("""<div style="display:flex;justify-content:center;align-items:center;min-height:40vh;">
            <div style="text-align:center;max-width:420px;">
            <div style="font-family:'Bebas Neue',sans-serif;font-size:28px;color:#2DD4BF;letter-spacing:2px;margin-bottom:4px;">STEP 2 OF 4</div>
            <div style="font-family:'Bebas Neue',sans-serif;font-size:22px;color:#E2E8F0;letter-spacing:1px;margin-bottom:8px;">WHAT DO YOU POST ABOUT?</div>
            <div style="font-size:12px;color:#6E7681;margin-bottom:30px;line-height:1.6;">
            This helps us find trending topics in your world and tailor content suggestions to your audience.</div>
            </div></div>""", unsafe_allow_html=True)
            _niche_options = ["Sports", "Tech", "Finance / Crypto", "Fitness / Health", "Entertainment", "Politics / News", "Business / Marketing", "Gaming", "Music", "Food / Lifestyle", "Other"]
            _selected_niche = st.selectbox("Your primary niche", _niche_options, key="onboard_niche_select", label_visibility="collapsed")
            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
            _topics_input = st.text_input("Your key topics (comma-separated, 3-5)", key="onboard_topics", placeholder="e.g. AI startups, SaaS growth, product launches", label_visibility="collapsed")
            st.markdown("<div style='font-size:11px;color:#6E7681;margin-top:-8px;margin-bottom:16px;'>These are the subjects you tweet about most. We use them to find relevant trending content.</div>", unsafe_allow_html=True)
            # Optional: add your own X lists
            with st.expander("Have X Lists you follow? (optional)", expanded=False):
                st.markdown("<div style='font-size:11px;color:#6E7681;margin-bottom:8px;'>Add list IDs from lists you follow on X. Find the ID in the URL: x.com/i/lists/<strong>1234567890</strong></div>", unsafe_allow_html=True)
                _custom_list_1_name = st.text_input("List name", placeholder="e.g. Tech Leaders", key="onboard_cl1_name", label_visibility="collapsed")
                _custom_list_1_id = st.text_input("List ID", placeholder="e.g. 1234567890", key="onboard_cl1_id", label_visibility="collapsed")
                _custom_list_2_name = st.text_input("List name 2", placeholder="e.g. AI Researchers", key="onboard_cl2_name", label_visibility="collapsed")
                _custom_list_2_id = st.text_input("List ID 2", placeholder="e.g. 9876543210", key="onboard_cl2_id", label_visibility="collapsed")
            if _selected_niche and _topics_input and _topics_input.strip():
                _topics_list = [t.strip() for t in _topics_input.split(",") if t.strip()]
                if len(_topics_list) < 2:
                    st.warning("Enter at least 2 topics separated by commas.")
                elif st.button("Continue", type="primary", use_container_width=True, key="onboard_niche_continue"):
                    _niche_data = {
                        "niche": _selected_niche,
                        "topics": _topics_list,
                        "set_at": datetime.now().isoformat(),
                    }
                    save_json("topics.json", _niche_data)
                    # Auto-generate search-based engagement feeds from topics
                    _auto_lists = {}
                    for _topic in _topics_list[:5]:
                        _auto_lists[_topic.title()] = {
                            "search_query": f"{_topic} min_faves:10 -filter:retweets",
                        }
                    # Add a general niche feed
                    _auto_lists[f"{_selected_niche} Feed"] = {
                        "search_query": f"{_selected_niche.split('/')[0].strip().lower()} -filter:retweets min_faves:20",
                    }
                    # Add any custom X lists the user provided
                    _cl1n = st.session_state.get("onboard_cl1_name", "").strip()
                    _cl1i = st.session_state.get("onboard_cl1_id", "").strip()
                    _cl2n = st.session_state.get("onboard_cl2_name", "").strip()
                    _cl2i = st.session_state.get("onboard_cl2_id", "").strip()
                    if _cl1n and _cl1i and _cl1i.isdigit():
                        _auto_lists[_cl1n] = {"list_id": _cl1i}
                    if _cl2n and _cl2i and _cl2i.isdigit():
                        _auto_lists[_cl2n] = {"list_id": _cl2i}
                    save_json("engagement_lists.json", _auto_lists)
                    st.session_state["onboarding_step"] = "syncing"
                    st.rerun()
            st.stop()

        # ── Step 3: Sync Tweet History ──
        elif _step == "syncing":
            _handle = st.session_state.get("user_handle", "")
            st.markdown(f"""<div style="display:flex;justify-content:center;align-items:center;min-height:40vh;">
            <div style="text-align:center;max-width:420px;">
            <div style="font-family:'Bebas Neue',sans-serif;font-size:28px;color:#2DD4BF;letter-spacing:2px;margin-bottom:4px;">STEP 3 OF 4</div>
            <div style="font-family:'Bebas Neue',sans-serif;font-size:22px;color:#E2E8F0;letter-spacing:1px;margin-bottom:8px;">LOADING YOUR POSTS</div>
            <div style="font-size:12px;color:#6E7681;margin-bottom:30px;line-height:1.6;">
            Pulling tweet history for <strong>@{_handle}</strong>. This may take a minute on first setup.</div>
            </div></div>""", unsafe_allow_html=True)
            _sync_bar = st.progress(0, text="Starting sync...")
            try:
                _sync_bar.progress(10, text="Fetching tweets...")
                _synced = sync_tweet_history(quick=False)
                _count = len(_synced)
                _sync_bar.progress(90, text=f"Loaded {_count} tweets")
                if _count < 20:
                    _sync_bar.progress(100, text="")
                    st.warning(f"Only found {_count} tweets. We need at least 20 original tweets to build your profile. Make sure your account is public and has enough posts.")
                    if st.button("Retry Sync", type="primary", key="onboard_retry_sync"):
                        st.session_state.pop("_tweet_history_cache", None)
                        st.session_state.pop("_pp_cache", None)
                        st.rerun()
                    st.stop()
                _sync_bar.progress(100, text=f"Synced {_count} tweets")
                import time as _t; _t.sleep(0.5)
                st.session_state["onboarding_step"] = "analyzing"
                st.rerun()
            except Exception as _e:
                _sync_bar.progress(100, text="")
                st.error(f"Sync failed: {_e}")
                if st.button("Retry", type="primary", key="onboard_retry_sync2"):
                    st.rerun()
                st.stop()

        # ── Step 3: Analyze Patterns & Build Benchmarks ──
        elif _step == "analyzing":
            _handle = st.session_state.get("user_handle", "")
            st.markdown(f"""<div style="display:flex;justify-content:center;align-items:center;min-height:40vh;">
            <div style="text-align:center;max-width:420px;">
            <div style="font-family:'Bebas Neue',sans-serif;font-size:28px;color:#2DD4BF;letter-spacing:2px;margin-bottom:4px;">STEP 4 OF 4</div>
            <div style="font-family:'Bebas Neue',sans-serif;font-size:22px;color:#E2E8F0;letter-spacing:1px;margin-bottom:8px;">ANALYZING YOUR VOICE</div>
            <div style="font-size:12px;color:#6E7681;margin-bottom:30px;line-height:1.6;">
            Building your personal benchmarks from @{_handle}'s top-performing posts.</div>
            </div></div>""", unsafe_allow_html=True)
            _a_bar = st.progress(0, text="Analyzing patterns...")
            try:
                # Clear cached patterns so they're rebuilt from this guest's data
                st.session_state.pop("_pp_cache", None)
                _a_bar.progress(30, text="Calculating engagement scores...")
                _pp = analyze_personal_patterns()
                if not _pp:
                    _a_bar.progress(100, text="")
                    st.warning("Not enough original tweets to analyze. Need at least 20 non-reply, non-RT tweets.")
                    if st.button("Retry", type="primary", key="onboard_retry_analyze"):
                        st.rerun()
                    st.stop()
                _a_bar.progress(60, text="Building benchmarks...")
                # Save benchmarks to guest data dir
                _benchmarks = {
                    "optimal_char_range": list(_pp.get("optimal_char_range", (80, 250))),
                    "top_avg_chars": _pp.get("top_avg_chars", 0),
                    "top_ellipsis_pct": _pp.get("top_ellipsis_pct", 0),
                    "top_question_pct": _pp.get("top_question_pct", 0),
                    "top_linebreaks_avg": _pp.get("top_linebreaks_avg", 0),
                    "avg_likes": _pp.get("avg_likes", 0),
                    "avg_rts": _pp.get("avg_rts", 0),
                    "avg_replies": _pp.get("avg_replies", 0),
                    "avg_views": _pp.get("avg_views", 0),
                    "top_first_words": _pp.get("top_first_words", []),
                    "top_examples": _pp.get("top_examples", []),
                    "top_examples_punchy": _pp.get("top_examples_punchy", []),
                    "top_examples_normal": _pp.get("top_examples_normal", []),
                    "top_examples_long": _pp.get("top_examples_long", []),
                    "analyzed_at": datetime.now().isoformat(),
                }
                save_json("benchmarks.json", _benchmarks)
                # Build and save voice fingerprint (language level, tone markers)
                _a_bar.progress(80, text="Fingerprinting voice...")
                _vfp = _analyze_voice_fingerprint(load_json("tweet_history.json", []))
                save_json("voice_fingerprint.json", _vfp)
                _a_bar.progress(100, text="Analysis complete")
                import time as _t; _t.sleep(0.5)
                # Mark complete
                st.session_state["onboarding_complete"] = True
                st.session_state["onboarding_step"] = "done"
                st.rerun()
            except Exception as _e:
                _a_bar.progress(100, text="")
                st.error(f"Analysis failed: {_e}")
                if st.button("Retry", type="primary", key="onboard_retry_analyze2"):
                    st.rerun()
                st.stop()

        # ── Fallback: unknown step ──
        else:
            st.session_state["onboarding_step"] = "connect"
            st.rerun()

        st.stop()  # Block app access until onboarding complete

# Set handle for owner (skip onboarding entirely)
if not is_guest():
    st.session_state["user_handle"] = TYLER_HANDLE
    st.session_state["onboarding_complete"] = True


# ─── Sidebar Navigation ────────────────────────────────────────────────────
# Read ?page= from URL on every render. Sidebar <a> links set ?page= which
# triggers a Streamlit rerun via WebSocket (not a full page reload).
# We also write the current page back to query_params so refresh works.
# Save auth token to session so it survives page nav (sidebar links drop query params)
if st.query_params.get("token"):
    st.session_state["_auth_token"] = st.query_params["token"]
if st.query_params.get("user"):
    st.session_state["auth_username"] = st.query_params["user"]

_qp_page = st.query_params.get("page", "")
if st.session_state.pop("_nav_override", False):
    pass  # current_page already set by nav button callback
elif _qp_page:
    st.session_state.current_page = _qp_page
else:
    st.session_state.current_page = "Creator Studio"
# Sync URL bar with current page so refresh preserves it
# Only sync if a page param already exists (avoid triggering rerun on fresh load)
if _qp_page and _qp_page != st.session_state.current_page:
    st.query_params["page"] = st.session_state.current_page
# Re-inject auth token + username into URL so refresh preserves login
if st.session_state.get("_auth_token") and not st.query_params.get("token"):
    st.query_params["token"] = st.session_state["_auth_token"]
if st.session_state.get("auth_username") and not st.query_params.get("user"):
    st.query_params["user"] = st.session_state["auth_username"]

_cur_pg = st.session_state.current_page

def _act(name):
    return "active" if _cur_pg == name else ""

# Token prefix for sidebar links — ensures auth survives page navigation
_tok_user_part = f"user={st.session_state.get('auth_username', '')}&" if st.session_state.get("auth_username") else ""
_tok_qp = f"token={st.session_state.get('_auth_token', '')}&{_tok_user_part}" if st.session_state.get("_auth_token") else ""
_owner_debug_zone = ""
_owner_signals_icon = ""
_owner_signals_panel = ""
_nav_pages = ["Creator Studio", "Raw Thoughts", "Content Coach", "Article Writer", "Reply Mode", "Idea Bank",
              "Post History", "Algorithm Score", "Account Audit", "My Stats", "Profile Analyzer"]
if is_owner():
    _owner_signals_icon = f"""<a href="/?{_tok_qp}page=Signals+%26+Prompts" class="mp-ico {_act('Signals & Prompts')}" target="_self">
      <div class="mp-active-pip"></div>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <path d="M22 12h-4l-3 9L9 3l-3 9H2" stroke="#00E5CC" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.4"/>
      </svg>
    </a>"""
    _owner_signals_panel = f"""<a href="/?{_tok_qp}page=Signals+%26+Prompts" class="mp-panel-item {_act('Signals & Prompts')}" target="_self">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M22 12h-4l-3 9L9 3l-3 9H2" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
        Signals & Prompts
      </a>"""
    _nav_pages.insert(4, "Signals & Prompts")
_nav_pages_js = json.dumps(_nav_pages)

_sidebar_html = f"""
<style>
.mp-rail {{
    display: flex; flex-direction: column; align-items: center;
    padding: 14px 8px 16px; gap: 10px; justify-content: flex-start;
    height: 100vh; position: fixed; top: 0; left: 0; width: 80px;
    background: #080E1E; z-index: 999; overflow: visible;
}}
.mp-logo {{
    width: 52px; height: 52px; border-radius: 10px;
    border: 1px solid #1E3050; display: flex; align-items: center; justify-content: center;
    margin-bottom: 8px; flex-shrink: 0; text-decoration: none !important;
    background: #0D1E36;
}}
.mp-logo:link,
.mp-logo:visited,
.mp-logo:hover,
.mp-logo:active {{ text-decoration: none !important; }}
.mp-zone {{
    width: 64px; background: #0A1628; border-radius: 11px; border: 1px solid #14203A;
    display: flex; flex-direction: column; align-items: center;
    padding: 8px 6px 10px; gap: 4px; flex-shrink: 0;
    position: relative; cursor: default; transition: border-color 0.2s; overflow: visible;
}}
.mp-zone-create:hover  {{ border-color: #00E5CC33; }}
.mp-zone-interact:hover {{ border-color: #C49E3C33; }}
.mp-zone-insights:hover {{ border-color: #6B8AAA33; }}
.mp-zone-label {{
    font-size: 7px; letter-spacing: 1.8px; font-weight: 700;
    padding: 3px 0 6px; font-family: sans-serif;
}}
.mp-zone-create .mp-zone-label   {{ color: #00E5CC44; }}
.mp-zone-interact .mp-zone-label  {{ color: #C49E3C44; }}
.mp-zone-insights .mp-zone-label  {{ color: #6B8AAA44; }}
.mp-zone-create:hover .mp-zone-label   {{ color: #00E5CC99; }}
.mp-zone-interact:hover .mp-zone-label {{ color: #C49E3C99; }}
.mp-zone-insights:hover .mp-zone-label {{ color: #6B8AAA99; }}
.mp-ico {{
    width: 48px; height: 40px; border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    position: relative; flex-shrink: 0; transition: background 0.15s; text-decoration: none !important;
}}
.mp-ico:link,
.mp-ico:visited,
.mp-ico:hover,
.mp-ico:active {{ text-decoration: none !important; }}
.mp-ico:hover {{ background: #142038; }}
.mp-ico.active {{ background: #00E5CC14; }}
.mp-ico.active svg * {{ stroke: #00E5CC !important; }}
.mp-active-pip {{
    position: absolute; left: -4px; top: 50%; transform: translateY(-50%);
    width: 3px; height: 16px; border-radius: 0 3px 3px 0; background: #00E5CC; opacity: 0;
}}
.mp-ico.active .mp-active-pip {{ opacity: 1; }}
.mp-panel {{
    position: fixed; top: 0; left: 0;
    background: #0D1929;
    border: 1px solid #1E3050; border-radius: 12px; padding: 8px 0; min-width: 180px;
    pointer-events: none; opacity: 0; transform: translateX(-4px);
    transition: opacity 0.12s, transform 0.12s; z-index: 99999;
    box-shadow: 0 12px 40px rgba(0,0,0,0.7);
}}
.mp-panel-header {{
    font-size: 8px; letter-spacing: 2px; font-weight: 700;
    padding: 2px 16px 9px; border-bottom: 1px solid #14203A;
    margin-bottom: 4px; font-family: sans-serif;
}}
.mp-zone-create .mp-panel-header   {{ color: #00E5CC66; }}
.mp-zone-interact .mp-panel-header  {{ color: #C49E3C66; }}
.mp-zone-insights .mp-panel-header  {{ color: #6B8AAA66; }}
.mp-panel-item {{
    padding: 8px 16px; font-size: 12px; color: #4A6888 !important;
    display: flex; align-items: center; gap: 10px; cursor: pointer;
    transition: background 0.12s, color 0.12s; text-decoration: none !important;
    -webkit-text-decoration: none !important; font-family: sans-serif;
}}
.mp-panel-item:link,
.mp-panel-item:visited {{ color: #4A6888 !important; text-decoration: none !important; }}
.mp-panel-item:hover,
.mp-panel-item:active {{ text-decoration: none !important; }}
.mp-panel-item:hover {{ background: #142038; color: #8AAAC8 !important; }}
.mp-panel-item.active {{ color: #00E5CC !important; }}
.mp-panel-item.active svg * {{ stroke: #00E5CC !important; }}
.mp-panel-item svg {{ flex-shrink: 0; opacity: 0.7; }}
.mp-panel-item:hover svg {{ opacity: 1; }}
.mp-panel-item.active svg {{ opacity: 1; }}
.mp-spacer {{ flex: 1; }}
.mp-pro {{
    font-size: 8px; font-weight: 700; letter-spacing: 1.5px; color: #C49E3C;
    background: #C49E3C14; border: 1px solid #C49E3C33; border-radius: 6px;
    padding: 4px 8px; font-family: sans-serif; margin-top: auto;
}}
</style>

<div class="mp-rail">

  <a href="/?{_tok_qp}page=Creator+Studio" class="mp-logo" target="_self">
    <svg width="32" height="28" viewBox="0 0 100 88" fill="none">
      <polygon points="18,82 42,40 50,54 30,82" fill="#2DD4BF"/>
      <polygon points="42,40 50,54 58,40" fill="#0D1E36"/>
      <polygon points="58,40 70,82 50,54 82,82" fill="#2DD4BF" opacity="0.75"/>
      <polygon points="42,40 50,26 58,40" fill="#C49E3C"/>
    </svg>
  </a>

  <div class="mp-zone mp-zone-create">
    <div class="mp-zone-label">CREATE</div>
    <a href="/?{_tok_qp}page=Creator+Studio" class="mp-ico {_act('Creator Studio')}" target="_self">
      <div class="mp-active-pip"></div>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <path d="M12 20h9" stroke="#00E5CC" stroke-width="1.5" stroke-linecap="round" opacity="0.9"/>
        <path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4 12.5-12.5z" stroke="#00E5CC" stroke-width="1.5" stroke-linejoin="round" opacity="0.9"/>
      </svg>
    </a>
    <a href="/?{_tok_qp}page=Raw+Thoughts" class="mp-ico {_act('Raw Thoughts')}" target="_self">
      <div class="mp-active-pip"></div>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="10" stroke="#00E5CC" stroke-width="1.5" opacity="0.4"/>
        <path d="M12 8v4l3 3" stroke="#00E5CC" stroke-width="1.5" stroke-linecap="round" opacity="0.4"/>
      </svg>
    </a>
    <a href="/?{_tok_qp}page=Content Coach" class="mp-ico {_act('Content Coach')}" target="_self">
      <div class="mp-active-pip"></div>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" stroke="#00E5CC" stroke-width="1.5" stroke-linejoin="round" opacity="0.4"/>
      </svg>
    </a>
    <a href="/?{_tok_qp}page=Article+Writer" class="mp-ico {_act('Article Writer')}" target="_self">
      <div class="mp-active-pip"></div>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" stroke="#00E5CC" stroke-width="1.5" stroke-linejoin="round" opacity="0.4"/>
        <polyline points="14 2 14 8 20 8" stroke="#00E5CC" stroke-width="1.5" stroke-linejoin="round" opacity="0.4"/>
        <line x1="16" y1="13" x2="8" y2="13" stroke="#00E5CC" stroke-width="1.5" stroke-linecap="round" opacity="0.4"/>
      </svg>
    </a>
    {_owner_signals_icon}
    <div class="mp-panel">
      <div class="mp-panel-header">CREATE</div>
      <a href="/?{_tok_qp}page=Creator+Studio" class="mp-panel-item {_act('Creator Studio')}" target="_self">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M12 20h9" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4 12.5-12.5z" stroke="#6B8AAA" stroke-width="1.5" stroke-linejoin="round"/></svg>
        Creator Studio
      </a>
      <a href="/?{_tok_qp}page=Raw+Thoughts" class="mp-panel-item {_act('Raw Thoughts')}" target="_self">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="#6B8AAA" stroke-width="1.5"/><path d="M12 8v4l3 3" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round"/></svg>
        Raw Thoughts
      </a>
      <a href="/?{_tok_qp}page=Content Coach" class="mp-panel-item {_act('Content Coach')}" target="_self">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" stroke="#6B8AAA" stroke-width="1.5" stroke-linejoin="round"/></svg>
        Content Coach
      </a>
      <a href="/?{_tok_qp}page=Article+Writer" class="mp-panel-item {_act('Article Writer')}" target="_self">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" stroke="#6B8AAA" stroke-width="1.5" stroke-linejoin="round"/><polyline points="14 2 14 8 20 8" stroke="#6B8AAA" stroke-width="1.5"/><line x1="16" y1="13" x2="8" y2="13" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round"/></svg>
        Article Writer
      </a>
      {_owner_signals_panel}
    </div>
  </div>

  <div class="mp-zone mp-zone-interact">
    <div class="mp-zone-label">INTERACT</div>
    <a href="/?{_tok_qp}page=Reply+Mode" class="mp-ico {_act('Reply Mode')}" target="_self">
      <div class="mp-active-pip"></div>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <polyline points="17 1 21 5 17 9" stroke="#C49E3C" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.6"/>
        <path d="M3 11V9a4 4 0 014-4h14" stroke="#C49E3C" stroke-width="1.5" stroke-linecap="round" opacity="0.6"/>
        <polyline points="7 23 3 19 7 15" stroke="#C49E3C" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.6"/>
        <path d="M21 13v2a4 4 0 01-4 4H3" stroke="#C49E3C" stroke-width="1.5" stroke-linecap="round" opacity="0.6"/>
      </svg>
    </a>
    <a href="/?{_tok_qp}page=Idea+Bank" class="mp-ico {_act('Idea Bank')}" target="_self">
      <div class="mp-active-pip"></div>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <path d="M12 2L2 7l10 5 10-5-10-5z" stroke="#C49E3C" stroke-width="1.5" stroke-linejoin="round" opacity="0.6"/>
        <path d="M2 17l10 5 10-5" stroke="#C49E3C" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.6"/>
        <path d="M2 12l10 5 10-5" stroke="#C49E3C" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.6"/>
      </svg>
    </a>
    <div class="mp-panel">
      <div class="mp-panel-header">INTERACT</div>
      <a href="/?{_tok_qp}page=Reply+Mode" class="mp-panel-item {_act('Reply Mode')}" target="_self">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><polyline points="17 1 21 5 17 9" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M3 11V9a4 4 0 014-4h14" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round"/><polyline points="7 23 3 19 7 15" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M21 13v2a4 4 0 01-4 4H3" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round"/></svg>
        Reply Mode
      </a>
      <a href="/?{_tok_qp}page=Idea+Bank" class="mp-panel-item {_act('Idea Bank')}" target="_self">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M12 2L2 7l10 5 10-5-10-5z" stroke="#6B8AAA" stroke-width="1.5" stroke-linejoin="round"/><path d="M2 17l10 5 10-5" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M2 12l10 5 10-5" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
        Idea Bank
      </a>
    </div>
  </div>

  <div class="mp-zone mp-zone-insights">
    <div class="mp-zone-label">INSIGHTS</div>
    <a href="/?{_tok_qp}page=Post+History" class="mp-ico {_act('Post History')}" target="_self">
      <div class="mp-active-pip"></div>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="10" stroke="#91A2B2" stroke-width="1.5" opacity="0.5"/>
        <polyline points="12 6 12 12 16 14" stroke="#91A2B2" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.5"/>
      </svg>
    </a>
    <a href="/?{_tok_qp}page=Algorithm+Score" class="mp-ico {_act('Algorithm Score')}" target="_self">
      <div class="mp-active-pip"></div>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <line x1="18" y1="20" x2="18" y2="10" stroke="#91A2B2" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>
        <line x1="12" y1="20" x2="12" y2="4" stroke="#91A2B2" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>
        <line x1="6" y1="20" x2="6" y2="14" stroke="#91A2B2" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>
      </svg>
    </a>
    <a href="/?{_tok_qp}page=Account+Audit" class="mp-ico {_act('Account Audit')}" target="_self">
      <div class="mp-active-pip"></div>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <path d="M22 11.08V12a10 10 0 11-5.93-9.14" stroke="#91A2B2" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>
        <polyline points="22 4 12 14.01 9 11.01" stroke="#91A2B2" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.5"/>
      </svg>
    </a>
    <a href="/?{_tok_qp}page=My+Stats" class="mp-ico {_act('My Stats')}" target="_self">
      <div class="mp-active-pip"></div>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" stroke="#91A2B2" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.5"/>
      </svg>
    </a>
    <a href="/?{_tok_qp}page=Profile+Analyzer" class="mp-ico {_act('Profile Analyzer')}" target="_self">
      <div class="mp-active-pip"></div>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <circle cx="11" cy="11" r="8" stroke="#91A2B2" stroke-width="1.5" opacity="0.5"/>
        <line x1="21" y1="21" x2="16.65" y2="16.65" stroke="#91A2B2" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>
      </svg>
    </a>
    <div class="mp-panel">
      <div class="mp-panel-header">INSIGHTS</div>
      <a href="/?{_tok_qp}page=Post+History" class="mp-panel-item {_act('Post History')}" target="_self">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="#6B8AAA" stroke-width="1.5"/><polyline points="12 6 12 12 16 14" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
        Post History
      </a>
      <a href="/?{_tok_qp}page=Algorithm+Score" class="mp-panel-item {_act('Algorithm Score')}" target="_self">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><line x1="18" y1="20" x2="18" y2="10" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round"/><line x1="12" y1="20" x2="12" y2="4" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round"/><line x1="6" y1="20" x2="6" y2="14" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round"/></svg>
        Algorithm Score
      </a>
      <a href="/?{_tok_qp}page=Account+Audit" class="mp-panel-item {_act('Account Audit')}" target="_self">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M22 11.08V12a10 10 0 11-5.93-9.14" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round"/><polyline points="22 4 12 14.01 9 11.01" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
        Account Audit
      </a>
      <a href="/?{_tok_qp}page=My+Stats" class="mp-panel-item {_act('My Stats')}" target="_self">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
        My Stats
      </a>
      <a href="/?{_tok_qp}page=Profile+Analyzer" class="mp-panel-item {_act('Profile Analyzer')}" target="_self">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><circle cx="11" cy="11" r="8" stroke="#6B8AAA" stroke-width="1.5"/><line x1="21" y1="21" x2="16.65" y2="16.65" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round"/></svg>
        Profile Analyzer
      </a>
    </div>
  </div>
  {_owner_debug_zone}

  <div class="mp-pro">{'GUEST' if is_guest() else 'PRO'}</div>
</div>

"""

with st.sidebar:
    st.markdown(_sidebar_html, unsafe_allow_html=True)
    if is_guest():
        _g_avatar = st.session_state.get("user_avatar", "")
        _g_name = st.session_state.get("user_display_name", "")
        _g_handle = get_current_handle()
        _g_username = st.session_state.get("auth_username", "")
        if _g_avatar and _g_handle:
            st.markdown(f"""<div style="text-align:center;margin:-6px 0 8px;">
                <img src="{_g_avatar}" style="width:32px;height:32px;border-radius:50%;border:1px solid #2DD4BF;margin-bottom:4px;" />
                <div style="font-size:11px;color:#E2E8F0;font-weight:600;">{_g_name or _g_handle}</div>
                <div style="font-size:10px;color:#6E7681;">@{_g_handle}</div>
            </div>""", unsafe_allow_html=True)
        elif _g_username:
            st.markdown(f'<div style="text-align:center;margin:-6px 0 8px;font-size:11px;color:#6E7681;">{_g_username}</div>', unsafe_allow_html=True)
    if st.button("Logout", key="_logout", type="secondary", use_container_width=True):
        st.session_state["auth_role"] = None
        st.session_state.pop("_auth_token", None)
        st.session_state.pop("auth_username", None)
        st.session_state.pop("user_handle", None)
        st.session_state.pop("user_display_name", None)
        st.session_state.pop("user_avatar", None)
        st.session_state.pop("onboarding_complete", None)
        st.session_state.pop("onboarding_step", None)
        for _k in ["token", "user", "guest_id"]:
            if _k in st.query_params:
                del st.query_params[_k]
        st.rerun()
    # Hidden buttons for each page — JS wires sidebar links to click these
    # instead of doing full page reloads (eliminates white flash)
    def _nav_to(pg):
        st.session_state.current_page = pg
        st.session_state._nav_override = True
    for _pg in _nav_pages:
        st.button(_pg, key=f"_nav_{_pg}", on_click=_nav_to, args=(_pg,),
                  type="secondary", use_container_width=True)

# ── Desktop flyout panels (JS, same-origin iframe) ──────────────────────────
import streamlit.components.v1 as _stc
_stc.html("""<script>
(function(){
  var doc=window.parent.document;
  var win=window.parent;

  /* ── Desktop flyout panels (skip on mobile) ── */
  var _isDesktop=win.innerWidth>768;
  function init(){
    if(!_isDesktop) return;
    doc.querySelectorAll('.mp-zone').forEach(function(zone){
      if(zone._mpReady) return;
      zone._mpReady=true;
      var panel=zone.querySelector('.mp-panel');
      if(!panel) return;
      doc.body.appendChild(panel);
      panel.style.position='fixed';panel.style.zIndex='999999';
      panel.style.opacity='0';panel.style.pointerEvents='none';
      panel.style.transform='translateX(-4px)';
      panel.style.transition='opacity 0.12s,transform 0.12s';
      panel.querySelectorAll('a').forEach(function(a){a.setAttribute('target','_self');});
      zone.querySelectorAll('a.mp-ico').forEach(function(a){a.setAttribute('target','_self');});
      var t=null;
      function show(){clearTimeout(t);var r=zone.getBoundingClientRect();panel.style.top=r.top+'px';panel.style.left=(r.right+8)+'px';panel.style.opacity='1';panel.style.transform='translateX(0)';panel.style.pointerEvents='all';}
      function hide(){t=setTimeout(function(){panel.style.opacity='0';panel.style.transform='translateX(-4px)';panel.style.pointerEvents='none';},300);}
      zone.addEventListener('mouseenter',show);zone.addEventListener('mouseleave',hide);
      panel.addEventListener('mouseenter',function(){clearTimeout(t);});panel.addEventListener('mouseleave',hide);
    });
  }
  setTimeout(init,600);setTimeout(init,1500);setTimeout(init,3000);

  /* ── Hide nav buttons + wire sidebar links to click them (no reload) ── */
  function wireNav(){
    var sidebar=doc.querySelector('section[data-testid="stSidebar"]');
    if(!sidebar) return;
    var pageNames=__PAGE_NAMES__;
    /* Hide nav buttons visually but keep clickable */
    sidebar.querySelectorAll('button').forEach(function(btn){
      var t=btn.textContent.trim();
      if(pageNames.indexOf(t)!==-1){
        var el=btn.closest('[data-testid="stElementContainer"]')||btn.closest('[data-testid="element-container"]')||btn.parentElement.parentElement;
        if(el) el.style.cssText='position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0);';
      }
    });
    /* Intercept sidebar <a> links — click matching hidden button, or fall back to URL nav */
    doc.querySelectorAll('a[href*="?page="]').forEach(function(a){
      if(a._wired) return;
      a._wired=true;
      a.addEventListener('click',function(e){
        e.preventDefault();
        var url=new URL(a.href,win.location.origin);
        var page=url.searchParams.get('page');
        if(!page){ win.location.href=a.href; return; }
        /* Try clicking the hidden nav button */
        var clicked=false;
        var btns=sidebar.querySelectorAll('button');
        for(var i=0;i<btns.length;i++){
          if(btns[i].textContent.trim()===page){
            btns[i].removeAttribute('disabled');
            btns[i].click();
            clicked=true;
            break;
          }
        }
        /* If button click didn't work (e.g. hidden by CSS), fall back to URL navigation */
        if(!clicked){
          /* Preserve auth token in URL */
          var tok=url.searchParams.get('token')||new URLSearchParams(win.location.search).get('token')||'';
          if(tok) url.searchParams.set('token',tok);
          win.location.href=url.toString();
        }
      });
    });
  }
  setTimeout(wireNav,800);setTimeout(wireNav,2000);setTimeout(wireNav,4000);

  /* ── Global: MutationObserver that wires docks/bottoms + tags pill rows ── */
  /* Hidden buttons are now hidden by CSS (clip:rect) in the global stylesheet — no JS hiding needed */
  /* Runs on EVERY DOM change so it works on reruns (not just full page loads) */
  function processDOM(){
    var btns=doc.querySelectorAll('button');
    /* Tag pill rows */
    var labels=['Punchy','Normal','Long','Thread','Article'];
    var voiceLabels=['Default','Critical','Hype','Sarcastic'];
    function findRow(textList){
      for(var i=0;i<btns.length;i++){
        if(textList.indexOf(btns[i].textContent.trim())!==-1){
          var block=btns[i].closest('[data-testid="stHorizontalBlock"]');
          if(block) return block.parentElement;
        }
      }
      return null;
    }
    var fmtRow=findRow(labels);
    if(fmtRow&&!fmtRow.classList.contains('cs-fmt-row')) fmtRow.classList.add('cs-fmt-row');
    var voiceRow=findRow(voiceLabels);
    if(voiceRow&&!voiceRow.classList.contains('cs-voice-row')) voiceRow.classList.add('cs-voice-row');
    /* Wire all icon dock buttons — try both with and without prefix */
    doc.querySelectorAll('.cs-idock-btn').forEach(function(d){
      if(d._wired) return; d._wired=true;
      d.addEventListener('click',function(){
        var raw=d.dataset.dock;
        var prefixed='dock_'+raw;
        for(var i=0;i<btns.length;i++){
          var t=btns[i].textContent.trim();
          if(t===raw||t===prefixed){btns[i].removeAttribute('disabled');btns[i].click();return;}
        }
      });
    });
    /* Wire all bottom bar buttons — try both with and without prefix */
    doc.querySelectorAll('.cs-bot').forEach(function(b){
      if(b._wired) return; b._wired=true;
      b.addEventListener('click',function(){
        var raw=b.dataset.bot;
        var prefixed='bot_'+raw;
        for(var i=0;i<btns.length;i++){
          var t=btns[i].textContent.trim();
          if(t===raw||t===prefixed){btns[i].removeAttribute('disabled');btns[i].click();return;}
        }
      });
    });
  }
  /* Run immediately + debounced on DOM changes (not every mutation) */
  setTimeout(processDOM,300);setTimeout(processDOM,800);setTimeout(processDOM,2000);
  var _pdTimer=null;
  var _observer=new MutationObserver(function(){
    if(_pdTimer) clearTimeout(_pdTimer);
    _pdTimer=setTimeout(processDOM,50);
  });
  _observer.observe(doc.body||doc.documentElement,{childList:true,subtree:true});
})();
</script>""".replace("__PAGE_NAMES__", _nav_pages_js), height=0)

# ── Mobile hamburger nav (CSS-only toggle, main page DOM, no iframe) ─────────
_lnk = "display:block;padding:14px 0;font-size:16px;color:#c0c8d8;text-decoration:none;border-bottom:1px solid #111a2a;"
_sec = "font-size:9px;letter-spacing:2px;color:#445;font-weight:700;margin:24px 0 10px;"
st.markdown(f"""
<style>
#_mob_chk{{display:none;}}
#_mob_ham{{display:none;position:fixed;top:10px;left:10px;z-index:9999;
  background:#0A1628;border:1px solid #1E3050;border-radius:8px;
  width:40px;height:40px;align-items:center;justify-content:center;cursor:pointer;}}
#_mob_nav{{display:none;position:fixed;inset:0;background:#080E1E;z-index:9998;
  padding:24px 28px;overflow-y:auto;font-family:-apple-system,sans-serif;}}
#_mob_chk:checked~#_mob_nav{{display:block;}}
#_mob_chk:checked~#_mob_ham{{display:none!important;}}
@media(max-width:768px){{#_mob_ham{{display:flex!important;}}}}
</style>
<input type="checkbox" id="_mob_chk">
<div id="_mob_nav">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:28px;">
    <div style="display:flex;align-items:center;gap:10px;">
      <svg width="28" height="24" viewBox="0 0 100 88" fill="none"><polygon points="18,82 42,40 50,54 30,82" fill="#2DD4BF"/><polygon points="42,40 50,54 58,40" fill="#0D1E36"/><polygon points="58,40 70,82 50,54 82,82" fill="#2DD4BF" opacity="0.75"/><polygon points="42,40 50,26 58,40" fill="#C49E3C"/></svg>
      <span style="font-size:13px;font-weight:700;color:#2DD4BF;letter-spacing:3px;">POST ASCEND</span>
    </div>
    <label for="_mob_chk" style="font-size:32px;cursor:pointer;color:#667;line-height:1;padding:4px 8px;">&#215;</label>
  </div>
  <div style="{_sec}">CREATE</div>
  <a href="/?{_tok_qp}page=Creator+Studio" target="_self" style="{_lnk}">Creator Studio</a>
  <a href="/?{_tok_qp}page=Raw+Thoughts" target="_self" style="{_lnk}">Raw Thoughts</a>
  <a href="/?{_tok_qp}page=Content Coach" target="_self" style="{_lnk}">Content Coach</a>
  <a href="/?{_tok_qp}page=Article+Writer" target="_self" style="{_lnk}">Article Writer</a>
  {'<a href="/?'+_tok_qp+'page=Signals+%26+Prompts" target="_self" style="'+_lnk+'">Signals & Prompts</a>' if is_owner() else ''}
  <div style="{_sec}">INTERACT</div>
  <a href="/?{_tok_qp}page=Reply+Mode" target="_self" style="{_lnk}">Reply Mode</a>
  <a href="/?{_tok_qp}page=Idea+Bank" target="_self" style="{_lnk}">Idea Bank</a>
  <div style="{_sec}">INSIGHTS</div>
  <a href="/?{_tok_qp}page=Post+History" target="_self" style="{_lnk}">Post History</a>
  <a href="/?{_tok_qp}page=Algorithm+Score" target="_self" style="{_lnk}">Algorithm Score</a>
  <a href="/?{_tok_qp}page=Account+Audit" target="_self" style="{_lnk}">Account Audit</a>
  <a href="/?{_tok_qp}page=My+Stats" target="_self" style="{_lnk}">My Stats</a>
  <a href="/?{_tok_qp}page=Profile+Analyzer" target="_self" style="{_lnk}">Profile Analyzer</a>
</div>
<label for="_mob_chk" id="_mob_ham">
  <svg width="18" height="14" viewBox="0 0 18 14" fill="none">
    <line x1="0" y1="1" x2="18" y2="1" stroke="#c0c8d8" stroke-width="2" stroke-linecap="round"/>
    <line x1="0" y1="7" x2="18" y2="7" stroke="#c0c8d8" stroke-width="2" stroke-linecap="round"/>
    <line x1="0" y1="13" x2="18" y2="13" stroke="#c0c8d8" stroke-width="2" stroke-linecap="round"/>
  </svg>
</label>
""", unsafe_allow_html=True)



page = st.session_state.current_page
if page in {"Debug Console", "Signals & Prompts"} and not is_owner():
    page = "Creator Studio"
    st.session_state.current_page = page


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: BRAIN DUMP
# ═══════════════════════════════════════════════════════════════════════════
def page_brain_dump():
    st.markdown('<div class="main-header">RAW <span>THOUGHTS</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Set a timer, dump your thoughts, turn them into content.</div>', unsafe_allow_html=True)
    st.markdown(
        '''<div style="display:flex;justify-content:flex-start;margin:0 0 16px 0;">
            <span class="cs-bot" data-bot="bd_help_video" style="height:52px;padding:0 18px;border-radius:14px;font-size:12px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;border:1px solid rgba(196,158,60,0.45);background:rgba(45,212,191,0.1);color:#C49E3C;cursor:pointer;display:inline-flex;align-items:center;gap:6px;">See How It Works</span>
        </div>''',
        unsafe_allow_html=True,
    )
    if st.button("bot_bd_help_video", key="bd_help_video"):
        _raw_thoughts_help_dialog()
    st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

    # Timer
    if "bd_timer_end" not in st.session_state:
        st.session_state.bd_timer_end = None
    if "bd_timer_mins" not in st.session_state:
        st.session_state.bd_timer_mins = 0

    # ── Timer as inline HTML pills + countdown ──
    _timer_active = st.session_state.bd_timer_mins if st.session_state.bd_timer_end else 0
    _timer_display = ""
    if st.session_state.bd_timer_end:
        _remaining = max(0, st.session_state.bd_timer_end - time.time())
        _tm, _ts = divmod(int(_remaining), 60)
        if _remaining > 0:
            _timer_display = f'<span style="font-family:Bebas Neue,sans-serif;font-size:22px;color:#2DD4BF;margin-left:12px;">{_tm:02d}:{_ts:02d}</span>'
        else:
            st.session_state.bd_timer_end = None
            _timer_display = '<span style="font-family:Bebas Neue,sans-serif;font-size:22px;color:#22c55e;margin-left:12px;">DONE</span>'

    _pill_base = "height:52px;padding:0 18px;border-radius:14px;font-size:10px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;cursor:pointer;display:inline-flex;align-items:center;"
    _pill_on = _pill_base + "background:rgba(45,212,191,0.1);border:1px solid rgba(45,212,191,0.4);color:#2DD4BF;"
    _pill_off = _pill_base + "background:#0e1a2e;border:1px solid #1a2a45;color:#5a7090;"

    _timer_html = f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">'
    _timer_html += '<span style="font-size:9px;font-weight:700;letter-spacing:1.2px;color:#3a5070;text-transform:uppercase;margin-right:4px;">Timer</span>'
    for _mins in [5, 10, 15, 30]:
        _cls = _pill_on if _mins == _timer_active else _pill_off
        _timer_html += f'<span class="cs-bot" data-bot="timer_{_mins}" style="{_cls}">{_mins} min</span>'
    _timer_html += _timer_display
    _timer_html += '</div>'
    st.markdown(_timer_html, unsafe_allow_html=True)

    # Hidden timer buttons
    for mins in [5, 10, 15, 30]:
        if st.button(f"timer_{mins}", key=f"timer_{mins}"):
            st.session_state.bd_timer_end = time.time() + mins * 60
            st.session_state.bd_timer_mins = mins
            st.rerun()

    # Auto-refresh for countdown
    if st.session_state.bd_timer_end and (st.session_state.bd_timer_end - time.time()) > 0:
        time.sleep(1)
        st.rerun()

    # ── Text area ──
    dump_text = st.text_area("Drop your raw thoughts:", height=200,
        placeholder="Whatever is in your head -- game reaction, hot take, rant, observation...",
        key="bd_text", label_visibility="collapsed")

    # ── Action dock: Subject | Ideas | Tweets | Long-form | Video ──
    st.markdown('''<div style="font-size:8px;font-weight:700;letter-spacing:1.5px;color:#2a3a55;text-transform:uppercase;margin:12px 0 8px;">ACTIONS</div>
    <div class="cs-icon-dock cs-bd-dock" style="display:flex;gap:8px;justify-content:center;margin-bottom:16px;">
      <div class="cs-idock-btn cs-idock-primary" data-dock="bd_subject" style="width:52px;height:52px;border-radius:14px;background:linear-gradient(135deg,#1fb8a8,#2DD4BF);display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" stroke="#060A12" stroke-width="2" stroke-linejoin="round"/></svg>
        <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">SUBJECT</span>
      </div>
      <div class="cs-idock-btn" data-dock="bd_ideas" style="width:52px;height:52px;border-radius:14px;border:1px solid #1a2a45;background:#0a1220;display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M12 2a7 7 0 017 7c0 2.38-1.19 4.47-3 5.74V17a1 1 0 01-1 1h-6a1 1 0 01-1-1v-2.26C6.19 13.47 5 11.38 5 9a7 7 0 017-7z" stroke="#5a7090" stroke-width="2"/><line x1="9" y1="21" x2="15" y2="21" stroke="#5a7090" stroke-width="2"/></svg>
        <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">IDEAS</span>
      </div>
      <div class="cs-idock-btn" data-dock="bd_gen_tweets" style="width:52px;height:52px;border-radius:14px;border:1px solid #1a2a45;background:#0a1220;display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M23 3a10.9 10.9 0 01-3.14 1.53A4.48 4.48 0 0012 7.5v1A10.66 10.66 0 013 4s-4 9 5 13a11.64 11.64 0 01-7 2c9 5 20 0 20-11.5" stroke="#5a7090" stroke-width="2"/></svg>
        <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">TWEETS</span>
      </div>
      <div class="cs-idock-btn" data-dock="bd_gen_long" style="width:52px;height:52px;border-radius:14px;border:1px solid #1a2a45;background:#0a1220;display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" stroke="#5a7090" stroke-width="2"/><polyline points="14 2 14 8 20 8" stroke="#5a7090" stroke-width="2"/></svg>
        <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">LONG-FORM</span>
      </div>
      <div class="cs-idock-btn" data-dock="bd_gen_video" style="width:52px;height:52px;border-radius:14px;border:1px solid #1a2a45;background:#0a1220;display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><polygon points="23 7 16 12 23 17 23 7" stroke="#5a7090" stroke-width="2"/><rect x="1" y="5" width="15" height="14" rx="2" stroke="#5a7090" stroke-width="2"/></svg>
        <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">VIDEO</span>
      </div>
    </div>''', unsafe_allow_html=True)

    # Hidden Streamlit buttons for dock actions
    if st.button("bd_subject", key="bd_subject"):
        with st.spinner("Thinking..."):
            _bd_topic = "Denver sports" if not is_guest() else load_json("topics.json", {}).get("niche", "trending topics")
            result = call_claude(f"Give ONE specific content subject to write about right now. {_bd_topic}. One sentence. Be specific and timely.", system=build_user_context(), max_tokens=150)
            st.session_state["bd_subject_result"] = result
    if st.button("bd_ideas", key="bd_ideas"):
        if dump_text.strip():
            with st.spinner("Generating ideas..."):
                result = call_claude(f'Brain dump:\n\n"{dump_text}"\n\nGenerate 5 specific content ideas from this brain dump. Each should be a different angle or format. Number them.', system=build_user_context(), max_tokens=600)
                st.session_state["bd_ideas_result"] = result
    if st.button("bd_gen_tweets", key="bd_gen_tweets"):
        if dump_text.strip():
            with st.spinner("Generating tweets..."):
                result = call_claude(f'Brain dump:\n\n"{dump_text}"\n\nWrite 5 tweet options from this. Each under 220 characters. Different angles and hooks. Number them. No hashtags. No emojis.', system=build_user_context(), max_tokens=500)
                st.session_state["bd_tweets"] = result
    if st.button("bd_gen_long", key="bd_gen_long"):
        if dump_text.strip():
            with st.spinner("Generating..."):
                result = call_claude(f'Brain dump:\n\n"{dump_text}"\n\nWrite a long-form X post (400-600 characters) that digs deeper into this topic. Voice: authoritative, direct. Include a strong opening hook.', system=build_user_context(), max_tokens=500)
                st.session_state["bd_longform"] = result
    if st.button("bd_gen_video", key="bd_gen_video"):
        if dump_text.strip():
            with st.spinner("Generating..."):
                result = call_claude(f'Brain dump:\n\n"{dump_text}"\n\nCreate a 3-5 minute video script outline:\n- Cold open hook (15 seconds)\n- 3-4 main talking points with bullet notes\n- Closing line / CTA\n\nKeep it conversational. Natural voice, not a news anchor.', system=build_user_context(), max_tokens=600)
                st.session_state["bd_video"] = result

    # ── Bottom bar ──
    st.markdown('''<div style="height:1px;background:#1a2a45;margin:24px 0 14px;"></div>
    <div class="cs-bottom-bar cs-bd-bottom" style="display:flex;gap:8px;justify-content:center;">
      <span class="cs-bot" data-bot="bd_save" style="height:52px;padding:0 18px;border-radius:14px;font-size:10px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;border:1px solid #1a2a45;background:#0a1220;color:#5a7090;cursor:pointer;display:inline-flex;align-items:center;gap:6px;">↓ Save</span>
      <span class="cs-bot" data-bot="bd_new" style="height:52px;padding:0 18px;border-radius:14px;font-size:10px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;border:1px solid #1a2a45;background:#0a1220;color:#5a7090;cursor:pointer;display:inline-flex;align-items:center;gap:6px;">↺ New</span>
      <span class="cs-bot" data-bot="bd_saved" style="height:52px;padding:0 18px;border-radius:14px;font-size:10px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;border:1px solid rgba(196,158,60,0.25);background:#0a1220;color:rgba(196,158,60,0.6);cursor:pointer;display:inline-flex;align-items:center;gap:6px;">Saved Thoughts</span>
    </div>''', unsafe_allow_html=True)

    # Hidden buttons for bottom bar
    if st.button("bd_save", key="bd_save"):
        if dump_text.strip():
            dumps = load_json("brain_dumps.json", [])
            dumps.append({"text": dump_text, "saved_at": datetime.now().isoformat(), "timer_mins": st.session_state.bd_timer_mins})
            save_json("brain_dumps.json", dumps)
            st.success("Saved.")
    if st.button("bd_new", key="bd_new"):
        st.session_state.bd_timer_end = None
        st.session_state.bd_timer_mins = 0
        for k in ["bd_subject_result", "bd_ideas_result", "bd_tweets", "bd_longform", "bd_video"]:
            st.session_state.pop(k, None)
        st.rerun()
    if st.button("bd_saved", key="bd_saved"):
        st.session_state["_bd_show_saved"] = True

    # ── Results display ──
    if st.session_state.get("bd_subject_result"):
        st.markdown(f'<div class="output-box">{st.session_state["bd_subject_result"]}</div>', unsafe_allow_html=True)
    if st.session_state.get("bd_ideas_result"):
        st.markdown(f'<div class="output-box">{st.session_state["bd_ideas_result"]}</div>', unsafe_allow_html=True)
    if st.session_state.get("bd_tweets"):
        st.markdown(f'<div class="output-box">{st.session_state["bd_tweets"]}</div>', unsafe_allow_html=True)
    if st.session_state.get("bd_longform"):
        st.markdown(f'<div class="output-box">{st.session_state["bd_longform"]}</div>', unsafe_allow_html=True)
    if st.session_state.get("bd_video"):
        st.markdown(f'<div class="output-box">{st.session_state["bd_video"]}</div>', unsafe_allow_html=True)

    # ── Saved thoughts modal ──
    if st.session_state.pop("_bd_show_saved", False):
        @st.dialog("Saved Thoughts", width="large")
        def _bd_saved_dialog():
            dumps = load_json("brain_dumps.json", [])
            if not dumps:
                st.markdown('<div class="output-box">No saved thoughts yet.</div>', unsafe_allow_html=True)
            else:
                for i, d in enumerate(reversed(dumps[-20:])):
                    ts = d.get("saved_at", "")[:16].replace("T", " ")
                    preview = d.get("text", "")[:200]
                    timer_info = f" ({d.get('timer_mins', '?')}m)" if d.get('timer_mins') else ""
                    st.markdown(f"""<div class="tweet-card">
                        <div class="tweet-num">{ts}{timer_info}</div>
                        <div style="color:#d8d8e8; font-size:13px;">{preview}{'...' if len(d.get('text','')) > 200 else ''}</div>
                    </div>""", unsafe_allow_html=True)
                    if st.button("Use This", key=f"bd_use_{i}", use_container_width=True):
                        st.session_state["bd_text"] = d.get("text", "")
                        st.rerun(scope="app")
        _bd_saved_dialog()

    # ── Hidden buttons are CSS-hidden; dock/bottom clicks wired by global MutationObserver ──


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: COMPOSE IDEAS
# ═══════════════════════════════════════════════════════════════════════════
# _FORMAT_GUIDES -> config.py


# ═══════════════════════════════════════════════════════════════════════════
# CREATOR STUDIO — STAT INJECTION + AI RUNNER
# ═══════════════════════════════════════════════════════════════════════════

def _input_has_stats(text: str) -> bool:
    """Returns True if the input already contains numeric stats."""
    for pattern in [r'\d+\.\d+', r'\d+%', r'\d+-\d+', r'\b\d{2,}\b']:
        if re.search(pattern, text):
            return True
    return False


def _tweet_wants_betting(text: str) -> str:
    """Determine if a tweet benefits from betting context.
    Returns:
      'explicit' — tweet is about betting/lines/picks → always inject full odds
      'game'     — tweet is about a specific upcoming game → inject as soft background
      ''         — no betting relevance → skip odds entirely
    """
    _text = text.lower()
    # Explicit gambling/betting intent
    _explicit = [
        "spread", "odds", "line ", "lines", "moneyline", "money line",
        "over/under", "o/u", "parlay", "bet ", "betting", "lock ",
        "fade ", "cover", "ats", "points favorite", "point favorite",
        "point underdog", "points underdog", "favored by", "underdog",
        "prop ", "props", "pick ", "picks", "teaser", "handicap",
        "juice", "vig", "sharp ", "square ", "book ", "bookie",
        "sportsbook", "fanduel", "draftkings", "bovada",
    ]
    if any(sig in _text for sig in _explicit):
        return "explicit"
    # Game-preview context (upcoming matchup, predictions, who wins)
    _game_signals = [
        "tonight", "game tonight", "tomorrow", "this weekend",
        "who wins", "going to win", "gonna win", "will win",
        "prediction", "preview", "matchup", "face off",
        "playoff", "series", "round 1", "round 2", "first round",
    ]
    if any(sig in _text for sig in _game_signals):
        return "game"
    return ""


def _detect_sports_entities(text: str) -> dict:
    """Detects player names and team names in the input."""
    text_lower = text.lower()
    nba_players = ["jokic", "murray", "gordon", "porter", "braun", "rivers", "westbrook"]
    nfl_players = ["bo nix", "nix", "sutton", "waddle", "dobbins", "payton", "mahomes", "kelce", "stafford", "allen"]
    nhl_players = ["mackinnon", "rantanen", "makar", "lehkonen"]
    nba_teams = ["nuggets", "lakers", "celtics", "warriors", "thunder", "wolves", "timberwolves", "clippers", "suns", "heat"]
    nfl_teams = ["broncos", "chiefs", "raiders", "chargers", "cowboys", "eagles", "49ers", "ravens", "bills", "packers"]
    nhl_teams = ["avalanche", "avs", "blues", "stars", "jets", "wild"]
    found_players = [p for p in nba_players + nfl_players + nhl_players if p in text_lower]
    found_teams = [t for t in nba_teams + nfl_teams + nhl_teams if t in text_lower]
    return {"players": found_players, "teams": found_teams}


def _fetch_live_stats(entities: dict, betting_level: str = "") -> str:
    """Calls ESPN API directly to get current stats for detected entities.
    betting_level: 'explicit' = full odds block, 'game' = soft background, '' = no odds.
    """
    import urllib.request
    stat_lines = []
    _team_map = {
        "nuggets": ("basketball", "nba", "den"), "lakers": ("basketball", "nba", "lal"),
        "celtics": ("basketball", "nba", "bos"), "warriors": ("basketball", "nba", "gsw"),
        "thunder": ("basketball", "nba", "okc"), "wolves": ("basketball", "nba", "min"),
        "timberwolves": ("basketball", "nba", "min"), "clippers": ("basketball", "nba", "lac"),
        "suns": ("basketball", "nba", "phx"), "heat": ("basketball", "nba", "mia"),
        "broncos": ("football", "nfl", "den"), "chiefs": ("football", "nfl", "kc"),
        "raiders": ("football", "nfl", "lv"), "chargers": ("football", "nfl", "lac"),
        "cowboys": ("football", "nfl", "dal"), "eagles": ("football", "nfl", "phi"),
        "49ers": ("football", "nfl", "sf"), "ravens": ("football", "nfl", "bal"),
        "bills": ("football", "nfl", "buf"), "packers": ("football", "nfl", "gb"),
        "avalanche": ("hockey", "nhl", "col"), "avs": ("hockey", "nhl", "col"),
    }
    for team in entities.get("teams", []):
        mapping = _team_map.get(team)
        if not mapping:
            continue
        sport, league, abbr = mapping
        try:
            url = f"https://site.api.espn.com/apis/site/v2/sports/{sport}/{league}/teams/{abbr}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
            t = data.get("team", {})
            records = t.get("record", {}).get("items", [])
            overall = records[0].get("summary", "") if records else ""
            name = t.get("displayName", team.title())
            next_ev = t.get("nextEvent", [])
            next_game = next_ev[0].get("name", "") if next_ev else ""
            line = f"{name}: {overall}" if overall else ""
            if next_game:
                line += f" | Next: {next_game}"
            if line:
                stat_lines.append(line)
        except Exception:
            pass
    # Get today's scores for relevant sports
    _sports_seen = set()
    for team in entities.get("teams", []):
        mapping = _team_map.get(team)
        if not mapping:
            continue
        sport, league, _ = mapping
        if league not in _sports_seen:
            _sports_seen.add(league)
            try:
                import sys as _s3
                _s3.path.insert(0, os.path.expanduser("~/.openclaw"))
                from apis.espn import espn
                summary = espn.scoreboard_summary(league)
                if summary:
                    stat_lines.append(f"Today's {league.upper()} scores:\n{summary}")
            except Exception:
                pass
    # Betting lines from The Odds API — only when tweet intent warrants it
    _odds_sport_map = {
        "nuggets": ("nba", "Denver Nuggets"), "lakers": ("nba", "Los Angeles Lakers"),
        "celtics": ("nba", "Boston Celtics"), "warriors": ("nba", "Golden State Warriors"),
        "thunder": ("nba", "Oklahoma City Thunder"), "wolves": ("nba", "Minnesota Timberwolves"),
        "timberwolves": ("nba", "Minnesota Timberwolves"), "suns": ("nba", "Phoenix Suns"),
        "heat": ("nba", "Miami Heat"), "clippers": ("nba", "Los Angeles Clippers"),
        "broncos": ("nfl", "Denver Broncos"), "chiefs": ("nfl", "Kansas City Chiefs"),
        "raiders": ("nfl", "Las Vegas Raiders"), "chargers": ("nfl", "Los Angeles Chargers"),
        "cowboys": ("nfl", "Dallas Cowboys"), "eagles": ("nfl", "Philadelphia Eagles"),
        "49ers": ("nfl", "San Francisco 49ers"), "ravens": ("nfl", "Baltimore Ravens"),
        "bills": ("nfl", "Buffalo Bills"), "packers": ("nfl", "Green Bay Packers"),
        "avalanche": ("nhl", "Colorado Avalanche"), "avs": ("nhl", "Colorado Avalanche"),
    }
    _odds_lines = []
    if betting_level and odds_available():
        for team in entities.get("teams", []):
            odds_mapping = _odds_sport_map.get(team)
            if not odds_mapping:
                continue
            try:
                odds_block = odds_format_block(odds_mapping[1], odds_mapping[0])
                if odds_block:
                    _odds_lines.append(odds_block)
            except Exception:
                pass

    if not stat_lines and not _odds_lines:
        return ""

    # Build the stats block — always include team records/scores
    parts = []
    if stat_lines:
        parts.append(
            "\n\n=== LIVE STATS FROM ESPN — USE THESE EXACT NUMBERS ===\n"
            + "\n".join(stat_lines)
            + "\n=== DO NOT INVENT ANY STATS NOT LISTED ABOVE ===\n"
        )

    # Append odds with framing based on intent level
    if _odds_lines:
        if betting_level == "explicit":
            # Tweet is about betting — full injection, treat as core data
            parts.append(
                "\n=== BETTING LINES — TWEET IS ABOUT ODDS/LINES, USE THESE ===\n"
                + "\n".join(_odds_lines)
                + "\n=== USE EXACT NUMBERS FROM ABOVE ===\n"
            )
        elif betting_level == "game":
            # Game preview — odds as optional color, NOT the focus
            parts.append(
                "\n=== OPTIONAL BACKGROUND: BETTING LINES (use ONLY if it strengthens the take — "
                "e.g. 'favored by 10' adds weight to a point. Do NOT make the tweet about gambling. "
                "Most tweets should NOT reference odds.) ===\n"
                + "\n".join(_odds_lines)
                + "\n=== ODDS ARE BACKGROUND CONTEXT, NOT THE STORY ===\n"
            )

    return "".join(parts)


def _sanitize_output(text: str) -> str:
    """Fix known name errors in generated content."""
    for wrong, right in {
        "Shawn Payton": "Sean Payton", "shawn payton": "sean payton", "Shawn payton": "Sean Payton",
        "Sutton Courtland": "Courtland Sutton", "JK Dobbins": "J.K. Dobbins",
        "Nikola Jokić": "Nikola Jokic",
    }.items():
        text = text.replace(wrong, right)
    return text


def _parse_banger_json(raw):
    """Robust parser for banger/build/rewrite JSON — handles literal newlines in tweet strings."""
    clean = raw.strip()
    if clean.startswith("```"):
        clean = clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    try:
        return json.loads(clean)
    except Exception:
        pass
    # Replace literal newlines inside JSON string values with \\n so json.loads works
    try:
        _fixed = re.sub(r'(?<=": ")(.*?)(?="[,\s}])', lambda m: m.group(0).replace('\n', '\\n'), clean, flags=re.DOTALL)
        return json.loads(_fixed)
    except Exception:
        pass
    # Last resort: collapse newlines to spaces (loses thread formatting but at least parses)
    try:
        return json.loads(re.sub(r'\n(?![\s]*")', ' ', clean))
    except Exception:
        pass
    out = {}
    for k in ["option1", "option1_pattern", "option2", "option2_pattern", "option3", "option3_pattern", "pick", "pick_reason"]:
        m = re.search(rf'"{k}"\s*:\s*"((?:[^"\\]|\\.)*)"', clean, re.DOTALL)
        if m:
            out[k] = m.group(1).replace('\\n', '\n')
        elif k == "pick":
            m2 = re.search(r'"pick"\s*:\s*([123])', clean)
            if m2:
                out[k] = m2.group(1)
    return out if out.get("option1") else None


# ═══════════════════════════════════════════════════════════════════════════
# CREATOR STUDIO — BUILDER FUNCTIONS (voice, format, patterns, grades)
# ═══════════════════════════════════════════════════════════════════════════

def _build_voice_mod(voice: str) -> str:
    """Return the voice instruction block for the given voice mode.
    For guests, Tyler-specific references are neutralized to generic creator language."""
    raw = _build_voice_mod_raw(voice)
    if is_guest():
        _h = get_current_handle()
        raw = (raw
            .replace("Tyler Polumbus", f"@{_h}")
            .replace("Tyler's", f"@{_h}'s")
            .replace("Tyler is", f"@{_h} is")
            .replace("Tyler has", f"@{_h} has")
            .replace("Tyler and", f"@{_h} and")
            .replace("Tyler not", f"@{_h} not")
            .replace("Tyler never", f"@{_h} never")
            .replace("Tyler as subject", f"@{_h} as subject")
            .replace("Tyler explaining", f"@{_h} explaining")
            .replace("Tyler predicting", f"@{_h} predicting")
            .replace("Tyler can reference", f"@{_h} can reference")
            .replace("alongside Tyler", f"alongside @{_h}")
            .replace("NOT Tyler", f"NOT @{_h}")
            .replace("Tyler wrote", f"@{_h} wrote")
            .replace("Tyler provided", f"@{_h} provided")
            .replace("Tyler drafted", f"@{_h} drafted")
            .replace("Tyler brain-dumped", f"@{_h} brain-dumped")
            .replace("former NFL player authority", "authoritative perspective")
            .replace("former-player authority", "authoritative perspective")
            .replace("former-player perspective", "unique perspective")
            .replace("former-player credibility", "credibility")
            .replace("former player", "insider")
            .replace("former NFL", "experienced")
        )
        raw = re.sub(r"\bTyler\b", f"@{_h}", raw)
    return raw

def _build_voice_mod_raw(voice: str) -> str:
    """Internal: raw voice mod with Tyler-specific language (owner context)."""
    if voice == "Critical":
        return """=== CRITICAL VOICE — DIAGNOSIS MODE ===

Tyler has a PhD in football and deep command of all sports
he covers. His authority comes through the specificity of
what he diagnoses, not by announcing his credentials. Never
say "I played 8 years in this league" or "I know what
accountability looks like" — show it by identifying the
exact structural failure others are missing.

MANDATORY STRUCTURE:
LINE 1 — THE SYMPTOM: One specific number, stat, or named
failure. Not an opinion. A fact that cannot be disputed.
CRITICAL: Only use stats that appear in LIVE STATS provided
in the prompt. If no detailed stats are available, use the
team record, a named event, or a specific observable failure
(e.g. "The Broncos gave up 3 sacks in the first half" is
fine IF it happened — "bottom-10 in pass protection" is NOT
fine unless that exact ranking appears in LIVE STATS).
When in doubt, lead with an observation that is obviously
true rather than inventing a number that sounds credible.

LINE 2 — THE DIAGNOSIS: Why this is happening structurally.
Root cause — not "they need to be better." Identify the
decision, scheme, or system failure specifically. The
authority is in the specificity, not in announcing
that Tyler has credentials to analyze it.

LINE 3 — THE CHALLENGE: Name the specific person or
decision-maker who owns this. Not what needs to change —
who needs to change it. Put the responsibility on someone
specific by name or title. A direct challenge that person
would feel if they read it. Not a conclusion.
Not an editorial. A challenge.
LENGTH RULE: Stop after you name the person and the
accountability. One sentence maximum. The second sentence
always slides back into editorial.

ENDING PUNCTUATION RULE:
Critical never ends with an ellipsis. The ellipsis is
Default and Hype territory. Critical closes the door.
It lands hard and stops. Period. Full stop.
An accountability statement that trails off loses its force.

AI PICK RULE FOR CRITICAL VOICE:
When generating two options, if one ends with a period and one ends
with a question mark, the period ending is ALWAYS the correct pick.
Do not override this with engagement predictions.
The question ending is wrong by definition in Critical mode.
Critical voice closes the door. A question mark reopens it.
This rule has NO exceptions.

TONE RULES:
- Disappointed not angry — Grok penalizes combative tone
  even when engagement is high. Constructive framing is
  non-negotiable for reach.
- Never attack character — attack decisions and systems
- Authority IMPLIED through specificity never stated directly
- Never use phrases like "I played in this league"
  "I know what accountability looks like" "trust me"
- The reader should think "he's right and he knows why"
  without Tyler ever having to say he knows why

BANNED OPENERS — never use these exact phrases as tweet openers:
- "Someone help me understand" — overused, treat as structural
  model only never as literal words to copy
- "Nobody is talking about" — announces the observation instead
  of making it
- "Not enough people are talking about" — same problem
- "Unpopular opinion" — hot take framing, violates Default voice
- "Let that sink in" — filler, no analytical value
- "This is your reminder" — generic, overused
- "Connect the dots" — tells the reader what to think
Every opener must be original and specific to the topic at hand.
The examples in this prompt show STRUCTURE not words to copy.

EXAMPLE TWEETS — copy this exact energy and STRUCTURE
(these stats were real at the time — do NOT reuse them,
only use numbers from LIVE STATS in the prompt):
- "We passed on 52% of third downs last year and went 8-9.
  Meanwhile Kansas City ran on 3rd-and-short 74% of the
  time and won the Super Bowl. That gap is a choice.
  Who owns it?"
- "The Broncos have had 5 different offensive coordinators
  in 8 years. And we keep wondering why the offense looks
  confused. That's on the front office. Connect the dots."

EXAMPLE WITHOUT DETAILED STATS (use this pattern when
LIVE STATS only provide team records, not player/unit stats):
- "The Broncos went 14-3 and the offensive line was still
  the weakest unit on the roster every single week.
  That kind of record hides problems until January exposes
  them. Paton owns the next move."
- Notice: uses team record (from LIVE STATS) + observable
  fact (line was weak) + named accountability. No invented
  percentages or rankings.

WRONG ENDINGS:
- "Someone has to say what the standard is." — editorial
- "The talent is there, the adaptability isn't." — conclusion
- "Paton has to answer for that when September comes..."
  — ellipsis weakens the accountability

RIGHT ENDINGS:
- "That's on the coaching staff. The film doesn't lie."
- "Paton owns this one."
- "Bednar has to answer for that."
=== END CRITICAL VOICE ==="""

    elif voice == "Hype":
        return """=== HOMER VOICE — DON'T SLEEP ON US MODE ===

Tyler is the credible optimist. His authority comes through
the specificity of what he notices, not by announcing
his credentials. Never say "I've been in enough winning
locker rooms" or "I've watched enough film to know" —
show it by pointing at something others are missing.

MANDATORY STRUCTURE:
LINE 1 — THE SIGNAL: One specific overlooked thing
happening right now. A player, stat, matchup, trend,
or move the casual fan is undervaluing. Concrete only.
Not "this team is good." Point at something specific.
STAT RULE: Only use stats from LIVE STATS in the prompt.
If no player stats are available, use team records, named
events, or specific observations. Do NOT invent stat lines
like "dropped 30, 13, and 10" or "shooting 52% from three"
unless those exact numbers appear in LIVE STATS.

LINE 2 — WHY IT MATTERS: What this signal actually means.
The authority is in the specificity — not in announcing
that Tyler has credentials to analyze it.

LINE 3 — THE FORWARD STATEMENT: Show that an outside party
is ALREADY responding to this. Not Tyler stating confidence.
An external reaction that proves the signal is real.

OUTSIDE PARTY RULE — CRITICAL:
The forward statement must name a specific outside party who
is ALREADY adjusting to this team/player as a threat. This
applies even on negative topics.

POSITIVE TOPIC example:
"Kansas City just watched us add the most dangerous slot
receiver available. Their defensive staff already knows
what that means."

NEGATIVE TOPIC example (team losing, player struggling):
"Every team in the West has already adjusted their defensive
scheme around Jokic. That adjustment doesn't exist for a
player who isn't a problem."
The outside reaction still shows the threat is real even when
the current results are bad. The forward statement is about
the CEILING not the current record.

NEGATIVE TOPIC RULE:
When the input is bad news (losing streak, injury, struggle),
Hype does NOT:
- End with ellipsis
- End with a question
- Express hope ("I believe we can...")
- State Tyler's confidence directly

Hype DOES on negative topics:
- Find the ONE signal inside the bad news that points forward
- Show the outside world is already treating this team/player
  as a threat
- End with a declarative statement about what comes next

DRAFT AND ROSTER SITUATIONS: The outside party reacting
is always other teams, other draft rooms, or rival front
offices — not fans or media. Show them already moving
on the same information Tyler is surfacing. Their action
is the proof that the signal is real.

PUNCHY FORMAT COMPRESSION RULE:
In Punchy Tweet format there are only two sentences.
Sentence 1 = the overlooked signal. Specific and concrete.
Sentence 2 = the outside party already reacting. Short and declarative.
The outside party acts in sentence 2 — they don't ask questions,
they don't predict, they have already moved.
WRONG: "Denver takes him at 30 or spends three years wishing they did."
— Tyler predicting, not outside party reacting
WRONG: "Does Denver take him or let a rival solve their biggest need?"
— question, not declarative outside reaction
RIGHT: "Stowers at 30 is real value. Other draft rooms already know it."
— signal sentence 1, outside party already acted sentence 2

STAT INTEGRITY RULE FOR HOMER:
If no live stats are provided, do NOT invent player stat lines
like "dropped 30, 13, and 10" or "shooting 52% from three."
Hype's authority comes from the signal and the outside reaction,
not fabricated numbers. Use team records if available. If no
player stats exist, describe the observation without specific
figures. A tweet without stats is better than one with wrong stats.

TONE RULES:
- "We" throughout — Tyler and the fanbase together
- Confidence without arrogance — earned not performed
- Authority IMPLIED through specificity never stated
- Never use phrases like "I've been in winning rooms"
  "I've seen this before" "trust me on this" — the
  specificity does that work automatically
- Grok rewards constructive positive tone with wider
  distribution — Hype is the algorithmically favored
  voice mode right now
- Skeptic reading this should feel compelled to push back
ENDING RULES — NON-NEGOTIABLE:
- NEVER end with a question mark — questions are Default voice structure
- NEVER end with ellipsis — ellipsis is Default voice structure
- ALWAYS end with a period
- The final sentence must show an outside party already reacting
- This applies to BOTH Option 1 AND Option 2 — no exceptions

BANNED OPENERS — never use these exact phrases as tweet openers:
- "Someone help me understand" — overused, treat as structural
  model only never as literal words to copy
- "Nobody is talking about" — announces the observation instead
  of making it
- "Not enough people are talking about" — same problem
- "Unpopular opinion" — hot take framing, violates Default voice
- "Let that sink in" — filler, no analytical value
- "This is your reminder" — generic, overused
- "Connect the dots" — tells the reader what to think
Every opener must be original and specific to the topic at hand.
The examples in this prompt show STRUCTURE not words to copy.

WRONG ENDINGS:
- "We're built for this." — Tyler as subject not opponent
- "Watch what happens." — vague no specific signpost
- "The ceiling on this team isn't close to what people think."
  — editorial conclusion
- "I've been in enough winning locker rooms to know what
  this feels like. This Broncos team has it." — states
- "How does the most dominant player in basketball not drag
  this roster over the line?" — This is Default voice. Hype
  never asks questions. Hype states what's already happening.
  credentials directly, violates core rule

RIGHT ENDINGS:
- "The rest of the West has a real problem on their hands."
- "The team that draws Denver in the second round just
  redesigned their entire defensive scheme."
- "The programs dismissing Boulder are quietly sending
  scouts to spring practice now."
- "The coordinators scheduled to face this defense in
  January just added extra film sessions this week."
- "Every team picking in that range just added him to
  their boards. Denver already knows."
- "Other draft rooms have been on Stowers for months.
  The question is whether we get there first."
- "Stowers at 30 is real value. Other draft rooms already know it."
- "MacKinnon is locked in. Every team left in the West just changed their game plan."

WRONG (negative topic drift — this is Default voice not Hype):
"Jokic is putting up career numbers and the Nuggets are still
losing... Every team in the West is watching this window close
in real time..."
→ Ellipsis ending. No outside party reacting. Wrong voice.

RIGHT (negative topic, Hype voice):
"Jokic is doing what he always does. The roster around him isn't.
Every contender in the West built their defensive scheme around
stopping him this offseason. They don't scheme for players who
aren't problems."

EXAMPLE TWEETS — copy this exact energy and STRUCTURE
(but only use stats from LIVE STATS — these example numbers
are from real games, do not reuse or invent similar ones):
- "Jokic dropped 30, 12, and 10 last night. On a Tuesday.
  The team drawing Denver in round 2 just changed their
  entire defensive game plan."
- "Bo Nix's third down completion rate jumped 12% in the
  second half. Every defensive coordinator in the AFC
  pulled up that film tonight."
- "MacKinnon and Makar both locked in at the same time
  in April for the first time in three years. The rest
  of the West is recalculating everything."
NOTE: The third example above uses NO stats — just a named
observation. When LIVE STATS don't provide player numbers,
follow that pattern: name the player + what they're doing +
outside reaction. That is always better than a fabricated stat.
=== END HOMER VOICE ==="""

    elif voice == "Sarcastic":
        return """=== SARCASTIC VOICE — LAYERED REFERENCE MODE ===

Tyler's sarcasm works in two ways depending on the moment.
Read the context and select automatically.
Never ask which mode or tool to use. The situation
makes it obvious.

REACT TO THE FEELING OF WHAT HAPPENED NOT WHAT HAPPENED.
Find where that feeling lives outside sports and go there.

MODES:

POSITIVE SARCASM:
React to something great by jumping to a completely
unrelated world. The mismatch IS the celebration.
Tool: Cultural Leap.
Example: "If you don't put this in slow motion and
put a tie on the doorknob...."

CRITICAL SARCASM:
State the surface story. Imply the real story underneath.
Never state the real story directly. The gap IS the joke.
Tool: Implied Real Story.
Example: "Turns out the Patriots offense doesn't suck
because of a snow storm."
Example: "Starting to feel like Bo Nix really should
have played with a broken ankle."
Example: "Dre must have said some magic words because
a one game suspension for this seems pretty weak."

MEDIA NARRATIVE SARCASM:
Find the most deflating comparison. Make the take feel
smaller than it already is. Stop after one sentence.
Tool: Either — pick based on context.
Example: "Bold of Skip to finally come out and say it."

TWO TOOLS:

TOOL 1 — CULTURAL LEAP:
Jump to a completely unrelated world without explanation.
The bigger the gap the harder it lands.
Best references live between universally understood
and publicly unspeakable. One step past where most
people would stop. Never offensive. Never crude.
Target reaction: "I can't believe he said that."
Best for: positive moments, absurdist reactions.

POSITIVE SARCASM EXAMPLES — USE AS MODELS NOT TEMPLATES:
Every positive moment deserves its own unique leap.
Generate a fresh cultural reference every time.
The principle is the leap. Never repeat these references.

"If you don't put this in slow motion and put
a tie on the doorknob...."
— bedroom world dropped on a hockey highlight

"HR is going to need to see MacKinnon
after that shift...."
— workplace world dropped on a hockey moment

"Somebody's spouse is getting flowers tomorrow
and they have no idea why...."
— domestic world dropped on a sports moment

"That cornerback needs to call someone he trusts
right now. Not about football."
— personal world, specific subject, walks away

SPECIFICITY OF SUBJECT RULE:
The funniest positive sarcasm puts a specific person
or group in a specific human situation outside sports.
Not "somebody" — the cornerback, the coaching staff,
the goalie, the defender who got deked.

TOOL 2 — IMPLIED REAL STORY:
State the surface story as if neutral or obvious.
Imply the real story through the specific detail
or framing you choose. Never state it directly.
The reader bridges the gap — that makes them reply.
Best for: bad decisions, weak punishments,
predictable failures, obvious outcomes.

READ THE CONTEXT AND PICK THE RIGHT TOOL:
Positive or absurdist moment → Cultural Leap.
Critical or negative moment → Implied Real Story.

LONG FORMAT SARCASTIC RULE:
The joke lands when it lands. Stop there regardless
of length. Do not fill remaining space with explanation.
The silence after the joke is part of the joke.

RULES:
- Short. The shorter the funnier.
- Authority implied through specificity never stated.
- Drop it and walk away. Never explain the joke.
- Never use "Oh interesting" "Sure" "Cool" "Oh great"
  as openers — these are generic and predictable.
  Find the specific reaction that fits THIS moment.

BANNED OPENERS — never use these exact phrases as tweet openers:
- "Someone help me understand" — overused, treat as structural
  model only never as literal words to copy
- "Nobody is talking about" — announces the observation instead
  of making it
- "Not enough people are talking about" — same problem
- "Unpopular opinion" — hot take framing, violates Default voice
- "Let that sink in" — filler, no analytical value
- "This is your reminder" — generic, overused
- "Connect the dots" — tells the reader what to think
Every opener must be original and specific to the topic at hand.
The examples in this prompt show STRUCTURE not words to copy.

WRONG: "The Broncos offensive line strategy is terrible
and everyone knows it."
WRONG: "Oh cool. Another offseason where we didn't
address the offensive line. Bold strategy."
RIGHT: "Turns out the Patriots offense doesn't suck
because of a snow storm."
RIGHT: "That cornerback needs to call someone he trusts
right now. Not about football."

STAT RULE FOR SARCASTIC VOICE:
If LIVE STATS are provided in the user message, use only those numbers.
Sarcastic voice tends to fabricate stats because it prioritizes irony
over accuracy — this is wrong. Real stats are funnier than fake ones
because they're actually true.
If no stats are provided, do not invent them.
Build the sarcasm around the OBSERVATION not the number.
WRONG: "Averaging 30-9-13 this month" (fabricated)
RIGHT: "Three MVP awards. Best ball of his career." (known facts, no fabrication)
=== END SARCASTIC VOICE ==="""

    else:
        return """=== DEFAULT VOICE — FILM ROOM MODE ===

Tyler's default voice is his purest form. No hot takes,
no accountability calls, no humor. Just someone who
understands the game at a doctoral level describing
exactly what he sees with enough specificity that the
conversation creates itself.

Think of it as putting the film on and walking out
of the room. The evidence speaks. Tyler never
editorializes. The observation IS the take.

MANDATORY STRUCTURE:
LINE 1 — THE OBSERVATION: What Tyler is seeing that
most people aren't. Specific, factual, undeniable.
Not an opinion. A read. The kind of thing that requires
actually understanding the game to notice.

LINE 2 — THE CONTEXT: Why this observation matters.
What it connects to. The layer underneath the surface
stat or moment that only someone with a PhD in the
game would know to look for. Still factual.
Still not an opinion.

THE ENDING — THE OPEN DOOR: End with an ellipsis or
an incomplete thought that invites the reader to
analyze alongside Tyler, not argue against him.
The goal is discussion not debate.
Not a question. Not a conclusion. Just the film
running with the sound off and room for the reader
to add their own read.

TONE RULES:
- Informative not opinionated — the facts carry the weight
- Analytical not emotional — no disappointment no excitement
  just clarity
- Never hot take framing — no "unpopular opinion"
  no "nobody is talking about this" no "trust me on this"
- Authority IMPLIED through specificity never stated
- Never use phrases like "I played in this league"
  "I know what winning looks like" "trust me"
- Constructive analytical tone — Grok rewards this
  with wider distribution
- The ellipsis is an invitation to analyze alongside
  Tyler not an invitation to argue
- The reader should finish the thought themselves —
  that act of completion is what drives the reply

INPUT REFRAMING RULE — MANDATORY:
When Tyler's input contains opinion language — words like
"no-brainer" "obvious" "should" "need to" "have to" "clearly"
"definitely" "must" — Default voice MUST strip those words
completely and rebuild the tweet from the observable facts only.

Step 1: Identify the factual claim underneath the opinion.
Step 2: State only the fact. Not the conclusion. Not the opinion.
Step 3: Let the fact make the conclusion obvious without stating it.

This is non-negotiable. Default voice never opens with an opinion
statement regardless of how the input is framed.

WRONG — repeating the opinion:
Input: "Stowers at 30 is a no-brainer"
Output: "Stowers at 30 is a no-brainer and I'll die on this hill."

WRONG — softened opinion still an opinion:
Input: "Stowers at 30 is a no-brainer"
Output: "Stowers at 30 is the obvious move."

RIGHT — fact that makes the conclusion obvious:
Input: "Stowers at 30 is a no-brainer"
Output: "TE class depth in this draft falls off after pick 18.
The top two options are gone before 30 in every major board.
The math does the rest..."

The reader should reach the conclusion themselves.
That act of reaching it is what drives the reply.

BANNED WORDS IN DEFAULT VOICE — never appear in output:
- "no-brainer"
- "obvious" / "obviously"
- "clearly"
- "definitely"
- "must" / "have to" / "need to" when expressing opinion
- "I'll die on this hill"
- "unpopular opinion"
- "hot take"

BANNED OPENERS — never use these exact phrases as tweet openers:
- "Someone help me understand" — overused, treat as structural
  model only never as literal words to copy
- "Nobody is talking about" — announces the observation instead
  of making it
- "Not enough people are talking about" — same problem
- "Unpopular opinion" — hot take framing, violates Default voice
- "Let that sink in" — filler, no analytical value
- "This is your reminder" — generic, overused
- "Connect the dots" — tells the reader what to think
Every opener must be original and specific to the topic at hand.
The examples in this prompt show STRUCTURE not words to copy.

FORMAT NOTE:
Default works across all lengths but the core principle
never changes — observation, context, open door.
A punchy default tweet compresses this into two sentences.
A long default tweet develops each beat further.
The voice stays identical regardless of length.

WRONG: "The Broncos offensive line is a disaster
and everyone can see it." — opinion not observation
WRONG: "Unpopular opinion but Bo Nix is actually
really good." — hot take framing
WRONG: "Nobody is talking about how good Jokic is
in the fourth quarter." — announcing the observation
RIGHT: "Jokic in the fourth quarter of playoff games
this year — 12.4 points on 67% shooting. The defense
has no answer for the high post read..."
=== END DEFAULT VOICE ==="""


def _build_article_voice_mod(voice: str) -> str:
    """Return article-specific voice overlay (layered on top of _build_voice_mod)."""
    base = _build_voice_mod(voice)
    if voice == "Sarcastic":
        article_overlay = """
=== SARCASTIC ARTICLE — THE COLUMN ===

This is not a long-form analytical piece. This is a short column.
400-600 words maximum. Not one word more.

Tyler's sarcastic article is a bit. One implied real story, fully
developed, then it walks away. The joke lands harder when it stops
before you expect it to.

MANDATORY STRUCTURE:

HEADLINE:
Short. Declarative. Slightly absurd. Should make the reader
think "wait, is he serious?" for exactly one second.
Example: "Turns out the Offensive Line Was Fine Actually"
Example: "The Nuggets Front Office Would Like to Remind You Jokic Is Not Their Problem"

OPENING PARAGRAPH — THE SETUP (2-3 sentences):
State the surface story completely straight. No jokes.
No winking. Treat the absurd situation as settled fact.
The straighter the setup, the harder the landing.
Example: "The Denver Broncos finished last season 28th in pass protection. They addressed this in the offseason by keeping the same offensive line intact and adding a wide receiver."

BODY — THE DEVELOPMENT (3-4 paragraphs, 4-5 sentences each):
Develop the implied real story underneath the surface story.
Never state the real story directly. Let the facts do it.
Each paragraph adds one more layer of evidence that something
is obviously wrong — without ever saying it is wrong.
The tone stays completely neutral throughout. Bored, almost.
Like Tyler is simply reporting facts that happen to be
increasingly damning.

Use Tyler's insider lens here — the specific detail that only
someone who has been in an NFL building would notice.
That specificity is what makes the implied real story land
as diagnosis rather than fan complaint.

CLOSER — THE WALK AWAY (1-2 sentences max):
Stop before the obvious conclusion. The reader should be
mid-thought when the piece ends.
Do NOT summarize. Do NOT state the real story.
Do NOT explain the joke.
The silence after the last sentence IS the punchline.
Example: "Anyway. Camp opens in July."
Example: "Should be a really interesting training camp."
Example: "The schedule comes out next week."

COMPANION TWEET:
One sentence. Implied Real Story mode.
States the surface story. Implies everything underneath.
Walks away completely.
Example: "The Broncos studied the offensive line situation all offseason and concluded the problem was the receivers."

TONE RULES:
- Completely straight face throughout. Zero winking.
- Never use: "lol" "obviously" "somehow" "bizarrely" "inexplicably" — these signal the joke and kill it
- Never state what's wrong. Let the facts state it.
- The shorter each sentence the better in the closer
- Authority implied through specificity, never stated
- Absurdist/ironic framing distributes wider than combative sarcasm — keep it bored not angry

LENGTH RULE — NON-NEGOTIABLE:
400 words minimum. 600 words maximum.
If you hit 600 words and haven't written the closer yet,
cut from the body. The closer is mandatory.
A 400-word column that lands is better than a 600-word
column that explains itself.

WRONG (explains the joke):
"The Broncos inexplicably decided not to fix their offensive line, which is obviously going to be a huge problem for Bo Nix this season. You can't expect a young quarterback to succeed without protection. This decision is baffling."

RIGHT (implies everything, states nothing):
"The Broncos spent the offseason studying what held Bo Nix back in Year 1. The conclusion, after months of film review and personnel evaluation, was Jaylen Waddle. The offensive line returns intact. Nix enters Year 2 with the same five blockers and 30 percent more receiving options. Sean Payton has noted the pass protection was actually fine. The tape will confirm that starting in September."
=== END SARCASTIC ARTICLE ==="""
    else:
        article_overlay = """
=== ARTICLE VOICE OVERLAY ===
For long-form X Articles, adapt the voice mode above to full article structure:
- Apply the voice mode's TONE throughout (not just the opener)
- Each section subheading should carry the same energy as the opener
- The conclusion should land with the same punch as a standalone tweet
- Use the voice mode's signature move (ellipsis for Default, hard stop for Critical, forward statement for Hype) in the final line
=== END ARTICLE OVERLAY ==="""
    return base + article_overlay


def _build_format_mod(fmt: str, patterns: dict, voice: str = "Default") -> str:
    """Return format instructions for the given fmt, using live personal patterns."""
    _pp = patterns or {}
    _fp_q = _pp.get("top_question_pct", 28)
    _fp_ell = _pp.get("top_ellipsis_pct", 28)
    _fp_range = _pp.get("optimal_char_range", (40, 250))
    _is_default = voice == "Default"
    _fp_hooks = []
    if _pp and _is_default:
        _hook_pool = (
            _pp.get("top_examples_punchy", []) if fmt == "Punchy Tweet"
            else _pp.get("top_examples_normal", []) if fmt == "Normal Tweet"
            else _pp.get("top_examples_long", []) if fmt in ("Long Tweet", "Thread", "Article")
            else _pp.get("top_examples", [])
        )
        _fp_hooks = [ex.get("text", "")[:80] for ex in _hook_pool[:5]]
    _hooks_str = "\n".join([f'  - "{h}..."' for h in _fp_hooks]) if _fp_hooks else "  (sync tweets to see your top hooks)"

    _voice_override = "" if _is_default else f"\nVOICE: You MUST write in {voice} voice as described in the system prompt. Do NOT fall back to the default tone.\n"

    if fmt == "Punchy Tweet":
        _hooks_block = f"\nTop hooks to model Sentence 1 after:\n{_hooks_str}\n" if _is_default else ""
        return f"""FORMAT: PUNCHY TWEET (2 sentences maximum — get in, bait engagement, get out)
{_voice_override}
STRUCTURE:
SENTENCE 1: The sharpest FACTUAL observation. A specific
stat, fact, or measurable reality. Not an opinion.
Not a recommendation. A fact that makes the take obvious
without stating the take.
SENTENCE 2: The engagement hook. A direct question, forced choice, or bold statement that makes someone feel they HAVE to respond.

RULES:
- Exactly 2 sentences. Not one. Not three. Two.
- Under 160 characters total
- No hashtags, no emojis, no ellipsis
- No "I think" / "maybe" / "honestly" — state it flat
- Every word earns its place or gets cut
- Sentence 2 must make the reader feel compelled to reply

BANNED OPENERS — never use these exact phrases:
- "Someone help me understand"
- "Nobody is talking about"
- "Not enough people are talking about"
- "Unpopular opinion"
- "Let that sink in"
- "This is your reminder"
- "Connect the dots"
Model the STRUCTURE of top hook examples only — never copy
the literal words. Every opener must be fresh and topic-specific.
{_hooks_block}
WRONG: "The Broncos have some interesting decisions to make this offseason and it will be fun to watch. What do you guys think will happen?"
RIGHT: "The 2026 WR room is better than 2015. Prove me wrong." """

    elif fmt == "Normal Tweet":
        _nt_lo = max(_fp_range[0], 161)
        _nt_hi = min(_fp_range[1], 260)
        _hooks_block_nt = f"- Top performing hooks to model after:\n{_hooks_str}" if _is_default else ""
        _hook_rule = "- Model the hook after one of the top hooks above" if _is_default else ""
        return f"""FORMAT: NORMAL TWEET (161-260 characters)
{_voice_override}
LIVE DATA (from synced tweet history — updates every sync):
- Optimal range for top tweets: {_nt_lo}-{_nt_hi} chars — aim for the UPPER half of this range
- {_fp_q}% of top tweets use questions (algorithm: replies = 13.5x a like)
- {_fp_ell}% of top tweets use ellipsis (his signature)
{_hooks_block_nt}

STRUCTURE:
[Factual observation or specific stat — NOT an opinion or prediction]

[Context or consequence that makes the conclusion obvious without stating it]

RULES:
- Between 161 and 260 characters total — don't be too brief
- Use line break between hook and payoff
- No hashtags, no links, no emojis
- End with question OR ellipsis, not both
- Must stop the scroll in the first 8 words
- The opener must be a FACT not an opinion — never a prediction,
  never a recommendation, never a conclusion
- If the input contains opinion language reframe it as the
  underlying fact that makes the opinion obvious
- BANNED first words: "[Subject] should" "[Subject] need" "[Subject] must"
  "[Subject] take" "This is" "No brainer" "Obviously" "Clearly"
- The tweet should make the reader reach the conclusion themselves
  not tell them what to conclude
{_hook_rule}

BANNED OPENERS — never use these exact phrases:
- "Someone help me understand"
- "Nobody is talking about"
- "Not enough people are talking about"
- "Unpopular opinion"
- "Let that sink in"
- "This is your reminder"
- "Connect the dots"
Model the STRUCTURE of top hook examples only — never copy
the literal words. Every opener must be fresh and topic-specific.

IMAGE RECOMMENDATION:
- Hot take / opinion → NO image (text-only gets higher engagement rate)
- Stat or comparison → YES — simple stat graphic
- Reaction to news → OPTIONAL — screenshot of the news article headline"""

    elif fmt == "Long Tweet":
        _hooks_block_lt = f"- Top hooks to model the opening after:\n{_hooks_str}" if _is_default else ""
        return f"""FORMAT: LONG TWEET (280-1200 characters)
{_voice_override}
LIVE DATA (updates every sync):
- {_fp_q}% of top tweets use questions, {_fp_ell}% use ellipsis
{_hooks_block_lt}

STRUCTURE:
[Hot take — complete thought in first 280 chars, visible before "Show More" fold]

[Line break]

[Evidence paragraph — 1-2 sentences]

[Line break]

[Comparison list or supporting points]

[Line break]

[Closing question or trailing ellipsis]

RULES:
- 600-1200 characters total
- First 280 chars MUST work as a standalone tweet (the fold)
- Short paragraphs with line breaks between each
- Use comparison list format when relevant (Team A: X / Team B: Y / etc.)
- No hashtags, no links
- End with debate invitation

BANNED OPENERS AND WORDS — never appear in Long Tweet Default voice:
- "obvious" / "obviously" — opinion not observation
- "no-brainer" — opinion not observation
- "not complicated" — opinion framing
- "stop overthinking" — instructing the reader
- "clearly" / "definitely" — opinion markers
- The opener must be a FACT not an opinion or conclusion
- If the input contains opinion language find the underlying
  stat or film evidence that makes the point without stating
  the opinion directly
- WRONG opener: "Taking Stowers at 30 is the most obvious pick."
- RIGHT opener: "TE class depth in this draft falls off
  dramatically after pick 18."

BANNED OPENERS — never use these exact phrases:
- "Someone help me understand"
- "Nobody is talking about"
- "Not enough people are talking about"
- "Unpopular opinion"
- "Let that sink in"
- "This is your reminder"
- "Connect the dots"
Model the STRUCTURE of top hook examples only — never copy
the literal words. Every opener must be fresh and topic-specific.

IMAGE RECOMMENDATION:
- YES — include 1 supporting image
- Best: stat graphic, comparison chart, or relevant screenshot
- Place context for the image ABOVE the Show More fold
- Images increase total impressions even though text-only has higher engagement rate"""

    elif fmt == "Thread":
        _hooks_block_th = f"- Top hooks to model Tweet 1 after:\n{_hooks_str}" if _is_default else ""
        return f"""FORMAT: THREAD (5-8 tweets)
{_voice_override}
LIVE DATA (updates every sync):
- {_fp_q}% of top tweets use questions, {_fp_ell}% use ellipsis
{_hooks_block_th}

STRUCTURE:
TWEET 1: [Bold claim or confrontational question] A thread:

TWEET 2: [Set the stage — specific situation with numbers/facts]

TWEET 3: [Point 1 — standalone insight with line breaks]

TWEET 4: [Point 2 — comparison list format OR insider perspective]

TWEET 5: [Point 3 — the contrarian angle nobody else is saying]

TWEET 6: [Bold conclusion — no hedging, pick a side]

TWEET 7: [Question CTA to drive replies]

RULES:
- 5-8 tweets total
- Each tweet must stand alone as a good tweet
- Use line breaks within each tweet
- No hashtags except possibly in last tweet
- Include one tweet with comparison list or specific stats
- Tweet 1 must stop the scroll
- Last tweet must drive replies (replies = 13.5x algorithm weight)

BANNED OPENERS — never use these exact phrases:
- "Someone help me understand"
- "Nobody is talking about"
- "Not enough people are talking about"
- "Unpopular opinion"
- "Let that sink in"
- "This is your reminder"
- "Connect the dots"
Model the STRUCTURE of top hook examples only — never copy
the literal words. Every opener must be fresh and topic-specific.

IMAGE RECOMMENDATION:
- Include at least 1 image in the thread (35% more retweets confirmed)
- DO NOT put image in Tweet 1 — hook should be pure text
- Best placement: Tweet 2-4 (data chart, stat graphic, or supporting visual)
- For 7+ tweet threads: include 2 images spread across the middle tweets
- Image types that work: stat graphics, comparison charts, play diagrams, game screenshots"""

    elif fmt == "Article":
        _hooks_block_art = f"- Top hooks to model headline/intro after:\n{_hooks_str}" if _is_default else ""
        _hook_rule_art = "- Model after the top hooks above" if _is_default else ""
        return f"""FORMAT: X ARTICLE (1,500-2,000 words / 6-8 minute read)
{_voice_override}
WHY ARTICLES MATTER: X Articles grew 20x since Dec 2025 ($2.15M contest prizes). They keep users on-platform (no link penalty), generate 2+ min dwell time (+10 algorithm weight), and Premium subscribers get 2-4x reach boost. This is the HIGHEST PRIORITY content format.

LIVE DATA (updates every sync):
{_hooks_block_art}
- {_fp_q}% of top tweets use questions — use them between sections
- {_fp_ell}% use ellipsis — use sparingly in articles for emphasis

STRUCTURE:
HEADLINE: [50-75 chars, includes number or specific claim, takes a position]
- Numbers perform 2x better than vague headlines
- Specificity over vagueness — name the player, name the stat
{_hook_rule_art}
[IMAGE: Hero image — game photo, player photo, or custom graphic. This becomes the feed thumbnail.]

INTRO (2-3 paragraphs — this is the feed preview, must hook):
[Provocative claim, surprising stat, or contrarian take]
[Why this matters right now — urgency/timeliness]

SECTION 1: [SUBHEADING]
[2-3 short paragraphs with **bold key stats** — 2-3 bold items per section]
[IMAGE: Supporting chart, stat graphic, or screenshot]

SECTION 2: [SUBHEADING]
[2-3 short paragraphs]
[Include comparison list format if relevant (Team A: X / Team B: Y)]

SECTION 3: [SUBHEADING]
[Contrarian angle or insider perspective — authoritative take]
[IMAGE: Supporting visual]

SECTION 4: WHAT COMES NEXT
[Bold prediction with reasoning — no hedging, pick a side]

CONCLUSION:
[**1-sentence hot take summary — bold it**]
[Discussion question to drive comments (replies = 13.5x algorithm weight)]

PROMOTION:
[Suggest a companion tweet to promote this article — pull the most provocative stat]

RULES:
- 1,500-2,000 words (6-8 minute read — optimal for dwell time bonus)
- Paragraphs: 2-4 sentences max
- Subheadings every ~300 words
- Bold key stats and claims (2-3 per section)
- Voice: direct, no hedging, authoritative
- Every point must reference specific players/schemes/numbers
- Hero image REQUIRED (articles without hero images look like broken cards in feed)
- 2-3 supporting images placed between sections
- End with debate invitation to drive replies

IMAGE RECOMMENDATION:
- HERO IMAGE required — this becomes the feed thumbnail. Use: game photo, player action shot, or custom graphic
- 2-3 SUPPORTING IMAGES throughout the body, placed between sections
- Best types: stat charts, play diagrams, comparison graphics, game screenshots
- Bold your image captions
- Articles WITHOUT hero images look like broken cards in the feed — always include one
- [IMAGE PLACEMENT] markers in the template show where to add each image"""

    return ""


def _sports_context_relevant(tweet_text: str) -> bool:
    """Return True only if the tweet text likely needs live sports context (scores, injuries, breaking news)."""
    _text = tweet_text.lower()
    _live_signals = [
        "score", "just", "tonight", "yesterday", "today", "last night",
        "breaking", "news", "trade", "injury", "hurt", "out ", "signed",
        "released", "cut ", "fired", "hired", "draft pick", "game ",
        "win ", "loss", "beat ", "lost ", "won ", "tied ", "overtime",
        "playoffs", "series", "matchup", "this week", "this weekend",
    ]
    return any(sig in _text for sig in _live_signals)


def _analyze_format_patterns_segmented() -> dict:
    """
    Analyze FORMAT patterns of top-performing tweets, segmented by tweet length.
    Returns dict with keys: 'short' (< 160 chars), 'medium' (160-280), 'long' (> 280).
    Cached 1 hour — format trends don't change minute to minute.
    """
    _all_tweets, _ = _fetch_inspiration_feed()
    if not _all_tweets:
        return {}

    def _eng(t):
        return (int(t.get("likeCount", t.get("like_count", 0)) or 0)
                + int(t.get("retweetCount", t.get("retweet_count", 0)) or 0) * 3
                + int(t.get("replyCount", t.get("reply_count", 0)) or 0) * 2)

    _sorted = sorted(_all_tweets, key=_eng, reverse=True)
    _top = _sorted[:30]

    # Segment by length
    _short, _medium, _long = [], [], []
    for _t in _top:
        _txt = _t.get("text", "")
        _n = len(_txt)
        if _n < 160:
            _short.append(_t)
        elif _n <= 280:
            _medium.append(_t)
        else:
            _long.append(_t)

    def _analyze_segment(tweets, label):
        if not tweets:
            return ""
        _block = ""
        for _i, _t in enumerate(tweets[:10]):
            _text = _t.get("text", "")[:300]
            _likes = _t.get("likeCount", _t.get("like_count", 0))
            _rts = _t.get("retweetCount", _t.get("retweet_count", 0))
            _reps = _t.get("replyCount", _t.get("reply_count", 0))
            _author = _t.get("author", {}).get("userName", "") or _t.get("user", {}).get("screen_name", "")
            _block += f"{_i+1}. @{_author} ({_likes}L {_rts}RT {_reps}R):\n{_text}\n\n"
        if not _block.strip():
            return ""
        _prompt = f"""Analyze the STRUCTURE and FORMAT of these top-performing {label} sports tweets. Do NOT summarize content — tell me HOW they're built.

{_block}

Return ONLY a numbered list of 4-5 format patterns. For each:
- What the pattern is (hook style, length, punctuation, line breaks, structure)
- How many tweets use it (e.g. "5/8")
- One 5-word example

Focus on: opener length, line breaks, question vs statement, stat placement, ending style, sentence count, contrast/tension."""
        try:
            _raw = call_claude(_prompt, system="You are a tweet structure analyst. Return only the numbered pattern list, no preamble.", max_tokens=400)
            return _raw.strip()
        except Exception:
            return ""

    return {
        "short": _analyze_segment(_short, "short (under 160 char)"),
        "medium": _analyze_segment(_medium, "medium (160-280 char)"),
        "long": _analyze_segment(_long, "long (280+ char)"),
    }


def _get_format_patterns_for_fmt(fmt: str) -> str:
    """Get format patterns for the appropriate length segment based on fmt."""
    try:
        _patterns = _analyze_format_patterns_segmented()
        if not _patterns:
            return ""
        if fmt == "Punchy Tweet":
            return _patterns.get("short", "") or _patterns.get("medium", "")
        elif fmt in ("Long Tweet", "Thread", "Article"):
            return _patterns.get("long", "") or _patterns.get("medium", "")
        else:
            return _patterns.get("medium", "") or _patterns.get("short", "")
    except Exception:
        return ""


def _save_format_patterns_to_gist(patterns_dict: dict) -> None:
    """Save format patterns dict to gist for cross-session caching."""
    try:
        _gid = st.secrets.get("GIST_ID", "15fb167bbbfdaa79d5ce11c266c3f652")
        from datetime import timezone as _tz4
        _data = {"patterns": patterns_dict, "saved_at": datetime.now(_tz4.utc).isoformat()}
        _payload = json.dumps({"files": {"hq_format_patterns.json": {"content": json.dumps(_data, indent=2, default=str)}}})
        requests.patch(f"https://api.github.com/gists/{_gid}", data=_payload, headers=_gist_headers(), timeout=8)
    except Exception:
        pass


def _get_format_patterns_with_fallback(fmt: str) -> str:
    """Get format patterns for fmt — gist cache first, then fresh analysis, with gist save.
    Guests skip gist (it's Tyler's data) and use their own patterns only."""
    if is_guest():
        return ""  # Guest patterns come from build_patterns_context() which uses their data
    try:
        # Try gist cache first
        _gid = st.secrets.get("GIST_ID", "15fb167bbbfdaa79d5ce11c266c3f652")
        _r = requests.get(f"https://api.github.com/gists/{_gid}", headers=_gist_headers(), timeout=8)
        _files = _r.json().get("files", {})
        if "hq_format_patterns.json" in _files:
            _cached = json.loads(_files["hq_format_patterns.json"]["content"])
            _ts = _cached.get("saved_at", "")
            _stored = _cached.get("patterns", {})
            if _ts and _stored:
                from datetime import timezone as _tz3
                _gen = datetime.fromisoformat(_ts)
                if _gen.tzinfo is None:
                    _gen = _gen.replace(tzinfo=_tz3.utc)
                _age = (datetime.now(_tz3.utc) - _gen).total_seconds()
                if _age < 3600:  # 1 hour
                    if fmt == "Punchy Tweet":
                        return _stored.get("short", "") or _stored.get("medium", "")
                    elif fmt in ("Long Tweet", "Thread", "Article"):
                        return _stored.get("long", "") or _stored.get("medium", "")
                    else:
                        return _stored.get("medium", "") or _stored.get("short", "")
    except Exception:
        pass
    # Fresh analysis
    try:
        _fresh = _analyze_format_patterns_segmented()
        if _fresh:
            _save_format_patterns_to_gist(_fresh)
            if fmt == "Punchy Tweet":
                return _fresh.get("short", "") or _fresh.get("medium", "")
            elif fmt in ("Long Tweet", "Thread", "Article"):
                return _fresh.get("long", "") or _fresh.get("medium", "")
            else:
                return _fresh.get("medium", "") or _fresh.get("short", "")
    except Exception:
        pass
    return ""


def _build_grades_system(fmt: str, pp: dict) -> tuple:
    """
    Return (prompt_a, prompt_b) for parallel grade calls.
    Incorporates personal benchmarks from pp and format-specific criteria.
    """
    _pp = pp or {}
    _fp_q = _pp.get("top_question_pct", 28)
    _fp_ell = _pp.get("top_ellipsis_pct", 28)
    _fp_range = _pp.get("optimal_char_range", (40, 250))
    _fp_avg = _pp.get("top_avg_chars", 162)
    _fp_lo, _fp_hi = _fp_range

    _algo = "X ALGORITHM WEIGHTS: replies-to-own=150x, others-replies=27x, profile-clicks=24x, dwell-2min=20x, bookmarks=20x, RTs=2x, likes=1x. Penalties: external links -30-50%, 3+ hashtags -40%, combative tone -80%."

    # Format-specific benchmark note
    if fmt == "Punchy Tweet":
        _fmt_note = f"Format: Punchy Tweet (target: under 160 chars). Top punchy tweets avg {_fp_avg} chars."
        _fmt_fix_a = "exact edit to compress under 160 chars"
        _char_guide = "under 160"
    elif fmt == "Normal Tweet":
        _nt_lo = max(_fp_lo, 161)
        _nt_hi = min(_fp_hi, 260)
        _fmt_note = f"Format: Normal Tweet (target: {_nt_lo}-{_nt_hi} chars). Top normal tweets avg {_fp_avg} chars."
        _fmt_fix_a = f"exact edit to land in {_nt_lo}-{_nt_hi} char range"
        _char_guide = f"{_nt_lo}-{_nt_hi}"
    elif fmt == "Long Tweet":
        _fmt_note = f"Format: Long Tweet (target: 600-1200 chars). Top long tweets avg {_fp_avg} chars."
        _fmt_fix_a = "exact edit to add depth above the Show More fold"
        _char_guide = "600-1200"
    elif fmt == "Thread":
        _fmt_note = "Format: Thread. Grade Tweet 1 as the hook — if it doesn't stop the scroll, the thread dies."
        _fmt_fix_a = "exact rewrite of Tweet 1 opener"
        _char_guide = "5-8 tweets"
    elif fmt == "Article":
        _fmt_note = "Format: X Article (1500-2000 words). Grade the headline and intro as the hook — they determine feed click-through."
        _fmt_fix_a = "exact rewrite of headline or intro sentence"
        _char_guide = "1500-2000 words"
    else:
        _fmt_note = f"Format: {fmt}. Top tweets avg {_fp_avg} chars."
        _fmt_fix_a = "exact edit to first line"
        _char_guide = f"{_fp_lo}-{_fp_hi}"

    _bm_label = "PERSONAL BENCHMARKS" if is_guest() else "TYLER'S PERSONAL BENCHMARKS"
    _bm_poss = "your" if is_guest() else "his"
    _benchmarks = f"""{_bm_label} (from synced tweet history):
- {_fp_q}% of {_bm_poss} top tweets use questions — benchmark for Conversation Catalyst
- {_fp_ell}% of {_bm_poss} top tweets use ellipsis — benchmark for Voice Match
- Optimal char range: {_fp_lo}-{_fp_hi} — benchmark for Format Fit
- {_fmt_note}"""

    _prompt_a = f"""Grade this tweet for X algorithm performance.\n\n{_algo}\n\n{_benchmarks}\n\n[TWEET]: "{{tweet_text}}" ({{char_count}} chars)\nHas question mark: {{has_q}} | Has ellipsis: {{has_ell}}\n\nGrade ONLY these 4 categories (score 1-10). Also compute algorithm_score and voice_score (0-100).\n\nReturn ONLY valid JSON:\n{{"algorithm_score":0,"voice_score":0,"grades":[{{"name":"Hook Strength","score":0,"detail":"...","fix":"{_fmt_fix_a}"}},{{"name":"Conversation Catalyst","score":0,"detail":"benchmark: {_fp_q}% question rate","fix":"exact edit to drive replies"}},{{"name":"Bookmark Worthiness","score":0,"detail":"...","fix":"exact stat or insight to add"}},{{"name":"Share/Quote Potential","score":0,"detail":"...","fix":"exact phrasing to sharpen the take"}}]}}"""

    _prompt_b = f"""Grade this tweet for X algorithm performance.\n\n{_algo}\n\n{_benchmarks}\n\n[TWEET]: "{{tweet_text}}" ({{char_count}} chars)\nHas question mark: {{has_q}} | Has ellipsis: {{has_ell}}\n\nGrade ONLY these 4 categories (score 1-10).\n\nReturn ONLY valid JSON:\n{{"grades":[{{"name":"Engagement Triggers","score":0,"detail":"...","fix":"exact punctuation or structural edit"}},{{"name":"Algorithm Compliance","score":0,"detail":"...","fix":"exact penalty to remove or No changes needed"}},{{"name":"Dwell Time Potential","score":0,"detail":"format: {_char_guide}","fix":"exact structural edit to increase read time"}},{{"name":"Voice Match","score":0,"detail":"benchmark: {_fp_ell}% ellipsis rate","fix":"exact word or phrase to change"}}]}}"""

    return _prompt_a, _prompt_b


def _run_ci_ai(action, tweet_text, fmt, voice):
    """Run AI generation and store results in session state. Must be called before _ci_output_panel."""
    # Force clear all previous results before every new generation
    for _clear_key in [
        "ci_banger_data", "ci_result", "ci_repurposed", "ci_preview",
        "ci_grades", "ci_banger_opt_1", "ci_banger_opt_2", "ci_banger_opt_3",
        "_verify_1", "_verify_2", "_verify_3", "_verify_result"
    ]:
        st.session_state.pop(_clear_key, None)

    # DEBUG: log every AI call to stderr (visible in Streamlit Cloud logs)
    import sys
    print(f"[AI-CALL] action={action} voice={voice} fmt={fmt} text={tweet_text[:80]!r}", file=sys.stderr, flush=True)

    voice_mod = _build_voice_mod(voice)
    pp = analyze_personal_patterns()
    format_mod = _build_format_mod(fmt, pp, voice)

    result = None

    # --- PARALLEL FETCH: stats + sports context at the same time ---
    # Skip sports context entirely for non-sports guests
    _live_stats_block = ""
    _sports_ctx = ""
    _skip_sports = is_guest() and "sport" not in load_json("topics.json", {}).get("niche", "").lower()
    if action in ("banger", "build", "rewrite") and tweet_text.strip() and not _skip_sports:
        _entities = _detect_sports_entities(tweet_text)
        _needs_stats = not _input_has_stats(tweet_text) and (_entities["players"] or _entities["teams"])
        _needs_sports = _sports_context_relevant(tweet_text)
        if _needs_stats or _needs_sports:
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as _ex:
                _fut_stats = _ex.submit(
                    lambda: _fetch_live_stats(_entities, betting_level=_tweet_wants_betting(tweet_text))
                ) if _needs_stats else None
                _fut_sports = _ex.submit(get_sports_context) if _needs_sports else None
                if _fut_stats:
                    try: _live_stats_block = _fut_stats.result(timeout=8)
                    except Exception: pass
                if _fut_sports:
                    try: _sports_ctx = f"\n\nLIVE SPORTS CONTEXT (use if relevant to the tweet):\n{_fut_sports.result(timeout=8)}"
                    except Exception: pass

    if action == "banger" and tweet_text.strip() and fmt == "Article":
        # Article format: single long-form article, NOT two-option JSON
        article_voice_mod = _build_article_voice_mod(voice)
        _is_sarcastic = voice == "Sarcastic"
        _article_length = "400-600 words. Short column format. Hard stop at 600." if _is_sarcastic else "1,500-2,000 words / 6-8 minute read"
        _article_structure = "" if _is_sarcastic else """
STRUCTURE:
- HEADLINE: 50-75 chars, include a number or specific claim, take a position.
- [IMAGE: Hero image placeholder]
- INTRO (2-3 paragraphs): Provocative claim or surprising stat, then why it matters now.
- SECTION 1 with subheading: 2-3 short paragraphs with **bold key stats**. [IMAGE placeholder]
- SECTION 2 with subheading: 2-3 short paragraphs, comparison list format if relevant.
- SECTION 3 with subheading: Contrarian angle or insider perspective. [IMAGE placeholder]
- SECTION 4 WHAT COMES NEXT: Bold prediction with reasoning.
- CONCLUSION: **1-sentence bold hot take summary**, then discussion question to drive comments.
- PROMOTION: Suggest a companion tweet pulling the most provocative stat from the article.

RULES:
- 1,500-2,000 words target
- Paragraphs: 2-4 sentences max
- Subheadings every ~300 words
- Bold key stats and claims (2-3 per section)
- Voice: direct, no hedging, authoritative
- Specific players/schemes/numbers only
- Include [IMAGE] markers where supporting visuals should go
- End with debate invitation to drive replies"""
        article_prompt = f"""Expand this concept into {'a short sarcastic column' if _is_sarcastic else 'a complete X Article'} — preserve the core take and phrasing as the foundation, then build around it.

Concept: "{tweet_text}"

FORMAT: {'SARCASTIC COLUMN' if _is_sarcastic else 'X ARTICLE'} ({_article_length})
{_sports_ctx}{_live_stats_block}
{_article_structure}

{article_voice_mod}

Return the article as plain text. Do NOT wrap in JSON or code blocks."""
        _sys_prompt = get_system_for_voice(voice, voice_mod)
        _max_tok = 1200 if _is_sarcastic else 3000
        raw = call_claude(article_prompt, system=_sys_prompt, max_tokens=_max_tok)
        result = _sanitize_output(raw.strip()) if raw else raw

    elif action == "banger" and tweet_text.strip():
        patterns_ctx = build_patterns_context(pp, fmt) if pp else ""
        _char_limit = 160 if fmt == "Punchy Tweet" else (260 if fmt == "Normal Tweet" else None)
        _opt_range = pp.get("optimal_char_range", (0, 280)) if pp else (0, 280)
        if _char_limit:
            _opt_range = (_opt_range[0], min(_opt_range[1], _char_limit))
        _char_rule = f"- CHARACTER LIMIT: Every option MUST be under {_char_limit} characters total — count carefully, no exceptions." if _char_limit else (f"- Optimal character range: {_opt_range[0]}-{_opt_range[1]} characters" if pp else "")
        _fmt_inject = ""
        if voice == "Default":
            _fmt_pats = _get_format_patterns_with_fallback(fmt)
            if _fmt_pats:
                _fmt_inject = f"\n\nFORMAT PATTERNS (from top-performing tweets THIS WEEK — match these structures):\n{_fmt_pats}\n"
        _bg_is_g = is_guest()
        _bg_examples = "" if _bg_is_g else """
EXAMPLE WITH STATS:
- Draft: "Nuggets are on a bit of a heater right now. Warriors aren't a great team but that game last night was a blast. 6 game winning streak and they are starting to figure some things out..."
- Stats available: Denver Nuggets 48-28, Golden State Warriors 36-39
- GOOD output: "48-28. 6 straight wins. Nuggets just beat a Warriors team fighting for their playoff lives and it wasn't even close. This team is on a heater and they're starting to figure some things out..."
- Why it works: Stronger hook (opens with the record), personality is still there, stats add credibility, tighter structure.

EXAMPLE WITHOUT STATS:
- Draft: "Bo Nix is getting better every single week. The arm talent was always there but something changed mentally this offseason"
- GOOD output: "Bo Nix is getting better every single week. The arm talent was always there. Something changed mentally this offseason and the rest of the AFC West is going to find out..."
- Why it works: Kept the observation, sharpened the closer into something that creates intrigue and drives replies.

TOO SAFE (don't do this): Just adding "But" or a period to the draft. Not an improvement.
TOO FAR (don't do this): Replacing the voice with a generic recap."""
        banger_prompt = f"""This is a tweet concept. Make it score 9+ on every X algorithm metric.

Draft: "{tweet_text}"

This draft is a CONCEPT — the take, the angle, the topic. Your job is to turn that concept into a polished, high-performing tweet. Keep the point of view and personality but IMPROVE the hook, tighten the structure, strengthen the closer, and weave in real stats from LIVE STATS below.
{_bg_examples}
{_live_stats_block}
{format_mod}
{patterns_ctx}{_sports_ctx}{_fmt_inject}

STAT INTEGRITY RULE (ZERO TOLERANCE — overrides voice rules):
- ONLY use stats that appear in LIVE STATS above or in the draft. Do not invent, estimate, or round any numbers.
- If LIVE STATS provide a team record (e.g. 48-28), use it. If they don't provide player averages, PFF grades, or rankings — you CANNOT use those.
- A tweet with a concrete observation is ALWAYS better than a tweet with a fabricated stat.
- If a voice rule asks for a "specific number" and no real one is available, use a named event, a team record, or a concrete observation instead. Never invent a number to fill the slot.
{"- CRITICAL VOICE: The 'symptom' does NOT have to be a number. 'The Broncos offensive line is the reason Bo Nix ran for his life in December' is a valid symptom. 'Bottom-10 in pass protection' is NOT valid unless that ranking appears in LIVE STATS." if voice == "Critical" else ""}{"- SARCASTIC VOICE: Do NOT fabricate stats. Sarcastic voice builds humor from observations and framing, not invented numbers." if voice == "Sarcastic" else ""}{"- HOMER VOICE: Do NOT invent player stat lines. Use team records if available. If no player stats exist, describe what you see without citing specific figures." if voice == "Hype" else ""}

Rules:
- Reading Level (7th-9th grade)
- No Hashtags, Links, Tags, Emojis
- Hook & Pattern Breakers (first line stops the scroll)
- Structure each option to match the FORMAT PATTERNS above
{_char_rule}

{"THREAD FORMAT: Inside each option, separate individual tweets with the marker ---TWEET--- between them. Example: first tweet text here---TWEET---second tweet text here---TWEET---third tweet text here" if fmt == "Thread" else ""}

VOICE-SPECIFIC ENDING OVERRIDE:
{"CRITICAL VOICE PICK RULE: ALWAYS prefer the option ending with a period over one ending with a question mark. A question ending in Critical voice is a structural failure regardless of engagement potential. Period ending wins every time. This overrides all other pick criteria." if voice == "Critical" else ""}
{"HOMER ENDING RULE: BOTH options MUST end with a period. No question closers. No ellipsis. If a pattern calls for a question closer, replace it with a declarative outside-reaction statement. WRONG: 'How does the most dominant player not drag this roster over the line?' RIGHT: 'Every team in the West designed their rotations around stopping him. That is not a problem you scheme for unless the threat is real.'" if voice == "Hype" else ""}

Return ONLY this JSON, no other text:
{{
  "option1": "full tweet text here",
  "option1_pattern": "which top tweet pattern this is modeled after",
  "option2": "full tweet text here",
  "option2_pattern": "which top tweet pattern this is modeled after",
  "pick": "1 or 2 — {'MUST be the period-ending option (Critical voice rule overrides all other criteria)' if voice == 'Critical' else 'just the number, no explanation'}",
  "pick_reason": "one sentence — {'why this option matches Critical voice structure (period ending = correct)' if voice == 'Critical' else 'why this option scores higher on the X algorithm'}"
}}"""
        _sys_prompt = get_system_for_voice(voice, voice_mod)
        _max_tok = 2000 if fmt == "Thread" else 400
        raw = call_claude(banger_prompt, system=_sys_prompt, max_tokens=_max_tok)
        banger_data = _parse_banger_json(raw)
        if banger_data and banger_data.get("option1"):
            for _ok in ["option1", "option2"]:
                if banger_data.get(_ok):
                    banger_data[_ok] = _sanitize_output(banger_data[_ok])
            # FIX 1: Critical voice — force pick to period-ending option
            if voice == "Critical" and banger_data.get("option1") and banger_data.get("option2"):
                _o1_ends_period = banger_data["option1"].rstrip().endswith(".")
                _o2_ends_period = banger_data["option2"].rstrip().endswith(".")
                _o1_ends_question = banger_data["option1"].rstrip().endswith("?")
                _o2_ends_question = banger_data["option2"].rstrip().endswith("?")
                if _o1_ends_period and _o2_ends_question:
                    banger_data["pick"] = "1"
                    banger_data["pick_reason"] = "Critical voice: period ending is structurally correct."
                elif _o2_ends_period and _o1_ends_question:
                    banger_data["pick"] = "2"
                    banger_data["pick_reason"] = "Critical voice: period ending is structurally correct."
            st.session_state["ci_banger_data"] = banger_data
            for _i in [1, 2, 3]:
                st.session_state.pop(f"ci_banger_opt_{_i}", None)
            for _k in ["ci_result", "ci_grades", "ci_repurposed", "ci_preview"]:
                st.session_state.pop(_k, None)
        else:
            result = raw

    elif action == "grades" and tweet_text.strip():
        # ── Cache check ──
        _grade_hash = hashlib.md5(tweet_text.strip().encode()).hexdigest()
        _cached = st.session_state.get("ci_grades_cache", {}).get(_grade_hash)
        if _cached:
            st.session_state["ci_grades"] = _cached
            for _k in ["ci_result", "ci_banger_data", "ci_repurposed", "ci_preview"]:
                st.session_state.pop(_k, None)
        else:
            # ── Lean system prompt (grading only needs voice context, not full Tyler bio) ──
            _grades_system = f"You are grading tweets for @{get_current_handle()}. Match their voice: direct, no fluff, punchy sentences, never hedges." if is_guest() else "You are grading tweets for Tyler Polumbus — former NFL lineman (8 seasons, Super Bowl 50 champion), Denver sports media host. Tyler's voice: direct, no fluff, punchy sentences, former-player authority, never hedges."
            _has_q = "yes" if "?" in tweet_text else "no"
            _has_ell = "yes" if "..." in tweet_text else "no"
            _char_count = len(tweet_text)

            # ── Two parallel calls of 4 grades each, with personal benchmarks ──
            _raw_a, _raw_b = _build_grades_system(fmt, pp)
            _prompt_a = _raw_a.replace("{tweet_text}", tweet_text).replace("{char_count}", str(_char_count)).replace("{has_q}", _has_q).replace("{has_ell}", _has_ell)
            _prompt_b = _raw_b.replace("{tweet_text}", tweet_text).replace("{char_count}", str(_char_count)).replace("{has_q}", _has_q).replace("{has_ell}", _has_ell)

            def _parse(raw):
                try:
                    clean = re.sub(r'```(?:json)?\s*', '', raw).strip().rstrip('`').strip()
                    m = re.search(r'\{.*\}', clean, re.DOTALL)
                    return json.loads(m.group()) if m else None
                except Exception:
                    return None

            _tok = _get_oauth_token() or _get_access_token()

            def _grade_call(prompt, tok):
                """Try direct OAuth API, fall back to proxy — never raises."""
                if tok:
                    try:
                        return _call_claude_direct(prompt, _grades_system, 700, _token=tok)
                    except Exception:
                        pass
                return call_claude(prompt, _grades_system, 700)

            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as _ex:
                _fa = _ex.submit(_grade_call, _prompt_a, _tok)
                _fb = _ex.submit(_grade_call, _prompt_b, _tok)
                _ra, _rb = _fa.result(), _fb.result()
            _da, _db = _parse(_ra), _parse(_rb)

            if _da and _db and "grades" in _da and "grades" in _db:
                _voice_score = _da.get("voice_score", _da.get("tyler_score", 0))
                gdata = {
                    "algorithm_score": _da.get("algorithm_score", 0),
                    "voice_score": _voice_score,
                    "tyler_score": _voice_score,
                    "grades": _da["grades"] + _db["grades"],
                }
                _cache = st.session_state.get("ci_grades_cache", {})
                _cache[_grade_hash] = gdata
                st.session_state["ci_grades_cache"] = _cache
                st.session_state["ci_grades"] = gdata
                for _k in ["ci_result", "ci_banger_data", "ci_repurposed", "ci_preview"]:
                    st.session_state.pop(_k, None)
            else:
                result = "Grades failed — try again"

    elif action == "build" and tweet_text.strip() and fmt == "Article":
        # Article format: single long-form article from concept
        _sports_ctx_b = _sports_ctx
        article_voice_mod = _build_article_voice_mod(voice)
        _is_sarcastic = voice == "Sarcastic"
        _article_length = "400-600 words. Short column format. Hard stop at 600." if _is_sarcastic else "1,500-2,000 words / 6-8 minute read"
        _article_structure = "" if _is_sarcastic else """
STRUCTURE:
- HEADLINE: 50-75 chars, include a number or specific claim
- [IMAGE: Hero image placeholder]
- INTRO (2-3 paragraphs): Provocative claim or surprising stat
- 4 SECTIONS with subheadings: 2-3 short paragraphs, **bold key stats**
- WHAT COMES NEXT: Bold prediction with reasoning
- CONCLUSION: 1-sentence bold hot take + debate question
- PROMOTION: companion tweet idea

RULES:
- 1,500-2,000 words, paragraphs 2-4 sentences max, subheadings every ~300 words
- Voice: direct, no hedging, authoritative
- Specific players/schemes/numbers only
- Include [IMAGE] markers for visuals
- End with debate invitation"""
        build_article_prompt = f"""@{get_current_handle()} has a concept to turn into {'a short sarcastic column' if _is_sarcastic else 'a full X Article'}.

CONCEPT/ANGLE:
\"{tweet_text}\"
{_sports_ctx_b}{_live_stats_block}

FORMAT: {'SARCASTIC COLUMN' if _is_sarcastic else 'X ARTICLE'} ({_article_length})
{_article_structure}

{article_voice_mod}

Return the article as plain text. Do NOT wrap in JSON or code blocks."""
        _max_tok = 1200 if _is_sarcastic else 3000
        raw = call_claude(build_article_prompt, system=get_system_for_voice(voice, voice_mod), max_tokens=_max_tok)
        result = _sanitize_output(raw.strip()) if raw else raw

    elif action == "build" and tweet_text.strip():
        _sports_ctx_b = _sports_ctx
        _fmt_inject_b = ""
        if voice == "Default":
            _fmt_pats_b = _get_format_patterns_with_fallback(fmt)
            if _fmt_pats_b:
                _fmt_inject_b = f"\n\nFORMAT PATTERNS (from top-performing tweets THIS WEEK — match these structures):\n{_fmt_pats_b}\n"
        _voice_task = f"matching the {voice} voice described in the system prompt" if voice != "Default" else "matching the voice in the system prompt exactly"
        # Parse structured brief if delimiters present
        _brief_delimiters = ["TOPIC:", "TENSION:", "KEY STATS:", "ANGLE:"]
        _has_brief = any(d in tweet_text for d in _brief_delimiters)
        if _has_brief:
            _brief_block = f"STRUCTURED BRIEF:\n{tweet_text}"
        else:
            _brief_block = f"CONCEPT/ANGLE:\n\"{tweet_text}\""
        _build_opening = "Here is a structured brief as source material. Extract the strongest take and write from scratch — 3 distinct variations." if _has_brief else "Here is a tweet concept/angle to turn into a finished tweet. Materialize this concept into the actual tweet — 3 distinct variations."
        _char_limit_b = 160 if fmt == "Punchy Tweet" else (260 if fmt == "Normal Tweet" else None)
        _char_rule_b = f"\n- CHARACTER LIMIT: Every option MUST be between 161 and 260 characters for Normal Tweet format. Count carefully." if fmt == "Normal Tweet" else (f"\n- CHARACTER LIMIT: Every option MUST be under 160 characters for Punchy Tweet format." if fmt == "Punchy Tweet" else (f"\n- LENGTH: Long Tweet format — 600-1200 characters. Use the space." if fmt == "Long Tweet" else ""))
        build_prompt = f"""{_build_opening}

{_brief_block}
{_live_stats_block}
{format_mod}{_sports_ctx_b}{_fmt_inject_b}

STAT INTEGRITY RULE (ZERO TOLERANCE — overrides voice rules):
- ONLY use stats from LIVE STATS above or from the brief. Do not invent, estimate, or round any numbers.
- If no detailed stats are available, use team records, named events, or concrete observations. Never fabricate a number to fill a slot.
- A tweet with a specific observation is ALWAYS better than one with a fabricated stat.
{"- CRITICAL VOICE: The 'symptom' does NOT have to be a number. Named failures and observable facts count." if voice == "Critical" else ""}{"- HOMER VOICE: Do NOT invent player stat lines. Use team records if available." if voice == "Hype" else ""}

TASK: Write 3 distinct, finished tweets from this concept. Each should take a different angle or structure while {_voice_task}. NOT rewrites of each other — each a unique execution of the idea.

Rules:
- Strong hook — first line stops the scroll
- No hashtags, no emojis
- 7th-9th grade reading level
- End with something that makes people reply or argue
- Algorithm optimized: strong opinion, relatable, invites engagement
- Structure each option to match the FORMAT PATTERNS above{_char_rule_b}

{"HOMER ENDING RULE: ALL options MUST end with a period. No question closers. No ellipsis. Replace question closers with declarative outside-reaction statements." if voice == "Hype" else ""}{"CRITICAL ENDING RULE: ALL options MUST end with a period. No question marks. Critical voice closes the door." if voice == "Critical" else ""}

CRITICAL: Each "option" field must contain the ACTUAL TWEET TEXT that @{get_current_handle()} would post — not a description of the tweet, not a pattern label, not instructions. Write the real tweet.

Return ONLY this JSON, no other text:
{{
  "option1": "the actual tweet text @{get_current_handle()} would post — written out in full, ready to copy and paste to X",
  "option1_pattern": "short label describing the angle this version takes",
  "option2": "the actual tweet text @{get_current_handle()} would post — a different angle, written out in full",
  "option2_pattern": "short label describing the angle this version takes",
  "option3": "the actual tweet text @{get_current_handle()} would post — a third angle, written out in full",
  "option3_pattern": "short label describing the angle this version takes",
  "pick": "1, 2, or 3 — just the number, no explanation"
}}"""
        _max_tok_b = 2000 if fmt == "Thread" else 700
        raw = call_claude(build_prompt, system=get_system_for_voice(voice, voice_mod), max_tokens=_max_tok_b)
        with open("/tmp/build_debug.log", "w") as _dbg:
            _dbg.write(f"RAW:\n{raw}\n\n")
        build_data = _parse_banger_json(raw)
        if build_data:
            with open("/tmp/build_debug.log", "a") as _dbg:
                _dbg.write(f"PARSED:\n{json.dumps(build_data, indent=2)}\n")
        if build_data and build_data.get("option1"):
            for _ok in ["option1", "option2", "option3"]:
                if build_data.get(_ok):
                    build_data[_ok] = _sanitize_output(build_data[_ok])
            # Critical voice: force pick to period-ending option
            if voice == "Critical" and build_data.get("option1") and build_data.get("option2"):
                _o1p = build_data["option1"].rstrip().endswith(".")
                _o2p = build_data["option2"].rstrip().endswith(".")
                _o1q = build_data["option1"].rstrip().endswith("?")
                _o2q = build_data["option2"].rstrip().endswith("?")
                if _o1p and _o2q:
                    build_data["pick"] = "1"
                elif _o2p and _o1q:
                    build_data["pick"] = "2"
            st.session_state["ci_banger_data"] = build_data
            for _i in [1, 2, 3]:
                st.session_state.pop(f"ci_banger_opt_{_i}", None)
            for _k in ["ci_result", "ci_repurposed", "ci_viral_data", "ci_grades", "ci_preview"]:
                st.session_state.pop(_k, None)
        else:
            st.session_state["ci_result"] = raw
            for _k in ["ci_repurposed", "ci_viral_data", "ci_grades", "ci_preview", "ci_banger_data"]:
                st.session_state.pop(_k, None)

    elif action == "rewrite" and tweet_text.strip() and fmt == "Article":
        # Article format: rewrite as full article
        article_voice_mod = _build_article_voice_mod(voice)
        _is_sarcastic = voice == "Sarcastic"
        _article_length = "400-600 words. Short column format. Hard stop at 600." if _is_sarcastic else "1,500-2,000 words / 6-8 minute read"
        _article_structure = "" if _is_sarcastic else """
STRUCTURE:
- HEADLINE: 50-75 chars, include a number or specific claim
- [IMAGE: Hero image placeholder]
- INTRO (2-3 paragraphs): Provocative claim or surprising stat
- 4 SECTIONS with subheadings: 2-3 short paragraphs, **bold key stats**
- WHAT COMES NEXT: Bold prediction with reasoning
- CONCLUSION: 1-sentence bold hot take + debate question
- PROMOTION: companion tweet idea

RULES:
- 1,500-2,000 words, paragraphs 2-4 sentences max
- Voice: direct, no hedging, authoritative
- Do NOT copy original phrasing — completely new execution
- Specific players/schemes/numbers only
- Include [IMAGE] markers for visuals"""
        rewrite_article_prompt = f"""Someone else wrote this content. Repurpose the underlying idea as {'a short sarcastic column' if _is_sarcastic else 'a full X Article'} in @{get_current_handle()}'s voice. Do NOT copy any original phrasing or structure — your version should be completely your own take on the same subject.

Source content (NOT yours): "{tweet_text}"
{_live_stats_block}

FORMAT: {'SARCASTIC COLUMN' if _is_sarcastic else 'X ARTICLE'} ({_article_length})
{_article_structure}

{article_voice_mod}

Return the article as plain text. Do NOT wrap in JSON or code blocks."""
        _max_tok = 1200 if _is_sarcastic else 3000
        raw = call_claude(rewrite_article_prompt, system=get_system_for_voice(voice, voice_mod), max_tokens=_max_tok)
        result = _sanitize_output(raw.strip()) if raw else raw

    elif action == "rewrite" and tweet_text.strip():
        _rw_voice = f"in the {voice} voice described in the system prompt" if voice != "Default" else "in the voice from the system prompt"
        _rw_handle = get_current_handle()
        repurpose_prompt = f"""You are helping @{_rw_handle} repurpose someone else's tweet into original content. The goal: take the UNDERLYING IDEA and write it as if @{_rw_handle} came up with it. Nobody should be able to trace it back to the original.

Source tweet (NOT yours — do NOT copy ANY phrasing, structure, or sentence patterns): "{tweet_text}"

REPURPOSING RULES:
- Extract the core IDEA or TAKE — then throw away everything else about the original tweet.
- Write {_rw_voice} with completely different wording, structure, and angle of attack.
- Your version should feel like an original thought — NOT a paraphrase.
- Change the entry point: if the original leads with a stat, lead with an observation (or vice versa).
- If the original names a person/topic, reference the same subject but frame it from your own perspective.
- Zero overlap in phrasing. If someone put them side by side, they should look like two people independently had the same thought.

{format_mod}{_live_stats_block}

- Strong hook in the first line
- Invites engagement/replies
- No hashtags, no emojis, no character count
- 7th-9th grade reading level

{"HOMER ENDING RULE: BOTH options MUST end with a period. No question closers. No ellipsis. Replace question closers with declarative outside-reaction statements." if voice == "Hype" else ""}{"CRITICAL ENDING RULE: BOTH options MUST end with a period. No question marks. Critical voice closes the door." if voice == "Critical" else ""}

Return ONLY this JSON, no other text:
{{
  "option1": "full tweet text — @{_rw_handle}'s completely original version",
  "option1_pattern": "angle @{_rw_handle} takes on this idea",
  "option2": "full tweet text — different @{_rw_handle} angle, also fully original",
  "option2_pattern": "angle @{_rw_handle} takes on this idea",
  "pick": "1 or 2 — just the number, no explanation"
}}"""
        _max_tok_r = 2000 if fmt == "Thread" else 400
        raw = call_claude(repurpose_prompt, system=get_system_for_voice(voice, voice_mod), max_tokens=_max_tok_r)
        rw_data = _parse_banger_json(raw)
        if rw_data and rw_data.get("option1"):
            for _ok in ["option1", "option2"]:
                if rw_data.get(_ok):
                    rw_data[_ok] = _sanitize_output(rw_data[_ok])
            # Critical voice: force pick to period-ending option
            if voice == "Critical" and rw_data.get("option1") and rw_data.get("option2"):
                _o1p = rw_data["option1"].rstrip().endswith(".")
                _o2p = rw_data["option2"].rstrip().endswith(".")
                _o1q = rw_data["option1"].rstrip().endswith("?")
                _o2q = rw_data["option2"].rstrip().endswith("?")
                if _o1p and _o2q:
                    rw_data["pick"] = "1"
                elif _o2p and _o1q:
                    rw_data["pick"] = "2"
            st.session_state["ci_banger_data"] = rw_data
            for _i in [1, 2, 3]:
                st.session_state.pop(f"ci_banger_opt_{_i}", None)
            for _k in ["ci_result", "ci_repurposed", "ci_viral_data", "ci_grades", "ci_preview"]:
                st.session_state.pop(_k, None)
        else:
            st.session_state["ci_repurposed"] = raw
            for _k in ["ci_result", "ci_viral_data", "ci_grades", "ci_preview", "ci_banger_data"]:
                st.session_state.pop(_k, None)

    if result:
        st.session_state["ci_result"] = result
        st.session_state["ci_result_edit"] = result
        for _k in ["ci_viral_data", "ci_grades", "ci_preview", "ci_repurposed", "ci_banger_data"]:
            st.session_state.pop(_k, None)


# ═══════════════════════════════════════════════════════════════════════════
# CREATOR STUDIO — OUTPUT DIALOG (display-only — AI already ran in _run_ci_ai)
# ═══════════════════════════════════════════════════════════════════════════
def _ci_output_panel_impl(action, tweet_text, fmt, voice):
    """Display AI results — AI ran BEFORE the dialog opened. This is display-only."""
    _RESULT_KEYS = ["ci_banger_data", "ci_grades", "ci_result", "ci_repurposed", "ci_preview"]

    # AI already ran before dialog opened — do NOT call _run_ci_ai here
    # (calling it inside @st.dialog caused fragment caching to serve stale results)

    # Track last action for Redo
    st.session_state["ci_last_action"] = {"type": action, "text": tweet_text, "fmt": fmt, "voice": voice}

    # Subtle format/voice subtitle
    _debug_hash = hex(hash(tweet_text))[-6:]
    _has_sep = "---TWEET---" in str(st.session_state.get("ci_banger_data", {}).get("option1", ""))
    st.markdown(
        f'<div style="font-size:11px;color:rgba(255,255,255,0.35);font-weight:400;margin-bottom:12px;">{fmt} · {voice} · v3.29 · sep:{_has_sep} · [{_debug_hash}]</div>',
        unsafe_allow_html=True)
    # ── Results from session state (AI already ran before dialog opened) ──
    if st.session_state.get("ci_banger_data"):
        bd = st.session_state["ci_banger_data"]
        _ai_pick = str(bd.get("pick", "1")).strip()
        opts = [(bd.get(f"option{i}", ""), bd.get(f"option{i}_pattern", "")) for i in [1, 2, 3] if bd.get(f"option{i}")]
        _ra, _rb = st.columns([1, 1])
        with _ra:
            if st.button("Refresh Options", key="ci_refresh_options", use_container_width=True):
                for _k in ["ci_banger_data", "ci_result", "ci_repurposed", "ci_preview", "ci_grades"]:
                    st.session_state.pop(_k, None)
                with st.spinner("Post Ascend AI is working... generating fresh options"):
                    _run_ci_ai(action, tweet_text, fmt, voice)
                st.session_state["_ci_reopen_dialog"] = {
                    "action": action,
                    "tweet_text": tweet_text,
                    "fmt": fmt,
                    "voice": voice,
                }
                st.rerun(scope="app")
        with _rb:
            st.markdown(
                f'<div style="font-size:10px;color:rgba(255,255,255,0.28);padding-top:10px;text-align:right;">Regenerates fresh options with the same {fmt} / {voice} settings.</div>',
                unsafe_allow_html=True,
            )
        for ti, (opt_text, pattern) in enumerate(opts):
            opt_key = f"ci_banger_opt_{ti + 1}"
            _is_pick = _ai_pick == str(ti + 1)
            if _is_pick:
                st.markdown(f'''<div style="font-size:11px;font-weight:700;letter-spacing:2px;margin:20px 0 4px;"><span style="color:#2DD4BF;">OPTION {ti + 1}</span>&nbsp;&nbsp;<span style="background:#2DD4BF;color:#0a0a14;padding:2px 8px;border-radius:4px;font-size:10px;">AI PICK</span></div>''', unsafe_allow_html=True)
                _pick_reason = bd.get("pick_reason", "")
                if _pick_reason:
                    st.markdown(f'''<div style="font-size:11px;color:#2DD4BF;opacity:0.7;margin-bottom:4px;font-style:italic;">{_pick_reason}</div>''', unsafe_allow_html=True)
            else:
                st.markdown(f'''<div style="font-size:11px;color:#2DD4BF;font-weight:700;letter-spacing:2px;margin:20px 0 4px;">OPTION {ti + 1}</div>''', unsafe_allow_html=True)
            if pattern:
                st.markdown(f'''<div style="font-size:11px;color:#666688;letter-spacing:0.5px;margin-bottom:8px;">{pattern}</div>''', unsafe_allow_html=True)
            # Thread format: render as X-native cards (no raw text area)
            _display_text = opt_text
            _is_thread = "---TWEET---" in _display_text
            if _is_thread:
                _card_html = render_thread_cards(_display_text, voice)
                if _card_html:
                    st.markdown(_card_html, unsafe_allow_html=True)
                # Store raw text for Save/Use buttons without displaying it
                _widget_key = f"{opt_key}_{hash(_display_text) % 100000}"
                edited_opt = _display_text
            else:
                # Non-thread: show editable text area as before
                _widget_key = f"{opt_key}_{hash(_display_text) % 100000}"
                edited_opt = st.text_area("", value=_display_text, height=auto_height(_display_text, min_h=100), key=_widget_key, label_visibility="collapsed")
            b1, b2, b3 = st.columns(3)
            with b1:
                if st.button("↓ Save", key=f"modal_bsave_{ti+1}", use_container_width=True):
                    ideas = load_json("saved_ideas.json", [])
                    ideas.append({"text": edited_opt, "format": fmt, "category": "Uncategorized", "saved_at": datetime.now().isoformat()})
                    save_json("saved_ideas.json", ideas)
                    st.success("Saved.")
            with b2:
                if st.button("↗ Use", key=f"modal_buse_{ti+1}", use_container_width=True, type="primary"):
                    v = st.session_state.get(_widget_key, opt_text)
                    if v:
                        st.session_state["_ci_text_stage"] = v
                    _current_page = st.query_params.get("page", "Creator Studio")
                    if _current_page != "Creator Studio":
                        st.query_params["page"] = "Creator Studio"
                    st.rerun(scope="app")
            with b3:
                if pplx_available() and st.button("Verify", key=f"modal_bverify_{ti+1}", use_container_width=True):
                    _v_text = st.session_state.get(_widget_key, opt_text)
                    with st.spinner("Fact-checking..."):
                        _fc = pplx_fact_check(_v_text)
                    if _fc.get("answer"):
                        st.session_state[f"_verify_{ti+1}"] = _fc
                    else:
                        st.warning("Couldn't verify — check API key.")
            _vr = st.session_state.get(f"_verify_{ti+1}")
            if _vr:
                _va = _vr["answer"]
                _vc = _vr.get("citations", [])
                _color = "#2DD4BF" if "accurate" in _va.lower() or "correct" in _va.lower() else "#FBBF24"
                st.markdown(f'<div style="background:#0d1829;border-left:3px solid {_color};padding:10px 14px;border-radius:6px;margin:8px 0;font-size:12px;color:#b8c8d8;line-height:1.6;">{_va}</div>', unsafe_allow_html=True)
                if _vc:
                    st.markdown(f'<div style="font-size:10px;color:#3a5070;margin-top:4px;">Sources: {", ".join(str(c) for c in _vc[:3])}</div>', unsafe_allow_html=True)

    elif st.session_state.get("ci_grades"):
        gd = st.session_state["ci_grades"]
        algo_score = gd.get("algorithm_score", 0)
        voice_score = gd.get("voice_score", gd.get("tyler_score", 0))
        grades = gd.get("grades", [])
        combined_score = round((algo_score + voice_score) / 2) if algo_score or voice_score else 0
        _voice_score_label = "Voice Match" if is_guest() else "Tyler Voice"

        # ── Session state for grade panel interactivity ──
        if "ci_grade_selected" not in st.session_state:
            st.session_state["ci_grade_selected"] = 0
        if "ci_grade_accepted" not in st.session_state:
            st.session_state["ci_grade_accepted"] = set()
        if "ci_grade_skipped" not in st.session_state:
            st.session_state["ci_grade_skipped"] = set()
        sel_idx = st.session_state["ci_grade_selected"]
        accepted = st.session_state["ci_grade_accepted"]
        skipped = st.session_state["ci_grade_skipped"]

        def _pill_color(s):
            if s >= 7: return ("rgba(45,212,191,0.12)", "#2DD4BF")
            if s >= 5: return ("rgba(251,191,36,0.12)", "#FBBF24")
            return ("rgba(248,113,113,0.12)", "#F87171")

        def _apply_fix(fix_instruction, clear_all=False):
            _base = st.session_state.get("ci_text", "")
            if clear_all:
                _accepted_grades = [g for i, g in enumerate(grades) if i in accepted and g.get("fix", "")]
                if not _accepted_grades:
                    _accepted_grades = [g for g in grades if g.get("fix", "")]
                _all = "\n".join([f'- {g.get("name","")}: {g.get("fix","")}' for g in _accepted_grades])
                _prompt = f'Tweet: "{_base}"\n\nApply ALL of these edits:\n{_all}\n\nReturn ONLY the updated tweet text, nothing else.'
            else:
                _prompt = f'Tweet: "{_base}"\n\nApply this specific edit only: {fix_instruction}\n\nReturn ONLY the updated tweet text, nothing else.'
            _updated = call_claude(_prompt, max_tokens=400)
            if _updated:
                # Use staging key — widget-owned "ci_text" gets overwritten on rerun
                st.session_state["_ci_text_stage"] = _updated.strip()
            for _k in ["ci_grades", "ci_grade_selected", "ci_grade_accepted", "ci_grade_skipped"]:
                st.session_state.pop(_k, None)
            st.rerun(scope="app")

        # ── SCORE STRIP — 3 cards ──
        st.markdown(f"""<div style="display:flex;gap:8px;margin:12px 0 16px;">
          <div style="flex:1;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-top:2px solid #2DD4BF;border-radius:10px;padding:12px 14px;text-align:center;">
            <div style="font-family:'Bebas Neue',sans-serif;font-size:32px;color:#2DD4BF;line-height:1;">{algo_score}</div>
            <div style="height:5px;background:rgba(45,212,191,0.1);border-radius:3px;margin:8px 0 6px;">
              <div style="width:{algo_score}%;height:100%;background:#2DD4BF;border-radius:3px;"></div>
            </div>
            <div style="font-size:8px;text-transform:uppercase;letter-spacing:0.1em;color:rgba(255,255,255,0.35);font-weight:600;">Algorithm</div>
          </div>
          <div style="flex:1;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-top:2px solid #C49E3C;border-radius:10px;padding:12px 14px;text-align:center;">
            <div style="font-family:'Bebas Neue',sans-serif;font-size:32px;color:#C49E3C;line-height:1;">{voice_score}</div>
            <div style="height:5px;background:rgba(196,158,60,0.1);border-radius:3px;margin:8px 0 6px;">
              <div style="width:{voice_score}%;height:100%;background:#C49E3C;border-radius:3px;"></div>
            </div>
            <div style="font-size:8px;text-transform:uppercase;letter-spacing:0.1em;color:rgba(255,255,255,0.35);font-weight:600;">{_voice_score_label}</div>
          </div>
          <div style="flex:1;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-top:2px solid rgba(255,255,255,0.18);border-radius:10px;padding:12px 14px;text-align:center;">
            <div style="font-family:'Bebas Neue',sans-serif;font-size:32px;color:rgba(255,255,255,0.7);line-height:1;">{combined_score}</div>
            <div style="height:5px;background:rgba(255,255,255,0.06);border-radius:3px;margin:8px 0 6px;">
              <div style="width:{combined_score}%;height:100%;background:rgba(255,255,255,0.25);border-radius:3px;"></div>
            </div>
            <div style="font-size:8px;text-transform:uppercase;letter-spacing:0.1em;color:rgba(255,255,255,0.35);font-weight:600;">Combined</div>
          </div>
        </div>""", unsafe_allow_html=True)

        # ── TWO-COLUMN BODY ──
        _left_col, _right_col = st.columns([1, 3])

        # ── LEFT LIST (pure st.button — no overlays) ──
        with _left_col:
            for i, _g in enumerate(grades):
                _gname = _g.get("name", "")
                _gscore = _g.get("score", 0)
                _gfix = _g.get("fix", "")
                _is_active = (i == sel_idx)
                _has_suggestion = (_gscore <= 6 or bool(_gfix))
                _is_accepted = (i in accepted)

                _pill = "✓" if _is_accepted else f"{_gscore}/10"
                _dot = " ●" if (_has_suggestion and not _is_accepted) else ""
                _label = f"{_pill}  {_gname}{_dot}"

                st.button(_label, key=f"ci_gsel_{i}", use_container_width=True,
                         type="primary" if _is_active else "secondary",
                         on_click=lambda idx=i: st.session_state.update({"ci_grade_selected": idx}))

        # ── RIGHT PANEL ──
        with _right_col:
            if grades and 0 <= sel_idx < len(grades):
                _sg = grades[sel_idx]
                _sname = _sg.get("name", "")
                _sscore = _sg.get("score", 0)
                _sdetail = _sg.get("detail", "")
                _sfix = _sg.get("fix", "")
                _sbg, _stx = _pill_color(_sscore)
                _is_accepted = (sel_idx in accepted)
                _is_skipped = (sel_idx in skipped)

                # Category header
                st.markdown(f'<div style="font-size:15px;font-weight:700;color:rgba(255,255,255,0.85);margin-bottom:4px;">{_sname}</div>', unsafe_allow_html=True)

                # Large score + progress bar
                st.markdown(f"""<div style="display:flex;align-items:baseline;gap:2px;margin-bottom:4px;">
                  <span style="font-size:36px;font-weight:800;color:{_stx};line-height:1;">{_sscore}</span>
                  <span style="font-size:12px;color:rgba(255,255,255,0.25);">/10</span>
                  <div style="flex:1;margin-left:10px;">
                    <div style="height:4px;background:{_sbg};border-radius:2px;">
                      <div style="width:{_sscore * 10}%;height:100%;background:{_stx};border-radius:2px;"></div>
                    </div>
                  </div>
                </div>""", unsafe_allow_html=True)

                # WHY THIS SCORE — between score and fix
                if _sdetail:
                    st.markdown(
                        f'<div style="font-size:8px;text-transform:uppercase;letter-spacing:0.08em;color:rgba(255,255,255,0.22);font-weight:600;margin:10px 0 4px;">Why This Score</div>'
                        f'<div style="font-size:11px;color:rgba(255,255,255,0.55);line-height:1.65;margin-bottom:14px;">{_sdetail}</div>', unsafe_allow_html=True)

                # FIX section
                if _sfix and _sfix.lower() != "no changes needed":
                    # FIX label with seafoam line
                    st.markdown('<div style="display:flex;align-items:center;gap:8px;margin-bottom:10px;">'
                                '<span style="font-size:8px;text-transform:uppercase;letter-spacing:0.08em;color:#2DD4BF;font-weight:700;">Fix</span>'
                                '<div style="flex:1;height:1px;background:rgba(45,212,191,0.15);"></div>'
                                '</div>', unsafe_allow_html=True)

                    _card_opacity = "0.3" if _is_skipped else "1"
                    _check_html = '<span style="color:#2DD4BF;font-weight:800;font-size:16px;margin-right:6px;">✓</span>' if _is_accepted else ''

                    # Suggestion card with background
                    st.markdown(
                        f'<div style="border-radius:12px;background:rgba(45,212,191,0.07);border:1px solid rgba(45,212,191,0.22);padding:16px 18px;opacity:{_card_opacity};">'
                        f'{_check_html}'
                        f'<span style="font-size:14px;color:rgba(255,255,255,0.88);font-weight:400;line-height:1.75;letter-spacing:0.01em;">{_sfix}</span>'
                        f'</div>', unsafe_allow_html=True)

                    # Apply + Skip buttons
                    if not _is_accepted and not _is_skipped:
                        if st.button("Apply this fix", key=f"ci_gapply_{sel_idx}", use_container_width=True, type="primary"):
                            with st.spinner("Applying fix..."):
                                _apply_fix(_sfix)
                        if st.button("Skip", key=f"ci_gskip_{sel_idx}", use_container_width=True):
                            skipped.add(sel_idx)
                            st.session_state["ci_grade_skipped"] = skipped
                            st.rerun()
                    elif _is_accepted:
                        st.markdown('<div style="font-size:10px;color:rgba(45,212,191,0.6);font-weight:600;margin-top:6px;">Applied</div>', unsafe_allow_html=True)

                else:
                    # No fix needed
                    st.markdown('<div style="border:1px dashed rgba(45,212,191,0.15);border-radius:12px;padding:20px;text-align:center;margin-top:12px;">'
                                '<div style="font-size:18px;font-weight:800;color:#2DD4BF;margin-bottom:4px;">✓</div>'
                                '<div style="font-size:11px;color:rgba(255,255,255,0.3);">No changes needed</div>'
                                '</div>', unsafe_allow_html=True)

        # ── BOTTOM CTA BAR ──
        st.markdown('<div style="height:1px;background:rgba(255,255,255,0.04);margin:16px 0 12px;"></div>', unsafe_allow_html=True)
        _accepted_fixes = [grades[i] for i in accepted if i < len(grades) and grades[i].get("fix", "")]
        _pending_count = sum(1 for i, g in enumerate(grades) if g.get("fix", "") and g.get("fix", "").lower() != "no changes needed" and i not in accepted and i not in skipped)
        if _accepted_fixes or _pending_count > 0:
            if st.button("⚡ Make All Changes", key="ci_fix_all", use_container_width=True, type="primary"):
                with st.spinner("Applying all fixes..."):
                    _apply_fix(None, clear_all=True)
            _sub_text = f"{len(_accepted_fixes)} fix{'es' if len(_accepted_fixes) != 1 else ''} queued" if _accepted_fixes else "Applies all accepted suggestions at once"
            st.markdown(f'<div style="text-align:center;font-size:10px;color:rgba(255,255,255,0.25);margin-top:-4px;">{_sub_text}</div>', unsafe_allow_html=True)

    elif st.session_state.get("ci_result") or st.session_state.get("ci_repurposed"):
        _rkey = "ci_result" if st.session_state.get("ci_result") else "ci_repurposed"
        _val = st.session_state[_rkey]
        _edit_key = f"modal_edit_{hash(_val) & 0xFFFFFF}"
        edited = st.text_area("", value=_val, height=auto_height(_val, min_h=160), key=_edit_key, label_visibility="collapsed")
        r1, r2, r3 = st.columns(3)
        with r1:
            if st.button("↓ Save", key="modal_result_save", use_container_width=True):
                ideas = load_json("saved_ideas.json", [])
                ideas.append({"text": edited, "format": fmt, "category": "Uncategorized", "saved_at": datetime.now().isoformat()})
                save_json("saved_ideas.json", ideas)
                st.success("Saved.")
        with r2:
            if st.button("↗ Use", key="modal_result_use", use_container_width=True, type="primary"):
                v = st.session_state.get(_edit_key, edited)
                if v:
                    st.session_state["ci_text"] = v
                st.rerun(scope="app")
        with r3:
            if pplx_available() and st.button("Verify", key="modal_result_verify", use_container_width=True):
                _v_text = st.session_state.get(_edit_key, _val)
                with st.spinner("Fact-checking..."):
                    _fc = pplx_fact_check(_v_text)
                if _fc.get("answer"):
                    st.session_state["_verify_result"] = _fc
                else:
                    st.warning("Couldn't verify — check API key.")
        _vr = st.session_state.get("_verify_result")
        if _vr:
            _va = _vr["answer"]
            _vc = _vr.get("citations", [])
            _color = "#2DD4BF" if "accurate" in _va.lower() or "correct" in _va.lower() else "#FBBF24"
            st.markdown(f'<div style="background:#0d1829;border-left:3px solid {_color};padding:10px 14px;border-radius:6px;margin:8px 0;font-size:12px;color:#b8c8d8;line-height:1.6;">{_va}</div>', unsafe_allow_html=True)
            if _vc:
                st.markdown(f'<div style="font-size:10px;color:#3a5070;margin-top:4px;">Sources: {", ".join(str(c) for c in _vc[:3])}</div>', unsafe_allow_html=True)

    # ── Bottom action bar ──
    st.divider()
    _b2, _b3 = st.columns(2)
    with _b2:
        import urllib.parse as _urlparse
        _post_text = (st.session_state.get("ci_result") or st.session_state.get("ci_repurposed") or tweet_text or "")[:280]
        _enc = _urlparse.quote(_post_text)
        st.markdown(f'<a href="https://twitter.com/intent/tweet?text={_enc}" target="_blank" style="display:block;text-align:center;padding:9px 0;background:transparent;border:1px solid #1a3050;border-radius:50px;color:#5a8090;font-size:13px;font-weight:600;text-decoration:none;">𝕏 Post to X</a>', unsafe_allow_html=True)
    with _b3:
        if st.button("✕ Close", use_container_width=True, key="modal_close"):
            for _k in _RESULT_KEYS:
                st.session_state.pop(_k, None)
            st.rerun(scope="app")


def _fetch_rss_headlines(url: str, max_items: int = 15) -> list:
    """Fetch and parse an RSS feed, return list of headline strings."""
    try:
        import xml.etree.ElementTree as _ET
        _resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        _root = _ET.fromstring(_resp.content)
        _ns = {"media": "http://search.yahoo.com/mrss/"}
        _items = _root.findall(".//item")[:max_items]
        _out = []
        for _item in _items:
            _title = (_item.findtext("title") or "").strip()
            _desc = (_item.findtext("description") or "").strip()
            _pub = (_item.findtext("pubDate") or "").strip()
            if _title:
                _out.append(f"{_title} [{_pub[:16]}]" + (f" — {_desc[:120]}" if _desc and _desc != _title else ""))
        return _out
    except Exception:
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_inspiration_feed():
    """Fetch all lists + Twitter searches + RSS. Cached 20 min — data doesn't change that fast."""
    import concurrent.futures as _cf
    from datetime import timezone as _tz
    _cutoff = datetime.now(_tz.utc) - timedelta(hours=24)

    # Layer 1: ALL Twitter lists in parallel
    _lists = load_engagement_lists()
    _all_list_ids = [v.get("list_id", "") for v in _lists.values() if isinstance(v, dict) and v.get("list_id")]
    # Also collect search-query-based feeds (guests get these from onboarding)
    _list_search_queries = [v.get("search_query", "") for v in _lists.values() if isinstance(v, dict) and v.get("search_query")]

    def _fetch_list(lid):
        if not lid:
            return []
        _raw = fetch_tweets_from_list(lid, count=20)
        _out = []
        for _t in _raw:
            _ts = _t.get("createdAt", "")
            try:
                from dateutil import parser as _dtp
                _dt = _dtp.parse(_ts)
                if _dt.tzinfo is None:
                    _dt = _dt.replace(tzinfo=_tz.utc)
                if _dt >= _cutoff:
                    _out.append(_t)
            except Exception:
                _out.append(_t)
        return _out

    # Layer 2: Twitter searches — personalized per user
    _is_g = is_guest()
    if _is_g:
        _topics_data = load_json("topics.json", {})
        _user_topics = _topics_data.get("topics", [])
        # Build search queries from user's topics + their engagement list queries
        _search_queries = _list_search_queries[:]
        if _user_topics:
            # Add a combined OR query from their top topics
            _topic_or = " OR ".join(_user_topics[:4])
            _search_queries.append(f"{_topic_or} min_faves:10 -filter:retweets")
    else:
        _search_queries = [
            "Denver Broncos OR Denver Nuggets OR Avalanche -filter:retweets",
            "March Madness OR NCAA Tournament OR NBA OR NFL Draft -filter:retweets",
        ]

    # Layer 3: RSS feeds — niche-aware for guests
    if _is_g:
        _niche = load_json("topics.json", {}).get("niche", "General").lower()
        _rss_feeds = [
            "https://news.google.com/rss/search?q=trending+news+today&hl=en-US&gl=US&ceid=US:en",
        ]
        # Add niche-specific RSS
        _niche_rss = {
            "sports": ["https://www.espn.com/espn/rss/news", "https://www.espn.com/espn/rss/nfl/news"],
            "tech": ["https://news.google.com/rss/search?q=technology+startups+AI&hl=en-US&gl=US&ceid=US:en"],
            "finance": ["https://news.google.com/rss/search?q=finance+markets+crypto&hl=en-US&gl=US&ceid=US:en"],
            "fitness": ["https://news.google.com/rss/search?q=fitness+health+wellness&hl=en-US&gl=US&ceid=US:en"],
            "entertainment": ["https://news.google.com/rss/search?q=entertainment+movies+music&hl=en-US&gl=US&ceid=US:en"],
            "politics": ["https://news.google.com/rss/search?q=politics+policy+government&hl=en-US&gl=US&ceid=US:en"],
            "business": ["https://news.google.com/rss/search?q=business+entrepreneurship+marketing&hl=en-US&gl=US&ceid=US:en"],
            "gaming": ["https://news.google.com/rss/search?q=gaming+esports+video+games&hl=en-US&gl=US&ceid=US:en"],
        }
        for _nk, _nurls in _niche_rss.items():
            if _nk in _niche:
                _rss_feeds.extend(_nurls)
                break
        # Also add RSS from their specific topics
        for _tp in load_json("topics.json", {}).get("topics", [])[:2]:
            _rss_feeds.append(f"https://news.google.com/rss/search?q={_tp.replace(' ', '+')}&hl=en-US&gl=US&ceid=US:en")
    else:
        _rss_feeds = [
            "https://www.espn.com/espn/rss/news",
            "https://www.espn.com/espn/rss/nfl/news",
            "https://www.espn.com/espn/rss/nba/news",
            "https://news.google.com/rss/search?q=sports+news+today&hl=en-US&gl=US&ceid=US:en",
            "https://news.google.com/rss/search?q=march+madness+NCAA+2026&hl=en-US&gl=US&ceid=US:en",
        ]

    # Run ALL fetches in parallel
    _list_tweets, _search_tweets, _rss_headlines = [], [], []
    _espn_headlines, _sleeper_lines = [], []
    _trends_lines, _reddit_lines, _newsapi_lines, _crypto_lines = [], [], [], []
    _topics_data = load_json("topics.json", {}) if _is_g else {}
    _user_niche = _topics_data.get("niche", "General") if _is_g else "Sports"
    _user_topics = _topics_data.get("topics", []) if _is_g else []
    _is_sports_niche = not _is_g or "sport" in _user_niche.lower()
    _is_crypto_niche = _is_g and ("crypto" in _user_niche.lower() or "finance" in _user_niche.lower())
    with _cf.ThreadPoolExecutor(max_workers=20) as _ex:
        _list_futs = [_ex.submit(_fetch_list, lid) for lid in _all_list_ids]
        _search_futs = [_ex.submit(fetch_tweets, q, 15) for q in _search_queries]
        _rss_futs = [_ex.submit(_fetch_rss_headlines, u, 12) for u in _rss_feeds]
        # ESPN + Sleeper — sports niche only
        if _is_sports_niche:
            _espn_fut = _ex.submit(get_espn_headlines_for_inspo)
            _sleeper_fut = _ex.submit(get_sleeper_trending_for_inspo)
        # Universal APIs — all users get Google Trends + Reddit
        _trends_fut = _ex.submit(get_google_trends)
        _reddit_fut = _ex.submit(get_reddit_trending, _user_niche, _user_topics)
        # NewsAPI — if key available
        _newsapi_fut = _ex.submit(get_newsapi_headlines, _user_topics, _user_niche)
        # CoinGecko — finance/crypto niche
        if _is_crypto_niche:
            _crypto_fut = _ex.submit(get_coingecko_trending)
        # Collect results
        for _f in _list_futs:
            try: _list_tweets.extend(_f.result())
            except Exception: pass
        for _f in _search_futs:
            try: _search_tweets.extend(_f.result())
            except Exception: pass
        for _f in _rss_futs:
            try:
                _rss_results = _f.result()
                _rss_headlines.extend([h for h in _rss_results if not h.startswith("RT ")])
            except Exception: pass
        if _is_sports_niche:
            try: _espn_headlines = _espn_fut.result()
            except Exception: pass
            try: _sleeper_lines = _sleeper_fut.result()
            except Exception: pass
        try: _trends_lines = _trends_fut.result()
        except Exception: pass
        try: _reddit_lines = _reddit_fut.result()
        except Exception: pass
        try: _newsapi_lines = _newsapi_fut.result()
        except Exception: pass
        if _is_crypto_niche:
            try: _crypto_lines = _crypto_fut.result()
            except Exception: pass

    # Merge all headline sources — higher quality sources first
    _rss_headlines = (_espn_headlines + _sleeper_lines + _crypto_lines +
                      _newsapi_lines + _trends_lines + _reddit_lines + _rss_headlines)

    # Dedupe tweets
    _seen = set()
    _all_tweets = []
    for _t in _list_tweets + _search_tweets:
        _tid = _t.get("id", _t.get("tweet_id", ""))
        if _tid and _tid not in _seen:
            _seen.add(_tid)
            _all_tweets.append(_t)

    return _all_tweets, _rss_headlines


# ── Format Pattern Analysis ──────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def _load_inspo_from_gist(_cache_key: str = "") -> tuple:
    """Load cached inspiration ideas from gist — instant, survives session resets."""
    if is_guest():
        _data = load_json("inspo_cache.json", {})
        return _data.get("ideas", []), _data.get("n_tweets", 0), _data.get("n_headlines", 0)
    try:
        _gid = st.secrets.get("GIST_ID", "15fb167bbbfdaa79d5ce11c266c3f652")
        _r = requests.get(f"https://api.github.com/gists/{_gid}", headers=_gist_headers(), timeout=8)
        _files = _r.json().get("files", {})
        if "hq_inspo_cache.json" in _files:
            _data = json.loads(_files["hq_inspo_cache.json"]["content"])
            _ideas = _data.get("ideas", [])
            _ts = _data.get("generated_at", "")
            _n_tweets = _data.get("n_tweets", 0)
            _n_heads = _data.get("n_headlines", 0)
            # Check freshness — use if under 2 hours old
            if _ts and _ideas:
                from datetime import timezone as _tz2
                _gen = datetime.fromisoformat(_ts)
                if _gen.tzinfo is None:
                    _gen = _gen.replace(tzinfo=_tz2.utc)
                _age = (datetime.now(_tz2.utc) - _gen).total_seconds()
                if _age < 7200:  # 2 hours
                    return _ideas, _n_tweets, _n_heads
    except Exception:
        pass
    return [], 0, 0

def _save_inspo_to_gist(ideas: list, n_tweets: int, n_headlines: int):
    """Persist inspiration ideas to gist for instant loads."""
    if is_guest():
        from datetime import timezone as _tz3
        save_json("inspo_cache.json", {
            "ideas": ideas,
            "n_tweets": n_tweets,
            "n_headlines": n_headlines,
            "generated_at": datetime.now(_tz3.utc).isoformat(),
        })
        return
    try:
        from datetime import timezone as _tz3
        _gid = st.secrets.get("GIST_ID", "15fb167bbbfdaa79d5ce11c266c3f652")
        _data = {"ideas": ideas, "n_tweets": n_tweets, "n_headlines": n_headlines,
                 "generated_at": datetime.now(_tz3.utc).isoformat()}
        _payload = json.dumps({"files": {"hq_inspo_cache.json": {"content": json.dumps(_data, indent=2, default=str)}}})
        requests.patch(f"https://api.github.com/gists/{_gid}", data=_payload, headers=_gist_headers(), timeout=8)
    except Exception:
        pass

@st.cache_data(ttl=1800, show_spinner=False)
def _run_inspiration_claude(_cache_key: str = ""):
    """Fetch feed + call Claude. Cached 30 min in-session, also saved to gist for cross-session."""
    _all_tweets, _rss_headlines = _fetch_inspiration_feed()

    _tweet_lines = []
    for _t in _all_tweets[:40]:
        _text = _t.get("text", "")
        if not _text:
            continue
        if _text.startswith("RT "):
            continue
        if _text.startswith("@"):
            continue
        _author = _t.get("author", {}).get("userName", "") or _t.get("user", {}).get("screen_name", "")
        _likes = _t.get("likeCount", _t.get("like_count", 0))
        _tweet_lines.append(f"@{_author} ({_likes}L): {_text[:100]}")
        if len(_tweet_lines) >= 20:
            break

    _rss_block = "\n".join(_rss_headlines[:10]) if _rss_headlines else "(none)"
    _tweet_block = "\n".join(_tweet_lines) if _tweet_lines else "(none)"

    _fmt_patterns = _get_format_patterns_with_fallback("Normal Tweet")
    _fmt_block = ""
    if _fmt_patterns:
        _fmt_block = f"""

FORMAT PATTERNS (from highest-engagement tweets RIGHT NOW — every hook MUST follow these patterns):
{_fmt_patterns}

Use these patterns to structure every hook. Match the opener style, line break placement, length, and ending style that's working THIS WEEK."""

    _wh_handle = get_current_handle()
    _wh_is_g = is_guest()
    _wh_angle = "their unique perspective and expertise" if _wh_is_g else "Tyler's unique angle as a former player and Denver media host"
    _wh_system = f"""You are @{_wh_handle}'s content strategist. Return only a JSON array, no other text.

{_WHATS_HOT_VOICE_GUIDE}"""

    # Split feed in half and run two parallel Sonnet calls for speed
    _tweet_lines_a = _tweet_lines[:len(_tweet_lines)//2]
    _tweet_lines_b = _tweet_lines[len(_tweet_lines)//2:]
    _rss_a = (_rss_headlines or [])[:5]
    _rss_b = (_rss_headlines or [])[5:10]
    _tweet_block_a = "\n".join(_tweet_lines_a) if _tweet_lines_a else "(none)"
    _tweet_block_b = "\n".join(_tweet_lines_b) if _tweet_lines_b else "(none)"
    _rss_block_a = "\n".join(_rss_a) if _rss_a else "(none)"
    _rss_block_b = "\n".join(_rss_b) if _rss_b else "(none)"

    def _build_wh_prompt(tweets, headlines, count):
        return f"""@{_wh_handle} needs {count} tweet ideas from what's hot RIGHT NOW.

FEED:
{tweets}

HEADLINES:
{headlines}

Rules:
- hook = ORIGINAL tweet draft in @{_wh_handle}'s voice (not a copy of feed text)
- voice = Default/Critical/Hype/Sarcastic (pick best fit)
- why = under 10 words, {_wh_angle}

Return ONLY JSON:
[{{"topic":"2-4 words","source":"twitter/espn/news","voice":"Default/Critical/Hype/Sarcastic","hook":"tweet draft","why":"short angle"}}]"""

    import concurrent.futures as _wh_cf
    _tok = None
    try:
        _tok = _get_oauth_token() or _get_access_token()
    except Exception:
        pass

    def _wh_call(prompt_text):
        try:
            if _tok:
                return _call_with_token(_tok, prompt_text, _wh_system, 700)
            return _call_claude_direct(prompt_text, _wh_system, max_tokens=700)
        except Exception:
            try:
                return call_claude(prompt_text, _wh_system, max_tokens=700)
            except Exception:
                return ""

    _prompt_a = _build_wh_prompt(_tweet_block_a, _rss_block_a, 4)
    _prompt_b = _build_wh_prompt(_tweet_block_b, _rss_block_b, 4)

    with _wh_cf.ThreadPoolExecutor(max_workers=2) as _wh_ex:
        _fut_a = _wh_ex.submit(_wh_call, _prompt_a)
        _fut_b = _wh_ex.submit(_wh_call, _prompt_b)
        _raw_a = _fut_a.result()
        _raw_b = _fut_b.result()

    # Merge results
    _raw = ""
    _ideas_merged = []
    for _raw_part in [_raw_a, _raw_b]:
        if not _raw_part:
            continue
        _clean_part = _raw_part.strip()
        if _clean_part.startswith("```"):
            _clean_part = _clean_part.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        try:
            _ideas_merged.extend(json.loads(_clean_part))
        except Exception:
            _m = re.search(r'\[[\s\S]*\]', _raw_part)
            if _m:
                try:
                    _ideas_merged.extend(json.loads(_m.group(0)))
                except Exception:
                    pass
    # Convert merged ideas back to raw JSON for existing parser compatibility
    _raw = json.dumps(_ideas_merged) if _ideas_merged else ""

    _ideas = []
    try:
        _clean = _raw.strip()
        if _clean.startswith("```"):
            _clean = _clean.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        _ideas = json.loads(_clean)
    except Exception:
        try:
            _m = re.search(r'\[[\s\S]*\]', _raw)
            if _m:
                _ideas = json.loads(_m.group(0))
        except Exception:
            pass

        for _idea in list(_ideas):
            _hook = _idea.get("hook", "")
            if _hook.startswith("RT ") or _hook.startswith("@"):
                _ideas.remove(_idea)
                continue
            if not _idea.get("hook", "").strip():
                _ideas.remove(_idea)
                continue
            if "voice" not in _idea or _idea["voice"] not in ("Default", "Critical", "Hype", "Sarcastic"):
                _idea["voice"] = "Default"

        for _idea in _ideas:
            _hook = _idea.get("hook", "")
            if "\n" in _hook:
                _hook = _hook.split("\n")[0].strip()
                _idea["hook"] = _hook
            if len(_hook) > 280:
                _idea["hook"] = _hook[:277] + "..."

    # Save to gist for instant loads on future visits
    if _ideas:
        _save_inspo_to_gist(_ideas, len(_all_tweets), len(_rss_headlines))

    return _ideas, len(_all_tweets), len(_rss_headlines)


@st.dialog("Build a Tweet", width="large")
def _ci_build_dialog():
    """Mini-form to guide users into providing the right raw material for BUILD."""
    st.markdown(
        '<div style="font-size:12px;color:rgba(255,255,255,0.35);margin-bottom:16px;">'
        'Give us a topic and we\'ll create 3 unique tweet options. The more context you add, the better the results.</div>',
        unsafe_allow_html=True)

    _bd_topic = st.text_input("What's the topic?", placeholder="e.g. Jokic MVP case, Broncos draft needs, Sean Payton play calling", key="build_topic")

    _bd_take = st.text_input("What's your take? (optional)", placeholder="e.g. he's the clear frontrunner, we need a TE round 1", key="build_take")

    _bd_col1, _bd_col2 = st.columns(2)
    with _bd_col1:
        _bd_tension = st.text_input("What's the debate? (optional)", placeholder="e.g. media keeps ignoring him, fans disagree", key="build_tension")
    with _bd_col2:
        _bd_stats = st.text_input("Any specific stats or facts? (optional)", placeholder="e.g. averaging a triple double, 48-28 record", key="build_stats")

    st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)

    if st.button("BUILD IT", key="build_submit", use_container_width=True, type="primary", disabled=not _bd_topic.strip()):
        # Assemble the structured brief from form fields
        _parts = []
        if _bd_topic.strip():
            _parts.append(f"TOPIC: {_bd_topic.strip()}")
        if _bd_tension.strip():
            _parts.append(f"TENSION: {_bd_tension.strip()}")
        if _bd_stats.strip():
            _parts.append(f"KEY STATS: {_bd_stats.strip()}")
        if _bd_take.strip():
            _parts.append(f"ANGLE: {_bd_take.strip()}")

        _assembled = "\n".join(_parts) if len(_parts) > 1 else _bd_topic.strip()

        # If they only gave a topic with no extras, use it as a simple concept
        if not _bd_take.strip() and not _bd_tension.strip() and not _bd_stats.strip():
            _assembled = _bd_topic.strip()

        _bd_fmt = st.session_state.get("ci_format", "Normal Tweet")
        _bd_voice = st.session_state.get("ci_voice", "Default")

        # Run AI generation inside the dialog so user sees the spinner
        with st.spinner("Building your tweets..."):
            st.session_state["ci_text"] = _assembled
            _run_ci_ai("build", _assembled, _bd_fmt, _bd_voice)

        # Show results inside the dialog
        _bd_result = st.session_state.get("ci_banger_data")
        if _bd_result:
            st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)
            st.markdown(
                '<div style="font-size:13px;font-weight:700;color:rgba(255,255,255,0.7);margin-bottom:10px;">Your Options</div>',
                unsafe_allow_html=True)
            for _bdi in range(1, 4):
                _bd_opt = _bd_result.get(f"option{_bdi}")
                _bd_pat = _bd_result.get(f"option{_bdi}_pattern", "")
                if not _bd_opt:
                    continue
                _bd_is_pick = str(_bd_result.get("pick", "")) == str(_bdi)
                _bd_border = "rgba(45,212,191,0.4)" if _bd_is_pick else "rgba(255,255,255,0.07)"
                _bd_pick_badge = '<span style="font-size:8px;font-weight:700;padding:2px 7px;border-radius:3px;background:rgba(45,212,191,0.15);color:rgba(45,212,191,0.8);border:1px solid rgba(45,212,191,0.3);margin-left:6px;">TOP PICK</span>' if _bd_is_pick else ""
                st.markdown(
                    f'<div style="border-radius:10px;border:1px solid {_bd_border};background:rgba(255,255,255,0.03);padding:14px;margin-bottom:8px;">'
                    f'<div style="font-size:9px;color:rgba(255,255,255,0.3);margin-bottom:6px;">{_bd_pat}{_bd_pick_badge}</div>'
                    f'<div style="font-size:14px;color:rgba(255,255,255,0.9);line-height:1.6;white-space:pre-wrap;">{_bd_opt}</div>'
                    f'</div>',
                    unsafe_allow_html=True)
                if st.button(f"Use Option {_bdi}", key=f"build_use_{_bdi}", use_container_width=True,
                             type="primary" if _bd_is_pick else "secondary"):
                    st.session_state["ci_text"] = _bd_opt
                    if _bd_voice in ("Default", "Critical", "Hype", "Sarcastic"):
                        st.session_state["ci_voice"] = _bd_voice
                    st.rerun(scope="app")
        elif st.session_state.get("ci_result"):
            st.markdown(f'<div style="font-size:14px;color:rgba(255,255,255,0.9);line-height:1.6;padding:12px;white-space:pre-wrap;">{st.session_state["ci_result"]}</div>', unsafe_allow_html=True)
            if st.button("Use This", key="build_use_raw", use_container_width=True, type="primary"):
                st.session_state["ci_text"] = st.session_state["ci_result"]
                st.rerun(scope="app")
        else:
            st.error("Couldn't generate tweets. Try again or add more detail.")


@st.dialog("What's Hot Right Now", width="large")
def _ci_inspiration_dialog():
    """Show cached ideas — only calls Claude once per open, not on every button click."""
    _inspo_handle = get_current_handle()
    _inspo_topics = load_json("topics.json", {}) if is_guest() else {}
    _inspo_cache_key = json.dumps({
        "handle": _inspo_handle,
        "guest": is_guest(),
        "topics": _inspo_topics,
    }, sort_keys=True)
    if st.session_state.get("inspo_handle") != _inspo_handle:
        for _k in ["inspo_ideas", "inspo_meta", "inspo_page"]:
            st.session_state.pop(_k, None)
        st.session_state["inspo_handle"] = _inspo_handle

    # Load ideas: session state > gist cache > Claude (slowest, last resort)
    if "inspo_ideas" not in st.session_state:
        # Try gist first — instant load if fresh ideas exist
        _gist_ideas, _gist_nt, _gist_nh = _load_inspo_from_gist(_inspo_cache_key)
        if _gist_ideas:
            st.session_state["inspo_ideas"] = _gist_ideas
            st.session_state["inspo_meta"] = (_gist_nt, _gist_nh)
            st.session_state["inspo_page"] = 0
        else:
            # No gist cache — generate fresh (slow, but only happens once)
            with st.spinner("Post Ascend AI is working..."):
                _all_ideas, _n_tweets, _n_heads = _run_inspiration_claude(_inspo_cache_key)
            if not _all_ideas:
                st.error("Couldn't generate ideas — try again.")
                return
            st.session_state["inspo_ideas"] = _all_ideas
            st.session_state["inspo_meta"] = (_n_tweets, _n_heads)
            st.session_state["inspo_page"] = 0

    _all_ideas = st.session_state["inspo_ideas"]
    _n_tweets, _n_heads = st.session_state.get("inspo_meta", (0, 0))
    _page = st.session_state.get("inspo_page", 0)
    _per_page = 7

    # Wrap page if beyond available ideas
    if _page > 0 and _page * _per_page >= len(_all_ideas):
        _page = 0
        st.session_state["inspo_page"] = 0

    _start = (_page * _per_page) % max(len(_all_ideas), 1)
    _ideas = (_all_ideas + _all_ideas)[_start:_start + _per_page]  # wrap-around slice

    # ── Header ──
    st.markdown(
        f'<div style="font-size:15px;font-weight:700;color:rgba(255,255,255,0.85);margin-bottom:3px;">What\'s Hot Right Now</div>'
        f'<div style="font-size:10px;color:rgba(255,255,255,0.22);margin-bottom:16px;">'
        f'{_n_tweets} timeline tweets · {_n_heads} news headlines · last 24h</div>',
        unsafe_allow_html=True)

    # ── Source badge styles ──
    _badge_styles = {
        "twitter":  ("rgba(45,212,191,0.1)",  "rgba(45,212,191,0.65)",  "rgba(45,212,191,0.18)",  "TIMELINE"),
        "espn":     ("rgba(251,191,36,0.1)",   "rgba(251,191,36,0.65)",  "rgba(251,191,36,0.18)",  "ESPN"),
        "news":     ("rgba(167,139,250,0.1)",  "rgba(167,139,250,0.65)", "rgba(167,139,250,0.18)", "NEWS"),
    }
    _badge_default = ("rgba(100,100,120,0.1)", "rgba(200,200,220,0.5)", "rgba(100,100,120,0.2)", "SOURCE")
    _voice_badge_styles = {
        "Default":   ("rgba(100,100,120,0.1)", "rgba(180,180,200,0.65)", "rgba(100,100,120,0.2)"),
        "Critical":  ("rgba(248,113,113,0.1)", "rgba(248,113,113,0.65)", "rgba(248,113,113,0.2)"),
        "Hype":     ("rgba(45,212,191,0.1)",  "rgba(45,212,191,0.65)",  "rgba(45,212,191,0.2)"),
        "Sarcastic": ("rgba(251,191,36,0.1)",  "rgba(251,191,36,0.65)",  "rgba(251,191,36,0.2)"),
    }

    # ── Cards ──
    for _i, _idea in enumerate(_ideas):
        _topic = _idea.get("topic", "")
        _src   = _idea.get("source", "twitter").lower()
        _hook  = _idea.get("hook", "")
        _why   = _idea.get("why", "")
        _bg, _fg, _border, _label = _badge_styles.get(_src, _badge_default)
        _voice = _idea.get("voice", "Default")
        _vbg, _vfg, _vborder = _voice_badge_styles.get(_voice, _voice_badge_styles["Default"])

        st.markdown(
            f'<div style="border-radius:12px;border:1px solid rgba(255,255,255,0.07);background:rgba(255,255,255,0.03);padding:16px;margin-bottom:4px;">'
              f'<div style="display:flex;align-items:center;gap:7px;margin-bottom:10px;">'
                f'<span style="font-size:11px;font-weight:600;color:rgba(255,255,255,0.38);">{_topic}</span>'
                f'<span style="font-size:8px;font-weight:700;padding:2px 7px;border-radius:3px;letter-spacing:0.05em;background:{_bg};color:{_fg};border:1px solid {_border};">{_label}</span>'
                f'<span style="font-size:8px;font-weight:700;padding:2px 7px;border-radius:3px;letter-spacing:0.05em;background:{_vbg};color:{_vfg};border:1px solid {_vborder};margin-left:4px;">{_voice.upper()}</span>'
              f'</div>'
              f'<div style="font-size:15px;font-weight:500;color:rgba(255,255,255,0.9);line-height:1.7;letter-spacing:0.01em;margin-bottom:8px;">{_hook}</div>'
              f'<div style="font-size:11px;color:rgba(255,255,255,0.35);line-height:1.5;margin-bottom:12px;">{_why}</div>'
            f'</div>',
            unsafe_allow_html=True)

        _ib1, _ib2 = st.columns([2, 1])
        with _ib1:
            if st.button("USE THIS", key=f"inspo_use_{_i}", use_container_width=True, type="primary"):
                if _hook:
                    st.session_state["ci_text"] = _hook
                    _idea_voice = _idea.get("voice", "Default")
                    if _idea_voice in ("Default", "Critical", "Hype", "Sarcastic"):
                        st.session_state["ci_voice"] = _idea_voice
                st.rerun(scope="app")
        with _ib2:
            if pplx_available() and st.button("Verify", key=f"inspo_verify_{_i}", use_container_width=True):
                with st.spinner("Checking..."):
                    _fci = pplx_fact_check(_hook)
                if _fci.get("answer"):
                    st.session_state[f"_inspo_v_{_i}"] = _fci
                else:
                    st.warning("Verify failed.")
        _ivr = st.session_state.get(f"_inspo_v_{_i}")
        if _ivr:
            _iva = _ivr["answer"]
            _ivc = _ivr.get("citations", [])
            _icol = "#2DD4BF" if "accurate" in _iva.lower() or "correct" in _iva.lower() else "#FBBF24"
            st.markdown(f'<div style="background:#0d1829;border-left:3px solid {_icol};padding:8px 12px;border-radius:6px;margin:4px 0;font-size:11px;color:#b8c8d8;line-height:1.5;">{_iva}</div>', unsafe_allow_html=True)
            if _ivc:
                st.markdown(f'<div style="font-size:9px;color:#3a5070;">Sources: {", ".join(str(c) for c in _ivc[:3])}</div>', unsafe_allow_html=True)

        st.markdown('<div style="margin-bottom:6px;"></div>', unsafe_allow_html=True)

    # ── Footer actions ──
    def _inspo_regenerate():
        """Nuke cached ideas and regenerate a completely fresh set."""
        _run_inspiration_claude.clear()
        st.session_state.pop("inspo_ideas", None)
        st.session_state.pop("inspo_meta", None)
        st.session_state["inspo_page"] = 0
        st.session_state["_ci_show_inspiration"] = True
    if st.button("New Ideas", use_container_width=True, key="inspo_regen", on_click=_inspo_regenerate):
        pass


@st.dialog("Creator Studio", width="large")
def _ci_output_panel(_nonce, action, tweet_text, fmt, voice):
    """_nonce forces Streamlit to create a fresh dialog every call.
    Without it, @st.dialog caches by arguments and may serve stale results."""
    _ci_output_panel_impl(action, tweet_text, fmt, voice)


@st.dialog("Idea Bank", width="large")
def _ci_bank_dialog():
    """Idea Bank as a popup modal."""
    _default_folders = ["Uncategorized", "Evergreen", "Timely", "Thread Ideas", "Video Ideas"]
    _all_folders = load_json("saved_ideas_folders.json", _default_folders)
    _folder_opts = ["Idea Bank Vault"] + _all_folders + ["All Ideas", "Rewrite Queue"]

    if "ci_folder" not in st.session_state:
        st.session_state["ci_folder"] = "Idea Bank Vault"
    folder = st.selectbox("Folder", _folder_opts, key="ci_folder")

    if folder in ("Idea Bank Vault", "Rewrite Queue"):
        _bank_kind = "inspiration" if folder == "Idea Bank Vault" else "repurpose"
        inspo_items = _load_bank_items(_bank_kind)
        if not inspo_items:
            st.markdown(f'<div class="output-box">No items in {folder} yet.</div>', unsafe_allow_html=True)
        else:
            for ii, item in enumerate(reversed(inspo_items[-30:])):
                orig_text = item.get("repurposed_text") or item.get("text", "")
                author = item.get("author", "") or item.get("handle", "")
                ts = item.get("saved_at", "")[:10]
                st.markdown(f"""<div class="tweet-card">
                    <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
                        <span class="tweet-num">{author}</span>
                        <span style="font-size:11px;color:#444466;">{ts}</span>
                    </div>
                    <div style="color:#d8d8e8;font-size:13px;line-height:1.5;">{orig_text[:200]}{'...' if len(orig_text)>200 else ''}</div>
                </div>""", unsafe_allow_html=True)
                _vb1, _vb2 = st.columns(2)
                with _vb1:
                    if st.button("Use This", key=f"ci_inspo_use_{ii}", use_container_width=True, type="primary"):
                        st.session_state["_ci_text_stage"] = item.get("text", orig_text)
                        st.rerun(scope="app")
                with _vb2:
                    if st.button("Repurpose", key=f"ci_inspo_{ii}", use_container_width=True):
                        st.session_state["ci_repurpose_seed"] = item.get("text", orig_text)
                        st.session_state["ci_auto_repurpose"] = True
                        st.rerun(scope="app")
    else:
        ideas = load_json("saved_ideas.json", [])
        if folder == "All Ideas":
            raw = _load_bank_items("inspiration")
            inspo_as_ideas = [{"text": i.get("text",""), "category": "Idea Bank", "format": i.get("author",""), "saved_at": i.get("saved_at","")} for i in raw]
            filtered = ideas + inspo_as_ideas
            filtered.sort(key=lambda x: x.get("saved_at",""), reverse=True)
        else:
            filtered = [i for i in ideas if i.get("category") == folder]
        if not filtered:
            st.markdown('<div class="output-box">No saved ideas yet.</div>', unsafe_allow_html=True)
        else:
            for i, idea in enumerate(reversed(filtered[-30:]) if folder != "All Ideas" else filtered[:30]):
                ts = idea.get("saved_at", "")[:10]
                cat = idea.get("category", "")
                st.markdown(f"""<div class="tweet-card">
                    <div style="display:flex;justify-content:space-between;">
                        <span class="tweet-num">{idea.get('format','')}</span>
                        <span style="font-size:11px;color:#444466;">{ts} <span class="tag">{cat}</span></span>
                    </div>
                    <div style="color:#d8d8e8;font-size:13px;">{idea.get('text','')[:150]}{'...' if len(idea.get('text',''))>150 else ''}</div>
                </div>""", unsafe_allow_html=True)
                if st.button("Use This", key=f"bank_use_{i}", use_container_width=True):
                    st.session_state["_ci_text_stage"] = idea.get("text", "")
                    st.rerun(scope="app")


@st.dialog("Creator Studio Walkthrough", width="large")
def _ci_help_dialog():
    st.markdown(
        '<div style="color:#8FA6C6;font-size:14px;margin-bottom:10px;">'
        'Watch the Creator Studio workflow for concept entry, voice selection, Build, Refresh Options, and Grades.'
        '</div>',
        unsafe_allow_html=True,
    )
    _creator_help_video = _load_local_video_bytes("creator-studio-walkthrough.mp4")
    if _creator_help_video:
        st.video(_creator_help_video)
    else:
        st.caption("Creator Studio walkthrough video is not available in this deployment yet.")


@st.dialog("Content Coach Walkthrough", width="large")
def _coach_help_dialog():
    st.markdown(
        '<div style="color:#8FA6C6;font-size:14px;margin-bottom:10px;">'
        'Watch how to use Content Coach to ask smarter questions, switch formats, and turn guidance into usable posts.'
        '</div>',
        unsafe_allow_html=True,
    )
    _coach_help_video = _load_local_video_bytes("content-coach-walkthrough.mp4")
    if _coach_help_video:
        st.video(_coach_help_video)
    else:
        st.caption("Content Coach walkthrough video is not available in this deployment yet.")


@st.dialog("Article Writer Walkthrough", width="large")
def _article_writer_help_dialog():
    st.markdown(
        '<div style="color:#8FA6C6;font-size:14px;margin-bottom:10px;">'
        'Watch how to turn tweets, raw thoughts, or scratch ideas into full X Articles with outlines, research, and polished drafts.'
        '</div>',
        unsafe_allow_html=True,
    )
    _article_help_video = _load_local_video_bytes("article-writer-walkthrough.mp4")
    if _article_help_video:
        st.video(_article_help_video)
    else:
        st.caption("Article Writer walkthrough video is not available in this deployment yet.")


@st.dialog("Reply Mode Walkthrough", width="large")
def _reply_mode_help_dialog():
    st.markdown(
        '<div style="color:#8FA6C6;font-size:14px;margin-bottom:10px;">'
        'Watch how to load a feed, generate stronger replies, and build a consistent daily engagement habit inside Reply Mode.'
        '</div>',
        unsafe_allow_html=True,
    )
    _reply_help_video = _load_local_video_bytes("reply-mode-walkthrough.mp4")
    if _reply_help_video:
        st.video(_reply_help_video)
    else:
        st.caption("Reply Mode walkthrough video is not available in this deployment yet.")


@st.dialog("Idea Bank Walkthrough", width="large")
def _idea_bank_help_dialog():
    st.markdown(
        '<div style="color:#8FA6C6;font-size:14px;margin-bottom:10px;">'
        'Watch how to save inspiration into the vault, filter your bank, and reuse strong ideas when you need them.'
        '</div>',
        unsafe_allow_html=True,
    )
    _idea_bank_help_video = _load_local_video_bytes("idea-bank-walkthrough.mp4")
    if _idea_bank_help_video:
        st.video(_idea_bank_help_video)
    else:
        st.caption("Idea Bank walkthrough video is not available in this deployment yet.")


@st.dialog("Account Audit Walkthrough", width="large")
def _account_audit_help_dialog():
    st.markdown(
        '<div style="color:#8FA6C6;font-size:14px;margin-bottom:10px;">'
        'Watch how to run an account audit, read the health score, and use the recommendations to tighten your growth strategy.'
        '</div>',
        unsafe_allow_html=True,
    )
    _account_audit_help_video = _load_local_video_bytes("account-audit-walkthrough.mp4")
    if _account_audit_help_video:
        st.video(_account_audit_help_video)
    else:
        st.caption("Account Audit walkthrough video is not available in this deployment yet.")


@st.dialog("Raw Thoughts Walkthrough", width="large")
def _raw_thoughts_help_dialog():
    st.markdown(
        '<div style="color:#8FA6C6;font-size:14px;margin-bottom:10px;">'
        'Watch how to set the timer, dump your thoughts fast, and turn raw ideas into subjects, tweet options, or longer content.'
        '</div>',
        unsafe_allow_html=True,
    )
    _raw_thoughts_help_video = _load_local_video_bytes("raw-thoughts-walkthrough.mp4")
    if _raw_thoughts_help_video:
        st.video(_raw_thoughts_help_video)
    else:
        st.caption("Raw Thoughts walkthrough video is not available in this deployment yet.")


@st.dialog("Post History Walkthrough", width="large")
def _post_history_help_dialog():
    st.markdown(
        '<div style="color:#8FA6C6;font-size:14px;margin-bottom:10px;">'
        'Watch how to sync post history, scan your best performers, and use the AI analysis tools to understand what is already working.'
        '</div>',
        unsafe_allow_html=True,
    )
    _post_history_help_video = _load_local_video_bytes("post-history-walkthrough.mp4")
    if _post_history_help_video:
        st.video(_post_history_help_video)
    else:
        st.caption("Post History walkthrough video is not available in this deployment yet.")


@st.dialog("Algorithm Score Walkthrough", width="large")
def _algorithm_score_help_dialog():
    st.markdown(
        '<div style="color:#8FA6C6;font-size:14px;margin-bottom:10px;">'
        'Watch how to paste in a draft, run Grades, and read the score, weaknesses, and optimized rewrite before posting.'
        '</div>',
        unsafe_allow_html=True,
    )
    _algorithm_score_help_video = _load_local_video_bytes("algorithm-score-walkthrough.mp4")
    if _algorithm_score_help_video:
        st.video(_algorithm_score_help_video)
    else:
        st.caption("Algorithm Score walkthrough video is not available in this deployment yet.")


@st.dialog("My Stats Walkthrough", width="large")
def _my_stats_help_dialog():
    st.markdown(
        '<div style="color:#8FA6C6;font-size:14px;margin-bottom:10px;">'
        'Watch how to refresh your account snapshot, review performance metrics, and use the pulse view to spot trends fast.'
        '</div>',
        unsafe_allow_html=True,
    )
    _my_stats_help_video = _load_local_video_bytes("my-stats-walkthrough.mp4")
    if _my_stats_help_video:
        st.video(_my_stats_help_video)
    else:
        st.caption("My Stats walkthrough video is not available in this deployment yet.")


@st.dialog("Profile Analyzer Walkthrough", width="large")
def _profile_analyzer_help_dialog():
    st.markdown(
        '<div style="color:#8FA6C6;font-size:14px;margin-bottom:10px;">'
        'Watch how to enter a handle, run research, and read the strategy, voice, and tactical takeaways from another account.'
        '</div>',
        unsafe_allow_html=True,
    )
    _profile_analyzer_help_video = _load_local_video_bytes("profile-analyzer-walkthrough.mp4")
    if _profile_analyzer_help_video:
        st.video(_profile_analyzer_help_video)
    else:
        st.caption("Profile Analyzer walkthrough video is not available in this deployment yet.")


@st.dialog("Signals & Prompts Walkthrough", width="large")
def _signals_prompts_help_dialog():
    st.markdown(
        '<div style="color:#8FA6C6;font-size:14px;margin-bottom:10px;">'
        'Watch how to scan beat and national signals, flip views, and turn live angles into creator-ready prompts.'
        '</div>',
        unsafe_allow_html=True,
    )
    _signals_help_video = _load_local_video_bytes("signals-prompts-walkthrough.mp4")
    if _signals_help_video:
        st.video(_signals_help_video)
    else:
        st.caption("Signals & Prompts walkthrough video is not available in this deployment yet.")


@st.dialog("Debug Console Walkthrough", width="large")
def _debug_console_help_dialog():
    st.markdown(
        '<div style="color:#8FA6C6;font-size:14px;margin-bottom:10px;">'
        'Watch how to use the owner debug console to inspect AI routing, proxy health, pipeline status, and live backend checks.'
        '</div>',
        unsafe_allow_html=True,
    )
    _debug_help_video = _load_local_video_bytes("debug-console-walkthrough.mp4")
    if _debug_help_video:
        st.video(_debug_help_video)
    else:
        st.caption("Debug Console walkthrough video is not available in this deployment yet.")


def page_compose_ideas():
    st.markdown('<div class="main-header">CREATOR <span>STUDIO</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Draft, refine, and ship your best content.</div>', unsafe_allow_html=True)
    st.markdown(
        '''<div style="display:flex;justify-content:flex-start;margin:0 0 16px 0;">
            <span class="cs-bot" data-bot="ci_help_video" style="height:52px;padding:0 18px;border-radius:14px;font-size:12px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;border:1px solid rgba(196,158,60,0.45);background:rgba(45,212,191,0.1);color:#C49E3C;cursor:pointer;display:inline-flex;align-items:center;gap:6px;">See How It Works</span>
        </div>''',
        unsafe_allow_html=True,
    )
    if st.button("bot_ci_help_video", key="ci_help_video"):
        _ci_help_dialog()
    st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

    # Consume staging key FIRST — before any widget is registered
    _idea_from_url = st.query_params.get("idea", "")
    if _idea_from_url:
        st.session_state["ci_text"] = _idea_from_url
        del st.query_params["idea"]
    elif "_ci_text_stage" in st.session_state:
        st.session_state["ci_text"] = st.session_state.pop("_ci_text_stage")

    # Auto-repurpose from Idea Bank Vault click
    if st.session_state.get("ci_auto_repurpose") and st.session_state.get("ci_repurpose_seed"):
        seed = st.session_state.pop("ci_repurpose_seed")
        st.session_state.pop("ci_auto_repurpose", None)
        st.session_state["ci_text"] = seed
        _fmt = st.session_state.get("ci_format", "Normal Tweet")
        _vc = st.session_state.get("ci_voice", "Default")
        with st.spinner("Post Ascend AI is working..."):
            _run_ci_ai("rewrite", seed, _fmt, _vc)
        _ci_output_panel(str(time.time()), "rewrite", seed, _fmt, _vc)
        return

    # Redo pending from modal
    _pending_redo = st.session_state.pop("ci_dialog_pending", None)

    # ── Init format/voice in session state ──
    if "ci_format" not in st.session_state:
        st.session_state["ci_format"] = "Normal Tweet"
    if "ci_voice" not in st.session_state:
        st.session_state["ci_voice"] = "Default"

    # ── CENTERED SINGLE-COLUMN LAYOUT ──
    _spacer_l, _center, _spacer_r = st.columns([0.5, 4, 0.5])
    with _center:
        # ── Text area ──
        tweet_text = st.text_area("Your concept", height=200, key="ci_text",
            placeholder="Drop your concept, angle, or raw thought...", label_visibility="collapsed")
        char_len = len(tweet_text)

        # ── Circular character counter ──
        _pct = min(char_len / 280 * 100, 100)
        _offset = 100 - _pct
        _cc = "#E8441A" if char_len >= 280 else "#C49E3C" if char_len >= 250 else "#2DD4BF"
        st.markdown(f'''<div style="display:flex;justify-content:flex-end;margin-top:-10px;margin-bottom:8px;">
          <div style="width:32px;height:32px;position:relative;">
            <svg viewBox="0 0 36 36" style="transform:rotate(-90deg);width:32px;height:32px;">
              <circle cx="18" cy="18" r="16" fill="none" stroke="#1a2a45" stroke-width="3"/>
              <circle cx="18" cy="18" r="16" fill="none" stroke="{_cc}" stroke-width="3"
                stroke-dasharray="100" stroke-dashoffset="{_offset}" stroke-linecap="round"/>
            </svg>
            <span style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-size:8px;color:#5a7090;font-weight:600;">{char_len}</span>
          </div>
        </div>''', unsafe_allow_html=True)

        # ── Format pills (real Streamlit buttons, CSS makes them compact) ──
        _fmt_opts = ["Punchy Tweet", "Normal Tweet", "Long Tweet", "Thread", "Article"]
        _fmt_short = {"Punchy Tweet": "Punchy", "Normal Tweet": "Normal", "Long Tweet": "Long", "Thread": "Thread", "Article": "Article"}
        _cur_fmt = st.session_state.get("ci_format", "Normal Tweet")
        st.markdown('<div style="font-size:9px;font-weight:700;letter-spacing:1.2px;color:#3a5070;text-transform:uppercase;margin-bottom:4px;">Format</div>', unsafe_allow_html=True)
        _fc = st.columns(len(_fmt_opts))
        for _i, _fo in enumerate(_fmt_opts):
            with _fc[_i]:
                if st.button(_fmt_short[_fo], key=f"cs_fmt_{_i}",
                             type="primary" if _fo == _cur_fmt else "secondary"):
                    st.session_state["ci_format"] = _fo
                    st.rerun()

        # ── Voice pills ──
        _custom_voices = load_json("voice_styles.json", [])
        _voice_opts = ["Default", "Critical", "Hype", "Sarcastic"] + [s["name"] for s in _custom_voices]
        _cur_voice = st.session_state.get("ci_voice", "Default")
        st.markdown('<div style="font-size:9px;font-weight:700;letter-spacing:1.2px;color:#3a5070;text-transform:uppercase;margin-bottom:4px;margin-top:8px;">Voice</div>', unsafe_allow_html=True)
        _vc = st.columns(len(_voice_opts))
        for _i, _vo in enumerate(_voice_opts):
            with _vc[_i]:
                if st.button(_vo, key=f"cs_voice_{_i}",
                             type="primary" if _vo == _cur_voice else "secondary"):
                    st.session_state["ci_voice"] = _vo
                    st.rerun()

        st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

        # ── Action dock: icon buttons rendered as HTML, hidden Streamlit buttons for click handling ──
        def _click_action(action):
            _ci_input = st.session_state.get("ci_text", "").strip()
            if _ci_input:
                # Smart nudge: if GO VIRAL with very short input, suggest BUILD instead
                if action == "banger" and len(_ci_input.split()) < 8:
                    st.session_state["_ci_show_build_dialog"] = True
                    return
                st.session_state["_ci_pending"] = (action, _ci_input,
                    st.session_state.get("ci_format", "Normal Tweet"), st.session_state.get("ci_voice", "Default"))

        st.markdown('''<div style="font-size:8px;font-weight:700;letter-spacing:1.5px;color:#2a3a55;text-transform:uppercase;margin-bottom:8px;">ACTIONS</div>
        <div class="cs-icon-dock" style="display:flex;gap:8px;justify-content:center;margin-bottom:16px;">
          <div class="cs-idock-btn cs-idock-primary" data-dock="banger" data-tooltip="Polish Your Draft Into A High-Performance Post" style="width:52px;height:52px;border-radius:14px;background:linear-gradient(135deg,#1fb8a8,#2DD4BF);display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" stroke="#060A12" stroke-width="2" stroke-linejoin="round"/></svg>
            <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">GO VIRAL</span>
          </div>
          <div class="cs-idock-btn" data-dock="build" data-tooltip="Create Tweets From A Topic, Idea, Or Bullet Points" style="width:52px;height:52px;border-radius:14px;border:1px solid #1a2a45;background:#0a1220;display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M12 5v14M5 12h14" stroke="#5a7090" stroke-width="2" stroke-linecap="round"/></svg>
            <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">BUILD</span>
          </div>
          <div class="cs-idock-btn" data-dock="rewrite" data-tooltip="Remix Your Draft Into A New Format Or Angle" style="width:52px;height:52px;border-radius:14px;border:1px solid #1a2a45;background:#0a1220;display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><polyline points="1 4 1 10 7 10" stroke="#5a7090" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10" stroke="#5a7090" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">REPURPOSE</span>
          </div>
          <div class="cs-idock-btn" data-dock="grades" data-tooltip="Grade Your Draft On Hook, Voice, And Viral Potential" style="width:52px;height:52px;border-radius:14px;border:1px solid #1a2a45;background:#0a1220;display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M22 12h-4l-3 9L9 3l-3 9H2" stroke="#5a7090" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
            <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">GRADES</span>
          </div>
        </div>''', unsafe_allow_html=True)

        # Hidden Streamlit buttons for dock click handling (inside real container)
        st.button("dock_banger", key="ci_banger", on_click=_click_action, args=("banger",))
        def _click_build():
            st.session_state["_ci_show_build_dialog"] = True
        st.button("dock_build", key="ci_build", on_click=_click_build)
        st.button("dock_rewrite", key="ci_repurpose", on_click=_click_action, args=("rewrite",))
        st.button("dock_grades", key="ci_engage", on_click=_click_action, args=("grades",))

        # ── Divider + Bottom bar as HTML ──
        st.markdown('''<div style="height:1px;background:#1a2a45;margin:24px 0 14px;"></div>
        <div class="cs-bottom-bar" style="display:flex;gap:8px;justify-content:center;">
          <span class="cs-bot" data-bot="save" data-tooltip="Save Draft To Your Idea Bank" style="height:52px;padding:0 18px;border-radius:14px;font-size:10px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;border:1px solid #1a2a45;background:#0a1220;color:#5a7090;cursor:pointer;display:inline-flex;align-items:center;gap:6px;">↓ Save</span>
          <span class="cs-bot" data-bot="bank" data-tooltip="Open Your Saved Ideas And Inspiration Vault" style="height:52px;padding:0 18px;border-radius:14px;font-size:10px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;border:1px solid rgba(196,158,60,0.25);background:#0a1220;color:rgba(196,158,60,0.6);cursor:pointer;display:inline-flex;align-items:center;gap:6px;">Bank</span>
          <span class="cs-bot" data-bot="hot" data-tooltip="Trending Topics And Fresh Tweet Ideas" style="height:52px;padding:0 18px;border-radius:14px;font-size:10px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;border:1px solid #1a2a45;background:#0a1220;color:#5a7090;cursor:pointer;display:inline-flex;align-items:center;gap:6px;">What\'s Hot</span>
          <span class="cs-bot" data-bot="post" data-tooltip="Post Directly To X" style="height:52px;padding:0 18px;border-radius:14px;font-size:10px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;background:linear-gradient(135deg,#1fb8a8,#2DD4BF);color:#060A12;cursor:pointer;display:inline-flex;align-items:center;gap:6px;border:none;">𝕏 Post</span>
        </div>''', unsafe_allow_html=True)

        # Hidden Streamlit buttons for bottom bar (inside real container)
        if st.button("bot_save", key="ci_save"):
            if tweet_text.strip():
                ideas = load_json("saved_ideas.json", [])
                ideas.append({"text": tweet_text, "format": st.session_state.get("ci_format", "Normal Tweet"),
                              "category": "Uncategorized", "saved_at": datetime.now().isoformat()})
                save_json("saved_ideas.json", ideas)
                st.success("Saved.")
        if st.button("bot_bank", key="ci_bank_btn"):
            st.session_state["_ci_show_bank"] = True
        if st.button("bot_hot", key="ci_inspiration"):
            st.session_state["_ci_show_inspiration"] = True
        if st.button("bot_post", key="ci_post_direct"):
            if is_guest():
                # Guests: open intent link in browser instead of direct post
                import urllib.parse as _up_post
                _enc_post = _up_post.quote(tweet_text.strip()[:280])
                st.markdown(f'<a href="https://twitter.com/intent/tweet?text={_enc_post}" target="_blank" style="display:inline-block;padding:8px 16px;background:#2DD4BF;border-radius:8px;color:#000;font-weight:600;text-decoration:none;">Open in X to Post</a>', unsafe_allow_html=True)
            elif tweet_text.strip():
                with st.spinner("Posting..."):
                    _ok, _err = _post_tweet(tweet_text.strip())
                if _ok:
                    st.success("Posted to X!")
                else:
                    st.error(f"Post failed — {_err}")

    # ── Modal triggers ──
    def _clear_banger():
        for _k in ["ci_banger_data"] + [f"ci_banger_opt_{i}" for i in [1, 2, 3]]:
            st.session_state.pop(_k, None)

    _ci_pending_raw = st.session_state.pop("_ci_pending", None)
    _is_redo = st.session_state.pop("_ci_pending_is_redo", False)
    if _ci_pending_raw:
        _pending = _ci_pending_raw
    elif _pending_redo:
        _pending = (_pending_redo["action"], _pending_redo["tweet_text"], _pending_redo["fmt"], _pending_redo["voice"])
        _is_redo = True
    else:
        _pending = None

    if _pending:
        _action, _txt, _fmt, _voice = _pending
        _skip_ai = st.session_state.pop("_ci_pending_skip_ai", False)
        if not _skip_ai:
            if _action in ("banger", "build", "rewrite"):
                _clear_banger()
            elif _action == "grades":
                st.session_state.pop("ci_grades", None)
            with st.spinner("Post Ascend AI is working..."):
                _run_ci_ai(_action, _txt, _fmt, _voice)
        _ci_output_panel(str(time.time()), _action, _txt, _fmt, _voice)

    _reopen_dialog = st.session_state.pop("_ci_reopen_dialog", None)
    if _reopen_dialog:
        _ci_output_panel(
            str(time.time()),
            _reopen_dialog["action"],
            _reopen_dialog["tweet_text"],
            _reopen_dialog["fmt"],
            _reopen_dialog["voice"],
        )

    if st.session_state.pop("_ci_show_build_dialog", False):
        _ci_build_dialog()

    if st.session_state.pop("_ci_show_inspiration", False):
        _ci_inspiration_dialog()

    if st.session_state.pop("_ci_show_bank", False):
        _ci_bank_dialog()

# ═══════════════════════════════════════════════════════════════════════════
# PAGE: CONTENT COACH
# ═══════════════════════════════════════════════════════════════════════════
def page_content_coach():
    st.markdown(f'<div class="main-header">CONTENT COACH: {AMPLIFIER_IMG} <span>AMPLIFIER</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Your AI social media expert. Knows your data, the algorithm, and how to grow.</div>', unsafe_allow_html=True)
    st.markdown(
        '''<div style="display:flex;justify-content:flex-start;margin:0 0 16px 0;">
            <span class="cs-bot" data-bot="coach_help_video" style="height:52px;padding:0 18px;border-radius:14px;font-size:12px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;border:1px solid rgba(196,158,60,0.45);background:rgba(45,212,191,0.1);color:#C49E3C;cursor:pointer;display:inline-flex;align-items:center;gap:6px;">See How It Works</span>
        </div>''',
        unsafe_allow_html=True,
    )
    if st.button("bot_coach_help_video", key="coach_help_video"):
        _coach_help_dialog()
    st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

    # --- Initialize session state ---
    if "coach_conversations" not in st.session_state:
        st.session_state.coach_conversations = load_json("coach_conversations.json", [])
    if "coach_current" not in st.session_state:
        st.session_state.coach_current = {"id": None, "messages": [], "title": "New Chat"}

    _coach_sports = ""
    _coach_skip_sports = is_guest() and "sport" not in load_json("topics.json", {}).get("niche", "").lower()
    if not _coach_skip_sports:
        try: _coach_sports = f"\n\nLIVE SPORTS CONTEXT (reference when relevant):\n{get_sports_context()}"
        except Exception: pass
    _coach_handle = get_current_handle()
    _coach_niche = load_json("topics.json", {}).get("niche", "content") if is_guest() else "sports content"
    COACH_SYSTEM = get_voice_context() + f"""

You are Amplifier, @{_coach_handle}'s personal social media coach. You are an EXPERT on:
- X (Twitter) algorithm: engagement weights (replies=27x, bookmarks=20x, retweets=20x, dwell time=20x, likes=1x), penalties (links=-50%, 3+ hashtags=-40%, negative sentiment reduces reach)
- Content strategy: hook formulas, thread structures, engagement tactics, audience growth
- @{_coach_handle}'s specific data: their top performing tweets, patterns, optimal character length, usage rates, what topics work for them
- All social media platforms (YouTube, Instagram, TikTok, LinkedIn) for future expansion
- {_coach_niche} specifically: what makes {_coach_niche} content go viral, audience psychology, timing

Your coaching style:
- Direct and practical — no fluff, no "great question!" filler
- Always reference @{_coach_handle}'s actual data when giving advice
- Give specific, actionable recommendations with examples
- Challenge them when their ideas won't perform well — don't just agree
- Think in terms of SYSTEMS not individual posts — build repeatable frameworks
- Always explain WHY something works in terms of the algorithm
{_coach_sports}"""

    DEMO_QUESTIONS = [
        "What topics work best for me?", "What topics should I avoid?",
        "What hooks get me the most engagement?", "What's my best posting time based on my data?",
        "Give me 5 tweet templates based on what works for me", "What should I write about today?",
        "Analyze my worst performing tweets — what went wrong?",
        "What content types should I try that I haven't been doing?",
        "How do I grow from 42K to 100K followers?", "What's my engagement rate and how do I improve it?",
        "Compare my style to [competitor] — what can I learn?",
        "What's the X algorithm prioritizing right now?",
    ]

    def _save_current():
        conv = st.session_state.coach_current
        if not conv["messages"]:
            return
        if conv["id"] is None:
            conv["id"] = str(uuid.uuid4())
            conv["created_at"] = datetime.now().isoformat()
        # Auto-title from first user message
        first_user = next((m["content"] for m in conv["messages"] if m["role"] == "user"), "Untitled")
        conv["title"] = first_user[:40].strip()
        # Upsert into saved list
        convs = st.session_state.coach_conversations
        existing = next((i for i, c in enumerate(convs) if c["id"] == conv["id"]), None)
        if existing is not None:
            convs[existing] = conv
        else:
            convs.append(conv)
        save_json("coach_conversations.json", convs)

    def _send_message(user_text, include_history, coach_fmt):
        msgs = st.session_state.coach_current["messages"]
        msgs.append({"role": "user", "content": user_text})
        # Build system prompt
        sys_prompt = COACH_SYSTEM
        if include_history:
            patterns = analyze_personal_patterns()
            if patterns:
                sys_prompt += build_patterns_context(patterns)
        if coach_fmt != "General Advice":
            sys_prompt += f"\n\nFormat your actionable suggestions as: {coach_fmt}"
        _hist_name = get_current_handle()
        history_str = "\n".join([f"{_hist_name if m['role']=='user' else 'Amplifier'}: {m['content']}" for m in msgs])
        reply = call_claude(f"Conversation so far:\n{history_str}\n\nRespond as Amplifier.", system=sys_prompt, max_tokens=1200)
        msgs.append({"role": "assistant", "content": reply})
        _save_current()

    # --- Conversations as HTML pills ---
    _convs = st.session_state.coach_conversations[-6:]
    _cur_id = st.session_state.coach_current.get("id")
    _pill_on = "height:44px;padding:0 16px;border-radius:14px;font-size:12px;font-weight:600;background:rgba(45,212,191,0.1);border:1px solid rgba(45,212,191,0.4);color:#2DD4BF;cursor:pointer;display:inline-flex;align-items:center;white-space:nowrap;"
    _pill_off = "height:44px;padding:0 16px;border-radius:14px;font-size:12px;font-weight:600;background:#0e1a2e;border:1px solid #1a2a45;color:#5a7090;cursor:pointer;display:inline-flex;align-items:center;white-space:nowrap;"
    _conv_html = '<div style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px;">'
    _conv_html += f'<span class="cs-bot" data-bot="cc_new" style="{_pill_off}">+ New</span>'
    for _ci, conv in enumerate(reversed(_convs)):
        _label = conv.get("title", "Untitled")[:18]
        _is_active = conv.get("id") == _cur_id
        _conv_html += f'<span class="cs-bot" data-bot="cc_conv_{_ci}" style="{_pill_on if _is_active else _pill_off}">{_label}</span>'
    if st.session_state.coach_conversations:
        _conv_html += f'<span class="cs-bot" data-bot="cc_clear" style="{_pill_off}">Clear</span>'
    _conv_html += '</div>'
    st.markdown(_conv_html, unsafe_allow_html=True)

    # Hidden buttons for conversations
    if st.button("cc_new", key="coach_new"):
        st.session_state.coach_current = {"id": None, "messages": [], "title": "New Chat"}
        st.rerun()
    for _ci, conv in enumerate(reversed(_convs)):
        if st.button(f"cc_conv_{_ci}", key=f"cv_{conv['id']}"):
            st.session_state.coach_current = json.loads(json.dumps(conv))
            st.rerun()
    if st.button("cc_clear", key="coach_clear_all"):
        st.session_state.coach_conversations = []
        st.session_state.coach_current = {"id": None, "messages": [], "title": "New Chat"}
        save_json("coach_conversations.json", [])
        st.rerun()

    # --- Output Format as HTML pills ---
    _fmt_opts = ["General Advice", "Normal Tweet", "Long Tweet", "Thread", "Article"]
    if "coach_fmt_sel" not in st.session_state:
        st.session_state.coach_fmt_sel = "General Advice"
    _cur_fmt = st.session_state.coach_fmt_sel
    _fmt_html = '<div style="display:flex;gap:6px;flex-wrap:wrap;margin:8px 0 12px;">'
    _fmt_html += '<span style="font-size:9px;font-weight:700;letter-spacing:1.2px;color:#3a5070;text-transform:uppercase;display:flex;align-items:center;margin-right:4px;">Format</span>'
    for _fi, _fo in enumerate(_fmt_opts):
        _short = _fo.replace("General ", "").replace(" Tweet", "")
        _cls = _pill_on if _fo == _cur_fmt else _pill_off
        _fmt_html += f'<span class="cs-bot" data-bot="cc_fmt_{_fi}" style="{_cls}">{_short}</span>'
    _fmt_html += '</div>'
    st.markdown(_fmt_html, unsafe_allow_html=True)

    # Hidden buttons for format
    for _fi, _fo in enumerate(_fmt_opts):
        if st.button(f"cc_fmt_{_fi}", key=f"cc_fmt_{_fi}"):
            st.session_state.coach_fmt_sel = _fo
            st.rerun()
    coach_fmt = st.session_state.coach_fmt_sel

    include_history = st.toggle("Include Post History", value=not bool(st.session_state.coach_current["messages"]), key="coach_hist_toggle", help="Feed recent tweet history to the advisor for personalized advice")

    # Demo questions dropdown
    if not st.session_state.coach_current["messages"]:
        demo_pick = st.selectbox("Demo questions:", ["-- Pick a question --"] + DEMO_QUESTIONS, key="coach_demo", label_visibility="collapsed")
        if demo_pick != "-- Pick a question --":
            with st.spinner("Post Ascend AI is working..."):
                _send_message(demo_pick, include_history, coach_fmt)
            st.rerun()

    # Chat display
    for msg in st.session_state.coach_current.get("messages", []):
        if msg["role"] == "user":
            role_label = st.session_state.get("user_display_name") or (f"@{get_current_handle()}" if get_current_handle() else "You")
            cls = "chat-user"
        else:
            role_label = f'{AMPLIFIER_IMG} <span style="color:#2DD4BF;">Amplifier</span>'
            cls = "chat-ai"
        st.markdown(f'<div class="chat-msg {cls}"><div class="chat-role">{role_label}</div><div style="color:#d8d8e8;font-size:16px;line-height:1.8;white-space:pre-wrap;">{msg["content"]}</div></div>', unsafe_allow_html=True)

    # Input
    user_input = st.text_area("Ask Amplifier:", height=80, key="coach_input", placeholder="What should I write about today?", label_visibility="collapsed")

    # --- Bottom bar ---
    st.markdown('''<div style="height:1px;background:#1a2a45;margin:24px 0 14px;"></div>
    <div class="cs-bottom-bar cs-cc-bottom" style="display:flex;gap:8px;justify-content:center;">
      <span class="cs-bot cs-idock-primary" data-bot="cc_send" style="height:52px;padding:0 24px;border-radius:14px;font-size:11px;font-weight:600;background:linear-gradient(135deg,#1fb8a8,#2DD4BF);color:#060A12;cursor:pointer;display:inline-flex;align-items:center;gap:6px;">Send</span>
      <span class="cs-bot" data-bot="cc_save" style="height:52px;padding:0 18px;border-radius:14px;font-size:10px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;border:1px solid #1a2a45;background:#0a1220;color:#5a7090;cursor:pointer;display:inline-flex;align-items:center;gap:6px;">Save Post</span>
      <span class="cs-bot" data-bot="cc_remix" style="height:52px;padding:0 18px;border-radius:14px;font-size:10px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;border:1px solid #1a2a45;background:#0a1220;color:#5a7090;cursor:pointer;display:inline-flex;align-items:center;gap:6px;">Remix</span>
    </div>''', unsafe_allow_html=True)

    # Hidden buttons for bottom bar
    if st.button("cc_send", key="coach_send"):
        if user_input.strip():
            with st.spinner("Amplifier is thinking..."):
                _send_message(user_input.strip(), include_history, coach_fmt)
            st.rerun()
    if st.button("cc_save", key="coach_save_idea"):
        # Save last assistant message to ideas
        _last_ai = next((m["content"] for m in reversed(st.session_state.coach_current.get("messages", [])) if m["role"] == "assistant"), "")
        if _last_ai.strip():
            ideas = load_json("saved_ideas.json", [])
            ideas.append({"id": str(uuid.uuid4()), "text": _last_ai.strip(), "category": "From Amplifier", "created_at": datetime.now().isoformat()})
            save_json("saved_ideas.json", ideas)
            st.success("Saved!")
    if st.button("cc_remix", key="coach_repurpose"):
        _last_ai = next((m["content"] for m in reversed(st.session_state.coach_current.get("messages", [])) if m["role"] == "assistant"), "")
        if _last_ai.strip():
            with st.spinner("Repurposing..."):
                repurposed = call_claude(f"Rewrite this into a compelling tweet:\n\n{_last_ai.strip()}", system=build_user_context(), max_tokens=600)
                st.session_state.coach_save_text_result = repurposed

    if "coach_save_text_result" in st.session_state:
        st.markdown(f'<div class="output-box">{st.session_state.coach_save_text_result}</div>', unsafe_allow_html=True)

    # ── Hidden buttons are CSS-hidden; bottom bar clicks wired by global MutationObserver ──


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: ARTICLE WRITER
# ═══════════════════════════════════════════════════════════════════════════
@st.dialog("New Article", width="large")
def _aw_create_new_dialog():
    """Popup for writing a new article from scratch."""
    _custom_voices = load_json("voice_styles.json", [])
    _voice_opts = ["Default", "Critical", "Hype", "Sarcastic"] + [s["name"] for s in _custom_voices]
    voice_pick = st.selectbox("Voice", _voice_opts, key="aw_dialog_voice",
        help="Default = natural | Critical = tough love | Hype = ultra positive | Sarcastic = short column, implied story")
    freeform = st.text_area("Write or paste your seed / article here:", height=300, key="aw_dialog_freeform",
        placeholder="Paste a topic, tweet, or start writing your article...")
    fc1, fc2, fc3 = st.columns(3)
    with fc1:
        if st.button("↓ Save Article", use_container_width=True, key="aw_dialog_save"):
            if freeform.strip():
                articles = load_json("saved_articles.json", [])
                articles.append({"content": freeform.strip(), "seed": "", "saved_at": datetime.now().isoformat()})
                save_json("saved_articles.json", articles)
                st.session_state["aw_result"] = freeform.strip()
                st.rerun()
            else:
                st.warning("Write something first.")
    with fc2:
        if st.button("Generate with AI", use_container_width=True, key="aw_dialog_gen", type="primary"):
            if freeform.strip():
                with st.spinner("Writing article..."):
                    voice_mod = _build_article_voice_mod(voice_pick)
                    voice_system = get_system_for_voice(voice_pick, voice_mod)
                    _is_sarcastic = voice_pick == "Sarcastic"
                    _article_length = "400-600 words. Short column. Hard stop at 600." if _is_sarcastic else "1,500-2,000 words / 6-8 minute read"
                    _aw_voice_rules = f"RULES: @{get_current_handle()}'s voice — direct, no hedging, authoritative. Specific players/schemes/numbers only."
                    _structure = "" if _is_sarcastic else f"\nSTRUCTURE:\n- HEADLINE: 50-75 chars, include a number or specific claim\n- INTRO (2-3 paragraphs): Provocative claim, why it matters now.\n- 4 SECTIONS with subheadings: 2-3 short paragraphs, **bold key stats**\n- WHAT COMES NEXT: Bold prediction\n- CONCLUSION: 1-sentence hot take + debate question\n- PROMOTION: companion tweet idea\n\n{_aw_voice_rules}"
                    prompt = f"""Write {'a short sarcastic column' if _is_sarcastic else 'a complete X Article'} based on this seed:\n\n\"{freeform.strip()}\"\n\nFORMAT: {'SARCASTIC COLUMN' if _is_sarcastic else 'X ARTICLE'} ({_article_length}){_structure}\n\n{voice_mod}\n\nReturn the article as plain text. Do NOT wrap in JSON or code blocks."""
                    _max_tok = 1200 if _is_sarcastic else 3000
                    result = call_claude(prompt, system=voice_system, max_tokens=_max_tok)
                    st.session_state["aw_result"] = result
                    st.rerun()
            else:
                st.warning("Type something first.")
    with fc3:
        if pplx_available() and st.button("Verify", use_container_width=True, key="aw_dialog_verify"):
            if freeform.strip():
                with st.spinner("Fact-checking..."):
                    _fc = pplx_fact_check(freeform.strip())
                if _fc.get("answer"):
                    st.session_state["_aw_verify"] = _fc
                else:
                    st.warning("Couldn't verify — check API key.")
            else:
                st.warning("Write something first.")
    _vr = st.session_state.get("_aw_verify")
    if _vr:
        _va = _vr["answer"]
        _vc = _vr.get("citations", [])
        _color = "#2DD4BF" if "accurate" in _va.lower() or "correct" in _va.lower() else "#FBBF24"
        st.markdown(f'<div style="background:#0d1829;border-left:3px solid {_color};padding:10px 14px;border-radius:6px;margin:8px 0;font-size:12px;color:#b8c8d8;line-height:1.6;">{_va}</div>', unsafe_allow_html=True)
        if _vc:
            st.markdown(f'<div style="font-size:10px;color:#3a5070;margin-top:4px;">Sources: {", ".join(str(c) for c in _vc[:3])}</div>', unsafe_allow_html=True)


def page_article_writer():
    # Handle Create New — open dialog
    if st.session_state.pop("aw_create_new", False):
        for k in ["aw_result", "aw_sel_tweet", "aw_sel_dump", "aw_autogen", "aw_research_data"]:
            st.session_state.pop(k, None)
        _aw_create_new_dialog()

    st.markdown('<div class="main-header">ARTICLE <span>WRITER</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Expand a tweet or brain dump into a full X Article.</div>', unsafe_allow_html=True)
    st.markdown(
        '''<div style="display:flex;justify-content:flex-start;margin:0 0 16px 0;">
            <span class="cs-bot" data-bot="aw_help_video" style="height:52px;padding:0 18px;border-radius:14px;font-size:12px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;border:1px solid rgba(196,158,60,0.45);background:rgba(45,212,191,0.1);color:#C49E3C;cursor:pointer;display:inline-flex;align-items:center;gap:6px;">See How It Works</span>
        </div>''',
        unsafe_allow_html=True,
    )
    if st.button("bot_aw_help_video", key="aw_help_video"):
        _article_writer_help_dialog()
    st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

    # --- Source as HTML buttons ---
    if "aw_source" not in st.session_state:
        st.session_state.aw_source = "Tweets"
    _src_opts = ["Tweets", "Raw Thoughts", "Scratch"]
    _btn_on = "height:44px;padding:0 16px;border-radius:14px;font-size:12px;font-weight:600;background:rgba(45,212,191,0.1);border:1px solid rgba(45,212,191,0.4);color:#2DD4BF;cursor:pointer;display:inline-flex;align-items:center;white-space:nowrap;"
    _btn_off = "height:44px;padding:0 16px;border-radius:14px;font-size:12px;font-weight:600;background:#0e1a2e;border:1px solid #1a2a45;color:#5a7090;cursor:pointer;display:inline-flex;align-items:center;white-space:nowrap;"
    _src_html = '<div style="display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 12px;">'
    _src_html += '<span style="font-size:9px;font-weight:700;letter-spacing:1.2px;color:#3a5070;text-transform:uppercase;display:flex;align-items:center;margin-right:4px;">Source</span>'
    for _si, _so in enumerate(_src_opts):
        _cls = _btn_on if st.session_state.aw_source == _so else _btn_off
        _src_html += f'<span class="cs-bot" data-bot="aw_src_{_si}" style="{_cls}">{_so}</span>'
    _src_html += '</div>'
    st.markdown(_src_html, unsafe_allow_html=True)

    # Hidden source buttons
    for _si, _so in enumerate(_src_opts):
        if st.button(f"aw_src_{_si}", key=f"aw_src_{_si}"):
            st.session_state.aw_source = _so
            st.rerun()

    tweets = load_json("tweet_history.json", [])
    top_tweets = sorted(tweets, key=lambda t: t.get("likeCount", 0) + t.get("retweetCount", 0) * 3, reverse=True)[:8] if tweets else []
    dumps = load_json("brain_dumps.json", [])

    if "aw_sel_tweet" not in st.session_state:
        st.session_state.aw_sel_tweet = None
    if "aw_sel_dump" not in st.session_state:
        st.session_state.aw_sel_dump = None

    # ── Action dock: horizontal, between source pills and cards ──
    st.markdown('''<div class="cs-icon-dock cs-aw-dock" style="display:flex;gap:8px;justify-content:center;margin:8px 0 16px;">
      <div class="cs-idock-btn cs-idock-primary" data-dock="aw_write" style="width:52px;height:52px;border-radius:14px;background:linear-gradient(135deg,#1fb8a8,#2DD4BF);display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" stroke="#060A12" stroke-width="2"/><polyline points="14 2 14 8 20 8" stroke="#060A12" stroke-width="2"/></svg>
        <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">WRITE</span>
      </div>
      <div class="cs-idock-btn" data-dock="aw_outline" style="width:52px;height:52px;border-radius:14px;border:1px solid #1a2a45;background:#0a1220;display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><line x1="8" y1="6" x2="21" y2="6" stroke="#5a7090" stroke-width="2"/><line x1="8" y1="12" x2="21" y2="12" stroke="#5a7090" stroke-width="2"/><line x1="8" y1="18" x2="21" y2="18" stroke="#5a7090" stroke-width="2"/><line x1="3" y1="6" x2="3.01" y2="6" stroke="#5a7090" stroke-width="2" stroke-linecap="round"/><line x1="3" y1="12" x2="3.01" y2="12" stroke="#5a7090" stroke-width="2" stroke-linecap="round"/><line x1="3" y1="18" x2="3.01" y2="18" stroke="#5a7090" stroke-width="2" stroke-linecap="round"/></svg>
        <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">OUTLINE</span>
      </div>
      <div class="cs-idock-btn" data-dock="aw_research" style="width:52px;height:52px;border-radius:14px;border:1px solid #1a2a45;background:#0a1220;display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><circle cx="11" cy="11" r="8" stroke="#5a7090" stroke-width="2"/><line x1="21" y1="21" x2="16.65" y2="16.65" stroke="#5a7090" stroke-width="2"/></svg>
        <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">RESEARCH</span>
      </div>
    </div>''', unsafe_allow_html=True)

    st.markdown('<div style="height:1px;background:#1a2a45;margin:8px 0 14px;"></div>', unsafe_allow_html=True)

    # ── Source cards ──
    if True:
        if st.session_state.aw_source == "Tweets":
            for i, tw in enumerate(top_tweets):
                txt = tw.get("text", "")
                dt = tw.get("createdAt", "")[:10]
                likes = tw.get("likeCount", 0)
                rts = tw.get("retweetCount", 0)
                reps = tw.get("replyCount", 0)
                views = tw.get("viewCount", 0)
                selected = st.session_state.aw_sel_tweet == i
                border = "border-left:3px solid #2DD4BF;" if selected else ""
                _sel_style = "margin-top:8px;height:32px;padding:0 14px;border-radius:10px;font-size:10px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;cursor:pointer;display:inline-flex;align-items:center;"
                _sel_cls = _sel_style + ("background:rgba(45,212,191,0.1);border:1px solid rgba(45,212,191,0.4);color:#2DD4BF;" if selected else "background:#0a1220;border:1px solid #1a2a45;color:#5a7090;")
                st.markdown(f"""<div class="tweet-card" style="{border}">
                    <div class="tweet-num">{dt}</div>
                    <div style="color:#d8d8e8;font-size:13px;">{txt[:220]}{'...' if len(txt)>220 else ''}</div>
                    <div style="margin-top:6px;font-size:11px;color:#8888aa;">{likes} likes &middot; {rts} RTs &middot; {reps} replies &middot; {views:,} views</div>
                    <span class="cs-bot" data-bot="aw_tw_{i}" style="{_sel_cls}">{'Selected' if selected else 'Select'}</span>
                </div>""", unsafe_allow_html=True)
                if st.button(f"aw_tw_{i}", key=f"aw_tw_{i}"):
                    st.session_state.aw_sel_tweet = i
                    st.session_state.aw_sel_dump = None
                    st.session_state["aw_autogen"] = tw.get("text", "")
                    st.rerun()
            if not top_tweets:
                st.info("No tweet history yet. Sync tweets in Post History first.")

        elif st.session_state.aw_source == "Raw Thoughts":
            if not dumps:
                st.markdown('<div class="output-box">No brain dumps yet. Create one in Raw Thoughts tool first.</div>', unsafe_allow_html=True)
            else:
                for j, d in enumerate(reversed(dumps[-6:])):
                    ts = d.get("saved_at", "")[:16].replace("T", " ")
                    preview = d.get("text", "")[:160]
                    selected = st.session_state.aw_sel_dump == j
                    border = "border-left:3px solid #2DD4BF;" if selected else ""
                    _sel_style = "margin-top:8px;height:32px;padding:0 14px;border-radius:10px;font-size:10px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;cursor:pointer;display:inline-flex;align-items:center;"
                    _sel_cls = _sel_style + ("background:rgba(45,212,191,0.1);border:1px solid rgba(45,212,191,0.4);color:#2DD4BF;" if selected else "background:#0a1220;border:1px solid #1a2a45;color:#5a7090;")
                    st.markdown(f"""<div class="tweet-card" style="{border}">
                        <div class="tweet-num">{ts}</div>
                        <div style="color:#d8d8e8;font-size:13px;">{preview}{'...' if len(d.get('text',''))>160 else ''}</div>
                        <span class="cs-bot" data-bot="aw_bd_{j}" style="{_sel_cls}">{'Selected' if selected else 'Select'}</span>
                    </div>""", unsafe_allow_html=True)
                    if st.button(f"aw_bd_{j}", key=f"aw_bd_{j}"):
                        st.session_state.aw_sel_dump = j
                        st.session_state.aw_sel_tweet = None
                        st.session_state["aw_autogen"] = d.get("text", "")
                        st.rerun()

        if st.session_state.aw_source == "Scratch":
            manual = st.text_area("Type / paste your own seed:", height=80, key="aw_manual",
                placeholder="Paste a tweet, idea, or topic to expand...", label_visibility="collapsed")

        # Research data display
        if st.session_state.get("aw_research_data"):
            _rr = st.session_state["aw_research_data"]
            st.markdown(f'<div style="background:#0d1829;border:1px solid #1e3a5f;border-left:3px solid #00E5CC;border-radius:8px;padding:14px;margin:8px 0;font-size:12px;color:#b8c8d8;line-height:1.7;"><div style="font-size:10px;color:#00E5CC;font-weight:700;letter-spacing:1px;margin-bottom:6px;">PERPLEXITY RESEARCH</div>{_rr["answer"]}</div>', unsafe_allow_html=True)
            if _rr.get("citations"):
                st.markdown(f'<div style="font-size:10px;color:#3a5070;margin-bottom:8px;">Sources: {", ".join(str(c) for c in _rr["citations"][:5])}</div>', unsafe_allow_html=True)

    # (action dock rendered above the cards)

    # Auto-generate when tweet/dump is selected
    if st.session_state.get("aw_autogen"):
        _auto_seed = st.session_state.pop("aw_autogen")
        with st.spinner("Writing article..."):
            voice = get_voice_context()
            pp = analyze_personal_patterns()
            pp_note = f"\nData: optimal char range {pp.get('optimal_char_range','N/A')}, {pp.get('top_question_pct',0)}% top tweets use questions, {pp.get('top_ellipsis_pct',0)}% use ellipsis." if pp else ""
            prompt = f"""Write a complete X Article based on this seed:\n\n\"{_auto_seed}\"\n\nFORMAT: X ARTICLE (1,500-2,000 words / 6-8 minute read)\n\nSTRUCTURE:\n- HEADLINE: 50-75 chars, include a number or specific claim\n- INTRO (2-3 paragraphs): Provocative claim, why it matters now.\n- 4 SECTIONS with subheadings: 2-3 short paragraphs, **bold key stats**\n- WHAT COMES NEXT: Bold prediction\n- CONCLUSION: 1-sentence hot take + debate question\n- PROMOTION: companion tweet idea\n\nRULES: @{get_current_handle()}'s voice — direct, no hedging, authoritative. Specific players/schemes/numbers only.{pp_note}"""
            st.session_state["aw_result"] = call_claude(prompt, system=voice, max_tokens=3000)

    # Resolve seed text for manual actions
    seed_text = ""
    if st.session_state.get("aw_sel_tweet") is not None and top_tweets:
        seed_text = top_tweets[st.session_state.aw_sel_tweet].get("text", "")
    elif st.session_state.get("aw_sel_dump") is not None and dumps:
        idx = st.session_state.aw_sel_dump
        rev = list(reversed(dumps[-6:]))
        if idx < len(rev):
            seed_text = rev[idx].get("text", "")
    if st.session_state.aw_source == "Scratch":
        seed_text = st.session_state.get("aw_manual", "").strip() or seed_text

    # Hidden buttons for dock
    if st.button("aw_write", key="aw_scratch"):
        if seed_text:
            with st.spinner("Writing full article..."):
                voice = get_voice_context()
                pp = analyze_personal_patterns()
                pp_note = ""
                if pp:
                    pp_note = f"\nData: optimal char range {pp.get('optimal_char_range','N/A')}, {pp.get('top_question_pct',0)}% top tweets use questions, {pp.get('top_ellipsis_pct',0)}% use ellipsis."
                _aw_sports = ""
                _aw_skip_sports = is_guest() and "sport" not in load_json("topics.json", {}).get("niche", "").lower()
                if not _aw_skip_sports:
                    try:
                        _aw_sports = f"\n\nLIVE SPORTS CONTEXT:\n{get_sports_context()}"
                    except Exception:
                        pass
                _aw_research = ""
                if st.session_state.get("aw_research_data", {}).get("answer"):
                    _aw_research = f"\n\nRESEARCH (use these verified facts):\n{st.session_state['aw_research_data']['answer'][:1500]}"
                prompt = f"""Write a complete X Article based on this seed:\n\n\"{seed_text}\"\n\nFORMAT: X ARTICLE (1,500-2,000 words / 6-8 minute read){_aw_sports}{_aw_research}\n\nCONTEXT: X Articles grew 20x since Dec 2025 ($2.15M contest prizes). They keep users on-platform (no link penalty), generate 2+ min dwell time (+10 algorithm weight), and Premium subscribers get 2-4x reach boost. This is the highest priority content format.\n\nSTRUCTURE:\n- HEADLINE: 50-75 chars, include a number or specific claim, take a position. Numbers perform 2x better.\n- [IMAGE: Hero image placeholder — game photo, player photo, or custom graphic]\n- INTRO (2-3 paragraphs): Provocative claim or surprising stat, then why it matters right now.\n- SECTION 1 with subheading: 2-3 short paragraphs with **bold key stats** (2-3 per section). [IMAGE placeholder]\n- SECTION 2 with subheading: 2-3 short paragraphs, comparison list format if relevant.\n- SECTION 3 with subheading: Contrarian angle or insider perspective. [IMAGE placeholder]\n- SECTION 4 WHAT COMES NEXT: Bold prediction with reasoning.\n- CONCLUSION: **1-sentence bold hot take summary**, then discussion question to drive comments.\n- PROMOTION: Suggest a companion tweet pulling the most provocative stat from the article.\n\nRULES:\n- 1,500-2,000 words target (6-8 min read for optimal dwell time bonus)\n- Paragraphs: 2-4 sentences max\n- Subheadings every ~300 words\n- Bold key stats and claims (2-3 per section)\n- Voice: direct, no hedging, authoritative\n- Every point must reference specific players/schemes/numbers\n- Include [IMAGE] markers where supporting visuals should go\n- End with debate invitation to drive replies{pp_note}"""
                st.session_state["aw_result"] = call_claude(prompt, system=voice, max_tokens=3000)
    if st.button("aw_outline", key="aw_outline"):
        if seed_text:
            with st.spinner("Generating outline..."):
                voice = get_voice_context()
                prompt = f"""Generate a detailed X Article outline based on:\n\n\"{seed_text}\"\n\nX Articles are the #1 priority format (20x growth since Dec 2025, 2+ min dwell time = +10 algorithm weight, Premium gets 2-4x reach).\n\nOutline format:\n- HEADLINE: 50-75 chars, include a number or specific claim (numbers perform 2x better)\n- [HERO IMAGE suggestion]\n- INTRO hook paragraph (provocative claim + why it matters now)\n- 4-6 section headers with subheadings every ~300 words, 2-3 bullet points each\n- Note where [IMAGE] placements go (2-3 supporting images)\n- WHAT COMES NEXT section with bold prediction\n- CONCLUSION: hot take + debate question\n- PROMOTION: companion tweet idea pulling most provocative stat\n\nTarget: 1,500-2,000 words (6-8 min read). Keep @{get_current_handle()}'s voice: direct, opinionated, authoritative."""
                st.session_state["aw_result"] = call_claude(prompt, system=voice, max_tokens=1000)
    if st.button("aw_research", key="aw_research_btn"):
        if seed_text and pplx_available():
            with st.spinner("Researching with Perplexity..."):
                _research = pplx_research(seed_text)
                if _research.get("answer"):
                    st.session_state["aw_research_data"] = _research
                else:
                    st.warning("Research failed — check API key.")

    # Output + editor
    if st.session_state.get("aw_result"):
        st.markdown(f'<div class="output-box">{st.session_state["aw_result"]}</div>', unsafe_allow_html=True)
        edited = st.text_area("Edit article:", value=st.session_state["aw_result"], height=300, key="aw_editor", label_visibility="collapsed")

        # --- Bottom bar ---
        st.markdown('''<div style="height:1px;background:#1a2a45;margin:24px 0 14px;"></div>
        <div class="cs-bottom-bar cs-aw-bottom" style="display:flex;gap:8px;justify-content:center;">
          <span class="cs-bot" data-bot="aw_save" style="height:52px;padding:0 18px;border-radius:14px;font-size:10px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;border:1px solid #1a2a45;background:#0a1220;color:#5a7090;cursor:pointer;display:inline-flex;align-items:center;gap:6px;">Save</span>
          <span class="cs-bot" data-bot="aw_articles" style="height:52px;padding:0 18px;border-radius:14px;font-size:10px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;border:1px solid rgba(196,158,60,0.25);background:#0a1220;color:rgba(196,158,60,0.6);cursor:pointer;display:inline-flex;align-items:center;gap:6px;">My Articles</span>
          <span class="cs-bot" data-bot="aw_copy" style="height:52px;padding:0 18px;border-radius:14px;font-size:10px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;border:1px solid #1a2a45;background:#0a1220;color:#5a7090;cursor:pointer;display:inline-flex;align-items:center;gap:6px;">Copy</span>
          <span class="cs-bot" data-bot="aw_verify" style="height:52px;padding:0 18px;border-radius:14px;font-size:10px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;border:1px solid #1a2a45;background:#0a1220;color:#5a7090;cursor:pointer;display:inline-flex;align-items:center;gap:6px;">Verify</span>
        </div>''', unsafe_allow_html=True)

        # Hidden buttons for bottom bar
        if st.button("aw_save", key="aw_save"):
            articles = load_json("saved_articles.json", [])
            articles.append({"content": edited, "seed": seed_text[:200], "saved_at": datetime.now().isoformat()})
            save_json("saved_articles.json", articles)
            st.success("Article saved.")
        if st.button("aw_articles", key="aw_show_articles"):
            st.session_state["_aw_show_articles"] = True
        if st.button("aw_copy", key="aw_copy"):
            st.code(edited, language=None)
            st.info("Text displayed above -- copy from there.")
        if st.button("aw_verify", key="aw_verify"):
            if pplx_available():
                with st.spinner("Fact-checking..."):
                    _fc = pplx_fact_check(edited)
                if _fc.get("answer"):
                    st.session_state["_aw_page_verify"] = _fc
                else:
                    st.warning("Couldn't verify — check API key.")

        _vr = st.session_state.get("_aw_page_verify")
        if _vr:
            _va = _vr["answer"]
            _vc = _vr.get("citations", [])
            _color = "#2DD4BF" if "accurate" in _va.lower() or "correct" in _va.lower() else "#FBBF24"
            st.markdown(f'<div style="background:#0d1829;border-left:3px solid {_color};padding:10px 14px;border-radius:6px;margin:8px 0;font-size:12px;color:#b8c8d8;line-height:1.6;">{_va}</div>', unsafe_allow_html=True)
            if _vc:
                st.markdown(f'<div style="font-size:10px;color:#3a5070;margin-top:4px;">Sources: {", ".join(str(c) for c in _vc[:3])}</div>', unsafe_allow_html=True)

    # ── My Articles modal ──
    if st.session_state.pop("_aw_show_articles", False):
        @st.dialog("My Articles", width="large")
        def _aw_articles_dialog():
            if st.button("Create New", key="aw_dlg_new", use_container_width=True, type="primary"):
                st.session_state["aw_create_new"] = True
                st.rerun()
            articles = load_json("saved_articles.json", [])
            if not articles:
                st.markdown('<div class="output-box">No saved articles yet.</div>', unsafe_allow_html=True)
            else:
                for idx, a in enumerate(reversed(articles[-10:])):
                    ts = a.get("saved_at", "")[:10]
                    preview = a.get("content", "")[:100]
                    st.markdown(f"""<div class="tweet-card">
                        <div class="tweet-num">{ts}</div>
                        <div style="color:#d8d8e8; font-size:13px;">{preview}...</div>
                    </div>""", unsafe_allow_html=True)
                    if st.button("Load", key=f"aw_load_{idx}", use_container_width=True):
                        st.session_state["aw_result"] = a.get("content", "")
                        st.rerun(scope="app")
        _aw_articles_dialog()

    # ── Hidden buttons are CSS-hidden; dock/bottom clicks wired by global MutationObserver ──


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: TWEET HISTORY
# ═══════════════════════════════════════════════════════════════════════════
def sync_tweet_history(quick=False):
    """Fetch tweets and merge into local knowledge base.
    quick=True: fetch latest ~10 tweets (fast, every page load).
    quick=False: sliding 2-week windows going back 6 months to collect up to 500 tweets.
                 Bypasses cursor pagination depth limits.
    """
    import time as _time

    def _fetch_window(query):
        """Fetch all pages for a single query window using cursor pagination."""
        window_tweets = []
        cursor = ""
        for _ in range(4):  # up to 4 pages per window (200 tweets max per window)
            try:
                params = {"query": query, "queryType": "Latest", "count": "50"}
                if cursor:
                    params["cursor"] = cursor
                resp = requests.get(
                    "https://api.twitterapi.io/twitter/tweet/advanced_search",
                    headers={"X-API-Key": TWITTER_API_IO_KEY},
                    params=params, timeout=8,
                )
                if resp.status_code != 200:
                    break
                data = resp.json()
                batch = data.get("tweets", [])
                if not batch:
                    break
                window_tweets.extend(batch)
                cursor = data.get("next_cursor", "")
                if not cursor:
                    break
                _time.sleep(0.3)
            except Exception:
                break
        return window_tweets

    handle = get_current_handle()
    if not handle:
        _save_debug_status("tweet_sync", {
            "status": "error",
            "at": datetime.now().isoformat(timespec="seconds"),
            "detail": "No handle available",
            "mode": "quick" if quick else "full",
        })
        return []

    try:
        if quick:
            all_tweets = _fetch_window(f"from:{handle}")[:10]
        else:
            # Slide backwards in 7-day windows for up to 2 years (104 windows) until 500 tweets collected
            # Smaller windows = fewer tweets per window = less pagination cutoff risk
            all_tweets = []
            seen_ids = set()
            end_dt = datetime.now()
            for _ in range(104):
                start_dt = end_dt - timedelta(days=7)
                since_str = start_dt.strftime("%Y-%m-%d")
                until_str = end_dt.strftime("%Y-%m-%d")
                query = f"from:{handle} since:{since_str} until:{until_str}"
                window = _fetch_window(query)
                for t in window:
                    tid = t.get("id", "")
                    if tid and tid not in seen_ids:
                        seen_ids.add(tid)
                        all_tweets.append(t)
                end_dt = start_dt
                _time.sleep(0.5)
                if len(all_tweets) >= 500:
                    break

        # Merge with existing history (from Gist)
        existing = _load_tweet_history_gist()
        combined = all_tweets + existing
        seen = set()
        unique = []
        for t in combined:
            tid = t.get("id", "")
            if tid and tid not in seen:
                seen.add(tid)
                unique.append(t)
        unique = unique[:500]
        _save_tweet_history_gist(unique)
        _save_debug_status("tweet_sync", {
            "status": "ok",
            "at": datetime.now().isoformat(timespec="seconds"),
            "detail": f"{len(unique)} tweets available",
            "mode": "quick" if quick else "full",
            "handle": handle,
        })
        return unique
    except Exception as e:
        _save_debug_status("tweet_sync", {
            "status": "error",
            "at": datetime.now().isoformat(timespec="seconds"),
            "detail": str(e)[:300],
            "mode": "quick" if quick else "full",
            "handle": handle,
        })
        raise


def _load_tweet_history_gist() -> list:
    """Load tweet history from Gist (persistent across Streamlit redeploys).
    Guests skip Gist — their data lives in isolated local dirs only."""
    _handle = get_current_handle()
    if st.session_state.get("_tweet_history_cache_handle") == _handle and "_tweet_history_cache" in st.session_state:
        return st.session_state["_tweet_history_cache"]
    # Guests: local file only (no gist)
    if is_guest():
        tweets = load_json("tweet_history.json", [])
        st.session_state["_tweet_history_cache"] = tweets
        st.session_state["_tweet_history_cache_handle"] = _handle
        return tweets
    try:
        gist_id = st.secrets.get("GIST_ID", "15fb167bbbfdaa79d5ce11c266c3f652")
        resp = requests.get(f"https://api.github.com/gists/{gist_id}", headers=_gist_headers(), timeout=8)
        file_meta = resp.json().get("files", {}).get("hq_tweet_history.json", {})
        if file_meta:
            # Always use raw_url — Gist API truncates files over ~1MB in content field
            raw_url = file_meta.get("raw_url", "")
            if raw_url:
                raw_resp = requests.get(raw_url, timeout=8)
                tweets = json.loads(raw_resp.text)
                st.session_state["_tweet_history_cache"] = tweets
                st.session_state["_tweet_history_cache_handle"] = _handle
                return tweets
    except Exception:
        pass
    # Fallback to local file
    return load_json("tweet_history.json", [])


def _slim_tweet(t: dict) -> dict:
    """Strip tweet to only fields the app uses — keeps Gist file small."""
    return {
        "id": t.get("id", ""),
        "text": t.get("text", ""),
        "likeCount": t.get("likeCount", t.get("like_count", 0)),
        "retweetCount": t.get("retweetCount", t.get("retweet_count", 0)),
        "replyCount": t.get("replyCount", t.get("reply_count", 0)),
        "viewCount": t.get("viewCount", t.get("view_count", 0)),
        "createdAt": t.get("createdAt", t.get("created_at", "")),
    }


def _save_tweet_history_gist(tweets: list):
    """Save tweet history to Gist and local file. Slims tweets first to avoid truncation.
    Guests save locally only — no gist write."""
    slimmed = [_slim_tweet(t) for t in tweets]
    st.session_state["_tweet_history_cache"] = slimmed
    st.session_state["_tweet_history_cache_handle"] = get_current_handle()
    save_json("tweet_history.json", slimmed)
    # Guests: local only, skip gist
    if is_guest():
        return
    try:
        gist_id = st.secrets.get("GIST_ID", "15fb167bbbfdaa79d5ce11c266c3f652")
        payload = json.dumps({"files": {"hq_tweet_history.json": {"content": json.dumps(slimmed)}}})
        requests.patch(f"https://api.github.com/gists/{gist_id}", data=payload, headers=_gist_headers(), timeout=8)
    except Exception:
        pass


def fetch_tweet_by_id(tweet_id: str) -> dict:
    """Fetch a single tweet by ID.
    twitterapi.io has no lookup endpoint — decode snowflake timestamp and
    do a targeted 1-day date-window search, then match by ID."""
    try:
        # Decode Twitter snowflake ID to posting date
        TWITTER_EPOCH = 1288834974657
        ts_ms = (int(tweet_id) >> 22) + TWITTER_EPOCH
        dt = datetime.utcfromtimestamp(ts_ms / 1000)
        since = dt.strftime("%Y-%m-%d")
        until = (dt + timedelta(days=1)).strftime("%Y-%m-%d")
        query = f"from:{get_current_handle()} since:{since} until:{until}"
        cursor = ""
        for _ in range(5):  # up to 5 pages
            params = {"query": query, "queryType": "Latest", "count": "50"}
            if cursor:
                params["cursor"] = cursor
            resp = requests.get(
                "https://api.twitterapi.io/twitter/tweet/advanced_search",
                headers={"X-API-Key": TWITTER_API_IO_KEY},
                params=params, timeout=8,
            )
            if resp.status_code != 200:
                break
            data = resp.json()
            for t in data.get("tweets", []):
                if str(t.get("id", "")) == str(tweet_id):
                    return t
            cursor = data.get("next_cursor", "")
            if not cursor:
                break
    except Exception:
        pass
    return {}


def get_tweet_knowledge_base():
    """Load tweet history — Gist-backed so it survives Streamlit redeploys."""
    return _load_tweet_history_gist()


def classify_tweet(tweet):
    """Classify a tweet — format tags map to Creator Studio formats."""
    text  = tweet.get("text", "")
    likes = tweet.get("likeCount", tweet.get("like_count", 0))
    rts   = tweet.get("retweetCount", tweet.get("retweet_count", 0))
    replies = tweet.get("replyCount", tweet.get("reply_count", 0))
    views = tweet.get("viewCount", tweet.get("view_count", 0))
    eng_rate = (likes + rts + replies) / max(views, 1) * 100
    has_url = "http" in text

    tags = []

    if text.startswith("RT "):
        tags.append("Repost")
    elif text.startswith("@"):
        tags.append("Reply")
    else:
        # Format classification — matches Creator Studio format options
        char_len = len(text)
        if char_len <= 160 and not has_url:
            tags.append("Punchy Tweet")
        elif char_len <= 260:
            tags.append("Normal Tweet")
        else:
            tags.append("Long")
        if not has_url:
            tags.append("Original")

    # Engagement tags
    if likes > 100 or rts > 20:
        tags.append("High Engagement")
    if views > 10000:
        tags.append("Viral")
    if replies > likes * 0.3 and replies > 5:
        tags.append("Conversation Starter")
    if eng_rate > 3:
        tags.append("Hot")
    time_words = ["today", "tonight", "right now", "just", "breaking", "live"]
    if not any(w in text.lower() for w in time_words) and likes > 20:
        tags.append("Evergreen")

    return tags


def page_tweet_history():
    st.markdown('<div class="main-header">YOUR POST <span>HISTORY</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Your knowledge base. Every AI feature in this app learns from these tweets.</div>', unsafe_allow_html=True)
    st.markdown(
        '''<div style="display:flex;justify-content:flex-start;margin:0 0 16px 0;">
            <span class="cs-bot" data-bot="th_help_video" style="height:52px;padding:0 18px;border-radius:14px;font-size:12px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;border:1px solid rgba(196,158,60,0.45);background:rgba(45,212,191,0.1);color:#C49E3C;cursor:pointer;display:inline-flex;align-items:center;gap:6px;">See How It Works</span>
        </div>''',
        unsafe_allow_html=True,
    )
    if st.button("bot_th_help_video", key="th_help_video"):
        _post_history_help_dialog()
    st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

    # Load stored tweets
    tweets = get_tweet_knowledge_base()

    # Header stats
    hc1, hc2, hc3, hc4 = st.columns([1, 1, 1, 2])
    with hc1:
        st.markdown(f'<div class="stat-card"><div class="stat-num">{len(tweets)}</div><div class="stat-label">Total Tweets</div></div>', unsafe_allow_html=True)
    with hc2:
        st.markdown(f'<div class="stat-card"><div style="font-size:13px;font-weight:700;color:#00E5CC;line-height:1.3;margin-bottom:4px;word-break:break-all;">@{get_current_handle()}</div><div class="stat-label">Handle</div></div>', unsafe_allow_html=True)
    with hc3:
        last_sync = ""
        if tweets:
            dates = [t.get("createdAt", "") for t in tweets if t.get("createdAt")]
            if dates:
                last_sync = sorted(dates, reverse=True)[0][:10]
        st.markdown(f'<div class="stat-card"><div style="font-size:12px;font-weight:700;color:#00E5CC;line-height:1.3;margin-bottom:4px;">{last_sync or "Never"}</div><div class="stat-label">Last Synced</div></div>', unsafe_allow_html=True)
    with hc4:
        if st.button("↻ Update Posts", use_container_width=True, key="th_sync", type="primary"):
            with st.spinner("Syncing up to 500 tweets from X... this may take a minute."):
                tweets = sync_tweet_history()
                st.success(f"Synced {len(tweets)} tweets.")
                st.rerun()

    if not tweets:
        st.warning("No tweets stored. Click 'Update Posts' to pull your history from X.")
        return

    # Search
    st.markdown('<div style="height:16px;"></div>', unsafe_allow_html=True)
    search = st.text_input("Search tweets and notes:", placeholder="Filter by keyword...", key="th_search", label_visibility="collapsed")

    # Filter pills
    st.markdown('<div style="font-size:9px;font-weight:700;letter-spacing:1.2px;color:#3a5070;text-transform:uppercase;margin:12px 0 4px;">Filter</div>', unsafe_allow_html=True)
    _th_filters = ["All", "Punchy", "Normal", "Long", "Hot"]
    _th_filter_map = {"All": "All Posts", "Punchy": "Punchy Tweet", "Normal": "Normal Posts", "Long": "Long Posts", "Hot": "High Engagement"}
    if "th_filter_sel" not in st.session_state:
        st.session_state.th_filter_sel = "All"
    _thf_cols = st.columns(len(_th_filters))
    for _tfi, _tf in enumerate(_th_filters):
        with _thf_cols[_tfi]:
            if st.button(_tf, key=f"th_filt_{_tfi}", type="primary" if st.session_state.th_filter_sel == _tf else "secondary"):
                st.session_state.th_filter_sel = _tf
                st.rerun()
    filter_type = _th_filter_map.get(st.session_state.th_filter_sel, "All Posts")

    # AI action icon dock
    st.markdown('''<div style="font-size:8px;font-weight:700;letter-spacing:1.5px;color:#2a3a55;text-transform:uppercase;margin:12px 0 8px;">AI ANALYSIS</div>
    <div class="cs-icon-dock cs-th-dock" style="display:flex;gap:8px;justify-content:center;margin-bottom:16px;">
      <div class="cs-idock-btn cs-idock-primary" data-dock="th_hooks" style="width:52px;height:52px;border-radius:14px;background:linear-gradient(135deg,#1fb8a8,#2DD4BF);display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M12 2L2 22h20L12 2z" stroke="#060A12" stroke-width="2" stroke-linejoin="round"/></svg>
        <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">HOOKS</span>
      </div>
      <div class="cs-idock-btn" data-dock="th_missed" style="width:52px;height:52px;border-radius:14px;border:1px solid #1a2a45;background:#0a1220;display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M12 2v20M2 12h20" stroke="#5a7090" stroke-width="2"/></svg>
        <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">MISSED</span>
      </div>
      <div class="cs-idock-btn" data-dock="th_style" style="width:52px;height:52px;border-radius:14px;border:1px solid #1a2a45;background:#0a1220;display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M12 20h9M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z" stroke="#5a7090" stroke-width="2"/></svg>
        <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">STYLE</span>
      </div>
      <div class="cs-idock-btn" data-dock="th_subjects" style="width:52px;height:52px;border-radius:14px;border:1px solid #1a2a45;background:#0a1220;display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><rect x="3" y="3" width="18" height="18" rx="2" stroke="#5a7090" stroke-width="2"/><line x1="3" y1="9" x2="21" y2="9" stroke="#5a7090" stroke-width="2"/><line x1="9" y1="21" x2="9" y2="9" stroke="#5a7090" stroke-width="2"/></svg>
        <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">SUBJECTS</span>
      </div>
    </div>''', unsafe_allow_html=True)

    # Hidden buttons for AI dock
    if st.button("th_hooks", key="th_ai_hooks"):
        top = sorted([t for t in tweets if not t.get("text","").startswith("@")], key=lambda t: t.get("likeCount", 0), reverse=True)[:20]
        hooks = [t.get("text", "").split(".")[0].split("...")[0].split("\n")[0][:100] for t in top]
        st.session_state["th_ai_result"] = "Your best-performing opening hooks:\n\n" + "\n".join([f"{i+1}. {h}" for i, h in enumerate(hooks)])
    if st.button("th_missed", key="th_ai_worst"):
        worst = sorted([t for t in tweets if not t.get("text","").startswith("@")], key=lambda t: t.get("viewCount", 0) if t.get("viewCount", 0) > 0 else 999999)[:10]
        st.session_state["th_ai_result"] = "Lowest performing tweets (by views):\n\n" + "\n".join([f"- {t.get('text','')[:80]}... ({t.get('viewCount',0):,} views)" for t in worst])
    if st.button("th_style", key="th_ai_voice"):
        sample = [t.get("text", "") for t in sorted([t for t in tweets if not t.get("text","").startswith("@")], key=lambda t: t.get("likeCount", 0), reverse=True)[:30]]
        with st.spinner("Analyzing your voice..."):
            _th_handle = get_current_handle() or "this creator"
            result = call_claude(f"Analyze @{_th_handle}'s writing voice based on these top-performing tweets. Identify patterns in: sentence length, punctuation style, opener types, tone, vocabulary, what makes this voice unique.\n\nTweets:\n" + "\n---\n".join(sample[:20]))
            st.session_state["th_ai_result"] = result
    if st.button("th_subjects", key="th_ai_topics"):
        sample = [f"{t.get('text','')[:100]} (likes:{t.get('likeCount',0)}, views:{t.get('viewCount',0)})" for t in sorted([t for t in tweets if not t.get("text","").startswith("@")], key=lambda t: t.get("likeCount", 0), reverse=True)[:40]]
        with st.spinner("Analyzing topics..."):
            _th_handle = get_current_handle() or "this creator"
            result = call_claude(f"Analyze which topics get @{_th_handle} the most engagement. Group these tweets by topic and show which themes consistently outperform. Be specific.\n\nTweets:\n" + "\n".join(sample))
            st.session_state["th_ai_result"] = result

    if st.session_state.get("th_ai_result"):
        st.markdown(f'<div class="output-box">{st.session_state["th_ai_result"]}</div>', unsafe_allow_html=True)

    st.markdown('<div style="height:1px;background:#1a2a45;margin:24px 0 14px;"></div>', unsafe_allow_html=True)

    # ── Hidden buttons are CSS-hidden; dock clicks wired by global MutationObserver ──

    # ── Hall of Fame ──
    def _eng_score(t):
        likes = t.get("likeCount", t.get("like_count", 0))
        rts   = t.get("retweetCount", t.get("retweet_count", 0))
        reps  = t.get("replyCount", t.get("reply_count", 0))
        views = t.get("viewCount", t.get("view_count", 0))
        # HOF = impressions first — views so dominant that engagement is just a tiebreaker
        return views * 10 + likes * 100 + rts * 300 + reps * 200

    hof_candidates = [t for t in tweets
        if not t.get("text", "").startswith("RT ")
        and not t.get("text", "").startswith("@")]
    hof_tweets = sorted(hof_candidates, key=_eng_score, reverse=True)[:20]

    with st.expander(f"★ Hall of Fame — Top {len(hof_tweets)} Tweets", expanded=False):
        # Manual import
        imp_col1, imp_col2 = st.columns([4, 1])
        with imp_col1:
            imp_url = st.text_input("Paste tweet URL to add to history:", placeholder="https://x.com/username/status/...", key="hof_import_url", label_visibility="collapsed")
        with imp_col2:
            if st.button("+ Add", key="hof_import_btn", use_container_width=True):
                if imp_url.strip():
                    # Extract tweet ID from URL
                    imp_id = imp_url.strip().rstrip("/").split("/")[-1].split("?")[0]
                    if imp_id.isdigit():
                        existing_ids = {t.get("id", "") for t in tweets}
                        if imp_id in existing_ids:
                            st.info("Already in your history.")
                        else:
                            with st.spinner("Fetching tweet..."):
                                fetched = fetch_tweet_by_id(imp_id)
                            if fetched and fetched.get("id"):
                                updated = [fetched] + tweets
                                _save_tweet_history_gist(updated[:500])
                                st.success(f"Added: {fetched.get('text','')[:80]}...")
                                st.rerun()
                            else:
                                st.error("Couldn't fetch that tweet — check the URL.")
                    else:
                        st.error("Couldn't parse tweet ID from URL.")
        st.markdown("---")
        for rank, t in enumerate(hof_tweets, 1):
            text  = t.get("text", "")
            likes = t.get("likeCount", t.get("like_count", 0))
            rts   = t.get("retweetCount", t.get("retweet_count", 0))
            reps  = t.get("replyCount", t.get("reply_count", 0))
            views = t.get("viewCount", t.get("view_count", 0))
            score = round(_eng_score(t))
            date  = t.get("createdAt", "")[:10]
            medal = "#FFD700" if rank == 1 else "#C0C0C0" if rank == 2 else "#CD7F32" if rank == 3 else "#6E7681"
            st.markdown(
                f'<div style="background:#0d0d1a;border-left:3px solid {medal};border-radius:10px;padding:14px 16px;margin-bottom:10px;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
                f'<span style="color:{medal};font-family:\'Bebas Neue\',sans-serif;font-size:18px;letter-spacing:1px;">#{rank}</span>'
                f'<div style="display:flex;gap:16px;font-size:11px;color:#666688;">'
                f'<span>⚡ {score}</span><span>♡ {likes:,}</span><span>↩ {reps:,}</span><span>↺ {rts:,}</span><span>👁 {views:,}</span><span>{date}</span>'
                f'</div></div>'
                f'<div style="color:#e8e8f0;font-size:14px;line-height:1.6;">{text}</div>'
                f'</div>',
                unsafe_allow_html=True)

    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

    # Apply filters — replies excluded by default
    filtered = [t for t in tweets if not t.get("text", "").startswith("@")]
    if search:
        filtered = [t for t in filtered if search.lower() in t.get("text", "").lower()]

    if filter_type != "All Posts":
        tag_map = {
            "Punchy Tweet": "Punchy Tweet", "Normal Posts": "Normal Tweet", "Long Posts": "Long",
            "High Engagement": "High Engagement", "Viral Posts": "Viral",
            "Conversation Starters": "Conversation Starter",
            "Evergreen": "Evergreen", "Hot": "Hot", "Original": "Original",
        }
        target_tag = tag_map.get(filter_type, "")
        filtered = [t for t in filtered if target_tag in classify_tweet(t)]

    st.markdown(f"**Showing {len(filtered)} of {len(tweets)} tweets**")

    # Debug panel — only shown when debug_mode is active
    if st.session_state.get("debug_mode", False):
        with st.expander("Debug: Pattern Analysis", expanded=False):
            _pp = analyze_personal_patterns()
            if not _pp:
                st.warning("Not enough data to compute patterns (need 20+ tweets with no URLs).")
            else:
                _diag_tweets = _load_tweet_history_gist()
                _has_likeCount = sum(1 for t in _diag_tweets if "likeCount" in t)
                _has_like_count = sum(1 for t in _diag_tweets if "like_count" in t)
                st.markdown(f"**Field name check:** `likeCount` present in {_has_likeCount} tweets | `like_count` present in {_has_like_count} tweets")
                st.markdown(f"**Optimal char range (25th–75th pct):** {_pp.get('optimal_char_range')}")
                st.markdown(f"**Top avg chars:** {_pp.get('top_avg_chars')} | **Punchy examples:** {len(_pp.get('top_examples_punchy',[]))} | **Normal examples:** {len(_pp.get('top_examples_normal',[]))} | **Long examples:** {len(_pp.get('top_examples_long',[]))}")
                st.markdown("**Top performers used for pattern analysis:**")
                for ex in _pp.get("top_examples", []):
                    sc = ex.get("score", 0)
                    sc_color = "#22c55e" if sc > 50 else "#2DD4BF"
                    st.markdown(
                        f'<div style="background:#0d0d18;border-left:3px solid {sc_color};border-radius:8px;padding:10px 14px;margin-bottom:6px;font-size:12px;">'
                        f'<span style="color:{sc_color};font-weight:700;">Score {sc}</span> · '
                        f'<span style="color:#888;">{len(ex.get("text",""))} chars · {ex.get("likes",0)} likes · {ex.get("replies",0)} replies</span><br>'
                        f'<span style="color:#d8d8e8;">{ex.get("text","")[:150]}</span></div>',
                        unsafe_allow_html=True)

    # Display tweets with classification tags and engagement scores
    for i, t in enumerate(filtered[:100]):
        text = t.get("text", "")
        likes = t.get("likeCount", 0)
        rts = t.get("retweetCount", 0)
        replies = t.get("replyCount", 0)
        views = t.get("viewCount", 0)
        created = t.get("createdAt", "")
        tags = classify_tweet(t)
        eng_rate = round((likes + rts + replies) / max(views, 1) * 100, 1)

        # Engagement score (0-100)
        score = min(100, int((likes * 2 + rts * 5 + replies * 3) / max(1, views / 1000)))

        hot_tags = {"Viral", "Hot", "High Engagement"}
        format_tags = {"Punchy Tweet", "Normal Tweet", "Long", "Thread"}
        def _tag_cls(tg):
            if tg in hot_tags: return "tag tag-hot"
            if tg in format_tags: return "tag tag-format"
            if tg == "Original": return "tag tag-original"
            if tg == "AI Generated": return "tag tag-ai"
            return "tag"
        tags_html = " ".join([f'<span class="{_tag_cls(tg)}">{tg}</span>' for tg in tags])

        score_color = "#22c55e" if score >= 60 else "#2DD4BF" if score >= 30 else "#ef4444"

        st.markdown(f"""<div class="tweet-card">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                <div>{tags_html}</div>
                <div style="display:flex; align-items:center; gap:8px;">
                    <span style="font-size:11px; color:#444466;">{created[:16] if created else ''}</span>
                    <span style="font-family:'Bebas Neue',sans-serif; font-size:20px; color:{score_color};">{score}</span>
                </div>
            </div>
            <div style="color:#d8d8e8; font-size:14px; margin-bottom:10px; line-height:1.6;">{text}</div>
            <div style="display:flex; gap:24px; font-size:12px; color:#666688;">
                <span>Likes: {likes:,}</span>
                <span>RTs: {rts:,}</span>
                <span>Replies: {replies:,}</span>
                <span>Views: {views:,}</span>
                <span>Eng: {eng_rate}%</span>
            </div>
        </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: ALGORITHM SCORE
# ═══════════════════════════════════════════════════════════════════════════
def page_algo_analyzer():
    st.markdown('<div class="main-header">ALGORITHM <span>SCORE</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Run your content through the algorithm lens before you post.</div>', unsafe_allow_html=True)
    st.markdown(
        '''<div style="display:flex;justify-content:flex-start;margin:0 0 16px 0;">
            <span class="cs-bot" data-bot="aa_help_video" style="height:52px;padding:0 18px;border-radius:14px;font-size:12px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;border:1px solid rgba(196,158,60,0.45);background:rgba(45,212,191,0.1);color:#C49E3C;cursor:pointer;display:inline-flex;align-items:center;gap:6px;">See How It Works</span>
        </div>''',
        unsafe_allow_html=True,
    )
    if st.button("bot_aa_help_video", key="aa_help_video"):
        _algorithm_score_help_dialog()
    st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

    st.markdown('<div style="background:#0d1929;border-left:3px solid #00E5CC;border-radius:8px;padding:14px 16px;font-size:12px;color:#5a8090;margin-bottom:16px;"><strong style="color:#00E5CC;">Example output:</strong> Score 72/100 — Strong hook, weak payoff. Opens with a bold claim but the final line doesn\'t land. Suggestion: End with a question to drive replies.</div>', unsafe_allow_html=True)
    content = st.text_area("Content to Analyze:", height=160, key="aa_input",
        value=st.session_state.get("aa_text", ""),
        placeholder="Paste or type content to analyze against the algorithm...", label_visibility="collapsed")
    char_len = len(content)
    cls = "char-over" if char_len > 280 else ""
    st.markdown(f'<div class="char-count {cls}">{char_len}/280</div>', unsafe_allow_html=True)

    # --- Grades button (same icon as Creator Studio grades) ---
    st.markdown('''<div class="cs-icon-dock cs-algo-dock" style="display:flex;gap:8px;justify-content:center;margin:16px 0;">
      <div class="cs-idock-btn cs-idock-primary" data-dock="aa_analyze" style="width:52px;height:52px;border-radius:14px;background:linear-gradient(135deg,#1fb8a8,#2DD4BF);display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M22 12h-4l-3 9L9 3l-3 9H2" stroke="#060A12" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
        <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">GRADES</span>
      </div>
    </div>''', unsafe_allow_html=True)

    # Hidden button
    _aa_run = st.button("aa_analyze", key="aa_run")

    if _aa_run:
        if content.strip():
            with st.spinner("Analyzing against the algorithm..."):
                prompt = f"""Analyze this content for X algorithm performance:

"{content}"

Score each factor 1-10 and explain in one sentence:
1. HOOK STRENGTH - Does the first line stop the scroll?
2. ENGAGEMENT POTENTIAL - Will people reply, like, RT?
3. CONTROVERSY FACTOR - Does it invite debate without being toxic?
4. FORMAT OPTIMIZATION - Is the length/structure optimal for X?
5. SHAREABILITY - Would someone share this with their audience?
6. TIMING RELEVANCE - Is this timely content?
7. VOICE AUTHENTICITY - Does it sound like a real person with authority?

Then give:
- OVERALL SCORE (out of 100)
- TOP IMPROVEMENT: The single change that would boost performance most
- REWRITE: An optimized version

Return as JSON:
{{"scores": {{"Hook Strength": {{"score": 7, "note": "..."}}, ...}}, "overall": 72, "improvement": "...", "rewrite": "..."}}"""
                raw = call_claude(prompt, max_tokens=800)
                try:
                    json_match = re.search(r'\{.*\}', raw, re.DOTALL)
                    data = json.loads(json_match.group()) if json_match else None
                except Exception:
                    data = None

                if data and "scores" in data:
                    overall = data.get("overall", 0)
                    color = "#22c55e" if overall >= 75 else "#2DD4BF" if overall >= 55 else "#ef4444"
                    st.markdown(f"""<div style="text-align:center; padding:20px 0;">
                        <div style="font-family:'Bebas Neue',sans-serif; font-size:80px; color:{color}; line-height:1;">{overall}</div>
                        <div style="color:#8888aa; font-size:13px; letter-spacing:2px; text-transform:uppercase;">Algorithm Score / 100</div>
                    </div>""", unsafe_allow_html=True)

                    for metric, val in data["scores"].items():
                        score = val.get("score", 0) if isinstance(val, dict) else val
                        note = val.get("note", "") if isinstance(val, dict) else ""
                        bar_color = "#22c55e" if score >= 8 else "#2DD4BF" if score >= 6 else "#ef4444"
                        st.markdown(f"""<div style="margin-bottom:12px;">
                            <div style="display:flex; justify-content:space-between;">
                                <span class="metric-label">{metric}</span>
                                <span class="metric-score">{score}/10</span>
                            </div>
                            <div class="score-bar-wrap"><div class="score-bar-fill" style="width:{score*10}%; background:{bar_color};"></div></div>
                            <div style="font-size:12px; color:#888899;">{note}</div>
                        </div>""", unsafe_allow_html=True)

                    if data.get("improvement"):
                        st.markdown(f'**Top Improvement:** {data["improvement"]}')
                    if data.get("rewrite"):
                        st.markdown(f'<div class="output-box"><strong>Optimized Version:</strong>\n\n{data["rewrite"]}</div>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div class="output-box">{raw}</div>', unsafe_allow_html=True)

    # ── Hidden buttons are CSS-hidden; dock clicks wired by global MutationObserver ──


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════════════
def page_health_check():
    st.markdown('<div class="main-header">ACCOUNT <span>AUDIT</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Full audit of your X account — posting cadence, engagement rate, hook quality, content mix, and actionable fixes.</div>', unsafe_allow_html=True)
    st.markdown(
        '''<div style="display:flex;justify-content:flex-start;margin:0 0 16px 0;">
            <span class="cs-bot" data-bot="hc_help_video" style="height:52px;padding:0 18px;border-radius:14px;font-size:12px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;border:1px solid rgba(196,158,60,0.45);background:rgba(45,212,191,0.1);color:#C49E3C;cursor:pointer;display:inline-flex;align-items:center;gap:6px;">See How It Works</span>
        </div>''',
        unsafe_allow_html=True,
    )
    if st.button("bot_hc_help_video", key="hc_help_video"):
        _account_audit_help_dialog()
    st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

    # What it checks — always visible
    st.markdown("""<div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin:8px 0 16px;">
      <div style="color:#5a7090;font-size:12px;">&#9632; Posting frequency &amp; consistency</div>
      <div style="color:#5a7090;font-size:12px;">&#9632; Hook quality (first-line scroll-stop rate)</div>
      <div style="color:#5a7090;font-size:12px;">&#9632; Engagement rate vs views</div>
      <div style="color:#5a7090;font-size:12px;">&#9632; Content mix (takes / analysis / humor)</div>
      <div style="color:#5a7090;font-size:12px;">&#9632; Underperforming tweets flagged</div>
      <div style="color:#5a7090;font-size:12px;">&#9632; Top 3 specific, actionable improvements</div>
    </div>""", unsafe_allow_html=True)

    # Last run timestamp
    hc_cache = load_json("health_check_cache.json", {})
    last_run = hc_cache.get("last_run", "")
    if last_run:
        try:
            _lr_dt = datetime.strptime(last_run[:10], "%Y-%m-%d")
            _days_ago = (datetime.now() - _lr_dt).days
            _ago_str = "today" if _days_ago == 0 else f"{_days_ago}d ago"
        except Exception:
            _ago_str = ""
        st.caption(f"Last run: {last_run}{' — ' + _ago_str if _ago_str else ''}")
    else:
        st.caption("Never run — click below to get your health score.")

    # --- Audit dock ---
    st.markdown('''<div class="cs-icon-dock cs-hc-dock" style="display:flex;gap:8px;justify-content:center;margin:16px 0;">
      <div class="cs-idock-btn cs-idock-primary" data-dock="hc_run" style="width:52px;height:52px;border-radius:14px;background:linear-gradient(135deg,#1fb8a8,#2DD4BF);display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" stroke="#060A12" stroke-width="2" stroke-linejoin="round"/></svg>
        <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">AUDIT</span>
      </div>
      <div class="cs-idock-btn" data-dock="hc_clear" style="width:52px;height:52px;border-radius:14px;border:1px solid #1a2a45;background:#0a1220;display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><line x1="18" y1="6" x2="6" y2="18" stroke="#5a7090" stroke-width="2"/><line x1="6" y1="6" x2="18" y2="18" stroke="#5a7090" stroke-width="2"/></svg>
        <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">CLEAR</span>
      </div>
    </div>''', unsafe_allow_html=True)

    # Hidden buttons for dock
    run_check = st.button("hc_run", key="hc_run")
    if st.button("hc_clear", key="hc_clear"):
        if hc_cache.get("data"):
            save_json("health_check_cache.json", {})
            st.rerun()

    if run_check:
        with st.spinner("Pulling tweets and analyzing..."):
            _audit_handle = get_current_handle()
            tweets = fetch_tweets(f"from:{_audit_handle}", count=30)
            if not tweets:
                st.error("Could not fetch tweets. Check API key.")
                return

            tweet_texts = "\n---\n".join([f"Tweet: {t.get('text','')}\nLikes: {t.get('likeCount',0)} | RTs: {t.get('retweetCount',0)} | Replies: {t.get('replyCount',0)} | Views: {t.get('viewCount',0)}" for t in tweets[:20]])

            prompt = f"""Analyze @{_audit_handle}'s recent X activity against best practices.

Here are their recent 20 tweets with engagement:
{tweet_texts}

Provide a health check report:

1. HEALTH SCORE (0-100) - Overall account health
2. POSTING FREQUENCY - How often are they posting? Is it enough?
3. ENGAGEMENT RATE - Are likes/RTs/replies proportional to views?
4. HOOK QUALITY - Are his openers stopping scrolls?
5. CONTENT MIX - Good balance of takes, analysis, humor, engagement?
6. FLAGGED TWEETS - Any tweets that underperformed badly? Why?
7. TOP 3 RECOMMENDATIONS - Specific, actionable changes
8. WHAT'S WORKING - Top 2-3 things to keep doing

Return ONLY valid JSON, no markdown, no code fences, no explanation before or after:
{{"health_score": 72, "sections": [{{"title": "...", "grade": "B+", "detail": "..."}}], "flagged": ["..."], "recommendations": ["..."]}}"""

            raw = call_claude(prompt, max_tokens=2000)
            # Parse JSON — try multiple approaches
            data = None
            _clean = raw.strip()
            # 1. Strip code fences
            _clean = re.sub(r'```\w*\s*', '', _clean).strip()
            _clean = _clean.rstrip('`').strip()
            # 2. Try direct parse
            try:
                data = json.loads(_clean)
            except Exception:
                pass
            # 3. Try regex extraction
            if not data:
                try:
                    _jm = re.search(r'\{.*"health_score".*\}', _clean, re.DOTALL)
                    if _jm:
                        data = json.loads(_jm.group())
                except Exception:
                    pass

            if data and isinstance(data, dict) and "health_score" in data:
                save_json("health_check_cache.json", {
                    "data": data,
                    "last_run": datetime.now().strftime("%Y-%m-%d %H:%M MST")
                })
                hc_cache = load_json("health_check_cache.json", {})
            else:
                st.error("Audit returned unexpected format. Click Clear and try again.")

    # Render cached results (persists across sessions)
    data = hc_cache.get("data")
    # Handle case where data was saved as string instead of dict
    if isinstance(data, str):
        try:
            _cd = re.sub(r'```\w*', '', data.strip()).strip()
            _s = _cd.index('{')
            _d = 0
            _e = _s
            for _ci, _ch in enumerate(_cd[_s:], _s):
                if _ch == '{': _d += 1
                elif _ch == '}': _d -= 1
                if _d == 0: _e = _ci + 1; break
            data = json.loads(_cd[_s:_e])
            if data:
                hc_cache["data"] = data
                save_json("health_check_cache.json", hc_cache)
        except Exception:
            data = None
    if data and isinstance(data, dict) and "health_score" in data:
        score = data["health_score"]
        ring_color = "#22c55e" if score >= 75 else "#2DD4BF" if score >= 55 else "#ef4444"
        st.markdown(f"""<div style="display:flex;flex-direction:column;align-items:center;margin:20px 0;">
          <div style="width:120px;height:120px;border-radius:50%;border:6px solid {ring_color};
                      display:flex;align-items:center;justify-content:center;
                      background:rgba(45,212,191,0.05);">
            <span style="font-family:'Bebas Neue',sans-serif;font-size:48px;font-weight:900;color:{ring_color};">{score}</span>
          </div>
          <span style="color:#91A2B2;font-size:12px;letter-spacing:2px;margin-top:8px;">HEALTH SCORE / 100</span>
        </div>""", unsafe_allow_html=True)

        for section in data.get("sections", []):
            _title = section.get("title", "")
            _grade = section.get("grade", "")
            _detail = section.get("detail", "")
            _gc = "#2DD4BF" if _grade and _grade[0] in "AB" else "#FBBF24" if _grade and _grade[0] == "C" else "#F87171"
            st.markdown(f'''<div style="background:#0a1220;border:1px solid #1a2a45;border-radius:14px;padding:16px 18px;margin-bottom:10px;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                    <span style="font-size:10px;font-weight:700;letter-spacing:0.08em;color:#5a7090;text-transform:uppercase;">{_title}</span>
                    <span style="font-size:14px;font-weight:800;color:{_gc};">{_grade}</span>
                </div>
                <div style="font-size:14px;color:#b0c0d0;line-height:1.7;">{_detail}</div>
            </div>''', unsafe_allow_html=True)

        if data.get("flagged"):
            st.markdown('<div style="font-size:10px;font-weight:700;letter-spacing:0.08em;color:#F87171;text-transform:uppercase;margin:16px 0 8px;">FLAGGED TWEETS</div>', unsafe_allow_html=True)
            for f in data["flagged"]:
                st.markdown(f'<div style="background:#0a1220;border:1px solid rgba(248,113,113,0.2);border-left:3px solid #F87171;border-radius:10px;padding:12px 16px;margin-bottom:8px;font-size:14px;color:#b0c0d0;line-height:1.6;">{f}</div>', unsafe_allow_html=True)

        if data.get("recommendations"):
            st.markdown('<div style="font-size:10px;font-weight:700;letter-spacing:0.08em;color:#2DD4BF;text-transform:uppercase;margin:16px 0 8px;">RECOMMENDATIONS</div>', unsafe_allow_html=True)
            for r in data["recommendations"]:
                st.markdown(f'<div style="background:#0a1220;border:1px solid #1a2a45;border-left:3px solid #2DD4BF;border-radius:10px;padding:12px 16px;margin-bottom:8px;font-size:14px;color:#b0c0d0;line-height:1.6;">{r}</div>', unsafe_allow_html=True)

    # ── Hidden buttons are CSS-hidden; dock clicks wired by global MutationObserver ──


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: ACCOUNT PULSE
# ═══════════════════════════════════════════════════════════════════════════
def page_account_pulse():
    st.markdown('<div class="main-header">MY <span>STATS</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Your account stats at a glance.</div>', unsafe_allow_html=True)
    st.markdown(
        '''<div style="display:flex;justify-content:flex-start;margin:0 0 16px 0;">
            <span class="cs-bot" data-bot="ap_help_video" style="height:52px;padding:0 18px;border-radius:14px;font-size:12px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;border:1px solid rgba(196,158,60,0.45);background:rgba(45,212,191,0.1);color:#C49E3C;cursor:pointer;display:inline-flex;align-items:center;gap:6px;">See How It Works</span>
        </div>''',
        unsafe_allow_html=True,
    )
    if st.button("bot_ap_help_video", key="ap_help_video"):
        _my_stats_help_dialog()
    st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

    _ap_handle = get_current_handle()
    _ap_ready_key = f"ap_ready::{_ap_handle}"
    _ap_loaded_key = f"ap_loaded::{_ap_handle}"
    _ap_user_key = f"ap_user::{_ap_handle}"
    _ap_tweets_key = f"ap_tweets::{_ap_handle}"
    if _ap_ready_key not in st.session_state:
        st.session_state[_ap_ready_key] = True

    # --- Refresh as primary dock button ---
    st.markdown('''<div class="cs-icon-dock cs-ap-dock" style="display:flex;gap:8px;justify-content:center;margin:8px 0 16px;">
      <div class="cs-idock-btn cs-idock-primary" data-dock="ap_refresh" style="width:52px;height:52px;border-radius:14px;background:linear-gradient(135deg,#1fb8a8,#2DD4BF);display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M23 4v6h-6M1 20v-6h6" stroke="#060A12" stroke-width="2"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" stroke="#060A12" stroke-width="2"/></svg>
        <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">REFRESH</span>
      </div>
    </div>''', unsafe_allow_html=True)

    if st.button("ap_refresh", key="ap_load"):
        with st.spinner("Refreshing..."):
            user = fetch_user_info(_ap_handle)
            tweets = fetch_tweets(f"from:{_ap_handle}", count=50)
            st.session_state[_ap_user_key] = user
            st.session_state[_ap_tweets_key] = tweets
            st.session_state[_ap_loaded_key] = True
            st.rerun()

    user = st.session_state.get(_ap_user_key, {})
    tweets = st.session_state.get(_ap_tweets_key, [])

    if not user:
        _msg = "Tap Refresh to load your latest account stats." if st.session_state.get(_ap_ready_key) else "Preparing stats..."
        st.markdown(f'<div style="color:#555778;font-size:13px;padding:12px 0;">{_msg}</div>', unsafe_allow_html=True)
        return

    followers = user.get("followers", user.get("followersCount", user.get("followers_count", 0)))
    following = user.get("following", user.get("followingCount", user.get("following_count", 0)))
    tweet_count = user.get("statusesCount", user.get("tweets_count", user.get("statuses_count", 0)))
    ratio = round(followers / max(following, 1), 1)
    followers_display = "—" if not followers else f"{followers:,}"

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="stat-card"><div class="stat-num">{followers_display}</div><div class="stat-label">Followers</div><div style="font-size:10px;color:#444466;margin-top:4px;">Sync via Update Posts</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="stat-card"><div class="stat-num">{ratio}x</div><div class="stat-label">Following Ratio</div></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="stat-card"><div class="stat-num">{tweet_count:,}</div><div class="stat-label">Total Posts</div></div>', unsafe_allow_html=True)
    with c4:
        freq = len(tweets) if tweets else 0
        st.markdown(f'<div class="stat-card"><div class="stat-num">{freq}</div><div class="stat-label">Recent Posts (batch)</div></div>', unsafe_allow_html=True)

    if tweets:
        st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

        # Analyze posting times and engagement
        total_likes = sum(t.get("likeCount", 0) for t in tweets)
        total_views = sum(t.get("viewCount", 0) for t in tweets)
        avg_likes = round(total_likes / max(len(tweets), 1))
        avg_views = round(total_views / max(len(tweets), 1))

        ac1, ac2, ac3 = st.columns(3)
        with ac1:
            st.markdown(f'<div class="stat-card"><div class="stat-num">{avg_likes:,}</div><div class="stat-label">Avg Likes/Post</div></div>', unsafe_allow_html=True)
        with ac2:
            st.markdown(f'<div class="stat-card"><div class="stat-num">{avg_views:,}</div><div class="stat-label">Avg Views/Post</div></div>', unsafe_allow_html=True)
        with ac3:
            eng_rate = round((total_likes / max(total_views, 1)) * 100, 2)
            st.markdown(f'<div class="stat-card"><div class="stat-num">{eng_rate}%</div><div class="stat-label">Engagement Rate</div></div>', unsafe_allow_html=True)

        # Top 5 tweets - sort pills as HTML
        _sort_opts = ["Likes", "Views", "Replies", "RTs"]
        if "stats_sort_sel" not in st.session_state:
            st.session_state.stats_sort_sel = "Likes"
        _son = "height:44px;padding:0 16px;border-radius:14px;font-size:12px;font-weight:600;background:rgba(45,212,191,0.1);border:1px solid rgba(45,212,191,0.4);color:#2DD4BF;cursor:pointer;display:inline-flex;align-items:center;white-space:nowrap;"
        _soff = "height:44px;padding:0 16px;border-radius:14px;font-size:12px;font-weight:600;background:#0e1a2e;border:1px solid #1a2a45;color:#5a7090;cursor:pointer;display:inline-flex;align-items:center;white-space:nowrap;"
        _sort_html = '<div style="display:flex;gap:8px;flex-wrap:wrap;margin:12px 0;">'
        _sort_html += '<span style="font-size:9px;font-weight:700;letter-spacing:1.2px;color:#3a5070;text-transform:uppercase;display:flex;align-items:center;margin-right:4px;">Sort By</span>'
        for _si, _so in enumerate(_sort_opts):
            _cls = _son if st.session_state.stats_sort_sel == _so else _soff
            _sort_html += f'<span class="cs-bot" data-bot="ap_sort_{_si}" style="{_cls}">{_so}</span>'
        _sort_html += '</div>'
        st.markdown(_sort_html, unsafe_allow_html=True)
        for _si, _so in enumerate(_sort_opts):
            if st.button(f"ap_sort_{_si}", key=f"ap_sort_{_si}"):
                st.session_state.stats_sort_sel = _so
                st.rerun()
        _sort_by = st.session_state.stats_sort_sel
        _sort_map = {"Likes": "likeCount", "Views": "viewCount", "Replies": "replyCount", "RTs": "retweetCount"}
        top5 = sorted(tweets, key=lambda t: t.get(_sort_map[_sort_by], 0), reverse=True)[:5]
        for t in top5:
            render_tweet_card(t)

        # AI analysis — Pulse dock button
        st.markdown('''<div class="cs-icon-dock cs-ap-pulse-dock" style="display:flex;gap:8px;justify-content:center;margin:16px 0;">
          <div class="cs-idock-btn cs-idock-primary" data-dock="ap_pulse" style="width:52px;height:52px;border-radius:14px;background:linear-gradient(135deg,#1fb8a8,#2DD4BF);display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M22 12h-4l-3 9L9 3l-3 9H2" stroke="#060A12" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/></svg>
            <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">PULSE</span>
          </div>
        </div>''', unsafe_allow_html=True)

        if st.button("ap_pulse", key="ap_ai"):
            with st.spinner("Analyzing patterns..."):
                tweet_summary = "\n".join([f"- {t.get('text','')[:100]} (Likes:{t.get('likeCount',0)}, Views:{t.get('viewCount',0)})" for t in tweets[:20]])
                _ap_handle_name = get_current_handle() or "this creator"
                _ap_poss = "their" if is_guest() else "his"
                result = call_claude(f"""Analyze @{_ap_handle_name}'s recent posting patterns:

Followers: {followers:,} | Following: {following:,} | Ratio: {ratio}x
Avg Likes: {avg_likes} | Avg Views: {avg_views} | Engagement: {eng_rate}%

Recent tweets:
{tweet_summary}

Give:
1. BEST POSTING TIME - When do {_ap_poss} best tweets seem to land?
2. TOP GROWTH OPPORTUNITIES - 3 specific things to improve
3. CONTENT MIX ASSESSMENT - What should {_ap_poss} content mix shift toward?
4. AVERAGE DAILY GROWTH ESTIMATE - Based on current trajectory""", max_tokens=800)
                st.markdown(f'<div class="output-box">{result}</div>', unsafe_allow_html=True)

    # ── Hidden buttons are CSS-hidden; dock clicks wired by global MutationObserver ──


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: ACCOUNT RESEARCHER
# ═══════════════════════════════════════════════════════════════════════════
def page_account_researcher():
    st.markdown('<div class="main-header">PROFILE <span>ANALYZER</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Research any X account. Understand their strategy.</div>', unsafe_allow_html=True)
    st.markdown(
        '''<div style="display:flex;justify-content:flex-start;margin:0 0 16px 0;">
            <span class="cs-bot" data-bot="ar_help_video" style="height:52px;padding:0 18px;border-radius:14px;font-size:12px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;border:1px solid rgba(196,158,60,0.45);background:rgba(45,212,191,0.1);color:#C49E3C;cursor:pointer;display:inline-flex;align-items:center;gap:6px;">See How It Works</span>
        </div>''',
        unsafe_allow_html=True,
    )
    if st.button("bot_ar_help_video", key="ar_help_video"):
        _profile_analyzer_help_dialog()
    st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

    handle = st.text_input("Enter X handle:", placeholder="@username", key="ar_handle_input", label_visibility="collapsed")

    # --- Research dock ---
    st.markdown('''<div class="cs-icon-dock cs-ar-dock" style="display:flex;gap:8px;justify-content:center;margin:12px 0 16px;">
      <div class="cs-idock-btn cs-idock-primary" data-dock="ar_research" style="width:52px;height:52px;border-radius:14px;background:linear-gradient(135deg,#1fb8a8,#2DD4BF);display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><circle cx="11" cy="11" r="8" stroke="#060A12" stroke-width="2"/><line x1="21" y1="21" x2="16.65" y2="16.65" stroke="#060A12" stroke-width="2"/></svg>
        <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">RESEARCH</span>
      </div>
    </div>''', unsafe_allow_html=True)

    if st.button("ar_research", key="ar_run"):
        if handle.strip():
            handle_clean = handle.strip().lstrip("@")
            with st.spinner(f"Researching @{handle_clean}..."):
                tweets = fetch_tweets(f"from:{handle_clean}", count=30)
                user_info = fetch_user_info(handle_clean)
                recent = load_json("recent_searches.json", [])
                if handle_clean not in [r.get("handle") for r in recent]:
                    recent.append({"handle": handle_clean, "searched_at": datetime.now().isoformat()})
                    save_json("recent_searches.json", recent[-20:])
                if tweets:
                    st.session_state["ar_tweets"] = tweets
                    st.session_state["ar_user"] = user_info
                    st.session_state["ar_handle"] = handle_clean
                    tweet_texts = "\n---\n".join([f"{t.get('text','')}\nLikes:{t.get('likeCount',0)} RTs:{t.get('retweetCount',0)} Views:{t.get('viewCount',0)}" for t in tweets[:20]])
                    raw = call_claude(f"""Analyze @{handle_clean}'s X account. Return ONLY a JSON object, no markdown, no explanation.

Tweets:
{tweet_texts}

Return this exact JSON structure:
{{
  "summary": "2-3 sentence paragraph describing their overall content strategy and voice",
  "content_themes": ["theme 1", "theme 2", "theme 3", "theme 4"],
  "tone": "one sentence describing tone",
  "voice": "one sentence describing voice",
  "formatting": "one sentence describing formatting style",
  "engagement_tactics": ["tactic 1", "tactic 2", "tactic 3", "tactic 4"],
  "unique_characteristics": ["characteristic 1", "characteristic 2", "characteristic 3"],
  "content_patterns": ["pattern 1", "pattern 2", "pattern 3"],
  "your_edge": "one sentence on where @{get_current_handle()}'s credibility or perspective beats this account",
  "steal_worthy": ["tactic to steal 1", "tactic to steal 2"]
}}""", max_tokens=1200)
                    try:
                        raw_clean = raw.strip()
                        if raw_clean.startswith("```"):
                            raw_clean = raw_clean.split("\n", 1)[1].rsplit("```", 1)[0]
                        st.session_state["ar_analysis"] = json.loads(raw_clean)
                    except Exception:
                        st.session_state["ar_analysis"] = {"summary": raw}
                else:
                    st.warning(f"Could not fetch tweets for @{handle_clean}")

    # Recent searches as pills
    recent = load_json("recent_searches.json", [])
    _recent_rev = list(reversed(recent[-8:]))
    if _recent_rev:
        st.markdown('<div style="font-size:9px;font-weight:700;letter-spacing:1.2px;color:#3a5070;text-transform:uppercase;margin:12px 0 4px;">Recent</div>', unsafe_allow_html=True)
        _rc = st.columns(min(len(_recent_rev), 6))
        for _ri, r in enumerate(_recent_rev[:6]):
            with _rc[_ri]:
                if st.button(f"@{r.get('handle','')}", key=f"ar_recent_{r.get('handle')}", type="secondary"):
                    st.session_state["ar_handle_input"] = r.get("handle", "")
                    st.rerun()

    st.markdown('<div style="height:1px;background:#1a2a45;margin:24px 0 14px;"></div>', unsafe_allow_html=True)

    # Analysis results
    analysis = st.session_state.get("ar_analysis")
    if not analysis:
        st.markdown('<div style="color:#555577; text-align:center; padding:40px 20px; font-size:14px;">Enter a handle and click Research</div>', unsafe_allow_html=True)
    else:
        hdl = st.session_state.get("ar_handle", "")
        ui = st.session_state.get("ar_user", {})
        _followers = ui.get("followers", ui.get("followersCount", 0))

        # ── Header + Save Voice at top ──
        hdl_for_save = hdl
        existing_styles = load_json("voice_styles.json", [])
        already_saved = any(s.get("handle") == hdl_for_save for s in existing_styles)

        _hdr = f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">'
        _hdr += f'<div><div style="font-size:11px;letter-spacing:2px;color:#2DD4BF;font-weight:700;">ACCOUNT ANALYSIS — @{hdl}</div>'
        if _followers:
            _hdr += f'<div style="font-size:12px;color:#666888;margin-top:2px;">{_followers:,} followers</div>'
        _hdr += '</div>'
        if already_saved:
            _hdr += '<div style="color:#4ade80;font-size:11px;font-weight:600;">✓ Voice Saved</div>'
        else:
            _hdr += '<span class="cs-bot" data-bot="ar_save_voice" style="height:44px;padding:0 16px;border-radius:14px;font-size:12px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;border:1px solid rgba(196,158,60,0.25);background:#0a1220;color:rgba(196,158,60,0.6);cursor:pointer;display:inline-flex;align-items:center;">SAVE VOICE</span>'
        _hdr += '</div>'
        st.markdown(_hdr, unsafe_allow_html=True)

        if already_saved:
            if st.button("Remove Voice Style", key="ar_remove_voice", type="secondary"):
                existing_styles = [s for s in existing_styles if s.get("handle") != hdl_for_save]
                save_json("voice_styles.json", existing_styles)
                st.rerun()
        else:
            if st.button("ar_save_voice", key="ar_save_voice"):
                tweets_sample = [t.get("text", "") for t in st.session_state.get("ar_tweets", [])[:15] if not t.get("text","").startswith("@") and len(t.get("text","")) > 30]
                style_entry = {"name": f"@{hdl_for_save}", "handle": hdl_for_save,
                    "summary": analysis.get("summary", "") + " Tone: " + analysis.get("tone", "") + " Voice: " + analysis.get("voice", ""),
                    "tweets": tweets_sample, "saved_at": datetime.now().isoformat()}
                existing_styles.append(style_entry)
                save_json("voice_styles.json", existing_styles)
                st.success(f"@{hdl_for_save} voice style saved!")
                st.rerun()

        # ── Two columns: Analysis left, Tweets right ──
        _ar_left, _ar_right = st.columns([3, 2])

        def ar_card(title, content, col):
            if isinstance(content, list):
                items = "".join([f'<li style="color:#b0c0d0;font-size:14px;margin-bottom:4px;">{i}</li>' for i in content])
                body = f'<ul style="margin:0;padding-left:18px;">{items}</ul>'
            else:
                body = f'<div style="color:#b0c0d0;font-size:14px;line-height:1.6;">{content}</div>'
            col.markdown(f'''<div style="background:#0a1220;border:1px solid #1a2a45;border-radius:14px;padding:14px 16px;margin-bottom:10px;">
                <div style="font-size:10px;font-weight:700;letter-spacing:0.08em;color:#5a7090;text-transform:uppercase;margin-bottom:6px;">{title}</div>
                {body}
            </div>''', unsafe_allow_html=True)

        if analysis.get("summary"):
            ar_card("Strategy", analysis["summary"], _ar_left)
        _edge = analysis.get("your_edge") or analysis.get("tylers_edge")
        if _edge:
            ar_card("Your Edge", _edge, _ar_left)
        if analysis.get("steal_worthy"):
            ar_card("Steal-Worthy", analysis["steal_worthy"], _ar_left)
        if analysis.get("content_themes"):
            ar_card("Themes", analysis["content_themes"], _ar_left)
        if analysis.get("engagement_tactics"):
            ar_card("Tactics", analysis["engagement_tactics"], _ar_left)
        if analysis.get("tone") or analysis.get("voice"):
            _style = ""
            if analysis.get("tone"): _style += f"<b>Tone:</b> {analysis['tone']}<br>"
            if analysis.get("voice"): _style += f"<b>Voice:</b> {analysis['voice']}<br>"
            if analysis.get("formatting"): _style += f"<b>Format:</b> {analysis['formatting']}"
            ar_card("Writing Style", _style, _ar_left)

        with _ar_right:
            _ar_tweets = st.session_state.get("ar_tweets", [])
            if _ar_tweets:
                st.markdown('<div style="font-size:9px;font-weight:700;letter-spacing:1.2px;color:#3a5070;text-transform:uppercase;margin-bottom:8px;">TOP TWEETS</div>', unsafe_allow_html=True)
                for t in _ar_tweets[:6]:
                    render_tweet_card(t)

    # ── Hidden buttons are CSS-hidden; dock/bottom clicks wired by global MutationObserver ──


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: REPLY GUY
# ═══════════════════════════════════════════════════════════════════════════
def page_reply_guy():
    XURL = "/home/linuxbrew/.linuxbrew/bin/xurl"
    if "custom_lists" not in st.session_state:
        st.session_state.custom_lists = load_engagement_lists()
    # Restore any known list_ids that got wiped (migration safety net) — owner only
    if not is_guest():
        for _k, _v in _ENGAGEMENT_DEFAULTS.items():
            if _k in st.session_state.custom_lists and isinstance(st.session_state.custom_lists[_k], dict):
                if not st.session_state.custom_lists[_k].get('list_id'):
                    st.session_state.custom_lists[_k]['list_id'] = _v['list_id']

    st.markdown('<div class="main-header">REPLY <span>MODE</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Build your daily reply habit. 50 replies a day grows the account.</div>', unsafe_allow_html=True)
    st.markdown(
        '''<div style="display:flex;justify-content:flex-start;margin:0 0 16px 0;">
            <span class="cs-bot" data-bot="rg_help_video" style="height:52px;padding:0 18px;border-radius:14px;font-size:12px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;border:1px solid rgba(196,158,60,0.45);background:rgba(45,212,191,0.1);color:#C49E3C;cursor:pointer;display:inline-flex;align-items:center;gap:6px;">See How It Works</span>
        </div>''',
        unsafe_allow_html=True,
    )
    if st.button("bot_rg_help_video", key="rg_help_video"):
        _reply_mode_help_dialog()
    st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

    # --- Load & roll-over progress ---
    progress = load_json("reply_progress.json", {"today": "", "count": 0, "streak": 0, "history": []})
    today_str = datetime.now().strftime("%Y-%m-%d")
    if progress.get("today") != today_str:
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        if progress.get("today") == yesterday and progress.get("count", 0) >= 10:
            progress["streak"] = progress.get("streak", 0) + 1
        elif progress.get("today") != yesterday:
            progress["streak"] = 0
        if progress.get("today"):
            progress["history"].append({"date": progress["today"], "count": progress.get("count", 0)})
        progress["history"] = progress["history"][-30:]
        progress["today"] = today_str
        progress["count"] = 0
        save_json("reply_progress.json", progress)
    reply_count = progress.get("count", 0)
    streak = progress.get("streak", 0)

    # ── Stats Bar ──
    _sc1, _sc2 = st.columns([3, 1])
    with _sc1:
        _pct = min(reply_count / 50 * 100, 100)
        st.markdown(f'<div style="margin-bottom:8px;">'
                    f'<div style="display:flex;justify-content:space-between;margin-bottom:5px;">'
                    f'<span style="font-size:9px;letter-spacing:.06em;text-transform:uppercase;color:rgba(45,212,191,0.75);font-weight:600;">TODAY\'S REPLIES</span>'
                    f'<span style="font-size:9px;font-weight:700;color:#2DD4BF;">{reply_count} / 50</span></div>'
                    f'<div style="height:5px;background:rgba(45,212,191,0.1);border-radius:3px;">'
                    f'<div style="width:{_pct}%;height:100%;background:linear-gradient(90deg,#1fb8a8,#2DD4BF);border-radius:3px;transition:width .3s;"></div>'
                    f'</div></div>', unsafe_allow_html=True)
    with _sc2:
        st.markdown(f'<div class="stat-card" style="padding:8px 10px;"><div class="stat-num" style="font-size:28px;">{streak}</div><div class="stat-label" style="font-size:9px;letter-spacing:1px;">Streak</div></div>', unsafe_allow_html=True)
    _day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    _hist_map = {h["date"]: h["count"] for h in progress.get("history", [])}
    _hist_map[today_str] = reply_count
    _week_html = '<div class="rg-week-grid">'
    for _d in range(6, -1, -1):
        _dt = datetime.now() - timedelta(days=_d)
        _ds = _dt.strftime("%Y-%m-%d")
        _dlabel = _day_labels[_dt.weekday()]
        _cnt = _hist_map.get(_ds, 0)
        _dcls = "day-card day-card-active" if _cnt > 0 else "day-card"
        _week_html += f'<div class="{_dcls}"><div class="day-card-label">{_dlabel}</div><div class="day-card-num">{_cnt}</div></div>'
    _week_html += '</div>'
    st.markdown(_week_html, unsafe_allow_html=True)
    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)
    _rg_actions = _load_actions_gist()
    replied_tweets = _rg_actions["replied"]
    liked_tweets_global = _rg_actions["liked"]

    def _bump_reply():
        progress["count"] = progress.get("count", 0) + 1
        save_json("reply_progress.json", progress)

    def _mark_replied(tweet_id):
        if tweet_id not in replied_tweets:
            replied_tweets.append(tweet_id)
            _rg_actions["replied"] = replied_tweets[-500:]
            _save_actions_gist(_rg_actions)

    # ── List selection as HTML pills ──
    _list_keys = list(st.session_state.custom_lists.keys())
    if "rg_source_sel" not in st.session_state:
        st.session_state.rg_source_sel = _list_keys[0] if _list_keys else ""
    _lon = "height:44px;padding:0 16px;border-radius:14px;font-size:12px;font-weight:600;background:rgba(45,212,191,0.1);border:1px solid rgba(45,212,191,0.4);color:#2DD4BF;cursor:pointer;display:inline-flex;align-items:center;white-space:nowrap;"
    _loff = "height:44px;padding:0 16px;border-radius:14px;font-size:12px;font-weight:600;background:#0e1a2e;border:1px solid #1a2a45;color:#5a7090;cursor:pointer;display:inline-flex;align-items:center;white-space:nowrap;"
    _list_html = '<div style="display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 12px;">'
    for _li, _lk in enumerate(_list_keys[:7]):
        _cls = _lon if st.session_state.rg_source_sel == _lk else _loff
        _list_html += f'<span class="cs-bot" data-bot="rg_list_{_li}" style="{_cls}">{_lk}</span>'
    _list_html += f'<span class="cs-bot" data-bot="rg_new_list" style="{_loff}">+ New</span>'
    _list_html += '</div>'
    st.markdown(_list_html, unsafe_allow_html=True)

    for _li, _lk in enumerate(_list_keys[:7]):
        if st.button(f"rg_list_{_li}", key=f"rg_list_{_li}"):
            st.session_state.rg_source_sel = _lk
            st.rerun()
    if st.button("rg_new_list", key="rg_new_list_btn"):
        st.session_state["rg_show_new_list"] = not st.session_state.get("rg_show_new_list", False)
    list_source = st.session_state.rg_source_sel

    # --- Action dock: Load Feed, My Replies, Verified ---
    st.markdown('''<div style="font-size:8px;font-weight:700;letter-spacing:1.5px;color:#2a3a55;text-transform:uppercase;margin:12px 0 8px;">ACTIONS</div>
    <div class="cs-icon-dock cs-rg-dock" style="display:flex;gap:8px;justify-content:center;margin-bottom:16px;">
      <div class="cs-idock-btn cs-idock-primary" data-dock="rg_load" style="width:52px;height:52px;border-radius:14px;background:linear-gradient(135deg,#1fb8a8,#2DD4BF);display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4M7 10l5 5 5-5M12 15V3" stroke="#060A12" stroke-width="2"/></svg>
        <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">LOAD</span>
      </div>
      <div class="cs-idock-btn" data-dock="rg_replies" style="width:52px;height:52px;border-radius:14px;border:1px solid #1a2a45;background:#0a1220;display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M21 11.5a8.38 8.38 0 01-.9 3.8 8.5 8.5 0 01-7.6 4.7 8.38 8.38 0 01-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 01-.9-3.8 8.5 8.5 0 014.7-7.6 8.38 8.38 0 013.8-.9h.5a8.48 8.48 0 018 8v.5z" stroke="#5a7090" stroke-width="2"/></svg>
        <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">REPLIES</span>
      </div>
      <div class="cs-idock-btn" data-dock="rg_verified" style="width:52px;height:52px;border-radius:14px;border:1px solid #1a2a45;background:#0a1220;display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M22 11.08V12a10 10 0 11-5.93-9.14" stroke="#5a7090" stroke-width="2"/><polyline points="22 4 12 14.01 9 11.01" stroke="#5a7090" stroke-width="2"/></svg>
        <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">VERIFIED</span>
      </div>
    </div>''', unsafe_allow_html=True)

    # Hidden buttons for dock
    do_load = st.button("rg_load", key="rg_load_posts")
    load_all = st.button("rg_replies", key="rg_load_all")
    load_verified = st.button("rg_verified", key="rg_load_verified")

    if st.session_state.get("rg_show_new_list"):
        st.markdown("**Add X List**")
        _nl_name = st.text_input("List name", placeholder="e.g. NFL Insiders", key="rg_nl_name")
        _nl_lid  = st.text_input("X List ID", placeholder="e.g. 1234567890  (from x.com/i/lists/...)", key="rg_nl_lid")
        st.caption("Find your List ID: open the list on X, copy the number from the URL")
        _s1, _s2 = st.columns(2)
        with _s1:
            if st.button("Save", use_container_width=True, type="primary", key="rg_nl_save"):
                if _nl_name.strip() and _nl_lid.strip():
                    import re as _re2
                    _raw_lid = _nl_lid.strip()
                    if '/' in _raw_lid:
                        _m2 = _re2.search(r'(\d{10,})', _raw_lid)
                        _raw_lid = _m2.group(1) if _m2 else _raw_lid
                    st.session_state.custom_lists[_nl_name.strip()] = {"list_id": _raw_lid}
                    save_engagement_lists(st.session_state.custom_lists)
                    st.session_state["rg_show_new_list"] = False
                    st.success(f"List '{_nl_name.strip()}' saved.")
                    st.rerun()
        with _s2:
            if st.button("Cancel", use_container_width=True, key="rg_nl_cancel"):
                st.session_state["rg_show_new_list"] = False
                st.rerun()

    _list_data = st.session_state.custom_lists.get(list_source, {})
    _list_id   = _list_data.get("list_id", "") if isinstance(_list_data, dict) else ""
    _cap_col, _del_col = st.columns([3, 1])
    with _cap_col:
        if _list_id:
            st.caption(f"X List ID: {_list_id}")
        elif _search_q:
            st.caption(f"Search: {_search_q}")
        else:
            st.caption("No List ID — click + New to add one")
    with _del_col:
        if st.button("🗑 Delete", key="rg_del_list_btn", use_container_width=True,
                     help="Remove this list from engagement targets"):
            st.session_state["rg_confirm_delete"] = list_source

    if st.session_state.get("rg_confirm_delete") == list_source:
        st.warning(f"Delete **{list_source}**? This cannot be undone.")
        _dc1, _dc2 = st.columns(2)
        with _dc1:
            if st.button("Yes, delete", key="rg_del_confirm", type="primary", use_container_width=True):
                del st.session_state.custom_lists[list_source]
                save_engagement_lists(st.session_state.custom_lists)
                st.session_state.pop("rg_confirm_delete", None)
                st.rerun()
        with _dc2:
            if st.button("Cancel", key="rg_del_cancel", use_container_width=True):
                st.session_state.pop("rg_confirm_delete", None)
                st.rerun()

    _search_q = _list_data.get("search_query", "") if isinstance(_list_data, dict) else ""
    if do_load:
        if not _list_id and not _search_q:
            st.error("No X List ID or search query for this feed. Use + New to set one.")
        else:
            with st.spinner("Fetching posts..."):
                from datetime import timezone as _tz, timedelta as _td
                from dateutil import parser as _dtparser
                if _list_id:
                    raw_tweets = fetch_tweets_from_list(_list_id, count=100)
                else:
                    raw_tweets = fetch_tweets(_search_q, count=50)
                _now_utc = datetime.now(_tz.utc)
                _cutoff  = _now_utc - _td(hours=24)
                def _fresh(t):
                    ts = t.get("createdAt", t.get("created_at", ""))
                    if not ts: return False
                    try:
                        td = _dtparser.parse(ts)
                        if td.tzinfo is None:
                            td = td.replace(tzinfo=_tz.utc)
                        return td >= _cutoff
                    except Exception:
                        try:
                            import re as _re
                            tc = _re.sub(r"\+\d{2}:\d{2}$", "Z", str(ts))
                            td = datetime.fromisoformat(tc.replace("Z", "+00:00"))
                            return td >= _cutoff
                        except Exception:
                            return False
                all_tweets = []
                for t in raw_tweets:
                    if _fresh(t):
                        author = t.get("author", {})
                        all_tweets.append({
                            "id": t.get("id", ""),
                            "text": t.get("text", ""),
                            "createdAt": t.get("createdAt", t.get("created_at", "")),
                            "likeCount": t.get("likeCount", 0),
                            "retweetCount": t.get("retweetCount", 0),
                            "replyCount": t.get("replyCount", 0),
                            "viewCount": t.get("viewCount", 0),
                            "_target_account": author.get("userName", author.get("username", "")),
                            "author": author,
                            "media": t.get("media", t.get("extendedEntities", {}).get("media", []) if isinstance(t.get("extendedEntities"), dict) else []),
                        })
                st.session_state["rg_tweets"] = all_tweets
                st.session_state["rg_loaded_at"] = datetime.now().strftime("%I:%M %p")
                _oldest = raw_tweets[-1].get("createdAt", "?") if raw_tweets else "none"
                st.session_state["rg_debug"] = (
                    f"DEBUG: fetched {len(raw_tweets)} from list, {len(all_tweets)} passed 24hr filter, "
                    f"oldest={_oldest}, cutoff={_cutoff.isoformat()}"
                )

    # ── My Tweet Replies data fetch (buttons now in merged top bar above) ──
    if load_all or load_verified:
        with st.spinner("Fetching tweets and replies..."):
            _rg_handle = get_current_handle()
            my_tweets = fetch_tweets(f"from:{_rg_handle}", count=15)
            filtered = [t for t in my_tweets if int(t.get("replyCount", t.get("reply_count", 0))) >= 2][:8]
            st.session_state["rg_my_tweets"] = filtered
            for idx, tw in enumerate(filtered):
                tw_id = tw.get("id", "")
                replies = fetch_tweets(f"conversation_id:{tw_id}", count=25)
                replies = [r for r in replies if r.get("author", {}).get("userName", "").lower() != _rg_handle.lower() and r.get("id", "") != tw_id]
                if load_verified:
                    replies = [r for r in replies if r.get("author", {}).get("isBlueVerified", False) or int(r.get("author", {}).get("followers", 0)) >= 5000]
                replies.sort(key=lambda r: int(r.get("likeCount", r.get("like_count", 0))), reverse=True)
                st.session_state[f"rg_replies_{idx}"] = replies[:8]

    # ── Main layout: tweet feed (left) + sticky Inspiration Engine (right) ──
    tweets_data = st.session_state.get("rg_tweets", [])
    if st.session_state.get("rg_loaded_at"):
        st.caption(f"Tweets from the last 24 hours · Loaded {st.session_state['rg_loaded_at']}")

    col_feed, col_insp = st.columns([3, 1])

    with col_insp:
        st.markdown('<div style="font-size:10px;letter-spacing:2px;color:#445;font-weight:700;margin-bottom:8px;">INSPIRATION ENGINE</div>', unsafe_allow_html=True)
        _insp_disabled = not bool(tweets_data)
        if st.button("⚡ Generate Ideas", use_container_width=True, type="primary", key="btn_inspiration", disabled=_insp_disabled):
            _lines = [f"@{t.get('_target_account','?')}: {t.get('text','')[:120]}" for t in tweets_data[:15]]
            _insp_handle = get_current_handle()
            _prompt = (
                "Based on these tweets from accounts in the feed:\n\n"
                + "\n".join(f"- {l}" for l in _lines)
                + f"\n\nGenerate 5 fresh, punchy tweet ideas for @{_insp_handle}. "
                "Each should react to something in the feed, match the voice in the system prompt, be under 280 chars. "
                "Numbered list. No hashtags. No emojis."
            )
            with st.spinner("Reading the feed..."):
                st.session_state["rg_inspiration_ideas"] = call_claude(_prompt, system=build_user_context(), max_tokens=1000)
        if not tweets_data:
            st.caption("Load a feed first")
        if st.session_state.get("rg_inspiration_ideas"):
            # Parse numbered list into individual ideas
            import re as _re_insp
            _raw_ideas = st.session_state["rg_inspiration_ideas"]
            _idea_parts = _re_insp.split(r'\n?\d+[\.\)]\s+', _raw_ideas)
            _ideas = [p.strip() for p in _idea_parts if p.strip()]
            for _ii, _idea in enumerate(_ideas):
                st.markdown(
                    f'<div style="font-size:12px;color:#c0c8d8;line-height:1.5;margin:8px 0 4px;">'
                    f'<span style="color:#445;font-size:10px;">{_ii+1}.</span> {_idea}</div>',
                    unsafe_allow_html=True)
                if st.button("⚡ Go Viral", key=f"rg_viral_{_ii}", use_container_width=True, type="primary"):
                    st.session_state["rg_viral_idea"] = _idea
                    st.session_state["rg_viral_fmt"] = "Normal Tweet"
                    st.session_state["rg_viral_voice"] = "Default"
                    st.rerun()
            if st.button("↺ Regen", use_container_width=True, key="btn_regen_insp"):
                del st.session_state["rg_inspiration_ideas"]
                st.session_state.pop("rg_viral_idea", None)
                st.rerun()
        # JS — makes this column position:fixed so it floats as user scrolls
        import streamlit.components.v1 as _stc_insp
        _stc_insp.html("""<script>
(function(){
  function floatInsp(){
    var doc=window.parent.document;
    var anchor=doc.getElementById('rg-insp-anchor');
    if(!anchor) return;
    var col=anchor;
    while(col && col.getAttribute && col.getAttribute('data-testid')!=='column'){col=col.parentElement;}
    if(!col || col._rgFloated) return;
    col._rgFloated=true;
    col.style.position='fixed';
    col.style.right='16px';
    col.style.top='70px';
    col.style.width='240px';
    col.style.maxHeight='calc(100vh - 90px)';
    col.style.overflowY='auto';
    col.style.zIndex='900';
    col.style.background='#0D1929';
    col.style.borderRadius='10px';
    col.style.border='1px solid #1E3050';
    col.style.padding='12px 14px';
    col.style.boxShadow='0 8px 32px rgba(0,0,0,0.6)';
    var hb=col.parentElement;
    if(hb){hb.style.height='0';hb.style.minHeight='0';hb.style.overflow='visible';}
    doc.body.classList.add('rg-insp-active');
  }
  setTimeout(floatInsp,400); setTimeout(floatInsp,1000); setTimeout(floatInsp,2500);
})();
</script>""", height=0)
        st.markdown('<span id="rg-insp-anchor"></span>', unsafe_allow_html=True)

    if tweets_data:
        # Sort by engagement score (likes*2 + replies*3 + retweets)
        tweets_data = sorted(tweets_data, key=lambda t: t.get("likeCount",0)*2 + t.get("replyCount",0)*3 + t.get("retweetCount",0), reverse=True)

        _actions_header = _rg_actions
        done_count = sum(1 for t in tweets_data if t.get("id","") in _actions_header["replied"])
        pending = [t for t in tweets_data if t.get("id","") not in _actions_header["replied"]]

        st.markdown(f'<div style="font-size:13px;color:#666888;margin-bottom:12px;">{done_count} done · {len(pending)} remaining — sorted by engagement</div>', unsafe_allow_html=True)

        # Batch AI Fill All
        if st.button("⚡ AI Fill All", key="rg_ai_fill_all", type="secondary"):
            with st.spinner(f"Generating replies for {len(pending[:10])} tweets..."):
                for t in pending[:10]:
                    acc_ = t.get("_target_account","")
                    text_ = t.get("text","")
                    tid_ = t.get("id","")
                    key_ = f"rg_et_{tweets_data.index(t)}"
                    if not st.session_state.get(key_,"").strip():
                        sug = call_claude(f'Reply to @{acc_}\'s tweet: "{text_[:150]}". Write ONE reply under 150 chars. Match the voice in the system prompt. No emojis.', system=build_user_context(), max_tokens=80)
                        st.session_state[key_] = sug
            st.rerun()

    for i, t in enumerate(tweets_data):
        acc = t.get("_target_account", "")
        text = t.get("text", "")
        tid = t.get("id", "")
        likes = t.get("likeCount", t.get("like_count", 0))
        rts = t.get("retweetCount", t.get("retweet_count", 0))
        rpl = t.get("replyCount", t.get("reply_count", 0))
        views = t.get("viewCount", t.get("view_count", 0))
        created = t.get("createdAt", t.get("created_at", ""))[:16]
        eng_score = likes * 2 + rpl * 3 + rts
        tweet_url = t.get("url", t.get("twitterUrl", f"https://x.com/{acc}/status/{tid}"))

        # Extract media image — extendedEntities.media is the authoritative source
        _ext = t.get("extendedEntities")
        media_list = (_ext.get("media", []) if isinstance(_ext, dict) else None) or t.get("media") or []
        img_url = ""
        _is_video = False
        if isinstance(media_list, list):
            for m in media_list:
                if isinstance(m, dict):
                    _is_video = m.get("type", "photo") in ("video", "animated_gif")
                    img_url = m.get("media_url_https", "")
                    if img_url:
                        break

        _actions = _rg_actions
        et_is_replied = tid in _actions["replied"] or tid in replied_tweets
        et_already_liked = tid in _actions["liked"]

        # Done state — collapsed grey row
        if et_is_replied:
            st.markdown(
                f'<div style="opacity:0.35;padding:10px 16px;border-radius:10px;border:1px solid rgba(255,255,255,0.04);margin:4px 0;display:flex;align-items:center;gap:12px;">'
                f'<span style="color:#4ade80;font-size:16px;">✓</span>'
                f'<span style="color:#666;font-size:13px;text-decoration:line-through;">@{acc} — {text[:80]}...</span>'
                f'</div>',
                unsafe_allow_html=True)
            continue

        et_input_key = f"rg_et_{i}"
        options_key = f"rg_et_opts_{i}"

        # Priority badge color
        score_color = "#4ade80" if eng_score >= 20 else "#2DD4BF" if eng_score >= 5 else "#555577"

        rc1, rc2, rc3 = st.columns([1, 3, 4])
        with rc1:
            st.markdown(
                f'<div style="padding-top:8px;">'
                f'<div style="font-weight:700;color:#2DD4BF;font-size:14px;">@{acc}</div>'
                f'<div style="margin-top:6px;display:inline-block;background:rgba(255,255,255,0.04);border-radius:6px;padding:3px 8px;font-size:12px;color:{score_color};font-weight:600;">⚡ {eng_score}</div>'
                f'</div>',
                unsafe_allow_html=True)
        with rc2:
            st.markdown(
                f'<div style="font-size:15px;color:#d8d8e8;line-height:1.6;">{text[:220]}</div>'
                f'<div style="font-size:11px;color:#555577;margin-top:6px;">{created} · {likes}♡ · {rpl}↩ · {rts}↺</div>'
                f'<a href="{tweet_url}" target="_blank" class="tweet-link">↗ view tweet</a>',
                unsafe_allow_html=True)
            if img_url:
                st.image(img_url, use_container_width=True)
                if _is_video:
                    st.markdown(f'<div style="font-size:11px;color:#888;margin-top:2px;">▶ video — <a href="{tweet_url}" target="_blank" style="color:#2DD4BF;">view on X</a></div>', unsafe_allow_html=True)
        with rc3:
            if st.session_state.get(f"{et_input_key}_p"):
                st.session_state[et_input_key] = st.session_state.pop(f"{et_input_key}_p")
            reply_text = st.text_area("r", key=et_input_key, label_visibility="collapsed",
                placeholder="Write your reply...", height=auto_height(st.session_state.get(et_input_key, "")))

            # AI options picker
            if st.session_state.get(options_key):
                opts = st.session_state[options_key]
                st.markdown('<div style="font-size:11px;color:#666888;margin-bottom:4px;">Pick an option:</div>', unsafe_allow_html=True)
                for oi, opt in enumerate(opts):
                    if st.button(f"{opt[:80]}{'...' if len(opt)>80 else ''}", key=f"rg_opt_{i}_{oi}", use_container_width=True, type="secondary"):
                        st.session_state[f"{et_input_key}_p"] = opt
                        del st.session_state[options_key]
                        st.rerun()

            # Action row — icon dock buttons
            _liked_html = f'<div style="width:40px;height:40px;border-radius:12px;background:rgba(74,222,128,0.1);border:1px solid rgba(74,222,128,0.3);display:flex;align-items:center;justify-content:center;"><span style="color:#4ade80;font-size:16px;">♥</span></div>' if et_already_liked else f'<div class="cs-bot" data-bot="rg_etl_{i}" style="width:40px;height:40px;border-radius:12px;border:1px solid #1a2a45;background:#0a1220;display:flex;align-items:center;justify-content:center;cursor:pointer;"><svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78L12 21.23l8.84-8.84a5.5 5.5 0 000-7.78z" stroke="#5a7090" stroke-width="2"/></svg></div>'
            st.markdown(f'''<div style="display:flex;gap:6px;margin-top:6px;">
              <div class="cs-bot" data-bot="rg_etg_{i}" data-tooltip="Generate AI Reply Suggestion" style="width:40px;height:40px;border-radius:12px;border:1px solid #1a2a45;background:#0a1220;display:flex;align-items:center;justify-content:center;cursor:pointer;">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" stroke="#5a7090" stroke-width="2" stroke-linejoin="round"/></svg>
              </div>
              {_liked_html}
              <div class="cs-bot" data-bot="rg_ets_{i}" data-tooltip="Post Reply To X" style="width:40px;height:40px;border-radius:12px;background:linear-gradient(135deg,#1fb8a8,#2DD4BF);display:flex;align-items:center;justify-content:center;cursor:pointer;">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><line x1="22" y1="2" x2="11" y2="13" stroke="#060A12" stroke-width="2"/><polygon points="22 2 15 22 11 13 2 9 22 2" stroke="#060A12" stroke-width="2"/></svg>
              </div>
              <div class="cs-bot" data-bot="rg_etrd_{i}" data-tooltip="Mark As Handled" style="width:40px;height:40px;border-radius:12px;border:1px solid #1a2a45;background:#0a1220;display:flex;align-items:center;justify-content:center;cursor:pointer;">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none"><polyline points="20 6 9 17 4 12" stroke="#5a7090" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </div>
            </div>''', unsafe_allow_html=True)

            # Hidden buttons for actions
            if st.button(f"rg_etg_{i}", key=f"rg_etg_{i}"):
                with st.spinner(""):
                    raw = call_claude(
                        f'Reply to @{acc}\'s tweet: "{text[:150]}". '
                        f'Write exactly 3 different reply options, each under 150 chars. '
                        f'Match the voice in the system prompt. No emojis. '
                        f'Format: one reply per line, no numbering, no labels.',
                        system=build_user_context(), max_tokens=250)
                    opts = [o.strip() for o in raw.strip().split("\n") if o.strip()][:3]
                    if opts:
                        st.session_state[options_key] = opts
                        if not st.session_state.get(et_input_key,"").strip():
                            st.session_state[f"{et_input_key}_p"] = opts[0]
                st.rerun()
            if not et_already_liked:
                if st.button(f"rg_etl_{i}", key=f"rg_etl_{i}"):
                    _proxy_tweet_action("like", tid)
                    _actions["liked"] = list(set(_actions["liked"] + [tid]))[-500:]
                    _save_actions_gist(_actions)
                    st.rerun()
            if st.button(f"rg_ets_{i}", key=f"rg_ets_{i}"):
                if reply_text.strip() and tid:
                    if _proxy_tweet_action("reply", tid, reply_text.strip()):
                        _bump_reply()
                        progress["count"] = progress.get("count", 0) + 1
                        save_json("reply_progress.json", progress)
                        _actions["replied"] = list(set(_actions["replied"] + [tid]))[-500:]
                        _save_actions_gist(_actions)
                        st.rerun()
                    else:
                        st.error("Reply failed")
            if st.button(f"rg_etrd_{i}", key=f"rg_etrd_{i}"):
                    _bump_reply()
                    progress["count"] = progress.get("count", 0) + 1
                    save_json("reply_progress.json", progress)
                    _actions["replied"] = list(set(_actions["replied"] + [tid]))[-500:]
                    _save_actions_gist(_actions)
                    st.rerun()

        st.markdown('<hr style="margin:6px 0;border-color:rgba(255,255,255,0.04);">', unsafe_allow_html=True)

    # Force rerun if flagged (workaround for st.rerun inside nested columns)
    if st.session_state.pop("rg_force_rerun", False):
        st.rerun()

    # ── Go Viral modal (from Inspiration Engine) ──
    if st.session_state.get("rg_viral_idea"):
        _viral_idea = st.session_state["rg_viral_idea"]
        _viral_fmt = st.session_state.get("rg_viral_fmt", "Normal Tweet")
        _viral_voice = st.session_state.get("rg_viral_voice", "Default")
        st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)
        _vf1, _vf2, _vclose = st.columns([2, 2, 1])
        with _vf1:
            _viral_fmt = st.selectbox("Format", ["Punchy Tweet", "Normal Tweet", "Long Tweet", "Thread", "Article"],
                index=["Punchy Tweet", "Normal Tweet", "Long Tweet", "Thread", "Article"].index(_viral_fmt),
                key="rg_viral_fmt_sel", label_visibility="collapsed")
        with _vf2:
            _viral_voice = st.selectbox("Voice", ["Default", "Critical", "Hype", "Sarcastic"],
                index=["Default", "Critical", "Hype", "Sarcastic"].index(_viral_voice),
                key="rg_viral_voice_sel", label_visibility="collapsed")
        with _vclose:
            if st.button("✕ Close", key="rg_viral_close", use_container_width=True):
                st.session_state.pop("rg_viral_idea", None)
                for _k in ["ci_banger_data", "ci_grades", "ci_result", "ci_repurposed", "ci_preview"]:
                    st.session_state.pop(_k, None)
                st.rerun()
        st.session_state["rg_viral_fmt"] = _viral_fmt
        st.session_state["rg_viral_voice"] = _viral_voice
        with st.spinner("Post Ascend AI is working..."):
            _run_ci_ai("banger", _viral_idea, _viral_fmt, _viral_voice)
        _ci_output_panel(str(time.time()), "banger", _viral_idea, _viral_fmt, _viral_voice)
        st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

    # ── PART 2: My Tweet Replies — Conversation Depth ──
    st.markdown('<div style="font-size:10px;letter-spacing:2px;color:#445;font-weight:700;margin-bottom:10px;">MY TWEET REPLIES</div>', unsafe_allow_html=True)

    for idx, tw in enumerate(st.session_state.get("rg_my_tweets", [])):
        txt = tw.get("text", "")
        likes = tw.get("likeCount", tw.get("like_count", 0))
        rts = tw.get("retweetCount", tw.get("retweet_count", 0))
        rpl = tw.get("replyCount", tw.get("reply_count", 0))
        views = tw.get("viewCount", tw.get("view_count", 0))
        st.markdown(f'<div class="tweet-card" style="border-left:3px solid #2DD4BF;">'
                    f'<div style="color:#2DD4BF;font-size:11px;font-weight:700;letter-spacing:1px;margin-bottom:6px;">YOUR TWEET</div>'
                    f'<div style="color:#e8e8f0;font-size:14px;line-height:1.5;margin-bottom:8px;">{txt}</div>'
                    f'<div style="font-size:11px;color:#666688;">{likes:,} likes | {rts:,} RTs | {rpl:,} replies | {views:,} views</div></div>', unsafe_allow_html=True)

        for ri, rp in enumerate(st.session_state.get(f"rg_replies_{idx}", [])):
            rauthor = rp.get("author", {}).get("userName", rp.get("user", {}).get("screen_name", ""))
            rid = rp.get("id", "")
            rtext = rp.get("text", "")
            r_likes = rp.get("likeCount", rp.get("like_count", 0))
            input_key = f"rg_ri_{idx}_{ri}"
            opts_key = f"rg_ri_opts_{idx}_{ri}"
            reply_url = rp.get("url", rp.get("twitterUrl", f"https://x.com/{rauthor}/status/{rid}"))
            already_liked = rid in liked_tweets_global
            is_replied_now = rid in replied_tweets

            # Done state — collapsed grey row
            if is_replied_now:
                st.markdown(
                    f'<div style="opacity:0.35;padding:10px 16px;border-radius:10px;border:1px solid rgba(255,255,255,0.04);margin:4px 0;display:flex;align-items:center;gap:12px;">'
                    f'<span style="color:#4ade80;font-size:16px;">✓</span>'
                    f'<span style="color:#666;font-size:13px;text-decoration:line-through;">@{rauthor} — {rtext[:80]}...</span>'
                    f'</div>',
                    unsafe_allow_html=True)
                continue

            rc1, rc2, rc3 = st.columns([1, 3, 4])
            with rc1:
                st.markdown(f'<div style="font-weight:700;color:#2DD4BF;font-size:13px;padding-top:8px;">@{rauthor}</div>'
                            f'<div style="font-size:11px;color:#555577;">{r_likes} likes</div>', unsafe_allow_html=True)
            with rc2:
                st.markdown(
                    f'<div style="font-size:14px;color:#d8d8e8;line-height:1.5;">{rtext[:250]}</div>'
                    f'<a href="{reply_url}" target="_blank" class="tweet-link">↗ view tweet</a>',
                    unsafe_allow_html=True)
            with rc3:
                if st.session_state.get(f"{input_key}_p"):
                    st.session_state[input_key] = st.session_state.pop(f"{input_key}_p")
                reply_val = st.text_area("r", key=input_key, label_visibility="collapsed",
                    placeholder="Write reply...", height=auto_height(st.session_state.get(input_key, "")))

                # AI options picker
                if st.session_state.get(opts_key):
                    opts = st.session_state[opts_key]
                    st.markdown('<div style="font-size:11px;color:#666888;margin-bottom:4px;">Pick an option:</div>', unsafe_allow_html=True)
                    for oi, opt in enumerate(opts):
                        if st.button(f"{opt[:80]}{'...' if len(opt)>80 else ''}", key=f"rg_ri_opt_{idx}_{ri}_{oi}", use_container_width=True, type="secondary"):
                            st.session_state[f"{input_key}_p"] = opt
                            del st.session_state[opts_key]
                            st.rerun()

                # Action row — uniform 4-button row
                ab1, ab2, ab3, ab4 = st.columns(4)
                with ab1:
                    if st.button("🤖 AI", key=f"rg_gen_{idx}_{ri}", use_container_width=True, help="Generate 3 reply options"):
                        with st.spinner(""):
                            raw = call_claude(
                                f'Original tweet: "{txt[:200]}"\n\n'
                                f'@{rauthor} replied: "{rtext[:200]}"\n\n'
                                f'Write exactly 3 different reply options. Under 150 chars each. '
                                f'Match the voice in the system prompt. No emojis. '
                                f'One reply per line, no numbering.',
                                system=build_user_context(), max_tokens=250)
                            opts = [o.strip() for o in raw.strip().split("\n") if o.strip()][:3]
                            if opts:
                                st.session_state[opts_key] = opts
                                if not st.session_state.get(input_key, "").strip():
                                    st.session_state[f"{input_key}_p"] = opts[0]
                        st.rerun()
                with ab2:
                    if already_liked:
                        st.markdown('<div style="text-align:center;padding:9px 0;font-size:16px;color:#4ade80;" title="Liked">♥</div>', unsafe_allow_html=True)
                    else:
                        if st.button("♡ Like", key=f"rg_like_{idx}_{ri}", use_container_width=True, help="Like on X"):
                            _proxy_tweet_action("like", rid)
                            _rg_actions["liked"] = list(set(liked_tweets_global + [rid]))[-500:]
                            _save_actions_gist(_rg_actions)
                            st.rerun()
                with ab3:
                    if st.button("↗ Send", key=f"rg_send_{idx}_{ri}", use_container_width=True, help="Send reply via proxy", type="primary"):
                        if reply_val.strip():
                            if _proxy_tweet_action("reply", rid, reply_val.strip()):
                                _bump_reply()
                                _mark_replied(rid)
                                st.rerun()
                            else:
                                st.error("Reply failed — check proxy")
                with ab4:
                    if st.button("✓ Done", key=f"rg_replied_done_{idx}_{ri}", use_container_width=True, help="Mark done (replied on native X)", type="secondary"):
                        _bump_reply()
                        _mark_replied(rid)
                        st.rerun()

            st.markdown('<hr style="margin:6px 0;border-color:rgba(255,255,255,0.04);">', unsafe_allow_html=True)

    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

    # ── Hidden buttons are CSS-hidden; dock clicks wired by global MutationObserver ──

# ═══════════════════════════════════════════════════════════════════════════
# PAGE: INSPIRATION
# ═══════════════════════════════════════════════════════════════════════════
def page_inspiration():
    st.markdown('<div class="main-header">IDEA <span>BANK</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Save tweets that inspire you. Reference them when you need ideas.</div>', unsafe_allow_html=True)
    st.markdown(
        '''<div style="display:flex;justify-content:flex-start;margin:0 0 16px 0;">
            <span class="cs-bot" data-bot="ib_help_video" style="height:52px;padding:0 18px;border-radius:14px;font-size:12px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;border:1px solid rgba(196,158,60,0.45);background:rgba(45,212,191,0.1);color:#C49E3C;cursor:pointer;display:inline-flex;align-items:center;gap:6px;">See How It Works</span>
        </div>''',
        unsafe_allow_html=True,
    )
    if st.button("bot_ib_help_video", key="ib_help_video"):
        _idea_bank_help_dialog()
    st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

    inspo = load_inspiration_gist()

    # Search + Add at top
    search = st.text_input("Search:", placeholder="Filter by keyword or tag...", key="insp_search", label_visibility="collapsed")

    # --- Add button as bottom bar style ---
    st.markdown('''<div class="cs-bottom-bar cs-ib-bottom" style="display:flex;gap:8px;justify-content:center;margin:8px 0 16px;">
      <span class="cs-bot cs-idock-primary" data-bot="ib_add" style="height:52px;padding:0 24px;border-radius:14px;font-size:11px;font-weight:600;background:linear-gradient(135deg,#1fb8a8,#2DD4BF);color:#060A12;cursor:pointer;display:inline-flex;align-items:center;gap:6px;">+ Add to Vault</span>
    </div>''', unsafe_allow_html=True)

    if st.button("ib_add", key="insp_show_add"):
        st.session_state["_ib_show_add"] = True

    # Add form as modal
    if st.session_state.pop("_ib_show_add", False):
        @st.dialog("Add to Vault", width="large")
        def _ib_add_dialog():
            inspo_text = st.text_area("Tweet text:", height=100, key="insp_text",
                placeholder="Paste the tweet that caught your eye...")
            inspo_author = st.text_input("Author:", placeholder="@username", key="insp_author")
            inspo_tags = st.text_input("Tags (comma-separated):", placeholder="hook, thread, broncos", key="insp_tags")
            _mc1, _mc2 = st.columns(2)
            with _mc1:
                inspo_likes = st.text_input("Likes:", value="", placeholder="e.g. 1200", key="insp_likes")
            with _mc2:
                inspo_views = st.text_input("Views:", value="", placeholder="e.g. 45000", key="insp_views")
            if st.button("Bank It", use_container_width=True, key="insp_save", type="primary"):
                if inspo_text.strip():
                    _inspo = load_inspiration_gist()
                    _inspo.append({
                        "text": inspo_text,
                        "author": inspo_author,
                        "tags": [t.strip() for t in inspo_tags.split(",") if t.strip()],
                        "likes": int(inspo_likes) if str(inspo_likes).strip().isdigit() else 0,
                        "views": int(inspo_views) if str(inspo_views).strip().isdigit() else 0,
                        "saved_at": datetime.now().isoformat(),
                    })
                    save_inspiration_gist(_inspo)
                    st.success("Saved to vault.")
                    st.rerun(scope="app")
        _ib_add_dialog()

    # Filter tags as HTML pills
    _all_tags = set()
    for item in inspo:
        for t in item.get("tags", []):
            _all_tags.add(t)
    _all_tags = sorted(_all_tags)[:8]
    if "insp_tag_sel" not in st.session_state:
        st.session_state.insp_tag_sel = ""
    _pon = "height:44px;padding:0 16px;border-radius:14px;font-size:12px;font-weight:600;background:rgba(45,212,191,0.1);border:1px solid rgba(45,212,191,0.4);color:#2DD4BF;cursor:pointer;display:inline-flex;align-items:center;white-space:nowrap;"
    _poff = "height:44px;padding:0 16px;border-radius:14px;font-size:12px;font-weight:600;background:#0e1a2e;border:1px solid #1a2a45;color:#5a7090;cursor:pointer;display:inline-flex;align-items:center;white-space:nowrap;"
    _tags_html = '<div style="display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 12px;">'
    _tags_html += f'<span class="cs-bot" data-bot="insp_tag_all" style="{_pon if not st.session_state.insp_tag_sel else _poff}">All</span>'
    for _ti, _tg in enumerate(_all_tags[:7]):
        _cls = _pon if st.session_state.insp_tag_sel == _tg else _poff
        _tags_html += f'<span class="cs-bot" data-bot="insp_tag_{_ti}" style="{_cls}">{_tg}</span>'
    _tags_html += '</div>'
    st.markdown(_tags_html, unsafe_allow_html=True)

    # Hidden tag buttons
    if st.button("insp_tag_all", key="insp_tag_all"):
        st.session_state.insp_tag_sel = ""
        st.rerun()
    for _ti, _tg in enumerate(_all_tags[:7]):
        if st.button(f"insp_tag_{_ti}", key=f"insp_tag_{_ti}"):
            st.session_state.insp_tag_sel = _tg
            st.rerun()
    tag_filter = st.session_state.insp_tag_sel

    st.markdown('<div style="height:1px;background:#1a2a45;margin:16px 0 14px;"></div>', unsafe_allow_html=True)

    # Vault display
    st.markdown(f'<div style="font-size:9px;font-weight:700;letter-spacing:1.2px;color:#3a5070;text-transform:uppercase;margin-bottom:8px;">Vault ({len(inspo)} saved)</div>', unsafe_allow_html=True)

    filtered = inspo
    if search:
        filtered = [i for i in filtered if search.lower() in i.get("text", "").lower() or search.lower() in i.get("author", "").lower()]
    if tag_filter:
        filtered = [i for i in filtered if tag_filter.lower() in [t.lower() for t in i.get("tags", [])]]

    # Handle delete via query param
    del_idx = st.query_params.get("del_inspo")
    if del_idx is not None:
        try:
            inspo.pop(int(del_idx))
            save_inspiration_gist(inspo)
        except Exception:
            pass
        st.query_params.pop("del_inspo", None)
        st.rerun()

    if not filtered:
        st.markdown('<div class="output-box">No inspiration saved yet. Start collecting posts that hit different.</div>', unsafe_allow_html=True)
    else:
        filtered_with_idx = [(inspo.index(item) if item in inspo else -1, item) for item in reversed(filtered[-20:])]
        for real_idx, item in filtered_with_idx:
            tags_html = " ".join([f'<span class="tag">{t}</span>' for t in item.get("tags", [])])
            metrics = ""
            if item.get("likes"):
                metrics += f"Likes: {item['likes']:,} "
            if item.get("views"):
                metrics += f"Views: {item['views']:,}"
            import urllib.parse as _urlparse
            _ib_encoded = _urlparse.quote(item.get("text", ""), safe="")
            _use_style = "height:44px;padding:0 18px;border-radius:14px;font-size:12px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;background-color:#0a1220;border:1px solid rgba(45,212,191,0.3);color:#2DD4BF;cursor:pointer;display:inline-flex;align-items:center;text-decoration:none;margin-right:6px;"
            _rep_style = "height:44px;padding:0 18px;border-radius:14px;font-size:12px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;background-color:#0a1220;border:1px solid #1a2a45;color:#5a7090;cursor:pointer;display:inline-flex;align-items:center;text-decoration:none;margin-right:6px;"
            _del_style = "height:32px;padding:0 10px;border-radius:10px;font-size:10px;font-weight:600;background:transparent;border:1px solid rgba(248,113,113,0.2);color:rgba(248,113,113,0.5);cursor:pointer;display:inline-flex;align-items:center;text-decoration:none;"
            st.markdown(f"""<div class="tweet-card" style="position:relative;">
                <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
                    <span class="tweet-num">{item.get('author','')}</span>
                    <span style="font-size:11px; color:#444466;">{item.get('saved_at','')[:10]}</span>
                </div>
                <div style="color:#d8d8e8; font-size:14px; margin-bottom:8px; line-height:1.6;">{item.get('text','')}</div>
                <div style="margin-bottom:6px;">{tags_html}</div>
                <div style="font-size:11px; color:#666688; margin-bottom:8px;">{metrics}</div>
                <div style="display:flex;gap:6px;align-items:center;">
                    <a href="/?{_tok_qp}page=Creator+Studio&idea={_ib_encoded}" target="_self" class="cs-bot" style="{_use_style}">USE</a>
                    <a href="/?{_tok_qp}page=Creator+Studio&idea={_ib_encoded}" target="_self" class="cs-bot" style="{_rep_style}">REPURPOSE</a>
                    <a href="?page=Idea+Bank&del_inspo={real_idx}" style="{_del_style}" title="Delete">✕</a>
                </div>
            </div>""", unsafe_allow_html=True)

    # ── Hidden buttons are CSS-hidden; bottom bar clicks wired by global MutationObserver ──


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: SIGNALS & PROMPTS
# ═══════════════════════════════════════════════════════════════════════════

_BEAT_REPORTERS = 'from:mikeklis OR from:bylucaevans OR from:ZacStevensDNVR OR from:AllbrightNFL OR from:TroyRenck OR from:MaseDenver OR from:christomasson OR from:KyleNewmanDP OR from:CodyRoarkNFL OR from:NickOehlerTV OR from:JamieLynchTV OR from:markkiszla OR from:ParkerJGabriel OR from:HarrisonWind OR from:BennettDurando OR from:VBenedetto OR from:chrisadempsey OR from:katywinge OR from:VicLombardi OR from:TJMcBrideNBA OR from:msinger OR from:MooseColorado OR from:DNVR_Nuggets OR from:PeterRBaugh OR from:evanrawal OR from:cmasisak22 OR from:adater OR from:megangley OR from:Jack_Carlough OR from:BrianHowell33 OR from:adamcm777 OR from:SeanKeeler OR from:Danny_Penza OR from:buffzone'
_NATIONAL_QUERY = '(Broncos OR Nuggets OR Avalanche OR "CU Buffs" OR "Bo Nix" OR "Sean Payton" OR "Nikola Jokic" OR "Nathan MacKinnon" OR "Courtland Sutton" OR "Jamal Murray") (from:AdamSchefter OR from:RapSheet OR from:TomPelissero OR from:JayGlazer OR from:AlbertBreer OR from:JeremyFowler OR from:MikeGarafolo OR from:PSchrags OR from:jeffdarlington OR from:DanGrazianoESPN OR from:DMRussini OR from:FieldYates OR from:ProFootballTalk OR from:nflnetwork OR from:NFL OR from:CharlesRobinson OR from:MikeSilver OR from:SiriusXMNFL OR from:ShamsCharania OR from:BrianWindhorst OR from:ChrisBHaynes OR from:TheSteinLine OR from:JakeLFischer OR from:espn OR from:NBAonTNT) -is:retweet'
_SIGNALS_CACHE = {"beat": None, "national": None, "ts": 0, "beat_cursor": "", "nat_cursor": ""}


def _fetch_signals(query, count=30, max_age_hours=48, pages=1, start_cursor=""):
    """Fetch tweets via TwitterAPI.io advanced_search with pagination, filtering stale results.
    Returns (tweets, last_cursor) tuple."""
    if not TWITTER_API_IO_KEY:
        return [], ""
    try:
        from datetime import timedelta, timezone
        all_tweets = []
        cursor = start_cursor
        for _ in range(pages):
            resp = requests.get(
                "https://api.twitterapi.io/twitter/tweet/advanced_search",
                headers={"X-API-Key": TWITTER_API_IO_KEY},
                params={"query": query, "queryType": "Latest", "count": min(count, 100), "cursor": cursor},
                timeout=8,
            )
            if resp.status_code != 200:
                break
            data = resp.json()
            all_tweets.extend(data.get("tweets", []))
            cursor = data.get("next_cursor", "")
            if not cursor:
                break
        # Filter to recent tweets only
        cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
        fresh = []
        for t in all_tweets:
            try:
                created = datetime.strptime(t.get("createdAt", ""), "%a %b %d %H:%M:%S %z %Y")
                if created >= cutoff:
                    fresh.append(t)
            except (ValueError, TypeError):
                pass
        return fresh, cursor
    except Exception:
        pass
    return [], ""


def _relative_time(created_at_str):
    """Convert createdAt to '2m ago', '1h ago', '3d ago'. Handles both Twitter format and ISO."""
    if not created_at_str:
        return "time unknown"
    try:
        from datetime import timezone
        # Twitter format: "Thu Nov 23 03:31:24 +0000 2023"
        try:
            created = datetime.strptime(created_at_str, "%a %b %d %H:%M:%S %z %Y")
        except ValueError:
            # ISO fallback: "2026-03-29T12:00:00Z"
            created = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - created
        secs = int(delta.total_seconds())
        if secs < 0:
            return "just now"
        elif secs < 60:
            return f"{secs}s ago"
        elif secs < 3600:
            return f"{secs // 60}m ago"
        elif secs < 86400:
            return f"{secs // 3600}h ago"
        else:
            return f"{secs // 86400}d ago"
    except Exception:
        return "time unknown"


def _get_trend_pill(topic_keywords):
    """Check tweet volume for timing indicator: Rising / Peak / Fading."""
    if not topic_keywords or not TWITTER_API_IO_KEY:
        return "peak", "Peak"
    try:
        recent, _ = _fetch_signals(topic_keywords, count=10)
        if not recent:
            return "fading", "Fading"
        # Check how many tweets are < 1hr old vs total
        from datetime import timezone
        now = datetime.now(timezone.utc)
        recent_count = 0
        for t in recent[:10]:
            try:
                created = datetime.fromisoformat(t.get("createdAt", "").replace("Z", "+00:00"))
                if (now - created).total_seconds() < 3600:
                    recent_count += 1
            except Exception:
                pass
        ratio = recent_count / max(len(recent[:10]), 1)
        if ratio > 0.5:
            return "rising", "Rising"
        elif ratio > 0.2:
            return "peak", "Peak"
        else:
            return "fading", "Fading"
    except Exception:
        return "peak", "Peak"


_STOP_WORDS = {"the", "a", "an", "is", "are", "was", "were", "in", "on", "at", "to", "for", "of", "and", "or", "with", "this", "that", "from", "by", "has", "have", "had", "his", "her", "its", "will", "be", "been"}

def _dedup_signals(tweets, min_overlap=3):
    """Collapse tweets about the same story, keeping the one with most replies."""
    if not tweets:
        return tweets
    kept = []
    for tw in tweets:
        words = set(w.lower() for w in re.findall(r'[A-Za-z]+', tw.get("text", "")) if len(w) > 2 and w.lower() not in _STOP_WORDS)
        is_dup = False
        for i, (ktw, kwords) in enumerate(kept):
            overlap = len(words & kwords)
            if overlap >= min_overlap:
                # Keep the one with more replies
                if tw.get("replyCount", 0) > ktw.get("replyCount", 0):
                    kept[i] = (tw, words | kwords)
                is_dup = True
                break
        if not is_dup:
            kept.append((tw, words))
    return [tw for tw, _ in kept]


def _quick_sport_tag(text):
    """Fast sport detection from text only — for card display pills."""
    _l = text.lower()
    _nfl = ["broncos", "nfl", "bo nix", "sean payton", "paton", "draft", "football", "owners meetings", "waddle", "sutton"]
    _nba = ["nuggets", "jokic", "jamal murray", "aaron gordon", "nba", "basketball", "halftime", "tipoff"]
    _nhl = ["avalanche", "avs", "mackinnon", "makar", "nhl", "hockey"]
    _cfb = ["buffs", "cu buffs", "deion", "shedeur"]
    scores = {"NFL": sum(1 for s in _nfl if s in _l), "NBA": sum(1 for s in _nba if s in _l),
              "NHL": sum(1 for s in _nhl if s in _l), "CFB": sum(1 for s in _cfb if s in _l)}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else None

_SPORT_PILL_COLORS = {
    "NFL": ("#F97316", "rgba(249,115,22,0.12)"),
    "NBA": ("#3B82F6", "rgba(59,130,246,0.12)"),
    "NHL": ("#06B6D4", "rgba(6,182,212,0.12)"),
    "CFB": ("#A855F7", "rgba(168,85,247,0.12)"),
}

_DENVER_GAMES_CACHE = {"games": None, "ts": 0}

def _get_denver_games_today():
    """Check ESPN for Denver teams playing today. Cached 30 min."""
    if _DENVER_GAMES_CACHE["games"] is not None and (time.time() - _DENVER_GAMES_CACHE["ts"]) < 1800:
        return _DENVER_GAMES_CACHE["games"]
    games = []
    _denver_teams = {
        "nba": {"DEN": "Nuggets"},
        "nhl": {"COL": "Avalanche"},
        "nfl": {"DEN": "Broncos"},
    }
    for league, teams in _denver_teams.items():
        try:
            scores = espn_scores(league, limit=15)
            for g in (scores or []):
                h_abbr = g.get("home", {}).get("abbr", "")
                a_abbr = g.get("away", {}).get("abbr", "")
                for abbr, name in teams.items():
                    if abbr in (h_abbr, a_abbr):
                        opp_abbr = a_abbr if h_abbr == abbr else h_abbr
                        games.append({
                            "league": league.upper(),
                            "team": name,
                            "opponent": opp_abbr,
                            "home": h_abbr == abbr,
                            "completed": g.get("completed", False),
                            "score": f"{g.get('away',{}).get('score','')}-{g.get('home',{}).get('score','')}" if g.get("completed") else None,
                        })
        except Exception:
            pass
    _DENVER_GAMES_CACHE["games"] = games
    _DENVER_GAMES_CACHE["ts"] = time.time()
    return games


def _fetch_parent_tweet(tweet_id):
    """Fetch a single tweet by ID for reply context."""
    if not tweet_id or not TWITTER_API_IO_KEY:
        return None
    try:
        resp = requests.get(
            "https://api.twitterapi.io/twitter/tweets",
            headers={"X-API-Key": TWITTER_API_IO_KEY},
            params={"tweet_ids": str(tweet_id)},
            timeout=8,
        )
        if resp.status_code == 200:
            tweets = resp.json().get("tweets", [])
            return tweets[0] if tweets else None
    except Exception:
        pass
    return None


def _get_thread_context(tweet):
    """Pull parent tweet and quoted tweet text for sport inference."""
    context_texts = []
    # Quoted tweet — already embedded
    qt = tweet.get("quoted_tweet")
    if qt and qt.get("text"):
        qt_author = qt.get("author", {}).get("userName", "")
        context_texts.append(f"@{qt_author}: {qt['text'][:200]}")
    # Reply parent — fetch if needed
    if tweet.get("isReply") and tweet.get("inReplyToId"):
        parent = _fetch_parent_tweet(tweet["inReplyToId"])
        if parent and parent.get("text"):
            p_author = parent.get("author", {}).get("userName", "")
            context_texts.append(f"@{p_author}: {parent['text'][:200]}")
    return context_texts


def _build_signal_brief(tweet):
    """Auto-generate a structured brief from a tweet signal."""
    author = tweet.get("author", {}).get("userName", "") or tweet.get("user", {}).get("screen_name", "")
    text = tweet.get("text", "")
    replies = tweet.get("replyCount", 0)
    rts = tweet.get("retweetCount", 0)
    likes = tweet.get("likeCount", 0)

    # Pull thread context (parent tweet, quoted tweet) for better sport inference
    _thread_ctx = _get_thread_context(tweet)
    _thread_text = " ".join(_thread_ctx)

    # Detect sport from tweet content + thread context — score each sport
    _all_text = (text + " " + _thread_text).lower()
    _sport_signals = {
        "NFL": ["broncos", "nfl", "bo nix", "sean payton", "paton", "football", "draft pick", "free agent", "wide receiver", "quarterback", "offensive line", "defensive", "owners meetings", "combine", "roster", "courtland sutton", "waddle", "dobbins", "touchdown", "super bowl"],
        "NBA": ["nuggets", "jokic", "jamal murray", "aaron gordon", "nba", "basketball", "three pointer", "dunk", "western conference", "halftime", "tipoff"],
        "NHL": ["avalanche", "avs", "mackinnon", "makar", "nhl", "hockey", "stanley cup", "power play", "goalie"],
        "CFB": ["buffs", "cu buffs", "deion", "shedeur", "colorado buffaloes", "big 12"],
    }
    _sport_scores = {}
    for league, signals in _sport_signals.items():
        _sport_scores[league] = sum(1 for s in signals if s in _all_text)

    _sb_skip_sports = is_guest() and "sport" not in load_json("topics.json", {}).get("niche", "").lower()
    _today_playing = _get_denver_games_today() if not _sb_skip_sports else []
    _best_sport = max(_sport_scores, key=_sport_scores.get) if max(_sport_scores.values()) > 0 else None

    if is_guest():
        _topics = load_json("topics.json", {})
        _niche_str = _topics.get("niche", "General").lower()
        _angles = {
            "NFL": f"@{get_current_handle()}'s perspective on football",
            "NBA": f"@{get_current_handle()}'s perspective on basketball",
            "NHL": f"@{get_current_handle()}'s perspective on hockey",
            "CFB": f"@{get_current_handle()}'s perspective on college football",
        }
    else:
        _angles = {
            "NFL": "Tyler's lens as a former professional athlete and Denver media host",
            "NBA": "Tyler's lens as a former professional athlete and Denver media host who watches the Nuggets daily",
            "NHL": "Tyler's lens as a former professional athlete and Denver media host who follows the Avalanche closely",
            "CFB": "Tyler's lens as a former professional athlete and Colorado insider",
        }

    if _best_sport:
        _sport = _best_sport
        _angle = _angles[_sport]
    elif _today_playing:
        _sport = _today_playing[0]["league"]
        _angle = f"{_angles.get(_sport, _angles['NFL'])} — {_today_playing[0]['team']} playing today"
    else:
        _sport = "NFL"
        _angle = _angles["NFL"]

    # Build game context line — only show games matching detected sport
    _game_ctx = ""
    if _today_playing:
        _league_map = {"NFL": "NFL", "NBA": "NBA", "NHL": "NHL", "CFB": "NCAAF"}
        _relevant = [g for g in _today_playing if g["league"] == _league_map.get(_sport, _sport)]
        if _relevant:
            _game_lines = []
            for g in _relevant:
                _status = f"Final {g['score']}" if g["completed"] else ("vs" if g["home"] else "@")
                _game_lines.append(f"{g['team']} {_status} {g['opponent']}")
            _game_ctx = f"\nGAME TODAY: {', '.join(_game_lines)}"

    # Thread context block for the brief
    _ctx_block = ""
    if _thread_ctx:
        _ctx_block = "\nCONTEXT: " + " → ".join(_thread_ctx)

    brief = f"""TOPIC: {text[:280]}
TENSION: @{author} {_sport} take generating {replies} replies — active debate in mentions
KEY STATS: {replies} replies, {rts} RTs, {likes} likes{_game_ctx}{_ctx_block}
ANGLE: {_angle}"""
    return brief


@st.dialog("Signal Brief", width="large")
def _signal_brief_dialog(_nonce):
    """Popup for editing a signal brief, building, and showing results — all in one dialog."""
    brief = st.session_state.get("sig_brief", "")
    if not brief:
        st.warning("No signal selected.")
        return

    # If AI already ran, show results directly
    if st.session_state.get("ci_banger_data") or st.session_state.get("ci_result"):
        fmt = st.session_state.get("_sig_last_fmt", "Normal Tweet")
        voice = st.session_state.get("_sig_last_voice", "Default")
        _ci_output_panel_impl("build", brief, fmt, voice)
        return

    # Show brief + controls
    st.markdown(f'<div style="background:rgba(45,212,191,0.06);border:1px solid rgba(45,212,191,0.15);border-radius:10px;padding:16px;margin-bottom:12px;font-size:12px;color:#b8c8d8;line-height:1.7;white-space:pre-wrap;">{brief}</div>', unsafe_allow_html=True)
    edited_brief = st.text_area("Edit brief:", value=brief, height=160, key="sig_brief_edit")

    _custom_voices = load_json("voice_styles.json", [])
    _voice_opts = ["Default", "Critical", "Hype", "Sarcastic"] + [s["name"] for s in _custom_voices]
    _fmt_opts = ["Punchy Tweet", "Normal Tweet", "Long Tweet", "Thread", "Article"]
    # Use session state defaults so changing voice/format doesn't close dialog
    _v_idx = _voice_opts.index(st.session_state.get("sig_voice", "Default")) if st.session_state.get("sig_voice", "Default") in _voice_opts else 0
    _f_idx = _fmt_opts.index(st.session_state.get("sig_fmt", "Normal Tweet")) if st.session_state.get("sig_fmt", "Normal Tweet") in _fmt_opts else 1
    vc1, vc2 = st.columns(2)
    with vc1:
        sig_voice = st.selectbox("Voice", _voice_opts, index=_v_idx, key="sig_voice")
    with vc2:
        sig_fmt = st.selectbox("Format", _fmt_opts, index=_f_idx, key="sig_fmt")

    if st.button("⊞ Build", use_container_width=True, key="sig_build", type="primary"):
        final_brief = st.session_state.get("sig_brief_edit", edited_brief)
        st.session_state["_sig_last_fmt"] = sig_fmt
        st.session_state["_sig_last_voice"] = sig_voice
        # Clear old results
        for _k in ["ci_banger_data", "ci_result", "ci_viral_data", "ci_grades", "ci_preview"]:
            st.session_state.pop(_k, None)
        # Run AI right here inside the dialog — spinner is visible to user
        with st.spinner("Building your tweets... AI is generating 3 options"):
            _run_ci_ai("build", final_brief, sig_fmt, sig_voice)
        # Signal main page to reopen this dialog with results
        st.session_state["_sig_reopen_with_results"] = True
        st.rerun()


def page_signals_prompts():
    st.markdown('<div class="main-header">SIGNALS <span>& PROMPTS</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Live hot topics auto-generate structured briefs for Creator Studio.</div>', unsafe_allow_html=True)
    st.markdown(
        '''<div style="display:flex;justify-content:flex-start;margin:0 0 16px 0;">
            <span class="cs-bot" data-bot="sig_help_video" style="height:52px;padding:0 18px;border-radius:14px;font-size:12px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;border:1px solid rgba(196,158,60,0.45);background:rgba(45,212,191,0.1);color:#C49E3C;cursor:pointer;display:inline-flex;align-items:center;gap:6px;">See How It Works</span>
        </div>''',
        unsafe_allow_html=True,
    )
    if st.button("bot_sig_help_video", key="sig_help_video"):
        _signals_prompts_help_dialog()
    st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

    # ── Handle incoming signal from Chrome extension URL params ──
    _sig_text = st.query_params.get("sig_text", "")
    if _sig_text:
        _sig_author = st.query_params.get("sig_author", "unknown")
        _sig_replies = st.query_params.get("sig_replies", "0")
        _sig_rts = st.query_params.get("sig_rts", "0")
        _sig_likes = st.query_params.get("sig_likes", "0")
        # Clean up URL params
        for _p in ["sig_text", "sig_author", "sig_replies", "sig_rts", "sig_likes", "sig_url"]:
            if _p in st.query_params:
                del st.query_params[_p]
        # Build a synthetic tweet dict and generate brief
        _ext_tweet = {
            "text": _sig_text,
            "author": {"userName": _sig_author},
            "replyCount": int(_sig_replies),
            "retweetCount": int(_sig_rts),
            "likeCount": int(_sig_likes),
        }
        st.session_state["sig_selected"] = _ext_tweet
        st.session_state["sig_brief"] = _build_signal_brief(_ext_tweet)
        for _k in ["ci_banger_data", "ci_result", "ci_viral_data", "ci_grades", "ci_preview"]:
            st.session_state.pop(_k, None)
        _signal_brief_dialog(str(time.time()))

    # ── Reopen dialog with results after Build ran AI inside dialog ──
    if st.session_state.pop("_sig_reopen_with_results", False):
        _signal_brief_dialog(str(time.time()))

    # ── Handle Redo from Signal Build dialog ──
    if st.session_state.pop("_sig_reopen_result", False):
        _signal_brief_dialog(str(time.time()))

    # ── Tab pills FIRST (render before fetch so page isn't empty) ──
    # Tab pills as HTML
    if "sig_tab" not in st.session_state:
        st.session_state.sig_tab = "Beat"
    _tab_on = "height:44px;padding:0 16px;border-radius:14px;font-size:12px;font-weight:600;background:rgba(45,212,191,0.1);border:1px solid rgba(45,212,191,0.4);color:#2DD4BF;cursor:pointer;display:inline-flex;align-items:center;white-space:nowrap;"
    _tab_off = "height:44px;padding:0 16px;border-radius:14px;font-size:12px;font-weight:600;background:#0e1a2e;border:1px solid #1a2a45;color:#5a7090;cursor:pointer;display:inline-flex;align-items:center;white-space:nowrap;"
    st.markdown(f'''<div style="display:flex;gap:8px;margin:8px 0 16px;">
      <span class="cs-bot" data-bot="sig_tab_beat" style="{_tab_on if st.session_state.sig_tab == 'Beat' else _tab_off}">Beat Reporters</span>
      <span class="cs-bot" data-bot="sig_tab_nat" style="{_tab_off if st.session_state.sig_tab == 'Beat' else _tab_on}">National Takes</span>
    </div>''', unsafe_allow_html=True)
    if st.button("sig_tab_beat", key="sig_tab_beat"):
        st.session_state.sig_tab = "Beat"
        st.rerun()
    if st.button("sig_tab_nat", key="sig_tab_nat"):
        st.session_state.sig_tab = "National"
        st.rerun()

    # ── Fetch signals ──
    _force_refresh = False
    if st.button("sig_next", key="sig_refresh"):
        _force_refresh = True

    _sig_ready_key = "_sig_fetch_ready"
    _cache_ts = st.session_state.get("_sig_cache_ts", 0)
    _has_cached_signals = bool(st.session_state.get("_sig_beat_tweets")) or bool(st.session_state.get("_sig_nat_tweets"))
    _cache_stale = (time.time() - _cache_ts > 300) if _cache_ts else False
    _need_fetch = _force_refresh or (_has_cached_signals and _cache_stale)
    if not _has_cached_signals and not _need_fetch:
        if st.session_state.get(_sig_ready_key):
            _need_fetch = True
        else:
            st.session_state[_sig_ready_key] = True
    if _need_fetch:
        with st.spinner("Scanning Twitter signals..."):
            try:
                _start_beat = st.session_state.get("_sig_beat_cursor", "") if _force_refresh else ""
                _start_nat = st.session_state.get("_sig_nat_cursor", "") if _force_refresh else ""
                _beat, _beat_cur = _fetch_signals(_BEAT_REPORTERS, count=100, pages=3, start_cursor=_start_beat)
                _nat, _nat_cur = _fetch_signals(_NATIONAL_QUERY, count=100, pages=2, max_age_hours=168, start_cursor=_start_nat)
                st.session_state["_sig_beat_tweets"] = _beat
                st.session_state["_sig_nat_tweets"] = _nat
                st.session_state["_sig_beat_cursor"] = _beat_cur
                st.session_state["_sig_nat_cursor"] = _nat_cur
                st.session_state["_sig_cache_ts"] = time.time()
                _save_debug_status("signals_fetch", {
                    "status": "ok",
                    "at": datetime.now().isoformat(timespec="seconds"),
                    "detail": f"beat={len(_beat)} national={len(_nat)}",
                    "force_refresh": bool(_force_refresh),
                })
            except Exception as e:
                _save_debug_status("signals_fetch", {
                    "status": "error",
                    "at": datetime.now().isoformat(timespec="seconds"),
                    "detail": str(e)[:300],
                    "force_refresh": bool(_force_refresh),
                })
                raise

    beat_tweets = _dedup_signals(st.session_state.get("_sig_beat_tweets", []))
    national_tweets = _dedup_signals(st.session_state.get("_sig_nat_tweets", []))
    beat_sorted = sorted(beat_tweets, key=lambda t: t.get("replyCount", 0), reverse=True)[:10]
    national_sorted = sorted(national_tweets, key=lambda t: t.get("retweetCount", 0) + t.get("quoteCount", 0), reverse=True)[:10]

    if not beat_tweets and not national_tweets and st.session_state.get(_sig_ready_key):
        st.markdown('<div style="color:#555778;font-size:13px;padding:0 0 12px 0;">Tap Next Page to load the latest live signals.</div>', unsafe_allow_html=True)

    # ── Signal 1: Beat Reporter Heat Map ──
    if st.session_state.sig_tab == "Beat":
        st.markdown('<div style="font-size:13px;font-weight:700;color:#2DD4BF;letter-spacing:1px;margin-bottom:10px;">BEAT REPORTER HEAT MAP</div>', unsafe_allow_html=True)
        st.markdown('<div style="font-size:10px;color:#3a5070;margin-bottom:12px;">35 Denver beat reporters — ranked by reply count</div>', unsafe_allow_html=True)
        if not beat_sorted:
            st.markdown('<div style="color:#3a5070;font-style:italic;font-size:12px;">No recent tweets from beat reporters.</div>', unsafe_allow_html=True)
        for idx, tw in enumerate(beat_sorted):
            author = tw.get("author", {}).get("userName", "") or "unknown"
            text = tw.get("text", "")[:200]
            replies = tw.get("replyCount", 0)
            rts = tw.get("retweetCount", 0)
            _ago = _relative_time(tw.get("createdAt", ""))
            # Timing pill
            keywords = " ".join(text.split()[:4])
            trend_key, trend_label = _get_trend_pill(keywords) if idx == 0 else ("peak", "Peak")  # Only check timing for top signal to save API calls
            pill_colors = {"rising": ("#10B981", "rgba(16,185,129,0.12)"), "peak": ("#FBBF24", "rgba(251,191,36,0.12)"), "fading": ("#EF4444", "rgba(239,68,68,0.12)")}
            pc, pbg = pill_colors.get(trend_key, pill_colors["peak"])
            _stag = _quick_sport_tag(tw.get("text", ""))
            _spill = ""
            if _stag:
                _sc, _sbg = _SPORT_PILL_COLORS.get(_stag, ("#666888", "rgba(102,104,136,0.12)"))
                _spill = f'<span style="font-size:9px;padding:2px 6px;border-radius:8px;background:{_sbg};color:{_sc};font-weight:600;margin-left:6px;">{_stag}</span>'
            st.markdown(f'''<div class="tweet-card" style="cursor:pointer;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                    <span style="font-size:11px;color:#2DD4BF;font-weight:600;">@{author}{_spill}</span>
                    <span style="font-size:9px;padding:2px 8px;border-radius:8px;background:{pbg};color:{pc};font-weight:600;">{trend_label}</span>
                </div>
                <div style="font-size:14px;color:#d8d8e8;line-height:1.6;">{text}{'...' if len(tw.get('text',''))>200 else ''}</div>
                <div style="margin-top:6px;font-size:10px;color:#666888;">{_ago}{' &middot; ' if _ago else ''}{replies} replies &middot; {rts} RTs</div>
                <span class="cs-bot" data-bot="sig_beat_{idx}" style="margin-top:8px;height:44px;padding:0 16px;border-radius:14px;font-size:12px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;background:#0a1220;border:1px solid #1a2a45;color:#5a7090;cursor:pointer;display:inline-flex;align-items:center;">USE SIGNAL</span>
            </div>''', unsafe_allow_html=True)
            if st.button(f"sig_beat_{idx}", key=f"sig_beat_{idx}"):
                st.session_state["sig_selected"] = tw
                st.session_state["sig_brief"] = _build_signal_brief(tw)
                for _k in ["ci_banger_data", "ci_result", "ci_viral_data", "ci_grades", "ci_preview"]:
                    st.session_state.pop(_k, None)
                _signal_brief_dialog(str(time.time()))

    # ── Signal 2: National Take Detector ──
    if st.session_state.sig_tab == "National":
        st.markdown('<div style="font-size:13px;font-weight:700;color:#C49E3C;letter-spacing:1px;margin-bottom:10px;">NATIONAL TAKE DETECTOR</div>', unsafe_allow_html=True)
        st.markdown('<div style="font-size:10px;color:#3a5070;margin-bottom:12px;">Schefter, Rapoport, Pelissero, Shams, ESPN + 20 more — ranked by RT+QT</div>', unsafe_allow_html=True)
        if not national_sorted:
            st.markdown('<div style="color:#3a5070;font-style:italic;font-size:12px;">No national takes about Denver teams found.</div>', unsafe_allow_html=True)
        for idx, tw in enumerate(national_sorted):
            author = tw.get("author", {}).get("userName", "") or "unknown"
            text = tw.get("text", "")[:200]
            rts = tw.get("retweetCount", 0)
            qts = tw.get("quoteCount", 0)
            replies = tw.get("replyCount", 0)
            _ago = _relative_time(tw.get("createdAt", ""))
            _stag_n = _quick_sport_tag(tw.get("text", ""))
            _spill_n = ""
            if _stag_n:
                _sc_n, _sbg_n = _SPORT_PILL_COLORS.get(_stag_n, ("#666888", "rgba(102,104,136,0.12)"))
                _spill_n = f'<span style="font-size:9px;padding:2px 6px;border-radius:8px;background:{_sbg_n};color:{_sc_n};font-weight:600;margin-right:6px;">{_stag_n}</span>'
            st.markdown(f'''<div class="tweet-card" style="cursor:pointer;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                    <span style="font-size:11px;color:#C49E3C;font-weight:600;">@{author}</span>
                    <div>{_spill_n}<span style="font-size:9px;padding:2px 8px;border-radius:8px;background:rgba(196,158,60,0.12);color:#C49E3C;font-weight:600;">NATIONAL</span></div>
                </div>
                <div style="font-size:14px;color:#d8d8e8;line-height:1.6;">{text}{'...' if len(tw.get('text',''))>200 else ''}</div>
                <div style="margin-top:6px;font-size:10px;color:#666888;">{_ago}{' &middot; ' if _ago else ''}{rts} RTs &middot; {qts} QTs &middot; {replies} replies</div>
                <span class="cs-bot" data-bot="sig_nat_{idx}" style="margin-top:8px;height:44px;padding:0 16px;border-radius:14px;font-size:12px;font-weight:600;letter-spacing:0.04em;text-transform:uppercase;background:#0a1220;border:1px solid #1a2a45;color:#5a7090;cursor:pointer;display:inline-flex;align-items:center;">USE SIGNAL</span>
            </div>''', unsafe_allow_html=True)
            if st.button(f"sig_nat_{idx}", key=f"sig_nat_{idx}"):
                st.session_state["sig_selected"] = tw
                st.session_state["sig_brief"] = _build_signal_brief(tw)
                for _k in ["ci_banger_data", "ci_result", "ci_viral_data", "ci_grades", "ci_preview"]:
                    st.session_state.pop(_k, None)
                _signal_brief_dialog(str(time.time()))

    # ── Next Page dock at bottom ──
    st.markdown('''<div style="height:1px;background:#1a2a45;margin:24px 0 14px;"></div>
    <div class="cs-icon-dock cs-sig-dock" style="display:flex;gap:8px;justify-content:center;margin:8px 0 16px;">
      <div class="cs-idock-btn cs-idock-primary" data-dock="sig_next" style="width:52px;height:52px;border-radius:14px;background:linear-gradient(135deg,#1fb8a8,#2DD4BF);display:flex;align-items:center;justify-content:center;cursor:pointer;position:relative;">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none"><path d="M23 4v6h-6M1 20v-6h6" stroke="#060A12" stroke-width="2"/><path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" stroke="#060A12" stroke-width="2"/></svg>
        <span style="position:absolute;bottom:-20px;font-size:10px;color:#5a7090;white-space:nowrap;letter-spacing:0.04em;font-weight:600;">NEXT PAGE</span>
      </div>
    </div>''', unsafe_allow_html=True)

    # ── Hidden buttons are CSS-hidden; dock clicks wired by global MutationObserver ──
    import streamlit.components.v1 as _sig_stc
    _sig_stc.html("""<script>
    (function(){
      var doc=window.parent.document;
      function wire(){
        var btns=doc.querySelectorAll('button');
        var hideLabels=['sig_next'];
        for(var i=0;i<btns.length;i++){
          if(hideLabels.indexOf(btns[i].textContent.trim())!==-1){
            var el=btns[i].closest('[data-testid="stElementContainer"]')||btns[i].parentElement.parentElement;
            el.style.cssText='position:absolute;width:0;height:0;overflow:hidden;padding:0;margin:0;border:0;opacity:0;pointer-events:none;';
          }
        }
        doc.querySelectorAll('.cs-sig-dock .cs-idock-btn').forEach(function(d){
          if(d._w2) return; d._w2=true;
          d.addEventListener('click',function(){
            var action=d.dataset.dock;
            for(var i=0;i<btns.length;i++){
              if(btns[i].textContent.trim()===action){btns[i].removeAttribute('disabled');btns[i].click();return;}
            }
          });
        });
      }
      setTimeout(wire,500);setTimeout(wire,1500);setTimeout(wire,3000);
    })();
    </script>""", height=0)


def _mask_debug_value(value: str, keep: int = 4) -> str:
    if not value:
        return "missing"
    if len(value) <= keep * 2:
        return "*" * len(value)
    return f"{value[:keep]}...{value[-keep:]}"


def _debug_has_secret(name: str) -> bool:
    try:
        return bool(st.secrets.get(name, ""))
    except Exception:
        return False


def _debug_exists(path_str: str) -> bool:
    return Path(os.path.expanduser(path_str)).exists()


def _debug_count_json_list(filename: str) -> int:
    try:
        data = load_json(filename, [])
        return len(data) if isinstance(data, list) else 0
    except Exception:
        return 0


def _debug_events_path() -> Path:
    return get_data_dir() / "debug_events.json"


def _debug_status_path() -> Path:
    return get_data_dir() / "debug_status.json"


def _load_debug_status() -> dict:
    path = _debug_status_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_debug_status(key: str, payload: dict):
    try:
        state = _load_debug_status()
        state[key] = payload
        _debug_status_path().write_text(json.dumps(state, indent=2, default=str))
    except Exception:
        pass


def _load_debug_events() -> list:
    path = _debug_events_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _append_debug_event(kind: str, status: str, detail: str, meta: dict | None = None):
    try:
        events = _load_debug_events()
        events.append({
            "at": datetime.now().isoformat(timespec="seconds"),
            "kind": kind,
            "status": status,
            "detail": detail[:300],
            "meta": meta or {},
        })
        _debug_events_path().write_text(json.dumps(events[-60:], indent=2, default=str))
    except Exception:
        pass


def _debug_file_info(filename: str) -> dict:
    path = get_data_dir() / filename
    info = {"file": filename, "exists": path.exists(), "count": "", "updated": ""}
    if path.exists():
        try:
            info["updated"] = datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
        except Exception:
            pass
        try:
            payload = json.loads(path.read_text())
            if isinstance(payload, list):
                info["count"] = len(payload)
            elif isinstance(payload, dict):
                info["count"] = len(payload.keys())
        except Exception:
            info["count"] = "invalid json"
    return info


def _get_build_info() -> dict:
    import platform
    info = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "cwd": os.getcwd(),
        "now": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            info["git_sha"] = result.stdout.strip()
    except Exception:
        pass
    for env_key in ["STREAMLIT_SERVER_PORT", "STREAMLIT_RUNTIME", "HOSTNAME"]:
        if os.environ.get(env_key):
            info[env_key.lower()] = os.environ.get(env_key)
    return info


def _get_proxy_health_debug() -> dict:
    import urllib.request
    proxy_url = _get_proxy_url()
    if not proxy_url:
        return {"ok": False, "error": "No proxy URL configured"}
    try:
        req = urllib.request.Request(
            f"{proxy_url.rstrip('/')}/health",
            headers={"ngrok-skip-browser-warning": "1"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return {"ok": True, "proxy_url": proxy_url, "data": data}
    except Exception as e:
        return {"ok": False, "proxy_url": proxy_url, "error": str(e)}


def _run_owner_ai_probe() -> dict:
    started = time.time()
    result = {
        "at": datetime.now().isoformat(timespec="seconds"),
        "model": "claude-sonnet-4-6",
    }
    try:
        text = call_claude("Reply with exactly: DEBUG_OK", system="You are terse.", max_tokens=12, model="claude-sonnet-4-6")
        result["ok"] = True
        result["text"] = text.strip()
        result["route"] = st.session_state.get("_ai_last_route", "unknown")
        result["provider"] = st.session_state.get("_ai_last_provider", "unknown")
        result["source"] = st.session_state.get("_ai_last_source", "unknown")
    except Exception as e:
        result["ok"] = False
        result["error"] = str(e)
    result["elapsed_s"] = round(time.time() - started, 2)
    result["proxy_health"] = _get_proxy_health_debug()
    _append_debug_event("probe", "ok" if result.get("ok") else "error", "live_ai_probe", {
        "route": result.get("route", ""),
        "provider": result.get("provider", ""),
        "elapsed_s": result.get("elapsed_s", 0),
    })
    return result


def _run_debug_test_suite() -> list:
    results = []

    proxy_health = _get_proxy_health_debug()
    results.append({
        "test": "Proxy health",
        "status": "ok" if proxy_health.get("ok") else "error",
        "detail": proxy_health.get("proxy_url", "") if proxy_health.get("ok") else proxy_health.get("error", "unknown"),
    })

    try:
        probe = _run_owner_ai_probe()
        results.append({
            "test": "AI route",
            "status": "ok" if probe.get("ok") else "error",
            "detail": probe.get("route", probe.get("error", "unknown")),
        })
    except Exception as e:
        results.append({"test": "AI route", "status": "error", "detail": str(e)})

    try:
        info = fetch_user_info(get_current_handle())
        detail = f"@{info.get('userName', '')}" if info.get("userName") else "no user payload"
        results.append({"test": "Twitter API", "status": "ok" if info.get("userName") else "error", "detail": detail})
    except Exception as e:
        results.append({"test": "Twitter API", "status": "error", "detail": str(e)})

    try:
        gist_id = st.secrets.get("GIST_ID", "")
        resp = requests.get(f"https://api.github.com/gists/{gist_id}", headers=_gist_headers(), timeout=8)
        ok = resp.status_code == 200
        results.append({"test": "Gist read", "status": "ok" if ok else "error", "detail": f"HTTP {resp.status_code}"})
    except Exception as e:
        results.append({"test": "Gist read", "status": "error", "detail": str(e)})

    try:
        gist_id = st.secrets.get("GIST_ID", "")
        payload = json.dumps({
            "files": {
                "hq_debug_probe.json": {
                    "content": json.dumps({"last_probe_at": datetime.now().isoformat(timespec="seconds")})
                }
            }
        })
        resp = requests.patch(f"https://api.github.com/gists/{gist_id}", data=payload, headers=_gist_headers(), timeout=8)
        ok = resp.status_code == 200
        results.append({"test": "Gist write", "status": "ok" if ok else "error", "detail": f"HTTP {resp.status_code}"})
    except Exception as e:
        results.append({"test": "Gist write", "status": "error", "detail": str(e)})

    try:
        tweet_count = _debug_count_json_list("tweet_history.json")
        status = "ok" if tweet_count >= 20 else "warn"
        results.append({"test": "Tweet history data", "status": status, "detail": f"{tweet_count} records"})
    except Exception as e:
        results.append({"test": "Tweet history data", "status": "error", "detail": str(e)})

    _append_debug_event("suite", "ok", "debug_test_suite", {"results": results})
    return results


def page_debug_console():
    if not is_owner():
        st.warning("Owner access required.")
        return

    st.markdown('<div class="main-header">DEBUG <span>CONSOLE</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Owner-only visibility into routing, services, runtime state, and live backend probes.</div>', unsafe_allow_html=True)
    st.markdown(
        '''<div style="display:flex;justify-content:flex-start;margin:0 0 16px 0;">
            <span class="cs-bot" data-bot="dbg_help_video" style="height:52px;padding:0 18px;border-radius:14px;font-size:12px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase;border:1px solid rgba(196,158,60,0.45);background:rgba(45,212,191,0.1);color:#C49E3C;cursor:pointer;display:inline-flex;align-items:center;gap:6px;">See How It Works</span>
        </div>''',
        unsafe_allow_html=True,
    )
    if st.button("bot_dbg_help_video", key="dbg_help_video"):
        _debug_console_help_dialog()
    st.markdown('<div style="height:12px;"></div>', unsafe_allow_html=True)

    b1, b2 = st.columns(2)
    with b1:
        if st.button("Run Live AI Probe", type="primary", use_container_width=True, key="debug_run_probe"):
            with st.spinner("Running live AI probe..."):
                st.session_state["_debug_last_probe"] = _run_owner_ai_probe()
    with b2:
        if st.button("Run Backend Test Suite", use_container_width=True, key="debug_run_suite"):
            with st.spinner("Running backend tests..."):
                st.session_state["_debug_test_suite"] = _run_debug_test_suite()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Auth Role", st.session_state.get("auth_role", "unknown"))
    c2.metric("Current Page", st.session_state.get("current_page", "unknown"))
    c3.metric("Handle", get_current_handle() or "n/a")
    c4.metric("Tweet History", f"{_debug_count_json_list('tweet_history.json'):,}")

    debug_status = _load_debug_status()
    tweet_sync_status = debug_status.get("tweet_sync", {})
    signals_fetch_status = debug_status.get("signals_fetch", {})
    proxy_health = _get_proxy_health_debug()
    last_route = st.session_state.get("_ai_last_route", "no AI call yet")
    last_route_at = st.session_state.get("_ai_last_at", "")
    card1, card2 = st.columns(2)
    with card1:
        st.markdown(
            f"""<div style="background:#0D1929;border:1px solid #1E3050;border-radius:12px;padding:14px 16px;margin:6px 0 10px;">
            <div style="font-size:11px;letter-spacing:1.4px;color:#6B8AAA;text-transform:uppercase;margin-bottom:8px;">Last Tweet Sync</div>
            <div style="font-size:18px;font-weight:700;color:#E2E8F0;">{tweet_sync_status.get('status', 'unknown').upper()}</div>
            <div style="font-size:12px;color:#9FB0C2;margin-top:6px;">{tweet_sync_status.get('detail', 'No sync recorded')}</div>
            <div style="font-size:11px;color:#6E7681;margin-top:6px;">{tweet_sync_status.get('at', 'No timestamp')}</div>
            </div>""",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""<div style="background:#0D1929;border:1px solid #1E3050;border-radius:12px;padding:14px 16px;margin:0 0 10px;">
            <div style="font-size:11px;letter-spacing:1.4px;color:#6B8AAA;text-transform:uppercase;margin-bottom:8px;">Last Signals Fetch</div>
            <div style="font-size:18px;font-weight:700;color:#E2E8F0;">{signals_fetch_status.get('status', 'unknown').upper()}</div>
            <div style="font-size:12px;color:#9FB0C2;margin-top:6px;">{signals_fetch_status.get('detail', 'No signal fetch recorded')}</div>
            <div style="font-size:11px;color:#6E7681;margin-top:6px;">{signals_fetch_status.get('at', 'No timestamp')}</div>
            </div>""",
            unsafe_allow_html=True,
        )
    with card2:
        st.markdown(
            f"""<div style="background:#0D1929;border:1px solid #1E3050;border-radius:12px;padding:14px 16px;margin:6px 0 10px;">
            <div style="font-size:11px;letter-spacing:1.4px;color:#6B8AAA;text-transform:uppercase;margin-bottom:8px;">Last AI Route</div>
            <div style="font-size:18px;font-weight:700;color:#E2E8F0;">{str(last_route).upper()}</div>
            <div style="font-size:12px;color:#9FB0C2;margin-top:6px;">{st.session_state.get('_ai_last_provider', 'unknown')} / {st.session_state.get('_ai_last_source', 'unknown')}</div>
            <div style="font-size:11px;color:#6E7681;margin-top:6px;">{last_route_at or 'No timestamp'}</div>
            </div>""",
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""<div style="background:#0D1929;border:1px solid #1E3050;border-radius:12px;padding:14px 16px;margin:0 0 10px;">
            <div style="font-size:11px;letter-spacing:1.4px;color:#6B8AAA;text-transform:uppercase;margin-bottom:8px;">Proxy Health</div>
            <div style="font-size:18px;font-weight:700;color:#E2E8F0;">{'OK' if proxy_health.get('ok') else 'DOWN'}</div>
            <div style="font-size:12px;color:#9FB0C2;margin-top:6px;">{proxy_health.get('proxy_url', proxy_health.get('error', 'No proxy URL'))}</div>
            <div style="font-size:11px;color:#6E7681;margin-top:6px;">Anthropic blocked: {bool(anthropic_get_state().get('blocked_until', 0) > time.time())}</div>
            </div>""",
            unsafe_allow_html=True,
        )

    s1, s2 = st.columns(2)
    with s1:
        st.markdown("### Pipeline Status")
        st.dataframe([
            {
                "pipeline": "Tweet sync",
                "status": tweet_sync_status.get("status", "unknown"),
                "at": tweet_sync_status.get("at", ""),
                "detail": tweet_sync_status.get("detail", ""),
                "mode": tweet_sync_status.get("mode", ""),
            },
            {
                "pipeline": "Signals fetch",
                "status": signals_fetch_status.get("status", "unknown"),
                "at": signals_fetch_status.get("at", ""),
                "detail": signals_fetch_status.get("detail", ""),
                "mode": "force" if signals_fetch_status.get("force_refresh") else "normal",
            },
        ], use_container_width=True, hide_index=True)
    with s2:
        st.markdown("### Quick Checks")
        st.dataframe([
            {"check": "Signals cache age (s)", "value": round(max(0, time.time() - st.session_state.get("_sig_cache_ts", 0)), 1) if st.session_state.get("_sig_cache_ts") else "missing"},
            {"check": "Signals beat cache", "value": len(st.session_state.get("_sig_beat_tweets", []))},
            {"check": "Signals national cache", "value": len(st.session_state.get("_sig_nat_tweets", []))},
            {"check": "Recent debug events", "value": len(_load_debug_events())},
        ], use_container_width=True, hide_index=True)

    st.markdown("### AI Routing")
    anthropic_state = anthropic_get_state()
    ai_rows = [
        {"item": "Primary model", "value": st.session_state.get("_ai_last_model", "claude-sonnet-4-6"), "notes": "default app model"},
        {"item": "Last route used", "value": st.session_state.get("_ai_last_route", "no AI call yet"), "notes": st.session_state.get("_ai_last_provider", "")},
        {"item": "Last route source", "value": st.session_state.get("_ai_last_source", "unknown"), "notes": st.session_state.get("_ai_last_at", "")},
        {"item": "Last AI error", "value": st.session_state.get("_ai_last_error", "") or "none", "notes": ""},
        {"item": "Anthropic blocked", "value": str(bool(anthropic_state.get("blocked_until", 0) > time.time())), "notes": anthropic_state.get("source", "")},
        {"item": "Anthropic last error", "value": anthropic_state.get("last_error", "") or "none", "notes": ""},
        {"item": "Proxy health", "value": "ok" if proxy_health.get("ok") else "down", "notes": proxy_health.get("proxy_url", "")},
    ]
    st.dataframe(ai_rows, use_container_width=True, hide_index=True)

    last_probe = st.session_state.get("_debug_last_probe")
    if last_probe:
        with st.expander("Last live probe", expanded=True):
            st.json(last_probe)
    if proxy_health.get("ok"):
        with st.expander("Proxy health payload", expanded=False):
            st.json(proxy_health.get("data", {}))
    elif proxy_health.get("error"):
        st.error(f"Proxy health failed: {proxy_health['error']}")

    suite_results = st.session_state.get("_debug_test_suite")
    if suite_results:
        st.markdown("### Backend Test Suite")
        st.dataframe(suite_results, use_container_width=True, hide_index=True)

    st.markdown("### Service Checks")
    service_rows = [
        {"service": "Anthropic refresh secret", "status": _debug_has_secret("CLAUDE_REFRESH_TOKEN")},
        {"service": "Proxy URL secret", "status": _debug_has_secret("CLAUDE_PROXY_URL")},
        {"service": "Proxy key secret", "status": _debug_has_secret("CLAUDE_PROXY_KEY")},
        {"service": "GitHub PAT", "status": _debug_has_secret("GITHUB_PAT")},
        {"service": "Gist ID", "status": _debug_has_secret("GIST_ID")},
        {"service": "Twitter API key", "status": _debug_has_secret("TWITTER_API_IO_KEY") or bool(TWITTER_API_IO_KEY)},
        {"service": "Perplexity key", "status": _debug_has_secret("PERPLEXITY_API_KEY")},
        {"service": "Odds key", "status": _debug_has_secret("ODDS_API_KEY")},
        {"service": "News API key", "status": _debug_has_secret("NEWSAPI_KEY")},
        {"service": "Local Claude creds", "status": _debug_exists("~/.claude/.credentials.json")},
        {"service": "Local Codex auth", "status": _debug_exists("~/.codex/auth.json")},
    ]
    st.dataframe(service_rows, use_container_width=True, hide_index=True)

    st.markdown("### Runtime State")
    runtime_rows = [
        {"item": "Data dir", "value": str(get_data_dir())},
        {"item": "Proxy URL", "value": proxy_health.get("proxy_url") or _get_proxy_url() or "missing"},
        {"item": "Auth token", "value": _mask_debug_value(st.session_state.get("_auth_token", ""))},
        {"item": "Auth username", "value": st.session_state.get("auth_username", "") or "owner"},
        {"item": "OAuth last error", "value": st.session_state.get("_oauth_last_error", "") or "none"},
        {"item": "Signals beat cache", "value": str(len(st.session_state.get("_sig_beat_tweets", [])))},
        {"item": "Signals national cache", "value": str(len(st.session_state.get("_sig_nat_tweets", [])))},
        {"item": "Idea bank count", "value": str(_debug_count_json_list("inspiration.json"))},
    ]
    st.dataframe(runtime_rows, use_container_width=True, hide_index=True)

    st.markdown("### Deploy Info")
    st.json(_get_build_info())

    st.markdown("### Data Health")
    data_rows = [
        _debug_file_info("tweet_history.json"),
        _debug_file_info("saved_ideas.json"),
        _debug_file_info("saved_articles.json"),
        _debug_file_info("brain_dumps.json"),
        _debug_file_info("coach_conversations.json"),
        _debug_file_info("reply_progress.json"),
        _debug_file_info("voice_styles.json"),
        _debug_file_info("topics.json"),
        _debug_file_info("benchmarks.json"),
        _debug_file_info("voice_fingerprint.json"),
    ]
    st.dataframe(data_rows, use_container_width=True, hide_index=True)

    st.markdown("### Recent Debug Events")
    recent_events = list(reversed(_load_debug_events()[-20:]))
    if recent_events:
        st.dataframe(recent_events, use_container_width=True, hide_index=True)
    else:
        st.caption("No debug events recorded yet.")

    with st.expander("Session state snapshot", expanded=False):
        snapshot = {}
        for key in sorted(st.session_state.keys()):
            value = st.session_state.get(key)
            if "token" in key.lower() or "password" in key.lower():
                snapshot[key] = _mask_debug_value(str(value))
            else:
                snapshot[key] = str(value)
        st.json(snapshot)

    with st.expander("Query params", expanded=False):
        masked_qp = {}
        for key, value in st.query_params.items():
            masked_qp[key] = _mask_debug_value(str(value)) if key == "token" else value
        st.json(masked_qp)


# ═══════════════════════════════════════════════════════════════════════════
# ROUTE TO PAGES
# ═══════════════════════════════════════════════════════════════════════════
page_map = {
    "Raw Thoughts": page_brain_dump,
    "Creator Studio": page_compose_ideas,
    "Content Coach": page_content_coach,
    "Article Writer": page_article_writer,
    "Post History": page_tweet_history,
    "Algorithm Score": page_algo_analyzer,
    "Account Audit": page_health_check,
    "My Stats": page_account_pulse,
    "Profile Analyzer": page_account_researcher,
    "Reply Mode": page_reply_guy,
    "Idea Bank": page_inspiration,
}
if is_owner():
    page_map["Signals & Prompts"] = page_signals_prompts
if is_owner():
    page_map["Debug Console"] = page_debug_console

st.markdown("""<div class="main-watermark">
  <svg width="80" height="70" viewBox="0 0 100 88" fill="none">
    <polygon points="18,82 42,40 50,54 30,82" fill="#2DD4BF"/>
    <polygon points="42,40 50,54 58,40" fill="#0D1E36"/>
    <polygon points="58,40 70,82 50,54 82,82" fill="#2DD4BF" opacity="0.75"/>
    <polygon points="42,40 50,26 58,40" fill="#C49E3C"/>
  </svg>
</div>""", unsafe_allow_html=True)

st.markdown("""<div class="pa-brand-bar">
  <svg width="22" height="19" viewBox="0 0 100 88" fill="none"><polygon points="18,82 42,40 50,54 30,82" fill="#2DD4BF"/><polygon points="42,40 50,54 58,40" fill="#0D1E36"/><polygon points="58,40 70,82 50,54 82,82" fill="#2DD4BF" opacity="0.75"/><polygon points="42,40 50,26 58,40" fill="#C49E3C"/></svg>
  <span class="pa-brand-text">POST <span>ASCEND</span></span>
</div>""", unsafe_allow_html=True)

page_fn = page_map.get(page)
if page_fn:
    page_fn()

_footer_handle = get_current_handle()
if is_guest():
    st.markdown(f"""
<div class="hq-footer">
  <a href="https://x.com/{_footer_handle}" target="_blank">@{_footer_handle}</a>
</div>
""", unsafe_allow_html=True)
else:
    st.markdown(f"""
<div class="hq-footer">
  <a href="https://x.com/{_footer_handle}" target="_blank">@{_footer_handle}</a>
  <span style="color:#1E3050;">|</span>
  <span style="font-family:'Bebas Neue',sans-serif;letter-spacing:2px;color:#4a5160;font-size:12px;">POST <span style="color:#2DD4BF;">ASCEND</span></span>
</div>
""", unsafe_allow_html=True)

# Reveal everything now that all content is rendered.
st.markdown("""<style>
[data-testid="stSidebar"]{opacity:1!important;pointer-events:auto!important}
.stApp [data-testid="stAppViewContainer"]{opacity:1!important}
</style>""", unsafe_allow_html=True)

# Tweet sync — skipped on first render so login is instant.
# Runs on the SECOND rerun (any widget click after page loads).
if st.session_state.get("auth_role"):
    if st.session_state.get("_tweet_sync_ready"):
        if "_tweet_sync_done" not in st.session_state:
            st.session_state["_tweet_sync_done"] = True
            try:
                sync_tweet_history(quick=True)
            except Exception:
                pass
    else:
        st.session_state["_tweet_sync_ready"] = True
