import { expect, type Page, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

function readPublicSupabaseUrl() {
  if (process.env.NEXT_PUBLIC_SUPABASE_URL) {
    return process.env.NEXT_PUBLIC_SUPABASE_URL;
  }

  const envPath = path.join(process.cwd(), ".env.local");
  if (!fs.existsSync(envPath)) {
    return undefined;
  }

  const match = fs
    .readFileSync(envPath, "utf8")
    .match(/^NEXT_PUBLIC_SUPABASE_URL=(.+)$/m);

  return match?.[1]?.trim().replace(/^["']|["']$/g, "");
}

async function selectRailTool(page: Page, name: string) {
  await page
    .getByRole("navigation", { name: "Workspace sections" })
    .getByRole("button", { name })
    .first()
    .evaluate((button: HTMLButtonElement) => button.click());
}

async function openOwnerPreviewTool(page: Page, path: string) {
  await page.goto("/login");
  await page.getByRole("button", { name: "Owner Preview" }).click();
  await expect(page).toHaveURL(/\/app\/creator-evolution$/);
  await page.goto(path);
}

test("marketing home loads", async ({ page }) => {
  await page.goto("/landing");
  await expect(
    page.getByRole("heading", {
      name: "A creator operating system for posts that still sound like you.",
    }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Start workspace setup" }).first()).toHaveAttribute(
    "href",
    "/app/onboarding",
  );
  await expect(
    page.getByRole("heading", { name: "Clear packaging with simple workspace setup." }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Start workspace setup" }).nth(1)).toHaveAttribute(
    "href",
    "/app/onboarding?plan=starter",
  );
  await expect(
    page.getByRole("heading", {
      name: "Open the Post Ascend website app and continue through the real workspace flow.",
    }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Open the app" }).first()).toHaveAttribute(
    "href",
    "/app/creator-studio",
  );
});

test("public preview query loads the preserved app shell", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Creator Studio" })).toBeVisible();

  const appNav = page.getByRole("navigation", { name: "Workspace sections" });
  await expect(appNav.getByRole("button", { name: "Creator Studio" }).first()).toBeVisible();
  await expect(appNav.getByRole("button", { name: "Reply Mode" }).first()).toBeVisible();
  await expect(appNav.getByRole("button", { name: "My Stats" }).first()).toBeVisible();
  await expect(appNav.getByRole("button", { name: "Signals & Prompts" })).toHaveCount(0);
  await expect(appNav.getByRole("button", { name: "Podcast" })).toHaveCount(0);
  await expect(appNav.getByRole("button", { name: "Creator Evolution" })).toHaveCount(0);
  await expect(appNav.getByRole("button", { name: "Voice Tuner" })).toHaveCount(0);
  await expect(appNav.getByRole("button", { name: "10/10 Audit" })).toHaveCount(0);
  await expect(appNav.getByRole("link", { name: "Gameday Mode" })).toHaveCount(0);
  await expect(appNav.getByRole("button", { name: "Debug Console" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Go Viral" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Grades" })).toBeVisible();
});

test("public root swaps through real app-matched workbench pages", async ({ page }) => {
  await page.goto("/");

  const checks = [
    { button: "Creator Studio", marker: page.locator('[data-testid="creator-input"]') },
    { button: "Raw Thoughts", marker: page.locator('[data-testid="raw-thoughts-input"]') },
    { button: "Content Coach", marker: page.locator('[data-testid="content-coach-input"]') },
    { button: "Article Writer", marker: page.locator('[data-testid="article-writer-action-write"]') },
    { button: "Reply Mode", marker: page.getByText("Today's Replies") },
    { button: "Idea Bank", marker: page.locator('[data-testid="idea-bank-list"]') },
    { button: "Post History", marker: page.locator('[data-testid="post-history-list"]') },
    { button: "Algorithm Score", marker: page.locator('[data-testid="algorithm-score-input"]') },
    { button: "Account Audit", marker: page.getByRole("button", { exact: true, name: "Audit" }) },
    { button: "My Stats", marker: page.locator('[data-testid="my-stats-top-posts"]') },
    { button: "Profile Analyzer", marker: page.locator('[data-testid="profile-analyzer-handle"]') },
  ];

  for (const check of checks) {
    await selectRailTool(page, check.button);
    await expect(check.marker).toBeVisible();
  }

  const appNav = page.getByRole("navigation", { name: "Workspace sections" });
  await expect(appNav.getByRole("link", { name: "Gameday Mode" })).toHaveCount(0);
  await expect(appNav.getByRole("button", { name: "Debug Console" })).toHaveCount(0);
});

test("public root uses app shell chrome and keeps handoffs in-page", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("navigation", { name: "Workspace sections" })).toBeVisible();
  await page.locator('[data-testid="creator-input"]').fill("One strong seed for Idea Bank handoff.");
  await page.getByRole("button", { name: "Build" }).click();
  await expect(page.locator('[data-testid="creator-result-panel"]')).toBeVisible();
  await page.getByRole("link", { name: /Open Idea Bank/i }).first().click();
  await expect(page.locator('[data-testid="idea-bank-list"]')).toBeVisible();
});

test("public root stays on website preview for signed-in browser sessions", async ({ page }) => {
  const supabaseUrl = readPublicSupabaseUrl();
  if (!supabaseUrl) {
    test.skip(true, "Supabase URL is required to seed browser auth storage.");
    return;
  }

  const projectRef = new URL(supabaseUrl).hostname.split(".")[0];
  const storageKey = `sb-${projectRef}-auth-token`;
  const expiresAt = Math.floor(Date.now() / 1000) + 60 * 60;

  await page.route("**/api/auth/sync-session", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true }),
    });
  });

  await page.addInitScript(
    ({ key, expiresAt: seededExpiresAt }) => {
      window.localStorage.setItem(
        key,
        JSON.stringify({
          access_token: "seeded-public-root-access-token",
          refresh_token: "seeded-public-root-refresh-token",
          token_type: "bearer",
          expires_at: seededExpiresAt,
          expires_in: 3600,
          user: {
            id: "public-root-preview-user",
            aud: "authenticated",
            role: "authenticated",
            email: "preview@example.com",
          },
        }),
      );
    },
    { key: storageKey, expiresAt },
  );

  await page.goto("/?page=Creator+Studio");
  await expect(page.locator('[data-testid="creator-input"]')).toBeVisible();
  await expect(page).toHaveURL(/\/\?page=Creator\+Studio$/);
  await page.waitForTimeout(1500);
  await expect(page).toHaveURL(/\/\?page=Creator\+Studio$/);
});

