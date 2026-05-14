const PROXY_URL = "https://gertrude-spectroscopic-nominally.ngrok-free.dev";
const PROXY_KEY = "polumbus_hq_proxy_2026";
const statusEl = document.getElementById("status");
const syncBtn = document.getElementById("sync-x");
const cookieStatusEl = document.getElementById("cookie-status");

async function checkConnection() {
  try {
    const resp = await fetch(`${PROXY_URL}/health`, {
      headers: {
        "X-Proxy-Key": PROXY_KEY,
        "ngrok-skip-browser-warning": "1"
      }
    });
    const data = await resp.json();
    if (data.status === "ok") {
      statusEl.textContent = "HQ proxy connected";
      statusEl.className = "status connected";
    } else {
      throw new Error("bad status");
    }
  } catch {
    statusEl.textContent = "Proxy offline — check watchdog";
    statusEl.className = "status disconnected";
  }
}

function renderCookieStatus(result) {
  if (!result) {
    cookieStatusEl.textContent = "Cookie sync not checked yet.";
    cookieStatusEl.className = "mini-status";
    return;
  }
  if (result.ok) {
    cookieStatusEl.textContent = `X login synced ${result.syncedAt || "now"}`;
    cookieStatusEl.className = "mini-status connected-text";
  } else {
    cookieStatusEl.textContent = result.error || "X login sync failed. Open x.com while logged in.";
    cookieStatusEl.className = "mini-status error-text";
  }
}

async function loadCookieStatus() {
  try {
    const result = await chrome.runtime.sendMessage({ type: "cookie-sync-status" });
    renderCookieStatus(result);
  } catch {
    renderCookieStatus({ ok: false, error: "Extension background worker unavailable." });
  }
}

async function syncXLogin() {
  syncBtn.disabled = true;
  syncBtn.textContent = "Syncing...";
  try {
    const result = await chrome.runtime.sendMessage({ type: "sync-cookies-now" });
    renderCookieStatus(result);
  } catch {
    renderCookieStatus({ ok: false, error: "Open x.com while logged in, then reload this extension." });
  }
  syncBtn.disabled = false;
  syncBtn.textContent = "Sync X Login";
}

syncBtn.addEventListener("click", syncXLogin);
checkConnection();
loadCookieStatus();
