import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const release = {
  release_id: "production-20260728",
  version: "2026.07.28",
  title: "头像与历史体验修复",
  summary: "完成用户体验问题修复并通过生产验证。",
  environment: "production",
  status: "succeeded",
  commit_sha: "abcdef1234567890",
  changes: ["修复头像设置", "修复训练提醒图标", "修复返回历史空白"],
  verification: {
    "服务健康": "通过",
    "桌面端": "通过",
    "移动端": "通过",
  },
  app_image: "sha256:app-image",
  worker_image: "sha256:worker-image",
  migration_revision: "20260728_0013",
  recovery_point: "20260728T153029Z",
  triggered_by: "operator",
  started_at: "2026-07-28T15:30:00+00:00",
  completed_at: "2026-07-28T15:34:00+00:00",
  created_at: "2026-07-28T15:34:00+00:00",
  updated_at: "2026-07-28T15:34:00+00:00",
};

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    sessionStorage.setItem(
      "interview-lab-admin-state-v1",
      JSON.stringify({
        accessToken: "admin-access",
        refreshToken: "admin-refresh",
        username: "operator",
      }),
    );
  });
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        user_id: "admin-1",
        username: "operator",
        role: "admin",
      }),
    }),
  );
  await page.route("**/api/admin/system-summary", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({ operator: "operator", role: "admin", counts: {} }),
    }),
  );
  await page.route("**/api/admin/runtime", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        dependencies: {},
        features: {},
        agent: { mode: "supervisor", specialists: [] },
      }),
    }),
  );
  await page.route("**/api/admin/releases?limit=100", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([release]),
    }),
  );
});

test("administrator can inspect a responsive release timeline and details", async ({
  page,
}) => {
  await page.goto("/admin");
  await page.getByRole("button", { name: "发版记录" }).click();

  await expect(page.getByRole("heading", { name: "最近发版记录" })).toBeVisible();
  await expect(page.getByText("头像与历史体验修复")).toBeVisible();
  await expect(page.locator(".release-card .release-status")).toHaveText("发布成功");
  await page.getByRole("button", { name: "查看 2026.07.28 发版详情" }).click();

  const dialog = page.getByRole("dialog", { name: "头像与历史体验修复" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("修复返回历史空白")).toBeVisible();
  await expect(dialog.getByText("服务健康")).toBeVisible();

  const layout = await page.evaluate(() => ({
    hasHorizontalOverflow:
      document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  }));
  expect(layout.hasHorizontalOverflow).toBe(false);

  const results = await new AxeBuilder({ page }).analyze();
  const blocking = results.violations.filter((item) =>
    item.impact === "critical" || item.impact === "serious",
  );
  expect(blocking).toEqual([]);

  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "查看 2026.07.28 发版详情" }),
  ).toBeFocused();
});
