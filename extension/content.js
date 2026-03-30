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

const TYLER_SYSTEM = `You are a content assistant for Tyler Polumbus — former NFL offensive lineman, Super Bowl 50 champion with the Denver Broncos, and current sports media personality.

Tyler's profile:
- Played 8 NFL seasons as an undrafted free agent, started 60+ games
- Host of The PhD Show on Altitude 92.5 radio (Denver)
- Runs Mount Polumbus podcast/YouTube channel
- Colorado native, deep Denver sports loyalist
- Covers Broncos (primary ~80%), Nuggets, Avalanche, CU Buffs
- Communication style: direct, blunt, no fluff, former-player perspective

Tyler's voice on X:
- Short punchy sentences. Never sounds like a press release.
- Uses "we" when talking Broncos — it's personal
- Hot takes backed by real football knowledge
- Doesn't hedge. If he thinks something, he says it.
- Occasional humor but never tries too hard
- Never uses emojis or hashtags
- Keeps tweets under 200 characters when possible for max punch`;

function buildRepurposePrompt(tweetData) {
  return `You are helping Tyler repurpose someone else's tweet into his own original content. The goal: take the UNDERLYING IDEA and write it as if Tyler came up with it himself. Nobody should be able to trace it back to the original.

Source tweet (NOT Tyler's — do NOT copy ANY phrasing, structure, or sentence patterns): "${tweetData.text}"

REPURPOSING RULES:
- Extract the core IDEA or TAKE — then throw away everything else about the original tweet.
- Write in Tyler's voice with completely different wording, structure, and angle of attack.
- Tyler's version should feel like his own original thought — NOT a paraphrase.
- Change the entry point: if the original leads with a stat, Tyler leads with an observation (or vice versa).
- If the original names a player/team, Tyler can reference the same subject but frame it from his former-player perspective.
- Zero overlap in phrasing. If someone put them side by side, they should look like two people independently had the same thought.

- Strong hook in the first line
- Invites engagement/replies
- No hashtags, no emojis, no character count
- 7th-9th grade reading level

Return ONLY the tweet text. No quotes, no preamble, no explanation.`;
}

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
      <textarea class="hq-modal-textarea" placeholder="Write your repurposed version..." rows="5"></textarea>
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
        prompt: buildRepurposePrompt(tweetData),
        system: TYLER_SYSTEM,
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

function buildReplyPrompt(tweetData) {
  return `Tyler Polumbus needs to reply to this tweet. Goal: engagement farming — Tyler's reply should get likes and replies on its own.

Tweet by ${tweetData.author} (${tweetData.handle}):
"${tweetData.text}"

STEP 1 — CLASSIFY the tweet:
- NEWS BREAK: reporter sharing new information
- HOT TAKE: opinion/argument about a team or player
- QUESTION: asking the audience something
- STAT DUMP: sharing numbers or data
- JOKE/MEME: humor or cultural reference
- HIGHLIGHT: sharing a play, clip, or moment

STEP 2 — WRITE TWO REPLIES using these angles:

OPTION A — AGREE & AMPLIFY:
- Co-sign the take, then raise the stakes higher
- Add insider context the original poster doesn't have
- Make people who agree with the original tweet ALSO want to like Tyler's reply
- Strategy: "Yes, and here's what people are missing..."

OPTION B — PUSH BACK:
- Respectful disagreement with specific reasoning
- Use former-player authority to challenge the framing
- Make people who DISAGREE with the original tweet rally behind Tyler's reply
- Strategy: "I hear you, but from inside the building..."

RULES FOR BOTH:
- Under 180 characters each — punchy, not wordy
- First 5 words must hook — people scroll replies fast
- The reply must work as a standalone tweet if someone only sees Tyler's reply without the parent
- End with something that makes OTHER people reply to Tyler's reply
- No hashtags, no emojis, no "great point" filler
- Tyler's voice: direct, former-player authority, occasionally uses ellipsis
- Logical connection to the original tweet — don't ignore what they said

Return ONLY this format, no other text:
AGREE: [reply text]
PUSH BACK: [reply text]`;
}

