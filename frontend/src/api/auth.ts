// 认证 API：注册、登录、刷新、登出、改密、恢复码与当前用户信息。
import type { AuthPayload } from "@/types";
import { apiFetch, expectOk } from "@/api/core";

export async function register(username: string, password: string): Promise<AuthPayload> {
  const response = await fetch("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  await expectOk(response);
  return response.json();
}

export async function login(username: string, password: string): Promise<AuthPayload> {
  const response = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  await expectOk(response);
  return response.json();
}

export async function logout(refreshToken: string | undefined): Promise<void> {
  await apiFetch(
    "/api/auth/logout",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken || null }),
    },
    false,
  );
}

export async function fetchCurrentUser(): Promise<AuthPayload["user"]> {
  const response = await apiFetch("/api/auth/me");
  await expectOk(response);
  return response.json();
}

export async function fetchPublicConfig(): Promise<{
  auth_required: boolean;
  resume_feature_enabled?: boolean;
  review_feature_enabled?: boolean;
  transcription_enabled?: boolean;
  transcription_provider_name?: string;
}> {
  const response = await fetch("/api/config");
  await expectOk(response);
  return response.json();
}

export async function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  const response = await apiFetch("/api/auth/change-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });
  await expectOk(response);
}

export async function resetPassword(
  username: string,
  recoveryCode: string,
  newPassword: string,
): Promise<{ recovery_code: string }> {
  const response = await fetch("/api/auth/reset-password", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      username,
      recovery_code: recoveryCode,
      new_password: newPassword,
    }),
  });
  await expectOk(response);
  return response.json();
}

export async function regenerateRecoveryCode(): Promise<string> {
  const response = await apiFetch("/api/auth/recovery-code", { method: "POST" });
  await expectOk(response);
  const payload = await response.json();
  return payload.recovery_code;
}
