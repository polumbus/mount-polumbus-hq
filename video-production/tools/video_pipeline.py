#!/usr/bin/env python3
"""Deterministic Post Ascend how-to video production scaffold.

This pipeline intentionally blocks final completion until the required
reference MP4 is available. It prepares scripts, storyboards, capture plans,
demo data, and QC packets without making unsafe live calls.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VP = ROOT / "video-production"
ASSETS_REF = ROOT / "assets" / "reference"
REFERENCE_MP4 = ASSETS_REF / "post-ascend-reference.mp4"


@dataclass(frozen=True)
class Page:
    canonical: str
    slug: str
    route: str
    component: str
    duration: int
    purpose: str
    takeaway: str
    demo: str
    actions: tuple[str, ...]
    callouts: tuple[str, ...]


PAGES: tuple[Page, ...] = (
    Page("Overview", "overview", "Creator Evolution", "cross-page montage", 30, "Introduce Post Ascend as a creator operating system.", "Capture, create, tune, score, and learn in one loop.", "Fast flashes of major app sections.", ("Show opening title", "Show page group flashes", "End on app view"), ("Capture", "Create", "Tune", "Score", "Learn")),
    Page("Creator Evolution", "creator-evolution", "Creator Evolution", "page_creator_evolution", 65, "Advanced creation engine for rough ideas into polished content.", "Messy idea in, polished options out.", "Broncos camp is going to expose which depth pieces are real and which ones are just offseason hype.", ("Open page", "Choose Normal Tweet", "Choose Witty Edge", "Paste raw idea", "Generate options", "Emphasize best option"), ("Messy idea in", "Choose format", "Choose voice", "Generate polished options")),
    Page("Voice Tuner", "voice-tuner", "Voice Tuner", "page_voice_tuner", 70, "Safe lab for testing voice changes before applying them live.", "Nothing changes live unless explicitly applied.", "Bo Nix may be on track, but one QB decision will show whether Denver trusts the ankle.", ("Open page", "Choose Promo", "Generate A/B Test", "Show A live and B sandbox", "Open guided feedback", "Show live controls collapsed"), ("Current live voice", "Sandbox test voice", "Safe until applied live")),
    Page("Creator Studio", "creator-studio", "Creator Studio", "page_compose_ideas", 60, "Fast drafting, grading, and saving workspace.", "Draft fast, grade, save the best idea.", "Camp battles tell you more than press conferences.", ("Open page", "Enter idea", "Choose format and voice", "Generate", "Open grades", "Save to Idea Bank"), ("Draft fast", "Grade the output", "Save the best idea")),
    Page("Raw Thoughts", "raw-thoughts", "Raw Thoughts", "page_brain_dump", 50, "Scratchpad for messy ideas before they become posts.", "Capture before the idea disappears.", "Broncos depth chart pressure at camp, who survives real reps vs offseason hype.", ("Open page", "Type messy note", "Save", "Show saved state"), ("Capture messy ideas", "Save before it disappears", "Turn it into content later")),
    Page("Content Coach", "content-coach", "Content Coach", "page_content_coach", 65, "Strategic advisor for angles, positioning, and stronger framing.", "Use it when the angle feels generic.", "How should I frame Sean Payton creating camp pressure without sounding generic?", ("Open page", "Ask coaching question", "Submit", "Highlight stronger framing"), ("Ask for strategy", "Sharpen the angle", "Use the best frame elsewhere")),
    Page("Article Writer", "article-writer", "Article Writer", "page_article_writer", 65, "Turns tweets, raw thoughts, or scratch ideas into long-form content.", "Small ideas become editable long-form structure.", "Use saved Broncos camp raw thought.", ("Open page", "Choose Raw Thoughts source", "Select saved idea", "Generate article structure"), ("Start from a saved idea", "Generate long-form structure", "Edit and publish")),
    Page("Reply Mode", "reply-mode", "Reply Mode", "page_reply_guy", 60, "Creates replies for engagement without sounding generic.", "Join conversations with replies that still sound like the account.", "The Broncos camp battles are more interesting than the starters this year.", ("Open page", "Paste fake post", "Generate replies", "Choose best reply"), ("Paste the post", "Generate replies", "Choose the strongest response")),
    Page("Idea Bank", "idea-bank", "Idea Bank", "page_inspiration", 55, "Saved content vault for ideas, drafts, and reusable inspiration.", "Good ideas stay available for reuse.", "Saved camp pressure idea.", ("Open page", "Browse ideas", "Open idea", "Show repurpose path"), ("Saved ideas", "Search and filter", "Repurpose later")),
    Page("Post History", "post-history", "Post History", "page_tweet_history", 55, "Tracks past posts and gives the app memory.", "Avoid repeats and give the system better context.", "Mock recent post history.", ("Open page", "Show previous posts", "Filter or scroll", "Highlight context value"), ("Past posts", "Avoid repeats", "Better context")),
    Page("Algorithm Score", "algorithm-score", "Algorithm Score", "page_algo_analyzer", 70, "Grades a draft for performance and fix opportunities.", "Use it as a pre-flight check before posting.", "Broncos camp is going to be interesting this year.", ("Open page", "Paste draft", "Run score", "Show weak category", "Apply suggested fix"), ("Score the draft", "Find the weak spot", "Improve and re-check")),
    Page("Account Audit", "account-audit", "Account Audit", "page_health_check", 60, "Reviews account-level health and strategic gaps.", "Turn account weaknesses into a fix list.", "Mock account audit results.", ("Open page", "Show audit categories", "Highlight recommendation"), ("Big-picture account review", "Find weak areas", "Turn recommendations into fixes")),
    Page("My Stats", "my-stats", "My Stats", "page_account_pulse", 55, "Summarizes account performance trends.", "Use trends to guide the next post.", "Mock performance metrics.", ("Open page", "Show metrics", "Highlight trend", "Connect trend to next post"), ("Performance trends", "Find what works", "Guide the next post")),
    Page("Profile Analyzer", "profile-analyzer", "Profile Analyzer", "page_account_researcher", 60, "Analyzes profile positioning, voice, and opportunities.", "Make the profile and content direction more intentional.", "Fake creator profile.", ("Open page", "Load safe sample profile", "Run analysis", "Show strengths and opportunities"), ("Analyze positioning", "Find strengths", "Spot opportunities")),
    Page("Signals & Prompts", "signals-prompts", "Signals & Prompts", "page_signals_prompts", 60, "Finds timely signals and turns them into prompts.", "Know what to talk about today.", "Mock Broncos camp and Denver sports signals.", ("Open page", "Load signals", "Pick one signal", "Turn it into prompt"), ("Find timely signals", "Pick the strongest angle", "Turn it into a prompt")),
    Page("Fan Pulse Gameday", "fan-pulse-gameday", "Fan Pulse Gameday", "page_gameday", 65, "Finds live sports fan emotion and timely angles.", "Post while the moment still matters.", "Mock Avalanche playoff momentum swing.", ("Open page", "Show live game topic", "Review fan angle", "Create timely post idea"), ("Live fan reaction", "Find the emotion", "Post while it matters")),
    Page("Podcast", "podcast", "Podcast", "page_podcast", 75, "Tracks podcast workflow from source to publish verification.", "Keep the episode moving through approved gates.", "Mock Draft Day episode run.", ("Open page", "Open run", "Show wizard steps", "Show package/clip/publish gates"), ("Start", "Package", "Clip", "Publish", "Done")),
    Page("10/10 Audit", "ten-ten-audit", "10/10 Audit", "page_ten_x_audit", 55, "Internal quality-control audit for app/workflow areas.", "Turn quality gaps into fixes.", "Mock Creator Evolution audit.", ("Open page", "Pick area", "Show findings", "Show fix list"), ("Quality audit", "Find what is weak", "Turn problems into fixes")),
    Page("Debug Console", "debug-console", "Debug Console", "page_debug_console", 50, "Owner-only diagnostics for provider and system health.", "Troubleshoot safely without exposing secrets.", "Safe fake provider and proxy health.", ("Open page in demo mode", "Show fake health cards", "Show no secrets"), ("Owner-only", "Provider health", "Safe diagnostics", "No secrets shown")),
)


DIRS = [
    VP / "scripts",
    VP / "storyboards",
    VP / "capture-plans",
    VP / "demo-data",
    VP / "renders" / "drafts",
    VP / "renders" / "finals",
    VP / "thumbnails",
    VP / "captions",
    VP / "qc" / "subagent-reviews",
    VP / "reference-frames",
    ASSETS_REF,
]


def sh(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=check)


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def ensure_dirs() -> None:
    for directory in DIRS:
        directory.mkdir(parents=True, exist_ok=True)


def reference_metadata() -> dict:
    if not REFERENCE_MP4.exists():
        return {
            "available": False,
            "blockedReason": "Reference MP4 is missing. Direct X download was blocked by yt-dlp guest-token/API failure.",
            "requiredPath": str(REFERENCE_MP4.relative_to(ROOT)),
        }
    try:
        probe = sh([
            "ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(REFERENCE_MP4)
        ])
        meta = json.loads(probe.stdout or "{}")
    except Exception as exc:
        return {"available": False, "blockedReason": f"ffprobe failed: {exc}", "requiredPath": str(REFERENCE_MP4.relative_to(ROOT))}
    video = next((s for s in meta.get("streams", []) if s.get("codec_type") == "video"), {})
    audio = next((s for s in meta.get("streams", []) if s.get("codec_type") == "audio"), {})
    return {
        "available": True,
        "path": str(REFERENCE_MP4.relative_to(ROOT)),
        "width": video.get("width"),
        "height": video.get("height"),
        "fps": video.get("r_frame_rate"),
        "duration": float(meta.get("format", {}).get("duration", 0) or 0),
        "videoCodec": video.get("codec_name"),
        "audioCodec": audio.get("codec_name"),
        "bitrate": meta.get("format", {}).get("bit_rate"),
    }


def write_reference_blocker() -> None:
    if REFERENCE_MP4.exists():
        return
    write(
        ASSETS_REF / "NEED_REFERENCE_VIDEO.md",
        """# Reference Video Required

