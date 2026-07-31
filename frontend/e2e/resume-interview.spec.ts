import { expect, test } from "@playwright/test";

const readyResume = {
  resume_id: "resume-ready",
  original_filename: "backend-resume.docx",
  content_type:
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  size_bytes: 4096,
  status: "ready",
  error: null,
  created_at: "2026-07-29T00:00:00+00:00",
  updated_at: "2026-07-29T00:00:00+00:00",
  latest_analysis: {
    analysis_id: "analysis-ready",
    resume_id: "resume-ready",
    status: "ready",
    job_description: "Python 后端工程师",
    target_role: "后端工程师",
    experience_level: "高级",
    report: { scores: {}, keyword_matches: [], keyword_gaps: [], issues: [] },
    draft: {
      name: "",
      headline: "",
      summary: "",
      sections: [],
      pending_questions: [],
    },
    warnings: [],
    revision: 1,
    error: null,
    created_at: "2026-07-29T00:00:00+00:00",
    updated_at: "2026-07-29T00:00:00+00:00",
  },
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/config", (route) =>
    route.fulfill({
      json: { auth_required: false, resume_feature_enabled: true },
    }),
  );
  await page.route("**/api/resumes", (route) =>
    route.fulfill({ json: [readyResume] }),
  );
  await page.route("**/api/interviews?*", (route) =>
    route.fulfill({ json: [] }),
  );
  await page.route("**/api/interviews/start", async (route) => {
    const body = route.request().postDataJSON();
    expect(body.resume_analysis_id).toBe("analysis-ready");
    await route.fulfill({
      json: {
        interview_id: "interview-resume",
        topic: body.topic,
        level: body.level,
        question_count: body.question_count,
        turn_index: 1,
        question: "请说明订单接口优化中的关键技术取舍。",
        status: "active",
        source_type: "resume",
        source_resume: {
          resume_id: "resume-ready",
          analysis_id: "analysis-ready",
          display_name: "backend-resume.docx",
          available: true,
        },
      },
    });
  });
});

test("user starts a mock interview from a ready resume", async ({ page }) => {
  await page.goto("/interviews");
  await page.getByLabel("基于简历追问").check();
  await expect(page.getByLabel("选择简历评估版本")).toHaveValue(
    "analysis-ready",
  );
  await page.getByRole("button", { name: "开始面试" }).click();

  await expect(page).toHaveURL(/\/interviews\/interview-resume$/);
  await expect(page.getByText("· 基于简历")).toBeVisible();
  await expect(
    page.getByRole("heading", {
      name: "请说明订单接口优化中的关键技术取舍。",
    }),
  ).toBeVisible();
});