test("public root handles reply handoff and malformed preview storage safely", async ({ page }) => {
  await page.goto("/?preview=workspace");
  await page.evaluate(() => {
    window.localStorage.setItem("postascend.preview-vault.items", JSON.stringify([{ tags: {} }]));
    window.localStorage.setItem("postascend.raw-thoughts.dumps", JSON.stringify([{}]));
  });

  await page.reload();
  await selectRailTool(page, "Raw Thoughts");
  await expect(page.locator('[data-testid="raw-thoughts-input"]')).toBeVisible();
  await selectRailTool(page, "Idea Bank");
  await expect(page.locator('[data-testid="idea-bank-list"]')).toBeVisible();

  await selectRailTool(page, "Reply Mode");
  await page.getByRole("button", { name: "Load" }).click();
  await page.locator('[data-testid="reply-mode-feed"] button').first().click();
  await page.locator('[data-testid^="reply-mode-option-"]').first().click();
  await page.getByRole("button", { name: "Use in Creator Studio" }).click();
  await expect(page).toHaveURL(/\/\?page=Creator\+Studio$/);
  await expect(page.locator('[data-testid="creator-input"]')).toHaveValue(/.+/);
});

test("public root rejects owner-only workflow deep-links", async ({ page }) => {
  await page.goto("/?tool=signals-prompts&sig_text=Imported%20signal%20from%20X&sig_author=beat_writer&sig_likes=12&sig_replies=3&sig_rts=2");
  await expect(page.getByRole("heading", { name: "Creator Studio" })).toBeVisible();
  await expect(page.getByText("Imported signal from X")).toHaveCount(0);

  await page.goto("/?tool=podcast&run=podcast-episode-042-building-the-product-while-flying-it&state=ready_to_publish");
  await expect(page.getByRole("heading", { name: "Creator Studio" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Podcast Workflow" })).toHaveCount(0);

  await page.goto("/?page=Creator+Evolution");
  await expect(page.getByRole("heading", { name: "Creator Studio" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Creator Evolution" })).toHaveCount(0);
});

test("extension fallback handoffs open the public website preview", async ({ page }) => {
  const checks = [
    {
      action: "save-tweet",
      expectedTool: "idea-bank",
      payload: { tweet: { text: "Save this public root signal.", handle: "source" } },
    },
    {
      action: "save-repurpose",
      expectedTool: "creator-studio",
      payload: { tweet: { text: "Rewrite this public root signal.", handle: "source" } },
    },
    {
      action: "open-reply",
      expectedTool: "reply-mode",
      payload: { tweet: { text: "Reply to this public root signal.", handle: "source" } },
    },
    {
      action: "open-signal",
      expectedPathname: "/app/signals-prompts",
      payload: { tweet: { text: "Promote this public root signal.", handle: "source" } },
    },
  ];

  for (const check of checks) {
    const response = await page.request.post(`/api/extension/${check.action}`, {
      data: check.payload,
    });
    const body = (await response.json()) as {
      ok: boolean;
      data?: {
        openUrl?: string;
      };
    };

    expect(response.ok()).toBeTruthy();
    expect(body.ok).toBeTruthy();
    const openUrl = new URL(body.data?.openUrl ?? "");
    if ("expectedPathname" in check) {
      expect(openUrl.pathname).toBe(check.expectedPathname);
    } else {
      expect(openUrl.pathname).toBe("/");
      expect(openUrl.searchParams.get("tool")).toBe(check.expectedTool);
    }
  }
});

test("login page can open a guest preview session", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Guest Preview" }).click();
  await expect(
    page.getByRole("heading", { name: "Guest setup can be previewed end to end" }),
  ).toBeVisible();
  await page.goto("/app");
  await expect(page.getByText("Preview Guest")).toBeVisible();
  await expect(page.getByText("Signals & Prompts")).toHaveCount(0);
});

test("active preview sessions redirect away from login", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Owner Preview" }).click();
  await page.goto("/login").catch(() => undefined);
  await expect(page).toHaveURL(/\/app\/creator-evolution$/);
});

test("guest onboarding completion updates the app shell profile", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Guest Preview" }).click();
  const handleInput = page.getByPlaceholder("@yourhandle");
  const displayNameInput = page.getByPlaceholder("Display name");
  await handleInput.fill("@milehighguest");
  await expect(handleInput).toHaveValue("@milehighguest");
  await displayNameInput.fill("Mile High Guest");
  await expect(displayNameInput).toHaveValue("Mile High Guest");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.getByText("Claim a legacy import if one matches")).toBeVisible();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.getByText("Choose your niche, topics, and feeds")).toBeVisible();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.getByText("X verification, tweet-history sync, and voice analysis stay pending")).toBeVisible();
  await page.getByRole("button", { name: "Complete Setup" }).click();
  await expect(page.getByText("Mile High Guest")).toBeVisible();
  await expect(page.getByText("@milehighguest", { exact: true })).toBeVisible();
  await expect(page.getByText("complete").first()).toBeVisible();
});

