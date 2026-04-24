# HQ Proxy Runbook

This is the operator setup for Mount Polumbus HQ's local Claude proxy.

## What Uses It

- `app.py` uses the proxy for Claude fallback calls and the podcast/tweet endpoints.
- `hq_watchdog.sh` keeps the proxy and ngrok tunnel alive and syncs the public proxy URL to the Gist.

## Source Of Truth

Use these files together:

- `/home/polfam/.config/openclaw/secrets.env`
  - host-side runtime env for `claude-proxy.service`
- `/home/polfam/mount_polumbus_hq/.env.local`
  - local operator env for `hq_watchdog.sh`
- `/home/polfam/mount_polumbus_hq/.streamlit/secrets.toml`
  - Streamlit client secrets for calling the proxy

Keep `HQ_PROXY_KEY` aligned across all three places.

The proxy also accepts the shared GitHub PAT as a fallback auth key so Streamlit Cloud can keep generating if `CLAUDE_PROXY_KEY` drifts. Do not rely on that as the primary path; fix the proxy key alignment when rotating secrets.

## Required Variables

Host runtime:

- `HQ_PROXY_KEY`
- `HQ_GITHUB_PAT`
- `HQ_TWITTER_API_IO_KEY`

Streamlit client:

- `CLAUDE_PROXY_URL`
- `CLAUDE_PROXY_KEY`
- `TWITTER_API_IO_KEY`
- `GITHUB_PAT`

## Service Model

The proxy should run as the user service `claude-proxy.service`, not a `nohup` shell job.

Useful commands:

```bash
systemctl --user daemon-reload
systemctl --user enable --now claude-proxy.service
systemctl --user restart claude-proxy.service
systemctl --user status claude-proxy.service
journalctl --user -u claude-proxy.service -n 50 --no-pager
```

## Health Checks

`/health` is protected. Every caller, including local watchdogs, must send `X-Proxy-Key`.

Example:

```bash
curl -H "X-Proxy-Key: $HQ_PROXY_KEY" http://127.0.0.1:7821/health
```

## Watchdog Behavior

`hq_watchdog.sh` now:

- loads `.env.local` and `/home/polfam/.config/openclaw/secrets.env`
- checks `/health` with `X-Proxy-Key`
- restarts `claude-proxy.service` first
- falls back to a manual process launch only if `systemctl --user` is unavailable

## Rotation Checklist

When rotating the proxy key or moving the setup:

1. Update `HQ_PROXY_KEY` in `/home/polfam/.config/openclaw/secrets.env`.
2. Update `HQ_PROXY_KEY` in `/home/polfam/mount_polumbus_hq/.env.local`.
3. Update `CLAUDE_PROXY_KEY` in `/home/polfam/mount_polumbus_hq/.streamlit/secrets.toml`.
4. Restart `claude-proxy.service`.
5. Verify authenticated health succeeds.

If Streamlit Cloud shows `AI unavailable` and the local proxy log shows `forbidden path=/call has_key=True`, the Cloud `CLAUDE_PROXY_KEY` is stale. Update it to match `HQ_PROXY_KEY`; the GitHub PAT fallback is only a recovery path.

## Failure Pattern To Remember

If `/health` starts returning `403`, the proxy is probably fine and the caller is missing `X-Proxy-Key`.
