# AI Provider Profiles

Mount Polumbus HQ intentionally has two separate AI runtime profiles.

## Streamlit HQ App

- Scope: root Python app, especially `app.py`, `claude_proxy.py`, `chatgpt_oauth.py`, and Streamlit Cloud behavior.
- Runtime: Streamlit Cloud plus the local HQ proxy when needed.
- AI auth model: OAuth/CLI/proxy first.
- Expected routes:
  - Claude OAuth direct calls from the Streamlit process when available.
  - Local Claude CLI through `claude_proxy.py` when Cloud needs Tyler's local machine.
  - ChatGPT OAuth fallback through the local Codex login path where this app already supports it.
- Do not convert this profile to `ANTHROPIC_API_KEY` or `OPENAI_API_KEY` unless the user explicitly asks to change the Streamlit app contract.

## Website

- Scope: everything under `web/`.
- Runtime: Next.js/Vercel.
- AI auth model: direct API keys only.
- Expected routes:
  - `ANTHROPIC_API_KEY`
  - `OPENAI_API_KEY`
  - model and timeout variables from `web/.env.example`
- Do not add Streamlit OAuth, Claude CLI, local proxy, or Codex OAuth dependencies to the website runtime.

## Boundary Rules

- Keep Streamlit AI routing in root Python modules.
- Keep website AI routing in `web/src/lib/ai-provider.ts` and website API routes.
- Do not share one automatic provider router between the two profiles.
- If behavior must be shared, share prompt text, validation rules, schemas, or fixtures, not credentials or provider transport.
- Name new env vars with the owning runtime in mind. Prefer website vars in `web/.env.example`; prefer Streamlit secrets in `.streamlit/secrets.toml` or Streamlit Cloud settings.
- When debugging AI failures, identify the active profile first. A website API-key issue and a Streamlit OAuth/proxy issue are different incidents.

## Repository Layout Recommendation

The app and website can stay in the same repository as long as this folder boundary stays strict:

- Streamlit HQ app: repo root.
- Website: `web/`.

Separate repositories are only worth it if deploy cadence, access control, or secret ownership becomes hard to manage. The immediate protection we need is explicit profile documentation, separate env examples, and no shared provider transport code.
