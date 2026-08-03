import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/config", (route) =>
    route.fulfill({
      json: {
        auth_required: false,
        resume_feature_enabled: true,
        review_feature_enabled: true,
      },
    }),
  );
  await page.route("**/api/conversations/citation-markdown/messages?*", (route) =>
    route.fulfill({
      json: [
        {
          role: "assistant",
          content: "引用格式回归测试",
          created_at: "2026-08-03T00:00:00Z",
          metadata: {
            turn_id: "turn-citation-markdown",
            citations: [
              {
                claim: "> ⚠️ **公开资料**：建议使用 `JDK 21`。 ``",
                evidence_ids: [],
                support: "unsupported",
              },
              {
                claim: "- 使用 **SATB (Snapshot-At-The-Beginning) ** 算法。",
                evidence_ids: ["chunk-1"],
                support: "supported",
              },
            ],
            unsupported_claims: ["公开资料需交叉验证。"],
          },
        },
      ],
    }),
  );
});

test("persisted claim citations render Markdown without raw delimiters", async ({ page }) => {
  await page.goto("/chat/citation-markdown");

  const citations = page.getByLabel("逐条引用与证据状态");
  await expect(citations).toBeVisible();
  await expect(citations.locator("blockquote")).toContainText("公开资料");
  await expect(citations.locator(".citation-claim strong").first()).toContainText("公开资料");
  await expect(citations.locator("code")).toHaveText("JDK 21");
  await expect(citations.locator(".citation-claim ul")).toBeVisible();
  await expect(citations).toContainText("暂无证据支持");
  await expect(citations).toContainText("证据 chunk-1");
  await expect(citations).not.toContainText("**");
  await expect(citations).not.toContainText("``");

  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  );
  expect(hasHorizontalOverflow).toBe(false);
});