test("app shell preview renders", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Owner Preview" }).click();
  await expect(page).toHaveURL(/\/app\/creator-evolution$/);
  await expect(page.getByLabel("Creator Evolution seed")).toBeVisible();
  await expect(page.getByText("Active Creator Evolution Rules")).toBeVisible();
});



test("owner Voice Tuner preview reflects structured feedback gates", async ({ page }) => {
  await page.goto("/login");
  const ownerPreview = page.getByRole("button", { name: "Owner Preview" });
  test.skip((await ownerPreview.count()) === 0, "Local preview auth is unavailable in this runtime.");
  await ownerPreview.click();
  await expect(page).toHaveURL(/\/app\/creator-evolution$/);
  await page.goto("/app/voice-tuner");
  await expect(page.getByText("Structured Feedback Gate")).toBeVisible();
  await expect(page.getByPlaceholder("Paste the test concept. Feedback is compiled into scoped structured rules before tuning.")).toBeVisible();
  await page.getByRole("button", { name: "Generate A/B Test" }).click();
  await expect(page.getByText("route metadata")).toBeVisible();
  await expect(page.getByText("feedback score")).toBeVisible();
  await page.getByRole("button", { name: "Apply Live" }).click();
  await expect(page.getByText("matching scoped rule hash")).toBeVisible();
});

