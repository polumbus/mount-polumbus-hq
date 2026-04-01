"""Global CSS styles for Post Ascend."""
import streamlit as st

def inject_css():
    """Inject the global CSS stylesheet. Called once at app startup."""
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
   CREATOR STUDIO — Clean Dock
═══════════════════════════════════════════════ */
/* Format/Voice pill rows — compact rectangular buttons */
.cs-fmt-row button, .cs-voice-row button {
  padding: 0 16px !important; border-radius: 14px !important;
  font-size: 12px !important; font-weight: 600 !important;
  min-height: 44px !important; height: 44px !important; line-height: 1.3 !important;
  width: auto !important; min-width: 0 !important;
}
.cs-fmt-row [data-testid="stHorizontalBlock"],
.cs-voice-row [data-testid="stHorizontalBlock"] {
  gap: 6px !important; justify-content: flex-start !important; flex-wrap: wrap !important;
}
.cs-fmt-row [data-testid="stColumn"], .cs-voice-row [data-testid="stColumn"],
.cs-fmt-row [data-testid="stLayoutWrapper"], .cs-voice-row [data-testid="stLayoutWrapper"] {
  width: auto !important; flex: 0 0 auto !important; min-width: 0 !important; max-width: none !important;
}
.cs-fmt-row [data-testid="stElementContainer"], .cs-voice-row [data-testid="stElementContainer"] {
  width: auto !important;
}
.cs-fmt-row button[kind="secondary"] {
  background: #0e1a2e !important; border: 1px solid #1a2a45 !important; color: #5a7090 !important;
}
.cs-fmt-row button[kind="secondary"]:hover { border-color: rgba(45,212,191,0.4) !important; color: #8ab0c8 !important; }
.cs-fmt-row button[kind="primary"] {
  background: rgba(45,212,191,0.1) !important; border: 1px solid rgba(45,212,191,0.4) !important; color: #2DD4BF !important;
}
.cs-voice-row button[kind="secondary"] {
  background: #0e1a2e !important; border: 1px solid rgba(196,158,60,0.2) !important; color: #5a7090 !important;
}
.cs-voice-row button[kind="secondary"]:hover { border-color: rgba(196,158,60,0.4) !important; color: #c0a050 !important; }
.cs-voice-row button[kind="primary"] {
  background: rgba(196,158,60,0.1) !important; border: 1px solid rgba(196,158,60,0.4) !important; color: #C49E3C !important;
}
/* Hidden action buttons — CSS hides them from first frame (no flash) */
/* clip:rect keeps elements in DOM and clickable, unlike display:none */
[class*="st-key-bd_subject"], [class*="st-key-bd_ideas"],
[class*="st-key-bd_gen_tweets"], [class*="st-key-bd_gen_long"],
[class*="st-key-bd_gen_video"], [class*="st-key-bd_save"],
[class*="st-key-bd_new"], [class*="st-key-bd_saved"],
[class~="st-key-ci_banger"], [class~="st-key-ci_build"],
[class~="st-key-ci_repurpose"], [class~="st-key-ci_engage"],
[class~="st-key-ci_save"], [class~="st-key-ci_bank_btn"],
[class~="st-key-ci_inspiration"], [class~="st-key-ci_post_direct"],
[class*="st-key-coach_new"], [class*="st-key-coach_clear_all"],
[class*="st-key-cv_"], [class*="st-key-cc_fmt_"],
[class*="st-key-coach_send"], [class*="st-key-coach_save_idea"],
[class*="st-key-coach_repurpose"],
[class*="st-key-aw_src_"], [class*="st-key-aw_tw_"], [class*="st-key-aw_bd_"],
[class*="st-key-aw_scratch"], [class*="st-key-aw_outline"],
[class*="st-key-aw_research_btn"], [class*="st-key-aw_save"],
[class*="st-key-aw_show_articles"], [class*="st-key-aw_copy"],
[class*="st-key-aw_verify"],
[class*="st-key-th_ai_hooks"], [class*="st-key-th_ai_worst"],
[class*="st-key-th_ai_voice"], [class*="st-key-th_ai_topics"],
[class*="st-key-aa_run"],
[class*="st-key-hc_run"], [class*="st-key-hc_clear"],
[class*="st-key-ap_load"], [class*="st-key-ap_ai"], [class*="st-key-ap_sort_"],
[class*="st-key-ar_run"], [class*="st-key-ar_save_voice"],
[class*="st-key-rg_load_posts"], [class*="st-key-rg_load_all"],
[class*="st-key-rg_load_verified"], [class*="st-key-rg_list_"],
[class*="st-key-rg_new_list_btn"], [class*="st-key-rg_etg_"],
[class*="st-key-rg_etl_"], [class*="st-key-rg_ets_"], [class*="st-key-rg_etrd_"],
[class*="st-key-insp_show_add"], [class*="st-key-insp_tag_"],
[class*="st-key-sig_refresh"], [class*="st-key-sig_tab_"],
[class*="st-key-sig_beat_"], [class*="st-key-sig_nat_"],
[class*="st-key-timer_5"], [class*="st-key-timer_10"],
[class*="st-key-timer_15"], [class*="st-key-timer_30"] {
  position: absolute !important;
  width: 1px !important;
  height: 1px !important;
  overflow: hidden !important;
  clip: rect(0,0,0,0) !important;
  white-space: nowrap !important;
  padding: 0 !important;
  margin: 0 !important;
  border: 0 !important;
}
/* Style remaining visible Streamlit buttons to match theme */
[class*="st-key-btn_inspiration"] button,
[class*="st-key-btn_regen_insp"] button,
[class*="st-key-rg_del_list_btn"] button,
[class*="st-key-rg_ai_fill_all"] button,
[class*="st-key-rg_nl_save"] button,
[class*="st-key-rg_nl_cancel"] button,
[class*="st-key-th_sync"] button,
[class*="st-key-hof_import_btn"] button,
[class*="st-key-insp_save"] button {
  border-radius: 14px !important; font-size: 12px !important; font-weight: 600 !important;
  min-height: 44px !important; letter-spacing: 0.04em !important;
}
/* Icon dock hover effect */
.cs-idock-btn:hover { opacity:0.85; transform:translateY(-2px); transition:all 0.2s; }
.cs-idock-primary:hover { box-shadow:0 4px 20px rgba(45,212,191,0.3); }
/* Bottom bar + inline button hover + active */
.cs-bot:hover { border-color:rgba(45,212,191,0.4) !important; color:#8ab0c8 !important; transition:all 0.15s; }
.cs-bot:active { transform:scale(0.95); opacity:0.8; transition:all 0.05s; }
/* Mobile: force pill rows horizontal, not stacked */
@media (max-width: 768px) {
  .cs-fmt-row [data-testid="stHorizontalBlock"],
  .cs-voice-row [data-testid="stHorizontalBlock"] {
    flex-direction: row !important; flex-wrap: wrap !important; gap: 6px !important;
  }
  .cs-fmt-row [data-testid="stColumn"],
  .cs-voice-row [data-testid="stColumn"] {
    width: auto !important; flex: 0 0 auto !important; min-width: 0 !important; max-width: none !important;
  }
  .cs-fmt-row button, .cs-voice-row button {
    padding: 5px 10px !important; font-size: 10px !important;
  }
  /* Dock icons stay horizontal on mobile */
  .cs-icon-dock { gap: 6px !important; flex-wrap: nowrap !important; }
  .cs-idock-btn { width: 44px !important; height: 44px !important; }
  /* Bottom bar wraps to 2 rows on very small screens */
  .cs-bottom-bar { flex-wrap: wrap !important; gap: 6px !important; }
  .cs-bot { height: 44px !important; padding: 0 12px !important; font-size: 10px !important; }
}

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
  user-select: none; opacity: 0.035;
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
