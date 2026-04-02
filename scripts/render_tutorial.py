#!/usr/bin/env python3
import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright
from PIL import Image, ImageDraw, ImageFilter, ImageFont

try:
    import edge_tts
except ImportError as exc:
    raise SystemExit(
        "Missing dependency edge-tts. Run scripts/make_tutorial_video so the tutorial venv is bootstrapped."
    ) from exc


ROOT = Path(__file__).resolve().parent.parent
TMP_ROOT = ROOT / "tutorials" / "build"
DEFAULT_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
CAPTURE_CACHE_FILE = "capture_cache.json"
PREMIUM_SCENE_BG = (7, 17, 31, 84)
PREMIUM_SCENE_ACCENT = (45, 212, 191, 255)


@dataclass
class SceneAudio:
    scene_id: str
    narration: str
    path: Path
    duration: float
    start: float
    end: float


@dataclass
class ActionEvent:
    type: str
    start: float
    end: float
    text: str = ""
    dock: str = ""


@dataclass
class SceneTimeline:
    scene_id: str
    start: float
    end: float
    audio_duration: float
    actions: list[ActionEvent]
    screenshot_path: Path | None = None


@dataclass
class RenderSettings:
    crf: str
    preset: str
    fps: int
    audio_bitrate: str
    still_zoom_end: float
    still_zoom_step: float


def run(cmd: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, check=check, capture_output=True, text=True)


def ffprobe_duration(path: Path) -> float:
    result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    return float(result.stdout.strip())


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def capture_cache_key(config: dict[str, Any]) -> str:
    payload = {
        "app_url": config.get("app_url"),
        "viewport": config.get("viewport"),
        "scenes": [{"id": scene["id"], "actions": scene.get("actions", [])} for scene in config["scenes"]],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()


def audio_cache_key(scene: dict[str, Any], config: dict[str, Any]) -> str:
    payload = {
        "narration": scene["narration"],
        "voice": config.get("voice", "en-US-AndrewNeural"),
        "rate": config.get("rate", "-4%"),
        "volume": config.get("volume", "+0%"),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def render_settings(draft: bool) -> RenderSettings:
    if draft:
        return RenderSettings(
            crf="26",
            preset="superfast",
            fps=24,
            audio_bitrate="128k",
            still_zoom_end=1.025,
            still_zoom_step=0.00035,
        )
    return RenderSettings(
        crf="20",
        preset="fast",
        fps=25,
        audio_bitrate="192k",
        still_zoom_end=1.05,
        still_zoom_step=0.00055,
    )


def serialize_timeline(timeline: SceneTimeline) -> dict[str, Any]:
    return {
        "scene_id": timeline.scene_id,
        "start": timeline.start,
        "end": timeline.end,
        "audio_duration": timeline.audio_duration,
        "actions": [event.__dict__ for event in timeline.actions],
        "screenshot_path": str(timeline.screenshot_path) if timeline.screenshot_path else "",
    }


def deserialize_timeline(payload: dict[str, Any]) -> SceneTimeline:
    return SceneTimeline(
        scene_id=payload["scene_id"],
        start=float(payload["start"]),
        end=float(payload["end"]),
        audio_duration=float(payload["audio_duration"]),
        actions=[ActionEvent(**event) for event in payload.get("actions", [])],
        screenshot_path=Path(payload["screenshot_path"]) if payload.get("screenshot_path") else None,
    )


def ensure_owner_token(owner_password: str | None, owner_token: str | None) -> str:
    if owner_token:
        return owner_token
    if not owner_password:
        raise SystemExit("Provide --owner-password or --owner-token.")
    digest = hashlib.sha256(f"mp_owner_{owner_password}".encode()).hexdigest()
    return digest[:16]


async def synthesize_scene_audio(scene: dict[str, Any], config: dict[str, Any], audio_dir: Path) -> Path:
    audio_dir.mkdir(parents=True, exist_ok=True)
    out_path = audio_dir / f"{scene['id']}-{audio_cache_key(scene, config)}.mp3"
    if out_path.exists():
        return out_path
    communicate = edge_tts.Communicate(
        text=scene["narration"],
        voice=config.get("voice", "en-US-AndrewNeural"),
        rate=config.get("rate", "-4%"),
        volume=config.get("volume", "+0%"),
    )
    await communicate.save(str(out_path))
    return out_path


async def build_audio_tracks(config: dict[str, Any], work_dir: Path) -> tuple[list[SceneAudio], Path, Path]:
    audio_dir = work_dir / "audio"
    scene_audio_files = []
    current = float(config.get("lead_in_seconds", 2.5))
    audio_paths = await asyncio.gather(
        *[synthesize_scene_audio(scene, config, audio_dir) for scene in config["scenes"]]
    )
    for scene, path in zip(config["scenes"], audio_paths):
        duration = ffprobe_duration(path)
        scene_audio_files.append(
            SceneAudio(
                scene_id=scene["id"],
                narration=scene["narration"],
                path=path,
                duration=duration,
                start=current,
                end=current + duration,
            )
        )
        current += duration

    concat_file = audio_dir / "audio_concat.txt"
    concat_file.write_text(
        "\n".join([f"file '{p.path.name}'" for p in scene_audio_files]),
        encoding="utf-8",
    )
    narration_path = work_dir / "narration.mp3"
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-c",
            "copy",
            str(narration_path),
        ],
        cwd=audio_dir,
    )

    srt_path = work_dir / "captions.srt"
    entries = []
    for idx, item in enumerate(scene_audio_files, start=1):
        entries.append(
            f"{idx}\n{format_srt_time(item.start)} --> {format_srt_time(item.end)}\n{textwrap.fill(item.narration, 64)}\n"
        )
    srt_path.write_text("\n".join(entries), encoding="utf-8")
    return scene_audio_files, narration_path, srt_path


