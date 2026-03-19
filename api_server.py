#!/usr/bin/python3
"""Simple API server for Mount Polumbus HQ Chrome extension.
Runs on port 8505. Receives saved tweets and adds to inspiration.json.
"""
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import os
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(os.path.expanduser("~/.openclaw/workspace-omaha/data"))
INSPO_FILE = DATA_DIR / "inspiration.json"
PORT = 8505

def load_inspo():
    if INSPO_FILE.exists():
        try:
            return json.loads(INSPO_FILE.read_text())
        except Exception:
            pass
    return []

def save_inspo(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    INSPO_FILE.write_text(json.dumps(data, indent=2, default=str))

def fetch_tweet_from_url(tweet_url):
    """Fetch tweet data from a URL using TwitterAPI.io."""
    import re
    match = re.search(r'/status/(\d+)', tweet_url)
    if not match:
        return None
    tweet_id = match.group(1)
    try:
        import tomli
        with open("/home/polfam/.openclaw/workspace-redzone/.streamlit/secrets.toml", "rb") as f:
            secrets = tomli.load(f)
        api_key = secrets.get("TWITTER_API_IO_KEY", "")
        if not api_key:
            return None
        import urllib.request
        req = urllib.request.Request(
            f"https://api.twitterapi.io/twitter/tweet/advanced_search?query=id:{tweet_id}&queryType=Latest&count=1",
            headers={"X-API-Key": api_key}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        tweets = data.get("tweets", [])
        if tweets:
            t = tweets[0]
            author = t.get("author", {})
            return {
                "text": t.get("text", ""),
                "author": author.get("name", ""),
                "handle": "@" + author.get("userName", ""),
                "likes": t.get("likeCount", 0),
                "retweets": t.get("retweetCount", 0),
                "views": t.get("viewCount", 0),
            }
    except Exception:
        pass
    return None

class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/save-tweet":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode()
            try:
                data = json.loads(body)
                tweet_url = data.get("tweet_url", "")

                # If we only have a URL (iOS shortcut), fetch full tweet data
                if tweet_url and (not data.get("text") or data.get("text") == "Saved from iOS"):
                    fetched = fetch_tweet_from_url(tweet_url)
                    if fetched:
                        data.update(fetched)

                source = "ios_shortcut" if data.get("source") == "ios_shortcut" else "chrome_extension"
                tweet = {
                    "text": data.get("text", ""),
                    "author": data.get("author", ""),
                    "handle": data.get("handle", ""),
                    "likes": data.get("likes", 0),
                    "retweets": data.get("retweets", 0),
                    "views": data.get("views", 0),
                    "tweet_url": tweet_url,
                    "tags": data.get("tags", []),
                    "source": source,
                    "saved_at": datetime.now().isoformat(),
                }
                inspo = load_inspo()
                inspo.append(tweet)
                save_inspo(inspo)

                self.send_response(200)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True, "count": len(inspo)}).encode())
            except Exception as e:
                self.send_response(400)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode())
        elif self.path == "/api/save-repurpose":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode()
            try:
                data = json.loads(body)
                ideas = []
                ideas_file = DATA_DIR / "saved_ideas.json"
                if ideas_file.exists():
                    ideas = json.loads(ideas_file.read_text())
                ideas.append({
                    "text": data.get("text", ""),
                    "format": "Short Tweet",
                    "category": "Repurpose",
                    "source_author": data.get("author", ""),
                    "source_url": data.get("tweet_url", ""),
                    "source": "chrome_extension",
                    "saved_at": datetime.now().isoformat(),
                })
                ideas_file.write_text(json.dumps(ideas, indent=2, default=str))

                self.send_response(200)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": True}).encode())
            except Exception as e:
                self.send_response(400)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"ok": False, "error": str(e)}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == "/api/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "ok", "app": "Mount Polumbus HQ"}).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress console logging

if __name__ == "__main__":
    server = HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"HQ API server running on port {PORT}")
    server.serve_forever()
