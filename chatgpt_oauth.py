import base64
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

CODEX_AUTH_FILE = Path.home() / ".codex" / "auth.json"
CODEX_RESPONSES_URL = "https://chatgpt.com/backend-api/codex/responses"
CODEX_FALLBACK_MODELS = ["gpt-5.1-codex-mini", "gpt-5.2"]


def _decode_jwt_payload(token: str):
    parts = token.split(".")
    if len(parts) < 2:
        return None
    payload_b64 = parts[1]
    pad = "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(payload_b64 + pad).decode("utf-8"))


def _token_expired(token: str, leeway_seconds: int = 60) -> bool:
    payload = _decode_jwt_payload(token)
    if not payload:
        return False
    exp = payload.get("exp")
    if not exp:
        return False
    return exp <= (time.time() + leeway_seconds)


def _load_codex_auth():
    if not CODEX_AUTH_FILE.exists():
        return {}
    with open(CODEX_AUTH_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _get_codex_access_token():
    auth = _load_codex_auth()
    token = None
    if isinstance(auth, dict):
        tokens = auth.get("tokens") or {}
        if isinstance(tokens, dict):
            token = tokens.get("access_token")
        if not token:
            token = auth.get("access_token")
    if not token:
        raise Exception(f"No Codex token in {CODEX_AUTH_FILE}")
    if _token_expired(token):
        raise Exception("Codex token is expired")
    return token


def _extract_chatgpt_account_id(access_token: str):
    payload = _decode_jwt_payload(access_token)
    if not payload:
        return None
    auth_claim = payload.get("https://api.openai.com/auth", {})
    if isinstance(auth_claim, dict):
        return auth_claim.get("chatgpt_account_id")
    return None


def _parse_sse_chunk(chunk: str):
    data_lines = []
    for line in chunk.split("\n"):
        if line.startswith("data:"):
            data_lines.append(line[5:].strip())
    if not data_lines:
        return None
    data = "\n".join(data_lines).strip()
    if not data or data == "[DONE]":
        return None
    return json.loads(data)


def _parse_sse_stream(raw: str):
    events = []
    buffer = ""
    for chunk in raw.splitlines(keepends=True):
        buffer += chunk
        while "\n\n" in buffer:
            event_chunk, buffer = buffer.split("\n\n", 1)
            event = _parse_sse_chunk(event_chunk)
            if event is not None:
                events.append(event)
    if buffer.strip():
        event = _parse_sse_chunk(buffer)
        if event is not None:
            events.append(event)
    return events


def _extract_output_text(response: dict) -> str:
    for item in response.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                return content["text"].strip()
    return ""


def _parse_codex_response_text(raw: str) -> str:
    events = _parse_sse_stream(raw)
    for evt in reversed(events):
        if evt.get("type") == "response.completed" and isinstance(evt.get("response"), dict):
            text = _extract_output_text(evt["response"])
            if text:
                return text
    output_text = ""
    for evt in events:
        delta = evt.get("delta")
        if isinstance(delta, str):
            output_text += delta
        text = evt.get("text")
        if isinstance(text, str):
            output_text += text
    return output_text.strip()


def call_chatgpt_oauth(prompt: str, system: str = "", model: str = None, timeout: int = 90) -> str:
    token = _get_codex_access_token()
    account_id = _extract_chatgpt_account_id(token)
    if not account_id:
        raise Exception("Missing chatgpt_account_id in Codex token")

    models = [model] if model else []
    models.extend(m for m in CODEX_FALLBACK_MODELS if m not in models)
    last_error = None

    for current_model in models:
        body = {
            "model": current_model,
            "stream": True,
            "store": False,
            "instructions": system or "",
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                }
            ],
        }
        req = urllib.request.Request(
            CODEX_RESPONSES_URL,
            data=json.dumps(body).encode(),
            headers={
                "Authorization": f"Bearer {token}",
                "chatgpt-account-id": account_id,
                "OpenAI-Beta": "responses=experimental",
                "originator": "pi",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
            text = _parse_codex_response_text(raw)
            if text:
                return text
            last_error = Exception(f"empty ChatGPT response on {current_model}")
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace")
            last_error = Exception(f"HTTP {e.code}: {body_text[:400]}")
            if e.code in (400, 403, 404, 429):
                continue
            raise last_error
        except Exception as e:
            last_error = e

    if last_error:
        raise last_error
    raise Exception("No ChatGPT fallback models available")