def format_srt_time(seconds: float) -> str:
    total_ms = int(round(seconds * 1000))
    hours = total_ms // 3_600_000
    total_ms %= 3_600_000
    minutes = total_ms // 60_000
    total_ms %= 60_000
    secs = total_ms // 1000
    millis = total_ms % 1000
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


async def click_by_text(page, text: str) -> None:
    locator = page.get_by_text(text, exact=True)
    if await locator.count():
        await locator.first.click()
        return
    locator = page.get_by_text(text)
    if await locator.count():
        await locator.first.click()
        return
    locator = page.locator(f"text={text}")
    if await locator.count():
        await locator.first.click()
        return
    raise RuntimeError(f"Could not find text to click: {text}")


async def click_button(page, text: str) -> None:
    locator = page.get_by_role("button", name=text)
    if await locator.count():
        await locator.first.click()
        return
    locator = page.locator("button", has_text=text)
    if await locator.count():
        await locator.first.click()
        return
    await click_by_text(page, text)


async def get_app_frame(page):
    await page.locator("iframe").first.wait_for(timeout=120000)
    deadline = asyncio.get_running_loop().time() + 120
    while asyncio.get_running_loop().time() < deadline:
        for frame in page.frames:
            if frame.url.startswith("https://postascend.streamlit.app/~/+"):
                return frame
        await page.wait_for_timeout(250)
    raise RuntimeError("Could not resolve Streamlit app iframe.")


async def perform_action(page, action: dict[str, Any], app_url: str, token: str) -> None:
    kind = action["type"]
    if kind == "goto_creator_studio":
        target = f"{app_url}/?token={token}&user=owner&page=Creator+Studio"
        await page.goto(target, wait_until="domcontentloaded", timeout=120000)
        await get_app_frame(page)
        return
    if kind == "goto_page":
        page_name = action["page"]
        target = f"{app_url}/?token={token}&user=owner&page={page_name}"
        await page.goto(target, wait_until="domcontentloaded", timeout=120000)
        await get_app_frame(page)
        return
    target = await get_app_frame(page)
    if kind == "wait_for_text":
        await target.get_by_text(action["text"]).first.wait_for(timeout=120000)
        return
    if kind == "wait":
        await target.wait_for_timeout(int(float(action.get("seconds", 1)) * 1000))
        return
    if kind == "fill_textarea":
        area = target.locator("textarea").first
        await area.wait_for(timeout=120000)
        await area.fill(action["text"])
        return
    if kind == "fill_input":
        field = target.locator("input[type='text'], input:not([type]), input[placeholder]").first
        await field.wait_for(timeout=120000)
        await field.fill(action["text"])
        return
    if kind == "click_text":
        await click_by_text(target, action["text"])
        return
    if kind == "click_button":
        await click_button(target, action["text"])
        return
    if kind == "click_dock":
        dock = action["dock"]
        locator = target.locator(f".cs-idock-btn[data-dock='{dock}']")
        await locator.first.wait_for(timeout=120000)
        await locator.first.click(force=True)
        return
    raise RuntimeError(f"Unsupported action type: {kind}")


