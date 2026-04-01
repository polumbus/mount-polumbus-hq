// Persist Post Ascend auth params so the X extension can reuse them.
// Runs once on page load — no interval, no cleanup needed.

(async function() {
  try {
    const params = new URLSearchParams(window.location.search);
    const token = params.get("token") || "";
    if (!token) return;

    const payload = { hq_auth_token: token };
    const user = params.get("user") || "";
    if (user) payload.hq_auth_user = user;

    await chrome.storage.local.set(payload);
  } catch (_) {
    // silently ignore — extension context may be invalidated
  }
})();
