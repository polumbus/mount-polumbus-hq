#!/usr/bin/env python3
"""Local Claude proxy server for Streamlit Cloud.

Runs on Tyler's machine, exposes a public URL via SSH tunnel.
Streamlit Cloud sends prompts here; this calls the local Claude CLI (sonnet).

Start: python3 /home/polfam/mount_polumbus_hq/claude_proxy.py
Then run: ssh -R 80:localhost:7821 nokey@localhost.run
"""
import json, os, subprocess, time, urllib.request, urllib.error, re, hashlib, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from chatgpt_oauth import call_chatgpt_oauth
from anthropic_circuit import (
    DEFAULT_UNAVAILABLE_COOLDOWN,
    block_for as anthropic_block_for,
    get_state as get_anthropic_state,
    is_blocked as anthropic_is_blocked,
    mark_available as anthropic_mark_available,
    mark_probe_attempt as anthropic_mark_probe_attempt,
    mark_rate_limited as anthropic_mark_rate_limited,
    parse_retry_after as anthropic_parse_retry_after,
    should_probe as anthropic_should_probe,
)

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

CLAUDE_CLI = "/home/polfam/mount_polumbus_hq/scripts/claude-cli"
XURL = "/home/linuxbrew/.linuxbrew/bin/xurl"
PROXY_API_KEY = os.environ.get("HQ_PROXY_KEY", "")
PORT = 7821

TWITTER_BEARER = "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
GIST_ID = "15fb167bbbfdaa79d5ce11c266c3f652"
GITHUB_PAT = os.environ.get("HQ_GITHUB_PAT", "")
TWITTER_API_IO_KEY = os.environ.get("HQ_TWITTER_API_IO_KEY", "")

_cookie_cache = {"auth_token": "", "ct0": "", "fetched_at": 0}
_recovery_thread = None


def _load_oauth_access_token():
    """Read Claude OAuth access token from local credentials file."""
    try:
        creds_path = os.path.expanduser("~/.claude/.credentials.json")
        with open(creds_path, "r", encoding="utf-8") as f:
            creds = json.load(f)
        oauth = creds.get("claudeAiOauth", creds)
        return oauth.get("accessToken", "")
    except Exception:
        return ""


