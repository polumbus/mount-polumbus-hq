#!/usr/bin/env python3
"""Local Claude proxy server for Streamlit Cloud.

Runs on Tyler's machine, exposes a public URL via SSH tunnel.
Streamlit Cloud sends prompts here; this calls the local Claude CLI (sonnet).

Start: python3 /home/polfam/mount_polumbus_hq/claude_proxy.py
Then run: ssh -R 80:localhost:7821 nokey@localhost.run
"""
import json, os, subprocess, time
from http.server import BaseHTTPRequestHandler, HTTPServer

CLAUDE_CLI = "/home/polfam/.npm-global/bin/claude"
PROXY_API_KEY = os.environ.get("HQ_PROXY_KEY", "")
PORT = 7821


class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[{time.strftime('%H:%M:%S')}] {format % args}")

    def send_json(self, code, data):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/call":
            self.send_json(404, {"error": "not found"})
            return

        # Auth check
        auth = self.headers.get("X-Proxy-Key", "")
        if PROXY_API_KEY and auth != PROXY_API_KEY:
            self.send_json(403, {"error": "forbidden"})
            return

        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        prompt = body.get("prompt", "")
        system = body.get("system", "")
        max_tokens = body.get("max_tokens", 1500)

        full_prompt = f"{system}\n\n{prompt}" if system else prompt
        try:
            result = subprocess.run(
                [CLAUDE_CLI, "-p", "--model", "claude-sonnet-4-6"],
                input=full_prompt,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if result.returncode == 0 and result.stdout.strip():
                self.send_json(200, {"text": result.stdout.strip()})
            else:
                self.send_json(500, {"error": result.stderr.strip() or "empty response"})
        except subprocess.TimeoutExpired:
            self.send_json(504, {"error": "timeout"})
        except Exception as e:
            self.send_json(500, {"error": str(e)})

    def do_GET(self):
        if self.path == "/health":
            self.send_json(200, {"status": "ok"})
        else:
            self.send_json(404, {"error": "not found"})


if __name__ == "__main__":
    if not PROXY_API_KEY:
        print("WARNING: HQ_PROXY_KEY not set — proxy is unprotected!")
    server = HTTPServer(("0.0.0.0", PORT), ProxyHandler)
    print(f"Claude proxy listening on port {PORT}")
    print("To expose publicly: ssh -R 80:localhost:7821 nokey@localhost.run")
    server.serve_forever()
