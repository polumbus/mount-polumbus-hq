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
from datetime import datetime, timedelta, date
from pathlib import Path
from apis import (get_sports_context, pplx_fact_check, pplx_research, pplx_available,
                  get_espn_headlines_for_inspo, get_sleeper_trending_for_inspo, espn_scores,
                  odds_available, odds_format_block)

# ─── Page Config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Mount Polumbus HQ",
    page_icon="mountain",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── Constants ──────────────────────────────────────────────────────────────
AMPLIFIER_B64 = "iVBORw0KGgoAAAANSUhEUgAAADAAAAAwCAIAAADYYG7QAAAR0klEQVR42p1ZaZRdVZXe+5w7vXmoV6/GV1WpSqqSykAGMkAIw2qXqMEQF0RQu1sbRUFxQFfT2oNi+0NRWluW2korKtrayCA2Q4MNSpgyB0KSSqoqNY9vnt+749n941ZVisAS9P16775z7vnOt/fZw3eQiOCtPoKIhOCcuz8HTg29cOD4kRMDQ9Mz88Vy2dAtIQBBYiyoKM2hUG+ibev6Nbsu3dK/rted4jgOImMM33It/NOACEA4jgtlemruwUeeevyFg0O5TE1B7tckWWEEKAhJAAAxJIYCyDItp2Z4DeqNxq7ZtWPf+65OdLS6sBjnfxoUCiEQ33yMEIIxBgCjY5Pfuefnjx4+XPLL3mhQsoSZKhm5ilXRHdMmRwAQEAACcsZlSfJ71Aa/3Bi0VV7NlUIl89ptWz//6Q/39HQuf+2fx5DjOJxz23G+cdePfvjo4/XWYDAU0Mcz5YmUVTOQM5Qk5IjIAACRAIAIgIAISAhhWSBI9qr+zkats7FcLqvTxVv2XvOlf/iELEnOIutvF5BtO5LET54a/PjtXztNlcYVLeXT06WReUBkqoyMARAJQHStCkTnOUZAAgIEREYkHN0EolB3U2BtIjM+twa99377KxvW97lLvC2TuUMfePDJT37t255NK3muljw8BIiSJgsCIEQXhTt/YUe46HKIC9tE9wFyQAS7bgFRfNsq0eCtHxv7/j/ffuP7d78ppgsZcgfd8/37//6H93VcsSH30mBpKq0GvEQLC7vWcddCBEQgAQvvQEJg4DoU0SJKQCRARASzVPMnYg07+yb3n7rrEx/53G0ffiOm1wFaQvP5e+/r2bVh+onjjmFJmkyCAJAAgQhxwSqO7TiODYRcYoxzQHAsW9gCELnEmcRoCdAiocjQ1i1Jldt3bxl58bW7P/Z3n73tby/AdB6Q62i/eejJv/7qN1dcsWHq0cOAyCSJBC0zEAKAY1mCY6CzMdjVxBS5MDxTHU8Bgb87Hupptap68dxsfS4vc4bIibmYgAgBCREdWyCJzr3bR/af+MWX77hh33uW+/gCIPconjw1uOsDn2y8fO3cE8cch5jEyFkgHhHJEbZlgYThNe1tV62Xwv5aviaFtEg8MvCT3wPA6g9dlUsWOJEW9pYHpyeeHzCKFVV3kDFa8LAFxoRNjGPb7i2p50+/8OsfrF/XtxQLkIiISAiybXvn7g/PJfz6KxPVVIGrCgly34KItmnziDe+qSfS2yq3RirJYvr4qBrxa7GQcEQw4JU8Km46U53NEoEvEWu8an1rZxtM5v/vG/dbw0lJlhhn590DwTEsbzzk2dTVOlV98YmfSbLEEBGR33nnnUIIzvnX77330ZEzfhuyA1OyTyMhFueC5ThNl61efcPlerlWLlawIVQ4MRFqjSgepTKWVsJ+aYyMly1OZlq6Wpo2rIRmf7gpXJ7L2qW6axgiACImS3qmHIwGJq0aS5Wv3LXNJQkdx0HEycmZrdffHNjQOfPEMe5RwSFCWkQjuq6/JLK6febQECksuKEr1NlSPDVhTKZKYylZkwMbu6LtjUK38smconnqs5nsqyPB5qgGatqadp+iOTU90hw5+8s/VgZnJYnTIlHI0KmbbbsvLp8YP/LQf3Z0thERE0SI+K17fma2BisD08CQSCygQbQsu+XKteGe1sEHXzJms5HuptzgTKcWWLttXWZwCip1YQmuyCgx2a/5miOZo4M84Gl/x6ZKuoC5SuX50+VcoTSdzSQLq/ZdxkMesUg8ABARMFY+PWW2Bb/1vZ8jIhExifO52eQjBw6GQ/7iWJKr8oLzIZAj5FigZefq8T+8yixbCngqE2k5VTrxzIFj//OCz+NRA14UNsoSBjxmQCVAqtRlhlZZl30qC3jU5tgV112tdTTWU3nwax3v2GRZNizlfAKuSqWxZDgYePjlA3OzSc45A4AHHnmqFJCNiezSUXBjjUmie8/2SrpsFipywIOI3qaoXdHzh4Zz+09VZ7LFiZQwbM6RN0f7168D3bIKtXO/fK58elzmUnUqowW0/Mx85cykMZ4qZ8tte7drbVFhOcvKCQJEfSJd9kkPPPIUADAieuy5l72RQHkizVR56SDYlr1y32VqW0Pm5IQW9CEiEDnlum070roEi/o9sWDLVet5LFg5N1s7PVnK5IxCRYv6Q11N2BrRdvQGE7Hk/pP7/+1XckWvjqWmH325Wq5d/E83YFBzkx8CEAFTpcpkxhcLPbb/ABGxobOjZ7NpxSKrZqBLJoLjCP/OvqZ3b0kPTnOGAECChGHVRuZ5U+Smuz679rb3+rsaDcu+7Nb36amyNZUeevawNZuvZ8u2xi/64Dvfd9sHiqYNjMdXdzkSi2/pId3MHBk2OXTv2WY7DizmIGRo1QxJt8+kk0NnR9n+l45WFbAyZWToJke0BcQDH/zXT5pFvTKesku60G2rWDOzVeTMyhSPHHgleXgwPzTNZen004fMQoVxrggsjM713XAlWTR1eOD4/qOiWFPiobZ3bCXOpKA3unmVVahM7z8d6mnTYkFhO+eNxpidrdRVtv/lo7ypq3+wXrSm845pAyIgki3UeKjp3Ztmjw/rk0k9U6xNpsxCzdcSZkEPWM70iyfNdMmYK5Rt11J5AAh2xBExPzqvtMckjuVzs9PHznTt6Leq9ey5GYkzyzCDXU3BFS3p0xOh9lhlIqUni0xiy0sWqSUUrAvua1lZVLE+llooHBAt04qsbof2iCjpJPOmK9bxsN/IliJrExj0IQOsmShxpnJPe8zf3SKFfYpXJSBbYtV8Jb6zv5LKt21aSY5Dfm99Ltd+9ZbqdCZ9cNDXFDGqtVBHTNSNwtkZSZaWkq6wHC3RAPkaV1u6nYBWG00yibuAHMcJrW7zJ+IOoi8ayI/Pt75zc2x7r163OONMldGjiroRWtflaQhWkqXwph417A3EQtEN3f54JNgWi/Z3GnO52WPnAqvbAytaynNZrSFYeHXEqeje1obG7WuYZWdeHUNBSzlbmJavI27mKqxkGCCEcMRisQAIaBZrit/jMCBFdrKVsV88KzPWtHFl9syEYzq+voS8riOwoas4m2deJdzdHN+0KlM3yrny/OGh4ccOZedx6Xq94ar1akOQy7w8PMs8cmhNwqrUoVCvzRdDF3VrsQA5C0UnIAiHkKik61xpXakEPdXxNFMkt1BnyMy6sWLP9nqpNvW7A8jAqpu518ZDzSF/awMw5l2d6H3Xjnql7pe5z6dNP3+ybDtbr9w+evh0/ewUVetSW3TXx/YYJM7d/+zc08dkBoJx/5o2WzetTGnm6NlVN+5KHzhbm87yRbMIy/Z3xPRilV3YcRAgZ0amNPvCKTtf1VNFye+98e7PMc6P3fVw4cQ4U7ivLbyhowMte/LZV07d90zptXGWLuqpXHVwWk8WFFWiqu43QaRL3LEbVjRrkUD5tRHSlI03v9dCCnc1VWYzatgvxAXlPCIAD3b0sZC3PpnhMl9MesAIa9lSx19tNBjjEktOzcsNfi0eET5F7Wz0B3zPPfRs4eUBf2ssciaBtl2bzh65/+mmFc1KyGfkq+Z4evDEmdzxc1Q20KuAI6SgN9LfueOSzSOTs061HmptKA/OlEbmuSwtMiS8XY1YMVhAUYizhSC0SBKTeXk0WRqc3X3Hh+R4KDs6Y5l2dGOnEg2EPVryuVPlJw5LNaOezOUHJpWGoNCt9r4Oq2oIR1Tmc1o0UD88wnOVeqrYtKHHsm1fPJw9NPjgTx/y+FVZU2zdMsv6UnNBBIwjcAyoCu/feElGcuy5Ai3VwAAAIHGWH50fOzLg96nRnhbVo5iFaufmldmxueTLpyVVi6zrDK/tRInZhYoU8JXnc5njo0rI23X1xaWppGWTtDYBYT9xDK5sN0tVM1PyIjcyBbUxFIyFJp48Crq1lGiZxOW2aAf3Sqs72gemhmS/xyhUkbPlBqViLf/imexLZ7hXlXyqbTpGrsR8mjCc8OpmJ+zffev7//dXj889kVWDSmxbX8tl6w3LXrNzc/L0uHdz13X/eFPKrGfmUoWhGds0TYssBL1mhrxa+uiwniwqiuy2S8IRSthnW/bqji6898f/fccDD6iGKA7OMk2ixWzvlmcIbiITAGDrVmRLd+LqTVMHBhUJLWBSPCJZlq85Uh5PoVeLb+2t6nVRrnscYBFfKNFcmM/nhydD7TEt4AVBxAFrpj6VGfz1ftStBZMhOroZ6m01PfyufTewy3de7LGIN/hJOLjYAy62WeBW3IAIDGWvWjgzbeaqiZ1rhCQ7pbo1n+PNIfCoDeu7/N1NtmW1dTb5Q/7CbDr1yujEkTP5V4cpWcoeHJx7/lRxKh1pikw+dfTMz59F3XKTq7ttEiTHAh5TXL7zYqm3r7uvoXGA12WfJmihh3LdiV4fDgiIEw398s9Nu9YktvYZtqOuafdH/cVXxwONIQNw/A8n8sPTbZet1ZxOn0+VPGppcKaUn6aqYeXKUkDLvjaWPjCoSBItDzZCyF7VUqX+aLxvdbeEiHsuv/TI478LdMbzg7NclYCcxcYYz5vP/YLIHJp7+kTq0LmmHauUqfTYwFRpPMUC2rqPvyvQGKzXjUhrQ2F4dur5U7IsybKkKnItXya/p6m/Y/S3Bxi53e5S0gBHt8N9bZV0/r179qJbxs7OJDdfd5O2qjn5zGtcU0g4y4PVErJl7o4khG3aJIhxxmVOguSWUM8Nl0sh/9TRs10X984PTFcnUowzJR6O9idiK5snHz048dgRWZKWakB0e9ma2fzOi/ShueOP/KS1rRlt2+acf+r2r/3X6Ek1XSuNJZkquTtYhuNNBCREdNlznYxsx5ZZ7wd28XhDrVBp7mshAfVClauSU6xO/f6VwslJ91i5mgQAMUTHsINdcSPm+eDKDT/4zr84jrPQBk1MzGy97mOBjV1zTxzjHonEkpXcOvNtSHGIwnLk9siGT10zPzTt8Wp6qpA+Mky6VU8WUICkSBcIG4yhXTfbdm8uvjJ+5OEfd3W1ExFjjAkhurraP3P9tcnRmfi2VWbZwIVO290OLmcJARAI38AbETGZ61PZqWdeibY3CIaSxCvD81aqJEvScjQLczkzy/WmbavmRmc/ff2eFSsSbqPIAIAx5jjiji98dA33WxFPINHo6DYuqG70BtXR5Zze+B8RybI09+IZNG2QMLomoTYGABeix7I+g5CBUzf8iZgd9fSj/4tfuNlxFnp7V5BDRFAV5af/fmf16Gj00l5Jk4XlACICLfFxXjABRrDcv84DI0Rm2MMPH2jqbilOpoRh4aLhlwYjIllC0pSGnb3lI6P3ffdOVVUQF6SVC+WYBx588m/uvKv7qoumfnfItYIrDsGyyIRv5A2WyVMAgkhrixr5KlQNeF2BQ8hAWASIHdduHfnDiV/ceceN79+9XI45n7w457bt3LDvPd+69aaR519L7N3OFcXRrcUER2+E4ap2LotL/xIAIqtPZqBmIFvaBbl+Y+s2U3jHtVvPPXfi7ltvcoW95QLom0t63/3e/Xf88L6OK9bnDw6VJ5JywEdEQIKAvQHT0kNalgOBcCHmLxgUOSKY5XqgozF6ae/EH09885aPfu7TbyXpLcf0mwefvPWrd2tbVkgFPXV4GAC4JhEhvH4CLgARtBgj8HVHAd3WytYtBhDf3uuE1PrRse9/5QtvV/S8QBa++bNfHaBKY09bZWC6ODIPAFyVkaGr8cCbnkNYzDiIIIRt2AAQ7m7297elR2b6efDe73z5T8nCbyWc21+/60f/8fBjRnvIHw6Yk7nKeMqs6siQSRw5Q8TXHUL3iDtC2A4Ikn1aoCuuJqLlYlmdKd2yd/eXvnjLXyKcX3i1MDr57Xt+9tuDh4pB2RcLyRbY6ZKRLVuVujAsIWgh1SAyxrjqXi0EpMaAzbGWKwVL1t4d227/zEd6ujv+8quFN718+c0jTz2+/8BQLl1VkPk1RZU5MBQCCFwnFgwJwDIsp1L3mtQbbbzm8h37rnt3ItHydi9f3tb1lCCi89dTZ04Pv3jg2OETZwYnp5OlYknXTccGAIVzv6o1h0K9ifZtF/Vfdsnmv+B66v8BQ0TjWPySRpIAAAAASUVORK5CYII="
AMPLIFIER_IMG = f'<img src="data:image/png;base64,{AMPLIFIER_B64}" style="width:20px;height:20px;border-radius:50%;vertical-align:middle;margin-right:4px;">'
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

KNOWN ENTITY SPELLINGS — always spell these correctly:
- Sean Payton (NOT Shawn Payton) — Broncos head coach
- Courtland Sutton (NOT Sutton Courtland)
- Nikola Jokic (NOT Jokić — skip the accent in tweet text)
- J.K. Dobbins (NOT JK Dobbins or J.K Dobbins)

IMPORTANT: Never use emojis in your output. Write plain text only."""

_WHATS_HOT_VOICE_GUIDE = """
VOICE SELECTION — read the topic and pick automatically:
DEFAULT: Pure analytical observation. State what the film
shows. Open with a specific stat or fact nobody is tracking.
End with ellipsis that invites the reader to analyze
alongside you. No opinion stated — the facts do that work.
Example: "Jokic in fourth quarter playoff games — 12.4
points on 67% shooting. The defense has no answer for
the high post read..."
CRITICAL: Diagnosis not complaint. Open with one undeniable
stat. Identify the structural cause. Name the specific
person or decision-maker who owns the fix. End with a
period not an ellipsis. Never attack character.
Never say "I played in this league."
Example: "We gave up 6 sacks in losses, 1.2 in wins.
The two-minute protection scheme is broken. Payton owns that."
HOMER: One overlooked signal the casual fan is missing.
State it specifically. Show why it matters. End by showing
a specific outside party already reacting — opposing coaches,
rival programs, national media. Their reaction is the proof.
Never state confidence directly. Never say "I've been in
winning rooms." Show the opposition already worried.
ENDING RULE: The final sentence must name a specific outside
party and show them already responding to what Tyler's team
is doing. NOT Tyler explaining the signal. NOT "this is real."
The opponent's reaction IS the proof — let it speak.
WRONG ENDING: "Position coaches don't travel for guys they're
not serious about." — Tyler explaining the insight
RIGHT ENDING: "Every team picking in that range just added
him to their board." — outside party already responding
Example: "Jokic averaging a triple double in March. The team
drawing Denver in round 2 just redesigned their defensive scheme."
SARCASTIC: Two modes only.
Positive moment → Cultural Leap: Jump to a completely
unrelated world. Specific person in a specific human
situation outside sports. Never explain the joke.
Example: "That cornerback needs to call someone he trusts
right now. Not about football."
Negative moment → Implied Real Story: State the surface
story as if neutral. Imply the real story underneath.
Never state it directly. Never use generic openers like
"Oh interesting" or "Oh cool."
Example: "Turns out the Patriots offense doesn't suck
because of a snow storm."
RULES FOR ALL VOICES:

