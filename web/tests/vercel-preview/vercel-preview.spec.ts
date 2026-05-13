import { expect, type Page, test } from "@playwright/test";

async function selectRailTool(page: Page, name: string) {
  await page
    .getByRole("navigation", { name: "Workspace sections" })
    .getByRole("button", { name })
    .first()
    .evaluate((button: HTMLButtonElement) => button.click());
}

test("Vercel Preview public root renders the sales landing and preserves app preview", async ({ page }) => {
  await page.goto("/");
  await expect(
    page.getByRole("heading", {
      name: "A creator operating system for posts that still sound like you.",
    }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Open the app" }).first()).toHaveAttribute(
    "href",
    "/app/creator-studio",
  );
  await expect(
    page.getByRole("heading", { name: "Clear packaging with simple workspace setup." }),
  ).toBeVisible();

  await page.goto("/?preview=workspace");
  await expect(page.getByRole("heading", { name: "Creator Studio" })).toBeVisible();

  const appNav = page.getByRole("navigation", { name: "Workspace sections" });
  await expect(appNav.getByRole("button", { name: "Debug Console" })).toHaveCount(0);
  await expect(appNav.getByRole("link", { name: "Gameday Mode" }).first()).toHaveAttribute(
    "href",
    "https://gameday-open.postascend.io",
  );

  await selectRailTool(page, "Creator Studio");
  await expect(page.locator('[data-testid="creator-input"]')).toBeVisible();

  await selectRailTool(page, "Signals & Prompts");
  await expect(page.locator('[data-testid="signals-list"]')).toBeVisible();
});

test("Vercel Preview guest onboarding uses preview cookies", async ({ page }) => {
  await page.goto("/login");
  await page.getByRole("button", { name: "Guest Preview" }).click();
  await expect(page).toHaveURL(/\/app\/onboarding$/);

  await page.getByPlaceholder("@yourhandle").fill("@previewguest");
  await page.getByPlaceholder("Display name").fill("Preview Guest");
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await page.getByRole("button", { name: "Complete Setup" }).click();

  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByText("Preview Guest").first()).toBeVisible();

  const debugResponse = await page.request.get("/api/admin/debug");
  expect(debugResponse.status()).toBe(403);
});

test("Vercel Preview owner can use owner preview without Supabase auth", async ({ page }) => {
  await page.goto("/login");
  await page.getByPlaceholder("Required for owner preview").fill("test-owner-preview-secret");
  await page.getByRole("button", { name: "Owner Preview" }).click();
  await expect(page).toHaveURL(/\/app$/);

  await page.goto("/app/debug-console");
  await expect(
    page.getByRole("heading", { name: "Owner runtime checks and launch readiness" }),
  ).toBeVisible();

  const payload = await page.evaluate(async () => {
    const response = await fetch("/api/admin/debug", { cache: "no-store" });
    return {
      status: response.status,
      body: (await response.json()) as {
        ok: boolean;
        data?: {
          mode?: string;
        };
      },
    };
  });
  expect(payload.status).toBe(200);
  expect(payload.body.ok).toBeTruthy();
  expect(payload.body.data?.mode).toBeTruthy();
});

test("Vercel Preview forged owner role cookie is rejected", async ({ context, page }) => {
  await context.addCookies([
    {
      name: "postascend-preview-role",
      value: "owner",
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

  const debugPayload = await page.evaluate(async () => {
    const response = await fetch("/api/admin/debug", { cache: "no-store" });
    return {
      status: response.status,
    };
  });
  expect(debugPayload.status).toBe(403);
});
