import json
import os
import subprocess
import sys
from pathlib import Path


COMMAND = Path("/home/polfam/.openclaw/workspace-omaha/scripts/creator_evolution_pulse_command.py")


def _run_command(content: str, tmp_path: Path, mock: str = ""):
    proc = subprocess.run(
        [
            sys.executable,
            str(COMMAND),
            "--content",
            content,
            "--request-id",
            "pulse_cmd_contract",
            "--channel-id",
            "dry-run",
            "--dry-run",
            *([] if not mock else ["--mock", mock]),
        ],
        text=True,
        capture_output=True,
        timeout=45,
        cwd="/home/polfam/.openclaw/workspace-omaha",
        env={**os.environ, "PYTHONPATH": "/home/polfam/mount_polumbus_hq", "PULSE_ARTIFACT_DIR": str(tmp_path)},
    )
    return proc


def test_discord_pulse_core_commands_are_routed(tmp_path):
    ready = _run_command("pulse", tmp_path, mock="ready")
    assert ready.returncode == 0, ready.stderr
    payload = json.loads(ready.stdout)
    assert payload["status"] == "ready"
    assert "Pulse quick codes" in "\n".join(payload["messages"])

    why = _run_command("pulse why", tmp_path)
    assert why.returncode == 0, why.stderr
    assert "Source basis" in "\n".join(json.loads(why.stdout)["messages"])

    source = _run_command("pulse source", tmp_path)
    assert source.returncode == 0, source.stderr
    assert "Exact source basis" in "\n".join(json.loads(source.stdout)["messages"])

    voice = _run_command("voice", tmp_path)
    assert voice.returncode == 0, voice.stderr
    assert "voice 1" in "\n".join(json.loads(voice.stdout)["messages"])

    fmt = _run_command("format", tmp_path)
    assert fmt.returncode == 0, fmt.stderr
    assert "format 1" in "\n".join(json.loads(fmt.stdout)["messages"])
