import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const queuedResume = {
  resume_id: "resume-e2e",
  original_filename: "synthetic-resume.pdf",
  content_type: "application/pdf",
  size_bytes: 128,
  status: "uploaded",
  error: null,
  created_at: "2026-07-29T00:00:00+00:00",
  updated_at: "2026-07-29T00:00:00+00:00",
  analyses: [
    {
      analysis_id: "analysis-e2e",
      resume_id: "resume-e2e",
      status: "pending",
      job_description: "Python 后端工程师",
      target_role: "后端工程师",
      experience_level: "senior",
      report: null,
      draft: null,
      warnings: [],
      revision: 1,
      error: null,
      created_at: "2026-07-29T00:00:00+00:00",
      updated_at: "2026-07-29T00:00:00+00:00",
    },
  ],
};

const readyResume = {
  ...queuedResume,
  resume_id: "resume-ready",
  original_filename: "AI应用开发工程师-简历.pdf",
  size_bytes: 158_720,
  status: "ready",
  updated_at: "2026-07-29T08:30:00+00:00",
  analyses: [
    {
      ...queuedResume.analyses[0],
      analysis_id: "analysis-ready",
      resume_id: "resume-ready",
      status: "ready",
      target_role: "AI应用开发工程师",
      report: {
        scores: {
          match: 78,
          completeness: 82,
          relevance: 75,
          clarity: 88,
          impact: 72,
          ats: 90,
        },
        keyword_matches: ["Python", "RAG", "LangChain"],
        keyword_gaps: ["模型评估", "成本治理"],
        issues: [
          {
            severity: "high",
            category: "成果影响",
            message: "项目成果缺少可验证的业务指标",
            evidence: "负责智能问答系统的设计与开发。",
            suggestion: "补充准确率、响应时延或节省工时等真实指标。",
          },
        ],
      },
      draft: {
        name: "测试候选人",
        headline: "AI应用开发工程师",
        summary: "具备后端与AI应用工程经验。",
        sections: [
          {
            title: "项目经历",
            items: ["设计并落地企业知识问答系统。"],
          },
        ],
        pending_questions: [],
      },
      warnings: [],
      revision: 2,
    },
  ],
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/config", (route) =>
    route.fulfill({
      json: { auth_required: false, resume_feature_enabled: true },
    }),
  );
  await page.route("**/api/resumes", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ status: 202, json: queuedResume });
      return;
    }
    await route.fulfill({ json: [] });
  });
});

test("resume upload enters durable processing state", async ({ page }) => {
  await page.goto("/resumes");
  await expect(page.getByRole("heading", { name: "简历中心" })).toBeVisible();
  await page
    .locator('input[type="file"]')
    .setInputFiles({
      name: "synthetic-resume.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4 synthetic resume"),
    });
  await page.getByLabel("目标 JD（可选）").fill("Python 后端工程师");
  await page.getByRole("button", { name: "上传并评估" }).click();

  await expect(page).toHaveURL(/\/resumes\/resume-e2e$/);
  await expect(
    page.getByRole("heading", { name: "synthetic-resume.pdf" }),
  ).toBeVisible();
  await expect(page.getByText("正在解析和评估简历")).toBeVisible();

  const hasHorizontalOverflow = await page.evaluate(
    () =>
      document.documentElement.scrollWidth
      > document.documentElement.clientWidth + 1,
  );
  expect(hasHorizontalOverflow).toBe(false);
  const results = await new AxeBuilder({ page }).analyze();
  expect(
    results.violations.filter(
      (item) => item.impact === "critical" || item.impact === "serious",
    ),
  ).toEqual([]);
});

test("ready resume report is scannable and responsive", async ({ page }) => {
  await page.unroute("**/api/resumes");
  await page.route("**/api/resumes", (route) =>
    route.fulfill({ json: [readyResume] }),
  );
  await page.route("**/api/resumes/resume-ready", (route) =>
    route.fulfill({ json: readyResume }),
  );

  await page.goto("/resumes/resume-ready");

  await expect(
    page.getByRole("heading", { name: "AI应用开发工程师-简历.pdf" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "简历竞争力" })).toBeVisible();
  await expect(page.locator(".resume-score-grid article")).toHaveCount(6);
  await expect(page.getByText("模型评估", { exact: true })).toBeVisible();
  await expect(
    page.getByText("项目成果缺少可验证的业务指标"),
  ).toBeVisible();
  await expect(page.getByLabel("个人简介")).toBeVisible();
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
