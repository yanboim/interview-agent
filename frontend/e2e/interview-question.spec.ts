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
  await page.route(`**/api/interviews/${interviewId}/answer`, async (route) => {
    await route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        score: 8,
        feedback: "结构清晰。",
        reference_answer:
          "先说明原则。  1. **通信机制设计 **： - 局部智能体自治。 "
          + "- **意图黑板**：广播意图。  2. **冲突仲裁**： - 检测环路。",
        dimensions: {
          accuracy: 8,
          depth: 8,
          communication: 8,
          practicality: 8,
        },
        strengths: ["结构清晰"],
        weaknesses: ["补充案例"],
        next_question: null,
        turn_index: 1,
        status: "completed",
      }),
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
      fontWeight: Number.parseInt(style.fontWeight, 10),
      lineHeightRatio: Number.parseFloat(style.lineHeight) / fontSize,
      hasHorizontalOverflow:
        document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
    };
  });

  expect(typography.fontSize).toBeLessThanOrEqual(20);
  expect(typography.fontSize).toBeGreaterThanOrEqual(18);
  expect(typography.fontWeight).toBeLessThanOrEqual(600);
  expect(typography.lineHeightRatio).toBeGreaterThanOrEqual(1.6);
  expect(typography.hasHorizontalOverflow).toBe(false);

  await page.getByLabel("你的回答").fill("我的回答");
  await page.getByRole("button", { name: "提交并评分" }).click();
  await page.getByText("查看参考回答").click();
  const reference = page.locator(".reference-answer .markdown-content");
  await expect(reference.locator("strong").first()).toHaveText("通信机制设计");
  await expect(reference.locator("ol")).toHaveCount(2);
  await expect(reference.locator("ol").first()).toBeVisible();
  await expect(reference.locator("ul")).toHaveCount(2);
  await expect(reference).not.toContainText("**");

  await page.getByRole("button", { name: "返回历史" }).click();
  await expect(page).toHaveURL(/\/interviews$/);
  await expect(page.getByRole("heading", { name: "创建一场模拟面试" })).toBeVisible();
  await expect(page.getByText("历史面试")).toBeVisible();
  await expect(page.getByText("Agent 系统设计", { exact: true })).toBeVisible();
});
