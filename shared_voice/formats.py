"""
Canonical format guide definitions for Tyler Polumbus content tools.

Source of truth for character limits, icons, and structural rules
used by both Mount Polumbus HQ and Post Ascend Gameday.
"""
from __future__ import annotations

FORMAT_GUIDES: dict[str, dict] = {
    "Punchy Tweet": {
        "chars": "<= 160 chars",
        "icon": "⚡",
        "rules": [
            "2 sentences only",
            "Take + engagement hook",
            "No hashtags, no ellipsis",
            "Every word earns its place",
        ],
    },
    "Normal Tweet": {
        "chars": "161 - 260 chars",
        "icon": "✦",
        "rules": [
            "Hook + line break + payoff",
            "Question OR ellipsis (not both)",
            "Stop the scroll in 8 words",
            "No links, no hashtags",
        ],
    },
    "Long Tweet": {
        "chars": "280 - 1200 chars",
        "icon": "◈",
        "rules": [
            "First 280 must work standalone",
            "Short paras + line breaks",
            "Comparison lists hit hard",
            "End with debate invite",
        ],
    },
    "Thread": {
        "chars": "5 - 8 tweets",
        "icon": "≡",
        "rules": [
            "Each tweet stands alone",
            "Tweet 1 = scroll stopper",
            "Tweet 7+ = replies CTA",
            "One stat-heavy tweet minimum",
        ],
    },
    "Article": {
        "chars": "1500 - 2000 words",
        "icon": "▣",
        "rules": [
            "Hero image REQUIRED",
            "Subheadings every 300 words",
            "Bold 2-3 key stats/section",
            "End with discussion question",
        ],
    },
}

FORMAT_KEYS: dict[str, str] = {
    "punchy": "Punchy Tweet",
    "normal": "Normal Tweet",
    "long": "Long Tweet",
    "thread": "Thread",
    "article": "Article",
}


def get_format(key: str) -> dict:
    """Return a format guide dict by lowercase key. Raises KeyError if unknown."""
    display_name = FORMAT_KEYS[key]
    return FORMAT_GUIDES[display_name]


def format_rules_text(key: str) -> str:
    """Return a human-readable rules block for injection into prompts."""
    fmt = get_format(key)
    display_name = FORMAT_KEYS[key]
    lines = [f"Format: {display_name} ({fmt['chars']})"]
    for rule in fmt["rules"]:
        lines.append(f"- {rule}")
    return "\n".join(lines)
