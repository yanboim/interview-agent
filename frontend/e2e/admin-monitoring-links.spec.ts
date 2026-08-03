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
      agent: { mode: "workflow_v2", specialists: [] },
      operator_links: [
        {
          id: "prometheus",
          name: "Prometheus",
          url: "https://ops.example.test/prometheus/",
        },
        {
          id: "grafana",
          name: "Grafana",
          url: "https://ops.example.test/grafana/",
        },
      ],
    }),
  }));
});

test("administrator navigation exposes configured monitoring consoles", async ({
  page,
}) => {
  await page.goto("/admin");

  const navigation = page.getByRole("navigation", { name: "后台导航" });
  await expect(navigation.getByText("运维工具")).toBeVisible({
    timeout: 15_000,
  });

  const prometheus = navigation.getByRole("link", { name: /Prometheus/ });
  const grafana = navigation.getByRole("link", { name: /Grafana/ });
  await expect(prometheus).toHaveAttribute(
    "href",
    "https://ops.example.test/prometheus/",
  );
  await expect(grafana).toHaveAttribute(
    "href",
    "https://ops.example.test/grafana/",
  );
  for (const link of [prometheus, grafana]) {
    await expect(link).toHaveAttribute("target", "_blank");
    await expect(link).toHaveAttribute("rel", "noopener noreferrer");
  }

  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  );
  expect(hasHorizontalOverflow).toBe(false);
});