The requested X reference video could not be downloaded programmatically.

Attempted source:
https://x.com/derekmeegan/status/2054694139397361842?s=20

Observed blocker:
`yt-dlp` failed while querying X/Twitter with a bad guest token/API error.

To complete final rendering and style-match QC, provide either:

1. `assets/reference/post-ascend-reference.mp4`
2. At least 8 representative screenshots under `assets/reference/screenshots/`

Until one of those exists, this pipeline may prepare scripts, storyboards,
capture plans, demo data, and QC structure, but it must not claim final
reference-matched rendered videos are complete.
""",
    )


def style_bible() -> None:
    meta = reference_metadata()
    md = [
        "# Post Ascend Reference Style Bible",
        "",
        f"Reference available: `{meta.get('available')}`",
        "",
    ]
    if not meta.get("available"):
        md.extend([
            "## Blocked",
            "",
            meta.get("blockedReason", "Reference MP4 missing."),
            "",
            "The production defaults below are provisional and must be replaced by measured values after the reference video is supplied.",
        ])
    else:
        md.extend([
            "## Measured Reference Metadata",
            "",
            f"- Resolution: {meta.get('width')}x{meta.get('height')}",
            f"- FPS: {meta.get('fps')}",
            f"- Duration: {meta.get('duration'):.2f}s",
            f"- Codec: {meta.get('videoCodec')}",
            f"- Audio codec: {meta.get('audioCodec')}",
            f"- Bitrate: {meta.get('bitrate')}",
        ])
        md.extend(reference_observation_markdown())
    md.extend([
        "",
        "## Post Ascend Production Targets",
        "",
        "- Primary resolution: match reference aspect ratio and use 1920x1123 or 1920x1080 safe 16:9 variant depending platform target.",
        "- FPS: 30fps to match reference cadence unless a platform variant requires otherwise.",
        "- Codec: H.264 yuv420p.",
        "- Audio: reference has no audio, but Post Ascend tutorials should add clean AAC narration at 48kHz, target -16 LUFS, true peak below -1 dB.",
        "- Page video length: 45-75 seconds.",
        "- Overview length: about 30 seconds, close to the reference 26.33s pace.",
        "- Motion: rapid but readable cuts, smooth zooms and pans, no static shot over 4 seconds.",
        "- Captions: reference uses no obvious burned-in captions; provide SRT/VTT and use only minimal burned-in callouts if needed.",
        "- Callouts: minimal, product-action-specific, one instructional idea per scene.",
        "- Security: demo mode only, fake data only, no secrets or real user data.",
    ])
    write(VP / "reference-style-bible.md", "\n".join(md) + "\n")
    write_json(VP / "reference-style-bible.json", {"reference": meta, "provisionalDefaults": {
        "resolution": "1920x1080",
        "fps": 60,
        "codec": "h264",
        "audio": "aac 48kHz -16 LUFS",
        "durationSeconds": {"overview": 30, "page": [45, 75]},
        "blockedUntilReferenceAvailable": not meta.get("available"),
    }, "observedStyle": reference_observation_json() if meta.get("available") else {}})


def reference_observation_markdown() -> list[str]:
    return [
        "",
        "## Observed Visual Style",
        "",
        "- Format: ultra-wide 3692x2160 capture, roughly 1.71:1 aspect ratio.",
        "- Duration: 26.33 seconds, fast product-demo pacing.",
        "- Audio: none in downloaded media. The original X post may rely on silent visual demo.",
        "- Opening: immediate UI context, no long logo intro.",
        "- Background: soft pink/peach textured canvas with black/red pixelated horizon-like accent behind floating app windows.",
        "- UI framing: browser/app windows float above the background with rounded top chrome and strong shadow/contrast.",
        "- Screen treatment: crisp UI, high-resolution capture, mostly dark-mode developer surface plus occasional bright web/API result panels.",
        "- Motion language: quick cuts, scroll/cursor interactions, and progressive reveal of generated output.",
        "- Cursor: visible standard cursor, used to guide attention; no oversized cursor styling observed.",
        "- Text overlays: minimal. Most explanatory text is inside the recorded app/terminal UI rather than added captions.",
        "- Captions: no obvious burned-in subtitles in the captured reference frames.",
        "- Callouts: restrained; emphasis comes from zoom/crop/framing and generated UI content.",
        "- Outro: ends on useful generated artifact/API output rather than a heavy end card.",
    ]


def reference_observation_json() -> dict:
    return {
        "aspectRatioApprox": 1.709,
        "durationSeconds": 26.333333,
        "audio": "none_detected",
        "openingTreatment": "immediate_ui_context_no_long_logo_intro",
        "backgroundTreatment": "soft_pink_peach_texture_with_black_red_pixel_horizon_accent",
        "windowFraming": "floating_browser_or_app_windows_with_dark_surfaces_and_subtle_shadow",
        "motionLanguage": "fast_cuts_scrolls_cursor_guidance_progressive_output_reveal",
        "cursor": "standard_visible_cursor",
        "captions": "no_obvious_burned_in_subtitles",
        "callouts": "minimal_rely_on_ui_content_and_framing",
        "recommendedAdaptation": "Post Ascend tutorials should use crisp UI capture, fast scene rhythm, minimal callouts, and optional narration/captions only where needed for teaching.",
    }


def extract_reference_frames() -> None:
    if not REFERENCE_MP4.exists():
        return
    frames_dir = VP / "reference-frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    if not any(frames_dir.glob("frame-*.jpg")):
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(REFERENCE_MP4), "-vf", "fps=1,scale=480:-1", str(frames_dir / "frame-%03d.jpg")],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    sheet = VP / "reference-contact-sheet.jpg"
    if not sheet.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(REFERENCE_MP4), "-vf", "fps=1,scale=480:-1,tile=7x4", "-frames:v", "1", str(sheet)],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def script_for(page: Page) -> str:
    narration = (
        f"{page.canonical} is for {page.purpose.lower()} "
        f"Use it when you need to {page.takeaway.lower()} "
        f"In this demo, we use {page.demo}. "
        f"The workflow is simple: {', '.join(a.lower() for a in page.actions[:5])}. "
        f"The value is clear: {page.takeaway}"
    )
    scenes = storyboard_for(page)["scenes"]
    lines = [
        f"# {page.canonical} Tutorial Script",
        "",
        f"Target duration: {page.duration} seconds",
        f"Route: `{page.route}`",
        "",
        "## Final Narration",
        "",
        narration,
        "",
        "## Scene Plan",
        "",
    ]
    for scene in scenes:
        lines.extend([
            f"### Scene {scene['sceneNumber']} ({scene['start']} - {scene['end']})",
            f"- UI action: {scene['uiAction']}",
            f"- Visual focus: {scene['visual']}",
            f"- Overlay text: {scene['overlayText']}",
            f"- Caption: {scene['caption']}",
            f"- Audio/SFX notes: {scene['sfx'] or 'Clean narration, subtle UI click if reference supports it.'}",
            "",
        ])
    return "\n".join(lines)


def storyboard_for(page: Page) -> dict:
    scene_count = 5 if page.slug != "overview" else 4
    segment = max(6, page.duration // scene_count)
    scenes = []
    for idx in range(scene_count):
        start_s = idx * segment
        end_s = page.duration if idx == scene_count - 1 else (idx + 1) * segment
        action = page.actions[min(idx, len(page.actions) - 1)]
        callout = page.callouts[min(idx, len(page.callouts) - 1)]
        scenes.append({
            "sceneNumber": idx + 1,
            "start": f"00:{start_s:02d}.000",
            "end": f"00:{end_s:02d}.000",
            "visual": f"Focused screen recording of {page.canonical}: {action}.",
            "uiAction": action,
            "cursorAction": "Smooth eased movement to the relevant control; click highlight only on the action.",
            "cameraMove": "Reference-matched zoom/pan once reference is available; provisional 1.0x to 1.18x ease-in-out.",
            "overlayText": callout,
            "narration": f"{page.canonical}: {action}.",
            "caption": callout,
            "sfx": "",
            "qcIntent": f"Prove viewer understands: {page.takeaway}",
        })
    return {
        "slug": page.slug,
        "title": page.canonical,
        "targetDurationSeconds": page.duration,
        "route": page.route,
        "pagePurpose": page.purpose,
        "viewerTakeaway": page.takeaway,
        "demoData": {"primaryExample": page.demo},
        "scenes": scenes,
        "requiredChecks": [
            "No secrets or real private data visible.",
            "Opening title present.",
            "Ending value line present.",
            "Captions present and readable.",
            "UI action shown, not just described.",
        ],
    }


def capture_plan_for(page: Page) -> str:
    selectors = [f"[data-video-id='{page.slug}-primary']", "main", "button", "textarea", "select"]
    return f"""# {page.canonical} Capture Plan

