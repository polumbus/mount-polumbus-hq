#!/usr/bin/env python3
"""Syncs current Claude OAuth access token to GitHub Gist every 7 hours.
Run via cron: 0 */7 * * * /usr/bin/python3 /home/polfam/mount_polumbus_hq/sync_token_to_gist.py
"""
import json, os, time, urllib.request, urllib.parse, subprocess, sys

CREDENTIALS_PATH = "/home/polfam/.claude/.credentials.json"
GIST_ID = "15fb167bbbfdaa79d5ce11c266c3f652"
GITHUB_PAT = os.environ.get("HQ_GITHUB_PAT", "")
OAUTH_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
OAUTH_TOKEN_URL = "https://platform.claude.com/v1/oauth/token"

def load_creds():
    with open(CREDENTIALS_PATH) as f:
        creds = json.load(f)
    return creds["claudeAiOauth"]

def save_creds(access_token, refresh_token, expires_at_ms):
    with open(CREDENTIALS_PATH) as f:
        creds = json.load(f)
    creds["claudeAiOauth"]["accessToken"] = access_token
    creds["claudeAiOauth"]["refreshToken"] = refresh_token
    creds["claudeAiOauth"]["expiresAt"] = expires_at_ms
    with open(CREDENTIALS_PATH, "w") as f:
        json.dump(creds, f, indent=2)

def refresh_token(refresh_tok):
    body = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_tok,
        "client_id": OAUTH_CLIENT_ID,
    }).encode()
    req = urllib.request.Request(
        OAUTH_TOKEN_URL, data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", "User-Agent": "claude-code/2.1.78"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())

def write_to_gist(access_token, expires_at_epoch):
    body = json.dumps({
        "files": {
            "hq_token.json": {
                "content": json.dumps({"access_token": access_token, "expires_at": expires_at_epoch}, indent=2)
            }
        }
    }).encode()
    req = urllib.request.Request(
        f"https://api.github.com/gists/{GIST_ID}",
        data=body,
        headers={
            "Authorization": f"Bearer {GITHUB_PAT}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="PATCH"
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        resp.read()

def main():
    oauth = load_creds()
    access_token = oauth["accessToken"]
    expires_at = oauth["expiresAt"] / 1000  # ms -> seconds

    # Refresh if expiring within 1 hour
    if time.time() > expires_at - 3600:
        print("Token expiring soon, refreshing...")
        data = refresh_token(oauth["refreshToken"])
        access_token = data["access_token"]
        new_refresh = data["refresh_token"]
        expires_at = time.time() + data["expires_in"]
        save_creds(access_token, new_refresh, int(expires_at * 1000))
        print("Refreshed and saved locally.")

    write_to_gist(access_token, expires_at)
    print(f"Token synced to Gist. Expires in {round((expires_at - time.time())/3600, 1)}h")

if __name__ == "__main__":
    main()
