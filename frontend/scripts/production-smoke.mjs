import { chromium, devices } from "@playwright/test";

const baseURL = process.env.PRODUCTION_SMOKE_URL;

if (!baseURL) {
  throw new Error("PRODUCTION_SMOKE_URL is required");
}

const browser = await chromium.launch();
const results = [];

try {
  for (const [name, options] of [
    ["desktop", devices["Desktop Chrome"]],
    ["mobile", devices["Pixel 7"]],
  ]) {
    const context = await browser.newContext(options);
    const page = await context.newPage();
    const consoleErrors = [];
    const pageErrors = [];
    const unexpectedResponses = [];

    page.on("console", (message) => {
      if (message.type() === "error") consoleErrors.push(message.text());
    });
    page.on("pageerror", (error) => pageErrors.push(error.message));
    page.on("response", (response) => {
      if (response.status() < 400) return;
      const url = new URL(response.url());
      const isExpectedAnonymousProbe =
        response.status() === 401 && url.pathname === "/api/auth/me";
      if (!isExpectedAnonymousProbe) {
        unexpectedResponses.push(`${response.status()} ${url.pathname}`);
      }
    });

    const response = await page.goto(new URL("/today", baseURL).toString(), {
      waitUntil: "networkidle",
    });
    if (!response?.ok()) throw new Error(`${name}: page returned ${response?.status()}`);

    const checks = await page.evaluate(async () => {
      const iconHref = document.querySelector('link[rel="icon"]')?.href;
      const iconStatus = iconHref ? (await fetch(iconHref)).status : 0;
      return {
        hasContent: document.body.innerText.trim().length > 0,
        hasErrorOverlay: Boolean(
          document.querySelector(
            "[data-nextjs-dialog], .vite-error-overlay, #webpack-dev-server-client-overlay",
          ),
        ),
        hasHorizontalOverflow:
          document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
        iconStatus,
      };
    });

    const loginHeadingVisible = await page
      .getByRole("heading", { name: "登录 Interview Lab" })
      .isVisible();
    const loginButtonVisible = await page.getByRole("button", { name: "登录" }).isVisible();

    const unexpectedConsoleErrors = consoleErrors.filter(
      (message) =>
        !(
          message.includes("Failed to load resource") &&
          !unexpectedResponses.length &&
          !pageErrors.length
        ),
    );

    if (
      !checks.hasContent ||
      checks.hasErrorOverlay ||
      checks.hasHorizontalOverflow ||
      checks.iconStatus !== 200 ||
      !loginHeadingVisible ||
      !loginButtonVisible ||
      unexpectedConsoleErrors.length ||
      pageErrors.length ||
      unexpectedResponses.length
    ) {
      throw new Error(
        `${name}: ${JSON.stringify({
          checks,
          unexpectedConsoleErrors,
          pageErrors,
          unexpectedResponses,
          loginHeadingVisible,
          loginButtonVisible,
        })}`,
      );
    }

    results.push({
      name,
      ...checks,
      loginHeadingVisible,
      loginButtonVisible,
      unexpectedConsoleErrors,
      pageErrors,
      unexpectedResponses,
    });
    await context.close();
  }
} finally {
  await browser.close();
}

console.log(JSON.stringify(results, null, 2));