def relative_now(started_at: float) -> float:
    return asyncio.get_running_loop().time() - started_at


async def record_tutorial(
    config: dict[str, Any],
    owner_token: str,
    work_dir: Path,
    scene_audio: list[SceneAudio],
    force_record: bool,
    reuse_only: bool = False,
) -> tuple[Path, list[SceneTimeline]]:
    video_dir = work_dir / "raw_video"
    video_dir.mkdir(parents=True, exist_ok=True)
    cache_path = work_dir / CAPTURE_CACHE_FILE
    cached_raw = work_dir / "screen_capture.webm"
    cache_key = capture_cache_key(config)
    if not force_record and cache_path.exists() and cached_raw.exists():
        cached = json.loads(cache_path.read_text(encoding="utf-8"))
        if cached.get("cache_key") == cache_key:
            timelines = [deserialize_timeline(item) for item in cached.get("timelines", [])]
            if all(timeline.screenshot_path and timeline.screenshot_path.exists() for timeline in timelines):
                print("Reusing cached browser capture...", flush=True)
                return cached_raw, timelines
    if reuse_only:
        raise SystemExit("No cached browser capture found. Run without --assemble-only first.")
    viewport = config.get("viewport", {"width": 1600, "height": 1000})
    tail = float(config.get("tail_seconds", 1.5))
    timelines: list[SceneTimeline] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--font-render-hinting=medium",
            ],
        )
        context = await browser.new_context(
            viewport=viewport,
            record_video_dir=str(video_dir),
            record_video_size=viewport,
            color_scheme="dark",
        )
        page = await context.new_page()
        recording_started = asyncio.get_running_loop().time()
        try:
            for idx, scene in enumerate(config["scenes"]):
                print(f"Scene {idx + 1}/{len(config['scenes'])}: {scene['id']}", flush=True)
                audio = scene_audio[idx]
                action_events: list[ActionEvent] = []
                scene_started_rel = relative_now(recording_started)
                scene_started = asyncio.get_running_loop().time()
                for action in scene.get("actions", []):
                    print(f"  action: {action['type']}", flush=True)
                    action_started_rel = relative_now(recording_started)
                    await perform_action(page, action, config["app_url"], owner_token)
                    action_ended_rel = relative_now(recording_started)
                    action_events.append(
                        ActionEvent(
                            type=action["type"],
                            start=action_started_rel,
                            end=action_ended_rel,
                            text=action.get("text", ""),
                            dock=action.get("dock", ""),
                        )
                    )
                elapsed = asyncio.get_running_loop().time() - scene_started
                remaining = max(0.2, audio.duration - elapsed)
                await page.wait_for_timeout(int(remaining * 1000))
                scene_ended_rel = relative_now(recording_started)
                stills_dir = work_dir / "scene_stills"
                stills_dir.mkdir(parents=True, exist_ok=True)
                still_path = stills_dir / f"{scene['id']}.png"
                if scene["id"] == "landing":
                    await page.wait_for_timeout(5000)
                await page.screenshot(path=str(still_path))
                timelines.append(
                    SceneTimeline(
                        scene_id=scene["id"],
                        start=scene_started_rel,
                        end=scene_ended_rel,
                        audio_duration=audio.duration,
                        actions=action_events,
                        screenshot_path=still_path,
                    )
                )
            await page.wait_for_timeout(int(tail * 1000))
            video = page.video
            await page.close()
            await context.close()
            video_path = await video.path()
        finally:
            await browser.close()
    final_raw = work_dir / "screen_capture.webm"
    Path(video_path).replace(final_raw)
    cache_path.write_text(
        json.dumps(
            {"cache_key": cache_key, "timelines": [serialize_timeline(timeline) for timeline in timelines]},
            indent=2,
        ),
        encoding="utf-8",
    )
    return final_raw, timelines


