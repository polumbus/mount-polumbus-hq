#!/usr/bin/env python3
"""Browser-driven Creator Evolution quality harness.

This intentionally drives the real Streamlit page with Playwright instead of
calling generation helpers directly. It is a regression harness for user-facing
Creator Evolution failures such as all drafts being rejected for repairable
format mistakes.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import creator_evolution as ce  # noqa: E402


DEFAULT_URL = "http://127.0.0.1:8501/?token=b2e6b5b6a8c2e1f6&user=owner&page=Creator+Evolution"
FORMATS = ["Punchy Tweet", "Normal Tweet", "Long Tweet", "Thread", "Article"]
FORMAT_BUTTON = {
    "Punchy Tweet": "Punchy",
    "Normal Tweet": "Normal",
    "Long Tweet": "Long",
    "Thread": "Thread",
    "Article": "Article",
}
SEEDS = [
    (
        "The Broncos keep saying the roster is deeper, but training camp will show if that is real depth "
        "or just more average players fighting for the same spots."
    ),
    (
        "The Avs keep acting like the goalie situation is settled, but the next tough start will show "
        "whether they actually believe that or are just hoping it settles itself."
    ),
    (
        "The Nuggets say everything is on the table this summer, but the non-Jokic minutes are still "
        "the part that keeps wrecking games."
    ),
]
ADVERSARIAL_SEEDS = [
    (
        "Make this a normal tweet with three stacked punchy beats and one final line by itself: "
        "the Broncos keep calling this competition, but the depth chart is about to tell us who they actually trust."
    ),
    (
        "Write this as a sharp tweet and end with what else are we supposed to call that? "
        "The Avs keep changing the goalie conversation every time it finally gets quiet."
    ),
    (
        "Call out the people responsible without holding back, but keep it postable: "
        "the Nuggets say everything is on the table while the same non-Jokic minutes keep wrecking games."
    ),
]
FAILURE_PATTERNS = [
    "Creator Evolution rejected every generated draft",
    "AI unavailable",
    "quality/safety",
    "Blocking reason:",
    "Traceback",
    "Exception",
    "No XAI_API_KEY",
    "No OPENAI_API_KEY",
]


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")


def _parse_csv(value: str, allowed: list[str]) -> list[str]:
    if not value or value.lower() == "all":
        return list(allowed)
    by_lower = {item.lower(): item for item in allowed}
    parsed: list[str] = []
    for raw in value.split(","):
        key = raw.strip().lower()
        if not key:
            continue
        if key not in by_lower:
            raise SystemExit(f"Unknown value {raw!r}. Allowed: {', '.join(allowed)}")
        parsed.append(by_lower[key])
    return parsed


def _click_text(page, text: str, *, timeout: int = 5000) -> None:
    locator = page.get_by_text(text, exact=True).last
    try:
        locator.click(timeout=timeout)
    except PlaywrightTimeoutError:
        locator.click(timeout=timeout, force=True)


def _select_format(page, fmt: str) -> None:
    _click_text(page, FORMAT_BUTTON[fmt], timeout=5000)
    page.wait_for_timeout(500)


def _select_voice(page, voice: str) -> None:
    combo = page.locator('[role="combobox"]').first
    current = combo.get_attribute("aria-label") or ""
    if f"Selected {voice}." in current:
        return
    try:
        combo.click(timeout=5000)
    except PlaywrightTimeoutError:
        combo.click(timeout=5000, force=True)
    page.wait_for_timeout(400)
    try:
        _click_text(page, voice, timeout=5000)
    except Exception:
        combo.fill(voice, timeout=5000)
        page.wait_for_timeout(300)
        page.keyboard.press("Enter")
    page.wait_for_timeout(500)


def _fill_concept(page, concept: str) -> None:
    area = page.locator("textarea").first
    area.fill(concept, timeout=5000)
    page.wait_for_timeout(300)


def _click_evolve(page) -> None:
    _click_text(page, "EVOLVE", timeout=5000)


def _body_text(page) -> str:
    return page.locator("body").inner_text(timeout=10000)


def _generated_option_count(page) -> int:
    return page.locator('textarea[aria-label="Generated option"]').count()


def _generated_option_preview(page) -> str:
    values: list[str] = []
    loc = page.locator('textarea[aria-label="Generated option"]')
    for idx in range(min(loc.count(), 3)):
        try:
            value = loc.nth(idx).input_value(timeout=1000).strip()
            if value:
                values.append(f"OPTION {idx + 1}\n{value}")
        except Exception:
            continue
    return "\n\n".join(values)


def _extract_result_text(body: str) -> str:
    marker = "\nCreator Evolution\n"
    if marker in body:
        body = body.rsplit(marker, 1)[-1]
    footer = "\nCREATE\nCreator Studio"
    if footer in body:
        body = body.split(footer, 1)[0]
    return body.strip()


def _failure_hits(text: str) -> list[str]:
    lower = text.lower()
    return [pattern for pattern in FAILURE_PATTERNS if pattern.lower() in lower]


def _run_case(page, *, fmt: str, voice: str, concept: str, seed_index: int, timeout_ms: int, screenshot_dir: Path) -> dict:
    start = time.monotonic()
    page.evaluate("window.scrollTo(0, 0)")
    page.wait_for_timeout(400)
    before = _body_text(page)
    before_preview = _generated_option_preview(page)
    _select_format(page, fmt)
    _select_voice(page, voice)
    _fill_concept(page, concept)
    _click_evolve(page)

    status = "timeout"
    body = ""
    for _ in range(max(1, timeout_ms // 1000)):
        page.wait_for_timeout(1000)
        body = _body_text(page)
        current_preview = _generated_option_preview(page)
        current_count = _generated_option_count(page)
        if _failure_hits(body) or (
            body != before
            and current_preview
            and current_preview != before_preview
            and current_count >= 3
        ) or (body != before and len(re.findall(r"\bOPTION\s+[123]\b", body)) >= 3):
            status = "ok"
            break

    elapsed = round(time.monotonic() - start, 2)
    generated_preview = _generated_option_preview(page)
    result_text = generated_preview or _extract_result_text(body)
    hits = _failure_hits(result_text or body)
    option_count = max(_generated_option_count(page), len(re.findall(r"\bOPTION\s+[123]\b", result_text)))
    if status == "ok" and (hits or option_count < 3):
        status = "failed"
    elif status == "ok":
        status = "passed"

    screenshot_path = ""
    if status != "passed":
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = str(screenshot_dir / f"{_slug(voice)}-{_slug(fmt)}-seed{seed_index}.png")
        page.screenshot(path=screenshot_path, full_page=True)

    return {
        "format": fmt,
        "voice": voice,
        "seed_index": seed_index,
        "concept": concept,
        "status": status,
        "elapsed_seconds": elapsed,
        "option_count": option_count,
        "failure_hits": hits,
        "preview": result_text[:2000],
        "screenshot": screenshot_path,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--voices", default="all")
    parser.add_argument("--formats", default="all")
    parser.add_argument("--max-cases", type=int, default=0, help="Optional smoke-run limit.")
    parser.add_argument("--seed-mode", choices=["default", "adversarial"], default="default")
    parser.add_argument("--start-at", type=int, default=1, help="1-based case index for resuming a long run.")
    parser.add_argument("--timeout-ms", type=int, default=90000)
    parser.add_argument("--headful", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    voices = _parse_csv(args.voices, list(ce.EMOTION_LANES))
    formats = _parse_csv(args.formats, FORMATS)
    seeds = ADVERSARIAL_SEEDS if args.seed_mode == "adversarial" else SEEDS
    cases = [
        (fmt, voice, seed_index, concept)
        for fmt in formats
        for voice in voices
        for seed_index, concept in enumerate(seeds, 1)
    ]
    if args.start_at > 1:
        cases = cases[args.start_at - 1 :]
    if args.max_cases:
        cases = cases[: args.max_cases]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = Path(args.output) if args.output else ROOT / "state" / "creator_evolution" / f"browser_quality_harness_{timestamp}.json"
    screenshot_dir = out_path.with_suffix("").parent / f"{out_path.with_suffix('').name}_screenshots"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=not args.headful)
        page = browser.new_page(viewport={"width": 1400, "height": 1200})
        page.goto(args.url, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        if "Creator Evolution" not in _body_text(page):
            raise SystemExit("Creator Evolution page did not load.")

        total = len(cases)
        for idx, (fmt, voice, seed_index, concept) in enumerate(cases, 1):
            print(f"[{idx}/{total}] {fmt} | {voice} | seed {seed_index}", flush=True)
            result = _run_case(
                page,
                fmt=fmt,
                voice=voice,
                concept=concept,
                seed_index=seed_index,
                timeout_ms=args.timeout_ms,
                screenshot_dir=screenshot_dir,
            )
            print(f"  -> {result['status']} options={result['option_count']} failures={result['failure_hits']}", flush=True)
            results.append(result)
            out_path.write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")

        browser.close()

    failed = [item for item in results if item["status"] != "passed"]
    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "url": args.url,
        "case_count": len(results),
        "passed": len(results) - len(failed),
        "failed": len(failed),
        "failures": failed,
        "results": results,
    }
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Report: {out_path}")
    print(f"Passed: {summary['passed']} / {summary['case_count']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