Page route:
`/?token=VIDEO_DEMO_TOKEN&user=owner&page={page.route.replace(' ', '+')}`

Demo mode:
`VIDEO_DEMO_MODE=1`

Required seed data:
`video-production/demo-data/video-demo-seed.json`

Exact selectors:
{chr(10).join(f"- `{selector}`" for selector in selectors)}

Exact actions:
{chr(10).join(f"{idx + 1}. {action}" for idx, action in enumerate(page.actions))}

Expected UI state after each action:
- The relevant control is visible.
- The page uses deterministic demo data.
- No real external API call is required.
- No token, cookie, API key, OAuth value, webhook, or real email is visible.

Failure conditions:
- Page route does not load.
- Loading spinner remains visible.
- Required control is hidden or offscreen.
- Any real private data appears.
- Captions or callouts cover the demonstrated control.
- Demo data differs from the storyboard.

Sensitive-data checks:
- Scan text assets and rendered frames for API keys, bearer tokens, OAuth tokens, passwords, real emails, cookies, private keys, and webhook URLs.

Capture notes:
- Use reference-matched aspect ratio once the reference is available.
- Use smooth cursor motion and one clear action per scene.
- Keep browser chrome hidden unless the reference shows browser chrome.

Known edge cases:
- Streamlit reruns can shift layout; wait for stable visible text before each capture.
- Owner-only pages must use demo token and fake owner identity.

