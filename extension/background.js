// Background service worker: keeps X login cookies synced to the HQ proxy.

const PROXY_URL = "https://gertrude-spectroscopic-nominally.ngrok-free.dev";
const PROXY_KEY = "polumbus_hq_proxy_2026";
const SYNC_ALARM = "sync-cookies";

function isXUrl(url = "") {
  return /^https:\/\/(x|twitter)\.com\//i.test(url);
}

async function getCookie(name, domain) {
  return new Promise(resolve => {
    chrome.cookies.get({ url: `https://${domain}/`, name }, cookie => {
      resolve(cookie ? cookie.value : null);
    });
  });
}

async function getCookieAny(name) {
  return await getCookie(name, "x.com") || await getCookie(name, "twitter.com");
}

async function syncCookiesToProxy() {
  const authToken = await getCookieAny("auth_token");
  const ct0 = await getCookieAny("ct0");
  if (!authToken || !ct0) {
    const missing = !authToken && !ct0 ? "auth_token and ct0" : !authToken ? "auth_token" : "ct0";
    const result = { ok: false, error: `Missing X cookie: ${missing}` };
    await chrome.storage.local.set({ lastCookieSync: { ...result, syncedAt: new Date().toISOString() } });
    return result;
  }

  try {
    const resp = await fetch(`${PROXY_URL}/sync-cookies`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Proxy-Key": PROXY_KEY,
        "ngrok-skip-browser-warning": "1"
      },
      body: JSON.stringify({ auth_token: authToken, ct0 })
    });
    const data = await resp.json().catch(() => ({}));
    if (!resp.ok) {
      throw new Error(data.error || `HTTP ${resp.status}`);
    }
    const result = { ok: true, syncedAt: new Date().toISOString() };
    await chrome.storage.local.set({ lastCookieSync: result });
    console.log("[HQ] Cookies synced at", result.syncedAt);
    return result;
  } catch (e) {
    console.error("[HQ] Cookie sync failed:", e);
    const result = { ok: false, error: String(e && e.message ? e.message : e), syncedAt: new Date().toISOString() };
    await chrome.storage.local.set({ lastCookieSync: result });
    return result;
  }
}

function scheduleCookieSync() {
  chrome.alarms.create(SYNC_ALARM, { periodInMinutes: 5 });
  syncCookiesToProxy();
}

chrome.runtime.onInstalled.addListener(() => {
  scheduleCookieSync();
});

chrome.runtime.onStartup.addListener(() => {
  scheduleCookieSync();
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message && message.type === "sync-cookies-now") {
    syncCookiesToProxy().then(sendResponse);
    return true;
  }
  if (message && message.type === "cookie-sync-status") {
    chrome.storage.local.get("lastCookieSync").then(data => sendResponse(data.lastCookieSync || { ok: false, error: "No sync has run yet" }));
    return true;
  }
  return false;
});

chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === SYNC_ALARM) syncCookiesToProxy();
});

chrome.cookies.onChanged.addListener(info => {
  if ((info.cookie.domain.includes("x.com") || info.cookie.domain.includes("twitter.com")) &&
      (info.cookie.name === "auth_token" || info.cookie.name === "ct0") &&
      !info.removed) {
    syncCookiesToProxy();
  }
});

chrome.tabs.onUpdated.addListener((_tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" && isXUrl(tab.url || "")) {
    syncCookiesToProxy();
  }
});

chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  try {
    const tab = await chrome.tabs.get(tabId);
    if (isXUrl(tab.url || "")) {
      syncCookiesToProxy();
    }
  } catch {
    // Ignore tabs the extension cannot inspect.
  }
});
