import { test as base, chromium, type BrowserContext, type Page } from "@playwright/test";
import { mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
import { startMockApi, type MockApi } from "./mock-api";

const EXTENSION_PATH = path.resolve(here, "../.output/chrome-mv3-dev");
const FIXTURE_HTML = path.resolve(here, "fixtures/two-sum.html");

function graphqlBody(slug: string) {
  return {
    data: {
      question: {
        questionId: "1",
        title: slug === "two-sum" ? "Synthetic Two Sum" : "Synthetic Anagram",
        difficulty: "Easy",
        content: "<p>Synthetic <b>statement</b>.</p>",
        topicTags: [{ name: "Array", slug: "array" }],
        exampleTestcases: "[1,2]\n3",
        metaData: JSON.stringify({ name: "twoSum", params: [] }),
      },
    },
  };
}

export const test = base.extend<{ context: BrowserContext; page: Page; api: MockApi }>({
  api: async ({}, use) => {
    const api = await startMockApi(8765);
    await use(api);
    await api.close();
  },
  context: async ({}, use) => {
    const userDataDir = mkdtempSync(path.join(tmpdir(), "aporia-e2e-"));
    const context = await chromium.launchPersistentContext(userDataDir, {
      channel: "chromium", // new headless mode, which supports extensions
      args: [`--disable-extensions-except=${EXTENSION_PATH}`, `--load-extension=${EXTENSION_PATH}`],
    });
    let [worker] = context.serviceWorkers();
    if (!worker) worker = await context.waitForEvent("serviceworker");

    // Serve the synthetic fixture at a leetcode.com URL and mock every other network call.
    await context.route("https://leetcode.com/**", async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname === "/graphql") {
        const post = route.request().postDataJSON() as { variables: { titleSlug: string } };
        await route.fulfill({ json: graphqlBody(post.variables.titleSlug) });
      } else if (url.pathname.endsWith("/interpret_solution/")) {
        await route.fulfill({ json: { interpret_id: "runcode_1", test_case: "[1,2]" } });
      } else if (url.pathname.includes("/check/")) {
        await route.fulfill({
          json: {
            state: "SUCCESS",
            status_code: 11,
            status_msg: "Wrong Answer",
            status_runtime: "N/A",
            last_testcase: "[1,2]\n3",
            expected_output: "[0,1]",
            code_output: "[]",
          },
        });
      } else if (url.pathname.startsWith("/problems/")) {
        await route.fulfill({ path: FIXTURE_HTML, contentType: "text/html" });
      } else {
        await route.fulfill({ status: 404, body: "" });
      }
    });
    await use(context);
    await context.close();
  },
  page: async ({ context }, use) => {
    const page = await context.newPage();
    await page.addInitScript(() => {
      const w = window as unknown as { __bridge: unknown[] };
      w.__bridge = [];
      window.addEventListener("message", (e) => {
        if (e.data && e.data.source === "aporia-bridge") w.__bridge.push(e.data);
      });
    });
    await use(page);
  },
});

export const expect = test.expect;