Never copy feed content — use it as topic inspiration only
Never say "I played in this league" or "I've been in
winning rooms" or "I know what winning looks like"
Authority comes from specificity not stated credentials
Hooks are Normal Tweet length — 161 to 260 characters
No hashtags no emojis no links
Never start a hook with RT or @
"""

# ─── Styles ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap');

/* ═══════════════════════════════════════════════
   RESET & BASE — Midnight Slate / Electric Cyan
═══════════════════════════════════════════════ */
html, body, [class*="css"] { font-family: 'Inter', sans-serif; font-size: 15px; }
#MainMenu { visibility: hidden; }
header[data-testid="stHeader"] { display: none !important; }
footer { visibility: hidden; }
html, body { background-color: #080E1E !important; }
.stApp { background: radial-gradient(ellipse at 50% 35%, #0F2244 0%, #080E1E 45%, #030508 100%) !important; color: #E6EDF3; }
.block-container { max-width: 1280px !important; padding-top: 1.5rem !important; }

/* ═══════════════════════════════════════════════
   SIDEBAR — ICON RAIL
═══════════════════════════════════════════════ */
section[data-testid="stSidebar"] {
  width: 80px !important;
  min-width: 80px !important;
  max-width: 80px !important;
  background: #080E1E !important;
  border-right: 1px solid #14203A !important;
  overflow: visible !important;
}
[data-testid="stSidebarResizeHandle"] { display: none !important; }
section[data-testid="stSidebar"] > div:first-child {
  padding: 0 !important;
  overflow: visible !important;
  height: 100vh !important;
  display: flex !important;
  flex-direction: column !important;
}
[data-testid="stSidebar"] > div:first-child {
  background: linear-gradient(180deg, #0a1628 0%, #070d1a 100%) !important;
  border-right: 1px solid rgba(45,212,191,0.1) !important;
}
[data-testid="stSidebarContent"] {
  height: 100vh !important;
  padding: 0 !important;
}
[data-testid="stSidebarUserContent"] {
  padding: 0 !important;
  height: 100% !important;
}
[data-testid="collapsedControl"],
[data-testid="baseButton-headerNoPadding"],
button[kind="header"],
.st-emotion-cache-1oe5cao,
.st-emotion-cache-nakb8l,
[data-testid="stSidebarCollapseButton"],
[aria-label="Collapse sidebar"] {
  display: none !important;
  visibility: hidden !important;
  width: 0 !important;
  height: 0 !important;
  overflow: hidden !important;
  pointer-events: none !important;
}
[data-testid="stSidebarNav"] { display: none !important; }
[data-testid="stAppViewContainer"] > .main { margin-left: 96px !important; }

/* ═══════════════════════════════════════════════
   PAGE HEADERS
═══════════════════════════════════════════════ */
.main-header {
  font-family: 'Bebas Neue', sans-serif; font-size: 52px; letter-spacing: 3px;
  line-height: 1; margin-bottom: 2px; font-weight: 400; color: rgba(255,255,255,0.75);
}
.main-header span {
  background: linear-gradient(135deg, #2DD4BF 0%, #5eebd4 60%, #8af5e4 100%);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
  filter: drop-shadow(0 0 20px rgba(45,212,191,0.35));
}
.main-header::after {
  content: ''; display: block; width: 44px; height: 2px;
  background: linear-gradient(90deg, #C49E3C, transparent);
  margin-top: 7px; margin-bottom: 4px;
}
.tool-desc { color: #4a5160; font-size: 13px; margin-bottom: 28px; letter-spacing: 0.3px; }

/* ═══════════════════════════════════════════════
   BUTTONS
═══════════════════════════════════════════════ */
.stButton > button {
  border-radius: 100px !important;
  font-family: 'Inter', sans-serif !important; font-weight: 600 !important;
  font-size: 13px !important; padding: 9px 22px !important;
  transition: all 0.2s cubic-bezier(0.34, 1.56, 0.64, 1) !important;
  letter-spacing: 0.3px; white-space: nowrap !important;
}
/* PRIMARY — gradient teal, glow on hover only */
.stButton > button[kind="primary"] {
  background: linear-gradient(135deg, #1fb8a8 0%, #2DD4BF 55%, #5eebd4 100%) !important;
  color: #0B0E14 !important; border: none !important; font-weight: 700 !important;
  box-shadow: none !important;
}
.stButton > button[kind="primary"]:hover {
  transform: translateY(-2px) scale(1.02) !important;
  box-shadow: 0 0 20px rgba(45,212,191,0.4), 0 8px 24px rgba(45,212,191,0.2) !important;
  background: linear-gradient(135deg, #25c4b0 0%, #33dcc8 55%, #8af5e4 100%) !important;
  border: none !important; color: #0B0E14 !important;
}
/* SECONDARY — ghost cyan outlined */
.stButton > button[kind="secondary"] {
  background: transparent !important;
  border: 1px solid rgba(45,212,191,0.25) !important;
  color: #2DD4BF !important; box-shadow: none !important;
}
.stButton > button[kind="secondary"]:hover {
  background: rgba(45,212,191,0.06) !important;
  border-color: rgba(45,212,191,0.6) !important;
  color: #2DD4BF !important; transform: translateY(-1px) !important;
  box-shadow: 0 0 16px rgba(45,212,191,0.15) !important;
}
/* DEFAULT (no kind) — ghost subtle */
.stButton > button:not([kind="primary"]):not([kind="secondary"]) {
  background: transparent !important;
  border: 1px solid #30363d !important;
  color: #8B949E !important;
}
.stButton > button:not([kind="primary"]):not([kind="secondary"]):hover {
  border-color: rgba(45,212,191,0.3) !important;
  color: #E6EDF3 !important; transform: translateY(-1px) !important;
}

/* ═══════════════════════════════════════════════
   SURFACE CARDS — solid depth, no glassmorphism
═══════════════════════════════════════════════ */
/* Pro card (generic reusable surface) */
.pro-card {
  background: #161B22; border: 1px solid rgba(45,212,191,0.15);
  border-radius: 12px; padding: 25px; margin-bottom: 20px;
  box-shadow: 0 10px 30px rgba(0,0,0,0.5);
}
/* Output box */
.output-box {
  background: #161B22; border: 1px solid rgba(45,212,191,0.15);
  border-left: 3px solid #2DD4BF; border-radius: 14px; padding: 20px 22px;
  margin: 12px 0; font-size: 14px; line-height: 1.75; color: #C9D1D9;
  white-space: pre-wrap; font-family: 'JetBrains Mono', monospace;
  box-shadow: 0 4px 20px rgba(0,0,0,0.5);
}
/* Tweet / idea cards */
.tweet-card {
  background: #161B22; border: 1px solid rgba(45,212,191,0.08);
  border-top: 2px solid transparent; border-radius: 14px;
  padding: 16px 20px; margin: 8px 0; position: relative;
  transition: all 0.2s ease;
  box-shadow: 0 4px 20px rgba(0,0,0,0.5);
}
.tweet-card:hover {
  border-color: rgba(45,212,191,0.2); border-top-color: #2DD4BF;
  background: #1c2128;
  box-shadow: 0 4px 28px rgba(0,0,0,0.6), 0 0 0 1px rgba(45,212,191,0.1);
  transform: translateY(-1px);
}
.tweet-num { font-family: 'Bebas Neue', sans-serif; font-size: 13px; color: #2DD4BF; letter-spacing: 1px; margin-bottom: 8px; }
/* Stat cards */
.stat-card {
  background: #161B22; border: 1px solid rgba(45,212,191,0.1);
  border-radius: 16px; padding: 20px; text-align: center; transition: all 0.2s ease;
  box-shadow: 0 4px 20px rgba(0,0,0,0.5);
}
.stat-card:hover { border-color: rgba(45,212,191,0.3); box-shadow: 0 4px 24px rgba(0,0,0,0.6), 0 0 12px rgba(45,212,191,0.08); }
.stat-num { font-family: 'Bebas Neue', sans-serif; font-size: 42px; color: #2DD4BF; line-height: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.stat-label { font-size: 11px; color: #4a5160; text-transform: uppercase; letter-spacing: 2px; margin-top: 4px; }

/* ═══════════════════════════════════════════════
   TAGS
═══════════════════════════════════════════════ */
.tag { display: inline-block; background: rgba(45,212,191,0.04); border: 1px solid rgba(45,212,191,0.12); border-radius: 100px; padding: 2px 10px; font-size: 10px; color: #6E7681; margin: 2px; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase; }
.tag-hot { background: rgba(45,212,191,0.1); color: #2DD4BF; border-color: rgba(45,212,191,0.3); }
.tag-format { background: rgba(45,212,191,0.1); border-color: rgba(45,212,191,0.28); color: #2DD4BF; }
.tag-original { background: rgba(196,158,60,0.1); border-color: rgba(196,158,60,0.28); color: #C49E3C; }
.tag-ai { background: rgba(139,92,246,0.1); border-color: rgba(139,92,246,0.28); color: #8B5CF6; }

/* ═══════════════════════════════════════════════
   INPUTS
═══════════════════════════════════════════════ */
.stTextArea textarea, .stTextInput input {
  background: rgba(255,255,255,0.04) !important;
  border: 1px solid rgba(45,212,191,0.2) !important;
  border-radius: 8px !important; color: #E6EDF3 !important;
  font-family: 'Inter', sans-serif !important; font-size: 14px !important;
  transition: border-color 0.2s ease, box-shadow 0.2s ease !important;
  padding-bottom: 10px !important;
}
.stTextArea textarea:focus, .stTextInput input:focus {
  border-color: rgba(45,212,191,0.55) !important;
  outline: none !important;
  box-shadow: 0 0 0 3px rgba(45,212,191,0.08) !important;
}
.stTextArea textarea { min-height: 60px !important; resize: vertical !important; }
.stSelectbox > div > div {
  background: rgba(255,255,255,0.04) !important;
  border: 1px solid rgba(45,212,191,0.18) !important;
  color: #E6EDF3 !important; border-radius: 12px !important;
}
input[type="number"] { background: #0D1117 !important; border: 1px solid #30363d !important; color: #E6EDF3 !important; border-radius: 8px !important; }
input[type="number"]::-webkit-inner-spin-button, input[type="number"]::-webkit-outer-spin-button { opacity: 0.4; }

/* ═══════════════════════════════════════════════
   TABS
═══════════════════════════════════════════════ */
.stTabs [data-baseweb="tab-list"] { background: #161B22 !important; border: 1px solid rgba(45,212,191,0.1); border-radius: 12px; gap: 2px; padding: 4px; }
.stTabs [data-baseweb="tab"] { background: transparent !important; color: #6E7681 !important; border-radius: 10px !important; font-weight: 600 !important; font-size: 13px !important; transition: all 0.15s ease !important; }
.stTabs [aria-selected="true"] { background: #2DD4BF !important; color: #0B0E14 !important; }
.stSpinner > div > div { border-top-color: #2DD4BF !important; }

/* ═══════════════════════════════════════════════
   EMPTY STATE CANVAS
═══════════════════════════════════════════════ */
.empty-canvas {
  background: #161B22; border: 1px dashed rgba(45,212,191,0.15);
  border-radius: 16px; padding: 60px 40px; text-align: center;
  margin: 16px 0; box-shadow: 0 4px 20px rgba(0,0,0,0.4);
}
.empty-canvas-icon { font-size: 40px; opacity: 0.3; margin-bottom: 16px; }
.empty-canvas-title { font-family: 'Bebas Neue', sans-serif; font-size: 22px; letter-spacing: 2px; color: #3d4450; margin-bottom: 8px; }
.empty-canvas-sub { font-size: 13px; color: #3d4450; }

/* ═══════════════════════════════════════════════
   STAT CARD BORDERS
═══════════════════════════════════════════════ */
[data-testid="metric-container"] {
  background: rgba(255,255,255,0.04) !important;
  border: 1px solid rgba(255,255,255,0.07) !important;
  border-left: 3px solid #2DD4BF !important;
  border-radius: 10px !important;
  padding: 12px 14px !important;
}

/* ═══════════════════════════════════════════════
   MISC
═══════════════════════════════════════════════ */
.section-divider { border: none; border-top: 1px solid rgba(45,212,191,0.06); margin: 28px 0; }
/* Reserve right space for the floating Inspiration Engine panel (added by JS on Reply Mode) */
body.rg-insp-active .block-container { padding-right: 270px !important; }
.metric-label { font-size: 12px; color: #6E7681; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; }
.metric-score { font-family: 'JetBrains Mono', monospace; font-size: 18px; color: #2DD4BF; }
.score-bar-wrap { background: #21262d; border-radius: 100px; height: 6px; width: 100%; margin: 6px 0 12px; overflow: hidden; }
.score-bar-fill { height: 100%; border-radius: 100px; transition: width 0.8s ease; }
.char-count { font-size: 12px; color: #4a5160; text-align: right; margin-top: -10px; margin-bottom: 10px; }
.char-over { color: #f85149 !important; }
.tweet-link { font-size: 11px; color: #58a6ff; text-decoration: none; letter-spacing: 0.5px; opacity: 0.8; }
.tweet-link:hover { opacity: 1; }

/* Chat */
.chat-msg { border-radius: 14px; padding: 20px 24px; margin: 12px 0; }
.chat-user { background: #161B22; border-left: 2px solid #30363d; }
.chat-ai { background: rgba(45,212,191,0.03); border-left: 3px solid #2DD4BF; }
.chat-role { font-size: 10px; color: #4a5160; font-weight: 700; text-transform: uppercase; letter-spacing: 2.5px; margin-bottom: 10px; }

/* Progress bar */
.progress-bar-bg { background: #21262d; border-radius: 100px; height: 12px; width: 100%; overflow: hidden; }
.progress-bar-fill { height: 100%; border-radius: 100px; background: linear-gradient(90deg, #2DD4BF, #5eebd4); transition: width 0.5s; }

/* Scrollbar */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: rgba(45,212,191,0.35); border-radius: 2px; }
::-webkit-scrollbar-thumb:hover { background: rgba(45,212,191,0.6); }

/* Watermark */
.main-watermark {
  position: fixed; bottom: 60px; right: 40px; z-index: 0; pointer-events: none;
  font-family: 'Bebas Neue', sans-serif; font-size: 120px; letter-spacing: 8px;
  line-height: 1; user-select: none;
  background: linear-gradient(135deg, rgba(45,212,191,0.03), rgba(45,212,191,0.01));
  -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}

/* Branded footer */
.hq-footer { text-align: center; padding: 24px 0 8px 0; margin-top: 40px; border-top: 1px solid rgba(45,212,191,0.06); }
.hq-footer a { color: #2DD4BF; text-decoration: none; font-size: 12px; letter-spacing: 1.5px; font-weight: 600; text-transform: uppercase; opacity: 0.6; margin: 0 12px; }
.hq-footer a:hover { opacity: 1; }

/* Day card */
.rg-week-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 4px; margin-bottom: 8px; }
.day-card { background: #161B22; border: 1px solid rgba(45,212,191,0.08); border-radius: 7px; padding: 5px 2px; text-align: center; }
.day-card-label { color: #6E7681; font-size: 9px; text-transform: uppercase; letter-spacing: 0.5px; }
.day-card-num { color: #E6EDF3; font-size: 15px; font-weight: 700; font-family: 'JetBrains Mono', monospace; line-height: 1.2; }
.day-card-active .day-card-num { color: #2DD4BF; }
.day-card-active { border-color: rgba(45,212,191,0.25); border-top: 2px solid #2DD4BF; }
@media (max-width: 640px) { .rg-week-grid { display: none; } }

/* Hide Streamlit chrome */
[data-testid="manage-app-button"] { display: none !important; }
[data-testid="stToolbarActions"] { display: none !important; }
.stDeployButton { display: none !important; }
.block-container { padding-bottom: 2rem !important; }
.main > div { padding-bottom: 0 !important; }

/* Slider */
.stSlider .st-br { background: #2DD4BF !important; }

/* Expander */
.streamlit-expanderHeader { color: #8B949E !important; }

/* Grade panel — left list uses button + overlay pattern */

/* Creator Studio 3-col grid */
.cs-panel-label {
  font-size: 9px; color: #4a5160; font-weight: 700; letter-spacing: 2.5px;
  text-transform: uppercase; margin-bottom: 14px; padding-bottom: 10px;
  border-bottom: 1px solid rgba(45,212,191,0.06);
}
.cs-params-wrap {
  background: #131920; border-radius: 12px;
  border: 1px solid rgba(45,212,191,0.06);
  padding: 16px; height: 100%;
}
.format-guide {
  background: #161B22; border: 1px solid rgba(45,212,191,0.1);
  border-top: 2px solid #2DD4BF; border-radius: 10px;
  padding: 14px 16px; margin-bottom: 12px;
}
.fg-format { font-family: 'Bebas Neue', sans-serif; font-size: 18px; color: #2DD4BF; letter-spacing: 1.5px; margin-bottom: 4px; }
.fg-chars { font-size: 11px; color: #6E7681; font-family: 'JetBrains Mono', monospace; margin-bottom: 10px; }
.fg-rule { font-size: 12px; color: #8B949E; padding: 3px 0 3px 10px; border-left: 2px solid rgba(45,212,191,0.2); margin-bottom: 4px; }
.cs-nav-link { display: block; padding: 8px 10px; border-radius: 8px; font-size: 12px; color: #6E7681; text-decoration: none; cursor: pointer; transition: all 0.15s; margin-bottom: 4px; border: 1px solid transparent; }
.cs-nav-link:hover { background: rgba(45,212,191,0.05); border-color: rgba(45,212,191,0.15); color: #2DD4BF; }
.canvas-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; padding-bottom: 10px; border-bottom: 1px solid rgba(45,212,191,0.06); }
.canvas-title { font-size: 9px; color: #4a5160; font-weight: 700; letter-spacing: 2.5px; text-transform: uppercase; }

/* Mobile */
@media screen and (max-width: 768px) {
    /* Hide Streamlit toolbar chrome */
    [data-testid="stToolbar"],
    [data-testid="stDecoration"],
    [data-testid="stAppDeployButton"],
    [data-testid="stMainMenu"],
    [data-testid="stMainMenuButton"],
    .st-emotion-cache-1dp5vir,
    .st-emotion-cache-15zrgzn { display: none !important; }

    /* Hide sidebar — JS injects hamburger + overlay instead */
    section[data-testid="stSidebar"] { display: none !important; }

    /* Main content full-width, leave room for hamburger button */
    [data-testid="stAppViewContainer"] > section.main,
    [data-testid="stMain"] {
        margin-left: 0 !important;
        padding-top: 60px !important;
    }
}
/* ─── Global color tokens ──────────────────────────────────────────── */
:root { --mp-cyan: #00E5CC; --mp-gold: #C49E3C; --mp-navy: #080E1E; --mp-steel: #91A2B2; }
[data-testid="stMetricValue"] { color: #C49E3C !important; }
hr { border-color: #14203A !important; }
[data-testid="stExpander"] summary p { color: #00E5CC !important; }

</style>
""", unsafe_allow_html=True)


