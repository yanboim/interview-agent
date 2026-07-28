import { expect, test } from "@playwright/test";

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
  await page.route("**/api/auth/me", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      user_id: "admin-1",
      username: "operator",
      role: "admin",
    }),
  }));
  await page.route("**/api/admin/system-summary", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({ operator: "operator", role: "admin", counts: {} }),
  }));
  await page.route("**/api/admin/runtime", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      dependencies: {},
      features: {},
      agent: { mode: "supervisor", specialists: [] },
    }),
  }));
  await page.route("**/api/admin/audit-events?limit=200", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([{
        event_id: "event-1",
        request_id: "request-1",
        actor_user_id: "user-1",
        actor_username: "alice",
        actor_role: "user",
        action: "chat",
        resource_type: "chat",
        resource_id: null,
        outcome: "success",
        method: "POST",
        path: "/api/chat",
        status_code: 200,
        duration_ms: 321,
        detail_json: "{}",
        created_at: "2026-07-28T16:00:00+00:00",
      }]),
    }),
  );
  await page.route("**/api/admin/interactions?limit=100", (route) =>
    route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([{
        interaction_type: "chat",
        interaction_id: "turn-1",
        user_id: "user-1",
        username: "alice",
        container_id: "session-1",
        container_title: "RAG 设计讨论",
        prompt_text: "",
        input_text: "用户输入原文",
        output_text: "系统输出原文",
        status: "completed",
        error: "",
        metadata_json: "{}",
        created_at: "2026-07-28T16:00:00+00:00",
        updated_at: "2026-07-28T16:00:01+00:00",
      }]),
    }),
  );
  await page.route(
    "**/api/admin/interactions/chat/turn-1/trace",
    (route) => route.fulfill({
      contentType: "application/json",
      body: JSON.stringify([{
        trace_id: "trace-1",
        request_id: "request-1",
        user_id: "user-1",
        interaction_type: "chat",
        interaction_id: "turn-1",
        stage: "agent_execution",
        status: "completed",
        duration_ms: 300,
        detail_json: "{\"model\":\"glm\"}",
        created_at: "2026-07-28T16:00:01+00:00",
      }]),
    }),
  );
});

test("administrator can correlate activity content and execution trace", async ({
  page,
}) => {
  await page.goto("/admin");
  await page.getByRole("button", { name: "审计中心" }).click();

  await expect(page.getByText("alice")).toBeVisible();
  await expect(page.getByText("request-1")).toBeVisible();
  await page.getByRole("tab", { name: "交互记录与执行链路" }).click();
  await page.getByRole("button", { name: /alice.*RAG 设计讨论/s }).click();

  const content = page.locator(".interaction-detail .content-block pre");
  await expect(content.nth(0)).toHaveText("用户输入原文");
  await expect(content.nth(1)).toHaveText("系统输出原文");
  await expect(page.getByText("agent_execution")).toBeVisible();
  await expect(page.getByText(/\"model\": \"glm\"/)).toBeVisible();
});