Retry behavior:
- Retry page load once.
- If deterministic demo data does not load, fail capture instead of recording real data.

Final visual checklist:
- Opening title visible.
- Main workflow visible.
- Example visible.
- Ending value line visible.
- No secrets.
"""


def demo_data() -> None:
    write_json(VP / "demo-data" / "video-demo-seed.json", {
        "mode": "VIDEO_DEMO_MODE",
        "token": "VIDEO_DEMO_TOKEN",
        "owner": "demo-owner",
        "examples": {page.slug: page.demo for page in PAGES},
    })
    write_json(VP / "demo-data" / "mock-ai-responses.json", {
        page.slug: [
            f"{page.demo} This version keeps the angle specific and ready to post.",
            f"The sharper read is simple: {page.takeaway}",
            f"{page.canonical} turns this from a rough idea into a usable next step.",
        ] for page in PAGES
    })
    write_json(VP / "demo-data" / "mock-post-history.json", {
        "posts": [
            {"text": "A camp battle is usually more revealing than a press conference.", "impressions": 18400},
            {"text": "Sean Payton does not have to say pressure out loud when the depth chart says it for him.", "impressions": 22100},
        ]
    })
    write_json(VP / "demo-data" / "mock-stats.json", {"impressions": 128400, "engagementRate": 0.061, "topTopic": "Broncos camp pressure"})
    write_json(VP / "demo-data" / "mock-audit-results.json", {"score": 92, "topFix": "Make the final sentence more specific and less generic."})
    write_json(VP / "demo-data" / "mock-signals.json", {"signals": ["Broncos camp depth", "Sean Payton roster pressure", "Avalanche goalie decision"]})
    write_json(VP / "demo-data" / "mock-podcast-run.json", {"title": "Draft Day", "state": "publish_pending", "steps": ["Start", "Package", "Clip", "Publish", "Done"]})


def route_map() -> None:
    write_json(VP / "page-route-map.json", [
        {
            "canonicalName": page.canonical,
            "slug": page.slug,
            "actualRoute": page.route,
            "componentPath": f"app.py::{page.component}",
            "requiredDemoData": f"video-production/demo-data/{'video-demo-seed.json'}",
            "primarySelectors": [f"data-video-id={page.slug}-primary", "main", "button", "textarea", "select"],
            "captureStatus": "planned",
            "notes": "Capture requires VIDEO_DEMO_MODE=1 and reference style bible finalization.",
        }
        for page in PAGES
    ])


def materialize_docs() -> None:
    ensure_dirs()
    write_reference_blocker()
    extract_reference_frames()
    style_bible()
    route_map()
    demo_data()
    for page in PAGES:
        write(VP / "scripts" / f"{page.slug}.md", script_for(page))
        write_json(VP / "storyboards" / f"{page.slug}.json", storyboard_for(page))
        write(VP / "capture-plans" / f"{page.slug}.md", capture_plan_for(page))
    write(VP / "qc" / "revision-log.md", "# Revision Log\n\nNo rendered-video revisions yet. Final rendering is blocked until the reference video is supplied.\n")


def asset_paths(page: Page) -> dict[str, Path]:
    return {
        "mp4": VP / "renders" / "finals" / f"{page.slug}.mp4",
        "srt": VP / "captions" / f"{page.slug}.srt",
        "vtt": VP / "captions" / f"{page.slug}.vtt",
        "thumb": VP / "thumbnails" / f"{page.slug}.png",
        "contact": VP / "qc" / f"{page.slug}-contact-sheet.jpg",
        "script": VP / "scripts" / f"{page.slug}.md",
        "storyboard": VP / "storyboards" / f"{page.slug}.json",
        "capture": VP / "capture-plans" / f"{page.slug}.md",
    }


SECRET_PATTERNS = [
    re.compile(r"(?i)api[_-]?key\\s*[:=]\\s*['\\\"][^'\\\"]+"),
    re.compile(r"(?i)bearer\\s+[a-z0-9._\\-]{20,}"),
    re.compile(r"(?i)oauth[_-]?token\\s*[:=]"),
    re.compile(r"-----BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(r"(?i)password\\s*[:=]\\s*['\\\"][^'\\\"]+"),
    re.compile(r"https://discord(?:app)?\\.com/api/webhooks/"),
    re.compile(r"(?<!fake)(?<!demo)[A-Z0-9._%+-]+@[A-Z0-9.-]+\\.[A-Z]{2,}", re.I),
]


def scan_text_assets() -> list[dict]:
    findings: list[dict] = []
    for path in list(VP.rglob("*.md")) + list(VP.rglob("*.json")) + list(VP.rglob("*.srt")) + list(VP.rglob("*.vtt")):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append({"path": str(path.relative_to(ROOT)), "issue": "potential_secret_or_private_data", "pattern": pattern.pattern})
    return findings


def media_meta(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        probe = sh(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
        return json.loads(probe.stdout or "{}")
    except Exception as exc:
        return {"error": str(exc)}


def qc() -> int:
    materialize_docs()
    reference = reference_metadata()
    results = {
        "reference": reference,
        "approvedForPublicRelease": False,
        "videos": {},
        "textSecretFindings": scan_text_assets(),
        "failures": [],
    }
    if not reference.get("available"):
        results["failures"].append("reference_mp4_missing")
    for page in PAGES:
        paths = asset_paths(page)
        checks = {}
        for key, path in paths.items():
            checks[f"{key}Exists"] = path.exists()
            if not path.exists():
                results["failures"].append(f"{page.slug}:{key}_missing")
        checks["mediaMetadata"] = media_meta(paths["mp4"])
        results["videos"][page.slug] = checks
    if results["textSecretFindings"]:
        results["failures"].append("text_secret_scan_failed")
    write_json(VP / "qc" / "automated-qc.json", results)
    write_qc_dashboard(results)
    write_final_report(results)
    write_subagent_review_packet()
    print(f"Automated QC failures: {len(results['failures'])}")
    for failure in results["failures"][:20]:
        print(f"- {failure}")
    if len(results["failures"]) > 20:
        print(f"- ... {len(results['failures']) - 20} more")
    print(f"QC dashboard: {VP / 'qc' / 'dashboard.html'}")
    print(f"Final report: {VP / 'qc' / 'final-report.md'}")
    return 1 if results["failures"] else 0


def write_qc_dashboard(results: dict) -> None:
    rows = []
    for slug, checks in results["videos"].items():
        status = "PASS" if all(v for k, v in checks.items() if k.endswith("Exists")) else "BLOCKED"
        rows.append(f"<tr><td>{slug}</td><td>{status}</td><td>{json.dumps(checks)}</td></tr>")
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Post Ascend Video QC</title>
<style>body{{font-family:Arial,sans-serif;background:#07111f;color:#e6edf3;padding:24px}}table{{width:100%;border-collapse:collapse}}td,th{{border:1px solid #22314a;padding:8px;vertical-align:top}}.bad{{color:#ff6b6b}}.ok{{color:#2dd4bf}}</style></head>
<body>
<h1>Post Ascend Video QC Dashboard</h1>
<p>Reference available: <strong>{results['reference'].get('available')}</strong></p>
<p class="bad">Final public-release approval is blocked until every final MP4, caption, thumbnail, contact sheet, and five-agent 10/10 review exists.</p>
<h2>Failures</h2><pre>{json.dumps(results.get('failures', []), indent=2)}</pre>
<h2>Videos</h2><table><thead><tr><th>Video</th><th>Status</th><th>Checks</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
</body></html>"""
    write(VP / "qc" / "dashboard.html", html)


