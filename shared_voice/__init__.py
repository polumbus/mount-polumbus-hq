"""
Shared voice and format definitions for Tyler Polumbus content tools.

This package is the single source of truth for voice configurations,
format guides, and Tyler's identity context. Both Mount Polumbus HQ
and Post Ascend Gameday import from here.
"""
from shared_voice.formats import (
    FORMAT_GUIDES,
    FORMAT_KEYS,
    format_rules_text,
    get_format,
)
from shared_voice.voices import (
    BANNED_OPENERS,
    BANNED_WORDS,
    CRITICAL_EXAMPLES,
    DEFAULT_VOICE_DESCRIPTION,
    HOMER_EXAMPLES,
    SARCASTIC_EXAMPLES,
    TYLER_CONTEXT,
    VOICE_BLOCKS,
    VOICE_KEYS,
    VOICE_LABELS,
    WHATS_HOT_VOICE_GUIDE,
    get_voice_instructions,
)

__all__ = [
    "BANNED_OPENERS",
    "BANNED_WORDS",
    "CRITICAL_EXAMPLES",
    "DEFAULT_VOICE_DESCRIPTION",
    "FORMAT_GUIDES",
    "FORMAT_KEYS",
    "HOMER_EXAMPLES",
    "SARCASTIC_EXAMPLES",
    "TYLER_CONTEXT",
    "VOICE_BLOCKS",
    "VOICE_KEYS",
    "VOICE_LABELS",
    "WHATS_HOT_VOICE_GUIDE",
    "format_rules_text",
    "get_format",
    "get_voice_instructions",
]
