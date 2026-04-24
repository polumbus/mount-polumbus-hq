<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

## AI Provider Profile

This `web/` app is the website build. It uses direct provider API keys only.

- Use `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, and the model variables in `web/.env.example`.
- Keep AI transport in `web/src/lib/ai-provider.ts` or website API routes.
- Do not import or depend on root Streamlit OAuth helpers, Claude CLI, `claude_proxy.py`, local Codex OAuth, or Streamlit secrets.
- The root Streamlit app has a different AI profile: OAuth/direct, Claude CLI, local proxy, and ChatGPT OAuth fallback.
- If a prompt, schema, or validator needs to be shared, copy or extract that non-secret logic deliberately; do not share credential routing.
