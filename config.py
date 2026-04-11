"""Pure constants — no Streamlit imports allowed here."""

import os

from shared_voice import (
    FORMAT_GUIDES,
    TYLER_CONTEXT,
    VOICE_LABELS,
    WHATS_HOT_VOICE_GUIDE,
    CRITICAL_EXAMPLES,
    HOMER_EXAMPLES,
    SARCASTIC_EXAMPLES,
    VOICE_BLOCKS,
)

TYLER_HANDLE = "tyler_polumbus"
GAMEDAY_URL = os.getenv("POSTASCEND_GAMEDAY_URL", "https://live-gameday.postascend.io")

AMPLIFIER_AVATAR_URL = "https://raw.githubusercontent.com/polumbus/mount-polumbus-hq/master/static/amplifier.jpg"
AMPLIFIER_IMG = f'<img src="{AMPLIFIER_AVATAR_URL}" style="width:20px;height:20px;border-radius:50%;vertical-align:middle;margin-right:4px;">'

# Re-export under original private names so existing HQ code works unchanged
_VOICE_LABELS = VOICE_LABELS
_FORMAT_GUIDES = FORMAT_GUIDES
_WHATS_HOT_VOICE_GUIDE = WHATS_HOT_VOICE_GUIDE