def create_intro_card(config: dict[str, Any], work_dir: Path) -> Path:
    viewport = config.get("viewport", {"width": 1600, "height": 1000})
    width = viewport["width"]
    height = viewport["height"]
    intro_seconds = float(config.get("lead_in_seconds", 2.5))
    font_path = DEFAULT_FONT if Path(DEFAULT_FONT).exists() else None
    intro_path = work_dir / "intro.mp4"
    intro_image = work_dir / "intro.png"

    image = Image.new("RGB", (width, height), "#08101f")
    draw = ImageDraw.Draw(image)
    title_font = ImageFont.truetype(font_path, 84) if font_path else ImageFont.load_default()
    subtitle_font = ImageFont.truetype(font_path, 36) if font_path else ImageFont.load_default()

    title = config["title"]
    subtitle = config.get("subtitle", "")
    title_box = draw.textbbox((0, 0), title, font=title_font)
    subtitle_box = draw.textbbox((0, 0), subtitle, font=subtitle_font)
    title_x = (width - (title_box[2] - title_box[0])) // 2
    title_y = (height // 2) - 110
    subtitle_x = (width - (subtitle_box[2] - subtitle_box[0])) // 2
    subtitle_y = title_y + 120

    draw.text((title_x + 3, title_y + 4), title, font=title_font, fill="#000000")
    draw.text((subtitle_x + 2, subtitle_y + 3), subtitle, font=subtitle_font, fill="#000000")
    draw.text((title_x, title_y), title, font=title_font, fill="#ffffff")
    draw.text((subtitle_x, subtitle_y), subtitle, font=subtitle_font, fill="#7dded1")
    image.save(intro_image)

    run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(intro_image),
            "-t",
            str(intro_seconds),
            "-r",
            "24",
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "superfast",
            "-crf",
            "22",
            str(intro_path),
        ]
    )
    return intro_path