async function openReplyModal(tweetElement) {
  const tweetData = extractTweetData(tweetElement);

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
      <div class="hq-modal-label" style="margin-top:14px;">OPTION A — AGREE & AMPLIFY</div>
      <div class="hq-reply-option" id="hq-reply-a" style="background:#1a1a2e;border:1px solid #2a2a4a;border-radius:8px;padding:12px;color:#e8e8f0;font-size:14px;line-height:1.5;cursor:pointer;transition:border-color 0.15s;margin-bottom:8px;min-height:40px;">Generating...</div>
      <div class="hq-modal-label">OPTION B — PUSH BACK</div>
      <div class="hq-reply-option" id="hq-reply-b" style="background:#1a1a2e;border:1px solid #2a2a4a;border-radius:8px;padding:12px;color:#e8e8f0;font-size:14px;line-height:1.5;cursor:pointer;transition:border-color 0.15s;margin-bottom:8px;min-height:40px;">Generating...</div>
      <div class="hq-modal-label" style="margin-top:14px;">YOUR REPLY (edit and copy)</div>
      <textarea class="hq-modal-textarea" placeholder="Click an option above or write your own..." rows="3"></textarea>
      <div class="hq-modal-actions">
        <button class="hq-modal-btn hq-modal-ai" id="hq-reply-regen-btn">⚡ Regenerate</button>
        <button class="hq-modal-btn hq-modal-save" id="hq-reply-copy-btn">📋 Copy</button>
      </div>
      <div class="hq-modal-status" id="hq-reply-status"></div>
    </div>
  `;
  document.body.appendChild(modal);

  const backdrop = modal.querySelector(".hq-modal-backdrop");
  const closeBtn = modal.querySelector(".hq-modal-close");
  const optionA = modal.querySelector("#hq-reply-a");
  const optionB = modal.querySelector("#hq-reply-b");
  const textarea = modal.querySelector(".hq-modal-textarea");
  const regenBtn = modal.querySelector("#hq-reply-regen-btn");
  const copyBtn = modal.querySelector("#hq-reply-copy-btn");
  const status = modal.querySelector("#hq-reply-status");

  function close() { modal.remove(); }
  backdrop.addEventListener("click", close);
  closeBtn.addEventListener("click", close);

  // Click option to select it
  function selectOption(el) {
    optionA.style.borderColor = "#2a2a4a";
    optionB.style.borderColor = "#2a2a4a";
    el.style.borderColor = "#2DD4BF";
    textarea.value = el.textContent;
  }
  optionA.addEventListener("click", () => selectOption(optionA));
  optionB.addEventListener("click", () => selectOption(optionB));

  async function generateReplies() {
    regenBtn.disabled = true;
    regenBtn.textContent = "Generating...";
    optionA.textContent = "Generating...";
    optionB.textContent = "Generating...";
    textarea.value = "";
    status.textContent = "";
    try {
      const result = await callProxy("/call", {
        prompt: buildReplyPrompt(tweetData),
        system: TYLER_SYSTEM,
      });
      if (result.text) {
        const text = result.text.trim();
        // Parse AGREE: ... and PUSH BACK: ...
        const agreeMatch = text.match(/AGREE:\s*(.+?)(?=\nPUSH BACK:|$)/s);
        const pushMatch = text.match(/PUSH BACK:\s*(.+?)$/s);
        const agreeText = agreeMatch ? agreeMatch[1].trim() : "";
        const pushText = pushMatch ? pushMatch[1].trim() : "";

        if (agreeText) {
          optionA.textContent = agreeText;
        } else {
          optionA.textContent = "Could not generate — write your own";
        }
        if (pushText) {
          optionB.textContent = pushText;
        } else {
          optionB.textContent = "Could not generate — write your own";
        }
        // Auto-select option A
        if (agreeText) selectOption(optionA);
      } else {
        optionA.textContent = "AI failed — write your own";
        optionB.textContent = "AI failed — write your own";
        status.textContent = "AI failed";
        status.style.color = "#ff4444";
      }
    } catch (e) {
      optionA.textContent = "Proxy unreachable";
      optionB.textContent = "Proxy unreachable";
      status.textContent = "Proxy unreachable";
      status.style.color = "#ff4444";
    }
    regenBtn.disabled = false;
    regenBtn.textContent = "⚡ Regenerate";
  }

  // Auto-generate on open
  generateReplies();
  regenBtn.addEventListener("click", generateReplies);

  copyBtn.addEventListener("click", async () => {
    const replyText = textarea.value.trim();
    if (!replyText) return;
    try {
      await navigator.clipboard.writeText(replyText);
      copyBtn.textContent = "Copied!";
      status.textContent = "Copied to clipboard — paste into your reply";
      status.style.color = "#22c55e";
      setTimeout(() => { copyBtn.textContent = "📋 Copy"; }, 2000);
    } catch (e) {
      // Fallback: select the textarea text
      textarea.select();
      status.textContent = "Text selected — Ctrl+C to copy";
      status.style.color = "#FBBF24";
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
