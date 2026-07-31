import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const awaiting = {
  review_id: "review-e2e",
  input_type: "text",
  original_filename: null,
  status: "awaiting_confirmation",
  transcript_revision: 1,
  confirmed_revision: null,
  segments: [
    { segment_id: "s1", speaker: "interviewer", text: "请介绍缓存一致性方案" },
    { segment_id: "s2", speaker: "candidate", text: "我会使用延迟双删" },
  ],
  turns: [],
  report: null,
  error: null,
  created_at: "2026-07-29T00:00:00+00:00",
  updated_at: "2026-07-29T00:00:00+00:00",
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/config", (route) =>
    route.fulfill({
      json: {
        auth_required: false,
        resume_feature_enabled: true,
        review_feature_enabled: true,
        transcription_enabled: false,
      },
    }),
  );
  await page.route("**/api/interview-reviews", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/interview-reviews/text", (route) =>
    route.fulfill({ status: 201, json: awaiting }),
  );
  await page.route("**/api/interview-reviews/review-e2e/transcript", (route) =>
    route.fulfill({
      json: { ...awaiting, transcript_revision: 2 },
    }),
  );
  await page.route(
    "**/api/interview-reviews/review-e2e/confirm-and-analyze",
    (route) =>
      route.fulfill({
        status: 202,
        json: {
          ...awaiting,
          transcript_revision: 2,
          confirmed_revision: 2,
          status: "ready",
          report: {
            overall_summary: "表达清晰，但需要补充异常场景。",
            dimension_scores: {
              accuracy: 7,
              depth: 6,
              communication: 8,
              practicality: 7,
            },
            strengths: ["表达清晰"],
            weaknesses: ["异常场景不足"],
            action_plan: ["补充失败重试方案"],
          },
          turns: [
            {
              turn_index: 1,
              question: "请介绍缓存一致性方案",
              answer: "我会使用延迟双删",
              score: 7,
              dimensions: { accuracy: 7 },
              strengths: ["结构清晰"],
              weaknesses: ["缺少权衡"],
              feedback: "补充失败处理。",
              improved_answer: "先说明一致性目标，再比较方案。",
            },
            {
              turn_index: 2,
              question: "如何处理删除失败？",
              answer: "记录失败任务并重试",
              score: 6,
              dimensions: { accuracy: 6 },
              strengths: ["有重试意识"],
              weaknesses: ["缺少幂等设计"],
              feedback: "补充幂等键和失败上限。",
              improved_answer: "使用幂等任务、指数退避和死信队列。",
            },
          ],
        },
      }),
  );
});

test("text transcript can be confirmed and reviewed", async ({ page }) => {
  await page.goto("/reviews");
  await page
    .getByLabel("粘贴逐字稿")
    .fill("面试官：请介绍缓存一致性方案\n\n候选人：我会使用延迟双删");
  await page.getByRole("button", { name: "创建文本复盘" }).click();
  await expect(page).toHaveURL(/\/reviews\/review-e2e$/);
  await expect(page.getByText("确认逐字稿与说话人")).toBeVisible();

  await page.getByRole("button", { name: "保存逐字稿" }).click();
  await page.getByRole("button", { name: "确认并生成复盘" }).click();
  await expect(page.getByText("表达清晰，但需要补充异常场景。")).toBeVisible();
  await expect(page.getByText("准确性")).toBeVisible();
  await expect(page.getByRole("heading", { name: "表现亮点" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "行动计划" })).toBeVisible();
  await expect(page.getByText("先说明一致性目标，再比较方案。")).toBeVisible();
  const reviewTurns = page.locator(".review-turn-card");
  await expect(reviewTurns).toHaveCount(2);
  await expect(reviewTurns.first()).toHaveAttribute("open", "");
  await expect(reviewTurns.nth(1)).not.toHaveAttribute("open", "");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  const results = await new AxeBuilder({ page }).analyze();
  expect(
    results.violations.filter(
      (item) => item.impact === "critical" || item.impact === "serious",
    ),
  ).toEqual([]);
});