# ─── Helpers ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600)
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
- "We passed on 52% of third downs last year and went 8-9. Meanwhile Kansas City ran on 3rd-and-short 74% of the time and won the Super Bowl. That gap is a choice. Who owns it?"
- "The Broncos have had 5 different offensive coordinators in 8 years. And we keep wondering why the offense looks confused. That's on the front office. Connect the dots."
- "Bo Nix threw for 3,000 yards last season. Good. But 18 of those touchdowns came against bottom-10 defenses. Payton needs to answer for that schedule construction."

CRITICAL VOICE RULES:
- Always open with a SPECIFIC number, stat, or named failure — never a vague complaint
- Identify the structural cause — not "they need to be better"
- End by naming the specific person who owns it. Period. Full stop. Never ellipsis.
- Authority IMPLIED through specificity — never say "I played in this league" or "I know what accountability looks like"
- Tone: disappointed not angry. Calm, credible, constructive.""",

        "Homer": """EXAMPLES OF TYLER WRITING IN HOMER VOICE (copy this exact energy):
- "Jokic dropped 30, 12, and 10 last night. On a Tuesday. The team drawing Denver in round 2 just changed their entire defensive game plan."
- "Bo Nix's third down completion rate jumped 12% in the second half. Every defensive coordinator in the AFC pulled up that film tonight."
- "MacKinnon and Makar both locked in at the same time in April for the first time in three years. The rest of the West is recalculating everything."

HOMER VOICE RULES:
- Always use "we" or "this team" — the reader is part of the belief
- Ground optimism in something SPECIFIC — a player, a stat, a moment
- End by showing the OPPONENT'S reaction — their worry is the proof. Not "we're ready" — "they're already adjusting"
- Authority IMPLIED through specificity — never say "I've been in winning rooms" or "I've watched enough film to know"
- Tone: infectious, grounded confidence. Earned optimism, not blind cheerleading.""",

        "Sarcastic": """EXAMPLES OF TYLER WRITING IN SARCASTIC VOICE (copy this exact energy):
- "Turns out the Patriots offense doesn't suck because of a snow storm."
- "That cornerback needs to call someone he trusts right now. Not about football."
- "Starting to feel like Bo Nix really should have played with a broken ankle."
- "Bold of Skip to finally come out and say it."

SARCASTIC VOICE RULES:
- Two modes: Cultural Leap (positive moments) or Implied Real Story (negative moments)
- Cultural Leap: Jump to a completely unrelated world. Specific person in a specific human situation. Never explain.
- Implied Real Story: State the surface story as if neutral. Imply the real story underneath. Never state it directly.
- Never use generic openers like "Oh interesting" "Sure" "Cool" "Oh great" — find the specific reaction that fits THIS moment
- Authority implied through specificity — never stated
- Drop it and walk away. Never explain the joke.""",
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

    return f"""
TYLER'S PERSONAL TWEET BENCHMARKS (from his actual tweet history):

Character Length:
- Sweet spot: {opt_range[0]}–{opt_range[1]} characters

Style Patterns (top performers):
- {patterns.get("top_ellipsis_pct", 0)}% use ellipsis (...) — his signature
- {patterns.get("top_question_pct", 0)}% end with a question
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