test("creator studio preview actions render structured results", async ({ page }) => {
  await page.goto("/app/creator-studio");
  await page.getByTestId("creator-input").fill(
    "Bo Nix looks more comfortable attacking the middle of the field and the whole offense feels faster because of it.",
  );
  await page.getByTestId("creator-action-banger").click();
  await expect(page.getByTestId("creator-result-panel")).toBeVisible();
  await expect(page.getByText("High-performance draft options")).toBeVisible();
  await page.getByTestId("creator-action-grades").click();
  await expect(page.getByText("Algorithm score", { exact: true })).toBeVisible();
  await expect(page.getByText("Voice score", { exact: true })).toBeVisible();
});

test("creator studio save flows into idea bank", async ({ page }) => {
  await page.goto("/?preview=workspace");
  await page.getByTestId("creator-input").fill(
    "Nikola Jokic controls pace better than anyone in the league because he never lets the defense speed him up.",
  );
  await page.getByRole("button", { name: "Save Draft" }).click();
  await page.getByRole("link", { name: "Open Idea Bank" }).click();
  await expect(page.getByRole("heading", { name: "Idea Bank" })).toBeVisible();
  await expect(page.getByTestId("idea-bank-list")).toContainText(
    "Nikola Jokic controls pace better than anyone in the league",
  );
});

test("idea bank imports an extension handoff from query params", async ({ page }) => {
  await page.goto(
    "/app/idea-bank?add=inspiration&text=The%20best%20creators%20repeat%20one%20sharp%20belief.&author=%40brandbuilderhq&tags=hook,positioning&likes=1200",
  );
  await expect(page.getByText("Imported a tweet from the extension into Idea Bank.")).toBeVisible();
  await expect(page.getByTestId("idea-bank-list")).toContainText(
    "The best creators repeat one sharp belief.",
  );
});

test("raw thoughts generates output and hands off to creator studio", async ({ page }) => {
  await page.goto("/app/raw-thoughts");
  await page.getByTestId("raw-thoughts-input").fill(
    "The offense looks calmer when the quarterback gets the ball out early and forces the defense to declare coverage faster.",
  );
  await page.getByTestId("raw-thoughts-action-ideas").click();
  await expect(page.getByTestId("raw-thoughts-result")).toBeVisible();
  await page.getByRole("link", { name: "Use in Creator Studio" }).click();
  await expect(page.getByTestId("creator-input")).toBeVisible();
  await expect(page.getByTestId("creator-input")).toContainText("Strong opinion");
});

