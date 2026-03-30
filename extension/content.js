// Mount Polumbus HQ - Chrome Extension
// Adds "Save" and "Repurpose" buttons to tweets on X

const PROXY_URL = "https://gertrude-spectroscopic-nominally.ngrok-free.dev";
const PROXY_KEY = "polumbus_hq_proxy_2026";

async function callProxy(path, body) {
  const resp = await fetch(`${PROXY_URL}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Proxy-Key": PROXY_KEY,
      "ngrok-skip-browser-warning": "1"
    },
    body: JSON.stringify(body)
  });
  return resp.json();
}

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

  const metricsGroup = tweetElement.querySelector('[role="group"]');
  let likes = 0, retweets = 0;
  if (metricsGroup) {
    const buttons = metricsGroup.querySelectorAll('[data-testid]');
    for (const btn of buttons) {
      const testId = btn.getAttribute("data-testid");
      const val = parseInt(btn.innerText.replace(/[,K.M]/g, "")) || 0;
      if (testId === "like") likes = val;
      if (testId === "retweet") retweets = val;
    }
  }

  const timeEl = tweetElement.querySelector("time");
  let tweetUrl = "";
  if (timeEl) {
    const link = timeEl.closest("a");
    if (link) tweetUrl = link.href;
  }

  return { text, author, handle, likes, retweets, tweet_url: tweetUrl, tags: [] };
}

// ── Repurpose Modal ──────────────────────────────────────────────────────────

function openRepurposeModal(tweetData) {
  // Remove existing modal if any
  const existing = document.getElementById("hq-repurpose-modal");
  if (existing) existing.remove();

  const modal = document.createElement("div");
  modal.id = "hq-repurpose-modal";
  modal.innerHTML = `
    <div class="hq-modal-backdrop"></div>
    <div class="hq-modal-box">
      <div class="hq-modal-header">
        <span class="hq-modal-title">REPURPOSE TWEET</span>
        <button class="hq-modal-close">✕</button>
      </div>
      <div class="hq-modal-original">
        <div class="hq-modal-label">ORIGINAL — ${tweetData.author} ${tweetData.handle}</div>
        <div class="hq-modal-source-text">${tweetData.text}</div>
      </div>
      <div class="hq-modal-label" style="margin-top:14px;">YOUR VERSION</div>
      <textarea class="hq-modal-textarea" placeholder="Write your repurposed version..." rows="5">${tweetData.text}</textarea>
      <div class="hq-modal-actions">
        <button class="hq-modal-btn hq-modal-ai" id="hq-ai-btn">⚡ Generate with AI</button>
        <button class="hq-modal-btn hq-modal-save" id="hq-save-draft-btn">Save Draft</button>
      </div>
      <div class="hq-modal-status" id="hq-modal-status"></div>
    </div>
  `;
  document.body.appendChild(modal);

  const backdrop = modal.querySelector(".hq-modal-backdrop");
  const closeBtn = modal.querySelector(".hq-modal-close");
  const textarea = modal.querySelector(".hq-modal-textarea");
  const aiBtn = modal.querySelector("#hq-ai-btn");
  const saveBtn = modal.querySelector("#hq-save-draft-btn");
  const status = modal.querySelector("#hq-modal-status");

  function close() { modal.remove(); }
  backdrop.addEventListener("click", close);
  closeBtn.addEventListener("click", close);

  aiBtn.addEventListener("click", async () => {
    aiBtn.disabled = true;
    aiBtn.textContent = "Generating...";
    status.textContent = "";
    try {
      const result = await callProxy("/call", {
        prompt: `You are Tyler Polumbus — former NFL player turned sports media personality. Repurpose this tweet in your voice: direct, no hashtags, ellipsis signature, former-player authority. Give ONLY the tweet text, nothing else.\n\nOriginal tweet by ${tweetData.author}:\n"${tweetData.text}"`
      });
      if (result.text) {
        textarea.value = result.text;
      } else {
        status.textContent = "AI failed — write it yourself";
        status.style.color = "#ff4444";
      }
    } catch (e) {
      status.textContent = "Proxy unreachable";
      status.style.color = "#ff4444";
    }
    aiBtn.disabled = false;
    aiBtn.textContent = "⚡ Generate with AI";
  });

  saveBtn.addEventListener("click", async () => {
    const draftText = textarea.value.trim();
    if (!draftText) return;
    saveBtn.disabled = true;
    saveBtn.textContent = "Saving...";
    try {
      await callProxy("/save-tweet", {
        type: "repurpose",
        tweet: {
          ...tweetData,
          repurposed_text: draftText,
        }
      });
      status.textContent = "Saved to repurpose queue!";
      status.style.color = "#22c55e";
      setTimeout(close, 1500);
    } catch (e) {
      status.textContent = "Save failed";
      status.style.color = "#ff4444";
      saveBtn.disabled = false;
      saveBtn.textContent = "Save Draft";
    }
  });
}

// ── Reply Modal ───────────────────────────────────────────────────────────────

async function openReplyModal(tweetElement) {
  const tweetData = extractTweetData(tweetElement);

  // Remove any existing HQ reply modal
  const existing = document.getElementById("hq-reply-modal");
  if (existing) existing.remove();

  const modal = document.createElement("div");
  modal.id = "hq-reply-modal";
  modal.innerHTML = `
    <div class="hq-modal-backdrop"></div>
    <div class="hq-modal-box">
      <div class="hq-modal-header">
        <span class="hq-modal-title">AI REPLY</span>
        <button class="hq-modal-close">✕</button>
      </div>
      <div class="hq-modal-original">
        <div class="hq-modal-label">REPLYING TO — ${tweetData.author} ${tweetData.handle}</div>
        <div class="hq-modal-source-text">${tweetData.text}</div>
      </div>
      <div class="hq-modal-label" style="margin-top:14px;">YOUR REPLY</div>
      <textarea class="hq-modal-textarea" placeholder="Generating reply..." rows="4"></textarea>
      <div class="hq-modal-actions">
        <button class="hq-modal-btn hq-modal-ai" id="hq-reply-regen-btn">⚡ Regenerate</button>
        <button class="hq-modal-btn hq-modal-save" id="hq-reply-post-btn">↗ Post Reply</button>
      </div>
      <div class="hq-modal-status" id="hq-reply-status"></div>
    </div>
  `;
  document.body.appendChild(modal);

  const backdrop = modal.querySelector(".hq-modal-backdrop");
  const closeBtn = modal.querySelector(".hq-modal-close");
  const textarea = modal.querySelector(".hq-modal-textarea");
  const regenBtn = modal.querySelector("#hq-reply-regen-btn");
  const postBtn = modal.querySelector("#hq-reply-post-btn");
  const status = modal.querySelector("#hq-reply-status");

  function close() { modal.remove(); }
  backdrop.addEventListener("click", close);
  closeBtn.addEventListener("click", close);

  async function generateReply() {
    regenBtn.disabled = true;
    regenBtn.textContent = "Generating...";
    textarea.placeholder = "Generating...";
    status.textContent = "";
    try {
      const result = await callProxy("/call", {
        prompt: `You are Tyler Polumbus — former NFL player turned sports media personality. Write a short reply to this tweet in your voice: direct, conversational, no hashtags, former-player authority, occasionally uses ellipsis. Keep it under 220 characters. Give ONLY the reply text, nothing else.\n\nTweet by ${tweetData.author} (${tweetData.handle}):\n"${tweetData.text}"`
      });
      if (result.text) {
        textarea.value = result.text;
        textarea.placeholder = "";
      } else {
        status.textContent = "AI failed — write it yourself";
        status.style.color = "#ff4444";
        textarea.placeholder = "Write your reply...";
      }
    } catch (e) {
      status.textContent = "Proxy unreachable";
      status.style.color = "#ff4444";
      textarea.placeholder = "Write your reply...";
    }
    regenBtn.disabled = false;
    regenBtn.textContent = "⚡ Regenerate";
  }

  // Auto-generate on open
  generateReply();
  regenBtn.addEventListener("click", generateReply);

  postBtn.addEventListener("click", async () => {
    const replyText = textarea.value.trim();
    if (!replyText) return;

    // Click X's native reply button to open compose box
    const nativeReplyBtn = tweetElement.querySelector('[data-testid="reply"]');
    if (nativeReplyBtn) {
      nativeReplyBtn.click();
      // Wait for X's compose box to appear, then inject text
      let attempts = 0;
      const inject = setInterval(() => {
        attempts++;
        const composeBox = document.querySelector('[data-testid="tweetTextarea_0"]');
        if (composeBox) {
          clearInterval(inject);
          composeBox.focus();
          // Use execCommand to properly trigger React's onChange
          document.execCommand("selectAll", false, null);
          document.execCommand("insertText", false, replyText);
          close();
        } else if (attempts > 30) {
          clearInterval(inject);
          status.textContent = "Could not find X's compose box";
          status.style.color = "#ff4444";
        }
      }, 100);
    } else {
      status.textContent = "Could not find reply button on tweet";
      status.style.color = "#ff4444";
    }
  });
}

// ── Use Signal ───────────────────────────────────────────────────────────────

const HQ_APP_URL = "https://polumbus-hq.streamlit.app";

function useSignal(tweetElement) {
  const data = extractTweetData(tweetElement);

  // Extract reply count from metrics group
  const metricsGroup = tweetElement.querySelector('[role="group"]');
  let replies = 0;
  if (metricsGroup) {
    const replyBtn = metricsGroup.querySelector('[data-testid="reply"]');
    if (replyBtn) {
      const val = parseInt(replyBtn.innerText.replace(/[,K.M]/g, "")) || 0;
      replies = val;
    }
  }

  // Build URL params for Signals & Prompts page
  const params = new URLSearchParams({
    page: "Signals & Prompts",
    sig_text: data.text.substring(0, 500),
    sig_author: data.handle.replace("@", ""),
    sig_replies: replies.toString(),
    sig_rts: data.retweets.toString(),
    sig_likes: data.likes.toString(),
    sig_url: data.tweet_url,
  });

  window.open(`${HQ_APP_URL}/?${params.toString()}`, "_blank");
}

// ── Buttons ──────────────────────────────────────────────────────────────────

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
    saveBtn.textContent = "Saving...";
    try {
      await callProxy("/save-tweet", { type: "inspiration", tweet: extractTweetData(tweetElement) });
      saveBtn.textContent = "Saved!";
      saveBtn.classList.add("hq-saved");
    } catch {
      saveBtn.textContent = "Error";
    }
    setTimeout(() => { saveBtn.textContent = "Save"; saveBtn.classList.remove("hq-saved"); }, 2000);
  };

  const repurposeBtn = document.createElement("button");
  repurposeBtn.className = "hq-btn hq-repurpose";
  repurposeBtn.textContent = "Repurpose";
  repurposeBtn.title = "Repurpose this tweet";
  repurposeBtn.onclick = (e) => {
    e.stopPropagation();
    e.preventDefault();
    openRepurposeModal(extractTweetData(tweetElement));
  };

  const replyBtn = document.createElement("button");
  replyBtn.className = "hq-btn hq-reply";
  replyBtn.textContent = "Reply";
  replyBtn.title = "Generate AI reply";
  replyBtn.onclick = (e) => {
    e.stopPropagation();
    e.preventDefault();
    openReplyModal(tweetElement);
  };

  const signalBtn = document.createElement("button");
  signalBtn.className = "hq-btn hq-signal";
  signalBtn.textContent = "Signal";
  signalBtn.title = "Use as signal in HQ";
  signalBtn.onclick = (e) => {
    e.stopPropagation();
    e.preventDefault();
    signalBtn.textContent = "Opening...";
    useSignal(tweetElement);
    setTimeout(() => { signalBtn.textContent = "Signal"; }, 2000);
  };

  container.appendChild(saveBtn);
  container.appendChild(repurposeBtn);
  container.appendChild(replyBtn);
  container.appendChild(signalBtn);
  metricsGroup.parentElement.appendChild(container);
}

function scanTweets() {
  const tweets = document.querySelectorAll('[data-testid="tweet"]');
  tweets.forEach(createHQButtons);
}

const observer = new MutationObserver(scanTweets);
observer.observe(document.body, { childList: true, subtree: true });
setInterval(scanTweets, 2000);