def write_final_report(results: dict) -> None:
    write(VP / "qc" / "final-report.md", f"""# Post Ascend Video Production Final Report

Status: BLOCKED

Reference available: `{results['reference'].get('available')}`

Automated QC failures:

```json
{json.dumps(results.get('failures', []), indent=2)}
```

This report is intentionally not marked complete until:

- Reference MP4 is available and measured.
- Final MP4s are rendered for every page.
- SRT/VTT captions, thumbnails, and contact sheets exist.
- Five subagent reviews produce only integer 10/10 scores for every category and every video.
- `APPROVED_FOR_PUBLIC_RELEASE` is true in `final-grade-matrix.json`.
""")
    write_json(VP / "qc" / "final-grade-matrix.json", {
        "APPROVED_FOR_PUBLIC_RELEASE": False,
        "blockedReason": "Final videos and five-agent 10/10 reviews are not complete.",
        "requiredAgents": [
            "STYLE_MATCH_DIRECTOR",
            "PRODUCT_EDUCATION_REVIEWER",
            "UI_ACCURACY_AND_SECURITY_QA",
            "AUDIO_CAPTION_ACCESSIBILITY_QA",
            "EXECUTIVE_LAUNCH_REVIEWER",
        ],
        "videos": {page.slug: {"status": "not_rendered", "grades": {}} for page in PAGES},
    })


