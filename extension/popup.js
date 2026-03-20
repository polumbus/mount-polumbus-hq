const statusEl = document.getElementById("status");
const urlInput = document.getElementById("api-url");

chrome.storage.local.get("apiBase", (data) => {
  if (data.apiBase) urlInput.value = data.apiBase;
});

const saveBtn = document.getElementById("save-btn");
saveBtn.onclick = () => {
  const url = urlInput.value.trim() || "http://localhost:8505";
  chrome.storage.local.set({ apiBase: url });
  saveBtn.textContent = "Saved!";
  setTimeout(() => { saveBtn.textContent = "Save Settings"; }, 1500);
  checkConnection(url);
};

async function checkConnection(base) {
  try {
    const resp = await fetch((base || "http://localhost:8505") + "/api/health");
    const data = await resp.json();
    if (data.status === "ok") {
      statusEl.textContent = "Connected to HQ";
      statusEl.className = "status connected";
    }
  } catch {
    statusEl.textContent = "Not connected — check URL";
    statusEl.className = "status disconnected";
  }
}

chrome.storage.local.get("apiBase", (data) => {
  checkConnection(data.apiBase || "http://localhost:8505");
});
