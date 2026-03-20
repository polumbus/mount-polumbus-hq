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
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
.stApp { background: #0a0a0f; color: #e8e8f0; }
section[data-testid="stSidebar"] { background: #0d0d18 !important; border-right: 1px solid #1e1e30; }
section[data-testid="stSidebar"] .stButton > button { background: transparent !important; border: none !important; color: #aaaacc !important; text-align: left !important; padding: 6px 12px !important; font-size: 14px !important; font-weight: 400 !important; box-shadow: none !important; border-radius: 8px !important; }
section[data-testid="stSidebar"] .stButton > button:hover { background: #151525 !important; color: #e8e8f0 !important; transform: none !important; box-shadow: none !important; }
section[data-testid="stSidebar"] .stButton > button[kind="primary"] { background: #1a2a2a !important; color: #4ecdc4 !important; font-weight: 600 !important; border-left: 3px solid #4ecdc4 !important; border-radius: 0 8px 8px 0 !important; }
section[data-testid="stSidebar"] .stButton > button[kind="primary"]:hover { transform: none !important; box-shadow: none !important; }
.logo-block { padding: 8px 0 24px 0; text-align: center; }
.logo-title { font-family: 'Bebas Neue', sans-serif; font-size: 28px; letter-spacing: 3px; background: linear-gradient(135deg, #FF6B00, #FFB347); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; line-height: 1; display: block; }
.logo-sub { font-size: 10px; color: #555577; letter-spacing: 4px; text-transform: uppercase; margin-top: 4px; display: block; }
.main-header { font-family: 'Bebas Neue', sans-serif; font-size: 48px; letter-spacing: 2px; line-height: 1; margin-bottom: 4px; }
.main-header span { background: linear-gradient(135deg, #FF6B00, #FFB347); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.tool-desc { color: #8888aa; font-size: 14px; margin-bottom: 28px; }
.stat-card { background: #111120; border: 1px solid #1e1e35; border-radius: 12px; padding: 20px; text-align: center; }
.stat-num { font-family: 'Bebas Neue', sans-serif; font-size: 42px; color: #FF6B00; line-height: 1; }
.stat-label { font-size: 11px; color: #666688; text-transform: uppercase; letter-spacing: 2px; margin-top: 4px; }
.stTextArea textarea, .stTextInput input { background: #111120 !important; border: 1px solid #1e1e35 !important; border-radius: 10px !important; color: #e8e8f0 !important; font-family: 'DM Sans', sans-serif !important; font-size: 14px !important; }
.stTextArea textarea:focus, .stTextInput input:focus { border-color: #FF6B00 !important; box-shadow: 0 0 0 2px rgba(255,107,0,0.15) !important; }
.stTextArea textarea { min-height: 60px !important; resize: vertical !important; }
@media (max-width: 768px) {
    .main-header { font-size: 32px !important; }
    .tool-desc { font-size: 13px !important; }
    .stat-card { padding: 12px !important; }
    .stat-num { font-size: 28px !important; }
    .tweet-card { padding: 12px 14px !important; }
    .output-box { padding: 14px !important; font-size: 13px !important; }
    [data-testid="column"] { min-width: 100% !important; flex: 100% !important; }
    [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
    section[data-testid="stSidebar"] { min-width: 180px !important; max-width: 220px !important; }
    .stButton > button { padding: 8px 14px !important; font-size: 13px !important; }
    .nav-section { font-size: 9px !important; }
}
.stButton > button { background: linear-gradient(135deg, #FF6B00, #cc4a00) !important; color: white !important; border: none !important; border-radius: 10px !important; font-family: 'DM Sans', sans-serif !important; font-weight: 600 !important; font-size: 14px !important; padding: 10px 24px !important; transition: all 0.15s ease !important; letter-spacing: 0.3px; }
.stButton > button:hover { transform: translateY(-1px) !important; box-shadow: 0 6px 20px rgba(255,107,0,0.35) !important; }
.output-box { background: #111120; border: 1px solid #1e1e35; border-left: 3px solid #FF6B00; border-radius: 10px; padding: 20px 22px; margin: 12px 0; font-size: 14px; line-height: 1.7; color: #d8d8e8; white-space: pre-wrap; font-family: 'DM Sans', sans-serif; }
.tweet-card { background: #111120; border: 1px solid #1e1e35; border-radius: 12px; padding: 18px 20px; margin: 10px 0; position: relative; }
.tweet-card:hover { border-color: #FF6B00; transition: border-color 0.2s; }
.tweet-num { font-family: 'Bebas Neue', sans-serif; font-size: 13px; color: #FF6B00; letter-spacing: 1px; margin-bottom: 8px; }
.tag { display: inline-block; background: #1e1e35; border-radius: 6px; padding: 3px 10px; font-size: 11px; color: #8888cc; margin: 2px; font-weight: 500; }
.tag-hot { background: rgba(255,107,0,0.15); color: #FF6B00; border: 1px solid rgba(255,107,0,0.3); }
.section-divider { border: none; border-top: 1px solid #1e1e35; margin: 24px 0; }
.metric-label { font-size: 12px; color: #8888aa; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; }
.metric-score { font-family: 'Bebas Neue', sans-serif; font-size: 18px; color: #FF6B00; }
.score-bar-wrap { background: #1a1a2e; border-radius: 6px; height: 8px; width: 100%; margin: 6px 0 12px; overflow: hidden; }
.score-bar-fill { height: 100%; border-radius: 6px; transition: width 0.8s ease; }
.stSelectbox > div > div { background: #111120 !important; border-color: #1e1e35 !important; color: #e8e8f0 !important; }
.stSlider .st-br { background: #FF6B00 !important; }
.stTabs [data-baseweb="tab-list"] { background: #0d0d18 !important; border-radius: 10px; gap: 4px; padding: 4px; }
.stTabs [data-baseweb="tab"] { background: transparent !important; color: #8888aa !important; border-radius: 8px !important; font-weight: 600 !important; font-size: 13px !important; }
.stTabs [aria-selected="true"] { background: #FF6B00 !important; color: white !important; }
.stSpinner > div > div { border-top-color: #FF6B00 !important; }
::-webkit-scrollbar { width: 6px; }
::-webkit-scrollbar-track { background: #0a0a0f; }
::-webkit-scrollbar-thumb { background: #1e1e35; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #FF6B00; }
.nav-section { font-size: 10px; color: #555577; letter-spacing: 3px; text-transform: uppercase; font-weight: 700; margin: 16px 0 6px 4px; }
.char-count { font-size: 12px; color: #666688; text-align: right; margin-top: -10px; margin-bottom: 10px; }
.char-over { color: #ef4444 !important; }
.chat-msg { border-radius: 10px; padding: 16px 20px; margin: 10px 0; }
.chat-user { background: #111120; border-left: 1px solid #1e1e35; }
.chat-ai { background: #1a1a30; border-left: 3px solid #FF6B00; }
.chat-role { font-size: 11px; color: #666688; font-weight: 600; text-transform: uppercase; letter-spacing: 2px; margin-bottom: 8px; }
.progress-bar-bg { background: #1a1a2e; border-radius: 8px; height: 14px; width: 100%; overflow: hidden; }
.progress-bar-fill { height: 100%; border-radius: 8px; background: linear-gradient(90deg, #FF6B00, #FFB347); transition: width 0.5s; }
</style>
""", unsafe_allow_html=True)


# ─── Helpers ────────────────────────────────────────────────────────────────
def get_voice_context():
    """Build Tyler's voice context from his actual tweet history."""
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


def analyze_personal_patterns():
    """Analyze Tyler's tweet history to build personal scoring benchmarks."""
    tweets = load_json("tweet_history.json", [])
    if len(tweets) < 20:
        return None

    # Filter out RTs and replies
    originals = [t for t in tweets if not t.get("text", "").startswith("RT ") and not t.get("text", "").startswith("@")]
    if len(originals) < 10:
        return None

    # Sort by engagement
    for t in originals:
        t["_eng"] = t.get("likeCount", 0) + t.get("retweetCount", 0) * 3 + t.get("replyCount", 0) * 2

    sorted_tweets = sorted(originals, key=lambda t: t["_eng"], reverse=True)
    top_20pct = sorted_tweets[:max(5, len(sorted_tweets) // 5)]
    bottom_20pct = sorted_tweets[-max(5, len(sorted_tweets) // 5):]

    patterns = {}

    # Average character length
    patterns["top_avg_chars"] = sum(len(t.get("text", "")) for t in top_20pct) // len(top_20pct)
    patterns["bottom_avg_chars"] = sum(len(t.get("text", "")) for t in bottom_20pct) // len(bottom_20pct)
    patterns["optimal_char_range"] = (min(len(t.get("text", "")) for t in top_20pct), max(len(t.get("text", "")) for t in top_20pct))

    # Ellipsis usage
    patterns["top_ellipsis_pct"] = round(sum(1 for t in top_20pct if "..." in t.get("text", "")) / len(top_20pct) * 100)
    patterns["bottom_ellipsis_pct"] = round(sum(1 for t in bottom_20pct if "..." in t.get("text", "")) / len(bottom_20pct) * 100)

    # Question marks
    patterns["top_question_pct"] = round(sum(1 for t in top_20pct if "?" in t.get("text", "")) / len(top_20pct) * 100)
    patterns["bottom_question_pct"] = round(sum(1 for t in bottom_20pct if "?" in t.get("text", "")) / len(bottom_20pct) * 100)

    # Line breaks
    patterns["top_linebreaks_avg"] = round(sum(t.get("text", "").count("\n") for t in top_20pct) / len(top_20pct), 1)

    # Average engagement
    patterns["avg_likes"] = sum(t.get("likeCount", 0) for t in originals) // len(originals)
    patterns["avg_rts"] = sum(t.get("retweetCount", 0) for t in originals) // len(originals)
    patterns["avg_replies"] = sum(t.get("replyCount", 0) for t in originals) // len(originals)
    patterns["avg_views"] = sum(t.get("viewCount", 0) for t in originals) // len(originals)

    # Top 10 tweets as examples
    patterns["top_examples"] = [{"text": t.get("text", ""), "likes": t.get("likeCount", 0), "rts": t.get("retweetCount", 0), "replies": t.get("replyCount", 0)} for t in top_20pct[:10]]
    patterns["bottom_examples"] = [{"text": t.get("text", ""), "likes": t.get("likeCount", 0)} for t in bottom_20pct[:5]]

    # First-word patterns in top tweets
    first_words = [t.get("text", "").split()[0].lower() if t.get("text", "").split() else "" for t in top_20pct]
    patterns["top_first_words"] = first_words

    # Top reply-getters
    reply_sorted = sorted(originals, key=lambda t: t.get("replyCount", 0), reverse=True)[:5]
    patterns["top_reply_examples"] = [{"text": t.get("text", ""), "replies": t.get("replyCount", 0), "likes": t.get("likeCount", 0)} for t in reply_sorted]

    return patterns


def build_patterns_context(patterns):
    """Build a string context block from personal patterns for prompt injection."""
    if not patterns:
        return ""

    top_ex = "\n".join([f"  - \"{ex['text'][:120]}\" ({ex['likes']} likes, {ex['rts']} RTs, {ex['replies']} replies)" for ex in patterns.get("top_examples", [])[:10]])
    bottom_ex = "\n".join([f"  - \"{ex['text'][:120]}\" ({ex['likes']} likes)" for ex in patterns.get("bottom_examples", [])[:5]])
    reply_ex = "\n".join([f"  - \"{ex['text'][:120]}\" ({ex['replies']} replies, {ex['likes']} likes)" for ex in patterns.get("top_reply_examples", [])[:5]])
    first_words = ", ".join(patterns.get("top_first_words", [])[:10])
    opt_range = patterns.get("optimal_char_range", (0, 280))

    return f"""
TYLER'S PERSONAL TWEET BENCHMARKS (from his actual tweet history):

Character Length:
- Top tweets average {patterns.get('top_avg_chars', 0)} characters
- Bottom tweets average {patterns.get('bottom_avg_chars', 0)} characters
- Optimal range: {opt_range[0]}-{opt_range[1]} characters

Style Patterns (top performers):
- {patterns.get('top_ellipsis_pct', 0)}% use ellipsis (...) vs {patterns.get('bottom_ellipsis_pct', 0)}% in bottom tweets
- {patterns.get('top_question_pct', 0)}% end with a question vs {patterns.get('bottom_question_pct', 0)}% in bottom tweets
- Average {patterns.get('top_linebreaks_avg', 0)} line breaks per top tweet
- Common first words in top tweets: {first_words}

Engagement Averages:
- Average likes: {patterns.get('avg_likes', 0)}
- Average RTs: {patterns.get('avg_rts', 0)}
- Average replies: {patterns.get('avg_replies', 0)}
- Average views: {patterns.get('avg_views', 0)}

Top 10 Performing Tweets:
{top_ex}

Bottom 5 Performing Tweets:
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
    total = max(lines, char_lines) + 2
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
    headers = {"Content-Type": "application/json"}
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
    headers = {"Content-Type": "application/json"}
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

    # Try proxy server (Streamlit Cloud path — calls Tyler's local machine)
    try:
        return _call_claude_proxy(prompt, system or "", max_tokens)
    except Exception:
        pass  # Proxy down or unreachable — fall through to OAuth

    # Fallback: direct OAuth
    try:
        return _call_claude_oauth(prompt, system or "", max_tokens)
    except Exception as e:
        last_err = st.session_state.get("_oauth_last_error", "")
        return f"Error: {e} | {last_err}"


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
        ("Compose Ideas", "bulb"),
        ("Brain Dump", "pencil2"),
        ("Content Coach", "speech_balloon"),
        ("Article Writer", "memo"),
    ],
    "ENGAGE": [
        ("Reply Guy", "left_speech_bubble"),
        ("Inspiration", "sparkles"),
    ],
    "ANALYZE": [
        ("Tweet History", "clock3"),
        ("Algo Analyzer", "bar_chart"),
        ("Health Check", "stethoscope"),
        ("Account Pulse", "chart_with_upwards_trend"),
        ("Account Researcher", "mag"),
    ],
}

NAV_ICONS = {
    "Brain Dump": "✏️", "Compose Ideas": "💡", "Content Coach": "💬", "Article Writer": "📝",
    "Tweet History": "🕐", "Algo Analyzer": "📊", "Health Check": "🩺", "Account Pulse": "📈",
    "Account Researcher": "🔍", "Reply Guy": "🗨️", "Inspiration": "✨",
}

if "current_page" not in st.session_state:
    st.session_state.current_page = st.query_params.get("page", "Compose Ideas")

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

    st.markdown("---")
    st.markdown("""<div style="font-size: 11px; color: #333355; text-align: center;">
    @tyler_polumbus | PhD Show | Altitude 92.5
    </div>""", unsafe_allow_html=True)

page = st.session_state.current_page


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: BRAIN DUMP
# ═══════════════════════════════════════════════════════════════════════════
def page_brain_dump():
    st.markdown('<div class="main-header">BRAIN <span>DUMP</span></div>', unsafe_allow_html=True)
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
            if st.button("Give Me a Subject", use_container_width=True, key="bd_subject"):
                with st.spinner("Thinking..."):
                    result = call_claude("Give Tyler ONE specific content subject to write about right now. Denver sports. One sentence. Be specific and timely.", max_tokens=150)
                    st.session_state["bd_subject_result"] = result
        with bc2:
            if st.button("Generate Content Ideas", use_container_width=True, key="bd_ideas"):
                if dump_text.strip():
                    with st.spinner("Generating ideas..."):
                        result = call_claude(f'Tyler brain-dumped this:\n\n"{dump_text}"\n\nGenerate 5 specific content ideas from this brain dump. Each should be a different angle or format. Number them.', max_tokens=600)
                        st.session_state["bd_ideas_result"] = result
        with bc3:
            if st.button("Save Brain Dump", use_container_width=True, key="bd_save"):
                if dump_text.strip():
                    dumps = load_json("brain_dumps.json", [])
                    dumps.append({"text": dump_text, "saved_at": datetime.now().isoformat(), "timer_mins": st.session_state.bd_timer_mins})
                    save_json("brain_dumps.json", dumps)
                    st.success("Saved.")
        with bc4:
            if st.button("New Brain Dump", use_container_width=True, key="bd_new"):
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

        # Collapsible generation sections
        with st.expander("Tweet Ideas"):
            if st.button("Generate Tweet Ideas", key="bd_gen_tweets"):
                if dump_text.strip():
                    with st.spinner("Generating tweets..."):
                        result = call_claude(f'Tyler brain-dumped:\n\n"{dump_text}"\n\nWrite 5 tweet options from this. Each under 220 characters. Different angles and hooks. Number them. No hashtags. No emojis.', max_tokens=500)
                        st.session_state["bd_tweets"] = result
            if st.session_state.get("bd_tweets"):
                st.markdown(f'<div class="output-box">{st.session_state["bd_tweets"]}</div>', unsafe_allow_html=True)

        with st.expander("Long-form Post Idea"):
            if st.button("Generate Long-form Idea", key="bd_gen_long"):
                if dump_text.strip():
                    with st.spinner("Generating..."):
                        result = call_claude(f'Tyler brain-dumped:\n\n"{dump_text}"\n\nWrite a long-form X post (400-600 characters) that digs deeper into this topic. Tyler\'s voice: authoritative, from the trenches, direct. Include a strong opening hook.', max_tokens=500)
                        st.session_state["bd_longform"] = result
            if st.session_state.get("bd_longform"):
                st.markdown(f'<div class="output-box">{st.session_state["bd_longform"]}</div>', unsafe_allow_html=True)

        with st.expander("Video Script Outline"):
            if st.button("Generate Video Outline", key="bd_gen_video"):
                if dump_text.strip():
                    with st.spinner("Generating..."):
                        result = call_claude(f'Tyler brain-dumped:\n\n"{dump_text}"\n\nCreate a 3-5 minute video script outline:\n- Cold open hook (15 seconds)\n- 3-4 main talking points with bullet notes\n- Closing line / CTA\n\nKeep it conversational. Tyler talks like a former player, not a news anchor.', max_tokens=600)
                        st.session_state["bd_video"] = result
            if st.session_state.get("bd_video"):
                st.markdown(f'<div class="output-box">{st.session_state["bd_video"]}</div>', unsafe_allow_html=True)

    with col_saved:
        st.markdown("### Saved Brain Dumps")
        dumps = load_json("brain_dumps.json", [])
        if not dumps:
            st.markdown('<div class="output-box">No saved brain dumps yet.</div>', unsafe_allow_html=True)
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
    st.markdown('<div class="main-header">COMPOSE <span>IDEAS</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Draft, refine, and save your content ideas.</div>', unsafe_allow_html=True)

    col_main, col_saved = st.columns([2, 1])

    # Auto-repurpose from Inspiration Vault click
    if st.session_state.get("ci_auto_repurpose") and st.session_state.get("ci_repurpose_seed"):
        seed = st.session_state.pop("ci_repurpose_seed")
        st.session_state.pop("ci_auto_repurpose", None)
        st.session_state["ci_text"] = seed
        with st.spinner("Repurposing in your voice..."):
            repurpose_prompt = f"""Repurpose this tweet in Tyler Polumbus's voice.

Original tweet:
\"{seed}\"

Tyler's voice: direct, no hashtags, ellipsis signature, former-player authority, concise.
Keep the core insight but make it sound like Tyler wrote it from scratch.

Give the repurposed tweet, then show character count."""
            st.session_state["ci_repurposed"] = call_claude(repurpose_prompt)

    with col_main:
        tweet_text = st.text_area("Write your tweet idea:", height=auto_height(st.session_state.get("ci_text", ""), min_h=140), key="ci_text",
            placeholder="Start typing your idea here...")
        char_len = len(tweet_text)
        cls = "char-over" if char_len > 280 else ""
        st.markdown(f'<div class="char-count {cls}">{char_len}/280</div>', unsafe_allow_html=True)

        fc1, fc2 = st.columns(2)
        with fc1:
            fmt = st.selectbox("Format", ["Short Tweet", "Long Tweet", "Thread", "Article"], key="ci_format")
        with fc2:
            voice = st.selectbox("Voice", ["Default", "Critical", "Homer", "Sarcastic"], key="ci_voice",
                help="Default = natural | Critical = tough love | Homer = ultra positive | Sarcastic = dry wit")

        sc1, sc2, sc3, sc4, sc5 = st.columns(5)
        with sc1:
            banger = st.button("MAKE ME A BANGER", key="ci_banger", use_container_width=True)
        with sc2:
            repurpose = st.button("Repurpose", key="ci_repurpose", use_container_width=True)
        with sc3:
            build_this = st.button("Build This", key="ci_build", use_container_width=True)
        with sc4:
            engage = st.button("Algorithm Grades", key="ci_engage", use_container_width=True)
        with sc5:
            biz = st.button("Preview", key="ci_biz", use_container_width=True)
        viral = False  # removed from main buttons

        # Voice modifier for prompts
        voice_mod = ""
        if voice == "Critical":
            voice_mod = """Voice style: CRITICAL — Accountability mode. Tyler as the tough-love analyst.

ALGORITHM-SAFE CRITICAL RULES:
- ALWAYS pair criticism with a specific stat, fact, or film observation. "The O-line allowed pressure on 42% of dropbacks" is safe. "This team sucks" gets throttled.
- Frame as accountability, never contempt. Energy: "I'm saying this because I believe this team can be better."
- NEVER attack individual fans, players personally, or use all-caps rants. X penalizes combative tone with up to 80% reach reduction.
- End with a constructive angle or question. This converts criticism into conversation (replies = 27x a like).
- Think: disappointed parent who played in the NFL, not angry fan on a barstool.
- Skeptical, direct, calls out what others won't say. But always backed by evidence or experience."""
        elif voice == "Homer":
            voice_mod = """Voice style: HOMER — Rally mode. Tyler as the ultimate believer.

ALGORITHM-BOOSTED HOMER RULES:
- Positive sentiment is explicitly boosted by X's Grok sentiment analysis. Zero risk of negative signal penalties.
- ALWAYS tie optimism to something specific. "I love what I'm seeing from Troy Franklin's route-running" beats "LET'S GOOOO."
- Defend positions with data or insider perspective. "Everyone's writing off this team, but the underlying numbers tell a different story" is credible homer content.
- Celebrate with substance. After wins: "Here's what went RIGHT" with specific plays/players.
- Rally the fanbase by making them feel included. Use "we" language. Fans follow sports accounts to feel good about their fandom.
- No blind cheerleading — genuine optimism grounded in real football knowledge from Tyler's 8 years in the league."""
        elif voice == "Sarcastic":
            voice_mod = """Voice style: SARCASTIC — Dry wit, deadpan delivery.

ALGORITHM-SAFE SARCASTIC RULES:
- Sarcasm through understatement, not mockery. "Oh cool, the Broncos did nothing again. Shocking." not "This franchise is a joke."
- The humor comes from stating the obvious with fake surprise or calm acceptance of absurdity.
- Dry, deadpan — like a former player who has seen everything and nothing surprises him anymore.
- NEVER punch down at fans or individuals. Punch at situations, decisions, outcomes.
- Sarcasm should make people laugh AND think. If it's just mean, it triggers blocks (-148x penalty).
- End with a genuine point wrapped in wit — the sarcasm is the delivery method for real analysis.
- Think: press conference energy where the player says something dry and the room cracks up.
- Still Tyler's voice — former NFL authority, but with an eyebrow raised."""
        else:
            voice_mod = """Voice style: DEFAULT — Tyler's natural voice. The balanced authority.

This is the algorithm's sweet spot. Balanced content generates the most diverse engagement (bookmarks + retweets + replies) which maximizes algorithmic value.
- Direct, confident, former-player authority
- Mix of positive and critical in the same post when appropriate
- Lead with insight, not just opinion
- Sentence structure: short punchy lines, ellipsis as signature, questions to drive replies
- 70% positive/neutral, 30% critical — the optimal content ratio for sustained growth"""

        # Pull live patterns for format templates (evolves with each sync)
        _fp = analyze_personal_patterns()
        _fp_avg = _fp.get("top_avg_chars", 162) if _fp else 162
        _fp_q = _fp.get("top_question_pct", 28) if _fp else 28
        _fp_ell = _fp.get("top_ellipsis_pct", 28) if _fp else 28
        _fp_range = _fp.get("optimal_char_range", (40, 387)) if _fp else (40, 387)
        _fp_hooks = []
        if _fp and _fp.get("top_examples"):
            _fp_hooks = [ex.get("text", "")[:80] for ex in _fp["top_examples"][:5]]
        _hooks_str = "\n".join([f"  - \"{h}...\"" for h in _fp_hooks]) if _fp_hooks else "  (sync tweets to see your top hooks)"

        format_mod = ""
        if fmt == "Short Tweet":
            format_mod = f"""FORMAT: SHORT TWEET (under 200 characters)

TYLER'S LIVE DATA (from synced tweet history — updates every sync):
- Average top tweet length: {_fp_avg} chars
- Optimal range: {_fp_range[0]}-{_fp_range[1]} chars
- {_fp_q}% of top tweets use questions (algorithm: replies = 13.5x a like)
- {_fp_ell}% of top tweets use ellipsis (his signature)
- Top performing hooks to model after:
{_hooks_str}

STRUCTURE:
[Confrontational hook or bold declaration]

[Punch line, trailing thought, or question]

RULES:
- Under 200 characters total
- Use line break between hook and payoff
- No hashtags, no links, no emojis
- End with question OR ellipsis, not both
- Must stop the scroll in the first 8 words
- Model the hook after one of Tyler's top hooks above

IMAGE RECOMMENDATION:
- Hot take / opinion → NO image (text-only gets higher engagement rate on short tweets)
- Stat or comparison → YES — simple stat graphic
- Reaction to news → OPTIONAL — screenshot of the news article headline
- If no image: that's fine, text-only short tweets outperform media posts by 30% on engagement rate"""

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
                patterns_ctx = build_patterns_context(pp) if pp else ""
                banger_prompt = f"""Tyler drafted this tweet. Rewrite it to score 9+ on every X algorithm metric AND match his proven winning style.

Draft: "{tweet_text}"

{voice_mod}

{format_mod}
{patterns_ctx}

Rules:
- Reading Level (7th-9th grade)
- No Hashtags, Links, Tags, Emojis
- Hook & Pattern Breakers (first line stops the scroll)
{"- Optimal character range: " + str(pp.get("optimal_char_range", (0, 280))[0]) + "-" + str(pp.get("optimal_char_range", (0, 280))[1]) + " characters" if pp else ""}

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
                raw = call_claude(banger_prompt)
                try:
                    raw_clean = raw.strip()
                    if raw_clean.startswith("```"):
                        raw_clean = raw_clean.split("\n", 1)[1].rsplit("```", 1)[0]
                    banger_data = json.loads(raw_clean)
                    st.session_state["ci_banger_data"] = banger_data
                    st.session_state["ci_last_action"] = {"type": "banger", "text": tweet_text, "fmt": fmt, "voice": voice}
                    st.session_state.pop("ci_result", None)
                except Exception:
                    result = raw  # fallback to plain text
        elif viral and tweet_text.strip():
            with st.spinner("Analyzing viral potential against your history..."):
                history = get_tweet_knowledge_base()
                pp = analyze_personal_patterns()
                patterns_ctx = build_patterns_context(pp) if pp else ""

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
                pp = analyze_personal_patterns()
                patterns_ctx = build_patterns_context(pp) if pp else ""

                grade_prompt = f"""Grade this tweet against X's CONFIRMED algorithm signals (from the open-sourced recommendation code) AND Tyler's personal tweet performance history.

CONFIRMED X ALGORITHM SIGNAL WEIGHTS:
- Author replies to replies on own tweet: 150x a like (THE #1 signal)
- Replies from others: 27x a like
- Profile clicks: 24x a like
- Dwell time (2+ min): 20x a like
- Bookmarks: 20x a like
- Retweets: 2x a like
- Likes: 1x (baseline)
- External links: CONFIRMED 30-50% reach penalty
- 3+ hashtags: CONFIRMED ~40% reach penalty
- Negative/combative tone: reduces distribution since 2026 (Grok sentiment analysis)
- First 30 minutes are critical — early engagement determines distribution

Tweet: "{tweet_text}"
{patterns_ctx}

{format_mod}

This draft is {len(tweet_text)} characters.
{"It " + ("contains" if "?" in tweet_text else "does NOT contain") + " a question mark." if pp else ""}
{"It " + ("uses" if "..." in tweet_text else "does NOT use") + " ellipsis." if pp else ""}

Score each category 1-10. Each detail MUST reference Tyler's actual data or a specific confirmed algorithm signal.

Return ONLY this JSON:
{{
    "algorithm_score": [0-100 for algorithm compliance],
    "tyler_score": [0-100 for matching Tyler's proven patterns],
    "grades": [
        {{"name": "Hook Strength (Dwell Time)", "score": 8, "detail": "The algorithm measures dwell time — how long users pause on your post. A strong hook = longer dwell = algorithmic boost. Compare this first line to Tyler's top hooks.", "benchmark": "Top hook: '[his best first line]' ([X] likes)"}},
        {{"name": "Conversation Catalyst", "score": 7, "detail": "Replies are 27x a like. Author replying to replies is 150x. Is this tweet structured so Tyler can meaningfully reply to responses? Open-ended? Invites debate? Compare to his top reply-getters.", "benchmark": "Top reply-getter: '[snippet]' ([X] replies)"}},
        {{"name": "Bookmark Worthiness", "score": 6, "detail": "Bookmarks are 20x a like — the 'silent like.' Does this tweet have save-for-later value? Reference, insight, or take worth returning to?", "benchmark": "Reference-worthy content scores highest"}},
        {{"name": "Share/Quote Potential", "score": 7, "detail": "Retweets are 20x a like. Would someone share this with THEIR audience? Hot takes, surprising stats, and strong opinions get shared most.", "benchmark": "Tyler's most shared: '[snippet]' ([X] RTs)"}},
        {{"name": "Engagement Triggers", "score": 7, "detail": "Questions, ellipsis, line breaks, open-ended statements. Compare to Tyler's patterns.", "benchmark": "[X]% of his top tweets use questions, [X]% use ellipsis"}},
        {{"name": "Algorithm Compliance", "score": 9, "detail": "External links get 30-50% penalty. 3+ hashtags get 40% penalty. Negative tone reduces reach. Check for all confirmed penalties.", "benchmark": "No links, 0-2 hashtags, constructive tone"}},
        {{"name": "Dwell Time Potential", "score": 7, "detail": "Beyond the hook — does the FULL tweet reward reading? Posts viewed <3 seconds get negative quality signals. Posts with 2+ min dwell get 20x boost. Line breaks, story structure, and payoff increase dwell.", "benchmark": "Multi-paragraph tweets with payoff perform best"}},
        {{"name": "Voice Match", "score": 8, "detail": "How closely does this match Tyler's proven winning patterns? Sentence length, punctuation style, authority level. Reference his actual style data.", "benchmark": "Tyler's voice: [key patterns]"}}
    ],
    "personal_insights": [
        "Data-driven insight comparing this draft to Tyler's actual patterns",
        "Another data-driven insight with specific numbers from his history"
    ],
    "suggestions": ["specific improvement 1 referencing confirmed algorithm signals", "specific improvement 2", "specific improvement 3"]
}}"""
                raw = call_claude(grade_prompt)
                try:
                    json_match = re.search(r'\{.*\}', raw, re.DOTALL)
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

{voice_mod}

{format_mod}

TASK: Extract the best version of this idea and write the finished tweet. This is NOT a rewrite — you are crafting the actual tweet from a raw concept description.

- Strong hook — first line stops the scroll
- No hashtags, no emojis
- 7th-9th grade reading level
- End with something that makes people reply or argue
- Algorithm optimized: strong opinion, relatable, invites engagement

Give ONLY the finished tweet/thread/article. No explanation. No character count. No commentary."""
                st.session_state["ci_result"] = call_claude(build_prompt)
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

{voice_mod}

{format_mod}

- Strong hook in the first line
- Invites engagement/replies
- No hashtags, no emojis
- 7th-9th grade reading level

Give the repurposed tweet, then show character count."""
                repurposed = call_claude(repurpose_prompt)
                st.session_state["ci_repurposed"] = repurposed
                st.session_state["ci_last_action"] = {"type": "repurpose", "text": tweet_text, "fmt": fmt, "voice": voice}
                st.session_state.pop("ci_result", None)
                st.session_state.pop("ci_viral_data", None)
                st.session_state.pop("ci_grades", None)
                st.session_state.pop("ci_preview", None)

        if result:
            st.session_state["ci_result"] = result
            st.session_state.pop("ci_viral_data", None)
            st.session_state.pop("ci_grades", None)
            st.session_state.pop("ci_preview", None)
            st.session_state.pop("ci_repurposed", None)
            st.session_state.pop("ci_banger_data", None)

        # Render results based on which button was pressed

        # Refresh button — re-runs last action with current format/voice
        last = st.session_state.get("ci_last_action")
        has_result = st.session_state.get("ci_result") or st.session_state.get("ci_banger_data") or st.session_state.get("ci_repurposed")
        if last and has_result:
            if st.button("↺  Regenerate with current format/voice", key="ci_refresh", use_container_width=True):
                st.session_state["ci_refresh_trigger"] = True
                st.rerun()

        if st.session_state.pop("ci_refresh_trigger", False):
            last = st.session_state.get("ci_last_action", {})
            _rtype = last.get("type")
            _rtext = last.get("text", tweet_text)
            _rfmt = last.get("fmt", fmt)
            _rvoice = last.get("voice", voice)
            if _rtype in ("build_this", "repurpose", "banger"):
                st.session_state["ci_refresh_pending"] = {"type": _rtype, "text": _rtext}
                st.session_state["ci_last_action"] = {"type": _rtype, "text": _rtext, "fmt": fmt, "voice": voice}

        # Handle refresh pending
        _pending = st.session_state.pop("ci_refresh_pending", None)
        if _pending:
            _rtype = _pending["type"]
            _rtext = _pending["text"]
            if _rtype == "build_this":
                with st.spinner("Rebuilding..."):
                    build_prompt = f"""Tyler Polumbus has a tweet concept/angle he wants turned into a finished tweet. Materialize this concept into the actual tweet.

CONCEPT/ANGLE:
\"{_rtext}\"

{voice_mod}

{format_mod}

TASK: Extract the best version of this idea and write the finished tweet. This is NOT a rewrite — you are crafting the actual tweet from a raw concept description.

- Strong hook — first line stops the scroll
- No hashtags, no emojis
- 7th-9th grade reading level
- End with something that makes people reply or argue

Give ONLY the finished tweet/thread/article. No explanation. No character count. No commentary."""
                    st.session_state["ci_result"] = call_claude(build_prompt)
                    st.session_state.pop("ci_banger_data", None)
                    st.session_state.pop("ci_repurposed", None)
            elif _rtype == "repurpose":
                with st.spinner("Repurposing..."):
                    rp = f"""Someone else wrote this tweet. Rewrite it in Tyler Polumbus's voice.\n\n{voice_mod}\n\nOriginal: \"{_rtext}\"\n\n{format_mod}\n\nGive the repurposed tweet, then character count."""
                    st.session_state["ci_repurposed"] = call_claude(rp)
                    st.session_state.pop("ci_result", None)
                    st.session_state.pop("ci_banger_data", None)

        # Banger — 3 separate boxes + recommendation at bottom
        if st.session_state.get("ci_banger_data"):
            bd = st.session_state["ci_banger_data"]
            for opt_key, pattern_key, idx in [("option1","option1_pattern",1),("option2","option2_pattern",2),("option3","option3_pattern",3)]:
                opt_text = bd.get(opt_key, "")
                pattern = bd.get(pattern_key, "")
                if opt_text:
                    if pattern:
                        st.markdown(f'<div style="font-size:11px; color:#666688; letter-spacing:1px; margin-top:16px; margin-bottom:4px;">OPTION {idx} — {pattern}</div>', unsafe_allow_html=True)
                    edited_opt = st.text_area("", value=opt_text, height=auto_height(opt_text), key=f"ci_banger_opt_{idx}")
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("Save", key=f"ci_banger_save_{idx}", use_container_width=True):
                            ideas = load_json("saved_ideas.json", [])
                            ideas.append({"text": edited_opt, "format": fmt, "category": "Uncategorized", "saved_at": datetime.now().isoformat()})
                            save_json("saved_ideas.json", ideas)
                            st.success("Saved.")
                    with b2:
                        if st.button("Use This", key=f"ci_banger_use_{idx}", use_container_width=True):
                            st.session_state["ci_text"] = edited_opt
                            st.session_state.pop("ci_banger_data", None)
                            st.rerun()
            if bd.get("recommendation"):
                st.markdown(f'<div style="background:#0d0d18; border:1px solid #2a2a4a; border-radius:8px; padding:14px; margin-top:20px; font-size:13px; color:#c0c0d8; line-height:1.6;"><span style="color:#ff6b00; font-weight:700; font-size:11px; letter-spacing:1px;">RECOMMENDATION</span><br><br>{bd["recommendation"]}</div>', unsafe_allow_html=True)

        # General result — editable text area
        if st.session_state.get("ci_result"):
            st.markdown('<div style="font-weight:700; margin:12px 0 8px;">Result:</div>', unsafe_allow_html=True)
            edited = st.text_area("Edit your result:", value=st.session_state["ci_result"], height=auto_height(st.session_state.get("ci_result","")), key="ci_result_edit")
            rc1, rc2, rc3 = st.columns(3)
            with rc1:
                if st.button("Save As New Idea", key="ci_save_result", use_container_width=True):
                    ideas = load_json("saved_ideas.json", [])
                    ideas.append({"text": edited, "format": fmt, "category": "Uncategorized", "saved_at": datetime.now().isoformat()})
                    save_json("saved_ideas.json", ideas)
                    st.success("Saved.")
            with rc2:
                if st.button("Copy to Draft", key="ci_copy_draft", use_container_width=True):
                    st.session_state["ci_text"] = edited
                    st.session_state.pop("ci_result", None)
                    st.rerun()

        # Repurposed content — editable
        if st.session_state.get("ci_repurposed"):
            st.markdown('<div style="font-weight:700; font-size:16px; margin:16px 0 8px;">Repurposed Content</div>', unsafe_allow_html=True)
            edited_rp = st.text_area("Edit repurposed tweet:", value=st.session_state["ci_repurposed"], height=auto_height(st.session_state.get("ci_repurposed","")), key="ci_rp_edit")
            rpc1, rpc2, rpc3 = st.columns(3)
            with rpc1:
                if st.button("Save As New Idea", key="ci_save_rp", use_container_width=True):
                    ideas = load_json("saved_ideas.json", [])
                    ideas.append({"text": edited_rp, "format": fmt, "category": "Uncategorized", "saved_at": datetime.now().isoformat()})
                    save_json("saved_ideas.json", ideas)
                    st.success("Saved.")
            with rpc2:
                if st.button("Copy to Draft", key="ci_copy_rp", use_container_width=True):
                    st.session_state["ci_text"] = edited_rp
                    st.session_state.pop("ci_repurposed", None)
                    st.rerun()

        # Viral Potential Analysis
        if st.session_state.get("ci_viral_data"):
            vd = st.session_state["ci_viral_data"]
            total = vd.get("total_predicted_engagement", 0)
            conf = vd.get("confidence", "Medium")
            compared = vd.get("compared_to_average", "Average")
            conf_color = "#22c55e" if conf == "High" else "#FF6B00" if conf == "Medium" else "#ef4444"
            comp_color = "#22c55e" if "Above" in compared else "#FF6B00" if "Average" in compared else "#ef4444"

            st.markdown(f"""<div class="output-box">
                <div style="font-family:'Bebas Neue',sans-serif; font-size:22px; letter-spacing:1px; margin-bottom:16px;">Viral Potential Analysis</div>
                <div style="font-size:13px; color:#8888aa; margin-bottom:16px;">Analyzing your tweet's potential performance based on your historical data.</div>
                <div style="background:#0d0d18; border:1px solid #1e1e35; border-radius:10px; padding:16px; margin-bottom:12px;">
                    <div style="display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid #1e1e35;"><span>Predicted Likes:</span><span style="font-family:'Bebas Neue',sans-serif; font-size:22px; color:#e8e8f0;">{vd.get('predicted_likes', 0):,}</span></div>
                    <div style="display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid #1e1e35;"><span>Predicted Retweets:</span><span style="font-family:'Bebas Neue',sans-serif; font-size:22px; color:#e8e8f0;">{vd.get('predicted_retweets', 0):,}</span></div>
                    <div style="display:flex; justify-content:space-between; padding:8px 0; border-bottom:1px solid #1e1e35;"><span>Predicted Comments:</span><span style="font-family:'Bebas Neue',sans-serif; font-size:22px; color:#e8e8f0;">{vd.get('predicted_comments', 0):,}</span></div>
                    <div style="display:flex; justify-content:space-between; padding:8px 0;"><span>Total Predicted Engagement:</span><span style="font-family:'Bebas Neue',sans-serif; font-size:22px; color:#FF6B00;">{total:,}</span></div>
                </div>
                <div style="background:#0d0d18; border:1px solid #1e1e35; border-radius:10px; padding:16px; margin-bottom:12px;">
                    <div style="font-weight:700; margin-bottom:8px;">Analysis Details</div>
                    <div style="margin-bottom:6px;">Confidence: <span style="background:{conf_color}; color:white; padding:2px 10px; border-radius:4px; font-size:12px;">{conf}</span></div>
                    <div style="margin-bottom:6px; color:#8888aa;">Compared to your average:</div>
                    <div style="color:{comp_color}; margin-bottom:12px;">{"↑" if "Above" in compared else "→" if "Average" in compared else "↓"} {compared}</div>
                    <div style="color:#8888aa; font-size:12px; margin-bottom:4px;">Reasoning:</div>
                    <div style="font-size:14px; line-height:1.6;">{vd.get('reasoning', '')}</div>
                </div>
                <div style="background:#0d0d18; border:1px solid #1e1e35; border-radius:10px; padding:16px;">
                    <div style="font-weight:700; margin-bottom:8px;">How to improve engagement</div>
                    <ul style="margin:0; padding-left:20px;">{''.join([f'<li style="margin-bottom:8px; line-height:1.5;">{tip}</li>' for tip in vd.get('improvements', [])])}</ul>
                </div>
            </div>""", unsafe_allow_html=True)

        # Algorithm Grades
        if st.session_state.get("ci_grades"):
            gd = st.session_state["ci_grades"]
            algo_score = gd.get("algorithm_score", 0)
            tyler_score = gd.get("tyler_score", 0)
            algo_color = "#22c55e" if algo_score >= 75 else "#FF6B00" if algo_score >= 55 else "#ef4444"
            tyler_color = "#22c55e" if tyler_score >= 75 else "#FF6B00" if tyler_score >= 55 else "#ef4444"

            st.markdown(f"""<div style="display:flex; gap:20px; margin:16px 0;">
                <div style="flex:1; background:#0d0d18; border:1px solid #1e1e35; border-radius:12px; padding:20px; text-align:center;">
                    <div style="font-family:'Bebas Neue',sans-serif; font-size:52px; color:{algo_color}; line-height:1;">{algo_score}</div>
                    <div style="font-size:11px; color:#666688; letter-spacing:2px; text-transform:uppercase; margin-top:4px;">Algorithm Score</div>
                </div>
                <div style="flex:1; background:#0d0d18; border:1px solid #1e1e35; border-radius:12px; padding:20px; text-align:center;">
                    <div style="font-family:'Bebas Neue',sans-serif; font-size:52px; color:{tyler_color}; line-height:1;">{tyler_score}</div>
                    <div style="font-size:11px; color:#666688; letter-spacing:2px; text-transform:uppercase; margin-top:4px;">Tyler Score</div>
                </div>
            </div>""", unsafe_allow_html=True)

            # Personal insights
            insights = gd.get("personal_insights", [])
            if insights:
                insights_html = "".join([f'<div style="background:#1a1a30; border-left:3px solid #FF6B00; border-radius:6px; padding:10px 14px; margin-bottom:8px; font-size:13px; color:#d8d8e8; line-height:1.5;">{ins}</div>' for ins in insights])
                st.markdown(f"""<div style="margin-bottom:16px;">
                    <div style="font-family:'Bebas Neue',sans-serif; font-size:16px; letter-spacing:1px; color:#8888aa; margin-bottom:8px;">Personal Insights</div>
                    {insights_html}
                </div>""", unsafe_allow_html=True)

            st.markdown('<div style="font-family:\'Bebas Neue\',sans-serif; font-size:22px; letter-spacing:1px; margin:8px 0 8px;">Grade Breakdown</div>', unsafe_allow_html=True)
            grades = gd.get("grades", [])
            # Display in 2-column grid
            for row_start in range(0, len(grades), 2):
                cols = st.columns(2)
                for col_idx in range(2):
                    idx = row_start + col_idx
                    if idx < len(grades):
                        g = grades[idx]
                        score = g.get("score", 0)
                        score_color = "#22c55e" if score >= 8 else "#FF6B00" if score >= 6 else "#ef4444"
                        benchmark = g.get("benchmark", "")
                        benchmark_html = f'<div style="font-size:11px; color:#FF6B00; margin-top:8px; font-style:italic;">{benchmark}</div>' if benchmark else ""
                        with cols[col_idx]:
                            st.markdown(f"""<div style="background:#0d0d18; border:1px solid #1e1e35; border-radius:10px; padding:16px; margin-bottom:10px; min-height:160px;">
                                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                                    <span style="font-weight:700; font-size:14px;">{g.get('name','')}</span>
                                    <span style="font-family:'JetBrains Mono',monospace; font-size:14px; background:{score_color}22; color:{score_color}; padding:2px 10px; border-radius:4px;">Score: {score}/10</span>
                                </div>
                                <div style="font-size:13px; color:#9999aa; line-height:1.5;">{g.get('detail','')}</div>
                                {benchmark_html}
                            </div>""", unsafe_allow_html=True)

            suggestions = gd.get("suggestions", [])
            if suggestions:
                st.markdown(f"""<div style="background:#0d0d18; border:1px solid #1e1e35; border-radius:10px; padding:16px; margin-top:8px;">
                    <div style="font-weight:700; margin-bottom:10px;">Suggestions for Improvement</div>
                    <ul style="margin:0; padding-left:20px; color:#9999aa;">{''.join([f'<li style="margin-bottom:8px; line-height:1.5;">{s}</li>' for s in suggestions])}</ul>
                </div>""", unsafe_allow_html=True)

        # Preview
        if st.session_state.get("ci_preview"):
            preview_text = st.session_state["ci_preview"]
            truncated = preview_text[:280]
            show_more = len(preview_text) > 280
            now_str = datetime.now().strftime("%b %d, %Y, %-I:%M %p")
            st.markdown(f"""<div class="output-box">
                <div style="font-weight:700; font-size:16px; margin-bottom:16px;">Post Preview</div>
                <div style="background:#0d0d18; border:1px solid #2e2e45; border-radius:16px; padding:20px;">
                    <div style="display:flex; align-items:center; gap:10px; margin-bottom:12px;">
                        <div style="width:40px; height:40px; border-radius:50%; background:linear-gradient(135deg, #FF6B00, #cc4a00); display:flex; align-items:center; justify-content:center; font-weight:700; color:white;">T</div>
                        <div><span style="font-weight:700;">Tyler Polumbus</span> <span style="color:#666688;">@{TYLER_HANDLE}</span></div>
                    </div>
                    <div style="font-size:15px; line-height:1.6; white-space:pre-wrap;">{truncated}{'<br><span style="color:#1d9bf0; cursor:pointer;">Show more</span>' if show_more else ''}</div>
                    <div style="color:#666688; font-size:13px; margin-top:12px;">{now_str} · X</div>
                    <div style="display:flex; gap:40px; margin-top:12px; color:#666688; font-size:14px;">
                        <span>💬</span><span>🔁</span><span>❤️</span><span>📊</span><span>—</span>
                    </div>
                </div>
                <div style="color:#8888aa; font-size:13px; margin-top:12px;">This preview shows how your post will appear on X{', including where the "Show more" button will be placed (after 280 characters). It is critical you make the hook before the show more button make users want to click it.' if show_more else '.'}</div>
            </div>""", unsafe_allow_html=True)

        st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

        # Save idea
        sc_cat = st.selectbox("Category", ["Uncategorized", "Evergreen", "Timely", "Thread Ideas", "Video Ideas"], key="ci_cat")
        if st.button("Save Idea", key="ci_save", use_container_width=True):
            if tweet_text.strip():
                ideas = load_json("saved_ideas.json", [])
                ideas.append({
                    "text": tweet_text,
                    "format": fmt,
                    "category": sc_cat,
                    "saved_at": datetime.now().isoformat(),
                })
                save_json("saved_ideas.json", ideas)
                st.success("Idea saved.")

    with col_saved:
        st.markdown("### Saved Ideas")
        folder = st.selectbox("Folder", ["All Ideas", "Uncategorized", "Evergreen", "Timely", "Thread Ideas", "Video Ideas", "Inspiration Vault", "Repurpose Queue"], key="ci_folder")

        if folder in ("Inspiration Vault", "Repurpose Queue"):
            gist_file = "hq_inspiration.json" if folder == "Inspiration Vault" else "hq_repurpose.json"
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
                        <div style="display:flex; justify-content:space-between; margin-bottom:4px;">
                            <span class="tweet-num">{author}</span>
                            <span style="font-size:11px; color:#444466;">{ts}</span>
                        </div>
                        <div style="color:#d8d8e8; font-size:13px; line-height:1.5;">{orig_text[:200]}{'...' if len(orig_text) > 200 else ''}</div>
                    </div>""", unsafe_allow_html=True)
                    if st.button("Repurpose This", key=f"ci_inspo_{ii}", use_container_width=True):
                        st.session_state["ci_repurpose_seed"] = item.get("text", orig_text)
                        st.session_state["ci_auto_repurpose"] = True
                        st.rerun()
        else:
            ideas = load_json("saved_ideas.json", [])
            filtered = ideas if folder == "All Ideas" else [i for i in ideas if i.get("category") == folder]
            if not filtered:
                st.markdown('<div class="output-box">No saved ideas yet.</div>', unsafe_allow_html=True)
            else:
                for i, idea in enumerate(reversed(filtered[-30:])):
                    ts = idea.get("saved_at", "")[:10]
                    cat = idea.get("category", "")
                    st.markdown(f"""<div class="tweet-card">
                        <div style="display:flex; justify-content:space-between;">
                            <span class="tweet-num">{idea.get('format','')}</span>
                            <span style="font-size:11px; color:#444466;">{ts}</span>
                        </div>
                        <div style="color:#d8d8e8; font-size:13px;">{idea.get('text','')[:150]}{'...' if len(idea.get('text','')) > 150 else ''}</div>
                        <span class="tag">{cat}</span>
                    </div>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: CONTENT COACH
# ═══════════════════════════════════════════════════════════════════════════
def page_content_coach():
    st.markdown('<div class="main-header">CONTENT <span>COACH</span></div>', unsafe_allow_html=True)
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
        if st.button("+ New Conversation", use_container_width=True, key="coach_new"):
            st.session_state.coach_current = {"id": None, "messages": [], "title": "New Chat"}
            st.rerun()
        for conv in reversed(st.session_state.coach_conversations[-20:]):
            label = conv.get("title", "Untitled")[:30]
            is_active = conv.get("id") == st.session_state.coach_current.get("id")
            if st.button((">> " if is_active else "") + label, key=f"cv_{conv['id']}", use_container_width=True):
                st.session_state.coach_current = json.loads(json.dumps(conv))
                st.rerun()
        if st.session_state.coach_conversations:
            if st.button("Clear All", key="coach_clear_all", use_container_width=True):
                st.session_state.coach_conversations = []
                st.session_state.coach_current = {"id": None, "messages": [], "title": "New Chat"}
                save_json("coach_conversations.json", [])
                st.rerun()

    with col_right:
        st.markdown("##### Output Format")
        coach_fmt = st.selectbox("Format", ["General Advice", "Short Tweet", "Long Tweet", "Thread", "Article"], key="coach_fmt", label_visibility="collapsed")
        st.markdown("---")
        st.markdown("##### Quick Save to Ideas")
        save_text = st.text_area("Save to Compose Ideas:", height=100, key="coach_save_text", placeholder="Paste coach advice here...")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Save Idea", use_container_width=True, key="coach_save_idea") and save_text.strip():
                ideas = load_json("saved_ideas.json", [])
                ideas.append({"id": str(uuid.uuid4()), "text": save_text.strip(), "category": "From Coach", "created_at": datetime.now().isoformat()})
                save_json("saved_ideas.json", ideas)
                st.success("Saved!")
        with c2:
            if st.button("Repurpose", use_container_width=True, key="coach_repurpose") and save_text.strip():
                with st.spinner("Repurposing..."):
                    repurposed = call_claude(f"Repurpose this into a compelling tweet for Tyler Polumbus:\n\n{save_text.strip()}", max_tokens=600)
                    st.session_state.coach_save_text_result = repurposed
        if "coach_save_text_result" in st.session_state:
            st.markdown(f"**Repurposed:**\n\n{st.session_state.coach_save_text_result}")

    with col_center:
        include_history = st.checkbox("Include Tweet History (check on first message per conversation)", value=not bool(st.session_state.coach_current["messages"]), key="coach_hist_toggle")

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
            st.markdown(f'<div class="chat-msg {cls}"><div class="chat-role">{role_label}</div><div style="color:#d8d8e8;font-size:14px;line-height:1.7;white-space:pre-wrap;">{msg["content"]}</div></div>', unsafe_allow_html=True)

        # Input
        user_input = st.text_area("Ask your coach:", height=80, key="coach_input", placeholder="What should I write about today?")
        if st.button("Send", use_container_width=True, key="coach_send") and user_input.strip():
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

    # ── Left 2/3: Tweet / Brain Dump selectors + generation ──────────────
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
            if st.button("Select", key=f"aw_tw_{i}", use_container_width=True):
                st.session_state.aw_sel_tweet = i
                st.session_state.aw_sel_dump = None
                st.session_state["aw_autogen"] = tw.get("text", "")
                st.rerun()

        if not top_tweets:
            st.info("No tweet history yet. Sync tweets in Tweet History first.")

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

        # Section 2 — Choose a Brain Dump
        st.markdown("#### Or Choose a Brain Dump")
        dumps = load_json("brain_dumps.json", [])
        if "aw_sel_dump" not in st.session_state:
            st.session_state.aw_sel_dump = None

        if not dumps:
            st.markdown('<div class="output-box">No brain dumps yet. Create one in Brain Dump tool first.</div>', unsafe_allow_html=True)
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
                if st.button("Select", key=f"aw_bd_{j}", use_container_width=True):
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
            if st.button("Start from scratch", use_container_width=True, key="aw_scratch"):
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
            if st.button("Generate Outline", use_container_width=True, key="aw_outline"):
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
                if st.button("Save Article", use_container_width=True, key="aw_save"):
                    articles = load_json("saved_articles.json", [])
                    articles.append({"content": edited, "seed": seed_text[:200], "saved_at": datetime.now().isoformat()})
                    save_json("saved_articles.json", articles)
                    st.success("Article saved.")
            with bc2:
                if st.button("Copy", use_container_width=True, key="aw_copy"):
                    st.code(edited, language=None)
                    st.info("Text displayed above -- copy from there.")
            with bc3:
                if st.button("New Article", use_container_width=True, key="aw_new"):
                    for k in ["aw_result", "aw_sel_tweet", "aw_sel_dump"]:
                        st.session_state.pop(k, None)
                    st.rerun()

    # ── Right 1/3: Saved Articles ────────────────────────────────────────
    with col_saved:
        sc1, sc2 = st.columns([2, 1])
        with sc1:
            st.markdown("### Saved Articles")
        with sc2:
            if st.button("New Article", key="aw_side_new", use_container_width=True):
                for k in ["aw_result", "aw_sel_tweet", "aw_sel_dump"]:
                    st.session_state.pop(k, None)
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
                    st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: TWEET HISTORY
# ═══════════════════════════════════════════════════════════════════════════
def sync_tweet_history():
    """Fetch up to 500 tweets and save to local knowledge base."""
    all_tweets = []
    cursor = ""
    batches = 0
    while batches < 10:  # 10 batches x 50 = 500 max
        try:
            params = {"query": f"from:{TYLER_HANDLE}", "queryType": "Latest", "count": "50"}
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
            tweets = data.get("tweets", [])
            if not tweets:
                break
            all_tweets.extend(tweets)
            cursor = data.get("next_cursor", "")
            if not cursor:
                break
            batches += 1
            import time; time.sleep(0.5)
        except Exception:
            break
    # Deduplicate by ID
    seen = set()
    unique = []
    for t in all_tweets:
        tid = t.get("id", "")
        if tid and tid not in seen:
            seen.add(tid)
            unique.append(t)
    save_json("tweet_history.json", unique)
    return unique


def get_tweet_knowledge_base():
    """Load the local tweet history — this is the knowledge base for the whole app."""
    return load_json("tweet_history.json", [])


def classify_tweet(tweet):
    """Classify a tweet into categories."""
    text = tweet.get("text", "")
    likes = tweet.get("likeCount", 0)
    rts = tweet.get("retweetCount", 0)
    replies = tweet.get("replyCount", 0)
    views = tweet.get("viewCount", 0)
    eng_rate = (likes + rts + replies) / max(views, 1) * 100

    tags = []
    if len(text) < 140:
        tags.append("Short")
    if len(text) > 200:
        tags.append("Long")
    if likes > 100 or rts > 20:
        tags.append("High Engagement")
    if views > 10000:
        tags.append("Viral")
    if replies > likes * 0.3 and replies > 5:
        tags.append("Conversation Starter")
    if eng_rate > 5:
        tags.append("Hot")
    if not text.startswith("@") and not text.startswith("RT ") and "http" not in text:
        tags.append("Original")
    if text.startswith("@"):
        tags.append("Reply")
    if "RT " in text[:5]:
        tags.append("Repost")
    # Evergreen detection — no time-sensitive words
    time_words = ["today", "tonight", "right now", "just", "breaking", "live"]
    if not any(w in text.lower() for w in time_words) and likes > 20:
        tags.append("Evergreen")

    return tags


def page_tweet_history():
    st.markdown('<div class="main-header">YOUR CONTENT <span>HISTORY</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Your knowledge base. Every AI feature in this app learns from these tweets.</div>', unsafe_allow_html=True)

    # Load stored tweets
    tweets = get_tweet_knowledge_base()

    # Header stats
    hc1, hc2, hc3, hc4 = st.columns([1, 1, 1, 2])
    with hc1:
        st.markdown(f'<div class="stat-card"><div class="stat-num">{len(tweets)}</div><div class="stat-label">Total Tweets</div></div>', unsafe_allow_html=True)
    with hc2:
        st.markdown(f'<div class="stat-card"><div class="stat-num">@{TYLER_HANDLE}</div><div class="stat-label">Handle</div></div>', unsafe_allow_html=True)
    with hc3:
        last_sync = ""
        if tweets:
            dates = [t.get("createdAt", "") for t in tweets if t.get("createdAt")]
            if dates:
                last_sync = sorted(dates, reverse=True)[0][:10]
        st.markdown(f'<div class="stat-card"><div class="stat-num">{last_sync or "Never"}</div><div class="stat-label">Last Synced</div></div>', unsafe_allow_html=True)
    with hc4:
        if st.button("Sync Tweets (pull last 500)", use_container_width=True, key="th_sync"):
            with st.spinner("Syncing up to 500 tweets from X... this may take a minute."):
                tweets = sync_tweet_history()
                st.success(f"Synced {len(tweets)} tweets.")
                st.rerun()

    if not tweets:
        st.warning("No tweets stored. Click 'Sync Tweets' to pull your history from X.")
        return

    # Search
    search = st.text_input("Search tweets and notes:", placeholder="Filter by keyword...", key="th_search")

    # Filter buttons as columns
    filters = ["All Posts", "Short Posts", "Long Posts", "High Engagement", "Viral Posts",
               "Conversation Starters", "Evergreen", "Hot", "Original", "Replies"]
    filter_type = st.selectbox("Filter", filters, key="th_filter")

    # AI filter buttons inline
    ac1, ac2, ac3, ac4 = st.columns(4)
    with ac1:
        if st.button("Find my best hooks", key="th_ai_hooks", use_container_width=True):
            top = sorted(tweets, key=lambda t: t.get("likeCount", 0), reverse=True)[:20]
            hooks = [t.get("text", "").split(".")[0].split("...")[0].split("\n")[0][:100] for t in top]
            st.session_state["th_ai_result"] = "Your best-performing opening hooks:\n\n" + "\n".join([f"{i+1}. {h}" for i, h in enumerate(hooks)])
    with ac2:
        if st.button("Find my worst performers", key="th_ai_worst", use_container_width=True):
            worst = sorted(tweets, key=lambda t: t.get("viewCount", 0) if t.get("viewCount", 0) > 0 else 999999)[:10]
            st.session_state["th_ai_result"] = "Lowest performing tweets (by views):\n\n" + "\n".join([f"- {t.get('text','')[:80]}... ({t.get('viewCount',0):,} views)" for t in worst])
    with ac3:
        if st.button("Analyze my voice patterns", key="th_ai_voice", use_container_width=True):
            sample = [t.get("text", "") for t in sorted(tweets, key=lambda t: t.get("likeCount", 0), reverse=True)[:30]]
            with st.spinner("Analyzing your voice..."):
                result = call_claude(f"Analyze Tyler's writing voice based on these top-performing tweets. Identify patterns in: sentence length, punctuation style, opener types, tone, vocabulary, what makes his voice unique.\n\nTweets:\n" + "\n---\n".join(sample[:20]))
                st.session_state["th_ai_result"] = result
    with ac4:
        if st.button("What topics perform best?", key="th_ai_topics", use_container_width=True):
            sample = [f"{t.get('text','')[:100]} (likes:{t.get('likeCount',0)}, views:{t.get('viewCount',0)})" for t in sorted(tweets, key=lambda t: t.get("likeCount", 0), reverse=True)[:40]]
            with st.spinner("Analyzing topics..."):
                result = call_claude(f"Analyze which TOPICS get Tyler the most engagement. Group his tweets by topic and show which topics consistently outperform. Be specific.\n\nTweets:\n" + "\n".join(sample))
                st.session_state["th_ai_result"] = result

    if st.session_state.get("th_ai_result"):
        st.markdown(f'<div class="output-box">{st.session_state["th_ai_result"]}</div>', unsafe_allow_html=True)

    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

    # Apply filters
    filtered = tweets
    if search:
        filtered = [t for t in filtered if search.lower() in t.get("text", "").lower()]

    if filter_type != "All Posts":
        tag_map = {
            "Short Posts": "Short", "Long Posts": "Long", "High Engagement": "High Engagement",
            "Viral Posts": "Viral", "Conversation Starters": "Conversation Starter",
            "Evergreen": "Evergreen", "Hot": "Hot", "Original": "Original", "Replies": "Reply",
        }
        target_tag = tag_map.get(filter_type, "")
        filtered = [t for t in filtered if target_tag in classify_tweet(t)]

    st.markdown(f"**Showing {len(filtered)} of {len(tweets)} tweets**")

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
# PAGE: ALGO ANALYZER
# ═══════════════════════════════════════════════════════════════════════════
def page_algo_analyzer():
    st.markdown('<div class="main-header">ALGO <span>ANALYZER</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Run your content through the algorithm lens before you post.</div>', unsafe_allow_html=True)

    col_ideas, col_analyze = st.columns([1, 2])

    with col_ideas:
        st.markdown("### Saved Ideas")
        ideas = load_json("saved_ideas.json", [])
        if not ideas:
            st.markdown('<div class="output-box">No saved ideas. Use Compose Ideas to save some.</div>', unsafe_allow_html=True)
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

        if st.button("AI Algo Analyzer", use_container_width=True, key="aa_run"):
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
    st.markdown('<div class="tool-desc">Audit your X account against best practices.</div>', unsafe_allow_html=True)

    st.markdown(f"**Account:** @{TYLER_HANDLE}")

    if st.button("Run Health Check", use_container_width=True, key="hc_run"):
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
            else:
                st.markdown(f'<div class="output-box">{raw}</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: ACCOUNT PULSE
# ═══════════════════════════════════════════════════════════════════════════
def page_account_pulse():
    st.markdown('<div class="main-header">ACCOUNT <span>PULSE</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Your account stats at a glance.</div>', unsafe_allow_html=True)

    if st.button("Load Account Data", use_container_width=True, key="ap_load"):
        with st.spinner("Fetching account data..."):
            user = fetch_user_info(TYLER_HANDLE)
            tweets = fetch_tweets(f"from:{TYLER_HANDLE}", count=50)
            st.session_state["ap_user"] = user
            st.session_state["ap_tweets"] = tweets

    user = st.session_state.get("ap_user", {})
    tweets = st.session_state.get("ap_tweets", [])

    if not user:
        st.info("Click 'Load Account Data' to pull your stats.")
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
        if st.button("AI Pulse Analysis", key="ap_ai"):
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
        if st.button("Research Account", use_container_width=True, key="ar_run"):
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


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: REPLY GUY
# ═══════════════════════════════════════════════════════════════════════════
def page_reply_guy():
    XURL = "/home/linuxbrew/.linuxbrew/bin/xurl"
    LISTS = {"Broncos Reporters": "1294328608417177604", "Nuggets": "1755985316752642285",
             "Morning Engagement": "2011987998699897046", "Work": "1182699241329721344"}

    st.markdown('<div class="main-header">REPLY <span>GUY</span></div>', unsafe_allow_html=True)
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
    replied_tweets = load_json("replied_tweets.json", [])

    def _bump_reply():
        progress["count"] = progress.get("count", 0) + 1
        save_json("reply_progress.json", progress)

    def _mark_replied(tweet_id):
        if tweet_id not in replied_tweets:
            replied_tweets.append(tweet_id)
            save_json("replied_tweets.json", replied_tweets[-500:])

    # ── PART 1: Top Stats Bar ──
    c1, c2 = st.columns([3, 1])
    with c1:
        pct = min(reply_count / 50 * 100, 100)
        st.markdown(f'<div style="margin-bottom:8px;"><div style="display:flex;justify-content:space-between;margin-bottom:4px;">'
                    f'<span class="metric-label">Daily Reply Progress</span><span class="metric-score">{reply_count}/50</span></div>'
                    f'<div class="progress-bar-bg"><div class="progress-bar-fill" style="width:{pct}%;"></div></div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="stat-card"><div class="stat-num">{streak}</div><div class="stat-label">Day Streak</div></div>', unsafe_allow_html=True)
    day_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    hist_map = {h["date"]: h["count"] for h in progress.get("history", [])}
    hist_map[today_str] = reply_count
    cols = st.columns(7)
    for d in range(6, -1, -1):
        dt = datetime.now() - timedelta(days=d)
        ds = dt.strftime("%Y-%m-%d")
        label = day_labels[dt.weekday()]
        cnt = hist_map.get(ds, 0)
        cols[6 - d].markdown(f'<div style="text-align:center;"><div style="color:#aaa;font-size:11px;">{label}</div>'
                             f'<div style="color:#fff;font-size:18px;font-weight:700;">{cnt}</div></div>', unsafe_allow_html=True)

    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

    # Force rerun if flagged (workaround for st.rerun inside nested columns)
    if st.session_state.pop("rg_force_rerun", False):
        st.rerun()

    # ── PART 2: My Tweet Replies — Conversation Depth ──
    st.markdown("### My Tweet Replies -- Conversation Depth")
    btn_c1, btn_c2 = st.columns(2)
    with btn_c1:
        load_all = st.button("Load All Tweet Replies", key="rg_load_all", use_container_width=True)
    with btn_c2:
        load_verified = st.button("Load Verified Follower Replies", key="rg_load_verified", use_container_width=True)

    if load_all or load_verified:
        with st.spinner("Fetching tweets and replies..."):
            my_tweets = fetch_tweets(f"from:{TYLER_HANDLE}", count=15)
            filtered = [t for t in my_tweets if int(t.get("replyCount", t.get("reply_count", 0))) >= 2][:8]
            st.session_state["rg_my_tweets"] = filtered
            for idx, tw in enumerate(filtered):
                replies = fetch_tweets(f"conversation_id:{tw.get('id', '')} to:{TYLER_HANDLE}", count=15)
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

        # Table header for replies
        if st.session_state.get(f"rg_replies_{idx}"):
            rhc1, rhc2, rhc3, rhc4 = st.columns([1, 3, 3, 1])
            rhc1.markdown("**Account**")
            rhc2.markdown("**Reply**")
            rhc3.markdown("**Your Response**")
            rhc4.markdown("**Done?**")
            st.markdown('<hr style="margin:2px 0;border-color:#1e1e35;">', unsafe_allow_html=True)

        for ri, rp in enumerate(st.session_state.get(f"rg_replies_{idx}", [])):
            rauthor = rp.get("author", {}).get("userName", rp.get("user", {}).get("screen_name", ""))
            rid = rp.get("id", "")
            rtext = rp.get("text", "")
            r_likes = rp.get("likeCount", rp.get("like_count", 0))
            already_replied = rid in replied_tweets
            input_key = f"rg_ri_{idx}_{ri}"

            rc1, rc2, rc3, rc4 = st.columns([1, 3, 3, 1])
            with rc1:
                st.markdown(f'<div style="font-weight:700;color:#FF6B00;font-size:13px;padding-top:8px;">@{rauthor}</div>', unsafe_allow_html=True)
            with rc2:
                st.markdown(f'<div style="font-size:14px;color:#d8d8e8;line-height:1.5;">{rtext[:250]}</div>'
                            f'<div style="font-size:11px;color:#888;margin-top:4px;">{r_likes} likes</div>', unsafe_allow_html=True)
            with rc3:
                ic1, ic2, ic3, ic4 = st.columns([6, 1, 1, 1])
                with ic2:
                    if st.button("✨", key=f"rg_gen_{idx}_{ri}", use_container_width=True):
                        sug = call_claude(f'Tyler originally tweeted: "{txt[:200]}"\n\nSomeone replied to Tyler\'s tweet. Tyler wants to reply back.\n\n@{rauthor} replied: "{rtext[:200]}"\n\nWrite Tyler\'s reply. Under 150 chars. Conversational, uses ellipsis, former NFL player perspective. No emojis. Just the reply text, nothing else.', max_tokens=80)
                        st.session_state[input_key] = sug
                with ic1:
                    reply_val = st.text_area("r", key=input_key, label_visibility="collapsed", placeholder="Write reply...", height=auto_height(st.session_state.get(input_key, "")))
                with ic3:
                    liked_tweets = load_json("liked_tweets.json", [])
                    already_liked = rid in liked_tweets
                    if already_liked:
                        st.button("💚", key=f"rg_like_{idx}_{ri}", use_container_width=True, disabled=True)
                    elif st.button("❤️", key=f"rg_like_{idx}_{ri}", use_container_width=True):
                        _proxy_tweet_action("like", rid)
                        liked_tweets.append(rid)
                        save_json("liked_tweets.json", liked_tweets[-500:])
                        st.rerun()
                with ic4:
                    # Check replied status fresh (same pattern as likes)
                    fresh_replied = load_json("replied_tweets.json", [])
                    is_replied_now = rid in fresh_replied
                    if is_replied_now:
                        st.button("✅", key=f"rg_send_{idx}_{ri}", use_container_width=True, disabled=True)
                    elif st.button("➡️", key=f"rg_send_{idx}_{ri}", use_container_width=True):
                        if reply_val.strip():
                            if _proxy_tweet_action("reply", rid, reply_val.strip()):
                                _bump_reply()
                                fresh_replied.append(rid)
                                save_json("replied_tweets.json", fresh_replied[-500:])
                                st.rerun()
                            else:
                                st.error("Reply failed — check proxy connection")

    st.markdown("<hr class='section-divider'>", unsafe_allow_html=True)

    # ── PART 3: Engagement Targets — Table Layout ──
    st.markdown("### Engagement Targets")
    ctrl1, ctrl2, ctrl3 = st.columns([2, 1, 2])
    with ctrl1:
        list_source = st.selectbox("List", ["My Custom List"] + list(LISTS.keys()), key="rg_source", label_visibility="collapsed")
    with ctrl2:
        do_load = st.button("Load Posts", key="rg_load_posts", use_container_width=True)
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
                        resp = requests.get(
                            "https://api.twitterapi.io/twitter/list/tweets",
                            headers={"X-API-Key": TWITTER_API_IO_KEY},
                            params={"listId": lid, "count": 20},
                            timeout=30,
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            for t in data.get("tweets", []):
                                author = t.get("author", {})
                                all_tweets.append({
                                    "id": t.get("id", t.get("tweet_id", "")),
                                    "text": t.get("text", ""),
                                    "createdAt": t.get("createdAt", t.get("created_at", "")),
                                    "likeCount": t.get("likeCount", t.get("like_count", 0)),
                                    "retweetCount": t.get("retweetCount", t.get("retweet_count", 0)),
                                    "replyCount": t.get("replyCount", t.get("reply_count", 0)),
                                    "viewCount": t.get("viewCount", t.get("view_count", 0)),
                                    "_target_account": author.get("userName", author.get("username", "")),
                                    "author": author,
                                })
                        else:
                            st.error(f"List fetch error: HTTP {resp.status_code}")
                    except Exception as e:
                        st.error(f"List fetch error: {str(e)[:100]}")
            st.session_state["rg_tweets"] = all_tweets

    # Table header
    tweets_data = st.session_state.get("rg_tweets", [])
    if tweets_data:
        hc1, hc2, hc3, hc4 = st.columns([1, 3, 3, 1])
        hc1.markdown("**Account**")
        hc2.markdown("**Latest Post**")
        hc3.markdown("**Reply**")
        hc4.markdown("**Done?**")
        st.markdown('<hr style="margin:4px 0;border-color:#1e1e35;">', unsafe_allow_html=True)

    for i, t in enumerate(tweets_data):
        acc = t.get("_target_account", "")
        text = t.get("text", "")
        tid = t.get("id", "")
        likes = t.get("likeCount", t.get("like_count", 0))
        rts = t.get("retweetCount", t.get("retweet_count", 0))
        rpl = t.get("replyCount", t.get("reply_count", 0))
        views = t.get("viewCount", t.get("view_count", 0))
        created = t.get("createdAt", t.get("created_at", ""))[:16]
        already = tid in replied_tweets
        sug_key = f"rg_et_sug_{i}"

        rc1, rc2, rc3, rc4 = st.columns([1, 3, 3, 1])
        with rc1:
            st.markdown(f'<div style="font-weight:700;color:#FF6B00;font-size:13px;padding-top:8px;">@{acc}</div>', unsafe_allow_html=True)
        with rc2:
            st.markdown(f'<div style="font-size:15px;color:#d8d8e8;line-height:1.5;">{text[:150]}</div>'
                        f'<div style="font-size:12px;color:#888;margin-top:4px;">{created} | {likes} likes | {rpl} replies | {rts} RTs | {views} views</div>', unsafe_allow_html=True)
        with rc3:
            et_input_key = f"rg_et_{i}"
            ic1, ic2, ic3, ic4 = st.columns([6, 1, 1, 1])
            with ic2:
                if st.button("✨", key=f"rg_etg_{i}", use_container_width=True):
                    sug = call_claude(f'Tyler wants to reply to @{acc}\'s tweet: "{text[:150]}". Write ONE short reply under 150 chars. Tyler\'s voice: direct, uses ellipsis, former NFL player. No emojis.', max_tokens=80)
                    st.session_state[et_input_key] = sug
            with ic1:
                reply_text = st.text_area("r", key=et_input_key, label_visibility="collapsed", placeholder="Write your reply...", height=auto_height(st.session_state.get(et_input_key,"")))
            with ic3:
                et_liked = load_json("liked_tweets.json", [])
                et_already_liked = tid in et_liked
                if et_already_liked:
                    st.button("💚", key=f"rg_etl_{i}", use_container_width=True, disabled=True)
                elif st.button("❤️", key=f"rg_etl_{i}", use_container_width=True):
                    _proxy_tweet_action("like", tid)
                    et_liked.append(tid)
                    save_json("liked_tweets.json", et_liked[-500:])
                    st.rerun()
            with ic4:
                fresh_et_replied = load_json("replied_tweets.json", [])
                et_is_replied = tid in fresh_et_replied
                if et_is_replied:
                    st.button("✅", key=f"rg_ets_{i}", use_container_width=True, disabled=True)
                elif st.button("➡️", key=f"rg_ets_{i}", use_container_width=True):
                    if reply_text.strip() and tid:
                        if _proxy_tweet_action("reply", tid, reply_text.strip()):
                            _bump_reply()
                            fresh_et_replied.append(tid)
                            save_json("replied_tweets.json", fresh_et_replied[-500:])
                            st.rerun()
                        else:
                            st.error("Reply failed — check proxy connection")
        with rc4:
            if already:
                st.markdown('<div style="text-align:center;padding-top:8px;color:#22c55e;font-size:18px;">&#10003;</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: INSPIRATION
# ═══════════════════════════════════════════════════════════════════════════
def page_inspiration():
    st.markdown('<div class="main-header">INSPIRATION <span>VAULT</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Save tweets that inspire you. Reference them when you need ideas.</div>', unsafe_allow_html=True)

    inspo = load_inspiration_gist()

    col_add, col_view = st.columns([1, 1])

    with col_add:
        st.markdown("### Save New Inspiration")
        inspo_text = st.text_area("Tweet text:", height=100, key="insp_text",
            placeholder="Paste the tweet that caught your eye...")
        inspo_author = st.text_input("Author:", placeholder="@username", key="insp_author")
        inspo_tags = st.text_input("Tags (comma-separated):", placeholder="hook, thread, broncos", key="insp_tags")
        inspo_likes = st.number_input("Likes (optional):", min_value=0, value=0, key="insp_likes")
        inspo_views = st.number_input("Views (optional):", min_value=0, value=0, key="insp_views")

        if st.button("Save to Vault", use_container_width=True, key="insp_save"):
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
                    <a href="?page=Inspiration&del_inspo={real_idx}" style="position:absolute;top:10px;right:12px;color:#333355;font-size:14px;text-decoration:none;line-height:1;" title="Delete">✕</a>
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
    "Brain Dump": page_brain_dump,
    "Compose Ideas": page_compose_ideas,
    "Content Coach": page_content_coach,
    "Article Writer": page_article_writer,
    "Tweet History": page_tweet_history,
    "Algo Analyzer": page_algo_analyzer,
    "Health Check": page_health_check,
    "Account Pulse": page_account_pulse,
    "Account Researcher": page_account_researcher,
    "Reply Guy": page_reply_guy,
    "Inspiration": page_inspiration,
}

page_fn = page_map.get(page)
if page_fn:
    page_fn()
