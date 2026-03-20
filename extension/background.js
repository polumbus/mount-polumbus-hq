// Background service worker — syncs Twitter cookies to HQ proxy every 30 min

async function getCookie(name, domain) {
  return new Promise(resolve => {
    chrome.cookies.get({ url: `https://${domain}/`, name }, cookie => {
      resolve(cookie ? cookie.value : null);
    });
  });
}

const PROXY_URL = "https://gertrude-spectroscopic-nominally.ngrok-free.dev";
const PROXY_KEY = "polumbus_hq_proxy_2026";

async function syncCookiesToProxy() {
  const authToken = await getCookie("auth_token", "x.com");
  const ct0 = await getCookie("ct0", "x.com");
  if (!authToken || !ct0) return;

  try {
    await fetch(`${PROXY_URL}/sync-cookies`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Proxy-Key": PROXY_KEY,
        "ngrok-skip-browser-warning": "1"
      },
      body: JSON.stringify({ auth_token: authToken, ct0 })
    });
    console.log("[HQ] Cookies synced at", new Date().toISOString());
  } catch (e) {
    console.error("[HQ] Cookie sync failed:", e);
  }
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create("sync-cookies", { periodInMinutes: 30 });
  syncCookiesToProxy();
});

chrome.alarms.onAlarm.addListener(alarm => {
  if (alarm.name === "sync-cookies") syncCookiesToProxy();
});

chrome.cookies.onChanged.addListener(info => {
  if (info.cookie.domain.includes("x.com") &&
      (info.cookie.name === "auth_token" || info.cookie.name === "ct0") &&
      !info.removed) {
    syncCookiesToProxy();
  }
});
