import { expect, test } from "@playwright/test";

test("goal setup fits a short mobile viewport without an inner scrollbar", async ({
  page,
  request,
}) => {
  const username = `goal_${Date.now()}`;
  const password = "Goal-dialog-2026!";
  const registration = await request.post("/api/auth/register", {
    data: { username, password },
  });
  expect(registration.ok()).toBe(true);
  const payload = await registration.json();

  await page.setViewportSize({ width: 393, height: 568 });
  await page.addInitScript((auth) => {
    localStorage.setItem("interview-lab-state-v1", JSON.stringify(auth));
  }, {
    accessToken: payload.access_token,
    refreshToken: payload.refresh_token,
    username: payload.user.username,
    role: payload.user.role,
    userId: payload.user.user_id,
    sessionId: `e2e-${Date.now()}`,
  });

  await page.goto("/today");
  const dialog = page.getByRole("dialog", { name: "先确定你的面试目标" });
  await expect(dialog).toBeVisible();
  await expect(page.getByText("完善面试信息")).toBeVisible();

  const layout = await dialog.evaluate((element) => {
    const bounds = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return {
      bottom: bounds.bottom,
      clientHeight: element.clientHeight,
      overflowY: style.overflowY,
      scrollHeight: element.scrollHeight,
      top: bounds.top,
      viewportHeight: window.innerHeight,
    };
  });

  expect(layout.overflowY).not.toBe("auto");
  expect(layout.scrollHeight).toBeLessThanOrEqual(layout.clientHeight + 1);
  expect(layout.top).toBeGreaterThanOrEqual(0);
  expect(layout.bottom).toBeLessThanOrEqual(layout.viewportHeight);
});