test("article writer creates a draft from scratch", async ({ page }) => {
  await page.goto("/app/article-writer");
  await page.getByRole("button", { name: "Scratch" }).click();
  await page.getByTestId("article-writer-scratch").fill(
    "Why the offense finally looks built around its quarterback instead of asking him to mimic someone else.",
  );
  await page.getByTestId("article-writer-action-write").click();
  await expect(page.getByTestId("article-writer-result")).toBeVisible();
  await expect(page.getByText("Companion post idea")).toBeVisible();
});

test("content coach creates a conversation from a starter prompt", async ({ page }) => {
  await page.goto("/app/content-coach");
  await page.locator("select.mp-input").selectOption("What should I write about today?");
  await expect(page.getByTestId("content-coach-thread")).toContainText(
    "The clearest move is to build around",
  );
});

test("algorithm score grades a draft", async ({ page }) => {
  await openOwnerPreviewTool(page, "/app/algorithm-score");
  await page.getByTestId("algorithm-score-input").fill(
    "The offense finally looks built around what the quarterback does best instead of forcing him into borrowed structure.",
  );
  await page.getByTestId("algorithm-score-run").click();
  await expect(page.getByTestId("algorithm-score-result")).toContainText("Algorithm Score");
});

test("post history shows imported legacy tweets", async ({ page }) => {
  await page.goto("/?page=Post+History");
  await expect(page.getByRole("heading", { name: "Your Post History" })).toBeVisible();
  await expect(page.getByTestId("post-history-list")).toContainText(
    "The local team did not just make a transaction.",
  );
});

test("my stats renders imported account metrics", async ({ page }) => {
  await page.goto("/?page=My+Stats");
  await expect(page.getByRole("heading", { name: "My Stats" })).toBeVisible();
  await expect(page.getByTestId("my-stats-top-posts")).toContainText("#1");
  await expect(page.getByText("Engagement Rate")).toBeVisible();
});

test("account audit renders recommendations", async ({ page }) => {
  await page.goto("/?page=Account+Audit");
  await expect(page.getByRole("heading", { name: "Account Audit" })).toBeVisible();
  await page.getByRole("button", { exact: true, name: "Audit" }).click();
  await expect(page.getByTestId("account-audit-sections")).toContainText(
    "Posting consistency",
  );
});

test("reply mode tracks a reply action", async ({ page }) => {
  await page.goto("/?page=Reply+Mode");
  await expect(page.getByRole("heading", { name: "Reply Mode" })).toBeVisible();
  await page.getByRole("button", { name: "Load" }).click();
  await page.locator('[data-testid="reply-mode-feed"] button').first().click();
  await page.getByTestId("reply-mode-option-0").click();
  await expect(page.getByTestId("reply-mode-editor")).toContainText("Exactly.");
  await page.getByTestId("reply-mode-mark-replied").click();
  await expect(page.getByText("Reply logged.")).toBeVisible();
  await page.getByTestId("reply-mode-mark-replied").click();
  await expect(page.getByText("reconciled today's reply count")).toBeVisible();
});

test("reply mode accepts an imported tweet from query params", async ({ page }) => {
  await openOwnerPreviewTool(
    page,
    "/app/reply-mode?text=The%20best%20offenses%20make%20the%20answer%20feel%20early.&author=FilmRoom&authorName=Film%20Room&likes=420&replies=18",
  );
  await expect(page.getByTestId("reply-mode-feed").getByText("Imported a tweet from X.")).toBeVisible();
  await expect(page.getByTestId("reply-mode-feed")).toContainText(
    "The best offenses make the answer feel early.",
  );
});

test("guest preview cannot open owner-only routes directly", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Guest Preview" }).click();
  await page.goto("/app/debug-console").catch(() => undefined);
  await expect(page).toHaveURL(/\/app\/onboarding$/);
  await expect(
    page.getByRole("heading", { name: "Guest setup can be previewed end to end" }),
  ).toBeVisible();
});