_VOICE_LABELS = {"Default": "Film Room", "Critical": "Diagnosis", "Homer": "Don't Sleep", "Sarcastic": "Layered"}


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
        card = f'''<div style="background:rgba(255,255,255,0.04);border:0.5px solid rgba(255,255,255,0.1);border-radius:10px;padding:14px 16px;margin-bottom:0;">
<div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;">
<div style="width:32px;height:32px;border-radius:50%;background:#0C1630;border:1.5px solid #2DD4BF;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:600;color:#2DD4BF;flex-shrink:0;">TP</div>
<div style="flex:1;"><div style="font-size:13px;font-weight:600;color:rgba(255,255,255,0.9);">Tyler Polumbus</div><div style="font-size:11px;color:rgba(255,255,255,0.4);">@tyler_polumbus</div></div>
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
            with urllib.request.urlopen(req, timeout=15) as resp:
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
    _ver = "2.1.86"
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
            "User-Agent": f"claude-cli/{_ver}",
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
    with urllib.request.urlopen(req, timeout=90) as resp:
        data = json.loads(resp.read())
    if "content" in data and data["content"]:
        return data["content"][0].get("text", "")
    raise Exception(f"API error: {data.get('error', data)}")


def _call_with_token(token: str, prompt: str, system: str, max_tokens: int, model: str = "claude-sonnet-4-6") -> str:
    """Thread-safe direct API call — token passed in, no session state access."""
    import urllib.request, hashlib as _hl
    _salt = "59cf53e54c78"
    _ver = "2.1.86"
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
            "User-Agent": f"claude-cli/{_ver}", "x-app": "cli",
            "anthropic-dangerous-direct-browser-access": "true",
            "x-stainless-lang": "js", "x-stainless-os": "Linux",
            "x-stainless-arch": "x64", "x-stainless-runtime": "node",
            "x-stainless-package-version": "0.74.0", "x-stainless-retry-count": "0",
        }, method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
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
    with urllib.request.urlopen(req, timeout=90) as resp:
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
            with urllib.request.urlopen(req, timeout=20) as resp:
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
        result = subprocess.run([XURL, "post", text], capture_output=True, text=True, timeout=15)
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


def call_claude(prompt: str, system: str = None, max_tokens: int = 1500, model: str = "claude-sonnet-4-6") -> str:
    if system is None:
        system = get_voice_context()

    # 1. Direct OAuth HTTP — fastest, no subprocess overhead
    try:
        return _call_claude_direct(prompt, system or "", max_tokens, model)
    except Exception:
        pass

    # 2. Local CLI fallback
    if os.path.exists(CLAUDE_CLI):
        try:
            clean_env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
            cmd = [CLAUDE_CLI, "-p", "--model", model]
            if system:
                cmd += ["--system-prompt", system]
            result = subprocess.run(
                cmd,
                input=prompt, capture_output=True, text=True, timeout=90, env=clean_env,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass

    # 3. Proxy server (Streamlit Cloud path — ngrok to Tyler's local machine)
    try:
        return _call_claude_proxy(prompt, system or "", max_tokens, model)
    except Exception:
        pass

    return "AI unavailable — check proxy or credentials."


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


ENGAGEMENT_LISTS_PATH = DATA_DIR / 'engagement_lists.json'

_ENGAGEMENT_DEFAULTS = {
    'Broncos Reporters': {'list_id': '1294328608417177604'},
    'Nuggets':           {'list_id': '1755985316752642285'},
    'Morning Engagement':{'list_id': '2011987998699897046'},
    'Work':              {'list_id': '1182699241329721344'},
}

def load_engagement_lists() -> dict:
    if ENGAGEMENT_LISTS_PATH.exists():
        try:
            loaded = json.loads(ENGAGEMENT_LISTS_PATH.read_text())
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
    return {k: dict(v) for k, v in _ENGAGEMENT_DEFAULTS.items()}

def save_engagement_lists(lists: dict):
    ENGAGEMENT_LISTS_PATH.write_text(json.dumps(lists, indent=2))


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
            timeout=30,
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
# Always sync page from query params (enables HTML link navigation)
# _nav_override flag lets button-driven navigation skip the query param override
_qp_page = st.query_params.get("page", "")
if st.session_state.pop("_nav_override", False):
    pass  # session_state.current_page already set by the button handler — keep it
elif _qp_page:
    st.session_state.current_page = _qp_page
else:
    st.session_state.current_page = "Creator Studio"
# Clear ?page= from browser URL so refresh always lands on Creator Studio
# st.markdown strips <script> tags — must use components.html for JS execution
if _qp_page:
    import streamlit.components.v1 as _components
    _components.html('<script>window.parent.history.replaceState(null,"",window.parent.location.pathname)</script>', height=0)

_cur_pg = st.session_state.current_page

def _act(name):
    return "active" if _cur_pg == name else ""

_sidebar_html = f"""
<style>
.mp-rail {{
    display: flex; flex-direction: column; align-items: center;
    padding: 14px 8px 16px; gap: 10px; justify-content: flex-start;
    height: 100vh; position: fixed; top: 0; left: 0; width: 80px;
    background: #080E1E; z-index: 999; overflow: visible;
}}
.mp-logo {{
    width: 52px; height: 52px; background: #0D1E36; border-radius: 10px;
    border: 1px solid #1E3050; display: flex; align-items: center; justify-content: center;
    margin-bottom: 8px; flex-shrink: 0; text-decoration: none !important;
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

  <a href="/?page=Creator+Studio" class="mp-logo" target="_self">
    <svg width="26" height="26" viewBox="0 0 20 20" fill="none">
      <polygon points="10,2 19,18 1,18" stroke="#C49E3C" stroke-width="1.2" stroke-linejoin="round" fill="none"/>
      <polygon points="10,7 15,17 5,17" fill="#C49E3C" opacity="0.25"/>
      <circle cx="10" cy="2" r="1.2" fill="#00E5CC"/>
    </svg>
  </a>

  <div class="mp-zone mp-zone-create">
    <div class="mp-zone-label">CREATE</div>
    <a href="/?page=Creator+Studio" class="mp-ico {_act('Creator Studio')}" target="_self">
      <div class="mp-active-pip"></div>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <path d="M12 20h9" stroke="#00E5CC" stroke-width="1.5" stroke-linecap="round" opacity="0.9"/>
        <path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4 12.5-12.5z" stroke="#00E5CC" stroke-width="1.5" stroke-linejoin="round" opacity="0.9"/>
      </svg>
    </a>
    <a href="/?page=Raw+Thoughts" class="mp-ico {_act('Raw Thoughts')}" target="_self">
      <div class="mp-active-pip"></div>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="10" stroke="#00E5CC" stroke-width="1.5" opacity="0.4"/>
        <path d="M12 8v4l3 3" stroke="#00E5CC" stroke-width="1.5" stroke-linecap="round" opacity="0.4"/>
      </svg>
    </a>
    <a href="/?page=Content Coach" class="mp-ico {_act('Content Coach')}" target="_self">
      <div class="mp-active-pip"></div>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" stroke="#00E5CC" stroke-width="1.5" stroke-linejoin="round" opacity="0.4"/>
      </svg>
    </a>
    <a href="/?page=Article+Writer" class="mp-ico {_act('Article Writer')}" target="_self">
      <div class="mp-active-pip"></div>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" stroke="#00E5CC" stroke-width="1.5" stroke-linejoin="round" opacity="0.4"/>
        <polyline points="14 2 14 8 20 8" stroke="#00E5CC" stroke-width="1.5" stroke-linejoin="round" opacity="0.4"/>
        <line x1="16" y1="13" x2="8" y2="13" stroke="#00E5CC" stroke-width="1.5" stroke-linecap="round" opacity="0.4"/>
      </svg>
    </a>
    <a href="/?page=Signals+%26+Prompts" class="mp-ico {_act('Signals & Prompts')}" target="_self">
      <div class="mp-active-pip"></div>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <path d="M22 12h-4l-3 9L9 3l-3 9H2" stroke="#00E5CC" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.4"/>
      </svg>
    </a>
    <div class="mp-panel">
      <div class="mp-panel-header">CREATE</div>
      <a href="/?page=Creator+Studio" class="mp-panel-item {_act('Creator Studio')}" target="_self">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M12 20h9" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4 12.5-12.5z" stroke="#6B8AAA" stroke-width="1.5" stroke-linejoin="round"/></svg>
        Creator Studio
      </a>
      <a href="/?page=Raw+Thoughts" class="mp-panel-item {_act('Raw Thoughts')}" target="_self">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="#6B8AAA" stroke-width="1.5"/><path d="M12 8v4l3 3" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round"/></svg>
        Raw Thoughts
      </a>
      <a href="/?page=Content Coach" class="mp-panel-item {_act('Content Coach')}" target="_self">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" stroke="#6B8AAA" stroke-width="1.5" stroke-linejoin="round"/></svg>
        Content Coach
      </a>
      <a href="/?page=Article+Writer" class="mp-panel-item {_act('Article Writer')}" target="_self">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" stroke="#6B8AAA" stroke-width="1.5" stroke-linejoin="round"/><polyline points="14 2 14 8 20 8" stroke="#6B8AAA" stroke-width="1.5"/><line x1="16" y1="13" x2="8" y2="13" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round"/></svg>
        Article Writer
      </a>
      <a href="/?page=Signals+%26+Prompts" class="mp-panel-item {_act('Signals & Prompts')}" target="_self">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M22 12h-4l-3 9L9 3l-3 9H2" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
        Signals & Prompts
      </a>
    </div>
  </div>

  <div class="mp-zone mp-zone-interact">
    <div class="mp-zone-label">INTERACT</div>
    <a href="/?page=Reply+Mode" class="mp-ico {_act('Reply Mode')}" target="_self">
      <div class="mp-active-pip"></div>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <polyline points="17 1 21 5 17 9" stroke="#C49E3C" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.6"/>
        <path d="M3 11V9a4 4 0 014-4h14" stroke="#C49E3C" stroke-width="1.5" stroke-linecap="round" opacity="0.6"/>
        <polyline points="7 23 3 19 7 15" stroke="#C49E3C" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.6"/>
        <path d="M21 13v2a4 4 0 01-4 4H3" stroke="#C49E3C" stroke-width="1.5" stroke-linecap="round" opacity="0.6"/>
      </svg>
    </a>
    <a href="/?page=Idea+Bank" class="mp-ico {_act('Idea Bank')}" target="_self">
      <div class="mp-active-pip"></div>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <path d="M12 2L2 7l10 5 10-5-10-5z" stroke="#C49E3C" stroke-width="1.5" stroke-linejoin="round" opacity="0.6"/>
        <path d="M2 17l10 5 10-5" stroke="#C49E3C" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.6"/>
        <path d="M2 12l10 5 10-5" stroke="#C49E3C" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.6"/>
      </svg>
    </a>
    <a href="/?page=R%26D+Council" class="mp-ico {_act('R&D Council')}" target="_self">
      <div class="mp-active-pip"></div>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="5" r="3" stroke="#C49E3C" stroke-width="1.5" opacity="0.6"/>
        <circle cx="4" cy="19" r="3" stroke="#C49E3C" stroke-width="1.5" opacity="0.6"/>
        <circle cx="20" cy="19" r="3" stroke="#C49E3C" stroke-width="1.5" opacity="0.6"/>
        <line x1="12" y1="8" x2="4" y2="16" stroke="#C49E3C" stroke-width="1.5" opacity="0.6"/>
        <line x1="12" y1="8" x2="20" y2="16" stroke="#C49E3C" stroke-width="1.5" opacity="0.6"/>
        <line x1="4" y1="19" x2="20" y2="19" stroke="#C49E3C" stroke-width="1.5" opacity="0.6"/>
      </svg>
    </a>
    <div class="mp-panel">
      <div class="mp-panel-header">INTERACT</div>
      <a href="/?page=Reply+Mode" class="mp-panel-item {_act('Reply Mode')}" target="_self">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><polyline points="17 1 21 5 17 9" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M3 11V9a4 4 0 014-4h14" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round"/><polyline points="7 23 3 19 7 15" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M21 13v2a4 4 0 01-4 4H3" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round"/></svg>
        Reply Mode
      </a>
      <a href="/?page=Idea+Bank" class="mp-panel-item {_act('Idea Bank')}" target="_self">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M12 2L2 7l10 5 10-5-10-5z" stroke="#6B8AAA" stroke-width="1.5" stroke-linejoin="round"/><path d="M2 17l10 5 10-5" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M2 12l10 5 10-5" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
        Idea Bank
      </a>
      <a href="/?page=R%26D+Council" class="mp-panel-item {_act('R&D Council')}" target="_self">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="5" r="3" stroke="#6B8AAA" stroke-width="1.5"/><circle cx="4" cy="19" r="3" stroke="#6B8AAA" stroke-width="1.5"/><circle cx="20" cy="19" r="3" stroke="#6B8AAA" stroke-width="1.5"/><line x1="12" y1="8" x2="4" y2="16" stroke="#6B8AAA" stroke-width="1.5"/><line x1="12" y1="8" x2="20" y2="16" stroke="#6B8AAA" stroke-width="1.5"/><line x1="4" y1="19" x2="20" y2="19" stroke="#6B8AAA" stroke-width="1.5"/></svg>
        R&D Council
      </a>
    </div>
  </div>

  <div class="mp-zone mp-zone-insights">
    <div class="mp-zone-label">INSIGHTS</div>
    <a href="/?page=Post+History" class="mp-ico {_act('Post History')}" target="_self">
      <div class="mp-active-pip"></div>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <circle cx="12" cy="12" r="10" stroke="#91A2B2" stroke-width="1.5" opacity="0.5"/>
        <polyline points="12 6 12 12 16 14" stroke="#91A2B2" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.5"/>
      </svg>
    </a>
    <a href="/?page=Algorithm+Score" class="mp-ico {_act('Algorithm Score')}" target="_self">
      <div class="mp-active-pip"></div>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <line x1="18" y1="20" x2="18" y2="10" stroke="#91A2B2" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>
        <line x1="12" y1="20" x2="12" y2="4" stroke="#91A2B2" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>
        <line x1="6" y1="20" x2="6" y2="14" stroke="#91A2B2" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>
      </svg>
    </a>
    <a href="/?page=Account+Audit" class="mp-ico {_act('Account Audit')}" target="_self">
      <div class="mp-active-pip"></div>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <path d="M22 11.08V12a10 10 0 11-5.93-9.14" stroke="#91A2B2" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>
        <polyline points="22 4 12 14.01 9 11.01" stroke="#91A2B2" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.5"/>
      </svg>
    </a>
    <a href="/?page=My+Stats" class="mp-ico {_act('My Stats')}" target="_self">
      <div class="mp-active-pip"></div>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" stroke="#91A2B2" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" opacity="0.5"/>
      </svg>
    </a>
    <a href="/?page=Profile+Analyzer" class="mp-ico {_act('Profile Analyzer')}" target="_self">
      <div class="mp-active-pip"></div>
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
        <circle cx="11" cy="11" r="8" stroke="#91A2B2" stroke-width="1.5" opacity="0.5"/>
        <line x1="21" y1="21" x2="16.65" y2="16.65" stroke="#91A2B2" stroke-width="1.5" stroke-linecap="round" opacity="0.5"/>
      </svg>
    </a>
    <div class="mp-panel">
      <div class="mp-panel-header">INSIGHTS</div>
      <a href="/?page=Post+History" class="mp-panel-item {_act('Post History')}" target="_self">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="10" stroke="#6B8AAA" stroke-width="1.5"/><polyline points="12 6 12 12 16 14" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
        Post History
      </a>
      <a href="/?page=Algorithm+Score" class="mp-panel-item {_act('Algorithm Score')}" target="_self">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><line x1="18" y1="20" x2="18" y2="10" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round"/><line x1="12" y1="20" x2="12" y2="4" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round"/><line x1="6" y1="20" x2="6" y2="14" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round"/></svg>
        Algorithm Score
      </a>
      <a href="/?page=Account+Audit" class="mp-panel-item {_act('Account Audit')}" target="_self">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M22 11.08V12a10 10 0 11-5.93-9.14" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round"/><polyline points="22 4 12 14.01 9 11.01" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
        Account Audit
      </a>
      <a href="/?page=My+Stats" class="mp-panel-item {_act('My Stats')}" target="_self">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
        My Stats
      </a>
      <a href="/?page=Profile+Analyzer" class="mp-panel-item {_act('Profile Analyzer')}" target="_self">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none"><circle cx="11" cy="11" r="8" stroke="#6B8AAA" stroke-width="1.5"/><line x1="21" y1="21" x2="16.65" y2="16.65" stroke="#6B8AAA" stroke-width="1.5" stroke-linecap="round"/></svg>
        Profile Analyzer
      </a>
    </div>
  </div>

  <div class="mp-pro">PRO</div>
</div>

"""

with st.sidebar:
    st.markdown(_sidebar_html, unsafe_allow_html=True)

# ── Desktop flyout panels (JS, same-origin iframe) ──────────────────────────
import streamlit.components.v1 as _stc
_stc.html("""<script>
(function(){
  var doc=window.parent.document;
  var win=window.parent;

  /* ── Desktop flyout panels ── */
  if(win.innerWidth<=768) return;
  function init(){
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
})();
</script>""", height=0)

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
    <div style="font-size:13px;font-weight:700;color:#2DD4BF;letter-spacing:3px;line-height:1.8;">MOUNT<br>POLUMBUS</div>
    <label for="_mob_chk" style="font-size:32px;cursor:pointer;color:#667;line-height:1;padding:4px 8px;">&#215;</label>
  </div>
  <div style="{_sec}">CREATE</div>
  <a href="/?page=Creator+Studio" target="_self" style="{_lnk}">Creator Studio</a>
  <a href="/?page=Raw+Thoughts" target="_self" style="{_lnk}">Raw Thoughts</a>
  <a href="/?page=Content Coach" target="_self" style="{_lnk}">Content Coach</a>
  <a href="/?page=Article+Writer" target="_self" style="{_lnk}">Article Writer</a>
  <a href="/?page=Signals+%26+Prompts" target="_self" style="{_lnk}">Signals & Prompts</a>
  <div style="{_sec}">INTERACT</div>
  <a href="/?page=Reply+Mode" target="_self" style="{_lnk}">Reply Mode</a>
  <a href="/?page=Idea+Bank" target="_self" style="{_lnk}">Idea Bank</a>
  <a href="/?page=R%26D+Council" target="_self" style="{_lnk}">R&D Council</a>
  <div style="{_sec}">INSIGHTS</div>
  <a href="/?page=Post+History" target="_self" style="{_lnk}">Post History</a>
  <a href="/?page=Algorithm+Score" target="_self" style="{_lnk}">Algorithm Score</a>
  <a href="/?page=Account+Audit" target="_self" style="{_lnk}">Account Audit</a>
  <a href="/?page=My+Stats" target="_self" style="{_lnk}">My Stats</a>
  <a href="/?page=Profile+Analyzer" target="_self" style="{_lnk}">Profile Analyzer</a>
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
                time.sleep(1)
                st.rerun()
            else:
                st.session_state.bd_timer_end = None
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
            st.markdown('<div style="padding:16px;border-radius:8px;background:#0d1929;border:1px solid #1a2540;color:#3a5070;font-style:italic;text-align:center;">No saved thoughts yet.</div>', unsafe_allow_html=True)
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
_FORMAT_GUIDES = {
    "Punchy Tweet":  {"chars": "≤ 160 chars", "icon": "⚡", "rules": ["2 sentences only", "Take + engagement hook", "No hashtags, no ellipsis", "Every word earns its place"]},
    "Normal Tweet":  {"chars": "161 – 260 chars", "icon": "✦", "rules": ["Hook + line break + payoff", "Question OR ellipsis (not both)", "Stop the scroll in 8 words", "No links, no hashtags"]},
    "Long Tweet":    {"chars": "280 – 1200 chars", "icon": "◈", "rules": ["First 280 must work standalone", "Short paras + line breaks", "Comparison lists hit hard", "End with debate invite"]},
    "Thread":        {"chars": "5 – 8 tweets", "icon": "≡", "rules": ["Each tweet stands alone", "Tweet 1 = scroll stopper", "Tweet 7+ = replies CTA", "One stat-heavy tweet minimum"]},
    "Article":       {"chars": "1500 – 2000 words", "icon": "▣", "rules": ["Hero image REQUIRED", "Subheadings every 300 words", "Bold 2-3 key stats/section", "End with discussion question"]},
}


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
            with urllib.request.urlopen(req, timeout=8) as resp:
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
    """Return the voice instruction block for the given voice mode."""
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
Default and Homer territory. Critical closes the door.
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
- "This is your reminder" — generic, not Tyler's voice
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

    elif voice == "Homer":
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
Homer does NOT:
- End with ellipsis
- End with a question
- Express hope ("I believe we can...")
- State Tyler's confidence directly

Homer DOES on negative topics:
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
Homer's authority comes from the signal and the outside reaction,
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
  distribution — Homer is the algorithmically favored
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
- "This is your reminder" — generic, not Tyler's voice
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
  this roster over the line?" — This is Default voice. Homer
  never asks questions. Homer states what's already happening.
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

WRONG (negative topic drift — this is Default voice not Homer):
"Jokic is putting up career numbers and the Nuggets are still
losing... Every team in the West is watching this window close
in real time..."
→ Ellipsis ending. No outside party reacting. Wrong voice.

RIGHT (negative topic, Homer voice):
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
- "This is your reminder" — generic, not Tyler's voice
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
- "This is your reminder" — generic, not Tyler's voice
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
- Use the voice mode's signature move (ellipsis for Default, hard stop for Critical, forward statement for Homer) in the final line
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

    _voice_override = "" if _is_default else f"\nVOICE: You MUST write in {voice} voice as described in the system prompt. Do NOT fall back to Tyler's default tone.\n"

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
        _hook_rule = "- Model the hook after one of Tyler's top hooks above" if _is_default else ""
        return f"""FORMAT: NORMAL TWEET (161-260 characters)
{_voice_override}
TYLER'S LIVE DATA (from synced tweet history — updates every sync):
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
- BANNED first words: "Broncos should" "Broncos need" "Broncos must"
  "Broncos take" "This is" "No brainer" "Obviously" "Clearly"
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
TYLER'S LIVE DATA (updates every sync):
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
TYLER'S LIVE DATA (updates every sync):
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
        _hook_rule_art = "- Model after Tyler's top hooks above" if _is_default else ""
        return f"""FORMAT: X ARTICLE (1,500-2,000 words / 6-8 minute read)
{_voice_override}
WHY ARTICLES MATTER: X Articles grew 20x since Dec 2025 ($2.15M contest prizes). They keep users on-platform (no link penalty), generate 2+ min dwell time (+10 algorithm weight), and Premium subscribers get 2-4x reach boost. This is the HIGHEST PRIORITY content format.

TYLER'S LIVE DATA (updates every sync):
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
    """Get format patterns for fmt — gist cache first, then fresh analysis, with gist save."""
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
        _fmt_note = f"Format: Punchy Tweet (target: under 160 chars). Tyler's top punchy tweets avg {_fp_avg} chars."
        _fmt_fix_a = "exact edit to compress under 160 chars"
        _char_guide = "under 160"
    elif fmt == "Normal Tweet":
        _nt_lo = max(_fp_lo, 161)
        _nt_hi = min(_fp_hi, 260)
        _fmt_note = f"Format: Normal Tweet (target: {_nt_lo}-{_nt_hi} chars). Tyler's top normal tweets avg {_fp_avg} chars."
        _fmt_fix_a = f"exact edit to land in {_nt_lo}-{_nt_hi} char range"
        _char_guide = f"{_nt_lo}-{_nt_hi}"
    elif fmt == "Long Tweet":
        _fmt_note = f"Format: Long Tweet (target: 600-1200 chars). Tyler's top long tweets avg {_fp_avg} chars."
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
        _fmt_note = f"Format: {fmt}. Tyler's top tweets avg {_fp_avg} chars."
        _fmt_fix_a = "exact edit to first line"
        _char_guide = f"{_fp_lo}-{_fp_hi}"

    _benchmarks = f"""TYLER'S PERSONAL BENCHMARKS (from synced tweet history):
- {_fp_q}% of his top tweets use questions — benchmark for Conversation Catalyst
- {_fp_ell}% of his top tweets use ellipsis — benchmark for Voice Match
- Optimal char range: {_fp_lo}-{_fp_hi} — benchmark for Format Fit
- {_fmt_note}"""

    _prompt_a = f"""Grade this tweet for X algorithm performance.\n\n{_algo}\n\n{_benchmarks}\n\n[TWEET]: "{{tweet_text}}" ({{char_count}} chars)\nHas question mark: {{has_q}} | Has ellipsis: {{has_ell}}\n\nGrade ONLY these 4 categories (score 1-10). Also compute algorithm_score and tyler_score (0-100).\n\nReturn ONLY valid JSON:\n{{"algorithm_score":0,"tyler_score":0,"grades":[{{"name":"Hook Strength","score":0,"detail":"...","fix":"{_fmt_fix_a}"}},{{"name":"Conversation Catalyst","score":0,"detail":"benchmark: {_fp_q}% question rate","fix":"exact edit to drive replies"}},{{"name":"Bookmark Worthiness","score":0,"detail":"...","fix":"exact stat or insight to add"}},{{"name":"Share/Quote Potential","score":0,"detail":"...","fix":"exact phrasing to sharpen the take"}}]}}"""

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
    _live_stats_block = ""
    _sports_ctx = ""
    if action in ("banger", "build", "rewrite") and tweet_text.strip():
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
                    try: _live_stats_block = _fut_stats.result(timeout=15)
                    except Exception: pass
                if _fut_sports:
                    try: _sports_ctx = f"\n\nLIVE SPORTS CONTEXT (use if relevant to the tweet):\n{_fut_sports.result(timeout=15)}"
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
- Tyler's voice: direct, no hedging, former-player authority
- Specific players/schemes/numbers only
- Include [IMAGE] markers where supporting visuals should go
- End with debate invitation to drive replies"""
        article_prompt = f"""Tyler wrote this concept. Expand it into {'a short sarcastic column' if _is_sarcastic else 'a complete X Article'} — preserve his core take and phrasing as the foundation, then build around it.

Tyler's concept: "{tweet_text}"

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
                _fmt_inject = f"\n\nFORMAT PATTERNS (from top-performing tweets on Tyler's timeline THIS WEEK — match these structures):\n{_fmt_pats}\n"
        banger_prompt = f"""Tyler drafted this tweet concept. Make it score 9+ on every X algorithm metric.

Draft: "{tweet_text}"

Tyler's draft is a CONCEPT — his take, his angle, his topic. Your job is to turn that concept into a polished, high-performing tweet. Keep his point of view and personality but IMPROVE the hook, tighten the structure, strengthen the closer, and weave in real stats from LIVE STATS below.

EXAMPLE WITH STATS:
- Tyler's draft: "Nuggets are on a bit of a heater right now. Warriors aren't a great team but that game last night was a blast. 6 game winning streak and they are starting to figure some things out..."
- Stats available: Denver Nuggets 48-28, Golden State Warriors 36-39
- GOOD output: "48-28. 6 straight wins. Nuggets just beat a Warriors team fighting for their playoff lives and it wasn't even close. This team is on a heater and they're starting to figure some things out..."
- Why it works: Stronger hook (opens with the record), Tyler's personality is still there ("on a heater", "figure some things out"), stats add credibility, tighter structure.

EXAMPLE WITHOUT STATS:
- Tyler's draft: "Bo Nix is getting better every single week. The arm talent was always there but something changed mentally this offseason"
- No stats available
- GOOD output: "Bo Nix is getting better every single week. The arm talent was always there. Something changed mentally this offseason and the rest of the AFC West is going to find out..."
- Why it works: Kept Tyler's observation, sharpened the closer into something that creates intrigue and drives replies, added competitive context that invites debate.
- GOOD output (alternate): "The arm talent was never the question with Bo Nix. Something changed mentally this offseason. He's getting better every single week and it's starting to show..."
- Why it works: Reordered for a stronger hook (the contrarian "never the question" opener stops the scroll), same observations, ellipsis closer.

TOO SAFE (don't do this): "Bo Nix is getting better every single week. The arm talent was always there. But something changed mentally this offseason..." — This is just Tyler's draft with a period and "But" added. Not an improvement.
TOO FAR (don't do this): "Denver dominated Golden State 116-93. Is this team finally clicking at the right time?" — This replaced Tyler's voice with a generic recap.
{_live_stats_block}
{format_mod}
{patterns_ctx}{_sports_ctx}{_fmt_inject}

STAT INTEGRITY RULE (ZERO TOLERANCE — overrides voice rules):
- ONLY use stats that appear in LIVE STATS above or in Tyler's draft. Do not invent, estimate, or round any numbers.
- If LIVE STATS provide a team record (e.g. 48-28), use it. If they don't provide player averages, PFF grades, or rankings — you CANNOT use those.
- A tweet with a concrete observation is ALWAYS better than a tweet with a fabricated stat.
- If a voice rule asks for a "specific number" and no real one is available, use a named event, a team record, or a concrete observation instead. Never invent a number to fill the slot.
{"- CRITICAL VOICE: The 'symptom' does NOT have to be a number. 'The Broncos offensive line is the reason Bo Nix ran for his life in December' is a valid symptom. 'Bottom-10 in pass protection' is NOT valid unless that ranking appears in LIVE STATS." if voice == "Critical" else ""}{"- SARCASTIC VOICE: Do NOT fabricate stats. Sarcastic voice builds humor from observations and framing, not invented numbers." if voice == "Sarcastic" else ""}{"- HOMER VOICE: Do NOT invent player stat lines. Use team records if available. If no player stats exist, describe what you see without citing specific figures." if voice == "Homer" else ""}

Rules:
- Reading Level (7th-9th grade)
- No Hashtags, Links, Tags, Emojis
- Hook & Pattern Breakers (first line stops the scroll)
- Structure each option to match the FORMAT PATTERNS above
{_char_rule}

{"THREAD FORMAT: Inside each option, separate individual tweets with the marker ---TWEET--- between them. Example: first tweet text here---TWEET---second tweet text here---TWEET---third tweet text here" if fmt == "Thread" else ""}

VOICE-SPECIFIC ENDING OVERRIDE:
{"CRITICAL VOICE PICK RULE: ALWAYS prefer the option ending with a period over one ending with a question mark. A question ending in Critical voice is a structural failure regardless of engagement potential. Period ending wins every time. This overrides all other pick criteria." if voice == "Critical" else ""}
{"HOMER ENDING RULE: BOTH options MUST end with a period. No question closers. No ellipsis. If a pattern calls for a question closer, replace it with a declarative outside-reaction statement. WRONG: 'How does the most dominant player not drag this roster over the line?' RIGHT: 'Every team in the West designed their rotations around stopping him. That is not a problem you scheme for unless the threat is real.'" if voice == "Homer" else ""}

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
            _grades_system = "You are grading tweets for Tyler Polumbus — former NFL lineman (8 seasons, Super Bowl 50 champion), Denver sports media host. Tyler's voice: direct, no fluff, punchy sentences, former-player authority, never hedges."
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
                gdata = {
                    "algorithm_score": _da.get("algorithm_score", 0),
                    "tyler_score": _da.get("tyler_score", 0),
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
- Tyler's voice: direct, no hedging, former-player authority
- Specific players/schemes/numbers only
- Include [IMAGE] markers for visuals
- End with debate invitation"""
        build_article_prompt = f"""Tyler Polumbus has a concept he wants turned into {'a short sarcastic column' if _is_sarcastic else 'a full X Article'}.

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
        _voice_task = f"matching the {voice} voice described in the system prompt" if voice != "Default" else "matching Tyler's voice exactly"
        # Parse structured brief if delimiters present
        _brief_delimiters = ["TOPIC:", "TENSION:", "KEY STATS:", "ANGLE:"]
        _has_brief = any(d in tweet_text for d in _brief_delimiters)
        if _has_brief:
            _brief_block = f"STRUCTURED BRIEF:\n{tweet_text}"
        else:
            _brief_block = f"CONCEPT/ANGLE:\n\"{tweet_text}\""
        _build_opening = "Tyler provided this structured brief as source material. Extract the strongest take and write from scratch — 3 distinct variations." if _has_brief else "Tyler Polumbus has a tweet concept/angle he wants turned into a finished tweet. Materialize this concept into the actual tweet — 3 distinct variations."
        build_prompt = f"""{_build_opening}

{_brief_block}

{format_mod}{_sports_ctx_b}{_fmt_inject_b}{_live_stats_block}

STAT INTEGRITY RULE:
- If LIVE STATS are provided above, use ONLY those numbers. Do not invent or adjust them.
- If NO stats are provided, do not fabricate specific numbers. A tweet without stats is better than one with wrong stats.

TASK: Write 3 distinct, finished tweets from this concept. Each should take a different angle or structure while {_voice_task}. NOT rewrites of each other — each a unique execution of the idea.

Rules:
- Strong hook — first line stops the scroll
- No hashtags, no emojis
- 7th-9th grade reading level
- End with something that makes people reply or argue
- Algorithm optimized: strong opinion, relatable, invites engagement
- Structure each option to match the FORMAT PATTERNS above

{"HOMER ENDING RULE: BOTH options MUST end with a period. No question closers. No ellipsis. Replace question closers with declarative outside-reaction statements." if voice == "Homer" else ""}{"CRITICAL ENDING RULE: BOTH options MUST end with a period. No question marks. Critical voice closes the door." if voice == "Critical" else ""}

Return ONLY this JSON, no other text:
{{
  "option1": "full tweet text here",
  "option1_pattern": "angle/structure this version takes",
  "option2": "full tweet text here",
  "option2_pattern": "angle/structure this version takes",
  "option3": "full tweet text here",
  "option3_pattern": "angle/structure this version takes",
  "pick": "1, 2, or 3 — just the number, no explanation"
}}"""
        _max_tok_b = 2000 if fmt == "Thread" else 700
        raw = call_claude(build_prompt, system=get_system_for_voice(voice, voice_mod), max_tokens=_max_tok_b)
        build_data = _parse_banger_json(raw)
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
- Tyler's voice: direct, no hedging, former-player authority
- Do NOT copy original phrasing — completely new execution
- Specific players/schemes/numbers only
- Include [IMAGE] markers for visuals"""
        rewrite_article_prompt = f"""Someone else wrote this content. Repurpose the underlying idea as {'a short sarcastic column' if _is_sarcastic else 'a full X Article'} in Tyler Polumbus's voice. Do NOT copy any original phrasing or structure — Tyler's version should be completely his own take on the same subject.

Source content (NOT Tyler's): "{tweet_text}"
{_live_stats_block}

FORMAT: {'SARCASTIC COLUMN' if _is_sarcastic else 'X ARTICLE'} ({_article_length})
{_article_structure}

{article_voice_mod}

Return the article as plain text. Do NOT wrap in JSON or code blocks."""
        _max_tok = 1200 if _is_sarcastic else 3000
        raw = call_claude(rewrite_article_prompt, system=get_system_for_voice(voice, voice_mod), max_tokens=_max_tok)
        result = _sanitize_output(raw.strip()) if raw else raw

    elif action == "rewrite" and tweet_text.strip():
        _rw_voice = f"in the {voice} voice described in the system prompt" if voice != "Default" else "in Tyler's voice"
        repurpose_prompt = f"""You are helping Tyler repurpose someone else's tweet into his own original content. The goal: take the UNDERLYING IDEA and write it as if Tyler came up with it himself. Nobody should be able to trace it back to the original.

Source tweet (NOT Tyler's — do NOT copy ANY phrasing, structure, or sentence patterns): "{tweet_text}"

REPURPOSING RULES:
- Extract the core IDEA or TAKE — then throw away everything else about the original tweet.
- Write {_rw_voice} with completely different wording, structure, and angle of attack.
- Tyler's version should feel like his own original thought — NOT a paraphrase.
- Change the entry point: if the original leads with a stat, Tyler leads with an observation (or vice versa).
- If the original names a player/team, Tyler can reference the same subject but frame it from his former-player perspective.
- Zero overlap in phrasing. If someone put them side by side, they should look like two people independently had the same thought.

{format_mod}{_live_stats_block}

- Strong hook in the first line
- Invites engagement/replies
- No hashtags, no emojis, no character count
- 7th-9th grade reading level

{"HOMER ENDING RULE: BOTH options MUST end with a period. No question closers. No ellipsis. Replace question closers with declarative outside-reaction statements." if voice == "Homer" else ""}{"CRITICAL ENDING RULE: BOTH options MUST end with a period. No question marks. Critical voice closes the door." if voice == "Critical" else ""}

Return ONLY this JSON, no other text:
{{
  "option1": "full tweet text — Tyler's completely original version",
  "option1_pattern": "angle Tyler takes on this idea",
  "option2": "full tweet text — different Tyler angle, also fully original",
  "option2_pattern": "angle Tyler takes on this idea",
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
        tyler_score = gd.get("tyler_score", 0)
        grades = gd.get("grades", [])
        combined_score = round((algo_score + tyler_score) / 2) if algo_score or tyler_score else 0

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
            <div style="font-family:'Bebas Neue',sans-serif;font-size:32px;color:#C49E3C;line-height:1;">{tyler_score}</div>
            <div style="height:5px;background:rgba(196,158,60,0.1);border-radius:3px;margin:8px 0 6px;">
              <div style="width:{tyler_score}%;height:100%;background:#C49E3C;border-radius:3px;"></div>
            </div>
            <div style="font-size:8px;text-transform:uppercase;letter-spacing:0.1em;color:rgba(255,255,255,0.35);font-weight:600;">Tyler Voice</div>
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
        _resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
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

    # Layer 2: Twitter searches
    _search_queries = [
        "Denver Broncos OR Denver Nuggets OR Avalanche -filter:retweets",
        "March Madness OR NCAA Tournament OR NBA OR NFL Draft -filter:retweets",
    ]

    # Layer 3: RSS feeds
    _rss_feeds = [
        "https://www.espn.com/espn/rss/news",
        "https://www.espn.com/espn/rss/nfl/news",
        "https://www.espn.com/espn/rss/nba/news",
        "https://news.google.com/rss/search?q=sports+news+today&hl=en-US&gl=US&ceid=US:en",
        "https://news.google.com/rss/search?q=march+madness+NCAA+2026&hl=en-US&gl=US&ceid=US:en",
    ]

    # Run ALL fetches in parallel (Twitter lists + searches + RSS + ESPN API + Sleeper API)
    _list_tweets, _search_tweets, _rss_headlines = [], [], []
    _espn_headlines, _sleeper_lines = [], []
    with _cf.ThreadPoolExecutor(max_workers=14) as _ex:
        _list_futs = [_ex.submit(_fetch_list, lid) for lid in _all_list_ids]
        _search_futs = [_ex.submit(fetch_tweets, q, 15) for q in _search_queries]
        _rss_futs = [_ex.submit(_fetch_rss_headlines, u, 12) for u in _rss_feeds]
        # ESPN + Sleeper APIs (fast, no auth, more reliable than RSS scraping)
        _espn_fut = _ex.submit(get_espn_headlines_for_inspo)
        _sleeper_fut = _ex.submit(get_sleeper_trending_for_inspo)
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
        try: _espn_headlines = _espn_fut.result()
        except Exception: pass
        try: _sleeper_lines = _sleeper_fut.result()
        except Exception: pass

    # Merge ESPN + Sleeper headlines into RSS block (they're higher quality)
    _rss_headlines = _espn_headlines + _sleeper_lines + _rss_headlines

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
def _load_inspo_from_gist() -> tuple:
    """Load cached inspiration ideas from gist — instant, survives session resets."""
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
def _run_inspiration_claude():
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

FORMAT PATTERNS (from highest-engagement tweets on Tyler's timeline RIGHT NOW — every hook MUST follow these patterns):
{_fmt_patterns}

Use these patterns to structure every hook. Match the opener style, line break placement, length, and ending style that's working THIS WEEK."""

    _prompt = f"""Tyler Polumbus needs 14 tweet ideas from what's happening RIGHT NOW.

FEED (last 24h):
{_tweet_block}

HEADLINES:
{_rss_block}{_fmt_block}

For each idea automatically select the most appropriate voice:
- DEFAULT: Stats, observations, analytical reads, pure film room perspective
- CRITICAL: Failures, bad decisions, accountability moments, underperformance
- HOMER: Positive signals being overlooked, team momentum, good news the casual fan is missing
- SARCASTIC: Ridiculous narratives, obvious takes presented as revelations, absurd situations, moments so good they deserve an unexpected cultural reference

Rules:
- hook = complete ORIGINAL Normal Tweet draft written in Tyler's voice — NEVER copy or paraphrase feed tweet text directly. Use the feed as inspiration for the topic only. Write a fresh original hook as if Tyler is reacting to or analyzing the situation.
- If the feed item is a retweet or starts with RT — ignore it completely and use a different feed item.
- why = under 10 words, Tyler's unique angle as a former player and Denver media host.

Return ONLY a JSON array of exactly 14 objects:
[{{"topic":"2-4 words","source":"twitter/espn/news","voice":"Default/Critical/Homer/Sarcastic","hook":"full tweet draft in the selected voice","why":"short angle under 10 words"}}]"""

    _system = f"""You are Tyler Polumbus's content strategist.
Tyler is a former NFL OL, Super Bowl 50 champion, Denver sports media host (@tyler_polumbus).

{_WHATS_HOT_VOICE_GUIDE}

Return only the JSON array, no other text."""
    try:
        _raw = _call_claude_direct(_prompt, _system, max_tokens=1800)
    except Exception:
        _raw = call_claude(_prompt, _system, max_tokens=1800)

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
            if "voice" not in _idea or _idea["voice"] not in ("Default", "Critical", "Homer", "Sarcastic"):
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


@st.dialog("What's Hot Right Now", width="large")
def _ci_inspiration_dialog():
    """Show cached ideas — only calls Claude once per open, not on every button click."""

    # Load ideas: session state > gist cache > Claude (slowest, last resort)
    if "inspo_ideas" not in st.session_state:
        # Try gist first — instant load if fresh ideas exist
        _gist_ideas, _gist_nt, _gist_nh = _load_inspo_from_gist()
        if _gist_ideas:
            st.session_state["inspo_ideas"] = _gist_ideas
            st.session_state["inspo_meta"] = (_gist_nt, _gist_nh)
            st.session_state["inspo_page"] = 0
        else:
            # No gist cache — generate fresh (slow, but only happens once)
            with st.spinner("Mount Polumbus AI is reaching the summit..."):
                _all_ideas, _n_tweets, _n_heads = _run_inspiration_claude()
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

    # If cached ideas are from old 7-idea prompt, clear and regenerate with 14
    if len(_all_ideas) <= _per_page and _page > 0:
        _run_inspiration_claude.clear()
        st.session_state.pop("inspo_ideas", None)
        st.session_state["inspo_page"] = 0
        with st.spinner("Generating fresh ideas..."):
            _fresh, _nt2, _nh2 = _run_inspiration_claude()
        if _fresh:
            st.session_state["inspo_ideas"] = _fresh
            st.session_state["inspo_meta"] = (_nt2, _nh2)
            _all_ideas = _fresh
            _n_tweets, _n_heads = _nt2, _nh2
        _page = 0

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
        "Homer":     ("rgba(45,212,191,0.1)",  "rgba(45,212,191,0.65)",  "rgba(45,212,191,0.2)"),
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
                    if _idea_voice in ("Default", "Critical", "Homer", "Sarcastic"):
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
    _rb1, _rb2 = st.columns(2)
    def _inspo_next_page():
        st.session_state["inspo_page"] = st.session_state.get("inspo_page", 0) + 1
        st.session_state["_ci_show_inspiration"] = True  # re-open dialog after full app rerun
    with _rb1:
        st.button("New Ideas", use_container_width=True, key="inspo_regen", on_click=_inspo_next_page)
    with _rb2:
        if st.button("Refresh Feed", use_container_width=True, key="inspo_clear_cache"):
            _fetch_inspiration_feed.clear()
            _run_inspiration_claude.clear()
            st.session_state.pop("inspo_ideas", None)
            st.session_state.pop("inspo_meta", None)
            st.session_state.pop("inspo_page", None)
            st.session_state["_ci_show_inspiration"] = True
            st.rerun(scope="app")


@st.dialog("Creator Studio", width="large")
def _ci_output_panel(_nonce, action, tweet_text, fmt, voice):
    """_nonce forces Streamlit to create a fresh dialog every call.
    Without it, @st.dialog caches by arguments and may serve stale results."""
    _ci_output_panel_impl(action, tweet_text, fmt, voice)


def page_compose_ideas():
    st.markdown('<div class="main-header">CREATOR <span>STUDIO</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Draft, refine, and ship your best content.</div>', unsafe_allow_html=True)

    # Consume staging key FIRST — before any widget is registered
    # Both "Use This" buttons and the URL ?idea= param funnel through here
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
        with st.spinner("Mount Polumbus AI is reaching the summit..."):
            _run_ci_ai("rewrite", seed, _fmt, _vc)
        _ci_output_panel(str(time.time()), "rewrite", seed, _fmt, _vc)
        return

    # Redo pending from modal "↺ Redo" button
    _pending_redo = st.session_state.pop("ci_dialog_pending", None)

    # ── 2-COLUMN LAYOUT ──
    col_left, col_right = st.columns([1, 2.5])

    # ═══════════════════════════════════════════════════════════════════
    # LEFT — Format Guide + Quick Links
    # ═══════════════════════════════════════════════════════════════════
    with col_left:
        _fmt_display = st.session_state.get("ci_format", "Normal Tweet")
        _fg = _FORMAT_GUIDES.get(_fmt_display, _FORMAT_GUIDES["Normal Tweet"])
        st.markdown('<div class="cs-panel-label">FORMAT GUIDE</div>', unsafe_allow_html=True)
        st.markdown(
            f'''<div style="font-size:13px;color:#2DD4BF;font-weight:700;margin-bottom:4px;">{_fg["icon"]} {_fmt_display.upper()}''' +
            f''' &nbsp;<span style="font-size:11px;color:#666888;font-weight:400;">{_fg["chars"]}</span></div>''',
            unsafe_allow_html=True)
        with st.expander("📋 Format Tips", expanded=False):
            _rules_html = "".join([f'<div class="fg-rule">{r}</div>' for r in _fg["rules"]])
            st.markdown(f'<div class="format-guide" style="border-top:none;margin:0;">{_rules_html}</div>', unsafe_allow_html=True)


    # ═══════════════════════════════════════════════════════════════════
    # RIGHT — Parameter Suite
    # ═══════════════════════════════════════════════════════════════════
    with col_right:
        st.markdown('<div class="cs-panel-label">PARAMETER SUITE</div>', unsafe_allow_html=True)

        tweet_text = st.text_area("Your concept", height=220, key="ci_text",
            placeholder="Drop the raw concept, angle, or draft here...")
        char_len = len(tweet_text)
        _cc = "#E8441A" if char_len >= 280 else "#C49E3C" if char_len >= 250 else "#3a5070"
        st.markdown(f'<div style="text-align:right;font-size:11px;color:{_cc};margin-top:-8px;margin-bottom:8px;">{char_len}/280</div>', unsafe_allow_html=True)

        fc1, fc2 = st.columns(2)
        with fc1:
            fmt = st.selectbox("Format", ["Punchy Tweet", "Normal Tweet", "Long Tweet", "Thread", "Article"], key="ci_format")
        with fc2:
            _custom_voices = load_json("voice_styles.json", [])
            _voice_opts = ["Default", "Critical", "Homer", "Sarcastic"] + [s["name"] for s in _custom_voices]
            voice = st.selectbox("Voice", _voice_opts, key="ci_voice",
                help="Default = natural | Critical = tough love | Homer = ultra positive | Sarcastic = dry wit")

        st.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)

        # Row 1: primary CTA
        def _click_banger():
            if st.session_state.get("ci_text", "").strip():
                st.session_state["_ci_pending"] = ("banger", st.session_state.get("ci_text", ""), st.session_state.get("ci_format", "Normal Tweet"), st.session_state.get("ci_voice", "Default"))
        st.button("⚡ Go Viral", key="ci_banger", use_container_width=True, type="primary", on_click=_click_banger)

        # Row 2: Build + Repurpose
        sr2, sr3 = st.columns(2)
        with sr2:
            def _click_build():
                if st.session_state.get("ci_text", "").strip():
                    st.session_state["_ci_pending"] = ("build", st.session_state.get("ci_text", ""), st.session_state.get("ci_format", "Normal Tweet"), st.session_state.get("ci_voice", "Default"))
            st.button("⊞ Build", key="ci_build", use_container_width=True, on_click=_click_build)
        with sr3:
            def _click_repurpose():
                if st.session_state.get("ci_text", "").strip():
                    st.session_state["_ci_pending"] = ("rewrite", st.session_state.get("ci_text", ""), st.session_state.get("ci_format", "Normal Tweet"), st.session_state.get("ci_voice", "Default"))
            st.button("↩ Repurpose", key="ci_repurpose", use_container_width=True, on_click=_click_repurpose)

        # Row 3: Grades
        def _click_engage():
            if st.session_state.get("ci_text", "").strip():
                st.session_state["_ci_pending"] = ("grades", st.session_state.get("ci_text", ""), st.session_state.get("ci_format", "Normal Tweet"), st.session_state.get("ci_voice", "Default"))
        st.button("≋ Grades", key="ci_engage", use_container_width=True, on_click=_click_engage)

        st.markdown('<div style="height:6px;"></div>', unsafe_allow_html=True)
        if st.button("What's Hot", key="ci_inspiration", use_container_width=True):
            st.session_state["_ci_show_inspiration"] = True

        st.divider()
        sc_col, sb_col, sp_col = st.columns([2.5, 1, 1])
        with sc_col:
            sc_cat = st.selectbox("Save to", ["Uncategorized", "Evergreen", "Timely", "Thread Ideas", "Video Ideas"],
                key="ci_cat", label_visibility="collapsed")
        with sb_col:
            if st.button("↓ Save Post", key="ci_save", use_container_width=True):
                if tweet_text.strip():
                    ideas = load_json("saved_ideas.json", [])
                    ideas.append({"text": tweet_text, "format": fmt, "category": sc_cat, "saved_at": datetime.now().isoformat()})
                    save_json("saved_ideas.json", ideas)
                    st.success("Saved.")
        with sp_col:
            if st.button("𝕏 Post", key="ci_post_direct", use_container_width=True, type="primary"):
                if tweet_text.strip():
                    with st.spinner("Posting..."):
                        _ok, _err = _post_tweet(tweet_text.strip())
                    if _ok:
                        st.success("Posted to X!")
                    else:
                        st.error(f"Post failed — {_err}")

    # ── Modal triggers — driven by one-shot session state, never by button return values ──
    def _clear_banger():
        for _k in ["ci_banger_data"] + [f"ci_banger_opt_{i}" for i in [1, 2, 3]]:
            st.session_state.pop(_k, None)

    # _pending_redo comes from modal Redo button (already popped above)
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
            # Run AI BEFORE opening dialog — dialog is display-only
            with st.spinner("Mount Polumbus AI is reaching the summit..."):
                _run_ci_ai(_action, _txt, _fmt, _voice)
        _ci_output_panel(str(time.time()), _action, _txt, _fmt, _voice)

    if st.session_state.pop("_ci_show_inspiration", False):
        _ci_inspiration_dialog()

    # ── Bank ──
    with st.expander("Bank", expanded=False):

        _default_folders = ["Uncategorized", "Evergreen", "Timely", "Thread Ideas", "Video Ideas"]
        _all_folders = load_json("saved_ideas_folders.json", _default_folders)
        _folder_opts = ["Idea Bank Vault"] + _all_folders + ["All Ideas", "Rewrite Queue"]

        if "ci_folder" not in st.session_state:
            st.session_state["ci_folder"] = "Idea Bank Vault"
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
                    _vb1, _vb2 = st.columns(2)
                    with _vb1:
                        if st.button("Use This", key=f"ci_inspo_use_{ii}", use_container_width=True, type="primary"):
                            st.session_state["_ci_text_stage"] = item.get("text", orig_text)
                            st.rerun()
                    with _vb2:
                        if st.button("↩ Repurpose", key=f"ci_inspo_{ii}", use_container_width=True):
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
                    if st.button("Use This", key=f"bank_use_{i}", use_container_width=True):
                        st.session_state["_ci_text_stage"] = idea.get("text", "")
                        st.rerun()

# ═══════════════════════════════════════════════════════════════════════════
# PAGE: CONTENT COACH
# ═══════════════════════════════════════════════════════════════════════════
def page_content_coach():
    st.markdown('<div class="main-header">CONTENT <span>COACH</span></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="tool-desc">{AMPLIFIER_IMG} <strong style="color:#2DD4BF;">Amplifier</strong> is your AI social media expert. Knows your data, the algorithm, and how to grow.</div>', unsafe_allow_html=True)

    # --- Initialize session state ---
    if "coach_conversations" not in st.session_state:
        st.session_state.coach_conversations = load_json("coach_conversations.json", [])
    if "coach_current" not in st.session_state:
        st.session_state.coach_current = {"id": None, "messages": [], "title": "New Chat"}

    _coach_sports = ""
    try: _coach_sports = f"\n\nLIVE SPORTS CONTEXT (reference when relevant):\n{get_sports_context()}"
    except Exception: pass
    COACH_SYSTEM = get_voice_context() + f"""

You are Amplifier, Tyler's personal social media coach. You are an EXPERT on:
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
        history_str = "\n".join([f"{'Tyler' if m['role']=='user' else 'Amplifier'}: {m['content']}" for m in msgs])
        reply = call_claude(f"Conversation so far:\n{history_str}\n\nRespond as Amplifier.", system=sys_prompt, max_tokens=1200)
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
        coach_fmt = st.selectbox("Format", ["General Advice", "Normal Tweet", "Long Tweet", "Thread", "Article"], key="coach_fmt", label_visibility="collapsed", help="General Advice = strategy tips. Tweet Ideas = ready-to-post content. Thread = multi-part breakdown.")
        st.markdown("---")
        st.markdown("##### Send to Creator Studio")
        save_text = st.text_area("Save to Creator Studio:", height=100, key="coach_save_text", placeholder="Paste Amplifier advice here...")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("↓ Save Post", use_container_width=True, key="coach_save_idea") and save_text.strip():
                ideas = load_json("saved_ideas.json", [])
                ideas.append({"id": str(uuid.uuid4()), "text": save_text.strip(), "category": "From Amplifier", "created_at": datetime.now().isoformat()})
                save_json("saved_ideas.json", ideas)
                st.success("Saved!")
        with c2:
            if st.button("↩ Remix", use_container_width=True, key="coach_repurpose") and save_text.strip():
                with st.spinner("Repurposing..."):
                    repurposed = call_claude(f"Rewrite this into a compelling tweet for Tyler Polumbus:\n\n{save_text.strip()}", max_tokens=600)
                    st.session_state.coach_save_text_result = repurposed
        if "coach_save_text_result" in st.session_state:
            st.markdown(f"**Repurposed:**\n\n{st.session_state.coach_save_text_result}")

    with col_center:
        include_history = st.toggle("Include Post History", value=not bool(st.session_state.coach_current["messages"]), key="coach_hist_toggle", help="Feed recent tweet history to the advisor for personalized advice")

        # Demo questions dropdown
        if not st.session_state.coach_current["messages"]:
            demo_pick = st.selectbox("Demo questions:", ["-- Pick a question --"] + DEMO_QUESTIONS, key="coach_demo")
            if demo_pick != "-- Pick a question --":
                with st.spinner("Mount Polumbus AI is reaching the summit..."):
                    _send_message(demo_pick, include_history, coach_fmt)
                st.rerun()

        # Chat display
        for msg in st.session_state.coach_current.get("messages", []):
            if msg["role"] == "user":
                role_label = "Tyler"
                cls = "chat-user"
            else:
                role_label = f'{AMPLIFIER_IMG} <span style="color:#2DD4BF;">Amplifier</span>'
                cls = "chat-ai"
            st.markdown(f'<div class="chat-msg {cls}"><div class="chat-role">{role_label}</div><div style="color:#d8d8e8;font-size:16px;line-height:1.8;white-space:pre-wrap;">{msg["content"]}</div></div>', unsafe_allow_html=True)

        # Input
        user_input = st.text_area("Ask Amplifier:", height=80, key="coach_input", placeholder="What should I write about today?")
        if st.button("↗ Send", use_container_width=True, key="coach_send") and user_input.strip():
            with st.spinner("Amplifier is thinking..."):
                _send_message(user_input.strip(), include_history, coach_fmt)
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: ARTICLE WRITER
# ═══════════════════════════════════════════════════════════════════════════
@st.dialog("New Article", width="large")
def _aw_create_new_dialog():
    """Popup for writing a new article from scratch."""
    _custom_voices = load_json("voice_styles.json", [])
    _voice_opts = ["Default", "Critical", "Homer", "Sarcastic"] + [s["name"] for s in _custom_voices]
    voice_pick = st.selectbox("Voice", _voice_opts, key="aw_dialog_voice",
        help="Default = natural | Critical = tough love | Homer = ultra positive | Sarcastic = short column, implied story")
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
                    _structure = "" if _is_sarcastic else "\nSTRUCTURE:\n- HEADLINE: 50-75 chars, include a number or specific claim\n- INTRO (2-3 paragraphs): Provocative claim, why it matters now.\n- 4 SECTIONS with subheadings: 2-3 short paragraphs, **bold key stats**\n- WHAT COMES NEXT: Bold prediction\n- CONCLUSION: 1-sentence hot take + debate question\n- PROMOTION: companion tweet idea\n\nRULES: Tyler's voice — direct, no hedging, former-player authority. Specific players/schemes/numbers only."
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
            border = "border-left:3px solid #2DD4BF;" if selected else ""
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
                border = "border-left:3px solid #2DD4BF;" if selected else ""
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
        ac1, ac2, ac3 = st.columns(3)
        with ac3:
            if pplx_available() and st.button("Research", use_container_width=True, key="aw_research_btn"):
                if seed_text:
                    with st.spinner("Researching with Perplexity..."):
                        _research = pplx_research(seed_text)
                        if _research.get("answer"):
                            st.session_state["aw_research_data"] = _research
                        else:
                            st.warning("Research failed — check API key.")
        if st.session_state.get("aw_research_data"):
            _rr = st.session_state["aw_research_data"]
            st.markdown(f'<div style="background:#0d1829;border:1px solid #1e3a5f;border-left:3px solid #00E5CC;border-radius:8px;padding:14px;margin:8px 0;font-size:12px;color:#b8c8d8;line-height:1.7;"><div style="font-size:10px;color:#00E5CC;font-weight:700;letter-spacing:1px;margin-bottom:6px;">PERPLEXITY RESEARCH</div>{_rr["answer"]}</div>', unsafe_allow_html=True)
            if _rr.get("citations"):
                st.markdown(f'<div style="font-size:10px;color:#3a5070;margin-bottom:8px;">Sources: {", ".join(str(c) for c in _rr["citations"][:5])}</div>', unsafe_allow_html=True)
        with ac1:
            if st.button("↺ Scratch", use_container_width=True, key="aw_scratch", type="primary"):
                if seed_text:
                    with st.spinner("Writing full article..."):
                        voice = get_voice_context()
                        pp = analyze_personal_patterns()
                        pp_note = ""
                        if pp:
                            pp_note = f"\nData: optimal char range {pp.get('optimal_char_range','N/A')}, {pp.get('top_question_pct',0)}% top tweets use questions, {pp.get('top_ellipsis_pct',0)}% use ellipsis."
                        _aw_sports = ""
                        try: _aw_sports = f"\n\nLIVE SPORTS CONTEXT:\n{get_sports_context()}"
                        except Exception: pass
                        _aw_research = ""
                        if st.session_state.get("aw_research_data", {}).get("answer"):
                            _aw_research = f"\n\nRESEARCH (use these verified facts):\n{st.session_state['aw_research_data']['answer'][:1500]}"
                        prompt = f"""Write a complete X Article based on this seed:\n\n\"{seed_text}\"\n\nFORMAT: X ARTICLE (1,500-2,000 words / 6-8 minute read){_aw_sports}{_aw_research}\n\nCONTEXT: X Articles grew 20x since Dec 2025 ($2.15M contest prizes). They keep users on-platform (no link penalty), generate 2+ min dwell time (+10 algorithm weight), and Premium subscribers get 2-4x reach boost. This is the highest priority content format.\n\nSTRUCTURE:\n- HEADLINE: 50-75 chars, include a number or specific claim, take a position. Numbers perform 2x better.\n- [IMAGE: Hero image placeholder — game photo, player photo, or custom graphic]\n- INTRO (2-3 paragraphs): Provocative claim or surprising stat, then why it matters right now.\n- SECTION 1 with subheading: 2-3 short paragraphs with **bold key stats** (2-3 per section). [IMAGE placeholder]\n- SECTION 2 with subheading: 2-3 short paragraphs, comparison list format if relevant.\n- SECTION 3 with subheading: Contrarian angle or insider perspective. [IMAGE placeholder]\n- SECTION 4 WHAT COMES NEXT: Bold prediction with reasoning.\n- CONCLUSION: **1-sentence bold hot take summary**, then discussion question to drive comments.\n- PROMOTION: Suggest a companion tweet pulling the most provocative stat from the article.\n\nRULES:\n- 1,500-2,000 words target (6-8 min read for optimal dwell time bonus)\n- Paragraphs: 2-4 sentences max\n- Subheadings every ~300 words\n- Bold key stats and claims (2-3 per section)\n- Tyler's voice: direct, no hedging, former-player authority\n- Every point must reference specific players/schemes/numbers\n- Include [IMAGE] markers where supporting visuals should go\n- End with debate invitation to drive replies{pp_note}"""
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
            bc1, bc2, bc3, bc4 = st.columns(4)
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
                if pplx_available() and st.button("Verify", use_container_width=True, key="aw_verify"):
                    with st.spinner("Fact-checking..."):
                        _fc = pplx_fact_check(edited)
                    if _fc.get("answer"):
                        st.session_state["_aw_page_verify"] = _fc
                    else:
                        st.warning("Couldn't verify — check API key.")
            with bc4:
                if st.button("↺ New", use_container_width=True, key="aw_new"):
                    _aw_create_new_dialog()
            _vr = st.session_state.get("_aw_page_verify")
            if _vr:
                _va = _vr["answer"]
                _vc = _vr.get("citations", [])
                _color = "#2DD4BF" if "accurate" in _va.lower() or "correct" in _va.lower() else "#FBBF24"
                st.markdown(f'<div style="background:#0d1829;border-left:3px solid {_color};padding:10px 14px;border-radius:6px;margin:8px 0;font-size:12px;color:#b8c8d8;line-height:1.6;">{_va}</div>', unsafe_allow_html=True)
                if _vc:
                    st.markdown(f'<div style="font-size:10px;color:#3a5070;margin-top:4px;">Sources: {", ".join(str(c) for c in _vc[:3])}</div>', unsafe_allow_html=True)

    # ── Right 1/3: My Articles ────────────────────────────────────────
    with col_saved:
        st.markdown("### My Articles")
        if st.button("↺ Create New", key="aw_side_new", use_container_width=True):
            _aw_create_new_dialog()
        articles = load_json("saved_articles.json", [])
        if not articles:
            st.markdown('<div style="padding:20px;border-radius:10px;background:#0d1929;border:1px solid rgba(0,229,204,0.13);color:#3a5070;text-align:center;font-style:italic;line-height:1.6;">No saved articles yet.<br>Select a tweet above, generate an article, then click Save Article.</div>', unsafe_allow_html=True)
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
        all_tweets = _fetch_window(f"from:{TYLER_HANDLE}")[:10]
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
        st.markdown(f'<div class="stat-card"><div style="font-size:13px;font-weight:700;color:#00E5CC;line-height:1.3;margin-bottom:4px;word-break:break-all;">@{TYLER_HANDLE}</div><div class="stat-label">Handle</div></div>', unsafe_allow_html=True)
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

    ideas = load_json("saved_ideas.json", [])
    if ideas:
        col_ideas, col_analyze = st.columns([1, 2])
        with col_ideas:
            st.markdown('<div style="font-size:9px;color:#3a5070;letter-spacing:2px;font-weight:700;margin-bottom:8px;">SAVED IDEAS</div>', unsafe_allow_html=True)
            for i, idea in enumerate(reversed(ideas[-15:])):
                if st.button(idea.get("text", "")[:60] + "...", key=f"aa_idea_{i}", use_container_width=True):
                    st.session_state["aa_text"] = idea.get("text", "")
    else:
        col_analyze = st.container()

    with col_analyze:
        st.markdown('<div style="background:#0d1929;border-left:3px solid #00E5CC;border-radius:8px;padding:14px 16px;font-size:12px;color:#5a8090;margin-bottom:16px;"><strong style="color:#00E5CC;">Example output:</strong> Score 72/100 — Strong hook, weak payoff. Opens with a bold claim but the final line doesn\'t land. Suggestion: End with a question to drive replies.</div>', unsafe_allow_html=True)
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


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: HEALTH CHECK
# ═══════════════════════════════════════════════════════════════════════════
def page_health_check():
    st.markdown('<div class="main-header">ACCOUNT <span>AUDIT</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Full audit of your X account — posting cadence, engagement rate, hook quality, content mix, and actionable fixes.</div>', unsafe_allow_html=True)

    # What it checks
    with st.expander("ℹ️ What this audits", expanded=False):
        st.markdown("""<div style="padding:4px 0;">
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
        try:
            _lr_dt = datetime.strptime(last_run[:10], "%Y-%m-%d")
            _days_ago = (datetime.now() - _lr_dt).days
            _ago_str = "today" if _days_ago == 0 else f"{_days_ago}d ago"
        except Exception:
            _ago_str = ""
        st.caption(f"Last run: {last_run}{' — ' + _ago_str if _ago_str else ''}")
    else:
        st.caption("Never run — click below to get your health score.")

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
    st.markdown('<div class="main-header">MY <span>STATS</span></div>', unsafe_allow_html=True)
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

        # Top 5 tweets
        _ts1, _ts2 = st.columns([3, 1])
        with _ts1:
            st.markdown("### Top Tweets")
        with _ts2:
            _sort_by = st.selectbox("Sort", ["Likes", "Views", "Replies", "RTs"], label_visibility="collapsed", key="stats_sort")
        _sort_map = {"Likes": "likeCount", "Views": "viewCount", "Replies": "replyCount", "RTs": "retweetCount"}
        top5 = sorted(tweets, key=lambda t: t.get(_sort_map[_sort_by], 0), reverse=True)[:5]
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
    st.markdown('<div class="main-header">PROFILE <span>ANALYZER</span></div>', unsafe_allow_html=True)
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
            st.markdown('<div style="color:#555577; text-align:center; padding:60px 20px; font-size:14px;">Enter a handle and click Research Account</div>', unsafe_allow_html=True)
        else:
            hdl = st.session_state.get("ar_handle", "")
            st.markdown(f"""<div style="font-size:11px; letter-spacing:2px; color:#2DD4BF; font-weight:700; margin-bottom:16px;">ACCOUNT ANALYSIS — @{hdl}</div>""", unsafe_allow_html=True)

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
    if "custom_lists" not in st.session_state:
        st.session_state.custom_lists = load_engagement_lists()
    # Restore any known list_ids that got wiped (migration safety net)
    for _k, _v in _ENGAGEMENT_DEFAULTS.items():
        if _k in st.session_state.custom_lists and isinstance(st.session_state.custom_lists[_k], dict):
            if not st.session_state.custom_lists[_k].get('list_id'):
                st.session_state.custom_lists[_k]['list_id'] = _v['list_id']

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

    # ── Top Controls: Engagement Targets + My Tweet Replies (merged) ──
    _rg_col_left, _rg_col_right = st.columns([3, 2])
    with _rg_col_left:
        st.markdown('<div style="font-size:10px;letter-spacing:2px;color:#2DD4BF;font-weight:700;opacity:0.7;margin-bottom:6px;">ENGAGEMENT TARGETS</div>', unsafe_allow_html=True)
        c1, c2, c3 = st.columns([3, 1.2, 0.9])
        with c1:
            list_source = st.selectbox("List", list(st.session_state.custom_lists.keys()),
                                       key="rg_source", label_visibility="collapsed")
        with c2:
            do_load = st.button("↓ Load Feed", key="rg_load_posts", use_container_width=True, type="primary")
        with c3:
            if st.button("+ New", key="rg_new_list_btn", use_container_width=True):
                st.session_state["rg_show_new_list"] = not st.session_state.get("rg_show_new_list", False)
    with _rg_col_right:
        st.markdown('<div style="font-size:10px;letter-spacing:2px;color:#2DD4BF;font-weight:700;opacity:0.7;margin-bottom:6px;">MY TWEET REPLIES</div>', unsafe_allow_html=True)
        c4, c5 = st.columns(2)
        with c4:
            load_all = st.button("↓ My Replies", key="rg_load_all", use_container_width=True)
        with c5:
            load_verified = st.button("↓ Verified Only", key="rg_load_verified", use_container_width=True, type="primary")

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
        else:
            st.caption("No List ID — click + New List to add one")
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

    if do_load:
        if not _list_id:
            st.error("No X List ID for this list. Use + New List to set one.")
        else:
            with st.spinner("Fetching posts..."):
                from datetime import timezone as _tz, timedelta as _td
                from dateutil import parser as _dtparser
                raw_tweets = fetch_tweets_from_list(_list_id, count=100)
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
            my_tweets = fetch_tweets(f"from:{TYLER_HANDLE}", count=15)
            filtered = [t for t in my_tweets if int(t.get("replyCount", t.get("reply_count", 0))) >= 2][:8]
            st.session_state["rg_my_tweets"] = filtered
            for idx, tw in enumerate(filtered):
                tw_id = tw.get("id", "")
                replies = fetch_tweets(f"conversation_id:{tw_id}", count=25)
                replies = [r for r in replies if r.get("author", {}).get("userName", "").lower() != TYLER_HANDLE.lower() and r.get("id", "") != tw_id]
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
            _prompt = (
                "Based on these tweets from sports journalists and analysts:\n\n"
                + "\n".join(f"- {l}" for l in _lines)
                + "\n\nGenerate 5 fresh, punchy tweet ideas for @tyler_polumbus — former NFL OL, Super Bowl 50 champion, Denver sports host. "
                "Each should react to something in the feed, sound like an NFL insider, be under 280 chars. "
                "Numbered list. No hashtags. No emojis."
            )
            with st.spinner("Reading the feed..."):
                st.session_state["rg_inspiration_ideas"] = call_claude(_prompt, system=TYLER_CONTEXT, max_tokens=1000)
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
                                st.session_state[f"{et_input_key}_p"] = opts[0]
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
            _viral_voice = st.selectbox("Voice", ["Default", "Critical", "Homer", "Sarcastic"],
                index=["Default", "Critical", "Homer", "Sarcastic"].index(_viral_voice),
                key="rg_viral_voice_sel", label_visibility="collapsed")
        with _vclose:
            if st.button("✕ Close", key="rg_viral_close", use_container_width=True):
                st.session_state.pop("rg_viral_idea", None)
                for _k in ["ci_banger_data", "ci_grades", "ci_result", "ci_repurposed", "ci_preview"]:
                    st.session_state.pop(_k, None)
                st.rerun()
        st.session_state["rg_viral_fmt"] = _viral_fmt
        st.session_state["rg_viral_voice"] = _viral_voice
        with st.spinner("Mount Polumbus AI is reaching the summit..."):
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

# ═══════════════════════════════════════════════════════════════════════════
# PAGE: INSPIRATION
# ═══════════════════════════════════════════════════════════════════════════
def page_inspiration():
    st.markdown('<div class="main-header">IDEA <span>BANK</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Save tweets that inspire you. Reference them when you need ideas.</div>', unsafe_allow_html=True)

    inspo = load_inspiration_gist()

    col_add, col_view = st.columns([1, 1])

    with col_add:
        st.markdown("### Save to Vault")
        inspo_text = st.text_area("Tweet text:", height=100, key="insp_text",
            placeholder="Paste the tweet that caught your eye...")
        inspo_author = st.text_input("Author:", placeholder="@username", key="insp_author")
        inspo_tags = st.text_input("Tags (comma-separated):", placeholder="hook, thread, broncos", key="insp_tags")
        inspo_likes = st.text_input("Likes (optional):", value="", placeholder="e.g. 1200", key="insp_likes")
        inspo_views = st.text_input("Views (optional):", value="", placeholder="e.g. 45000", key="insp_views")

        if st.button("↓ Bank It", use_container_width=True, key="insp_save", type="primary"):
            if inspo_text.strip():
                inspo.append({
                    "text": inspo_text,
                    "author": inspo_author,
                    "tags": [t.strip() for t in inspo_tags.split(",") if t.strip()],
                    "likes": int(inspo_likes) if str(inspo_likes).strip().isdigit() else 0,
                    "views": int(inspo_views) if str(inspo_views).strip().isdigit() else 0,
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
                import urllib.parse as _urlparse
                _ib_encoded = _urlparse.quote(item.get("text", ""), safe="")
                st.markdown(
                    f'<a href="/?page=Creator+Studio&idea={_ib_encoded}" target="_self" '
                    f'style="display:block;width:100%;padding:8px 12px;background:#1e3a5f;'
                    f'border:1px solid #2d5a8e;border-radius:4px;color:#7eb8f7;text-align:center;'
                    f'text-decoration:none;font-size:14px;font-weight:600;margin-top:4px;">'
                    f'→ Use in Creator Studio</a>',
                    unsafe_allow_html=True
                )


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: R&D COUNCIL DASHBOARD
# ═══════════════════════════════════════════════════════════════════════════

_RD_AGENTS = [
    {"id": "cadence", "name": "Cadence", "role": "Strategy & Command", "color": "#2DD4BF"},
    {"id": "blitz", "name": "Blitz", "role": "Content & Twitter", "color": "#C49E3C"},
    {"id": "scout", "name": "Scout", "role": "Research & Intelligence", "color": "#6B8AAA"},
    {"id": "tempo", "name": "Tempo", "role": "Show Prep & Ops", "color": "#E8441A"},
    {"id": "booth", "name": "Booth", "role": "Podcast & YouTube", "color": "#9B59B6"},
    {"id": "redzone", "name": "Redzone", "role": "Breaking News", "color": "#E53E3E"},
    {"id": "snap", "name": "Snap", "role": "Email & Sponsors", "color": "#38A169"},
    {"id": "audible", "name": "Audible", "role": "Personal Clarity", "color": "#805AD5"},
    {"id": "gunner", "name": "Gunner", "role": "Daily Intelligence", "color": "#4299E1"},
]

def _load_council_sessions() -> list:
    try:
        _gid = st.secrets.get("GIST_ID", "15fb167bbbfdaa79d5ce11c266c3f652")
        _r = requests.get(f"https://api.github.com/gists/{_gid}", headers=_gist_headers(), timeout=10)
        _files = _r.json().get("files", {})
        if "rd_council_sessions.json" in _files:
            return json.loads(_files["rd_council_sessions.json"]["content"])
    except Exception:
        pass
    return []

def _save_council_sessions(sessions: list):
    try:
        _gid = st.secrets.get("GIST_ID", "15fb167bbbfdaa79d5ce11c266c3f652")
        _payload = json.dumps({"files": {"rd_council_sessions.json": {"content": json.dumps(sessions[:30], indent=2, default=str)}}})
        requests.patch(f"https://api.github.com/gists/{_gid}", data=_payload, headers=_gist_headers(), timeout=10)
    except Exception:
        pass

def _run_rd_council_hq(session_type: str) -> dict:
    """Run a full council session from the HQ app using Claude OAuth."""
    from datetime import datetime as _dt_c
    import uuid as _uuid_c
    _today = date.today()
    _day_num = _today.timetuple().tm_yday
    _sidx = 0 if session_type == "morning" else 1
    _pidx = (_day_num * 2 + _sidx) % len(_RD_AGENTS)
    _proposer = _RD_AGENTS[_pidx]
    _responders = [a for a in _RD_AGENTS if a["id"] != _proposer["id"]]

    _sports_live = ""
    try: _sports_live = f"\n\nLIVE SPORTS CONTEXT:\n{get_sports_context()}"
    except Exception: pass
    _ctx = (
        "Tyler Polumbus - Former NFL OL, Super Bowl 50 champion (Denver Broncos). "
        "Host of The PhD Show on Altitude 92.5 (noon-3 PM MST). 42K+ Twitter followers. "
        "YouTube channel. Goals: grow to 100K Twitter, build YouTube, land more sponsorships."
        f"{_sports_live}"
    )

    _agent_personas = {
        "cadence": "You are Cadence, Tyler's head coach agent. See the whole field. Think strategically, make decisive calls. Direct, no filler.",
        "blitz": "You are Blitz, Tyler's content and Twitter agent. You know what goes viral in sports media. Focus on content ROI and social growth.",
        "scout": "You are Scout, Tyler's research agent. Track what's winning on YouTube and Twitter in sports media. Surface data-driven gaps.",
        "tempo": "You are Tempo, agent for The PhD Show on Altitude 92.5. Know Tyler's workflow and how to turn content into radio moments.",
        "booth": "You are Booth, Tyler's podcast and YouTube agent. Understand clip strategy, thumbnails, and growing a sports YouTube channel.",
        "redzone": "You are Redzone, Tyler's real-time sports intelligence. Track what's trending RIGHT NOW and which stories have legs.",
        "snap": "You are Snap, Tyler's email and communications agent. Think about monetization through partnerships and sponsorships.",
        "audible": "You are Audible, Tyler's personal clarity agent. Ask: is this sustainable? Is Tyler spreading too thin? Protect against burnout.",
        "gunner": "You are Gunner, Tyler's daily briefing agent. Know the news cycle and connect current events to content opportunities.",
    }

    # Step 1: Proposer generates idea
    _idea = call_claude(
        f"{_ctx}\n\nToday: {_today.strftime('%A, %B %d, %Y')}. {session_type.title()} session.\n\n"
        f"As {_proposer['name']} ({_proposer['role']}), propose ONE specific tactical idea for Tyler "
        f"to grow his business in the next 7 days. Not vague - a real move with a first step. 3-4 sentences.",
        system=_agent_personas.get(_proposer["id"], ""), max_tokens=250,
    )

    # Step 2: Each agent responds
    _debate_ctx = f"{_ctx}\n\n{_proposer['name']}'s proposed idea:\n{_idea}"
    _responses = []
    for _ag in _responders:
        _resp = call_claude(
            f"{_debate_ctx}\n\nAs {_ag['name']} ({_ag['role']}), your honest 2-3 sentence take. "
            f"Agree and build, push back, or flag a risk. Direct and specific.",
            system=_agent_personas.get(_ag["id"], ""), max_tokens=180,
        )
        _responses.append({"agent": _ag["name"], "role": _ag["role"], "id": _ag["id"], "response": _resp})

    # Step 3: Cadence synthesizes
    _all_text = "\n\n".join(f"{r['agent']} ({r['role']}):\n{r['response']}" for r in _responses)
    _memo = call_claude(
        f"{_ctx}\n\nProposed idea by {_proposer['name']}:\n{_idea}\n\nCouncil:\n{_all_text}\n\n"
        f"As Cadence, decisive memo:\nVERDICT: Move on this? Yes/No/Modified - one sentence why.\n"
        f"#1 ACTION TODAY: One specific thing Tyler does in 24 hours.\nWATCH: One risk.\n4-6 sentences total.",
        system=_agent_personas["cadence"], max_tokens=320,
    )

    return {
        "id": str(_uuid_c.uuid4()),
        "date": _today.strftime("%Y-%m-%d"),
        "time": _dt_c.now().strftime("%-I:%M %p"),
        "session": session_type,
        "proposer": {"id": _proposer["id"], "name": _proposer["name"], "role": _proposer["role"]},
        "idea": _idea,
        "responses": _responses,
        "memo": _memo,
    }

def _render_council_session(s: dict):
    """Display a single council session with agent cards and memo."""
    _session_lbl = s.get("session", "").upper() + " SESSION"
    _date_str = s.get("date", "")
    _time_str = s.get("time", "")
    _prop = s.get("proposer", {})
    _idea = s.get("idea", "")
    _responses = s.get("responses", [])
    _memo = s.get("memo", "")
    _pcol = next((a["color"] for a in _RD_AGENTS if a["id"] == _prop.get("id", "")), "#2DD4BF")

    # Header + proposed idea
    st.markdown(f"""
    <div style="background:#0d1829;border:1px solid #1e3a5f;border-radius:10px;padding:16px 20px;margin-bottom:16px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
        <div>
          <span style="font-size:11px;letter-spacing:2px;color:#3a5070;font-weight:700;">{_session_lbl}</span>
          <div style="font-size:13px;color:#8899aa;margin-top:2px;">{_date_str} &middot; {_time_str} MST</div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:11px;color:#3a5070;letter-spacing:1px;">PROPOSER</div>
          <div style="font-size:14px;font-weight:700;color:{_pcol};">{_prop.get('name','')}</div>
          <div style="font-size:11px;color:#556680;">{_prop.get('role','')}</div>
        </div>
      </div>
      <div style="font-size:11px;letter-spacing:2px;color:#3a5070;font-weight:700;margin-bottom:6px;">PROPOSED IDEA</div>
      <div style="color:#d8d8e8;font-size:14px;line-height:1.7;border-left:3px solid {_pcol};padding-left:12px;">{_idea}</div>
    </div>""", unsafe_allow_html=True)

    # Council debate - 3-column grid
    st.markdown('<div style="font-size:11px;letter-spacing:2px;color:#3a5070;font-weight:700;margin-bottom:10px;">COUNCIL DEBATE</div>', unsafe_allow_html=True)
    _cols = st.columns(3)
    for _i, _r in enumerate(_responses):
        _acol = next((a["color"] for a in _RD_AGENTS if a["id"] == _r.get("id", "") or a["name"] == _r.get("agent", "")), "#6B8AAA")
        with _cols[_i % 3]:
            st.markdown(f"""
            <div style="background:#0a1220;border:1px solid #1a2d45;border-top:3px solid {_acol};border-radius:8px;padding:12px;margin-bottom:10px;min-height:130px;">
              <div style="font-size:12px;font-weight:700;color:{_acol};margin-bottom:2px;">{_r.get('agent','')}</div>
              <div style="font-size:10px;color:#3a5070;margin-bottom:8px;">{_r.get('role','')}</div>
              <div style="font-size:12px;color:#b8c8d8;line-height:1.6;">{_r.get('response','')}</div>
            </div>""", unsafe_allow_html=True)

    # Cadence's call (memo)
    st.markdown(f"""
    <div style="background:#0a1a10;border:1px solid #1a4a2a;border-left:4px solid #2DD4BF;border-radius:8px;padding:16px 20px;margin-top:8px;">
      <div style="font-size:11px;letter-spacing:2px;color:#2DD4BF;font-weight:700;margin-bottom:8px;">CADENCE'S CALL</div>
      <div style="color:#d8f0d8;font-size:14px;line-height:1.7;white-space:pre-wrap;">{_memo}</div>
    </div>""", unsafe_allow_html=True)

def page_rd_council():
    st.markdown('<div class="main-header">R&D <span>COUNCIL</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">9-agent business advisory. Proposes, debates, and delivers a decisive memo twice daily (9 AM + 5 PM MST).</div>', unsafe_allow_html=True)

    _sessions = _load_council_sessions()

    # ── Action bar ──
    _c1, _c2, _c3 = st.columns([1, 1, 2])
    with _c1:
        _run_m = st.button("Run Morning Session", key="rdc_morning", use_container_width=True, type="primary")
    with _c2:
        _run_e = st.button("Run Evening Session", key="rdc_evening", use_container_width=True)
    with _c3:
        st.markdown(f'<div style="font-size:12px;color:#3a5070;padding-top:10px;">Auto-scheduled 9 AM + 5 PM MST &middot; {len(_RD_AGENTS)} agents &middot; {len(_sessions)} sessions logged</div>', unsafe_allow_html=True)

    if _run_m or _run_e:
        _stype = "morning" if _run_m else "evening"
        with st.spinner(f"Council in session... {len(_RD_AGENTS)} agents debating"):
            try:
                _new = _run_rd_council_hq(_stype)
                _sessions = [_new] + _sessions[:29]
                _save_council_sessions(_sessions)
                st.rerun()
            except Exception as _e:
                st.error(f"Session failed: {_e}")

    if not _sessions:
        st.markdown("""
        <div style="background:#0d1829;border:1px solid #1e3a5f;border-radius:10px;padding:40px;text-align:center;margin-top:20px;">
          <div style="font-size:32px;margin-bottom:12px;">&#9878;</div>
          <div style="font-size:16px;color:#8899aa;margin-bottom:6px;">No council sessions yet</div>
          <div style="font-size:13px;color:#3a5070;">Run the first one above or wait for the 9 AM auto-session.</div>
        </div>""", unsafe_allow_html=True)
        return

    st.markdown("---")

    # ── Latest session ──
    st.markdown('<div style="font-size:11px;letter-spacing:2px;color:#2DD4BF;font-weight:700;margin-bottom:12px;">LATEST SESSION</div>', unsafe_allow_html=True)
    _render_council_session(_sessions[0])

    # ── History ──
    if len(_sessions) > 1:
        st.markdown('<div style="font-size:11px;letter-spacing:2px;color:#3a5070;font-weight:700;margin:24px 0 10px;">PAST SESSIONS</div>', unsafe_allow_html=True)
        for _s in _sessions[1:]:
            _label = f"{_s.get('date','')} &middot; {_s.get('session','').upper()} &middot; Proposed by {_s.get('proposer',{}).get('name','')}"
            with st.expander(_label):
                _render_council_session(_s)


# ═══════════════════════════════════════════════════════════════════════════
# PAGE: SIGNALS & PROMPTS
# ═══════════════════════════════════════════════════════════════════════════

_BEAT_REPORTERS = 'from:mikeklis OR from:bylucaevans OR from:ZacStevensDNVR OR from:AllbrightNFL OR from:TroyRenck OR from:MaseDenver OR from:christomasson OR from:KyleNewmanDP OR from:CodyRoarkNFL OR from:NickOehlerTV OR from:JamieLynchTV OR from:markkiszla OR from:ParkerJGabriel OR from:HarrisonWind OR from:BennettDurando OR from:VBenedetto OR from:chrisadempsey OR from:katywinge OR from:VicLombardi OR from:TJMcBrideNBA OR from:msinger OR from:MooseColorado OR from:DNVR_Nuggets OR from:PeterRBaugh OR from:evanrawal OR from:cmasisak22 OR from:adater OR from:megangley OR from:Jack_Carlough OR from:BrianHowell33 OR from:adamcm777 OR from:SeanKeeler OR from:Danny_Penza OR from:buffzone'
_NATIONAL_QUERY = '(Broncos OR Nuggets OR Avalanche OR "CU Buffs" OR "Bo Nix" OR "Sean Payton" OR "Nikola Jokic" OR "Nathan MacKinnon" OR "Courtland Sutton" OR "Jamal Murray") (from:AdamSchefter OR from:RapSheet OR from:TomPelissero OR from:JayGlazer OR from:AlbertBreer OR from:JeremyFowler OR from:MikeGarafolo OR from:PSchrags OR from:jeffdarlington OR from:DanGrazianoESPN OR from:DMRussini OR from:FieldYates OR from:ProFootballTalk OR from:nflnetwork OR from:NFL OR from:CharlesRobinson OR from:MikeSilver OR from:SiriusXMNFL OR from:ShamsCharania OR from:BrianWindhorst OR from:ChrisBHaynes OR from:TheSteinLine OR from:JakeLFischer OR from:espn OR from:NBAonTNT) -is:retweet'
_SIGNALS_CACHE = {"beat": None, "national": None, "ts": 0, "beat_cursor": "", "nat_cursor": ""}


def _fetch_signals(query, count=30, max_age_hours=48, pages=1):
    """Fetch tweets via TwitterAPI.io advanced_search with pagination, filtering stale results."""
    if not TWITTER_API_IO_KEY:
        return []
    try:
        from datetime import timedelta, timezone
        all_tweets = []
        cursor = ""
        for _ in range(pages):
            resp = requests.get(
                "https://api.twitterapi.io/twitter/tweet/advanced_search",
                headers={"X-API-Key": TWITTER_API_IO_KEY},
                params={"query": query, "queryType": "Latest", "count": min(count, 100), "cursor": cursor},
                timeout=30,
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
        return fresh
    except Exception:
        pass
    return []


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
        recent = _fetch_signals(topic_keywords, count=10)
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
            timeout=15,
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

    _today_playing = _get_denver_games_today()
    _best_sport = max(_sport_scores, key=_sport_scores.get) if max(_sport_scores.values()) > 0 else None

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
    """Popup for editing a signal brief and choosing voice/format before building."""
    brief = st.session_state.get("sig_brief", "")
    if not brief:
        st.warning("No signal selected.")
        return

    st.markdown(f'<div style="background:rgba(45,212,191,0.06);border:1px solid rgba(45,212,191,0.15);border-radius:10px;padding:16px;margin-bottom:12px;font-size:12px;color:#b8c8d8;line-height:1.7;white-space:pre-wrap;">{brief}</div>', unsafe_allow_html=True)
    edited_brief = st.text_area("Edit brief:", value=brief, height=160, key="sig_brief_edit")

    _custom_voices = load_json("voice_styles.json", [])
    _voice_opts = ["Default", "Critical", "Homer", "Sarcastic"] + [s["name"] for s in _custom_voices]
    _fmt_opts = ["Punchy Tweet", "Normal Tweet", "Long Tweet", "Thread", "Article"]
    vc1, vc2 = st.columns(2)
    with vc1:
        sig_voice = st.selectbox("Voice", _voice_opts, key="sig_voice")
    with vc2:
        sig_fmt = st.selectbox("Format", _fmt_opts, index=1, key="sig_fmt")

    if st.button("⊞ Build", use_container_width=True, key="sig_build", type="primary"):
        # Store pending build — AI will run on the main page OUTSIDE this dialog
        st.session_state["_sig_pending_build"] = {
            "brief": st.session_state.get("sig_brief_edit", edited_brief),
            "fmt": sig_fmt,
            "voice": sig_voice,
        }
        st.rerun()


@st.dialog("Signal Build", width="large")
def _signal_result_dialog(_nonce):
    """Display-only dialog showing AI build results from a signal brief."""
    brief = st.session_state.get("sig_brief", "")
    fmt = st.session_state.get("sig_fmt", "Normal Tweet")
    voice = st.session_state.get("sig_voice", "Default")
    _ci_output_panel_impl("build", brief, fmt, voice)


def page_signals_prompts():
    st.markdown('<div class="main-header">SIGNALS <span>& PROMPTS</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="tool-desc">Live hot topics auto-generate structured briefs for Creator Studio.</div>', unsafe_allow_html=True)

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

    # ── Handle pending build (AI runs HERE on main page, visible to user) ──
    _pending = st.session_state.pop("_sig_pending_build", None)
    if _pending:
        for _k in ["ci_banger_data", "ci_result", "ci_viral_data", "ci_grades", "ci_preview"]:
            st.session_state.pop(_k, None)
        _status = st.empty()
        _status.markdown('<div style="text-align:center;padding:40px 0;"><div style="font-size:15px;font-weight:600;color:#2DD4BF;margin-bottom:8px;">Building your tweets...</div><div style="font-size:12px;color:#666888;">AI is generating 3 options from your signal brief</div></div>', unsafe_allow_html=True)
        _run_ci_ai("build", _pending["brief"], _pending["fmt"], _pending["voice"])
        _status.empty()
        st.session_state["sig_fmt"] = _pending["fmt"]
        st.session_state["sig_voice"] = _pending["voice"]
        _signal_result_dialog(str(time.time()))

    # ── Handle Redo from Signal Build dialog ──
    if st.session_state.pop("_sig_reopen_result", False):
        _signal_result_dialog(str(time.time()))

    # ── Refresh button ──
    if st.button("↻ Refresh Signals", use_container_width=False, key="sig_refresh"):
        _SIGNALS_CACHE["beat"] = None
        _SIGNALS_CACHE["national"] = None
        _SIGNALS_CACHE["ts"] = 0

    # ── Fetch signals (cache 5 min) ──
    if time.time() - _SIGNALS_CACHE["ts"] > 300 or not _SIGNALS_CACHE["beat"]:
        with st.spinner("Scanning Twitter signals..."):
            _SIGNALS_CACHE["beat"] = _fetch_signals(_BEAT_REPORTERS, count=100, pages=3)
            _SIGNALS_CACHE["national"] = _fetch_signals(_NATIONAL_QUERY, count=100, pages=2, max_age_hours=168)
            _SIGNALS_CACHE["ts"] = time.time()

    beat_tweets = _dedup_signals(_SIGNALS_CACHE.get("beat", []))
    national_tweets = _dedup_signals(_SIGNALS_CACHE.get("national", []))

    # Sort by reply count (replies = controversy = prompt gold)
    beat_sorted = sorted(beat_tweets, key=lambda t: t.get("replyCount", 0), reverse=True)[:10]
    national_sorted = sorted(national_tweets, key=lambda t: t.get("retweetCount", 0) + t.get("quoteCount", 0), reverse=True)[:10]

    tab_beat, tab_national = st.tabs(["Beat Reporter Heat Map", "National Take Detector"])

    # ── Signal 1: Beat Reporter Heat Map ──
    with tab_beat:
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
                <div style="font-size:12px;color:#d8d8e8;line-height:1.5;">{text}{'...' if len(tw.get('text',''))>200 else ''}</div>
                <div style="margin-top:6px;font-size:10px;color:#666888;">{_ago}{' &middot; ' if _ago else ''}{replies} replies &middot; {rts} RTs</div>
            </div>''', unsafe_allow_html=True)
            if st.button("Use Signal", key=f"sig_beat_{idx}", use_container_width=True):
                st.session_state["sig_selected"] = tw
                st.session_state["sig_brief"] = _build_signal_brief(tw)
                for _k in ["ci_banger_data", "ci_result", "ci_viral_data", "ci_grades", "ci_preview"]:
                    st.session_state.pop(_k, None)
                _signal_brief_dialog(str(time.time()))

    # ── Signal 2: National Take Detector ──
    with tab_national:
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
                <div style="font-size:12px;color:#d8d8e8;line-height:1.5;">{text}{'...' if len(tw.get('text',''))>200 else ''}</div>
                <div style="margin-top:6px;font-size:10px;color:#666888;">{_ago}{' &middot; ' if _ago else ''}{rts} RTs &middot; {qts} QTs &middot; {replies} replies</div>
            </div>''', unsafe_allow_html=True)
            if st.button("Use Signal", key=f"sig_nat_{idx}", use_container_width=True):
                st.session_state["sig_selected"] = tw
                st.session_state["sig_brief"] = _build_signal_brief(tw)
                for _k in ["ci_banger_data", "ci_result", "ci_viral_data", "ci_grades", "ci_preview"]:
                    st.session_state.pop(_k, None)
                _signal_brief_dialog(str(time.time()))



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
    "R&D Council": page_rd_council,
    "Signals & Prompts": page_signals_prompts,
}

# Sync strategy:
# @st.cache_data(ttl=3600) means this runs AT MOST once per hour across ALL page loads.
# st.session_state resets on every navigation (full page reload on Streamlit Cloud),
# so the old session_state guard was useless — the sync ran on every click.
@st.cache_data(ttl=3600, show_spinner=False)
def _auto_sync_tweets():
    try:
        gist_id = st.secrets.get("GIST_ID", "15fb167bbbfdaa79d5ce11c266c3f652")
        resp = requests.get(
            f"https://api.github.com/gists/{gist_id}",
            headers=_gist_headers(), timeout=10
        )
        file_meta = resp.json().get("files", {}).get("hq_tweet_history.json", {})
        existing_count = 0
        if file_meta:
            raw_url = file_meta.get("raw_url", "")
            if raw_url:
                raw_resp = requests.get(raw_url, timeout=20)
                existing_count = len(json.loads(raw_resp.text))
        if existing_count < 50:
            sync_tweet_history(quick=False)
        else:
            sync_tweet_history(quick=True)
    except Exception:
        pass

_auto_sync_tweets()

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
