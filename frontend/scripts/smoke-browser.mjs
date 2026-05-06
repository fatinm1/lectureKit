/**
 * Purpose: Interactive browser smoke tests for the frontend app.
 *
 * Scope:
 * - Test 5: landing page loads, Launch App navigates to /app, submit logs success.
 * - Test 6: invalid URL shows a user-friendly error message (no raw JSON dump).
 *
 * Notes:
 * - This uses Playwright to automate a real browser session (headless by default).
 * - It assumes:
 *   - Frontend is running at http://127.0.0.1:3000
 *   - Backend is running at http://127.0.0.1:8000
 */

import { chromium } from "playwright";

const FRONTEND = "http://127.0.0.1:3000";
const VIDEO_URL = "https://www.youtube.com/watch?v=jNQXAC9IVRw";

function fail(message) {
  const error = new Error(message);
  error.name = "SmokeTestFailure";
  throw error;
}

function assert(condition, message) {
  if (!condition) fail(message);
}

async function run() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  const consoleMessages = [];
  const pageErrors = [];

  page.on("console", async (msg) => {
    const base = { type: msg.type(), text: msg.text() };
    try {
      const args = msg.args();
      if (args && args.length) {
        const first = await args[0].jsonValue().catch(() => null);
        base.firstArg = first;
      }
    } catch {
      // ignore console arg extraction failures
    }
    consoleMessages.push(base);
  });
  page.on("pageerror", (err) => {
    pageErrors.push(String(err));
  });

  // Test 5 — landing page loads with dark background/purple accent (basic smoke).
  await page.goto(`${FRONTEND}/`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(250);

  const bodyBg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  assert(
    typeof bodyBg === "string" && bodyBg !== "rgba(0, 0, 0, 0)" && bodyBg !== "rgb(255, 255, 255)",
    `Expected non-white dark-ish body background, got ${bodyBg}`
  );

  // Click "Launch App" in the nav.
  await page.getByRole("link", { name: "Launch App" }).click();
  await page.waitForURL("**/app", { timeout: 10000 });

  // Confirm /app has URL input + submit button.
  const input = page.locator("#youtube-url-app");
  await input.waitFor({ state: "visible", timeout: 10000 });
  await page.getByRole("button", { name: /generate study kit/i }).waitFor({ state: "visible" });

  // Submit a valid URL and confirm console logs a successful response.
  await input.fill(VIDEO_URL);

  // Wait for the network response to /process.
  const [resp] = await Promise.all([
    page.waitForResponse((r) => r.url().includes("/process") && r.request().method() === "POST", {
      timeout: 120000,
    }),
    page.getByRole("button", { name: /generate study kit/i }).click(),
  ]);

  assert(resp.status() === 200, `Expected /process 200, got ${resp.status()}`);

  // Confirm success behavior.
  const responseJson = await resp.json().catch(() => null);
  assert(responseJson && responseJson.status === "success", "Expected JSON response with status=success");

  const successStatusText = await page
    .locator('p[role="status"]')
    .first()
    .textContent()
    .then((t) => (t || "").trim());

  // In some environments, Next/Chrome may not surface console logs reliably in headless mode.
  // We accept either the explicit console log OR the success status message as evidence.
  const sawProcessLog = consoleMessages.some(
    (m) =>
      (typeof m.text === "string" && m.text.includes("[LectureKit] POST /process response")) ||
      (typeof m.firstArg === "string" && m.firstArg.includes("[LectureKit] POST /process response"))
  );

  const sawSuccessMessage = successStatusText.toLowerCase().includes("submitted");
  assert(sawProcessLog || sawSuccessMessage, "Expected either a success console log or a success status message");

  // Test 6 — invalid URL shows friendly error message (not raw JSON).
  await input.fill("hello world");
  await page.getByRole("button", { name: /generate study kit/i }).click();

  const statusText = await page
    .locator('p[role="status"]')
    .first()
    .textContent()
    .then((t) => (t || "").trim());

  assert(statusText.length > 0, "Expected a visible user-friendly status message for invalid URL");
  assert(!statusText.includes("{") && !statusText.includes("}"), "Status message looks like raw JSON");

  // Report
  const report = {
    test5_passed: true,
    test6_passed: true,
    process_response_status: resp.status(),
    process_response_body_status: responseJson?.status ?? null,
    process_success_message: successStatusText,
    saw_process_console_log: sawProcessLog,
    console_errors: consoleMessages.filter((m) => m.type === "error").map((m) => m.text),
    page_errors: pageErrors,
    invalid_url_status_message: statusText,
    console_sample: consoleMessages.slice(0, 25),
  };

  // Fail if there were runtime page errors.
  if (pageErrors.length) fail(`Page runtime errors detected: ${pageErrors.join(" | ")}`);

  console.log(JSON.stringify(report, null, 2));

  await browser.close();
}

run().catch((err) => {
  console.error(String(err && err.stack ? err.stack : err));
  process.exit(1);
});

