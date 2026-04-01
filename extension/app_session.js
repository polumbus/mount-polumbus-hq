// Persist Post Ascend auth params so the X extension can reuse them.

const AUTH_KEYS = {
  token: "hq_auth_token",
  user: "hq_auth_user"
};

let _hqInterval = null;

function getAuthFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const token = params.get("token") || "";
  const user = params.get("user") || "";
  return { token, user };
}

async function saveAuthIfPresent() {
  // If extension was reloaded, chrome.runtime.id becomes undefined — bail out
  if (!chrome.runtime?.id) {
    if (_hqInterval) clearInterval(_hqInterval);
    return;
  }

  const { token, user } = getAuthFromUrl();
  if (!token) return;

  const payload = { [AUTH_KEYS.token]: token };
  if (user) payload[AUTH_KEYS.user] = user;

  try {
    await chrome.storage.local.set(payload);
  } catch (_) {
    if (_hqInterval) clearInterval(_hqInterval);
  }
}

saveAuthIfPresent();
_hqInterval = setInterval(saveAuthIfPresent, 2000);
