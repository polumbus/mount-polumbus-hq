import streamlit as st
import subprocess
import json
import re
import os
import time
import uuid
import requests
import tomli
from datetime import datetime, timedelta
from pathlib import Path

# ─── Page Config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Mount Polumbus HQ",
    page_icon="mountain",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Constants ──────────────────────────────────────────────────────────────
CLAUDE_CLI = "/home/polfam/.npm-global/bin/claude"
XURL = "/home/linuxbrew/.linuxbrew/bin/xurl"
DATA_DIR = Path(os.path.expanduser("~/.openclaw/workspace-omaha/data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

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

TYLER_HANDLE = "tyler_polumbus"

# ─── Tyler's Voice System Prompt ─────────────────────────────────────────────
TYLER_CONTEXT = """You are a content assistant for Tyler Polumbus — former NFL offensive lineman, Super Bowl 50 champion with the Denver Broncos, and current sports media personality.

Tyler's profile:
- Played 8 NFL seasons as an undrafted free agent, started 60+ games
- Host of The PhD Show on Altitude 92.5 radio (Denver)
- Runs Mount Polumbus podcast/YouTube channel
- Colorado native, deep Denver sports loyalist
- Covers Broncos (primary ~80% of content), Nuggets, Avalanche, CU Buffs
- 42K+ followers on X (@tyler_polumbus)
- Communication style: direct, blunt, no fluff, former-player perspective, knows the game from inside the trenches

Tyler's voice on X:
- Short punchy sentences. Never sounds like a press release.
- Uses "we" when talking Broncos — it's personal
- Hot takes that have teeth — backed by real football knowledge
- Doesn't hedge. If he thinks something, he says it.
- Occasional humor but never tries too hard
- Knows X-specific hooks: numbers, provocative openers, "unpopular opinion" frames
- Never uses emojis unless it's the fire emoji or a sport-specific one
- Threads are rare but devastating when used
- Keeps tweets under 200 characters when possible for max punch

Denver sports context:
- Broncos: Always relevant, always rebuilding faith post-Super Bowl 50
- Nuggets: Back-to-back runs, Jokic era content is premium
- Avalanche: Stanley Cup window, Nathan MacKinnon era
- CU Buffs: Deion Sanders era is must-cover content

IMPORTANT: Never use emojis in your output. Write plain text only."""

# ─── Styles ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;600&display=swap');

/* ── Reset & base ── */
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; font-size: 15px; }
#MainMenu { visibility: hidden; }
header[data-testid="stHeader"] { display: none !important; }
footer { visibility: hidden; }
.stApp { background: radial-gradient(ellipse at 20% 0%, #0e0620 0%, #06061a 40%, #080c10 100%); color: #e8e8f0; }
.block-container { max-width: 1280px !important; padding-top: 1.5rem !important; }

/* ── Sidebar ── */
section[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #07071e 0%, #06060f 60%, #050508 100%) !important;
  border-right: 1px solid rgba(255,183,0,0.12) !important;
}
section[data-testid="stSidebar"] .stButton > button {
  background: transparent !important; border: none !important; color: #7878a0 !important;
  text-align: left !important; padding: 7px 14px !important; font-size: 13px !important;
  font-weight: 400 !important; box-shadow: none !important; border-radius: 10px !important;
  transition: all 0.15s ease !important;
}
section[data-testid="stSidebar"] .stButton > button:hover {
  background: rgba(255,255,255,0.05) !important; color: #e8e8f0 !important;
  transform: none !important; box-shadow: none !important;
}
section[data-testid="stSidebar"] .stButton > button[kind="primary"] {
  background: rgba(255,107,0,0.1) !important; color: #FF6B00 !important;
  font-weight: 600 !important; border-left: 2px solid #FF6B00 !important;
  border-radius: 0 10px 10px 0 !important; border-top: none !important;
  border-right: none !important; border-bottom: none !important;
  box-shadow: none !important;
}
section[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover {
  transform: none !important; box-shadow: none !important;
  background: rgba(255,107,0,0.15) !important;
}

/* ── Logo ── */
.logo-block { padding: 8px 0 20px 0; text-align: center; }
.logo-title { font-family: 'Bebas Neue', sans-serif; font-size: 28px; letter-spacing: 3px; background: linear-gradient(135deg, #FF6B00, #FFB347); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; line-height: 1; display: block; }
.logo-sub { font-size: 10px; color: #2d2d44; letter-spacing: 4px; text-transform: uppercase; margin-top: 4px; display: block; }

/* ── Sidebar nav section labels ── */
.nav-section {
  font-size: 9px; color: #FF6B00; letter-spacing: 3px; text-transform: uppercase;
  font-weight: 700; margin: 20px 0 6px 4px; padding-top: 14px;
  border-top: 1px solid rgba(255,183,0,0.15);
  opacity: 0.7;
}

/* ── Page headers ── */
.main-header {
  font-family: 'Bebas Neue', sans-serif; font-size: 52px; letter-spacing: 3px;
  line-height: 1; margin-bottom: 2px; font-weight: 400;
}
.main-header span {
  background: linear-gradient(135deg, #FF6B00 0%, #FFB347 60%, #ffcc70 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
  text-shadow: none; filter: drop-shadow(0 0 18px rgba(255,107,0,0.35));
}
.tool-desc { color: #555778; font-size: 13px; margin-bottom: 28px; letter-spacing: 0.3px; }

/* ── Buttons — base ── */
.stButton > button {
  border-radius: 100px !important;
  font-family: 'DM Sans', sans-serif !important; font-weight: 600 !important;
  font-size: 13px !important; padding: 9px 22px !important;
  transition: all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1) !important;
  letter-spacing: 0.3px; white-space: nowrap !important;
}
/* PRIMARY (type="primary") — filled orange */
.stButton > button[kind="primary"] {
  background: linear-gradient(135deg, #FF6B00, #d94f00) !important;
  color: white !important; border: none !important;
  box-shadow: 0 2px 16px rgba(255,107,0,0.2) !important;
}
.stButton > button[kind="primary"]:hover {
  transform: translateY(-2px) scale(1.02) !important;
  box-shadow: 0 8px 28px rgba(255,107,0,0.45) !important;
  background: linear-gradient(135deg, #ff7a14, #e05500) !important;
  border: none !important; color: white !important;
}
/* SECONDARY/DEFAULT — ghost outlined */
.stButton > button[kind="secondary"] {
  background: transparent !important;
  border: 1px solid rgba(255,107,0,0.45) !important;
  color: #FF8C3A !important; box-shadow: none !important;
}
.stButton > button[kind="secondary"]:hover {
  background: rgba(255,107,0,0.08) !important;
  border-color: rgba(255,107,0,0.8) !important;
  color: #FF6B00 !important; transform: translateY(-1px) !important;
  box-shadow: 0 4px 16px rgba(255,107,0,0.15) !important;
}

/* ── Output box ── */
.output-box {
  background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.06);
  border-left: 3px solid #FF6B00; border-radius: 14px; padding: 20px 22px;
  margin: 12px 0; font-size: 14px; line-height: 1.75; color: #d0d0e8;
  white-space: pre-wrap; font-family: 'DM Sans', sans-serif;
}

/* ── Tweet / idea cards ── */
.tweet-card {
  background: rgba(255,255,255,0.018); border: 1px solid rgba(255,255,255,0.055);
  border-left: 3px solid rgba(255,183,0,0.25); border-radius: 14px;
  padding: 16px 20px; margin: 8px 0; position: relative;
  transition: all 0.2s ease;
}
.tweet-card:hover {
  border-color: rgba(255,107,0,0.35); border-left-color: #FF6B00;
  background: rgba(255,107,0,0.025);
  box-shadow: 0 4px 20px rgba(0,0,0,0.3);
  transform: translateY(-1px);
}
.tweet-num { font-family: 'Bebas Neue', sans-serif; font-size: 13px; color: #FF6B00; letter-spacing: 1px; margin-bottom: 8px; }

/* ── Stat cards ── */
.stat-card {
  background: rgba(255,255,255,0.025); border: 1px solid rgba(255,255,255,0.06);
  border-radius: 18px; padding: 20px; text-align: center; transition: all 0.2s ease;
}
.stat-card:hover { border-color: rgba(255,183,0,0.3); box-shadow: 0 4px 20px rgba(0,0,0,0.25); }
.stat-num { font-family: 'Bebas Neue', sans-serif; font-size: 42px; color: #FF6B00; line-height: 1; }
.stat-label { font-size: 11px; color: #404060; text-transform: uppercase; letter-spacing: 2px; margin-top: 4px; }

/* ── Tags ── */
.tag { display: inline-block; background: rgba(255,183,0,0.07); border: 1px solid rgba(255,183,0,0.2); border-radius: 100px; padding: 2px 10px; font-size: 10px; color: #aa9966; margin: 2px; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase; }
.tag-hot { background: rgba(255,107,0,0.12); color: #FF6B00; border-color: rgba(255,107,0,0.3); }

/* ── Inputs ── */
.stTextArea textarea, .stTextInput input {
  background: #0a0a18 !important; border: 1px solid rgba(255,255,255,0.08) !important;
  border-radius: 12px !important; color: #e8e8f0 !important;
  font-family: 'DM Sans', sans-serif !important; font-size: 14px !important;
  transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
  padding-bottom: 10px !important;
}
.stTextArea textarea:focus, .stTextInput input:focus {
  border-color: rgba(255,183,0,0.5) !important;
  box-shadow: 0 0 0 3px rgba(255,183,0,0.07), 0 0 20px rgba(255,107,0,0.06) !important;
  outline: none !important;
}
.stTextArea textarea { min-height: 60px !important; resize: vertical !important; }

/* ── Selectbox ── */
.stSelectbox > div > div { background: #0a0a18 !important; border-color: rgba(255,255,255,0.08) !important; color: #e8e8f0 !important; border-radius: 12px !important; }

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] { background: rgba(255,255,255,0.025) !important; border: 1px solid rgba(255,255,255,0.05); border-radius: 12px; gap: 2px; padding: 4px; }
.stTabs [data-baseweb="tab"] { background: transparent !important; color: #555778 !important; border-radius: 10px !important; font-weight: 600 !important; font-size: 13px !important; transition: all 0.15s ease !important; }
.stTabs [aria-selected="true"] { background: #FF6B00 !important; color: white !important; }
.stSpinner > div > div { border-top-color: #FF6B00 !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.07); border-radius: 10px; }
::-webkit-scrollbar-thumb:hover { background: rgba(255,107,0,0.35); }

/* ── Misc ── */
.section-divider { border: none; border-top: 1px solid rgba(255,255,255,0.04); margin: 28px 0; }
.metric-label { font-size: 12px; color: #8888aa; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; }
.metric-score { font-family: 'Bebas Neue', sans-serif; font-size: 18px; color: #FF6B00; }
.score-bar-wrap { background: rgba(255,255,255,0.04); border-radius: 100px; height: 6px; width: 100%; margin: 6px 0 12px; overflow: hidden; }
.score-bar-fill { height: 100%; border-radius: 100px; transition: width 0.8s ease; }
.char-count { font-size: 12px; color: #404060; text-align: right; margin-top: -10px; margin-bottom: 10px; }
.char-over { color: #ef4444 !important; }
.tweet-link { font-size: 11px; color: #4ecdc4; text-decoration: none; letter-spacing: 0.5px; opacity: 0.8; }
.tweet-link:hover { opacity: 1; }

/* ── Chat ── */
.chat-msg { border-radius: 14px; padding: 20px 24px; margin: 12px 0; }
.chat-user { background: rgba(255,255,255,0.02); border-left: 2px solid rgba(255,255,255,0.08); }
.chat-ai { background: rgba(255,107,0,0.04); border-left: 3px solid #FF6B00; }
.chat-role { font-size: 10px; color: #404060; font-weight: 700; text-transform: uppercase; letter-spacing: 2.5px; margin-bottom: 10px; }

/* ── Progress ── */
.progress-bar-bg { background: rgba(255,255,255,0.05); border-radius: 100px; height: 12px; width: 100%; overflow: hidden; }
.progress-bar-fill { height: 100%; border-radius: 100px; background: linear-gradient(90deg, #C49E3C, #E8C84A); transition: width 0.5s; }

/* ── Watermark ── */
.main-watermark {
  position: fixed; bottom: 60px; right: 40px; z-index: 0; pointer-events: none;
  font-family: 'Bebas Neue', sans-serif; font-size: 120px; letter-spacing: 8px;
  color: rgba(255,107,0,0.03); line-height: 1; user-select: none;
  background: linear-gradient(135deg, rgba(255,107,0,0.05), rgba(255,183,0,0.02));
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}

/* ── Branded footer ── */
.hq-footer {
  text-align: center; padding: 24px 0 8px 0; margin-top: 40px;
  border-top: 1px solid rgba(255,183,0,0.1);
}
.hq-footer a { color: #FF6B00; text-decoration: none; font-size: 12px; letter-spacing: 1.5px; font-weight: 600; text-transform: uppercase; opacity: 0.7; margin: 0 12px; }
.hq-footer a:hover { opacity: 1; }

/* ── Number inputs — dark theme ── */
input[type="number"] {
  background: #0a0a18 !important; border: 1px solid rgba(255,255,255,0.08) !important;
  color: #e8e8f0 !important; border-radius: 8px !important;
}
input[type="number"]::-webkit-inner-spin-button,
input[type="number"]::-webkit-outer-spin-button { opacity: 0.4; }

/* ── Stat card — no wrapping ── */
.stat-num { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 32px !important; }

/* ── Progress bar ── */
.progress-bar-bg { background: rgba(255,255,255,0.1) !important; height: 14px !important; }

/* ── Day card (weekly grid) ── */
.day-card {
  background: rgba(255,255,255,0.025); border: 1px solid rgba(255,255,255,0.05);
  border-radius: 10px; padding: 10px 4px; text-align: center;
}
.day-card-label { color: #888; font-size: 10px; text-transform: uppercase; letter-spacing: 1px; }
.day-card-num { color: #fff; font-size: 22px; font-weight: 700; font-family: 'Bebas Neue', sans-serif; line-height: 1.2; }
.day-card-active .day-card-num { color: #FF6B00; }

/* ── Manage app button ── */
[data-testid="manage-app-button"] { display: none !important; }
[data-testid="stToolbarActions"] { display: none !important; }
.stDeployButton { display: none !important; }

/* ── Reduce bottom dead space ── */
.block-container { padding-bottom: 2rem !important; }
.main > div { padding-bottom: 0 !important; }

/* ── Slider ── */
.stSlider .st-br { background: #FF6B00 !important; }

/* ── Mobile ── */
@media (max-width: 768px) {
  .main-header { font-size: 34px !important; }
  .stat-num { font-size: 28px !important; }
  .main-watermark { display: none; }
  .stButton > button { padding: 7px 14px !important; font-size: 12px !important; }
}
</style>
""", unsafe_allow_html=True)


# ─── Helpers ────────────────────────────────────────────────────────────────
def get_voice_context():
    """Build Tyler's voice context from his actual tweet history (default voice only)."""
    tweets = load_json("tweet_history.json", [])
    if not tweets:
        return TYLER_CONTEXT

    # Get top 15 tweets by engagement as voice examples
    top = sorted(tweets, key=lambda t: t.get("likeCount", 0) + t.get("retweetCount", 0) * 3, reverse=True)[:15]
    examples = "\n".join([f"- {t.get('text', '')}" for t in top if not t.get("text", "").startswith("RT ")])

    return TYLER_CONTEXT + f"""

TYLER'S ACTUAL TOP-PERFORMING TWEETS (use these as voice/style reference):
{examples}

Match this exact voice, tone, sentence structure, and style in everything you write.

Note: Format-specific rules (character limits, structure, thread formatting, article layout) will be provided separately. Follow those format rules for structure while maintaining this voice."""


def get_system_for_voice(voice_name: str, voice_mod: str) -> str:
    """Return the right system prompt for the selected voice mode.

    For Default: uses Tyler's actual top-tweet examples (anchors to his natural style).
    For Critical/Homer/Sarcastic: uses Tyler's background + mode-specific example tweets.
    Passing top-tweet examples for non-default modes locks the model onto default voice —
    that's the bug this function fixes.
    """
    if voice_name == "Default":
        return get_voice_context()

    # For non-default voices: Tyler's profile/background only (no top-tweet examples),
    # plus concrete example tweets that show exactly what this voice sounds like.
    voice_examples = {
        "Critical": """EXAMPLES OF TYLER WRITING IN CRITICAL VOICE (copy this exact energy):
- "We passed on 52% of third downs last year and went 8-9. Meanwhile, Kansas City ran on 3rd-and-short 74% of the time and won the Super Bowl. This isn't complicated."
- "The Broncos have had 5 different offensive coordinators in 8 years. And we keep wondering why the offense looks confused. Connect the dots."
- "Bo Nix threw for 3,000 yards last season. Good. But 18 of those touchdowns came against teams with bottom-10 defenses. Test him against real competition before crowning him."
- "I played 8 years in this league. I know what accountability looks like. What I'm watching right now isn't it."

CRITICAL VOICE RULES:
- Always open with a SPECIFIC number, stat, or named failure — never a vague complaint
- Call out exactly what isn't working and why it costs the team
- End with a pointed question or hard truth that makes people think
- Tone: disappointed former player, not an angry fan. Calm and credible, not emotional.""",

        "Homer": """EXAMPLES OF TYLER WRITING IN HOMER VOICE (copy this exact energy):
- "I've been in enough winning locker rooms to know what this feels like. This Broncos team has it. Watch the film. The energy is different this year."
- "Sean Payton has been to this rodeo before. We have the right coach. The pieces are falling into place. We're not done building."
- "Jokic dropped 30, 12, and 10 last night. On a Tuesday. For fun. We are watching the greatest basketball player alive right now. Appreciate it."
- "Everyone's counting us out. Good. That's when this team plays its best ball. Trust the process. We're not done."

HOMER VOICE RULES:
- Always use "we" or "this team" — the reader is part of the belief
- Ground optimism in something SPECIFIC (a player name, a stat, a moment) — not generic hype
- End with forward momentum or something to look forward to
- Tone: infectious, grounded confidence. Earned optimism, not blind cheerleading.""",

        "Sarcastic": """EXAMPLES OF TYLER WRITING IN SARCASTIC VOICE (copy this exact energy):
- "Oh interesting. The Broncos addressed the offensive line by signing a 32-year-old guard. That's definitely the move."
- "Sure, let's rank the Broncos as a bottom-10 team again. Ignore the offseason. Ignore the draft. Same prediction as every year. Bold take."
- "Cool, another week of people discovering the Nuggets are really good. Jokic casually averages a triple double and somehow everyone is shocked. Every. Single. Season."
- "Oh great. Another hot take about how the Broncos need to rebuild. Very original. Never heard that one before."

SARCASTIC VOICE RULES:
- Open with flat, understated acknowledgment: 'Oh interesting.', 'Sure.', 'Cool.', 'Oh great.', 'Wild.' — pick the one that fits
- State the obvious as if calmly explaining something absurd to someone who doesn't see it
- The punchline lands through UNDERSTATEMENT, not anger. Deadpan, not mean.
- End with one dry observation — don't explain the joke.""",
    }

    examples_for_mode = voice_examples.get(voice_name, "")
    if examples_for_mode:
        return TYLER_CONTEXT + f"""

{examples_for_mode}

{voice_mod}

IMPORTANT: Write ONLY in the voice mode above. Do NOT fall back to Tyler's typical default voice."""

    # Custom account voice style
    custom_styles = load_json("voice_styles.json", [])
    for style in custom_styles:
        if style.get("name") == voice_name:
            handle = style.get("handle", "")
            summary = style.get("summary", "")
            tweets = style.get("tweets", [])
            tweet_block = "\n".join([f'- "{t}"' for t in tweets[:10]])
            return TYLER_CONTEXT + f"""

You are writing AS TYLER POLUMBUS but in the STYLE of @{handle}.

THEIR VOICE PROFILE:
{summary}

EXAMPLE TWEETS FROM @{handle} (match this energy, not Tyler's default voice):
{tweet_block}

STYLE RULES:
- Adopt @{handle}'s tone, rhythm, and formatting approach
- Keep Tyler's former-player credibility and sports authority
- Write about Tyler's topics (Broncos, Nuggets, sports) in @{handle}'s voice
- Do NOT copy their exact tweets — channel the style

{voice_mod}

IMPORTANT: Write in @{handle}'s STYLE as described above."""

    return TYLER_CONTEXT


def analyze_personal_patterns():
    """Analyze Tyler's tweet history to build personal scoring benchmarks."""
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

    top_ex    = "\n".join([f'  - "{ex["text"][:120]}" ({ex["likes"]} likes, {ex["rts"]} RTs, {ex["replies"]} replies)' for ex in top_pool[:8]])
    bottom_ex = "\n".join([f'  - "{ex["text"][:120]}" ({ex["likes"]} likes)' for ex in patterns.get("bottom_examples", [])[:5]])
    reply_ex  = "\n".join([f'  - "{ex["text"][:120]}" ({ex["replies"]} replies, {ex["likes"]} likes)' for ex in patterns.get("top_reply_examples", [])[:5]])
    first_words = ", ".join(patterns.get("top_first_words", [])[:10])
    opt_range = patterns.get("optimal_char_range", (0, 280))

    return f"""
TYLER'S PERSONAL TWEET BENCHMARKS (from his actual tweet history):

Character Length:
- Top tweets average {patterns.get("top_avg_chars", 0)} characters
- Sweet spot: {opt_range[0]}–{opt_range[1]} characters (25th–75th percentile of top performers)

Style Patterns (top performers):
- {patterns.get("top_ellipsis_pct", 0)}% use ellipsis (...) vs {patterns.get("bottom_ellipsis_pct", 0)}% in bottom tweets
- {patterns.get("top_question_pct", 0)}% end with a question vs {patterns.get("bottom_question_pct", 0)}% in bottom tweets
- Average {patterns.get("top_linebreaks_avg", 0)} line breaks per top tweet
- Common first words in top tweets: {first_words}

Engagement Averages:
- Average likes: {patterns.get("avg_likes", 0)}
- Average RTs: {patterns.get("avg_rts", 0)}
- Average replies: {patterns.get("avg_replies", 0)}
- Average views: {patterns.get("avg_views", 0)}

{pool_label}:
{top_ex}

Bottom 5 Performing Tweets (avoid these patterns):
{bottom_ex}

Top Reply-Getters (conversation starters):
{reply_ex}
"""


def auto_height(text, min_h=80, chars_per_line=55, line_h=22):
    """Calculate text_area height based on content length."""
    if not text:
        return min_h
    lines = text.count('\n') + 1
    char_lines = max(1, len(text) // chars_per_line)
    total = max(lines, char_lines) + 4  # +4 lines of padding so text isn't flush with bottom
    return max(min_h, total * line_h)


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
    with urllib.request.urlopen(req, timeout=15) as resp:
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
        with urllib.request.urlopen(req, timeout=120) as resp:
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
            with _ur.urlopen(req, timeout=10) as resp:
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


def _call_claude_proxy(prompt: str, system: str, max_tokens: int) -> str:
    """Call local Claude proxy server (for Streamlit Cloud — uses CLI on Tyler's machine)."""
    import urllib.request, urllib.error
    proxy_url = _get_proxy_url()
    if not proxy_url:
        raise Exception("No proxy configured")
    try:
        proxy_key = st.secrets.get("CLAUDE_PROXY_KEY", "")
    except Exception:
        proxy_key = ""

    body = json.dumps({"prompt": prompt, "system": system, "max_tokens": max_tokens}).encode()
    headers = {"Content-Type": "application/json", "ngrok-skip-browser-warning": "1"}
    if proxy_key:
        headers["X-Proxy-Key"] = proxy_key
    req = urllib.request.Request(f"{proxy_url.rstrip('/')}/call", data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=130) as resp:
        data = json.loads(resp.read())
    if "error" in data:
        raise Exception(data["error"])
    return data["text"]


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
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read())
        return data.get("ok", False)
    except Exception:
        # Fall back to local xurl if available
        if os.path.exists(XURL):
            cmd = [XURL, action, tweet_id] + ([text] if text else [])
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            return result.returncode == 0
        return False


def call_claude(prompt: str, system: str = None, max_tokens: int = 1500) -> str:
    if system is None:
        system = get_voice_context()

    # Try local CLI first (fastest when running locally)
    if os.path.exists(CLAUDE_CLI):
        try:
            full_prompt = f"{system}\n\n{prompt}" if system else prompt
            result = subprocess.run(
                [CLAUDE_CLI, "-p", "--model", "claude-sonnet-4-6"],
                input=full_prompt, capture_output=True, text=True, timeout=120,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass

    # Try proxy server (Streamlit Cloud path — calls Tyler's local machine via ngrok)
    try:
        return _call_claude_proxy(prompt, system or "", max_tokens)
    except Exception as e:
        return f"Proxy error: {str(e)[:150]}"


def _gist_headers():
    pat = st.secrets.get("GITHUB_PAT", "") or os.environ.get("HQ_GITHUB_PAT", "")
    return {"Authorization": f"Bearer {pat}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28", "Content-Type": "application/json"}

def load_inspiration_gist() -> list:
    try:
        gist_id = st.secrets.get("GIST_ID", "15fb167bbbfdaa79d5ce11c266c3f652")
        resp = requests.get(f"https://api.github.com/gists/{gist_id}", headers=_gist_headers(), timeout=10)
        data = resp.json()
        if "hq_inspiration.json" in data.get("files", {}):
            return json.loads(data["files"]["hq_inspiration.json"]["content"])
    except Exception:
        pass
    return []

def save_inspiration_gist(items: list):
    try:
        gist_id = st.secrets.get("GIST_ID", "15fb167bbbfdaa79d5ce11c266c3f652")
        payload = json.dumps({"files": {"hq_inspiration.json": {"content": json.dumps(items, indent=2, default=str)}}})
        requests.patch(f"https://api.github.com/gists/{gist_id}", data=payload, headers=_gist_headers(), timeout=10)
    except Exception:
        pass


def _load_actions_gist() -> dict:
    """Load liked/replied tweet ID sets from Gist."""
    if "_actions_cache" in st.session_state:
        return st.session_state["_actions_cache"]
    try:
        gist_id = st.secrets.get("GIST_ID", "15fb167bbbfdaa79d5ce11c266c3f652")
        resp = requests.get(f"https://api.github.com/gists/{gist_id}", headers=_gist_headers(), timeout=10)
        data = resp.json()
        content = data.get("files", {}).get("hq_actions.json", {}).get("content", "{}")
        result = json.loads(content)
    except Exception:
        result = {}
    result.setdefault("liked", [])
    result.setdefault("replied", [])
    st.session_state["_actions_cache"] = result
    return result


def _save_actions_gist(actions: dict):
    """Persist liked/replied IDs to Gist so they survive Streamlit restarts."""
    st.session_state["_actions_cache"] = actions
    try:
        gist_id = st.secrets.get("GIST_ID", "15fb167bbbfdaa79d5ce11c266c3f652")
        payload = json.dumps({"files": {"hq_actions.json": {"content": json.dumps(actions, indent=2)}}})
        requests.patch(f"https://api.github.com/gists/{gist_id}", data=payload, headers=_gist_headers(), timeout=5)
    except Exception:
        pass


def load_json(filename: str, default=None):
    path = DATA_DIR / filename
    if path.exists():
        try:
            return json.loads(path.read_text())
        except Exception:
            pass
    return default if default is not None else []


def save_json(filename: str, data):
    path = DATA_DIR / filename
    path.write_text(json.dumps(data, indent=2, default=str))


def fetch_tweets(query: str, count: int = 50) -> list:
    if not TWITTER_API_IO_KEY:
        return []
    try:
        resp = requests.get(
            "https://api.twitterapi.io/twitter/tweet/advanced_search",
            headers={"X-API-Key": TWITTER_API_IO_KEY},
            params={"query": query, "queryType": "Latest", "cursor": ""},
            timeout=30,
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
            timeout=15,
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


# ─── Sidebar Navigation ────────────────────────────────────────────────────
NAV_ITEMS = {
    "CREATE": [
        ("Creator Studio", "bulb"),
        ("Raw Thoughts", "pencil2"),
        ("Content Advisor", "speech_balloon"),
        ("Article Writer", "memo"),
    ],
    "INTERACT": [
        ("Reply Mode", "left_speech_bubble"),
        ("Idea Bank", "sparkles"),
    ],
    "INSIGHTS": [
        ("Post History", "clock3"),
        ("Algorithm Score", "bar_chart"),
        ("Account Audit", "stethoscope"),
        ("My Stats", "chart_with_upwards_trend"),
        ("Profile Analyzer", "mag"),
    ],
}

NAV_ICONS = {
    "Raw Thoughts": "✏️", "Creator Studio": "💡", "Content Advisor": "💬", "Article Writer": "📝",
    "Post History": "🕐", "Algorithm Score": "📊", "Account Audit": "🩺", "My Stats": "📈",
    "Profile Analyzer": "🔍", "Reply Mode": "🗨️", "Idea Bank": "✨",
}

if "current_page" not in st.session_state:
    st.session_state.current_page = st.query_params.get("page", "Creator Studio")

with st.sidebar:
    st.markdown("""
    <div class="logo-block">
        <span class="logo-title">MOUNT POLUMBUS</span>
        <span class="logo-sub">Content HQ</span>
    </div>
    """, unsafe_allow_html=True)

    for section, items in NAV_ITEMS.items():
        st.markdown(f'<div class="nav-section">{section}</div>', unsafe_allow_html=True)
        for name, _ in items:
            icon = NAV_ICONS.get(name, "")
            is_active = st.session_state.current_page == name
            if st.button(f"{icon}  {name}", key=f"nav_{name}",
                        use_container_width=True,
                        type="primary" if is_active else "secondary"):
                st.session_state.current_page = name
                st.query_params["page"] = name
                st.rerun()


page = st.session_state.current_page


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: BRAIN DUMP
# ═══════════════════════════════════════════════════════════════════════════
def page_brain_dump():
    st.markdown('<div class="main-header">RAW <span>THOUGHTS</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Set a timer, dump your thoughts, turn them into content.</div>', unsafe_allow_html=True)

    # Timer
    if "bd_timer_end" not in st.session_state:
        st.session_state.bd_timer_end = None
    if "bd_timer_mins" not in st.session_state:
        st.session_state.bd_timer_mins = 0

    tcols = st.columns([1, 1, 1, 1, 2])
    for i, mins in enumerate([5, 10, 15, 30]):
        with tcols[i]:
            if st.button(f"{mins} min", key=f"timer_{mins}", use_container_width=True):
                st.session_state.bd_timer_end = time.time() + mins * 60
                st.session_state.bd_timer_mins = mins

    with tcols[4]:
        if st.session_state.bd_timer_end:
            remaining = max(0, st.session_state.bd_timer_end - time.time())
            m, s = divmod(int(remaining), 60)
            if remaining > 0:
                st.markdown(f'<div class="stat-card"><div class="stat-num">{m:02d}:{s:02d}</div><div class="stat-label">Remaining</div></div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="stat-card"><div class="stat-num" style="color:#22c55e;">DONE</div><div class="stat-label">Time\'s up</div></div>', unsafe_allow_html=True)

    col_main, col_saved = st.columns([2, 1])

    with col_main:
        dump_text = st.text_area("Drop your raw thoughts:", height=200,
            placeholder="Whatever is in your head -- game reaction, hot take, rant, observation...",
            key="bd_text")

        bc1, bc2, bc3, bc4 = st.columns(4)
        with bc1:
            if st.button("⚡ Subject", use_container_width=True, key="bd_subject", type="primary"):
                with st.spinner("Thinking..."):
                    result = call_claude("Give Tyler ONE specific content subject to write about right now. Denver sports. One sentence. Be specific and timely.", max_tokens=150)
                    st.session_state["bd_subject_result"] = result
        with bc2:
            if st.button("⚡ Ideas", use_container_width=True, key="bd_ideas", type="primary"):
                if dump_text.strip():
                    with st.spinner("Generating ideas..."):
                        result = call_claude(f'Tyler brain-dumped this:\n\n"{dump_text}"\n\nGenerate 5 specific content ideas from this brain dump. Each should be a different angle or format. Number them.', max_tokens=600)
                        st.session_state["bd_ideas_result"] = result
        with bc3:
            if st.button("↓ Save", use_container_width=True, key="bd_save"):
                if dump_text.strip():
                    dumps = load_json("brain_dumps.json", [])
                    dumps.append({"text": dump_text, "saved_at": datetime.now().isoformat(), "timer_mins": st.session_state.bd_timer_mins})
                    save_json("brain_dumps.json", dumps)
                    st.success("Saved.")
        with bc4:
            if st.button("↺ New", use_container_width=True, key="bd_new"):
                st.session_state.bd_timer_end = None
                st.session_state.bd_timer_mins = 0
                for k in ["bd_subject_result", "bd_ideas_result", "bd_tweets", "bd_longform", "bd_video"]:
                    st.session_state.pop(k, None)
                st.rerun()

        if st.session_state.get("bd_subject_result"):
            st.markdown(f'<div class="output-box">{st.session_state["bd_subject_result"]}</div>', unsafe_allow_html=True)
        if st.session_state.get("bd_ideas_result"):
            st.markdown(f'<div class="output-box">{st.session_state["bd_ideas_result"]}</div>', unsafe_allow_html=True)

        st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

        # Generation sections — open by default so they're discoverable
        with st.expander("Tweet Ideas", expanded=True):
            if st.button("⚡ Generate Tweets", key="bd_gen_tweets", type="primary"):
                if dump_text.strip():
                    with st.spinner("Generating tweets..."):
                        result = call_claude(f'Tyler brain-dumped:\n\n"{dump_text}"\n\nWrite 5 tweet options from this. Each under 220 characters. Different angles and hooks. Number them. No hashtags. No emojis.', max_tokens=500)
                        st.session_state["bd_tweets"] = result
            if st.session_state.get("bd_tweets"):
                st.markdown(f'<div class="output-box">{st.session_state["bd_tweets"]}</div>', unsafe_allow_html=True)

        with st.expander("Long-form Post Idea", expanded=True):
            if st.button("⚡ Generate Long-form", key="bd_gen_long", type="primary"):
                if dump_text.strip():
                    with st.spinner("Generating..."):
                        result = call_claude(f'Tyler brain-dumped:\n\n"{dump_text}"\n\nWrite a long-form X post (400-600 characters) that digs deeper into this topic. Tyler\'s voice: authoritative, from the trenches, direct. Include a strong opening hook.', max_tokens=500)
                        st.session_state["bd_longform"] = result
            if st.session_state.get("bd_longform"):
                st.markdown(f'<div class="output-box">{st.session_state["bd_longform"]}</div>', unsafe_allow_html=True)

        with st.expander("Video Script Outline", expanded=True):
            if st.button("⚡ Generate Outline", key="bd_gen_video", type="primary"):
                if dump_text.strip():
                    with st.spinner("Generating..."):
                        result = call_claude(f'Tyler brain-dumped:\n\n"{dump_text}"\n\nCreate a 3-5 minute video script outline:\n- Cold open hook (15 seconds)\n- 3-4 main talking points with bullet notes\n- Closing line / CTA\n\nKeep it conversational. Tyler talks like a former player, not a news anchor.', max_tokens=600)
                        st.session_state["bd_video"] = result
            if st.session_state.get("bd_video"):
                st.markdown(f'<div class="output-box">{st.session_state["bd_video"]}</div>', unsafe_allow_html=True)

    with col_saved:
        st.markdown("### Saved Thoughts")
        dumps = load_json("brain_dumps.json", [])
        if not dumps:
            st.markdown('<div class="output-box">No Raw Thoughts</div>', unsafe_allow_html=True)
        else:
            for i, d in enumerate(reversed(dumps[-20:])):
                ts = d.get("saved_at", "")[:16].replace("T", " ")
                preview = d.get("text", "")[:120]
                timer_info = f" ({d.get('timer_mins', '?')}m)" if d.get('timer_mins') else ""
                st.markdown(f"""<div class="tweet-card">
                    <div class="tweet-num">{ts}{timer_info}</div>
                    <div style="color:#d8d8e8; font-size:13px;">{preview}{'...' if len(d.get('text','')) > 120 else ''}</div>
                </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: COMPOSE IDEAS
# ═══════════════════════════════════════════════════════════════════════════
def page_compose_ideas():
    st.markdown('<div class="main-header">CREATOR <span>STUDIO</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Draft, refine, and save your content ideas.</div>', unsafe_allow_html=True)

    _RESULT_KEYS = ["ci_banger_data", "ci_grades", "ci_result", "ci_repurposed", "ci_preview", "ci_viral_data"]

    # on_click callbacks for Use buttons — sets ci_text BEFORE widget re-renders (no crash)
    def _use_option(opt_key):
        val = st.session_state.get(opt_key, "")
        if val:
            st.session_state["ci_text"] = val
        for _k in _RESULT_KEYS:
            st.session_state.pop(_k, None)

    def _use_result(edit_key):
        val = st.session_state.get(edit_key, "")
        if val:
            st.session_state["ci_text"] = val
        for _k in _RESULT_KEYS:
            st.session_state.pop(_k, None)

    # Auto-repurpose from Idea Bank Vault click
    if st.session_state.get("ci_auto_repurpose") and st.session_state.get("ci_repurpose_seed"):
        seed = st.session_state.pop("ci_repurpose_seed")
        st.session_state.pop("ci_auto_repurpose", None)
        st.session_state["ci_text"] = seed
        with st.spinner("Repurposing in your voice..."):
            repurpose_prompt = f"""Rewrite this tweet in Tyler Polumbus's voice.

Original tweet:
\"{seed}"

Tyler's voice: direct, no hashtags, ellipsis signature, former-player authority, concise.
Keep the core insight but make it sound like Tyler wrote it from scratch.

Give the repurposed tweet, then show character count."""
            st.session_state["ci_repurposed"] = call_claude(repurpose_prompt)
            st.session_state["ci_rp_edit"] = st.session_state.get("ci_repurposed", "")

    tweet_text = st.text_area("Write your tweet idea:", height=auto_height(st.session_state.get("ci_text", ""), min_h=140), key="ci_text",
        placeholder="Start typing your idea here...")
    char_len = len(tweet_text)
    cls = "char-over" if char_len > 280 else ""
    st.markdown(f'<div class="char-count {cls}">{char_len}/280</div>', unsafe_allow_html=True)

    fc1, fc2 = st.columns(2)
    with fc1:
        fmt = st.selectbox("Format", ["Normal Tweet", "Punchy Tweet", "Long Tweet", "Thread", "Article"], key="ci_format")
    with fc2:
        _custom_voices = load_json("voice_styles.json", [])
        _voice_opts = ["Default", "Critical", "Homer", "Sarcastic"] + [s["name"] for s in _custom_voices]
        voice = st.selectbox("Voice", _voice_opts, key="ci_voice",
            help="Default = natural | Critical = tough love | Homer = ultra positive | Sarcastic = dry wit | @handle = their style")

    # Row 1: primary action + 2 supporting
    sr1, sr2, sr3 = st.columns([2, 1, 1])
    with sr1:
        banger = st.button("⚡ Go Viral", key="ci_banger", use_container_width=True, type="primary")
    with sr2:
        repurpose = st.button("↩ Rewrite", key="ci_repurpose", use_container_width=True)
    with sr3:
        build_this = st.button("⊞ Build", key="ci_build", use_container_width=True)
    # Row 2: utility actions
    sr4, sr5, sr6 = st.columns(3)
    with sr4:
        engage = st.button("≋ Grades", key="ci_engage", use_container_width=True)
    with sr5:
        biz = st.button("◎ Preview", key="ci_biz", use_container_width=True)
    with sr6:
        regenerate = st.button("↺ Redo", key="ci_regen_top", use_container_width=True)
    viral = False  # removed from main buttons

    # Voice modifier for prompts
    voice_mod = ""
    if voice == "Critical":
        voice_mod = """=== CRITICAL VOICE MODE — MANDATORY STRUCTURE ===
YOU MUST write this as a hard accountability take. The output MUST:
1. Open with a specific stat, number, or named failure — NOT a vague opinion (e.g. "The Broncos ran on only 38% of first downs in losses..." not "The Broncos need to do better")
2. Call out exactly what isn't working and why it matters
3. End with a pointed question or challenge that puts the responsibility on someone specific
4. Sound like a disappointed former NFL player holding the team accountable — NOT an angry fan ranting
5. DO NOT use generic phrases like "we need to be better" or "this has to change" — name the specific problem

The tone is: calm, pointed, credible. Former player who knows what winning looks like and isn't seeing it.
WRONG: "The Broncos need to improve their running game."
RIGHT: "We ran on 38% of first downs in losses last year. Every team that made a Super Bowl run in the last 5 years was above 50%. That gap is a choice."
=== END CRITICAL VOICE ==="""
    elif voice == "Homer":
        voice_mod = """=== HOMER VOICE MODE — MANDATORY STRUCTURE ===
YOU MUST write this as a genuine believer rallying the fanbase. The output MUST:
1. Use "we" or "this team" — make the reader feel included in the belief
2. Ground the optimism in something SPECIFIC — a player name, a stat, a moment, an observation (NOT generic "this team is special")
3. Convey real belief that comes from insider football knowledge — "I played 8 years in this league and I know what a winning culture looks like"
4. End with forward momentum — something to look forward to or build on
5. Make the reader feel GOOD about being a fan — positive sentiment, energy, shared belief

The tone is: infectious confidence, grounded in real knowledge. NOT blind cheerleading — earned optimism.
WRONG: "LET'S GO BRONCOS! This team is gonna be great!"
RIGHT: "I've been in enough locker rooms to know when something is real. What I'm watching from this group right now... it's real. We're not done."
=== END HOMER VOICE ==="""
    elif voice == "Sarcastic":
        voice_mod = """=== SARCASTIC VOICE MODE — MANDATORY STRUCTURE ===
YOU MUST write this as dry, deadpan understatement. The output MUST:
1. State the obvious as if calmly explaining something absurd to someone who doesn't see it
2. Use flat, understated language — "Oh interesting." / "Sure." / "Apparently." / "Cool." as openers work well
3. The punchline is the deadpan acceptance of something that SHOULD be outrageous
4. End with one dry final observation that lands the joke without explaining it
5. DO NOT be mean or attack people — punch at situations, decisions, outcomes

The tone is: former player press conference energy. Seen everything. Nothing surprises him. One eyebrow raised.
WRONG: "This franchise is a disaster and everyone is incompetent."
RIGHT: "Oh cool. Another offseason where we didn't address the offensive line. That's been working great. Can't wait to see how it plays out."
=== END SARCASTIC VOICE ==="""
    else:
        voice_mod = """=== DEFAULT VOICE MODE ===
Tyler's natural voice — direct, confident, former-player authority. The output MUST:
1. Lead with the insight or take — no throat-clearing
2. Short punchy sentences. Ellipsis (...) as signature where appropriate
3. State it flat. No hedging, no "maybe", no "I think" — just the take
4. End with either a trailing thought (...) or a question that invites debate
=== END DEFAULT VOICE ==="""

    # Pull live patterns for format templates (evolves with each sync)
    _fp = analyze_personal_patterns()
    _fp_avg = _fp.get("top_avg_chars", 162) if _fp else 162
    _fp_q = _fp.get("top_question_pct", 28) if _fp else 28
    _fp_ell = _fp.get("top_ellipsis_pct", 28) if _fp else 28
    _fp_range = _fp.get("optimal_char_range", (40, 250)) if _fp else (40, 250)
    _fp_hooks = []
    if _fp:
        # Use format-specific examples so short formats only see short hooks
        _hook_pool = (
            _fp.get("top_examples_punchy", []) if fmt == "Punchy Tweet"
            else _fp.get("top_examples_normal", []) if fmt == "Normal Tweet"
            else _fp.get("top_examples_long", []) if fmt in ("Long Tweet", "Thread", "Article")
            else _fp.get("top_examples", [])
        )
        _fp_hooks = [ex.get("text", "")[:80] for ex in _hook_pool[:5]]
    _hooks_str = "\n".join([f'  - "{h}..."' for h in _fp_hooks]) if _fp_hooks else "  (sync tweets to see your top hooks)"

    format_mod = ""
    if fmt == "Punchy Tweet":
        format_mod = f"""FORMAT: PUNCHY TWEET (2 sentences maximum — get in, bait engagement, get out)

STRUCTURE:
SENTENCE 1: The sharpest version of the take. Specific, declarative, no setup. Drop it cold.
SENTENCE 2: The engagement hook. A direct question, forced choice, or bold statement that makes someone feel they HAVE to respond.

RULES:
- Exactly 2 sentences. Not one. Not three. Two.
- Under 160 characters total
- No hashtags, no emojis, no ellipsis
- No "I think" / "maybe" / "honestly" — state it flat
- Every word earns its place or gets cut
- Sentence 2 must make the reader feel compelled to reply

Top hooks to model Sentence 1 after:
{_hooks_str}

WRONG: "The Broncos have some interesting decisions to make this offseason and it will be fun to watch. What do you guys think will happen?"
RIGHT: "The 2026 WR room is better than 2015. Prove me wrong." """

    elif fmt == "Normal Tweet":
        _nt_lo = max(_fp_range[0], 161)
        _nt_hi = min(_fp_range[1], 260)
        format_mod = f"""FORMAT: NORMAL TWEET (161-260 characters)

TYLER'S LIVE DATA (from synced tweet history — updates every sync):
- Optimal range for top tweets: {_nt_lo}-{_nt_hi} chars — aim for the UPPER half of this range
- {_fp_q}% of top tweets use questions (algorithm: replies = 13.5x a like)
- {_fp_ell}% of top tweets use ellipsis (his signature)
- Top performing hooks to model after:
{_hooks_str}

STRUCTURE:
[Confrontational hook or bold declaration]

[Punch line, trailing thought, or question]

RULES:
- Between 161 and 260 characters total — don't be too brief
- Use line break between hook and payoff
- No hashtags, no links, no emojis
- End with question OR ellipsis, not both
- Must stop the scroll in the first 8 words
- Model the hook after one of Tyler's top hooks above

IMAGE RECOMMENDATION:
- Hot take / opinion → NO image (text-only gets higher engagement rate)
- Stat or comparison → YES — simple stat graphic
- Reaction to news → OPTIONAL — screenshot of the news article headline"""

    elif fmt == "Long Tweet":
        format_mod = f"""FORMAT: LONG TWEET (280-1200 characters)

TYLER'S LIVE DATA (updates every sync):
- {_fp_q}% of top tweets use questions, {_fp_ell}% use ellipsis
- Top hooks to model the opening after:
{_hooks_str}

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

IMAGE RECOMMENDATION:
- YES — include 1 supporting image
- Best: stat graphic, comparison chart, or relevant screenshot
- Place context for the image ABOVE the Show More fold
- Images increase total impressions even though text-only has higher engagement rate"""

    elif fmt == "Thread":
        format_mod = f"""FORMAT: THREAD (5-8 tweets)

TYLER'S LIVE DATA (updates every sync):
- {_fp_q}% of top tweets use questions, {_fp_ell}% use ellipsis
- Top hooks to model Tweet 1 after:
{_hooks_str}

STRUCTURE:
TWEET 1: [Bold claim or confrontational question modeled after Tyler's top hooks above] A thread:

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

IMAGE RECOMMENDATION:
- Include at least 1 image in the thread (35% more retweets confirmed)
- DO NOT put image in Tweet 1 — hook should be pure text
- Best placement: Tweet 2-4 (data chart, stat graphic, or supporting visual)
- For 7+ tweet threads: include 2 images spread across the middle tweets
- Image types that work: stat graphics, comparison charts, play diagrams, game screenshots"""

    elif fmt == "Article":
        format_mod = f"""FORMAT: X ARTICLE (1,500-2,000 words / 6-8 minute read)

WHY ARTICLES MATTER: X Articles grew 20x since Dec 2025 ($2.15M contest prizes). They keep users on-platform (no link penalty), generate 2+ min dwell time (+10 algorithm weight), and Premium subscribers get 2-4x reach boost. This is the HIGHEST PRIORITY content format.

TYLER'S LIVE DATA (updates every sync):
- Top hooks to model headline/intro after:
{_hooks_str}
- {_fp_q}% of top tweets use questions — use them between sections
- {_fp_ell}% use ellipsis — use sparingly in articles for emphasis

STRUCTURE:
HEADLINE: [50-75 chars, includes number or specific claim, takes a position]
- Numbers perform 2x better than vague headlines
- Specificity over vagueness — name the player, name the stat
- Model after Tyler's top hooks above
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
[Contrarian angle or insider perspective — former NFL player authority]
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
- Tyler's voice throughout — direct, no hedging, former-player authority
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

    result = None
    if banger and tweet_text.strip():
        with st.spinner("Perfecting your tweet..."):
            pp = analyze_personal_patterns()
            patterns_ctx = build_patterns_context(pp, fmt) if pp else ""
            _char_limit = 160 if fmt == "Punchy Tweet" else (260 if fmt == "Normal Tweet" else None)
            _opt_range = pp.get("optimal_char_range", (0, 280)) if pp else (0, 280)
            if _char_limit:
                # Clamp the range so synced long-tweet examples don't override the hard limit
                _opt_range = (_opt_range[0], min(_opt_range[1], _char_limit))
            _char_rule = f"- CHARACTER LIMIT: Every option MUST be under {_char_limit} characters total — count carefully, no exceptions." if _char_limit else (f"- Optimal character range: {_opt_range[0]}-{_opt_range[1]} characters" if pp else "")
            banger_prompt = f"""Tyler drafted this tweet. Rewrite it to score 9+ on every X algorithm metric.

Draft: "{tweet_text}"

{format_mod}
{patterns_ctx}

Rules:
- Reading Level (7th-9th grade)
- No Hashtags, Links, Tags, Emojis
- Hook & Pattern Breakers (first line stops the scroll)
{_char_rule}

Return ONLY this JSON, no other text:
{{
  "option1": "full tweet text here",
  "option1_pattern": "which top tweet pattern this is modeled after",
  "option2": "full tweet text here",
  "option2_pattern": "which top tweet pattern this is modeled after",
  "option3": "full tweet text here",
  "option3_pattern": "which top tweet pattern this is modeled after",
  "recommendation": "Which option to post and exactly why — reference his patterns and algorithm signals"
}}"""
            raw = call_claude(banger_prompt, system=get_system_for_voice(voice, voice_mod))
            try:
                raw_clean = raw.strip()
                if raw_clean.startswith("```"):
                    raw_clean = raw_clean.split("\n", 1)[1].rsplit("```", 1)[0]
                banger_data = json.loads(raw_clean)
                st.session_state["ci_banger_data"] = banger_data
                for _i in [1,2,3]: st.session_state.pop(f"ci_banger_opt_{_i}", None)  # fresh widget per new generation
                st.session_state["ci_last_action"] = {"type": "banger", "text": tweet_text, "fmt": fmt, "voice": voice}
                st.session_state.pop("ci_result", None)
            except Exception:
                result = raw  # fallback to plain text
    elif viral and tweet_text.strip():
        with st.spinner("Analyzing viral potential against your history..."):
            history = get_tweet_knowledge_base()
            pp = analyze_personal_patterns()
            patterns_ctx = build_patterns_context(pp, fmt) if pp else ""

            if history:
                avg_likes = sum(t.get("likeCount", 0) for t in history) // max(len(history), 1)
                avg_rts = sum(t.get("retweetCount", 0) for t in history) // max(len(history), 1)
                avg_replies = sum(t.get("replyCount", 0) for t in history) // max(len(history), 1)
                top_tweets = sorted(history, key=lambda t: t.get("likeCount", 0), reverse=True)[:10]
                top_examples = "\n".join([f"- {t.get('text','')[:120]} (likes:{t.get('likeCount',0)}, rts:{t.get('retweetCount',0)}, replies:{t.get('replyCount',0)})" for t in top_tweets])
                history_ctx = f"\n\nTyler's average tweet performance: {avg_likes} likes, {avg_rts} RTs, {avg_replies} replies.\n\nHis top 10 tweets:\n{top_examples}"
            else:
                history_ctx = "\n\nNo tweet history available — sync tweets first for better predictions."
                avg_likes = 50
                avg_rts = 5
                avg_replies = 10

            viral_prompt = f"""Analyze this draft tweet's viral potential based on Tyler's ACTUAL historical data and personal benchmarks.

Draft: "{tweet_text}"
{history_ctx}
{patterns_ctx}

{format_mod}

Compare this draft against Tyler's personal patterns:
- His top tweets average {pp.get('top_avg_chars', 'N/A') if pp else 'N/A'} characters — this draft is {len(tweet_text)} characters
- {pp.get('top_question_pct', 'N/A') if pp else 'N/A'}% of his top tweets use questions
- {pp.get('top_ellipsis_pct', 'N/A') if pp else 'N/A'}% of his top tweets use ellipsis
- His optimal character range is {pp.get('optimal_char_range', 'N/A') if pp else 'N/A'}

Return ONLY this JSON format:
{{
"predicted_likes": [number based on his history],
"predicted_retweets": [number],
"predicted_comments": [number],
"total_predicted_engagement": [sum],
"confidence": "High" or "Medium" or "Low",
"compared_to_average": "Above average" or "Average" or "Below average",
"reasoning": "[2-3 sentences explaining why, referencing specific similar tweets from his history that performed well or poorly and comparing against his personal benchmarks]",
"improvements": ["specific tip referencing his data 1", "specific tip referencing his data 2", "specific tip referencing his data 3"]
}}"""
            raw = call_claude(viral_prompt)
            try:
                json_match = re.search(r'\{.*\}', raw, re.DOTALL)
                vdata = json.loads(json_match.group()) if json_match else None
            except Exception:
                vdata = None

            if vdata and "predicted_likes" in vdata:
                st.session_state["ci_viral_data"] = vdata
            else:
                result = raw
    elif engage and tweet_text.strip():
        with st.spinner("Grading against the algorithm and your history..."):

            grade_prompt = f"""Grade this tweet for X algorithm performance.

X ALGORITHM WEIGHTS: replies-to-own=150x, others-replies=27x, profile-clicks=24x, dwell-2min=20x, bookmarks=20x, RTs=2x, likes=1x. Penalties: external links -30-50%, 3+ hashtags -40%, combative tone -80%.

Tweet ({len(tweet_text)} chars): "{tweet_text}"
Has question mark: {"yes" if "?" in tweet_text else "no"} | Has ellipsis: {"yes" if "..." in tweet_text else "no"}

Grade these 8 categories (score 1-10). For each, give a specific detail referencing the algorithm weight and a concrete fix (exact words, not general advice).

Return ONLY valid JSON:
{{
"algorithm_score": 0-100,
"tyler_score": 0-100,
"grades": [
    {{"name": "Hook Strength", "score": 0, "detail": "...", "benchmark": "...", "fix": "exact edit to first line"}},
    {{"name": "Conversation Catalyst", "score": 0, "detail": "...", "benchmark": "...", "fix": "exact edit to drive replies"}},
    {{"name": "Bookmark Worthiness", "score": 0, "detail": "...", "benchmark": "...", "fix": "exact stat or insight to add"}},
    {{"name": "Share/Quote Potential", "score": 0, "detail": "...", "benchmark": "...", "fix": "exact phrasing to sharpen the take"}},
    {{"name": "Engagement Triggers", "score": 0, "detail": "...", "benchmark": "...", "fix": "exact punctuation or structural edit"}},
    {{"name": "Algorithm Compliance", "score": 0, "detail": "...", "benchmark": "...", "fix": "exact penalty to remove or 'No changes needed'"}},
    {{"name": "Dwell Time Potential", "score": 0, "detail": "...", "benchmark": "...", "fix": "exact structural edit to increase read time"}},
    {{"name": "Voice Match", "score": 0, "detail": "...", "benchmark": "...", "fix": "exact word or phrase to change"}}
],
"personal_insights": ["insight 1 with Tyler's data", "insight 2 with Tyler's data"],
"suggestions": ["improvement 1", "improvement 2", "improvement 3"]
}}"""
            raw = call_claude(grade_prompt, system=TYLER_CONTEXT)
            try:
                clean = re.sub(r'```(?:json)?\s*', '', raw).strip().rstrip('`').strip()
                json_match = re.search(r'\{.*\}', clean, re.DOTALL)
                gdata = json.loads(json_match.group()) if json_match else None
            except Exception:
                gdata = None
            if gdata and "grades" in gdata:
                st.session_state["ci_grades"] = gdata
                st.session_state.pop("ci_result", None)
            else:
                result = raw

    elif biz and tweet_text.strip():
        # Preview — show how tweet looks on X
        st.session_state["ci_preview"] = tweet_text
        st.session_state.pop("ci_result", None)
        st.session_state.pop("ci_repurposed", None)

    elif build_this and tweet_text.strip():
        with st.spinner("Building your tweet..."):
            build_prompt = f"""Tyler Polumbus has a tweet concept/angle he wants turned into a finished tweet. Materialize this concept into the actual tweet.

CONCEPT/ANGLE:
\"{tweet_text}\"

{format_mod}

TASK: Extract the best version of this idea and write the finished tweet. This is NOT a rewrite — you are crafting the actual tweet from a raw concept description.

- Strong hook — first line stops the scroll
- No hashtags, no emojis
- 7th-9th grade reading level
- End with something that makes people reply or argue
- Algorithm optimized: strong opinion, relatable, invites engagement


Give ONLY the finished tweet/thread/article. No explanation. No character count. No commentary."""
            st.session_state["ci_result"] = call_claude(build_prompt, system=get_system_for_voice(voice, voice_mod))
            st.session_state["ci_result_edit"] = st.session_state.get("ci_result", "")
            st.session_state["ci_last_action"] = {"type": "build_this", "text": tweet_text, "fmt": fmt, "voice": voice}
            st.session_state.pop("ci_repurposed", None)
            st.session_state.pop("ci_viral_data", None)
            st.session_state.pop("ci_grades", None)
            st.session_state.pop("ci_preview", None)
            st.session_state.pop("ci_banger_data", None)

    elif repurpose and tweet_text.strip():
        with st.spinner("Repurposing in your voice..."):
            repurpose_prompt = f"""Someone else wrote this tweet. Write a completely NEW tweet on the same subject — do NOT copy any original phrasing.

Original tweet (NOT Tyler's): "{tweet_text}"

{format_mod}

- Strong hook in the first line
- Invites engagement/replies
- No hashtags, no emojis
- 7th-9th grade reading level


Give the repurposed tweet, then show character count."""
            repurposed = call_claude(repurpose_prompt, system=get_system_for_voice(voice, voice_mod))
            st.session_state["ci_repurposed"] = repurposed
            st.session_state["ci_rp_edit"] = st.session_state.get("ci_repurposed", "")
            st.session_state["ci_last_action"] = {"type": "repurpose", "text": tweet_text, "fmt": fmt, "voice": voice}
            st.session_state.pop("ci_result", None)
            st.session_state.pop("ci_viral_data", None)
            st.session_state.pop("ci_grades", None)
            st.session_state.pop("ci_preview", None)

    if result:
        st.session_state["ci_result"] = result
        st.session_state["ci_result_edit"] = st.session_state.get("ci_result", "")
        st.session_state.pop("ci_viral_data", None)
        st.session_state.pop("ci_grades", None)
        st.session_state.pop("ci_preview", None)
        st.session_state.pop("ci_repurposed", None)
        st.session_state.pop("ci_banger_data", None)

    # Regenerate — re-runs last action with current format/voice
    # (button is declared above voice_mod so it fires in the same render cycle)
    if regenerate:
        last = st.session_state.get("ci_last_action", {})
        _rtype = last.get("type")
        _rtext = last.get("text", tweet_text)
        if _rtype == "build_this" and _rtext:
            with st.spinner("Rebuilding..."):
                build_prompt = f"""Tyler Polumbus has a tweet concept/angle he wants turned into a finished tweet. Materialize this concept into the actual tweet.

CONCEPT/ANGLE:
\"{_rtext}\"

{format_mod}

TASK: Extract the best version of this idea and write the finished tweet. This is NOT a rewrite — you are crafting the actual tweet from a raw concept description.

- Strong hook — first line stops the scroll
- No hashtags, no emojis
- 7th-9th grade reading level
- End with something that makes people reply or argue


Give ONLY the finished tweet/thread/article. No explanation. No character count. No commentary."""
                st.session_state["ci_result"] = call_claude(build_prompt, system=get_system_for_voice(voice, voice_mod))
                st.session_state["ci_result_edit"] = st.session_state.get("ci_result", "")
                st.session_state["ci_last_action"] = {"type": "build_this", "text": _rtext, "fmt": fmt, "voice": voice}
                st.session_state.pop("ci_banger_data", None)
                st.session_state.pop("ci_repurposed", None)
        elif _rtype == "repurpose" and _rtext:
            with st.spinner("Repurposing..."):
                rp = f"""Someone else wrote this tweet. Write a completely NEW tweet on the same subject.\n\nOriginal: \"{_rtext}\"\n\n{format_mod}\n\nGive the repurposed tweet, then character count."""
                st.session_state["ci_repurposed"] = call_claude(rp, system=get_system_for_voice(voice, voice_mod))
                st.session_state["ci_rp_edit"] = st.session_state.get("ci_repurposed", "")
                st.session_state["ci_last_action"] = {"type": "repurpose", "text": _rtext, "fmt": fmt, "voice": voice}
                st.session_state.pop("ci_result", None)
                st.session_state.pop("ci_banger_data", None)
        elif _rtype == "banger" and _rtext:
            with st.spinner("Perfecting your tweet..."):
                pp = analyze_personal_patterns()
                patterns_ctx = build_patterns_context(pp, fmt) if pp else ""
                _redo_char_limit = 160 if fmt == "Punchy Tweet" else (260 if fmt == "Normal Tweet" else None)
                _redo_char_rule = f"- CHARACTER LIMIT: Every option MUST be under {_redo_char_limit} characters total — no exceptions." if _redo_char_limit else ""
                banger_prompt = f"""Tyler drafted this tweet. Rewrite it to score 9+ on every X algorithm metric.

Draft: "{_rtext}"

{format_mod}
{patterns_ctx}

Rules:
- Reading Level (7th-9th grade)
- No Hashtags, Links, Tags, Emojis
- Hook in the first line
{_redo_char_rule}

Return ONLY this JSON, no other text:
{{
  "option1": "tweet text", "option1_pattern": "pattern name",
  "option2": "tweet text", "option2_pattern": "pattern name",
  "option3": "tweet text", "option3_pattern": "pattern name",
  "recommendation": "which to post and why"
}}"""
                raw = call_claude(banger_prompt, system=get_system_for_voice(voice, voice_mod))
                try:
                    raw_clean = raw.strip()
                    if raw_clean.startswith("```"):
                        raw_clean = raw_clean.split("\n", 1)[1].rsplit("```", 1)[0]
                    st.session_state["ci_banger_data"] = json.loads(raw_clean)
                    for _i in [1,2,3]: st.session_state.pop(f"ci_banger_opt_{_i}", None)
                    st.session_state["ci_last_action"] = {"type": "banger", "text": _rtext, "fmt": fmt, "voice": voice}
                    st.session_state.pop("ci_result", None)
                except Exception:
                    st.session_state["ci_result"] = raw
                    st.session_state["ci_result_edit"] = raw
                    st.session_state.pop("ci_banger_data", None)  # clear old 3-box view
                    st.session_state["ci_last_action"] = {"type": "banger", "text": _rtext, "fmt": fmt, "voice": voice}


    # ── RESULTS (full width, below buttons) ──
    if st.session_state.get("ci_banger_data"):
        bd = st.session_state["ci_banger_data"]
        _la = st.session_state.get("ci_last_action", {})
        _la_fmt = (_la.get("fmt") or fmt).upper()
        _la_voice = (_la.get("voice") or voice).upper()

        hdr1, hdr2 = st.columns([4, 1])
        with hdr1:
            st.markdown(
                f'<div style="font-size:11px;color:#666888;font-weight:700;letter-spacing:1.5px;margin:4px 0 12px;">{_la_fmt} · {_la_voice} VOICE</div>',
                unsafe_allow_html=True)
        with hdr2:
            if st.button("✕ Clear", key="ci_clear_banger"):
                for _k in _RESULT_KEYS:
                    st.session_state.pop(_k, None)
                st.rerun()

        opts = [(bd.get(f"option{i}", ""), bd.get(f"option{i}_pattern", "")) for i in [1, 2, 3] if bd.get(f"option{i}")]
        for ti, (opt_text, pattern) in enumerate(opts):
            opt_key = f"ci_banger_opt_{ti + 1}"
            st.markdown(
                f'<div style="font-size:11px;color:#FF6B00;font-weight:700;letter-spacing:2px;margin:20px 0 4px;">OPTION {ti + 1}</div>',
                unsafe_allow_html=True)
            if pattern:
                st.markdown(
                    f'<div style="font-size:11px;color:#666688;letter-spacing:0.5px;margin-bottom:8px;">{pattern}</div>',
                    unsafe_allow_html=True)
            edited_opt = st.text_area("", value=opt_text, height=auto_height(opt_text, min_h=100),
                                      key=opt_key, label_visibility="collapsed")
            b1, b2 = st.columns(2)
            with b1:
                if st.button("↓ Save", key=f"ci_banger_save_{ti + 1}", use_container_width=True):
                    ideas = load_json("saved_ideas.json", [])
                    ideas.append({"text": edited_opt, "format": fmt, "category": "Uncategorized",
                                  "saved_at": datetime.now().isoformat()})
                    save_json("saved_ideas.json", ideas)
                    st.success("Saved.")
            with b2:
                st.button("↗ Use", key=f"ci_banger_use_{ti + 1}", use_container_width=True,
                          type="primary", on_click=_use_option, args=(opt_key,))

        if bd.get("recommendation"):
            st.markdown(
                '<div style="font-size:11px;color:#FF6B00;font-weight:700;letter-spacing:2px;margin:24px 0 8px;">RECOMMENDATION</div>',
                unsafe_allow_html=True)
            st.markdown(
                f'<div style="background:rgba(255,107,0,0.05);border:1px solid rgba(255,107,0,0.15);border-left:3px solid #FF6B00;border-radius:12px;padding:16px 18px;font-size:13px;color:#c0c0d8;line-height:1.7;">{bd["recommendation"]}</div>',
                unsafe_allow_html=True)

    elif st.session_state.get("ci_grades"):
        gd = st.session_state["ci_grades"]
        gd = st.session_state["ci_grades"]
        algo_score = gd.get("algorithm_score", 0)
        tyler_score = gd.get("tyler_score", 0)
        algo_color = "#22c55e" if algo_score >= 75 else "#FF6B00" if algo_score >= 55 else "#ef4444"
        tyler_color = "#22c55e" if tyler_score >= 75 else "#FF6B00" if tyler_score >= 55 else "#ef4444"
        st.markdown(f"""<div style="display:flex;gap:12px;margin-bottom:14px;">
            <div style="flex:1;background:#0d0d18;border:1px solid #1e1e35;border-radius:10px;padding:14px;text-align:center;">
                <div style="font-family:'Bebas Neue',sans-serif;font-size:44px;color:{algo_color};line-height:1;">{algo_score}</div>
                <div style="font-size:10px;color:#666688;letter-spacing:2px;text-transform:uppercase;margin-top:2px;">Algo Score</div>
            </div>
            <div style="flex:1;background:#0d0d18;border:1px solid #1e1e35;border-radius:10px;padding:14px;text-align:center;">
                <div style="font-family:'Bebas Neue',sans-serif;font-size:44px;color:{tyler_color};line-height:1;">{tyler_score}</div>
                <div style="font-size:10px;color:#666688;letter-spacing:2px;text-transform:uppercase;margin-top:2px;">Tyler Score</div>
            </div>
        </div>""", unsafe_allow_html=True)
        insights = gd.get("personal_insights", [])
        if insights:
            for ins in insights:
                st.markdown(f'<div style="background:#1a1a30;border-left:3px solid #FF6B00;border-radius:6px;padding:8px 12px;margin-bottom:6px;font-size:12px;color:#d8d8e8;line-height:1.5;">{ins}</div>', unsafe_allow_html=True)
        grades = gd.get("grades", [])
        if grades:
            st.markdown('<div style="font-size:11px;color:#888;letter-spacing:1px;text-transform:uppercase;margin:10px 0 6px;">Grade Breakdown</div>', unsafe_allow_html=True)
            for g in grades:
                score = g.get("score", 0)
                sc = "#22c55e" if score >= 8 else "#FF6B00" if score >= 6 else "#ef4444"
                fix = g.get("fix", "")
                fix_html = f'<div style="font-size:11px;color:#4ecdc4;margin-top:6px;border-left:2px solid #4ecdc4;padding-left:8px;">Fix: {fix}</div>' if fix else ""
                st.markdown(f"""<div style="background:#0d0d18;border:1px solid #1e1e35;border-radius:8px;padding:12px;margin-bottom:8px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                        <span style="font-weight:600;font-size:13px;">{g.get('name','')}</span>
                        <span style="font-size:13px;color:{sc};font-weight:700;">{score}/10</span>
                    </div>
                    <div style="font-size:12px;color:#9999aa;line-height:1.5;">{g.get('detail','')}</div>
                    {fix_html}
                </div>""", unsafe_allow_html=True)
        suggestions = gd.get("suggestions", [])
        if suggestions:
            st.markdown('<div style="font-size:11px;color:#888;letter-spacing:1px;text-transform:uppercase;margin:10px 0 6px;">Improvements</div>', unsafe_allow_html=True)
            for s in suggestions:
                st.markdown(f'<div style="font-size:12px;color:#9999aa;padding:4px 0 4px 10px;border-left:2px solid rgba(255,107,0,0.3);margin-bottom:6px;line-height:1.5;">{s}</div>', unsafe_allow_html=True)

    elif st.session_state.get("ci_result") or st.session_state.get("ci_repurposed"):
        _rkey = "ci_result" if st.session_state.get("ci_result") else "ci_repurposed"
        _val = st.session_state[_rkey]
        _edit_key = f"ci_right_edit_{hash(_val) & 0xFFFFFF}"
        edited = st.text_area("", value=_val, height=auto_height(_val, min_h=160), key=_edit_key, label_visibility="collapsed")
        r1, r2 = st.columns(2)
        with r1:
            if st.button("↓ Save", key="ci_right_save", use_container_width=True):
                ideas = load_json("saved_ideas.json", [])
                ideas.append({"text": edited, "format": fmt, "category": "Uncategorized", "saved_at": datetime.now().isoformat()})
                save_json("saved_ideas.json", ideas)
                st.success("Saved.")
        with r2:
            st.button("↗ Use", key="ci_right_use", use_container_width=True, type="primary",
                      on_click=_use_result, args=(_edit_key,))


    elif st.session_state.get("ci_preview"):
        preview_text = st.session_state["ci_preview"]
        truncated = preview_text[:280]
        show_more = len(preview_text) > 280
        now_str = datetime.now().strftime("%b %d, %Y, %-I:%M %p")
        st.markdown(f"""<div style="background:#0d0d18;border:1px solid #2e2e45;border-radius:16px;padding:18px;">
            <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">
                <div style="width:36px;height:36px;border-radius:50%;background:linear-gradient(135deg,#FF6B00,#cc4a00);display:flex;align-items:center;justify-content:center;font-weight:700;color:white;font-size:14px;">T</div>
                <div style="font-size:14px;"><span style="font-weight:700;">Tyler Polumbus</span><br><span style="color:#666688;font-size:12px;">@{TYLER_HANDLE}</span></div>
            </div>
            <div style="font-size:14px;line-height:1.6;white-space:pre-wrap;color:#e8e8f0;">{truncated}{'<span style="color:#1d9bf0;"> Show more</span>' if show_more else ''}</div>
            <div style="color:#666688;font-size:12px;margin-top:12px;">{now_str} · X</div>
        </div>
        {'<div style="font-size:11px;color:#555578;margin-top:8px;">Hook lands before "Show more" cutoff — good.</div>' if not show_more else '<div style="font-size:11px;color:#FF6B00;margin-top:8px;">280 char cutoff above. Make sure the hook is before it.</div>'}""", unsafe_allow_html=True)

    elif st.session_state.get("ci_viral_data"):
        vd = st.session_state["ci_viral_data"]
        total = vd.get("total_predicted_engagement", 0)
        conf = vd.get("confidence", "Medium")
        compared = vd.get("compared_to_average", "Average")
        conf_color = "#22c55e" if conf == "High" else "#FF6B00" if conf == "Medium" else "#ef4444"
        comp_icon = "↑" if "Above" in compared else "→" if "Average" in compared else "↓"
        st.markdown(f"""<div style="background:#0d0d18;border:1px solid #1e1e35;border-radius:10px;padding:16px;margin-bottom:10px;">
            <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #1e1e35;"><span style="font-size:13px;color:#8888aa;">Predicted Likes</span><span style="font-family:'Bebas Neue',sans-serif;font-size:22px;color:#e8e8f0;">{vd.get('predicted_likes',0):,}</span></div>
            <div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #1e1e35;"><span style="font-size:13px;color:#8888aa;">Predicted RTs</span><span style="font-family:'Bebas Neue',sans-serif;font-size:22px;color:#e8e8f0;">{vd.get('predicted_retweets',0):,}</span></div>
            <div style="display:flex;justify-content:space-between;padding:6px 0;"><span style="font-size:13px;color:#8888aa;">Total Engagement</span><span style="font-family:'Bebas Neue',sans-serif;font-size:22px;color:#FF6B00;">{total:,}</span></div>
        </div>
        <div style="margin-bottom:10px;font-size:13px;">Confidence: <span style="background:{conf_color};color:white;padding:2px 8px;border-radius:4px;font-size:11px;">{conf}</span> &nbsp; {comp_icon} {compared}</div>
        <div style="font-size:13px;color:#c0c0d8;line-height:1.6;">{vd.get('reasoning','')}</div>""", unsafe_allow_html=True)
        for tip in vd.get("improvements", []):
            st.markdown(f'<div style="font-size:12px;color:#9999aa;padding:4px 0 4px 10px;border-left:2px solid rgba(255,107,0,0.3);margin-bottom:6px;">{tip}</div>', unsafe_allow_html=True)

    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

    # ── Save Post ──
    sc_cat = st.selectbox("Category", ["Uncategorized", "Evergreen", "Timely", "Thread Ideas", "Video Ideas"], key="ci_cat")
    if st.button("↓ Save Post", key="ci_save", use_container_width=True):
        if tweet_text.strip():
            ideas = load_json("saved_ideas.json", [])
            ideas.append({"text": tweet_text, "format": fmt, "category": sc_cat, "saved_at": datetime.now().isoformat()})
            save_json("saved_ideas.json", ideas)
            st.success("Idea saved.")

    # ── Bank ──
    with st.expander("Bank", expanded=False):

        _default_folders = ["Uncategorized", "Evergreen", "Timely", "Thread Ideas", "Video Ideas"]
        _all_folders = load_json("saved_ideas_folders.json", _default_folders)
        _folder_opts = ["All Ideas"] + _all_folders + ["Idea Bank Vault", "Rewrite Queue"]

        folder = st.selectbox("Folder", _folder_opts, key="ci_folder")

        with st.expander("Manage Folders"):
            new_folder_name = st.text_input("New folder name:", key="ci_new_folder", placeholder="e.g. Hot Takes")
            if st.button("+ Add Folder", key="ci_add_folder") and new_folder_name.strip():
                fname = new_folder_name.strip()
                if fname not in _all_folders:
                    _all_folders.append(fname)
                    save_json("saved_ideas_folders.json", _all_folders)
                    st.rerun()
            for cf in list(_all_folders):
                if st.button(f"✕ {cf}", key=f"ci_del_{cf}"):
                    _all_folders = [f for f in _all_folders if f != cf]
                    save_json("saved_ideas_folders.json", _all_folders)
                    st.rerun()

        if folder in ("Idea Bank Vault", "Rewrite Queue"):
            gist_file = "hq_inspiration.json" if folder == "Idea Bank Vault" else "hq_repurpose.json"
            try:
                gist_id = st.secrets.get("GIST_ID", "15fb167bbbfdaa79d5ce11c266c3f652")
                resp = requests.get(f"https://api.github.com/gists/{gist_id}", headers=_gist_headers(), timeout=10)
                gist_data = resp.json()
                inspo_items = json.loads(gist_data["files"][gist_file]["content"]) if gist_file in gist_data.get("files", {}) else []
            except Exception:
                inspo_items = []
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
                    if st.button("↩ Rewrite", key=f"ci_inspo_{ii}", use_container_width=True):
                        st.session_state["ci_repurpose_seed"] = item.get("text", orig_text)
                        st.session_state["ci_auto_repurpose"] = True
                        st.rerun()
        else:
            ideas = load_json("saved_ideas.json", [])
            if folder == "All Ideas":
                inspo_as_ideas = []
                try:
                    gist_id = st.secrets.get("GIST_ID", "15fb167bbbfdaa79d5ce11c266c3f652")
                    resp = requests.get(f"https://api.github.com/gists/{gist_id}", headers=_gist_headers(), timeout=10)
                    gist_data = resp.json()
                    raw = json.loads(gist_data["files"]["hq_inspiration.json"]["content"]) if "hq_inspiration.json" in gist_data.get("files", {}) else []
                    inspo_as_ideas = [{"text": i.get("text",""), "category": "Idea Bank", "format": i.get("author",""), "saved_at": i.get("saved_at","")} for i in raw]
                except Exception:
                    pass
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

# ═══════════════════════════════════════════════════════════════════════════
# PAGE: CONTENT COACH
# ═══════════════════════════════════════════════════════════════════════════
def page_content_coach():
    st.markdown('<div class="main-header">CONTENT <span>ADVISOR</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Your AI social media expert. Knows your data, the algorithm, and how to grow.</div>', unsafe_allow_html=True)

    # --- Initialize session state ---
    if "coach_conversations" not in st.session_state:
        st.session_state.coach_conversations = load_json("coach_conversations.json", [])
    if "coach_current" not in st.session_state:
        st.session_state.coach_current = {"id": None, "messages": [], "title": "New Chat"}

    COACH_SYSTEM = get_voice_context() + """

You are Tyler's personal social media coach. You are an EXPERT on:
- X (Twitter) algorithm: engagement weights (replies=27x, bookmarks=20x, retweets=20x, dwell time=20x, likes=1x), penalties (links=-50%, 3+ hashtags=-40%, negative sentiment reduces reach)
- Content strategy: hook formulas, thread structures, engagement tactics, audience growth
- Tyler's specific data: his top performing tweets, patterns, optimal character length, question/ellipsis usage rates, what topics work for him
- All social media platforms (YouTube, Instagram, TikTok, LinkedIn) for future expansion
- Sports content specifically: what makes sports commentary go viral, fan psychology, timing around games/events

Your coaching style:
- Direct and practical — no fluff, no "great question!" filler
- Always reference Tyler's actual data when giving advice
- Give specific, actionable recommendations with examples
- Challenge Tyler when his ideas won't perform well — don't just agree
- Think in terms of SYSTEMS not individual posts — build repeatable frameworks
- Always explain WHY something works in terms of the algorithm
"""

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
        history_str = "\n".join([f"{'Tyler' if m['role']=='user' else 'Coach'}: {m['content']}" for m in msgs])
        reply = call_claude(f"Conversation so far:\n{history_str}\n\nRespond as the coach.", system=sys_prompt, max_tokens=1200)
        msgs.append({"role": "assistant", "content": reply})
        _save_current()

    # --- Layout: 3 columns ---
    col_left, col_center, col_right = st.columns([1, 3, 1])

    with col_left:
        st.markdown("##### Conversations")
        if st.button("+ New", use_container_width=True, key="coach_new"):
            st.session_state.coach_current = {"id": None, "messages": [], "title": "New Chat"}
            st.rerun()
        for conv in reversed(st.session_state.coach_conversations[-20:]):
            label = conv.get("title", "Untitled")[:30]
            is_active = conv.get("id") == st.session_state.coach_current.get("id")
            if st.button((">> " if is_active else "") + label, key=f"cv_{conv['id']}", use_container_width=True):
                st.session_state.coach_current = json.loads(json.dumps(conv))
                st.rerun()
        if st.session_state.coach_conversations:
            if st.button("⊘ Clear", key="coach_clear_all", use_container_width=True):
                st.session_state.coach_conversations = []
                st.session_state.coach_current = {"id": None, "messages": [], "title": "New Chat"}
                save_json("coach_conversations.json", [])
                st.rerun()

    with col_right:
        st.markdown("##### Output Format")
        coach_fmt = st.selectbox("Format", ["General Advice", "Normal Tweet", "Long Tweet", "Thread", "Article"], key="coach_fmt", label_visibility="collapsed")
        st.markdown("---")
        st.markdown("##### Quick Save to Ideas")
        save_text = st.text_area("Save to Creator Studio:", height=100, key="coach_save_text", placeholder="Paste coach advice here...")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("↓ Save Post", use_container_width=True, key="coach_save_idea") and save_text.strip():
                ideas = load_json("saved_ideas.json", [])
                ideas.append({"id": str(uuid.uuid4()), "text": save_text.strip(), "category": "From Coach", "created_at": datetime.now().isoformat()})
                save_json("saved_ideas.json", ideas)
                st.success("Saved!")
        with c2:
            if st.button("↩ Remix", use_container_width=True, key="coach_repurpose") and save_text.strip():
                with st.spinner("Repurposing..."):
                    repurposed = call_claude(f"Rewrite this into a compelling tweet for Tyler Polumbus:\n\n{save_text.strip()}", max_tokens=600)
                    st.session_state.coach_save_text_result = repurposed
        if "coach_save_text_result" in st.session_state:
            st.markdown(f"**Rewrited:**\n\n{st.session_state.coach_save_text_result}")

    with col_center:
        include_history = st.checkbox("Include Post History (check on first message per conversation)", value=not bool(st.session_state.coach_current["messages"]), key="coach_hist_toggle")

        # Demo questions dropdown
        if not st.session_state.coach_current["messages"]:
            demo_pick = st.selectbox("Demo questions:", ["-- Pick a question --"] + DEMO_QUESTIONS, key="coach_demo")
            if demo_pick != "-- Pick a question --":
                with st.spinner("Coach is thinking..."):
                    _send_message(demo_pick, include_history, coach_fmt)
                st.rerun()

        # Chat display
        for msg in st.session_state.coach_current.get("messages", []):
            role_label = "Tyler" if msg["role"] == "user" else "Coach"
            cls = "chat-user" if msg["role"] == "user" else "chat-ai"
            st.markdown(f'<div class="chat-msg {cls}"><div class="chat-role">{role_label}</div><div style="color:#d8d8e8;font-size:16px;line-height:1.8;white-space:pre-wrap;">{msg["content"]}</div></div>', unsafe_allow_html=True)

        # Input
        user_input = st.text_area("Ask your coach:", height=80, key="coach_input", placeholder="What should I write about today?")
        if st.button("↗ Send", use_container_width=True, key="coach_send") and user_input.strip():
            with st.spinner("Coach is thinking..."):
                _send_message(user_input.strip(), include_history, coach_fmt)
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: ARTICLE WRITER
# ═══════════════════════════════════════════════════════════════════════════
def page_article_writer():
    st.markdown('<div class="main-header">ARTICLE <span>WRITER</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Expand a tweet or brain dump into a full X Article.</div>', unsafe_allow_html=True)

    col_main, col_saved = st.columns([2, 1])

    # ── Left 2/3: Tweet / Raw Thoughts selectors + generation ──────────────
    with col_main:
        # Section 1 — Choose a Tweet
        st.markdown("#### Choose a Tweet to Expand")
        st.caption("Select a tweet to expand into an article")
        tweets = load_json("tweet_history.json", [])
        top_tweets = sorted(tweets, key=lambda t: t.get("likeCount", 0) + t.get("retweetCount", 0) * 3, reverse=True)[:8] if tweets else []

        if "aw_sel_tweet" not in st.session_state:
            st.session_state.aw_sel_tweet = None

        for i, tw in enumerate(top_tweets):
            txt = tw.get("text", "")
            dt = tw.get("createdAt", "")[:10]
            likes = tw.get("likeCount", 0)
            rts = tw.get("retweetCount", 0)
            reps = tw.get("replyCount", 0)
            views = tw.get("viewCount", 0)
            selected = st.session_state.aw_sel_tweet == i
            border = "border-left:3px solid #FF6B00;" if selected else ""
            st.markdown(f"""<div class="tweet-card" style="{border}">
                <div class="tweet-num">{dt}</div>
                <div style="color:#d8d8e8;font-size:13px;">{txt[:220]}{'...' if len(txt)>220 else ''}</div>
                <div style="margin-top:6px;font-size:11px;color:#8888aa;">{likes} likes &middot; {rts} RTs &middot; {reps} replies &middot; {views:,} views</div>
            </div>""", unsafe_allow_html=True)
            if st.button("→ Select", key=f"aw_tw_{i}", use_container_width=True):
                st.session_state.aw_sel_tweet = i
                st.session_state.aw_sel_dump = None
                st.session_state["aw_autogen"] = tw.get("text", "")
                st.rerun()

        if not top_tweets:
            st.info("No tweet history yet. Sync tweets in Post History first.")

        # Auto-generate when tweet is selected
        if st.session_state.get("aw_autogen"):
            seed_text = st.session_state.pop("aw_autogen")
            with st.spinner("Writing article..."):
                voice = get_voice_context()
                pp = analyze_personal_patterns()
                pp_note = f"\nData: optimal char range {pp.get('optimal_char_range','N/A')}, {pp.get('top_question_pct',0)}% top tweets use questions, {pp.get('top_ellipsis_pct',0)}% use ellipsis." if pp else ""
                prompt = f"""Write a complete X Article based on this seed:\n\n\"{seed_text}\"\n\nFORMAT: X ARTICLE (1,500-2,000 words / 6-8 minute read)\n\nSTRUCTURE:\n- HEADLINE: 50-75 chars, include a number or specific claim\n- INTRO (2-3 paragraphs): Provocative claim, why it matters now.\n- 4 SECTIONS with subheadings: 2-3 short paragraphs, **bold key stats**\n- WHAT COMES NEXT: Bold prediction\n- CONCLUSION: 1-sentence hot take + debate question\n- PROMOTION: companion tweet idea\n\nRULES: Tyler's voice — direct, no hedging, former-player authority. Specific players/schemes/numbers only.{pp_note}"""
                st.session_state["aw_result"] = call_claude(prompt, system=voice, max_tokens=3000)

        st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

        # Section 2 — Choose a Raw Thoughts
        st.markdown("#### Or Choose a Raw Thoughts")
        dumps = load_json("brain_dumps.json", [])
        if "aw_sel_dump" not in st.session_state:
            st.session_state.aw_sel_dump = None

        if not dumps:
            st.markdown('<div class="output-box">No brain dumps yet. Create one in Raw Thoughts tool first.</div>', unsafe_allow_html=True)
        else:
            for j, d in enumerate(reversed(dumps[-6:])):
                ts = d.get("saved_at", "")[:16].replace("T", " ")
                preview = d.get("text", "")[:160]
                selected = st.session_state.aw_sel_dump == j
                border = "border-left:3px solid #FF6B00;" if selected else ""
                st.markdown(f"""<div class="tweet-card" style="{border}">
                    <div class="tweet-num">{ts}</div>
                    <div style="color:#d8d8e8;font-size:13px;">{preview}{'...' if len(d.get('text',''))>160 else ''}</div>
                </div>""", unsafe_allow_html=True)
                if st.button("→ Select", key=f"aw_bd_{j}", use_container_width=True):
                    st.session_state.aw_sel_dump = j
                    st.session_state.aw_sel_tweet = None
                    st.session_state["aw_autogen"] = d.get("text", "")
                    st.rerun()

        st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

        # Resolve seed text
        seed_text = ""
        if st.session_state.aw_sel_tweet is not None and top_tweets:
            seed_text = top_tweets[st.session_state.aw_sel_tweet].get("text", "")
        elif st.session_state.aw_sel_dump is not None and dumps:
            idx = st.session_state.aw_sel_dump
            rev = list(reversed(dumps[-6:]))
            if idx < len(rev):
                seed_text = rev[idx].get("text", "")

        manual = st.text_area("Or type / paste your own seed:", height=80, key="aw_manual",
            placeholder="Paste a tweet, idea, or topic to expand...")
        if manual.strip():
            seed_text = manual.strip()

        # Section 3 — Generation buttons
        ac1, ac2 = st.columns(2)
        with ac1:
            if st.button("↺ Scratch", use_container_width=True, key="aw_scratch", type="primary"):
                if seed_text:
                    with st.spinner("Writing full article..."):
                        voice = get_voice_context()
                        pp = analyze_personal_patterns()
                        pp_note = ""
                        if pp:
                            pp_note = f"\nData: optimal char range {pp.get('optimal_char_range','N/A')}, {pp.get('top_question_pct',0)}% top tweets use questions, {pp.get('top_ellipsis_pct',0)}% use ellipsis."
                        prompt = f"""Write a complete X Article based on this seed:\n\n\"{seed_text}\"\n\nFORMAT: X ARTICLE (1,500-2,000 words / 6-8 minute read)\n\nCONTEXT: X Articles grew 20x since Dec 2025 ($2.15M contest prizes). They keep users on-platform (no link penalty), generate 2+ min dwell time (+10 algorithm weight), and Premium subscribers get 2-4x reach boost. This is the highest priority content format.\n\nSTRUCTURE:\n- HEADLINE: 50-75 chars, include a number or specific claim, take a position. Numbers perform 2x better.\n- [IMAGE: Hero image placeholder — game photo, player photo, or custom graphic]\n- INTRO (2-3 paragraphs): Provocative claim or surprising stat, then why it matters right now.\n- SECTION 1 with subheading: 2-3 short paragraphs with **bold key stats** (2-3 per section). [IMAGE placeholder]\n- SECTION 2 with subheading: 2-3 short paragraphs, comparison list format if relevant.\n- SECTION 3 with subheading: Contrarian angle or insider perspective. [IMAGE placeholder]\n- SECTION 4 WHAT COMES NEXT: Bold prediction with reasoning.\n- CONCLUSION: **1-sentence bold hot take summary**, then discussion question to drive comments.\n- PROMOTION: Suggest a companion tweet pulling the most provocative stat from the article.\n\nRULES:\n- 1,500-2,000 words target (6-8 min read for optimal dwell time bonus)\n- Paragraphs: 2-4 sentences max\n- Subheadings every ~300 words\n- Bold key stats and claims (2-3 per section)\n- Tyler's voice: direct, no hedging, former-player authority\n- Every point must reference specific players/schemes/numbers\n- Include [IMAGE] markers where supporting visuals should go\n- End with debate invitation to drive replies{pp_note}"""
                        st.session_state["aw_result"] = call_claude(prompt, system=voice, max_tokens=3000)
        with ac2:
            if st.button("⚡ Outline", use_container_width=True, key="aw_outline", type="primary"):
                if seed_text:
                    with st.spinner("Generating outline..."):
                        voice = get_voice_context()
                        prompt = f"""Generate a detailed X Article outline based on:\n\n\"{seed_text}\"\n\nX Articles are the #1 priority format (20x growth since Dec 2025, 2+ min dwell time = +10 algorithm weight, Premium gets 2-4x reach).\n\nOutline format:\n- HEADLINE: 50-75 chars, include a number or specific claim (numbers perform 2x better)\n- [HERO IMAGE suggestion]\n- INTRO hook paragraph (provocative claim + why it matters now)\n- 4-6 section headers with subheadings every ~300 words, 2-3 bullet points each\n- Note where [IMAGE] placements go (2-3 supporting images)\n- WHAT COMES NEXT section with bold prediction\n- CONCLUSION: hot take + debate question\n- PROMOTION: companion tweet idea pulling most provocative stat\n\nTarget: 1,500-2,000 words (6-8 min read). Keep Tyler's voice: direct, opinionated, former-player authority."""
                        st.session_state["aw_result"] = call_claude(prompt, system=voice, max_tokens=1000)

        # Section 4 — Output + editor
        if st.session_state.get("aw_result"):
            st.markdown(f'<div class="output-box">{st.session_state["aw_result"]}</div>', unsafe_allow_html=True)
            edited = st.text_area("Edit article:", value=st.session_state["aw_result"], height=300, key="aw_editor")
            bc1, bc2, bc3 = st.columns(3)
            with bc1:
                if st.button("↓ Save Article", use_container_width=True, key="aw_save"):
                    articles = load_json("saved_articles.json", [])
                    articles.append({"content": edited, "seed": seed_text[:200], "saved_at": datetime.now().isoformat()})
                    save_json("saved_articles.json", articles)
                    st.success("Article saved.")
            with bc2:
                if st.button("⎘ Copy", use_container_width=True, key="aw_copy"):
                    st.code(edited, language=None)
                    st.info("Text displayed above -- copy from there.")
            with bc3:
                if st.button("↺ New", use_container_width=True, key="aw_new"):
                    for k in ["aw_result", "aw_sel_tweet", "aw_sel_dump"]:
                        st.session_state.pop(k, None)
                    st.rerun()

    # ── Right 1/3: My Articles ────────────────────────────────────────
    with col_saved:
        sc1, sc2 = st.columns([2, 1])
        with sc1:
            st.markdown("### My Articles")
        with sc2:
            if st.button("↺ Create New", key="aw_side_new", use_container_width=True):
                for k in ["aw_result", "aw_sel_tweet", "aw_sel_dump"]:
                    st.session_state.pop(k, None)
                st.rerun()
        articles = load_json("saved_articles.json", [])
        if not articles:
            st.markdown('<div class="output-box" style="text-align:center;padding:28px 16px;">'
                        '<div style="font-size:28px;margin-bottom:10px;opacity:0.4;">📄</div>'
                        '<div style="color:#555778;font-size:13px;line-height:1.6;">No saved articles yet.<br>'
                        '<span style="color:#404060;font-size:12px;">Select a tweet above, generate an article,<br>then click Save Article.</span></div>'
                        '</div>', unsafe_allow_html=True)
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
                    st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: TWEET HISTORY
# ═══════════════════════════════════════════════════════════════════════════
def sync_tweet_history(quick=False):
    """Fetch tweets and merge into local knowledge base.
    quick=True: fetch latest ~25 tweets (fast, every page load).
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
                    params=params, timeout=30,
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

    if quick:
        all_tweets = _fetch_window(f"from:{TYLER_HANDLE}")[:25]
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
            query = f"from:{TYLER_HANDLE} since:{since_str} until:{until_str}"
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
    return unique


def _load_tweet_history_gist() -> list:
    """Load tweet history from Gist (persistent across Streamlit redeploys).
    Gist API truncates large files — always fetch via raw_url."""
    if "_tweet_history_cache" in st.session_state:
        return st.session_state["_tweet_history_cache"]
    try:
        gist_id = st.secrets.get("GIST_ID", "15fb167bbbfdaa79d5ce11c266c3f652")
        resp = requests.get(f"https://api.github.com/gists/{gist_id}", headers=_gist_headers(), timeout=15)
        file_meta = resp.json().get("files", {}).get("hq_tweet_history.json", {})
        if file_meta:
            # Always use raw_url — Gist API truncates files over ~1MB in content field
            raw_url = file_meta.get("raw_url", "")
            if raw_url:
                raw_resp = requests.get(raw_url, timeout=30)
                tweets = json.loads(raw_resp.text)
                st.session_state["_tweet_history_cache"] = tweets
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
    """Save tweet history to Gist and local file. Slims tweets first to avoid truncation."""
    slimmed = [_slim_tweet(t) for t in tweets]
    st.session_state["_tweet_history_cache"] = slimmed
    save_json("tweet_history.json", slimmed)
    try:
        gist_id = st.secrets.get("GIST_ID", "15fb167bbbfdaa79d5ce11c266c3f652")
        payload = json.dumps({"files": {"hq_tweet_history.json": {"content": json.dumps(slimmed)}}})
        requests.patch(f"https://api.github.com/gists/{gist_id}", data=payload, headers=_gist_headers(), timeout=15)
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
        query = f"from:{TYLER_HANDLE} since:{since} until:{until}"
        cursor = ""
        for _ in range(5):  # up to 5 pages
            params = {"query": query, "queryType": "Latest", "count": "50"}
            if cursor:
                params["cursor"] = cursor
            resp = requests.get(
                "https://api.twitterapi.io/twitter/tweet/advanced_search",
                headers={"X-API-Key": TWITTER_API_IO_KEY},
                params=params, timeout=15,
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

    # Load stored tweets
    tweets = get_tweet_knowledge_base()

    # Header stats
    hc1, hc2, hc3, hc4 = st.columns([1, 1, 1, 2])
    with hc1:
        st.markdown(f'<div class="stat-card"><div class="stat-num">{len(tweets)}</div><div class="stat-label">Total Tweets</div></div>', unsafe_allow_html=True)
    with hc2:
        st.markdown(f'<div class="stat-card"><div class="stat-num" style="font-size:18px!important;letter-spacing:0;">@{TYLER_HANDLE}</div><div class="stat-label">Handle</div></div>', unsafe_allow_html=True)
    with hc3:
        last_sync = ""
        if tweets:
            dates = [t.get("createdAt", "") for t in tweets if t.get("createdAt")]
            if dates:
                last_sync = sorted(dates, reverse=True)[0][:10]
        st.markdown(f'<div class="stat-card"><div class="stat-num">{last_sync or "Never"}</div><div class="stat-label">Last Synced</div></div>', unsafe_allow_html=True)
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
    search = st.text_input("Search tweets and notes:", placeholder="Filter by keyword...", key="th_search")

    # Filter buttons as columns
    filters = ["All Posts", "Punchy Tweet", "Normal Posts", "Long Posts", "High Engagement",
               "Viral Posts", "Conversation Starters", "Evergreen", "Hot", "Original"]
    filter_type = st.selectbox("Filter", filters, key="th_filter")

    # AI filter buttons inline
    ac1, ac2, ac3, ac4 = st.columns(4)
    with ac1:
        if st.button("↑ Best Hooks", key="th_ai_hooks", use_container_width=True):
            top = sorted([t for t in tweets if not t.get("text","").startswith("@")], key=lambda t: t.get("likeCount", 0), reverse=True)[:20]
            hooks = [t.get("text", "").split(".")[0].split("...")[0].split("\n")[0][:100] for t in top]
            st.session_state["th_ai_result"] = "Your best-performing opening hooks:\n\n" + "\n".join([f"{i+1}. {h}" for i, h in enumerate(hooks)])
    with ac2:
        if st.button("↓ Missed Shots", key="th_ai_worst", use_container_width=True):
            worst = sorted([t for t in tweets if not t.get("text","").startswith("@")], key=lambda t: t.get("viewCount", 0) if t.get("viewCount", 0) > 0 else 999999)[:10]
            st.session_state["th_ai_result"] = "Lowest performing tweets (by views):\n\n" + "\n".join([f"- {t.get('text','')[:80]}... ({t.get('viewCount',0):,} views)" for t in worst])
    with ac3:
        if st.button("⊙ Style Report", key="th_ai_voice", use_container_width=True):
            sample = [t.get("text", "") for t in sorted([t for t in tweets if not t.get("text","").startswith("@")], key=lambda t: t.get("likeCount", 0), reverse=True)[:30]]
            with st.spinner("Analyzing your voice..."):
                result = call_claude(f"Analyze Tyler's writing voice based on these top-performing tweets. Identify patterns in: sentence length, punctuation style, opener types, tone, vocabulary, what makes his voice unique.\n\nTweets:\n" + "\n---\n".join(sample[:20]))
                st.session_state["th_ai_result"] = result
    with ac4:
        if st.button("≋ Top Subjects", key="th_ai_topics", use_container_width=True):
            sample = [f"{t.get('text','')[:100]} (likes:{t.get('likeCount',0)}, views:{t.get('viewCount',0)})" for t in sorted([t for t in tweets if not t.get("text","").startswith("@")], key=lambda t: t.get("likeCount", 0), reverse=True)[:40]]
            with st.spinner("Analyzing topics..."):
                result = call_claude(f"Analyze which TOPICS get Tyler the most engagement. Group his tweets by topic and show which topics consistently outperform. Be specific.\n\nTweets:\n" + "\n".join(sample))
                st.session_state["th_ai_result"] = result

    if st.session_state.get("th_ai_result"):
        st.markdown(f'<div class="output-box">{st.session_state["th_ai_result"]}</div>', unsafe_allow_html=True)

    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

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
            imp_url = st.text_input("Paste tweet URL to add to history:", placeholder="https://x.com/Tyler_Polumbus/status/...", key="hof_import_url", label_visibility="collapsed")
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
            medal = "#FFD700" if rank == 1 else "#C0C0C0" if rank == 2 else "#CD7F32" if rank == 3 else "#FF6B00"
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
                    sc_color = "#22c55e" if sc > 50 else "#FF6B00"
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
        tags_html = " ".join([f'<span class="tag{" tag-hot" if tg in hot_tags else ""}">{tg}</span>' for tg in tags])

        score_color = "#22c55e" if score >= 60 else "#FF6B00" if score >= 30 else "#ef4444"

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

    col_ideas, col_analyze = st.columns([1, 2])

    with col_ideas:
        st.markdown("### Bank")
        ideas = load_json("saved_ideas.json", [])
        if not ideas:
            st.markdown('<div class="output-box">No saved ideas. Use Creator Studio to save some.</div>', unsafe_allow_html=True)
        else:
            for i, idea in enumerate(reversed(ideas[-15:])):
                if st.button(idea.get("text", "")[:60] + "...", key=f"aa_idea_{i}", use_container_width=True):
                    st.session_state["aa_text"] = idea.get("text", "")

    with col_analyze:
        content = st.text_area("Content to Analyze:", height=160, key="aa_input",
            value=st.session_state.get("aa_text", ""),
            placeholder="Paste or type content to analyze against the algorithm...")
        char_len = len(content)
        cls = "char-over" if char_len > 280 else ""
        st.markdown(f'<div class="char-count {cls}">{char_len}/280</div>', unsafe_allow_html=True)

        if st.button("⚡ Analyze", use_container_width=True, key="aa_run"):
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
                        color = "#22c55e" if overall >= 75 else "#FF6B00" if overall >= 55 else "#ef4444"
                        st.markdown(f"""<div style="text-align:center; padding:20px 0;">
                            <div style="font-family:'Bebas Neue',sans-serif; font-size:80px; color:{color}; line-height:1;">{overall}</div>
                            <div style="color:#8888aa; font-size:13px; letter-spacing:2px; text-transform:uppercase;">Algorithm Score / 100</div>
                        </div>""", unsafe_allow_html=True)

                        for metric, val in data["scores"].items():
                            score = val.get("score", 0) if isinstance(val, dict) else val
                            note = val.get("note", "") if isinstance(val, dict) else ""
                            bar_color = "#22c55e" if score >= 8 else "#FF6B00" if score >= 6 else "#ef4444"
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


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════════════
def page_health_check():
    st.markdown('<div class="main-header">HEALTH <span>CHECK</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Full audit of your X account — posting cadence, engagement rate, hook quality, content mix, and actionable fixes.</div>', unsafe_allow_html=True)

    # What it checks
    st.markdown("""<div style="background:rgba(255,255,255,0.02);border:1px solid rgba(255,255,255,0.05);border-radius:14px;padding:18px 22px;margin-bottom:20px;">
    <div style="font-size:11px;color:#FF6B00;font-weight:700;letter-spacing:2px;margin-bottom:12px;">WHAT THIS AUDITS</div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">
      <div style="color:#8888aa;font-size:13px;">&#9632; Posting frequency &amp; consistency</div>
      <div style="color:#8888aa;font-size:13px;">&#9632; Hook quality (first-line scroll-stop rate)</div>
      <div style="color:#8888aa;font-size:13px;">&#9632; Engagement rate vs views</div>
      <div style="color:#8888aa;font-size:13px;">&#9632; Content mix (takes / analysis / humor)</div>
      <div style="color:#8888aa;font-size:13px;">&#9632; Underperforming tweets flagged</div>
      <div style="color:#8888aa;font-size:13px;">&#9632; Top 3 specific, actionable improvements</div>
    </div>
    </div>""", unsafe_allow_html=True)

    # Last run timestamp
    hc_cache = load_json("health_check_cache.json", {})
    last_run = hc_cache.get("last_run", "")
    if last_run:
        st.markdown(f'<div style="font-size:12px;color:#404060;margin-bottom:16px;">Last run: {last_run}</div>', unsafe_allow_html=True)

    hcb1, hcb2 = st.columns([2, 1])
    with hcb1:
        run_check = st.button("⚡ Run Account Audit", use_container_width=True, key="hc_run", type="primary")
    with hcb2:
        if hc_cache.get("data") and st.button("Clear Results", use_container_width=True, key="hc_clear"):
            save_json("health_check_cache.json", {})
            st.rerun()

    if run_check:
        with st.spinner("Pulling tweets and analyzing..."):
            tweets = fetch_tweets(f"from:{TYLER_HANDLE}", count=30)
            if not tweets:
                st.error("Could not fetch tweets. Check API key.")
                return

            tweet_texts = "\n---\n".join([f"Tweet: {t.get('text','')}\nLikes: {t.get('likeCount',0)} | RTs: {t.get('retweetCount',0)} | Replies: {t.get('replyCount',0)} | Views: {t.get('viewCount',0)}" for t in tweets[:20]])

            prompt = f"""Analyze Tyler Polumbus's (@tyler_polumbus) recent X activity against best practices.

Here are his recent 20 tweets with engagement:
{tweet_texts}

Provide a health check report:

1. HEALTH SCORE (0-100) - Overall account health
2. POSTING FREQUENCY - How often is he posting? Is it enough?
3. ENGAGEMENT RATE - Are likes/RTs/replies proportional to views?
4. HOOK QUALITY - Are his openers stopping scrolls?
5. CONTENT MIX - Good balance of takes, analysis, humor, engagement?
6. FLAGGED TWEETS - Any tweets that underperformed badly? Why?
7. TOP 3 RECOMMENDATIONS - Specific, actionable changes
8. WHAT'S WORKING - Top 2-3 things to keep doing

Return as JSON:
{{"health_score": 72, "sections": [{{"title": "...", "grade": "B+", "detail": "..."}}], "flagged": ["..."], "recommendations": ["..."]}}"""

            raw = call_claude(prompt, max_tokens=1200)
            try:
                json_match = re.search(r'\{.*\}', raw, re.DOTALL)
                data = json.loads(json_match.group()) if json_match else None
            except Exception:
                data = None

            if data and "health_score" in data:
                save_json("health_check_cache.json", {
                    "data": data,
                    "last_run": datetime.now().strftime("%Y-%m-%d %H:%M MST")
                })
                hc_cache = load_json("health_check_cache.json", {})
            else:
                st.markdown(f'<div class="output-box">{raw}</div>', unsafe_allow_html=True)

    # Render cached results (persists across sessions)
    data = hc_cache.get("data")
    if data and "health_score" in data:
        score = data["health_score"]
        color = "#22c55e" if score >= 75 else "#FF6B00" if score >= 55 else "#ef4444"
        st.markdown(f"""<div style="text-align:center; padding:20px 0;">
            <div style="font-family:'Bebas Neue',sans-serif; font-size:80px; color:{color}; line-height:1;">{score}</div>
            <div style="color:#8888aa; font-size:13px; letter-spacing:2px; text-transform:uppercase;">Health Score / 100</div>
        </div>""", unsafe_allow_html=True)

        for section in data.get("sections", []):
            with st.expander(f"{section.get('title', '')} — {section.get('grade', '')}"):
                st.markdown(f'<div class="output-box">{section.get("detail", "")}</div>', unsafe_allow_html=True)

        if data.get("flagged"):
            st.markdown("### Flagged Tweets")
            for f in data["flagged"]:
                st.markdown(f'<div class="output-box" style="border-left-color:#ef4444;">{f}</div>', unsafe_allow_html=True)

        if data.get("recommendations"):
            st.markdown("### Recommendations")
            for r in data["recommendations"]:
                st.markdown(f"- {r}")


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: ACCOUNT PULSE
# ═══════════════════════════════════════════════════════════════════════════
def page_account_pulse():
    st.markdown('<div class="main-header">ACCOUNT <span>PULSE</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Your account stats at a glance.</div>', unsafe_allow_html=True)

    # Auto-load on first visit this session
    if "ap_user" not in st.session_state:
        with st.spinner("Loading account data..."):
            user = fetch_user_info(TYLER_HANDLE)
            tweets = fetch_tweets(f"from:{TYLER_HANDLE}", count=50)
            st.session_state["ap_user"] = user
            st.session_state["ap_tweets"] = tweets

    if st.button("↺ Refresh", use_container_width=True, key="ap_load", type="primary"):
        with st.spinner("Refreshing..."):
            user = fetch_user_info(TYLER_HANDLE)
            tweets = fetch_tweets(f"from:{TYLER_HANDLE}", count=50)
            st.session_state["ap_user"] = user
            st.session_state["ap_tweets"] = tweets
            st.rerun()

    user = st.session_state.get("ap_user", {})
    tweets = st.session_state.get("ap_tweets", [])

    if not user:
        st.markdown('<div style="color:#555778;font-size:13px;padding:12px 0;">Could not load account data — check your API key.</div>', unsafe_allow_html=True)
        return

    followers = user.get("followersCount", 0)
    following = user.get("followingCount", 0)
    tweet_count = user.get("statusesCount", 0)
    ratio = round(followers / max(following, 1), 1)

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f'<div class="stat-card"><div class="stat-num">{followers:,}</div><div class="stat-label">Followers</div></div>', unsafe_allow_html=True)
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

        # Top 5 tweets
        st.markdown("### Top 5 Tweets (by likes)")
        top5 = sorted(tweets, key=lambda t: t.get("likeCount", 0), reverse=True)[:5]
        for t in top5:
            render_tweet_card(t)

        # AI analysis
        if st.button("⚡ Pulse", key="ap_ai"):
            with st.spinner("Analyzing patterns..."):
                tweet_summary = "\n".join([f"- {t.get('text','')[:100]} (Likes:{t.get('likeCount',0)}, Views:{t.get('viewCount',0)})" for t in tweets[:20]])
                result = call_claude(f"""Analyze Tyler's recent posting patterns:

Followers: {followers:,} | Following: {following:,} | Ratio: {ratio}x
Avg Likes: {avg_likes} | Avg Views: {avg_views} | Engagement: {eng_rate}%

Recent tweets:
{tweet_summary}

Give:
1. BEST POSTING TIME - When do his best tweets seem to land?
2. TOP GROWTH OPPORTUNITIES - 3 specific things to improve
3. CONTENT MIX ASSESSMENT - What should he post more/less of?
4. AVERAGE DAILY GROWTH ESTIMATE - Based on current trajectory""", max_tokens=800)
                st.markdown(f'<div class="output-box">{result}</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: ACCOUNT RESEARCHER
# ═══════════════════════════════════════════════════════════════════════════
def page_account_researcher():
    st.markdown('<div class="main-header">ACCOUNT <span>RESEARCHER</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Research any X account. Understand their strategy.</div>', unsafe_allow_html=True)

    col_left, col_right = st.columns([1, 1])

    with col_left:
        handle = st.text_input("Enter X handle:", placeholder="@username", key="ar_handle_input")
        if st.button("⚡ Research", use_container_width=True, key="ar_run", type="primary"):
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
  "tylers_edge": "one sentence on where Tyler's former-player credibility beats this account",
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

        # Recent searches
        st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)
        st.markdown("**Recent Searches**")
        recent = load_json("recent_searches.json", [])
        for r in reversed(recent[-8:]):
            if st.button(f"@{r.get('handle','')}  ·  {r.get('searched_at','')[:10]}", key=f"ar_recent_{r.get('handle')}", use_container_width=True):
                st.session_state["ar_handle_prefill"] = r.get("handle", "")

        # Top recent tweets
        tweets = st.session_state.get("ar_tweets", [])
        if tweets:
            hdl = st.session_state.get("ar_handle", "")
            ui = st.session_state.get("ar_user", {})
            st.markdown("<div style='margin-top:20px;'></div>", unsafe_allow_html=True)
            st.markdown(f"**@{hdl}** — {ui.get('followersCount',0):,} followers")
            for t in tweets[:8]:
                render_tweet_card(t)

    with col_right:
        analysis = st.session_state.get("ar_analysis")
        if not analysis:
            st.markdown('<div class="output-box" style="color:#555577; text-align:center; padding:40px;">Enter a handle and click Research Account</div>', unsafe_allow_html=True)
        else:
            hdl = st.session_state.get("ar_handle", "")
            st.markdown(f"""<div style="font-size:11px; letter-spacing:2px; color:#ff6b00; font-weight:700; margin-bottom:16px;">ACCOUNT ANALYSIS — @{hdl}</div>""", unsafe_allow_html=True)

            def ar_section(title, content):
                st.markdown(f'<div style="font-size:13px; font-weight:700; color:#e8e8f0; margin-top:20px; margin-bottom:6px;">{title}</div>', unsafe_allow_html=True)
                if isinstance(content, list):
                    items = "".join([f'<li style="color:#c0c0d8; font-size:13px; margin-bottom:4px;">{i}</li>' for i in content])
                    st.markdown(f'<ul style="margin:0; padding-left:18px;">{items}</ul>', unsafe_allow_html=True)
                else:
                    st.markdown(f'<div style="color:#c0c0d8; font-size:13px; line-height:1.6;">{content}</div>', unsafe_allow_html=True)

            if analysis.get("summary"):
                ar_section("Content Strategy Summary", analysis["summary"])

            if analysis.get("content_themes"):
                ar_section("Content Themes", analysis["content_themes"])

            if analysis.get("tone") or analysis.get("voice") or analysis.get("formatting"):
                st.markdown('<div style="font-size:13px; font-weight:700; color:#e8e8f0; margin-top:20px; margin-bottom:6px;">Writing Style</div>', unsafe_allow_html=True)
                for label, key in [("Tone", "tone"), ("Voice", "voice"), ("Formatting", "formatting")]:
                    if analysis.get(key):
                        st.markdown(f'<div style="color:#c0c0d8; font-size:13px; margin-bottom:6px;"><span style="color:#888899;">{label}:</span> {analysis[key]}</div>', unsafe_allow_html=True)

            if analysis.get("engagement_tactics"):
                ar_section("Engagement Tactics", analysis["engagement_tactics"])

            if analysis.get("unique_characteristics"):
                ar_section("Unique Characteristics", analysis["unique_characteristics"])

            if analysis.get("content_patterns"):
                ar_section("Content Patterns", analysis["content_patterns"])

            if analysis.get("tylers_edge"):
                ar_section("Tyler's Edge", analysis["tylers_edge"])

            if analysis.get("steal_worthy"):
                ar_section("Steal-Worthy Tactics", analysis["steal_worthy"])

            st.markdown("---")
            hdl_for_save = st.session_state.get("ar_handle", "")
            existing_styles = load_json("voice_styles.json", [])
            already_saved = any(s.get("handle") == hdl_for_save for s in existing_styles)
            if already_saved:
                st.markdown(f'<div style="color:#4ade80;font-size:13px;">✓ @{hdl_for_save} voice saved — available in Creator Studio</div>', unsafe_allow_html=True)
                if st.button("✕ Remove Voice Style", key="ar_remove_voice"):
                    existing_styles = [s for s in existing_styles if s.get("handle") != hdl_for_save]
                    save_json("voice_styles.json", existing_styles)
                    st.rerun()
            else:
                if st.button("➕ Save as Voice Style", key="ar_save_voice", use_container_width=True):
                    tweets_sample = [t.get("text", "") for t in st.session_state.get("ar_tweets", [])[:15] if not t.get("text","").startswith("@") and len(t.get("text","")) > 30]
                    style_entry = {
                        "name": f"@{hdl_for_save}",
                        "handle": hdl_for_save,
                        "summary": analysis.get("summary", "") + " Tone: " + analysis.get("tone", "") + " Voice: " + analysis.get("voice", ""),
                        "tweets": tweets_sample,
                        "saved_at": datetime.now().isoformat(),
                    }
                    existing_styles.append(style_entry)
                    save_json("voice_styles.json", existing_styles)
                    st.success(f"@{hdl_for_save} voice style saved! Now available in Creator Studio → Voice dropdown.")
                    st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: REPLY GUY
# ═══════════════════════════════════════════════════════════════════════════
def page_reply_guy():
    XURL = "/home/linuxbrew/.linuxbrew/bin/xurl"
    LISTS = {"Broncos Reporters": "1294328608417177604", "Nuggets": "1755985316752642285",
             "Morning Engagement": "2011987998699897046", "Work": "1182699241329721344"}

    st.markdown('<div class="main-header">REPLY <span>MODE</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Build your daily reply habit. 50 replies a day grows the account.</div>', unsafe_allow_html=True)

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

    # ── PART 1: Top Stats Bar ──
    c1, c2 = st.columns([3, 1])
    with c1:
        pct = min(reply_count / 50 * 100, 100)
        st.markdown(f'<div style="margin-bottom:8px;"><div style="display:flex;justify-content:space-between;margin-bottom:4px;">'
                    f'<span class="metric-label">Today&#39;s Replies</span><span class="metric-score">{reply_count}/50</span></div>'
                    f'<div class="progress-bar-bg"><div class="progress-bar-fill" style="width:{pct}%;"></div></div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="stat-card"><div class="stat-num">{streak}</div><div class="stat-label">Reply Streak</div></div>', unsafe_allow_html=True)
    day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    hist_map = {h["date"]: h["count"] for h in progress.get("history", [])}
    hist_map[today_str] = reply_count
    cols = st.columns(7)
    for d in range(6, -1, -1):
        dt = datetime.now() - timedelta(days=d)
        ds = dt.strftime("%Y-%m-%d")
        label = day_labels[dt.weekday()]
        cnt = hist_map.get(ds, 0)
        active_cls = "day-card day-card-active" if cnt > 0 else "day-card"
        cols[6 - d].markdown(
            f'<div class="{active_cls}">'
            f'<div class="day-card-label">{label}</div>'
            f'<div class="day-card-num">{cnt}</div>'
            f'</div>',
            unsafe_allow_html=True)

    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

    # Force rerun if flagged (workaround for st.rerun inside nested columns)
    if st.session_state.pop("rg_force_rerun", False):
        st.rerun()

    # ── PART 2: My Tweet Replies — Conversation Depth ──
    st.markdown("### My Tweet Replies -- Conversation Depth")
    btn_c1, btn_c2 = st.columns(2)
    with btn_c1:
        load_all = st.button("↓ My Replies", key="rg_load_all", use_container_width=True, type="primary")
    with btn_c2:
        load_verified = st.button("↓ Verified Replies", key="rg_load_verified", use_container_width=True, type="primary")

    if load_all or load_verified:
        with st.spinner("Fetching tweets and replies..."):
            my_tweets = fetch_tweets(f"from:{TYLER_HANDLE}", count=15)
            filtered = [t for t in my_tweets if int(t.get("replyCount", t.get("reply_count", 0))) >= 2][:8]
            st.session_state["rg_my_tweets"] = filtered
            for idx, tw in enumerate(filtered):
                tw_id = tw.get("id", "")
                replies = fetch_tweets(f"conversation_id:{tw_id}", count=25)
                # Exclude Tyler's own tweets from the conversation
                replies = [r for r in replies if r.get("author", {}).get("userName", "").lower() != TYLER_HANDLE.lower() and r.get("id", "") != tw_id]
                if load_verified:
                    replies = [r for r in replies if r.get("author", {}).get("isBlueVerified", False) or int(r.get("author", {}).get("followers", 0)) >= 5000]
                replies.sort(key=lambda r: int(r.get("likeCount", r.get("like_count", 0))), reverse=True)
                st.session_state[f"rg_replies_{idx}"] = replies[:8]

    for idx, tw in enumerate(st.session_state.get("rg_my_tweets", [])):
        txt = tw.get("text", "")
        likes = tw.get("likeCount", tw.get("like_count", 0))
        rts = tw.get("retweetCount", tw.get("retweet_count", 0))
        rpl = tw.get("replyCount", tw.get("reply_count", 0))
        views = tw.get("viewCount", tw.get("view_count", 0))
        st.markdown(f'<div class="tweet-card" style="border-left:3px solid #FF6B00;">'
                    f'<div style="color:#FF6B00;font-size:11px;font-weight:700;letter-spacing:1px;margin-bottom:6px;">YOUR TWEET</div>'
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
                st.markdown(f'<div style="font-weight:700;color:#FF6B00;font-size:13px;padding-top:8px;">@{rauthor}</div>'
                            f'<div style="font-size:11px;color:#555577;">{r_likes} likes</div>', unsafe_allow_html=True)
            with rc2:
                st.markdown(
                    f'<div style="font-size:14px;color:#d8d8e8;line-height:1.5;">{rtext[:250]}</div>'
                    f'<a href="{reply_url}" target="_blank" class="tweet-link">↗ view tweet</a>',
                    unsafe_allow_html=True)
            with rc3:
                reply_val = st.text_area("r", key=input_key, label_visibility="collapsed",
                    placeholder="Write reply...", height=auto_height(st.session_state.get(input_key, "")))

                # AI options picker
                if st.session_state.get(opts_key):
                    opts = st.session_state[opts_key]
                    st.markdown('<div style="font-size:11px;color:#666888;margin-bottom:4px;">Pick an option:</div>', unsafe_allow_html=True)
                    for oi, opt in enumerate(opts):
                        if st.button(f"{opt[:80]}{'...' if len(opt)>80 else ''}", key=f"rg_ri_opt_{idx}_{ri}_{oi}", use_container_width=True, type="secondary"):
                            st.session_state[input_key] = opt
                            del st.session_state[opts_key]
                            st.rerun()

                # Action row — uniform 4-button row
                ab1, ab2, ab3, ab4 = st.columns(4)
                with ab1:
                    if st.button("🤖 AI", key=f"rg_gen_{idx}_{ri}", use_container_width=True, help="Generate 3 reply options"):
                        with st.spinner(""):
                            raw = call_claude(
                                f'Tyler originally tweeted: "{txt[:200]}"\n\n'
                                f'@{rauthor} replied: "{rtext[:200]}"\n\n'
                                f'Write exactly 3 different reply options from Tyler. Under 150 chars each. '
                                f'Direct, ellipsis style, former NFL player. No emojis. '
                                f'One reply per line, no numbering.',
                                max_tokens=250)
                            opts = [o.strip() for o in raw.strip().split("\n") if o.strip()][:3]
                            if opts:
                                st.session_state[opts_key] = opts
                                if not st.session_state.get(input_key, "").strip():
                                    st.session_state[input_key] = opts[0]
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

    # ── PART 3: Engagement Targets — Table Layout ──
    st.markdown("### Engagement Targets")
    ctrl1, ctrl2, ctrl3 = st.columns([2, 1, 2])
    with ctrl1:
        list_source = st.selectbox("List", ["My Custom List"] + list(LISTS.keys()), key="rg_source", label_visibility="collapsed")
    with ctrl2:
        do_load = st.button("↓ Load", key="rg_load_posts", use_container_width=True, type="primary")
    with ctrl3:
        new_acc = st.text_input("Add account", key="rg_add_acc", placeholder="@handle", label_visibility="collapsed")

    if list_source == "My Custom List":
        custom_accounts = st.text_input("Accounts (comma-separated):", placeholder="@MikeKlis, @TroyRenck", key="rg_accounts")

    if do_load:
        with st.spinner("Fetching posts..."):
            all_tweets = []
            if list_source == "My Custom List":
                accs = [a.strip().lstrip("@") for a in (custom_accounts if list_source == "My Custom List" else "").replace(",", "\n").split("\n") if a.strip()]
                if new_acc.strip():
                    accs.append(new_acc.strip().lstrip("@"))
                for acc in accs[:12]:
                    tweets = fetch_tweets(f"from:{acc}", count=1)
                    for t in tweets:
                        t["_target_account"] = acc
                    all_tweets.extend(tweets)
            else:
                lid = LISTS.get(list_source, "")
                if lid:
                    try:
                        # Get list members first (list/tweets API is stale/cached)
                        mem_resp = requests.get(
                            "https://api.twitterapi.io/twitter/list/members",
                            headers={"X-API-Key": TWITTER_API_IO_KEY},
                            params={"list_id": lid, "count": 30},
                            timeout=30,
                        )
                        if mem_resp.status_code != 200:
                            st.error(f"Could not load list members: HTTP {mem_resp.status_code}")
                        else:
                            members = mem_resp.json().get("members", [])
                            handles = [m.get("userName") or m.get("username", "") for m in members if m.get("userName") or m.get("username")]
                            handles = [h for h in handles if h][:15]
                            if handles:
                                # Real-time search for recent tweets from list members
                                query = " OR ".join([f"from:{h}" for h in handles])
                                tweets = fetch_tweets(query, count=20)
                                for t in tweets:
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
                            else:
                                st.warning("List has no members or couldn't be read")
                    except Exception as e:
                        st.error(f"List fetch error: {str(e)[:100]}")
            st.session_state["rg_tweets"] = all_tweets

    # ── Engagement Targets header + controls ──
    tweets_data = st.session_state.get("rg_tweets", [])

    if tweets_data:
        # Sort by engagement score (likes*2 + replies*3 + retweets)
        tweets_data = sorted(tweets_data, key=lambda t: t.get("likeCount",0)*2 + t.get("replyCount",0)*3 + t.get("retweetCount",0), reverse=True)

        _actions_header = _load_actions_gist()
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
                        sug = call_claude(f'Tyler wants to reply to @{acc_}\'s tweet: "{text_[:150]}". Write ONE reply under 150 chars. Tyler\'s voice: direct, ellipsis, former NFL player. No emojis.', max_tokens=80)
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

        # Extract media image
        media_list = t.get("media", t.get("extendedEntities", {}).get("media", []) if isinstance(t.get("extendedEntities"), dict) else [])
        img_url = ""
        if media_list and isinstance(media_list, list):
            for m in media_list:
                if isinstance(m, dict):
                    img_url = m.get("mediaUrl", m.get("url", m.get("media_url_https", "")))
                    if img_url:
                        break

        _actions = _load_actions_gist()
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
        score_color = "#4ade80" if eng_score >= 20 else "#FF6B00" if eng_score >= 5 else "#555577"

        rc1, rc2, rc3 = st.columns([1, 3, 4])
        with rc1:
            st.markdown(
                f'<div style="padding-top:8px;">'
                f'<div style="font-weight:700;color:#FF6B00;font-size:14px;">@{acc}</div>'
                f'<div style="margin-top:6px;display:inline-block;background:rgba(255,255,255,0.04);border-radius:6px;padding:3px 8px;font-size:12px;color:{score_color};font-weight:600;">⚡ {eng_score}</div>'
                f'</div>',
                unsafe_allow_html=True)
        with rc2:
            img_html = f'<img src="{img_url}" style="width:100%;max-width:280px;border-radius:10px;margin-top:8px;display:block;" />' if img_url else ""
            st.markdown(
                f'<div style="font-size:15px;color:#d8d8e8;line-height:1.6;">{text[:220]}</div>'
                f'{img_html}'
                f'<div style="font-size:11px;color:#555577;margin-top:6px;">{created} · {likes}♡ · {rpl}↩ · {rts}↺</div>'
                f'<a href="{tweet_url}" target="_blank" class="tweet-link">↗ view tweet</a>',
                unsafe_allow_html=True)
        with rc3:
            reply_text = st.text_area("r", key=et_input_key, label_visibility="collapsed",
                placeholder="Write your reply...", height=auto_height(st.session_state.get(et_input_key, "")))

            # AI options picker
            if st.session_state.get(options_key):
                opts = st.session_state[options_key]
                st.markdown('<div style="font-size:11px;color:#666888;margin-bottom:4px;">Pick an option:</div>', unsafe_allow_html=True)
                for oi, opt in enumerate(opts):
                    if st.button(f"{opt[:80]}{'...' if len(opt)>80 else ''}", key=f"rg_opt_{i}_{oi}", use_container_width=True, type="secondary"):
                        st.session_state[et_input_key] = opt
                        del st.session_state[options_key]
                        st.rerun()

            # Action row — uniform pill buttons
            ab1, ab2, ab3, ab4 = st.columns(4)
            with ab1:
                if st.button("🤖 AI", key=f"rg_etg_{i}", use_container_width=True, help="Generate 3 reply options"):
                    with st.spinner(""):
                        raw = call_claude(
                            f'Tyler wants to reply to @{acc}\'s tweet: "{text[:150]}". '
                            f'Write exactly 3 different reply options, each under 150 chars. '
                            f'Tyler\'s voice: direct, uses ellipsis, former NFL player. No emojis. '
                            f'Format: one reply per line, no numbering, no labels.',
                            max_tokens=250)
                        opts = [o.strip() for o in raw.strip().split("\n") if o.strip()][:3]
                        if opts:
                            st.session_state[options_key] = opts
                            if not st.session_state.get(et_input_key,"").strip():
                                st.session_state[et_input_key] = opts[0]
                    st.rerun()
            with ab2:
                if et_already_liked:
                    st.markdown('<div style="text-align:center;padding:9px 0;font-size:16px;color:#4ade80;" title="Liked">♥</div>', unsafe_allow_html=True)
                else:
                    if st.button("♡ Like", key=f"rg_etl_{i}", use_container_width=True, help="Like on X"):
                        _proxy_tweet_action("like", tid)
                        _actions["liked"] = list(set(_actions["liked"] + [tid]))[-500:]
                        _save_actions_gist(_actions)
                        st.rerun()
            with ab3:
                if st.button("↗ Send", key=f"rg_ets_{i}", use_container_width=True, help="Send reply via proxy", type="primary"):
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
            with ab4:
                if st.button("✓ Done", key=f"rg_etrd_{i}", use_container_width=True, help="Mark done (replied on native X)", type="secondary"):
                    _bump_reply()
                    progress["count"] = progress.get("count", 0) + 1
                    save_json("reply_progress.json", progress)
                    _actions["replied"] = list(set(_actions["replied"] + [tid]))[-500:]
                    _save_actions_gist(_actions)
                    st.rerun()

        st.markdown('<hr style="margin:6px 0;border-color:rgba(255,255,255,0.04);">', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: INSPIRATION
# ═══════════════════════════════════════════════════════════════════════════
def page_inspiration():
    st.markdown('<div class="main-header">INSPIRATION <span>VAULT</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Save tweets that inspire you. Reference them when you need ideas.</div>', unsafe_allow_html=True)

    inspo = load_inspiration_gist()

    col_add, col_view = st.columns([1, 1])

    with col_add:
        st.markdown("### Save New Idea Bank")
        inspo_text = st.text_area("Tweet text:", height=100, key="insp_text",
            placeholder="Paste the tweet that caught your eye...")
        inspo_author = st.text_input("Author:", placeholder="@username", key="insp_author")
        inspo_tags = st.text_input("Tags (comma-separated):", placeholder="hook, thread, broncos", key="insp_tags")
        inspo_likes = st.number_input("Likes (optional):", min_value=0, value=0, key="insp_likes")
        inspo_views = st.number_input("Views (optional):", min_value=0, value=0, key="insp_views")

        if st.button("↓ Bank It", use_container_width=True, key="insp_save", type="primary"):
            if inspo_text.strip():
                inspo.append({
                    "text": inspo_text,
                    "author": inspo_author,
                    "tags": [t.strip() for t in inspo_tags.split(",") if t.strip()],
                    "likes": inspo_likes,
                    "views": inspo_views,
                    "saved_at": datetime.now().isoformat(),
                })
                save_inspiration_gist(inspo)
                st.success("Saved to vault.")
                st.rerun()

    with col_view:
        st.markdown(f"### Vault ({len(inspo)} saved)")
        search = st.text_input("Search:", placeholder="Filter by keyword or tag...", key="insp_search")
        tag_filter = st.text_input("Filter by tag:", placeholder="e.g. hook", key="insp_tag_filter")

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
            real_indices = list(range(len(inspo)))
            filtered_with_idx = [(inspo.index(item) if item in inspo else -1, item) for item in reversed(filtered[-20:])]
            for real_idx, item in filtered_with_idx:
                tags_html = " ".join([f'<span class="tag">{t}</span>' for t in item.get("tags", [])])
                metrics = ""
                if item.get("likes"):
                    metrics += f"Likes: {item['likes']:,} "
                if item.get("views"):
                    metrics += f"Views: {item['views']:,}"
                st.markdown(f"""<div class="tweet-card" style="position:relative;">
                    <a href="?page=Idea Bank&del_inspo={real_idx}" style="position:absolute;top:10px;right:12px;color:#333355;font-size:14px;text-decoration:none;line-height:1;" title="Delete">✕</a>
                    <div style="display:flex; justify-content:space-between; margin-bottom:6px; padding-right:20px;">
                        <span class="tweet-num">{item.get('author','')}</span>
                        <span style="font-size:11px; color:#444466;">{item.get('saved_at','')[:10]}</span>
                    </div>
                    <div style="color:#d8d8e8; font-size:14px; margin-bottom:8px; line-height:1.6;">{item.get('text','')}</div>
                    <div style="margin-bottom:4px;">{tags_html}</div>
                    <div style="font-size:11px; color:#666688;">{metrics}</div>
                </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# ROUTE TO PAGES
# ═══════════════════════════════════════════════════════════════════════════
page_map = {
    "Raw Thoughts": page_brain_dump,
    "Creator Studio": page_compose_ideas,
    "Content Advisor": page_content_coach,
    "Article Writer": page_article_writer,
    "Post History": page_tweet_history,
    "Algorithm Score": page_algo_analyzer,
    "Account Audit": page_health_check,
    "My Stats": page_account_pulse,
    "Profile Analyzer": page_account_researcher,
    "Reply Mode": page_reply_guy,
    "Idea Bank": page_inspiration,
}

# Sync strategy:
# - If tweet_history.json is empty or missing → full 500-tweet sync (one time, slow, builds the base)
# - If history exists → quick sync of last 25 only (fast, every load)
if not st.session_state.get("_tweets_synced"):
    try:
        _existing_history = _load_tweet_history_gist()
        if len(_existing_history) < 50:
            sync_tweet_history(quick=False)  # first-ever load: build full history
        else:
            sync_tweet_history(quick=True)   # history exists: just grab latest 25
    except Exception:
        pass
    st.session_state["_tweets_synced"] = True

st.markdown('<div class="main-watermark">MP</div>', unsafe_allow_html=True)

page_fn = page_map.get(page)
if page_fn:
    page_fn()

st.markdown("""
<div class="hq-footer">
  <a href="https://x.com/tyler_polumbus" target="_blank">@tyler_polumbus</a>
  <a href="#" target="_blank">PhD Show</a>
  <a href="#" target="_blank">Altitude 92.5</a>
</div>
""", unsafe_allow_html=True)