def create_outro_card(config: dict[str, Any], work_dir: Path, settings: RenderSettings) -> Path:
    viewport = config.get("viewport", {"width": 1600, "height": 1000})
    width = viewport["width"]
    height = viewport["height"]
    outro_image = work_dir / "outro.png"
    outro_path = work_dir / "outro.mp4"

    image = Image.new("RGB", (width, height), "#08101f")
    draw = ImageDraw.Draw(image)
    font_path = DEFAULT_FONT if Path(DEFAULT_FONT).exists() else None
    title_font = ImageFont.truetype(font_path, 78) if font_path else ImageFont.load_default()
    subtitle_font = ImageFont.truetype(font_path, 28) if font_path else ImageFont.load_default()

    draw.rounded_rectangle((160, 300, width - 160, height - 300), radius=46, fill="#0a1220", outline="#173455", width=2)
    draw.rounded_rectangle((190, 338, 382, 368), radius=15, fill="#123859")
    draw.text((218, 339), "POST ASCEND", font=subtitle_font, fill="#7dded1")

    title = "Create faster. Publish better."
    title_box = draw.textbbox((0, 0), title, font=title_font)
    title_x = (width - (title_box[2] - title_box[0])) // 2
    draw.text((title_x + 3, height // 2 - 38), title, font=title_font, fill="#000000")
    draw.text((title_x, height // 2 - 42), title, font=title_font, fill="#ffffff")
    draw.text((width // 2 - 210, height // 2 + 56), "Creator Studio walkthrough complete", font=subtitle_font, fill="#7dded1")
    image.save(outro_image)

    run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(outro_image),
            "-t",
            "2.0",
            "-r",
            str(settings.fps),
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            settings.preset,
            "-crf",
            settings.crf,
            str(outro_path),
        ]
    )
    return outro_path


def style_scene_still(scene: dict[str, Any], screenshot_path: Path, work_dir: Path) -> Path:
    styled_dir = work_dir / "styled_stills"
    styled_dir.mkdir(parents=True, exist_ok=True)
    styled_path = styled_dir / screenshot_path.name
    if styled_path.exists() and styled_path.stat().st_mtime >= screenshot_path.stat().st_mtime:
        return styled_path

    image = Image.open(screenshot_path).convert("RGBA")
    width, height = image.size
    focus = scene.get("focus_circle")
    if not focus:
        image.convert("RGB").save(styled_path)
        return styled_path

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    if focus:
        cx = int(focus.get("x", width // 2))
        cy = int(focus.get("y", height // 2))
        radius = int(focus.get("r", 36))
        glow = Image.new("RGBA", image.size, (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse((cx - radius * 2, cy - radius * 2, cx + radius * 2, cy + radius * 2), fill=(45, 212, 191, 70))
        glow = glow.filter(ImageFilter.GaussianBlur(22))
        overlay = Image.alpha_composite(overlay, glow)
        draw = ImageDraw.Draw(overlay)
        draw.ellipse((cx - radius, cy - radius, cx + radius, cy + radius), outline=(45, 212, 191, 255), width=4)
        draw.ellipse((cx - radius // 2, cy - radius // 2, cx + radius // 2, cy + radius // 2), outline=(255, 255, 255, 210), width=2)

    composed = Image.alpha_composite(image, overlay)
    composed.save(styled_path)
    return styled_path


def normalize_recording(raw_video_path: Path, work_dir: Path, settings: RenderSettings) -> Path:
    normalized = work_dir / "screen_capture.mp4"
    if normalized.exists() and normalized.stat().st_mtime >= raw_video_path.stat().st_mtime:
        return normalized
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(raw_video_path),
            "-c:v",
            "libx264",
            "-preset",
            settings.preset,
            "-crf",
            settings.crf,
            "-r",
            str(settings.fps),
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(normalized),
        ]
    )
    return normalized


def find_action_event(timeline: SceneTimeline, matcher: dict[str, Any]) -> ActionEvent | None:
    kind = matcher.get("type", "")
    text = matcher.get("text", "")
    dock = matcher.get("dock", "")
    for event in timeline.actions:
        if kind and event.type != kind:
            continue
        if text and event.text != text:
            continue
        if dock and event.dock != dock:
            continue
        return event
    return None


def clamp_window(start: float, end: float, minimum: float = 0.2) -> tuple[float, float]:
    if end - start >= minimum:
        return start, end
    return start, start + minimum


def scene_segments(scene: dict[str, Any], timeline: SceneTimeline) -> list[tuple[float, float]]:
    edit = scene.get("edit", {})
    if not edit:
        return [clamp_window(timeline.start, timeline.end)]

    default_start = timeline.start
    if edit.get("start_on"):
        anchor = find_action_event(timeline, edit["start_on"])
        if anchor:
            default_start = max(timeline.start, anchor.end - float(edit.get("pre_seconds", 0.25)))

    if edit.get("jump_after") and edit.get("resume_on"):
        trigger = find_action_event(timeline, edit["jump_after"])
        resume = find_action_event(timeline, edit["resume_on"])
        if trigger and resume and resume.end > trigger.end:
            show_loading = float(edit.get("show_loading_seconds", 0.8))
            post_ready = float(edit.get("post_ready_seconds", 1.0))
            pre_resume = float(edit.get("pre_resume_seconds", 0.25))
            first = clamp_window(default_start, min(trigger.end + show_loading, resume.start))
            second_start = max(trigger.end + show_loading, resume.end - pre_resume)
            second = clamp_window(second_start, min(timeline.end, resume.end + post_ready))
            return [first, second]

    end_at = timeline.end
    if edit.get("end_on"):
        anchor = find_action_event(timeline, edit["end_on"])
        if anchor:
            end_at = min(timeline.end, anchor.end + float(edit.get("post_seconds", 1.0)))
    return [clamp_window(default_start, end_at)]


def build_scene_clip(
    normalized_video_path: Path,
    scene: dict[str, Any],
    timeline: SceneTimeline,
    work_dir: Path,
    settings: RenderSettings,
) -> Path:
    scene_dir = work_dir / "edited_scenes"
    scene_dir.mkdir(parents=True, exist_ok=True)
    if scene.get("edit", {}).get("use_screenshot") and timeline.screenshot_path:
        styled_still = style_scene_still(scene, timeline.screenshot_path, work_dir)
        screenshot_clip = scene_dir / f"{timeline.scene_id}_still.mp4"
        frames = max(1, int(round(timeline.audio_duration * settings.fps)))
        motion = scene.get("motion", {})
        motion_enabled = bool(motion.get("enabled", False))
        if motion_enabled:
            zoom_end = float(motion.get("zoom_end", settings.still_zoom_end))
            zoom_step = float(motion.get("zoom_step", settings.still_zoom_step))
            vf = (
                f"zoompan=z='min(zoom+{zoom_step:.6f},{zoom_end:.3f})':"
                f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
                f"d={frames}:s=1600x1000:fps={settings.fps},"
                "fade=t=in:st=0:d=0.35,fade=t=out:st="
                f"{max(0, timeline.audio_duration - 0.4):.2f}:d=0.35"
            )
        else:
            vf = (
                f"scale=1600:1000:flags=lanczos,fps={settings.fps},"
                "fade=t=in:st=0:d=0.20,fade=t=out:st="
                f"{max(0, timeline.audio_duration - 0.25):.2f}:d=0.20"
            )
        run(
            [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-i",
                str(styled_still),
                "-vf",
                vf,
                "-t",
                f"{timeline.audio_duration:.3f}",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                settings.preset,
                "-crf",
                settings.crf,
                "-pix_fmt",
                "yuv420p",
                str(screenshot_clip),
            ]
        )
        return screenshot_clip
    segments = scene_segments(scene, timeline)
    segment_paths: list[Path] = []

    for idx, (start, end) in enumerate(segments):
        segment_path = scene_dir / f"{timeline.scene_id}_segment_{idx + 1}.mp4"
        run(
            [
                "ffmpeg",
                "-y",
                "-ss",
                f"{start:.3f}",
                "-to",
                f"{end:.3f}",
                "-i",
                str(normalized_video_path),
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                settings.preset,
                "-crf",
                settings.crf,
                "-r",
                str(settings.fps),
                "-pix_fmt",
                "yuv420p",
                str(segment_path),
            ]
        )
        segment_paths.append(segment_path)

    if len(segment_paths) == 1:
        stitched_scene = segment_paths[0]
    else:
        concat_path = scene_dir / f"{timeline.scene_id}_segments.txt"
        concat_path.write_text(
            "\n".join([f"file '{path.name}'" for path in segment_paths]),
            encoding="utf-8",
        )
        stitched_scene = scene_dir / f"{timeline.scene_id}_stitched.mp4"
        run(
            [
                "ffmpeg",
                "-y",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(concat_path),
                "-c",
                "copy",
                str(stitched_scene),
            ],
            cwd=scene_dir,
        )

    current_duration = ffprobe_duration(stitched_scene)
    final_scene = scene_dir / f"{timeline.scene_id}_final.mp4"
    if current_duration < timeline.audio_duration:
        pad_amount = timeline.audio_duration - current_duration
        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(stitched_scene),
                "-vf",
                f"tpad=stop_mode=clone:stop_duration={pad_amount:.3f}",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                settings.preset,
                "-crf",
                settings.crf,
                "-r",
                str(settings.fps),
                "-pix_fmt",
                "yuv420p",
                str(final_scene),
            ]
        )
        return final_scene

    if current_duration > timeline.audio_duration + 0.05:
        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(stitched_scene),
                "-t",
                f"{timeline.audio_duration:.3f}",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                settings.preset,
                "-crf",
                settings.crf,
                "-r",
                str(settings.fps),
                "-pix_fmt",
                "yuv420p",
                str(final_scene),
            ]
        )
        return final_scene

    return stitched_scene


def build_edited_video(
    config: dict[str, Any],
    normalized_video_path: Path,
    timelines: list[SceneTimeline],
    work_dir: Path,
    settings: RenderSettings,
) -> Path:
    scene_lookup = {scene["id"]: scene for scene in config["scenes"]}
    scene_clips = [
        build_scene_clip(normalized_video_path, scene_lookup[timeline.scene_id], timeline, work_dir, settings)
        for timeline in timelines
    ]
    concat_txt = work_dir / "edited_video_concat.txt"
    concat_txt.write_text(
        "\n".join([f"file '{clip.resolve()}'" for clip in scene_clips]),
        encoding="utf-8",
    )
    edited_path = work_dir / "edited_screen_capture.mp4"
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_txt),
            "-c",
            "copy",
            str(edited_path),
        ]
    )
    return edited_path


def concat_video_and_audio(
    config: dict[str, Any],
    work_dir: Path,
    intro_path: Path,
    outro_path: Path,
    raw_video_path: Path,
    narration_path: Path,
    srt_path: Path,
    timelines: list[SceneTimeline],
    settings: RenderSettings,
) -> tuple[Path, Path]:
    normalized_video_path = normalize_recording(raw_video_path, work_dir, settings)
    edited_video_path = build_edited_video(config, normalized_video_path, timelines, work_dir, settings)
    concat_txt = work_dir / "video_concat.txt"
    concat_txt.write_text(
        f"file '{intro_path.name}'\nfile '{edited_video_path.name}'\nfile '{outro_path.name}'\n",
        encoding="utf-8",
    )
    stitched = work_dir / "stitched.mp4"
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_txt),
            "-c",
            "copy",
            str(stitched),
        ],
        cwd=work_dir,
    )
    lead_in = float(config.get("lead_in_seconds", 2.5))
    tail_outro = 2.0
    intro_silence = work_dir / "intro_silence.mp3"
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=24000:cl=mono",
            "-t",
            str(lead_in),
            "-q:a",
            "9",
            "-acodec",
            "libmp3lame",
            str(intro_silence),
        ]
    )
    outro_silence = work_dir / "outro_silence.mp3"
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=24000:cl=mono",
            "-t",
            str(tail_outro),
            "-q:a",
            "9",
            "-acodec",
            "libmp3lame",
            str(outro_silence),
        ]
    )
    audio_concat = work_dir / "audio_with_intro.txt"
    audio_concat.write_text(
        f"file '{intro_silence.name}'\nfile '{narration_path.name}'\nfile '{outro_silence.name}'\n",
        encoding="utf-8",
    )
    audio_track = work_dir / "full_audio.mp3"
    run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(audio_concat),
            "-c",
            "copy",
            str(audio_track),
        ],
        cwd=work_dir,
    )

    output_dir = ROOT / "tutorials" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / f"{config['output_name']}.mp4"
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(stitched),
            "-i",
            str(audio_track),
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "libx264",
            "-preset",
            settings.preset,
            "-crf",
            settings.crf,
            "-r",
            str(settings.fps),
            "-c:a",
            "aac",
            "-b:a",
            settings.audio_bitrate,
            "-shortest",
            str(final_path),
        ]
    )
    final_srt = output_dir / f"{config['output_name']}.srt"
    final_srt.write_text(srt_path.read_text(encoding="utf-8"), encoding="utf-8")
    return final_path, final_srt