test("completed guest preview still cannot open owner-only routes directly", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Guest Preview" }).click();

  await page.getByPlaceholder("@yourhandle").fill("@milehighguest");
  await page.getByPlaceholder("Display name").fill("Mile High Guest");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Complete Setup" }).click();
  await expect(page).toHaveURL(/\/app\/creator-studio$/);

  await page.goto("/app/debug-console");
  await expect(
    page.getByRole("heading", { name: "Debug Console is reserved for owner accounts." }),
  ).toBeVisible();
  await page.goto("/app/signals-prompts");
  await expect(
    page.getByRole("heading", { name: "Signals & Prompts is reserved for owner accounts." }),
  ).toBeVisible();
});

test("invalid preview role cookie does not grant owner access", async ({ context, page }) => {
  await context.addCookies([
    {
      name: "postascend-preview-role",
      value: "ownerish",
      domain: "127.0.0.1",
      path: "/",
    },
  ]);

  await page.goto("/app/debug-console");
  await expect(
    page.getByRole("heading", { name: "Debug Console is reserved for owner accounts." }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Owner runtime checks and launch readiness" }),
  ).toHaveCount(0);
});

test("new guest preview clears stale completed onboarding cookies", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Guest Preview" }).click();

  await page.getByPlaceholder("@yourhandle").fill("@milehighguest");
  await page.getByPlaceholder("Display name").fill("Mile High Guest");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Complete Setup" }).click();
  await expect(page).toHaveURL(/\/app\/creator-studio$/);

  await Promise.all([
    page.waitForURL(/\/login$/, { timeout: 5000 }).catch(() => undefined),
    page.getByRole("button", { name: "Sign out" }).click(),
  ]);
  if (!/\/login$/.test(page.url())) {
    await page.goto("/login").catch(() => undefined);
  }
  await page.getByRole("button", { name: "Guest Preview" }).click();

  await expect(page).toHaveURL(/\/app\/onboarding$/);
  await expect(
    page.getByRole("heading", { name: "Guest setup can be previewed end to end" }),
  ).toBeVisible();
});

test("malformed preview profile cookie is ignored", async ({ context, page }) => {
  await context.addCookies([
    {
      name: "postascend-preview-role",
      value: "owner",
      domain: "127.0.0.1",
      path: "/",
    },
    {
      name: "postascend-preview-profile",
      value: JSON.stringify({ displayName: ["bad"], xHandle: 42, onboardingStatus: "complete" }),
      domain: "127.0.0.1",
      path: "/",
    },
  ]);

  await page.goto("/app");
  await expect(page.getByLabel("Creator Evolution seed")).toBeVisible();
  await expect(page.getByText("Active Creator Evolution Rules")).toBeVisible();
});

test("profile analyzer researches and saves a voice style", async ({ page }) => {
  await page.goto("/?page=Profile+Analyzer");
  await page.getByTestId("profile-analyzer-handle").fill("brandbuilderhq");
  await page.getByTestId("profile-analyzer-run").click();
  await expect(page.getByTestId("profile-analyzer-result")).toContainText("@brandbuilderhq");
  await page.getByTestId("profile-analyzer-save-voice").click();
  await expect(page.getByText("Saved @brandbuilderhq as a reusable voice style.")).toBeVisible();
  await expect(page.getByTestId("profile-analyzer-result")).toContainText("@brandbuilderhq");
});

test("signals page builds owner drafts", async ({ page }) => {
  await openOwnerPreviewTool(page, "/app/signals-prompts");
  await expect(page.getByText("Signals & Prompts").first()).toBeVisible();
  await page.getByTestId("signals-build").click();
  await expect(page.getByTestId("signals-result")).toContainText("Expanded draft directions");
});