def write_subagent_review_packet() -> None:
    reviews = {
        "STYLE_MATCH_DIRECTOR.md": """# STYLE_MATCH_DIRECTOR Review Packet

Current grade: 4/10

Finding:
The existing renderer can capture, narrate, and assemble videos, but final production cannot be graded 10/10 without measured reference ingestion, contact sheets, formal QC reports, and reference-style comparison.

Required before 10/10:
- Reference MP4 or approved screenshots.
- Style bible with measurable values.
- Contact sheets for reference, capture, final, and style delta.
- Render manifests with ffprobe/loudness/timeline evidence.
""",
        "PRODUCT_EDUCATION_REVIEWER.md": """# PRODUCT_EDUCATION_REVIEWER Review Packet

Current grade: blocked pending rendered videos.

Finding:
The page map and tutorial teaching objectives are now represented in scripts, storyboards, and capture plans. Final grade requires actual rendered videos showing each workflow with deterministic demo data.

Required before 10/10:
- Every page route captured.
- Every page teaches purpose, when to use it, workflow, example, and final value.
- Owner-only pages must be clearly owner-only and safe.
""",
        "UI_ACCURACY_AND_SECURITY_QA.md": """# UI_ACCURACY_AND_SECURITY_QA Review Packet

Current grade: blocked pending VIDEO_DEMO_MODE enforcement.

Finding:
Final recording must not call real AI, posting, OAuth, Twitter/X, proxy, podcast workers, Gists, or real data stores. Current production app does not yet enforce an app-wide demo boundary.

Required before 10/10:
- VIDEO_DEMO_MODE fixtures only.
- No secrets, real emails, tokens, cookies, private logs, webhook URLs, or real account data in scripts/captions/frames.
- Debug Console and Podcast demos must use fake safe data only.
""",
        "AUDIO_CAPTION_ACCESSIBILITY_QA.md": """# AUDIO_CAPTION_ACCESSIBILITY_QA Review Packet

Current grade: blocked pending media assets.

Finding:
ffmpeg/ffprobe and the existing renderer can support narration and SRT output. Final grade requires VTT, transcript, loudness checks, caption readability checks, and audio/video duration validation.

Required before 10/10:
- MP4, SRT, VTT, thumbnail, contact sheet per video.
- Audio stream present, no clipping, target loudness.
- Captions timed within 250ms and readable at mobile size.
""",
        "EXECUTIVE_LAUNCH_REVIEWER.md": """# EXECUTIVE_LAUNCH_REVIEWER Review Packet

Current grade: blocked pending full render and review gate.

Finding:
The system needs a public-launch gate that refuses false greens. The current video-production control plane is structured to fail until all final assets and five-agent 10/10 grades exist.

Required before 10/10:
- All 19 final videos rendered.
- QC dashboard and final report generated.
- final-grade-matrix.json contains only integer 10 scores and APPROVED_FOR_PUBLIC_RELEASE=true.
""",
    }
    for filename, content in reviews.items():
        write(VP / "qc" / "subagent-reviews" / filename, content)


def placeholder_command(name: str) -> int:
    materialize_docs()
    print(f"video:{name} prepared planning artifacts.")
    print("Final capture/render remains blocked until assets/reference/post-ascend-reference.mp4 is supplied.")
    return 1 if name in {"record", "render", "captions", "review"} and not REFERENCE_MP4.exists() else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["seed", "record", "render", "captions", "qc", "review", "all", "prepare"])
    args = parser.parse_args()
    if args.command in {"seed", "prepare"}:
        materialize_docs()
        print(f"Prepared {len(PAGES)} page scripts, storyboards, capture plans, route map, and demo data.")
        return 0
    if args.command in {"record", "render", "captions", "review"}:
        return placeholder_command(args.command)
    if args.command == "qc":
        return qc()
    if args.command == "all":
        materialize_docs()
        return qc()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