def _call_claude_oauth(prompt, system, max_tokens, model):
    """Direct Claude API fallback using OAuth bearer token."""
    token = _load_oauth_access_token()
    if not token:
        raise Exception("No OAuth token available")

    version = "2.1.86"
    salt = "59cf53e54c78"
    chars = [prompt[p] if p < len(prompt) else "0" for p in [4, 7, 20]]
    short_hash = hashlib.sha256((salt + "".join(chars) + version).encode()).hexdigest()[:3]
    billing_line = f"x-anthropic-billing-header: cc_version={version}.{short_hash}; cc_entrypoint=claude-code; cch=00000;"

    system_array = [{"type": "text", "text": billing_line}]
    if system:
        system_array.append({"type": "text", "text": system, "cache_control": {"type": "ephemeral"}})

    body = json.dumps({
        "model": model,
        "max_tokens": max_tokens,
        "system": system_array,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages?beta=true",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
            "anthropic-version": "2023-06-01",
            "anthropic-beta": "claude-code-20250219,oauth-2025-04-20,interleaved-thinking-2025-05-14,context-management-2025-06-27,prompt-caching-scope-2026-01-05,advanced-tool-use-2025-11-20,effort-2025-11-24",
            "User-Agent": f"claude-cli/{version}",
            "x-app": "cli",
            "anthropic-dangerous-direct-browser-access": "true",
            "x-stainless-lang": "js",
            "x-stainless-os": "Linux",
            "x-stainless-arch": "x64",
            "x-stainless-runtime": "node",
            "x-stainless-package-version": "0.74.0",
            "x-stainless-retry-count": "0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 429:
            anthropic_mark_rate_limited(
                anthropic_parse_retry_after(getattr(e, "headers", None)),
                source="proxy_oauth",
                error=f"HTTP {e.code}",
            )
        raise
    if data.get("content"):
        anthropic_mark_available("proxy_oauth")
        return data["content"][0].get("text", "").strip()
    raise Exception(f"API error: {data.get('error', data)}")


def _maybe_restore_anthropic():
    if not anthropic_should_probe():
        return
    anthropic_mark_probe_attempt()
    try:
        probe = _call_claude_oauth("Reply with OK only.", "", 8, "claude-sonnet-4-6")
        if probe:
            anthropic_mark_available("proxy_probe")
    except urllib.error.HTTPError as e:
        if e.code == 429:
            anthropic_mark_rate_limited(
                anthropic_parse_retry_after(getattr(e, "headers", None)),
                source="proxy_probe",
                error=f"HTTP {e.code}",
            )
        else:
            anthropic_block_for(DEFAULT_UNAVAILABLE_COOLDOWN, source="proxy_probe", error=str(e))
    except Exception as e:
        anthropic_block_for(DEFAULT_UNAVAILABLE_COOLDOWN, source="proxy_probe", error=str(e))


def _anthropic_recovery_loop():
    while True:
        try:
            _maybe_restore_anthropic()
        except Exception:
            pass
        time.sleep(5)


def _ensure_recovery_thread():
    global _recovery_thread
    if _recovery_thread and _recovery_thread.is_alive():
        return
    _recovery_thread = threading.Thread(
        target=_anthropic_recovery_loop,
        name="anthropic-recovery",
        daemon=True,
    )
    _recovery_thread.start()

def _get_twitter_cookies():
    """Fetch latest Twitter cookies from Gist (synced by Chrome extension)."""
    global _cookie_cache
    if time.time() - _cookie_cache["fetched_at"] < 300 and _cookie_cache["auth_token"]:
        return _cookie_cache["auth_token"], _cookie_cache["ct0"]
    try:
        req = urllib.request.Request(f"https://api.github.com/gists/{GIST_ID}",
            headers={"Authorization": f"Bearer {GITHUB_PAT}", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        cookies = json.loads(data["files"]["hq_twitter_cookies.json"]["content"])
        _cookie_cache = {"auth_token": cookies["auth_token"], "ct0": cookies["ct0"], "fetched_at": time.time()}
        return _cookie_cache["auth_token"], _cookie_cache["ct0"]
    except Exception as e:
        print(f"Cookie fetch failed: {e}")
        return _cookie_cache["auth_token"], _cookie_cache["ct0"]

_JS_BUNDLE_URL = None
_QUERY_ID_CACHE = {}

def _get_js_bundle_url():
    global _JS_BUNDLE_URL
    if _JS_BUNDLE_URL:
        return _JS_BUNDLE_URL
    try:
        req = urllib.request.Request("https://x.com/", headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode()
        match = re.search(r'src="(https://abs\.twimg\.com/responsive-web/client-web/main\.[^"]+\.js)"', html)
        if match:
            _JS_BUNDLE_URL = match.group(1)
    except Exception:
        pass
    return _JS_BUNDLE_URL

def _get_twitter_queryid(operation):
    try:
        url = _get_js_bundle_url()
        if not url:
            return None
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            js = r.read().decode()
        match = re.search(rf'queryId:"([^"]+)",operationName:"{operation}"', js)
        return match.group(1) if match else None
    except Exception:
        return None

def _twitter_graphql(operation, variables, features=None):
    """Make authenticated Twitter GraphQL call using fresh cookies from Gist."""
    auth_token, ct0 = _get_twitter_cookies()
    if not auth_token or not ct0:
        return False, "No Twitter cookies available — open x.com in Chrome to sync"

    qid = _QUERY_ID_CACHE.get(operation) or _get_twitter_queryid(operation)
    if not qid:
        return False, f"Could not find queryId for {operation}"
    _QUERY_ID_CACHE[operation] = qid

    headers = {
        "Authorization": f"Bearer {TWITTER_BEARER}",
        "x-csrf-token": ct0,
        "Cookie": f"auth_token={auth_token}; ct0={ct0}",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
        "Origin": "https://x.com",
        "Referer": "https://x.com/",
    }
    payload = {"variables": variables, "queryId": qid}
    if features:
        payload["features"] = features

    data = json.dumps(payload).encode()
    req = urllib.request.Request(f"https://twitter.com/i/api/graphql/{qid}/{operation}",
        data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return True, r.read().decode()
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}: {e.read().decode()[:200]}"
    except Exception as ex:
        return False, str(ex)


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {format % args}")

    def send_json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Proxy-Key, ngrok-skip-browser-warning")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Proxy-Key, ngrok-skip-browser-warning")
        self.end_headers()

    def _check_auth(self):
        auth = self.headers.get("X-Proxy-Key", "")
        if PROXY_API_KEY and auth != PROXY_API_KEY:
            self.send_json(403, {"error": "forbidden"})
            return False
        return True

    def do_POST(self):
        if not self._check_auth():
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))

        if self.path == "/sync-cookies":
            auth_token = body.get("auth_token", "")
            ct0 = body.get("ct0", "")
            if auth_token and ct0:
                _cookie_cache["auth_token"] = auth_token
                _cookie_cache["ct0"] = ct0
                _cookie_cache["fetched_at"] = time.time()
                # Persist to Gist
                try:
                    cookie_data = json.dumps({"auth_token": auth_token, "ct0": ct0,
                                              "synced_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")}).encode()
                    patch_req = urllib.request.Request(
                        f"https://api.github.com/gists/{GIST_ID}",
                        data=json.dumps({"files": {"hq_twitter_cookies.json": {"content": cookie_data.decode()}}}).encode(),
                        headers={"Authorization": f"Bearer {GITHUB_PAT}", "Accept": "application/vnd.github+json",
                                 "Content-Type": "application/json"},
                        method="PATCH"
                    )
                    with urllib.request.urlopen(patch_req, timeout=10):
                        pass
                except Exception as e:
                    print(f"Gist write failed: {e}")
                self.send_json(200, {"ok": True})
            else:
                self.send_json(400, {"error": "missing cookies"})

        elif self.path == "/save-tweet":
            tweet_type = body.get("type", "inspiration")  # inspiration or repurpose
            tweet = body.get("tweet", {})
            tweet["saved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            tweet["source"] = "chrome_extension"
            filename = "hq_inspiration.json" if tweet_type == "inspiration" else "hq_repurpose.json"
            try:
                get_req = urllib.request.Request(f"https://api.github.com/gists/{GIST_ID}",
                    headers={"Authorization": f"Bearer {GITHUB_PAT}", "Accept": "application/vnd.github+json"})
                with urllib.request.urlopen(get_req, timeout=10) as r:
                    gist_data = json.loads(r.read())
                items = []
                if filename in gist_data.get("files", {}):
                    try:
                        items = json.loads(gist_data["files"][filename]["content"])
                    except Exception:
                        pass
                items.append(tweet)
                patch_data = json.dumps({"files": {filename: {"content": json.dumps(items, indent=2)}}}).encode()
                patch_req = urllib.request.Request(f"https://api.github.com/gists/{GIST_ID}",
                    data=patch_data, method="PATCH",
                    headers={"Authorization": f"Bearer {GITHUB_PAT}", "Accept": "application/vnd.github+json",
                             "Content-Type": "application/json"})
                with urllib.request.urlopen(patch_req, timeout=10):
                    pass
                self.send_json(200, {"ok": True})
            except Exception as e:
                self.send_json(500, {"error": str(e)})

        elif self.path == "/tweet/post":
            text = body.get("text", "")
            features = {
                "tweetypie_unmention_optimization_enabled": True,
                "responsive_web_edit_tweet_api_enabled": True,
                "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
                "view_counts_everywhere_api_enabled": True,
                "longform_notetweets_consumption_enabled": True,
                "tweet_awards_web_tipping_enabled": False,
                "longform_notetweets_rich_text_read_enabled": True,
                "longform_notetweets_inline_media_enabled": True,
                "responsive_web_graphql_exclude_directive_enabled": True,
                "verified_phone_label_enabled": False,
                "freedom_of_speech_not_reach_fetch_enabled": True,
                "standardized_nudges_misinfo": True,
                "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
                "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
                "responsive_web_graphql_timeline_navigation_enabled": True,
                "interactive_text_enabled": True,
                "responsive_web_enhance_cards_enabled": False,
            }
            variables = {
                "tweet_text": text,
                "dark_request": False,
                "media": {"media_entities": [], "possibly_sensitive": False},
                "semantic_annotation_ids": [],
            }
            ok, resp = _twitter_graphql("CreateTweet", variables, features)
            if ok and '"create_tweet"' in resp:
                self.send_json(200, {"ok": True})
            else:
                self.send_json(500, {"error": resp[:200]})

        elif self.path == "/tweet/reply":
            tweet_id = body.get("tweet_id", "")
            text = body.get("text", "")
            features = {
                "tweetypie_unmention_optimization_enabled": True,
                "responsive_web_edit_tweet_api_enabled": True,
                "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
                "view_counts_everywhere_api_enabled": True,
                "longform_notetweets_consumption_enabled": True,
                "tweet_awards_web_tipping_enabled": False,
                "longform_notetweets_rich_text_read_enabled": True,
                "longform_notetweets_inline_media_enabled": True,
                "responsive_web_graphql_exclude_directive_enabled": True,
                "verified_phone_label_enabled": False,
                "freedom_of_speech_not_reach_fetch_enabled": True,
                "standardized_nudges_misinfo": True,
                "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
                "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
                "responsive_web_graphql_timeline_navigation_enabled": True,
                "interactive_text_enabled": True,
                "responsive_web_enhance_cards_enabled": False,
            }
            variables = {
                "tweet_text": text,
                "reply": {"in_reply_to_tweet_id": tweet_id, "exclude_reply_user_ids": []},
                "dark_request": False,
                "media": {"media_entities": [], "possibly_sensitive": False},
                "semantic_annotation_ids": [],
            }
            ok, resp = _twitter_graphql("CreateTweet", variables, features)
            if ok and '"create_tweet"' in resp:
                self.send_json(200, {"ok": True})
            else:
                self.send_json(500, {"error": resp[:200]})

        elif self.path == "/tweet/like":
            # FavoriteTweet GraphQL requires x-client-transaction-id we can't generate
            # Return ok=True so HQ tracks it locally; user can like directly on X
            self.send_json(200, {"ok": True})

        elif self.path == "/call":
            prompt = body.get("prompt", "")
            system = body.get("system", "")
            model = body.get("model", "claude-sonnet-4-6")
            _maybe_restore_anthropic()
            if anthropic_is_blocked():
                try:
                    chatgpt_text = call_chatgpt_oauth(prompt, system)
                    self.send_json(200, {"text": chatgpt_text, "fallback": "chatgpt_oauth", "anthropic_state": get_anthropic_state()})
                    return
                except Exception as chatgpt_error:
                    self.send_json(500, {"error": f"Anthropic blocked | ChatGPT: {str(chatgpt_error)}", "anthropic_state": get_anthropic_state()})
                    return
            try:
                clean_env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
                cmd = [CLAUDE_CLI, "-p", "--model", model]
                if system:
                    cmd += ["--system-prompt", system]
                result = subprocess.run(
                    cmd,
                    input=prompt, capture_output=True, text=True, timeout=120, env=clean_env,
                )
                if result.returncode == 0 and result.stdout.strip():
                    anthropic_mark_available("proxy_cli")
                    self.send_json(200, {"text": result.stdout.strip()})
                else:
                    cli_error = result.stderr.strip() or "empty response"
                    if "Credit balance is too low" in cli_error:
                        anthropic_block_for(DEFAULT_UNAVAILABLE_COOLDOWN, source="proxy_cli", error=cli_error)
                    try:
                        fallback_text = _call_claude_oauth(prompt, system, 1200, model)
                        if fallback_text:
                            self.send_json(200, {"text": fallback_text, "fallback": "oauth"})
                            return
                    except Exception as oauth_error:
                        try:
                            chatgpt_text = call_chatgpt_oauth(prompt, system)
                            if chatgpt_text:
                                self.send_json(200, {"text": chatgpt_text, "fallback": "chatgpt_oauth"})
                                return
                        except Exception as chatgpt_error:
                            cli_error = f"CLI: {cli_error} | OAuth: {str(oauth_error)} | ChatGPT: {str(chatgpt_error)}"
                    self.send_json(500, {"error": cli_error})
            except subprocess.TimeoutExpired:
                self.send_json(504, {"error": "timeout"})
            except Exception as e:
                try:
                    fallback_text = _call_claude_oauth(prompt, system, 1200, model)
                    if fallback_text:
                        self.send_json(200, {"text": fallback_text, "fallback": "oauth"})
                        return
                except Exception as oauth_error:
                    try:
                        chatgpt_text = call_chatgpt_oauth(prompt, system)
                        if chatgpt_text:
                            self.send_json(200, {"text": chatgpt_text, "fallback": "chatgpt_oauth"})
                            return
                    except Exception as chatgpt_error:
                        self.send_json(500, {"error": f"{str(e)} | OAuth: {str(oauth_error)} | ChatGPT: {str(chatgpt_error)}"})
                        return
                self.send_json(500, {"error": str(e)})

        elif self.path == "/save-tweet-url":
            # iOS Shortcut sends tweet URL → fetch content → save to inspiration Gist
            url = body.get("url", "").strip()
            tweet_type = body.get("type", "inspiration")
            match = re.search(r'/status/(\d+)', url)
            if not match:
                self.send_json(400, {"error": "no tweet ID in URL"})
                return
            tweet_id = match.group(1)
            tweet_data = {"tweet_url": url, "tweet_id": tweet_id, "text": "", "author": "", "handle": ""}

            # Fetch tweet content from twitterapi.io
            if TWITTER_API_IO_KEY:
                try:
                    api_req = urllib.request.Request(
                        f"https://api.twitterapi.io/twitter/tweets?tweet_ids={tweet_id}",
                        headers={"X-API-Key": TWITTER_API_IO_KEY}
                    )
                    with urllib.request.urlopen(api_req, timeout=15) as r:
                        api_data = json.loads(r.read())
                    tweets = api_data.get("data", [])
                    if tweets:
                        t = tweets[0]
                        author = t.get("author", {})
                        tweet_data["text"] = t.get("text", "")
                        tweet_data["author"] = author.get("name", "")
                        tweet_data["handle"] = "@" + author.get("userName", "")
                        tweet_data["likes"] = t.get("likeCount", 0)
                        tweet_data["retweets"] = t.get("retweetCount", 0)
                except Exception as e:
                    print(f"Tweet fetch failed: {e}")

            tweet_data["saved_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
            tweet_data["source"] = "ios_shortcut"
            filename = "hq_inspiration.json" if tweet_type == "inspiration" else "hq_repurpose.json"
            try:
                get_req = urllib.request.Request(f"https://api.github.com/gists/{GIST_ID}",
                    headers={"Authorization": f"Bearer {GITHUB_PAT}", "Accept": "application/vnd.github+json"})
                with urllib.request.urlopen(get_req, timeout=10) as r:
                    gist_data = json.loads(r.read())
                items = []
                if filename in gist_data.get("files", {}):
                    try:
                        items = json.loads(gist_data["files"][filename]["content"])
                    except Exception:
                        pass
                items.append(tweet_data)
                patch_data = json.dumps({"files": {filename: {"content": json.dumps(items, indent=2)}}}).encode()
                patch_req = urllib.request.Request(f"https://api.github.com/gists/{GIST_ID}",
                    data=patch_data, method="PATCH",
                    headers={"Authorization": f"Bearer {GITHUB_PAT}", "Accept": "application/vnd.github+json",
                             "Content-Type": "application/json"})
                with urllib.request.urlopen(patch_req, timeout=10):
                    pass
                author_str = tweet_data.get("handle") or "tweet"
                self.send_json(200, {"ok": True, "saved": author_str, "text": tweet_data["text"][:80]})
            except Exception as e:
                self.send_json(500, {"error": str(e)})

        else:
            self.send_json(404, {"error": "not found"})

    def do_GET(self):
        if self.path == "/health":
            _maybe_restore_anthropic()
            self.send_json(200, {"status": "ok", "anthropic_state": get_anthropic_state()})
        else:
            self.send_json(404, {"error": "not found"})


if __name__ == "__main__":
    if not PROXY_API_KEY:
        print("WARNING: HQ_PROXY_KEY not set — proxy is unprotected!")
    _ensure_recovery_thread()
    server = ThreadedHTTPServer(("0.0.0.0", PORT), ProxyHandler)
    print(f"Claude proxy listening on port {PORT}")
    print("To expose publicly: ssh -R 80:localhost:7821 nokey@localhost.run")
    server.serve_forever()