async def main() -> None:
    parser = argparse.ArgumentParser(description="Render a narrated Post Ascend tutorial video.")
    parser.add_argument("config", help="Path to tutorial JSON config.")
    parser.add_argument("--owner-password", default=os.environ.get("POST_ASCEND_OWNER_PASSWORD", ""))
    parser.add_argument("--owner-token", default=os.environ.get("POST_ASCEND_OWNER_TOKEN", ""))
    parser.add_argument("--draft", action="store_true", help="Use faster, lower-quality encoding for iteration.")
    parser.add_argument("--force-record", action="store_true", help="Ignore cached browser capture and record again.")
    parser.add_argument("--assemble-only", action="store_true", help="Skip browser capture and require a cached capture.")
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = json.loads(config_path.read_text(encoding="utf-8"))
    owner_token = ensure_owner_token(args.owner_password, args.owner_token)
    settings = render_settings(args.draft)

    work_dir = TMP_ROOT / config["output_name"]
    work_dir.mkdir(parents=True, exist_ok=True)

    print("Generating narration...")
    scene_audio, narration_path, srt_path = await build_audio_tracks(config, work_dir)

    print("Recording browser walkthrough...")
    raw_video_path, timelines = await record_tutorial(
        config, owner_token, work_dir, scene_audio, force_record=args.force_record, reuse_only=args.assemble_only
    )

    print("Building intro card...")
    intro_path = create_intro_card(config, work_dir)
    outro_path = create_outro_card(config, work_dir, settings)

    print("Assembling final video...")
    final_path, srt_output = concat_video_and_audio(
        config, work_dir, intro_path, outro_path, raw_video_path, narration_path, srt_path, timelines, settings
    )

    print(f"Tutorial ready: {final_path}")
    print(f"Captions ready: {srt_output}")


if __name__ == "__main__":
    asyncio.run(main())
