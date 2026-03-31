import json
import time
from pathlib import Path

STATE_FILE = Path("/tmp/mount_polumbus_anthropic_state.json")
DEFAULT_RATE_LIMIT_COOLDOWN = 60
DEFAULT_UNAVAILABLE_COOLDOWN = 300
PROBE_INTERVAL = 15


def _default_state():
    return {
        "blocked_until": 0.0,
        "last_probe_at": 0.0,
        "last_error": "",
        "source": "",
        "last_success_at": 0.0,
    }


def _load_state():
    if not STATE_FILE.exists():
        return _default_state()
    try:
        return {**_default_state(), **json.loads(STATE_FILE.read_text())}
    except Exception:
        return _default_state()


def _save_state(state):
    try:
        STATE_FILE.write_text(json.dumps(state))
    except Exception:
        pass


def get_state():
    return _load_state()


def is_blocked(now=None):
    now = now or time.time()
    state = _load_state()
    return state["blocked_until"] > now


def block_for(seconds, source="", error=""):
    state = _load_state()
    until = time.time() + max(1, int(seconds))
    state["blocked_until"] = max(state["blocked_until"], until)
    state["source"] = source
    state["last_error"] = error
    _save_state(state)


def mark_rate_limited(retry_after=None, source="", error=""):
    cooldown = retry_after if retry_after is not None else DEFAULT_RATE_LIMIT_COOLDOWN
    block_for(cooldown, source=source, error=error)


def mark_available(source=""):
    state = _load_state()
    state["blocked_until"] = 0.0
    state["last_probe_at"] = 0.0
    state["last_error"] = ""
    state["source"] = source
    state["last_success_at"] = time.time()
    _save_state(state)


def should_probe(now=None):
    now = now or time.time()
    state = _load_state()
    if state["blocked_until"] > now:
        return False
    return state["last_probe_at"] + PROBE_INTERVAL <= now


def mark_probe_attempt():
    state = _load_state()
    state["last_probe_at"] = time.time()
    _save_state(state)


def parse_retry_after(headers):
    if not headers:
        return None
    value = headers.get("Retry-After")
    if not value:
        return None
    try:
        return max(1, int(float(value)))
    except Exception:
        return None
