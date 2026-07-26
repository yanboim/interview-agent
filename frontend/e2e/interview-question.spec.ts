import { expect, test } from "@playwright/test";

test("long interview questions use readable typography and inline Markdown", async ({
  page,
}) => {
  const interviewId = "typography-test";
  const question =
    "在复杂业务场景中，自主智能体需要连续执行长链条工具调用。请设计完整的"
    + "**异常恢复与动态重规划机制**，并说明 `retry budget` 如何避免死循环？";
  const activeInterview = {
    interview_id: interviewId,
    topic: "Agent 系统设计",
    level: "高级",
    question_count: 5,
    turn_index: 1,
    question,
    status: "active",
  };

  await page.route("**/api/interviews?*", async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([
        {
          ...activeInterview,
          total_questions: 5,
          answered_questions: 0,
          average_score: null,
          archived_at: null,
          updated_at: "2026-07-26T00:00:00Z",
        },
      ]),
    });
  });
  await page.route(`**/api/interviews/${interviewId}/resume`, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify(activeInterview),
    });
  });

  await page.goto(`/interviews/${interviewId}`);
  const heading = page.locator(".interview-question");
  await expect(heading).toBeVisible();
  await expect(heading.locator("strong")).toHaveText("异常恢复与动态重规划机制");
  await expect(heading.locator("code")).toHaveText("retry budget");
  await expect(heading).not.toContainText("**");

  const typography = await heading.evaluate((element) => {
    const style = getComputedStyle(element);
    const fontSize = Number.parseFloat(style.fontSize);
    return {
      fontSize,
      lineHeightRatio: Number.parseFloat(style.lineHeight) / fontSize,
      hasHorizontalOverflow:
        document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
    };
  });

  expect(typography.fontSize).toBeLessThanOrEqual(24);
  expect(typography.fontSize).toBeGreaterThanOrEqual(19);
  expect(typography.lineHeightRatio).toBeGreaterThanOrEqual(1.5);
  expect(typography.hasHorizontalOverflow).toBe(false);
});
