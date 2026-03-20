#!/bin/bash
# HQ Watchdog — keeps proxy + tunnel alive, syncs URL + OAuth token to Gist
# Cron: * * * * * bash /home/polfam/mount_polumbus_hq/hq_watchdog.sh >> /tmp/hq_watchdog.log 2>&1

source /home/polfam/mount_polumbus_hq/.env.local 2>/dev/null
GIST_ID="15fb167bbbfdaa79d5ce11c266c3f652"
PROXY_PORT=7821
TUNNEL_LOG="/tmp/hq_tunnel.log"
URL_FILE="/tmp/hq_tunnel_url"

# --- 0. Keep OAuth token fresh in Gist (runs every minute, refreshes when <60 min left) ---
HQ_GITHUB_PAT="$HQ_GITHUB_PAT" /usr/bin/python3 - <<'PYEOF'
import json, urllib.request, urllib.parse, os, time

GIST_ID = "15fb167bbbfdaa79d5ce11c266c3f652"
GITHUB_PAT = os.environ.get("HQ_GITHUB_PAT", "")
CREDS_PATH = os.path.expanduser("~/.claude/.credentials.json")
OAUTH_TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"

if not GITHUB_PAT:
    raise SystemExit("No GITHUB_PAT")

with open(CREDS_PATH) as f:
    creds = json.load(f)["claudeAiOauth"]

access_token  = creds["accessToken"]
refresh_token = creds["refreshToken"]
expires_at_ms = creds["expiresAt"]  # milliseconds

# Refresh if less than 60 minutes remaining
if time.time() * 1000 > expires_at_ms - 3_600_000:
    print(f"[token] Refreshing (expires in <60 min)...")
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
    }).encode()
    req = urllib.request.Request(OAUTH_TOKEN_URL, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "User-Agent": "claude-code/2.1.78"}, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        tok = json.loads(r.read())
    access_token  = tok["access_token"]
    refresh_token = tok.get("refresh_token", refresh_token)
    expires_at_ms = int((time.time() + tok["expires_in"]) * 1000)

    # Save back to local credentials
    with open(CREDS_PATH) as f:
        full_creds = json.load(f)
    full_creds["claudeAiOauth"]["accessToken"]  = access_token
    full_creds["claudeAiOauth"]["refreshToken"] = refresh_token
    full_creds["claudeAiOauth"]["expiresAt"]    = expires_at_ms
    with open(CREDS_PATH, "w") as f:
        json.dump(full_creds, f, indent=2)
    print(f"[token] Refreshed. New expiry: {expires_at_ms}")

# Always push current token to Gist so Streamlit Cloud has it
token_data = json.dumps({
    "access_token": access_token,
    "refresh_token": refresh_token,
    "expires_at": expires_at_ms,
    "synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
}, indent=2).encode()

patch_body = json.dumps({"files": {"hq_token.json": {"content": token_data.decode()}}}).encode()
req2 = urllib.request.Request(
    f"https://api.github.com/gists/{GIST_ID}",
    data=patch_body, method="PATCH",
    headers={"Authorization": f"Bearer {GITHUB_PAT}", "Accept": "application/vnd.github+json",
             "Content-Type": "application/json", "X-GitHub-Api-Version": "2022-11-28"}
)
with urllib.request.urlopen(req2, timeout=15) as r:
    r.read()
PYEOF

# --- 1. Keep proxy alive ---
if ! /usr/bin/python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:$PROXY_PORT/health', timeout=2)" > /dev/null 2>&1; then
    echo "[$(date)] Proxy down — restarting..."
    pkill -f "claude_proxy.py" 2>/dev/null
    sleep 1
    nohup bash -c "HQ_PROXY_KEY=$HQ_PROXY_KEY HQ_GITHUB_PAT=$HQ_GITHUB_PAT /usr/bin/python3 /home/polfam/mount_polumbus_hq/claude_proxy.py" > /tmp/hq_proxy.log 2>&1 &
    sleep 3
fi

# --- 2. Keep tunnel alive ---
NGROK="/home/polfam/.local/bin/ngrok"
NGROK_DOMAIN="gertrude-spectroscopic-nominally.ngrok-free.dev"
if ! pgrep -f "ngrok" > /dev/null 2>&1; then
    echo "[$(date)] Tunnel down — restarting ngrok..."
    nohup "$NGROK" http "$PROXY_PORT" --url="$NGROK_DOMAIN" > "$TUNNEL_LOG" 2>&1 &
    sleep 5
fi

# --- 3. ngrok domain is static, no URL detection needed ---
CURRENT_URL="https://$NGROK_DOMAIN"

# --- 4. Update Gist if URL changed ---
STORED_URL=$(cat "$URL_FILE" 2>/dev/null)
if [ "$CURRENT_URL" != "$STORED_URL" ]; then
    echo "[$(date)] URL changed to $CURRENT_URL — updating Gist..."
    HQ_GITHUB_PAT="$HQ_GITHUB_PAT" /usr/bin/python3 - "$CURRENT_URL" <<'PYEOF'
import json, urllib.request, os, sys

GIST_ID = "15fb167bbbfdaa79d5ce11c266c3f652"
GITHUB_PAT = os.environ["HQ_GITHUB_PAT"]
NEW_URL = sys.argv[1]

req = urllib.request.Request(
    f"https://api.github.com/gists/{GIST_ID}",
    headers={"Authorization": f"Bearer {GITHUB_PAT}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
)
with urllib.request.urlopen(req, timeout=15) as resp:
    data = json.loads(resp.read())
token_content = data["files"]["hq_token.json"]["content"]

body = json.dumps({
    "files": {
        "hq_token.json": {"content": token_content},
        "hq_proxy_url.json": {"content": json.dumps({"proxy_url": NEW_URL}, indent=2)}
    }
}).encode()
req2 = urllib.request.Request(
    f"https://api.github.com/gists/{GIST_ID}",
    data=body,
    headers={"Authorization": f"Bearer {GITHUB_PAT}", "Accept": "application/vnd.github+json",
             "Content-Type": "application/json", "X-GitHub-Api-Version": "2022-11-28"},
    method="PATCH"
)
with urllib.request.urlopen(req2, timeout=15) as resp:
    resp.read()
print("Gist updated:", NEW_URL)
PYEOF
    echo "$CURRENT_URL" > "$URL_FILE"
fi
