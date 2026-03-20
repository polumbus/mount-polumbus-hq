const PROXY_URL = "https://gertrude-spectroscopic-nominally.ngrok-free.dev";
const statusEl = document.getElementById("status");

async function checkConnection() {
  try {
    const resp = await fetch(`${PROXY_URL}/health`, {
      headers: { "ngrok-skip-browser-warning": "1" }
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

checkConnection();
