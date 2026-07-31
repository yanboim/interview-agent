import { expect, test } from "@playwright/test";

test("avatar and reminder controls stay compact and persist by account", async ({
  page,
  request,
}, testInfo) => {
  const username = `avatar_${Date.now()}_${testInfo.project.name.replaceAll("-", "_")}`;
  const password = "Avatar-profile-2026!";
  const registration = await request.post("/api/auth/register", {
    data: { username, password },
  });
  expect(registration.ok()).toBe(true);
  const payload = await registration.json();
  const headers = { Authorization: `Bearer ${payload.access_token}` };

  const profile = await request.put("/api/profile", {
    headers,
    data: {
      user_id: payload.user.user_id,
      target_role: "高级 Java 工程师",
      experience_level: "高级",
      focus_areas: "",
      interview_date: null,
      job_description: "",
    },
  });
  expect(profile.ok()).toBe(true);

  await page.addInitScript(({ auth, goal }) => {
    localStorage.setItem("interview-lab-state-v1", JSON.stringify(auth));
    localStorage.setItem(
      `interview-lab-goal:${auth.userId}`,
      JSON.stringify(goal),
    );
  }, {
    auth: {
      accessToken: payload.access_token,
      refreshToken: payload.refresh_token,
      username: payload.user.username,
      role: payload.user.role,
      userId: payload.user.user_id,
      sessionId: `e2e-${Date.now()}`,
    },
    goal: {
      targetRole: "高级 Java 工程师",
      experienceLevel: "高级",
      focusAreas: "",
      interviewDate: "",
      jobDescription: "",
    },
  });
  await page.goto("/today");
  if (testInfo.project.name.startsWith("mobile")) {
    await page.getByRole("button", { name: "打开菜单" }).click();
  }

  const avatar = page.getByRole("button", { name: "设置头像" });
  await expect(avatar).toBeVisible();
  const avatarLayout = await avatar.evaluate((element) => {
    const bounds = element.getBoundingClientRect();
    return {
      width: bounds.width,
      height: bounds.height,
      left: bounds.left,
      parentLeft: element.parentElement?.getBoundingClientRect().left || 0,
    };
  });
  expect(avatarLayout.width).toBe(40);
  expect(avatarLayout.height).toBe(40);
  expect(avatarLayout.left).toBeGreaterThanOrEqual(avatarLayout.parentLeft);

  await avatar.click();
  const dialog = page.getByRole("dialog", { name: "训练目标与高级设置" });
  await expect(dialog).toBeVisible();

  const reminder = page.getByRole("checkbox", { name: "开启每日到期复习提醒" });
  const reminderTrack = dialog.locator(".reminder-switch-track");
  await expect(reminder).not.toBeChecked();
  await expect(reminderTrack).toHaveCSS("width", "42px");
  await expect(reminderTrack).toHaveCSS("height", "24px");
  await reminder.check();
  await expect(reminder).toBeChecked();

  const avatarPng = await page.screenshot();
  await page.getByLabel("选择头像图片").setInputFiles({
    name: "avatar.png",
    mimeType: "image/png",
    buffer: avatarPng,
  });
  await expect(dialog.locator(".avatar-preview img")).toBeVisible();
  await page.getByRole("button", { name: "保存设置" }).click();
  await expect(dialog).toBeHidden();

  await expect(page.getByRole("button", { name: "设置头像" }).locator("img")).toBeVisible();

  const savedProfile = await request.get(
    `/api/profile?user_id=${encodeURIComponent(payload.user.user_id)}`,
    { headers },
  );
  expect(savedProfile.ok()).toBe(true);
  expect((await savedProfile.json()).avatar_data_url).toMatch(/^data:image\/webp;base64,/);

  await page.getByRole("button", { name: "设置头像" }).click();
  const reopenedDialog = page.getByRole("dialog", { name: "训练目标与高级设置" });
  await reopenedDialog.getByLabel("新记忆").fill("偏好先看详细原理");
  await reopenedDialog.getByRole("button", { name: "添加待确认记忆" }).click();
  let memoryItem = reopenedDialog.locator(".memory-settings-list li").filter({
    hasText: "偏好先看详细原理",
  });
  await expect(memoryItem).toContainText("待确认");
  await memoryItem.getByRole("button", { name: "确认", exact: true }).click();
  await expect(memoryItem).toContainText("已确认");
  await memoryItem.getByRole("button", { name: "纠正", exact: true }).click();
  memoryItem = reopenedDialog.locator(".memory-settings-list li").last();
  await memoryItem.getByRole("textbox").fill("偏好先看结论，再看详细原理");
  await memoryItem.getByRole("button", { name: "保存纠正" }).click();
  memoryItem = reopenedDialog.locator(".memory-settings-list li").filter({
    hasText: "偏好先看结论，再看详细原理",
  });
  await expect(memoryItem).toContainText("待确认");
  await memoryItem.getByRole("button", { name: "确认", exact: true }).click();
  await expect(memoryItem).toContainText("已确认");
  await reopenedDialog.getByRole("button", { name: "取消" }).click();

  await page.getByRole("button", { name: "设置头像" }).click();
  const persistedMemory = page
    .getByRole("dialog", { name: "训练目标与高级设置" })
    .locator(".memory-settings-list li")
    .filter({ hasText: "偏好先看结论，再看详细原理" });
  await expect(persistedMemory).toContainText("已确认");
  await expect(persistedMemory.locator("span")).toHaveText("偏好先看结论，再看详细原理");
  await page.getByRole("button", { name: "取消" }).click();

  const hasHorizontalOverflow = await page.evaluate(
    () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  );
  expect(hasHorizontalOverflow).toBe(false);
});
