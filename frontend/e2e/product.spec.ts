import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("today workspace is responsive and has no serious accessibility violations", async ({
  page,
}) => {
  await page.goto("/today");
  await expect(page.getByRole("heading", { name: /开始今天的面试训练|再进一步/ })).toBeVisible();
  await expect(page.locator("main")).toBeVisible();
  await expect(page.locator(".today-card h3").first()).toBeVisible();

  const layout = await page.evaluate(() => {
    const hero = document.querySelector<HTMLElement>(".today-hero h1");
    const reviewTitle = document.querySelector<HTMLElement>(".today-card h3");
    return {
      hasHorizontalOverflow:
        document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
      heroFontSize: hero ? Number.parseFloat(getComputedStyle(hero).fontSize) : 0,
      reviewLineClamp: reviewTitle ? getComputedStyle(reviewTitle).webkitLineClamp : "",
    };
  });
  expect(layout.hasHorizontalOverflow).toBe(false);
  expect(layout.heroFontSize).toBeLessThanOrEqual(46);
  expect(layout.reviewLineClamp).toBe("3");

  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations.filter((item) =>
    item.impact === "critical" || item.impact === "serious",
  );
  expect(blocking).toEqual([]);
});

test("primary training action works with keyboard or touch", async ({ page }, testInfo) => {
  await page.goto("/today");
  if (testInfo.project.name.startsWith("mobile")) {
    await page.getByRole("button", { name: /创建模拟面试|继续面试/ }).tap();
    await expect(page).toHaveURL(/\/interviews/);
    return;
  }
  const primaryAction = page.getByRole("button", { name: /创建模拟面试|继续面试/ });
  await primaryAction.focus();
  await expect(primaryAction).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/interviews/);
});

test("history and operational settings are separated from the sidebar", async ({
  page,
}, testInfo) => {
  await page.goto("/today");
  if (testInfo.project.name.startsWith("mobile")) {
    await page.getByRole("button", { name: "打开菜单" }).click();
  }

  await expect(page.getByPlaceholder("搜索会话")).toHaveCount(0);
  await page.getByRole("button", { name: "历史记录" }).click();
  await expect(page).toHaveURL(/\/history$/);
  await expect(page.getByRole("heading", { name: "历史记录", level: 1 })).toBeVisible();
  await expect(page.getByPlaceholder("搜索标题或关键词")).toBeVisible();

  if (testInfo.project.name.startsWith("mobile")) {
    await page.getByRole("button", { name: "打开菜单" }).click();
  }
  await expect(page.getByRole("link", { name: "后台" })).toHaveCount(0);
  await page.getByRole("button", { name: "打开设置" }).click();
  await expect(page.getByText(/API Key|Bearer Key/)).toHaveCount(0);
});
