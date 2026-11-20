/* eslint-disable @typescript-eslint/no-explicit-any -- page.evaluate callbacks read untyped window globals */
import { expect, test } from "./extension";

const PROBLEM = "https://leetcode.com/problems/two-sum/";

// Waits for the bridge to publish code, so the hint request has the student's code.
async function waitForCode(page: import("@playwright/test").Page): Promise<void> {
  await expect
    .poll(() => page.evaluate(() => (window as any).__bridge.some((m: any) => m.type === "code")))
    .toBe(true);
  // The isolated script receives the same window message; give its handler a tick.
  await page.waitForTimeout(100);
}

test("panel appears and click streams a hint with the device header", async ({ page, api }) => {
  await page.goto(PROBLEM);
  await waitForCode(page);
  const mascot = page.getByRole("button", { name: "Ask Aporia for a hint" });
  await expect(mascot).toBeVisible();
  await mascot.click();
  await expect(page.getByTestId("hint-view")).toContainText("L1: What happens with one element?");
  await expect(page.getByTestId("level-badge")).toContainText("L1");
  expect(api.requests).toHaveLength(1);
  const [req] = api.requests;
  expect(req?.body.problem.slug).toBe("two-sum");
  expect(req?.body.level).toBe(1);
  expect(req?.body.language).toBe("python");
  expect(req?.body.code).toContain("class Solution");
  expect(String(req?.headers["x-aporia-device"])).toMatch(/^[0-9a-f-]{36}$/);
});

test("bridge reports code changes and verdicts", async ({ page }) => {
  await page.goto(PROBLEM);
  await expect
    .poll(() => page.evaluate(() => (window as any).__bridge.some((m: any) => m.type === "code")))
    .toBe(true);

  await page.evaluate(() => (window as any).__setCode("changed code"));
  await expect
    .poll(() =>
      page.evaluate(() =>
        (window as any).__bridge.some((m: any) => m.type === "code" && m.code === "changed code"),
      ),
    )
    .toBe(true);

  await page.getByRole("button", { name: "Run" }).click();
  await expect
    .poll(() =>
      page.evaluate(() => (window as any).__bridge.find((m: any) => m.type === "verdict")),
    )
    .toMatchObject({ phase: "run", statusMessage: "Wrong Answer", actualOutput: "[]" });
});

test("SPA navigation resets state and the next hint uses the new slug", async ({ page, api }) => {
  await page.goto(PROBLEM);
  await page.getByRole("button", { name: "Ask Aporia for a hint" }).click();
  await expect(page.getByTestId("hint-view")).toContainText("element?");

  await page.getByRole("button", { name: "Next problem" }).click();
  await expect(page).toHaveURL(/valid-anagram/);
  await expect(page.getByTestId("hint-view")).toHaveCount(0);

  await page.getByRole("button", { name: "Collapse Aporia" }).click();
  await page.getByRole("button", { name: "Ask Aporia for a hint" }).click();
  await expect(page.getByTestId("hint-view")).toContainText("element?");
  expect(api.requests.at(-1)?.body.problem.slug).toBe("valid-anagram");
});

test("shows a clear error when the API is unreachable", async ({ page, api }) => {
  await api.close();
  await page.goto(PROBLEM);
  await page.getByRole("button", { name: "Ask Aporia for a hint" }).click();
  await expect(page.getByRole("alert")).toContainText("Could not reach the Aporia server");
});

test("ladder: bigger hint escalates one level at a time with the typed message", async ({
  page,
  api,
}) => {
  await page.goto(PROBLEM);
  await waitForCode(page);
  await page.getByRole("button", { name: "Ask Aporia for a hint" }).click();
  await expect(page.getByTestId("level-badge")).toContainText("L1");
  await expect(page.getByTestId("hint-view")).toContainText("element?");

  await page.getByLabel(/stuck on/i).fill("I do not understand the loop");
  await page.getByRole("button", { name: "Need a bigger hint" }).click();
  await expect(page.getByTestId("level-badge")).toContainText("L2");
  await expect(page.getByTestId("hint-view")).toContainText("L2: What happens");
  expect(api.requests.at(-1)?.body).toMatchObject({
    level: 2,
    student_message: "I do not understand the loop",
  });

  for (const level of [3, 4]) {
    await page.getByRole("button", { name: "Need a bigger hint" }).click();
    await expect(page.getByTestId("level-badge")).toContainText(`L${level}`);
  }
  await expect(page.getByRole("button", { name: "Need a bigger hint" })).toBeDisabled();
  expect(api.requests.map((r) => r.body.level)).toEqual([1, 2, 3, 4]);
});

