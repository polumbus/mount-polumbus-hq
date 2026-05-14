# Article Writer Capture Plan

Page route:
`/?token=VIDEO_DEMO_TOKEN&user=owner&page=Article+Writer`

Demo mode:
`VIDEO_DEMO_MODE=1`

Required seed data:
`video-production/demo-data/video-demo-seed.json`

Exact selectors:
- `[data-video-id='article-writer-primary']`
- `main`
- `button`
- `textarea`
- `select`

Exact actions:
1. Open page
2. Choose Raw Thoughts source
3. Select saved idea
4. Generate article structure

Expected UI state after each action:
- The relevant control is visible.
- The page uses deterministic demo data.
- No real external API call is required.
- No token, cookie, API key, OAuth value, webhook, or real email is visible.

Failure conditions:
- Page route does not load.
- Loading spinner remains visible.
- Required control is hidden or offscreen.
- Any real private data appears.
- Captions or callouts cover the demonstrated control.
- Demo data differs from the storyboard.

Sensitive-data checks:
- Scan text assets and rendered frames for API keys, bearer tokens, OAuth tokens, passwords, real emails, cookies, private keys, and webhook URLs.

Capture notes:
- Use reference-matched aspect ratio once the reference is available.
- Use smooth cursor motion and one clear action per scene.
- Keep browser chrome hidden unless the reference shows browser chrome.

Known edge cases:
- Streamlit reruns can shift layout; wait for stable visible text before each capture.
- Owner-only pages must use demo token and fake owner identity.

Retry behavior:
- Retry page load once.
- If deterministic demo data does not load, fail capture instead of recording real data.

Final visual checklist:
- Opening title visible.
- Main workflow visible.
- Example visible.
- Ending value line visible.
- No secrets.