test("signals page accepts an imported signal from query params", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Owner Preview" }).click();
  await expect(page).toHaveURL(/\/app\/creator-evolution$/);
  await page.goto(
    "/app/signals-prompts?sig_text=League%20belief%20in%20this%20team%20is%20changing%20fast.&sig_author=AdamSchefter&sig_author_name=Adam%20Schefter&sig_replies=222&sig_rts=101&sig_likes=1800",
  );
  await expect(page.getByText("Imported a signal from X.")).toBeVisible();
  await expect(page.getByTestId("signals-list")).toContainText(
    "League belief in this team is changing fast.",
  );
});

test("gameday page builds a reaction draft", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Owner Preview" }).click();
  await expect(page).toHaveURL(/\/app\/creator-evolution$/);
  await page.goto("/app/gameday");
  await expect(
    page.getByRole("heading", { name: "Live game board and reaction drafting for the owner desk" }),
  ).toBeVisible();
  await page.getByTestId("gameday-build").click();
  await expect(page.getByTestId("gameday-result")).toContainText("Expanded draft directions");
});

test("debug console refreshes checks and runs an AI probe", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Owner Preview" }).click();
  await expect(page).toHaveURL(/\/app\/creator-evolution$/);
  await page.goto("/app/debug-console");
  await expect(
    page.getByRole("heading", { name: "Owner runtime checks and launch readiness" }),
  ).toBeVisible();
  await page.getByTestId("debug-refresh").click();
  await expect(page.getByTestId("debug-service-state")).toContainText("postascend-web");
  await page.getByTestId("debug-probe").click();
  await expect(page.getByTestId("debug-probe-result")).toContainText("Probe passed");
});

test("launch handoff endpoint returns deployment readiness JSON", async ({ request }) => {
  const response = await request.get("/api/launch-handoff");
  expect(response.ok()).toBeTruthy();
  const payload = (await response.json()) as {
    ok: boolean;
    action: string;
    data?: {
      deploymentState?: string;
      launchReady?: boolean;
      overallStatus?: string;
      source?: string;
      operatorChecklist?: Array<{ key: string }>;
      services?: Array<{ key: string }>;
    };
  };

  expect(payload.ok).toBeTruthy();
  expect(payload.action).toBe("launch-handoff");
  expect(payload.data?.deploymentState).toBeTruthy();
  expect(typeof payload.data?.launchReady).toBe("boolean");
  expect(payload.data?.overallStatus).toBeTruthy();
  if (payload.data?.source === "public") {
    expect(payload.data?.operatorChecklist).toBeUndefined();
    expect(payload.data?.services).toBeUndefined();
  } else {
    expect(payload.data?.operatorChecklist?.length).toBeGreaterThan(0);
    expect(payload.data?.services?.length).toBeGreaterThan(0);
  }
});

test("billing checkout fails closed when Stripe env is absent", async ({ request }) => {
  const response = await request.post("/api/billing/checkout", {
    data: {
      plan: "starter",
    },
  });
  expect([200, 503]).toContain(response.status());
  const payload = (await response.json()) as {
    ok: boolean;
    error?: string;
    data?: {
      url?: string;
    };
  };

  if (response.status() === 503) {
    expect(payload.ok).toBeFalsy();
    expect(payload.error).toContain("Checkout is not configured yet");
  } else {
    expect(payload.ok).toBeTruthy();
    expect(payload.data?.url).toMatch(/^https:\/\/checkout\.stripe\.com\//);
  }
});

test("owner-only APIs reject unauthenticated requests", async ({ request }) => {
  const [gamedayResponse, signalsInboxResponse, adminDebugResponse, xSignalsResponse] = await Promise.all([
    request.get("/api/gameday/board"),
    request.get("/api/data/signals-inbox"),
    request.get("/api/admin/debug"),
    request.get("/api/x/signals?tab=beat"),
  ]);

  expect(gamedayResponse.status()).toBe(401);
  expect(signalsInboxResponse.status()).toBe(401);
  expect(adminDebugResponse.status()).toBe(403);
  expect(xSignalsResponse.status()).toBe(401);
});