test("Not helpful sends a rating for the delivered hint", async ({ page, api }) => {
  await page.goto(PROBLEM);
  await waitForCode(page);
  await page.getByRole("button", { name: "Ask Aporia for a hint" }).click();
  await expect(page.getByTestId("hint-view")).toContainText("element?");
  await page.getByRole("button", { name: "Not helpful" }).click();
  await expect(page.getByText("Thanks for the feedback")).toBeVisible();
  await expect.poll(() => api.ratings.length).toBe(1);
  expect(api.ratings[0]).toMatchObject({ hintId: "h-1", rating: 1 });
  expect(String(api.ratings[0]?.device)).toMatch(/^[0-9a-f-]{36}$/);
});

test("unsupported problems show a banner", async ({ page, api }) => {
  // Loaded directly (SPA navigation has its own test): the mock API marks "anagram" unsupported.
  await page.goto("https://leetcode.com/problems/valid-anagram/");
  await waitForCode(page);
  await page.getByRole("button", { name: "Ask Aporia for a hint" }).click();
  await expect(page.getByText(/cannot run your code on this problem yet/)).toBeVisible();

  // the supported problem shows no banner
  await page.goto(PROBLEM);
  await waitForCode(page);
  await page.getByRole("button", { name: "Ask Aporia for a hint" }).click();
  await expect(page.getByTestId("hint-view")).toContainText("element?");
  await expect(page.getByText(/cannot run your code/)).toHaveCount(0);
  expect(api.requests.map((r) => r.body.problem.slug)).toEqual(["valid-anagram", "two-sum"]);
});

test("failed verdicts are reported as failed attempts on the next hint", async ({ page, api }) => {
  await page.goto(PROBLEM);
  await waitForCode(page);
  for (let i = 0; i < 3; i += 1) {
    await page.getByRole("button", { name: "Run" }).click();
    await expect
      .poll(() =>
        page.evaluate(
          () => (window as any).__bridge.filter((m: any) => m.type === "verdict").length,
        ),
      )
      .toBe(i + 1);
  }
  await page.waitForTimeout(100);
  await page.getByRole("button", { name: "Ask Aporia for a hint" }).click();
  await expect(page.getByTestId("hint-view")).toContainText("element?");
  expect(api.requests[0]?.body.failed_attempts).toBe(3);
});

// ---- proactive nudge ----

async function failSubmissions(page: import("@playwright/test").Page, times: number) {
  const seen = () =>
    page.evaluate(
      () => (window as any).__bridge.filter((m: any) => m.type === "verdict").length as number,
    );
  const start = await seen();
  for (let i = 1; i <= times; i += 1) {
    await page.getByRole("button", { name: "Submit" }).click();
    await expect.poll(seen).toBe(start + i);
  }
}

const bubble = (page: import("@playwright/test").Page) => page.getByTestId("nudge-bubble");

test("nudge: three failed submissions offer help, and only Yes opens a hint", async ({
  page,
  api,
}) => {
  await page.goto(PROBLEM);
  await waitForCode(page);
  await failSubmissions(page, 3);
  await expect(bubble(page)).toContainText("Stuck? Want a nudge?");
  await expect(page.getByRole("img", { name: /mascot, attentive/ })).toBeVisible();
  expect(api.requests).toHaveLength(0); // the offer alone never asks for a hint

  await page.getByRole("button", { name: "Yes" }).click();
  await expect(page.getByTestId("hint-view")).toContainText("L1:");
  expect(api.requests).toHaveLength(1);
  expect(api.requests[0]?.body.level).toBe(1);
  await expect(bubble(page)).toHaveCount(0);
});

test("nudge: Not now snoozes it, even after a reload", async ({ page, api }) => {
  await page.goto(PROBLEM);
  await waitForCode(page);
  await failSubmissions(page, 3);
  await bubble(page).getByRole("button", { name: "Not now" }).click();
  await expect(bubble(page)).toHaveCount(0);

  await failSubmissions(page, 2); // still stuck, but snoozed
  await page.waitForTimeout(500);
  await expect(bubble(page)).toHaveCount(0);

  await page.reload();
  await waitForCode(page);
  await failSubmissions(page, 3);
  await page.waitForTimeout(500);
  await expect(bubble(page)).toHaveCount(0); // the snooze is stored, not just in memory
  expect(api.requests).toHaveLength(0);
});

test("nudge: Never on this problem stays off after a reload", async ({ page }) => {
  await page.goto(PROBLEM);
  await waitForCode(page);
  await failSubmissions(page, 3);
  await bubble(page).getByRole("button", { name: "Never on this problem" }).click();
  await expect(bubble(page)).toHaveCount(0);

  await page.reload();
  await waitForCode(page);
  await failSubmissions(page, 3);
  await page.waitForTimeout(500);
  await expect(bubble(page)).toHaveCount(0); // stored for the slug, not just in memory
});

test("nudge: the bubble dismisses itself after 12 seconds", async ({ page }) => {
  await page.goto(PROBLEM);
  await waitForCode(page);
  await failSubmissions(page, 3);
  await expect(bubble(page)).toBeVisible();
  await expect(bubble(page)).toHaveCount(0, { timeout: 15_000 });
});
