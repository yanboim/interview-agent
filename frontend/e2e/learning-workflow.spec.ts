import { expect, test } from "@playwright/test";

test("user confirms a durable personalized training workflow", async ({
  page,
  request,
}, testInfo) => {
  const username = `workflow_${Date.now()}_${testInfo.project.name.replaceAll("-", "_")}`;
  const registration = await request.post("/api/auth/register", {
    data: { username, password: "Workflow-test-2026!" },
  });
  expect(registration.ok()).toBe(true);
  const auth = await registration.json();
  let completed = false;

  const proposal = {
    run_id: "run-training-1",
    run_type: "personalized_training_program",
    status: "awaiting_confirmation",
    proposal: {
      schema_version: "training-program-proposal-v1",
      target_role: "Staff Backend Engineer",
      topic: "分布式系统",
      answered_questions: 3,
      candidates: [
        {
          dimension: "工程实践",
          weakness: "缺少故障降级方案",
          action: "补充一次真实故障的指标、处置和复盘。",
        },
      ],
      interview_create_url: "/interviews",
    },
    result: null,
    steps: [
      { step_id: "step-plan", step_key: "plan", step_type: "read", status: "completed", attempt_count: 1, error_code: null },
      { step_id: "step-create", step_key: "create_tasks", step_type: "command", status: "pending", attempt_count: 0, error_code: null },
    ],
    events: [{ event: "planned", run_id: "run-training-1" }],
    error_code: null,
  };

  await page.route("**/api/agent-runs/training-program", async (route) => {
    expect(route.request().headers()["idempotency-key"]).toBeTruthy();
    await route.fulfill({ status: 201, json: proposal });
  });
  await page.route("**/api/agent-runs/run-training-1/confirm", async (route) => {
    completed = true;
    await route.fulfill({
      status: 200,
      json: {
        ...proposal,
        status: "completed",
        result: {
          task_ids: ["task-1"],
          task_count: 1,
          interview_create_url: "/interviews",
        },
        events: [...proposal.events, { event: "done", run_id: proposal.run_id }],
      },
    });
  });
  await page.route("**/api/learning-tasks?**", async (route) => {
    await route.fulfill({
      status: 200,
      json: completed
        ? [{
            task_id: "task-1",
            dimension: "工程实践",
            weakness: "缺少故障降级方案",
            action: "补充一次真实故障的指标、处置和复盘。",
            status: "todo",
            due_at: "2026-08-07T00:00:00+00:00",
            review_count: 0,
            next_review_at: "2026-08-01T00:00:00+00:00",
          }]
        : [],
    });
  });

  await page.addInitScript(({ payload, goal }) => {
    localStorage.setItem("interview-lab-state-v1", JSON.stringify(payload));
    localStorage.setItem(
      `interview-lab-goal:${payload.userId}`,
      JSON.stringify(goal),
    );
  }, {
    payload: {
      accessToken: auth.access_token,
      refreshToken: auth.refresh_token,
      username: auth.user.username,
      role: auth.user.role,
      userId: auth.user.user_id,
      sessionId: `workflow-${Date.now()}`,
    },
    goal: {
      targetRole: "Staff Backend Engineer",
      experienceLevel: "高级",
      focusAreas: "分布式系统",
      interviewDate: "",
      jobDescription: "",
    },
  });
  await page.goto("/learning");
  await page.getByLabel("生成主题").fill("分布式系统");
  await page.getByRole("button", { name: "生成个性化训练方案" }).click();

  const preview = page.getByRole("region", { name: "面向 Staff Backend Engineer 的训练安排" });
  await expect(preview).toContainText("缺少故障降级方案");
  await expect(preview).toContainText("不会自动开始面试或修改简历");
  await preview.getByRole("button", { name: "确认并创建任务" }).click();

  await expect(page.getByRole("heading", { name: "缺少故障降级方案" })).toBeVisible();
  await expect(preview).toBeHidden();
});
