"""Pure constants — no Streamlit imports allowed here."""

import os

from shared_voice import (
    DEFAULT_TWEET_FORMAT,
    DEFAULT_TWEET_VOICE,
    FORMAT_GUIDES,
    FORMAT_ORDER,
    TYLER_CONTEXT,
    VOICE_LABELS,
    WHATS_HOT_VOICE_GUIDE,
    CRITICAL_EXAMPLES,
    HOMER_EXAMPLES,
    SARCASTIC_EXAMPLES,
    VOICE_BLOCKS,
)

TYLER_HANDLE = "tyler_polumbus"
GAMEDAY_URL = "https://gameday-open.postascend.io"

AMPLIFIER_AVATAR_URL = "https://raw.githubusercontent.com/polumbus/mount-polumbus-hq/master/static/amplifier.jpg"
AMPLIFIER_IMG = f'<img src="{AMPLIFIER_AVATAR_URL}" style="width:20px;height:20px;border-radius:50%;vertical-align:middle;margin-right:4px;">'

# Re-export under original private names so existing HQ code works unchanged
_VOICE_LABELS = VOICE_LABELS
_FORMAT_GUIDES = FORMAT_GUIDES
_WHATS_HOT_VOICE_GUIDE = WHATS_HOT_VOICE_GUIDE
_DEFAULT_TWEET_FORMAT = DEFAULT_TWEET_FORMAT
_DEFAULT_TWEET_VOICE = DEFAULT_TWEET_VOICE
_FORMAT_ORDER = FORMAT_ORDER
