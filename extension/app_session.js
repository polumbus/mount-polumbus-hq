// Persist Post Ascend auth params so the X extension can reuse them.

const AUTH_KEYS = {
  token: "hq_auth_token",
  user: "hq_auth_user"
};

function getAuthFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const token = params.get("token") || "";
  const user = params.get("user") || "";
  return { token, user };
}

async function saveAuthIfPresent() {
  const { token, user } = getAuthFromUrl();
  if (!token) return;

  const payload = {
    [AUTH_KEYS.token]: token
  };
  if (user) payload[AUTH_KEYS.user] = user;

  try {
    await chrome.storage.local.set(payload);
  } catch (err) {
    // Extension context invalidated (e.g. after reload) — stop polling
    if (_hqInterval) clearInterval(_hqInterval);
  }
}

saveAuthIfPresent();
const _hqInterval = setInterval(saveAuthIfPresent, 2000);

