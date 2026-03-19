// Mount Polumbus HQ - Chrome Extension
// Adds "Save" and "Repurpose" buttons to tweets on X

const API_BASE = "http://localhost:8505"; // Change to tunnel URL for remote

function extractTweetData(tweetElement) {
  const textEl = tweetElement.querySelector('[data-testid="tweetText"]');
  const text = textEl ? textEl.innerText : "";
  
  const userEl = tweetElement.querySelector('[data-testid="User-Name"]');
  let author = "", handle = "";
  if (userEl) {
    const spans = userEl.querySelectorAll("span");
    for (const span of spans) {
      if (span.textContent.startsWith("@")) {
        handle = span.textContent;
      } else if (span.textContent && !span.textContent.startsWith("@") && span.textContent !== "·") {
        if (!author) author = span.textContent;
      }
    }
  }

  // Try to get metrics
  const metricsGroup = tweetElement.querySelector('[role="group"]');
  let likes = 0, retweets = 0, views = 0;
  if (metricsGroup) {
    const buttons = metricsGroup.querySelectorAll('[data-testid]');
    for (const btn of buttons) {
      const testId = btn.getAttribute("data-testid");
      const val = parseInt(btn.innerText.replace(/[,K.M]/g, "")) || 0;
      if (testId === "like") likes = val;
      if (testId === "retweet") retweets = val;
    }
  }

  // Get tweet URL
  const timeEl = tweetElement.querySelector("time");
  let tweetUrl = "";
  if (timeEl && timeEl.parentElement) {
    const link = timeEl.closest("a");
    if (link) tweetUrl = link.href;
  }

  return { text, author, handle, likes, retweets, views, tweet_url: tweetUrl };
}

function createHQButtons(tweetElement) {
  if (tweetElement.querySelector(".hq-btn-container")) return;

  const metricsGroup = tweetElement.querySelector('[role="group"]');
  if (!metricsGroup) return;

  const container = document.createElement("div");
  container.className = "hq-btn-container";

  const saveBtn = document.createElement("button");
  saveBtn.className = "hq-btn hq-save";
  saveBtn.textContent = "Save";
  saveBtn.title = "Save to Inspiration Vault";
  saveBtn.onclick = async (e) => {
    e.stopPropagation();
    e.preventDefault();
    const data = extractTweetData(tweetElement);
    try {
      const resp = await fetch(API_BASE + "/api/save-tweet", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      const result = await resp.json();
      if (result.ok) {
        saveBtn.textContent = "Saved!";
        saveBtn.classList.add("hq-saved");
        setTimeout(() => { saveBtn.textContent = "Save"; saveBtn.classList.remove("hq-saved"); }, 2000);
      }
    } catch (err) {
      saveBtn.textContent = "Error";
      setTimeout(() => { saveBtn.textContent = "Save"; }, 2000);
    }
  };

  const repurposeBtn = document.createElement("button");
  repurposeBtn.className = "hq-btn hq-repurpose";
  repurposeBtn.textContent = "Repurpose";
  repurposeBtn.title = "Save to Repurpose queue";
  repurposeBtn.onclick = async (e) => {
    e.stopPropagation();
    e.preventDefault();
    const data = extractTweetData(tweetElement);
    try {
      const resp = await fetch(API_BASE + "/api/save-repurpose", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data),
      });
      const result = await resp.json();
      if (result.ok) {
        repurposeBtn.textContent = "Queued!";
        repurposeBtn.classList.add("hq-saved");
        setTimeout(() => { repurposeBtn.textContent = "Repurpose"; repurposeBtn.classList.remove("hq-saved"); }, 2000);
      }
    } catch (err) {
      repurposeBtn.textContent = "Error";
      setTimeout(() => { repurposeBtn.textContent = "Repurpose"; }, 2000);
    }
  };

  container.appendChild(saveBtn);
  container.appendChild(repurposeBtn);
  metricsGroup.parentElement.appendChild(container);
}

function scanTweets() {
  const tweets = document.querySelectorAll('[data-testid="tweet"]');
  tweets.forEach(createHQButtons);
}

// Run on load and on scroll/navigation
const observer = new MutationObserver(scanTweets);
observer.observe(document.body, { childList: true, subtree: true });
setInterval(scanTweets, 2000);
