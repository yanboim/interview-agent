// 管理端 API 基础设施：管理员会话独立持久化（sessionStorage）与带鉴权的 fetch。
import type { AuthPayload } from "@/types";
import { ApiError, parseApiError } from "@/api/core";

export const ADMIN_STORAGE_KEY = "interview-lab-admin-state-v1";

export interface AdminPersistedState {
  accessToken?: string;
  refreshToken?: string;
  username?: string;
}

export function loadAdminState(): AdminPersistedState {
  try {
    const raw = sessionStorage.getItem(ADMIN_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

export function saveAdminState(state: AdminPersistedState) {
  sessionStorage.setItem(ADMIN_STORAGE_KEY, JSON.stringify(state));
}

export function clearAdminState() {
  sessionStorage.removeItem(ADMIN_STORAGE_KEY);
}

async function refreshAdminAuthentication(): Promise<boolean> {
  const state = loadAdminState();
  if (!state.refreshToken) return false;
  try {
    const response = await fetch("/api/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: state.refreshToken }),
    });
    if (!response.ok) return false;
    const payload: AuthPayload = await response.json();
    if (payload.user.role !== "admin") {
      clearAdminState();
      return false;
    }
    saveAdminState({
      accessToken: payload.access_token,
      refreshToken: payload.refresh_token,
      username: payload.user.username,
    });
    return true;
  } catch {
    return false;
  }
}

export async function adminFetch(
  url: string,
  options: RequestInit = {},
  retry = true,
): Promise<Response> {
  const state = loadAdminState();
  const headers = {
    ...(options.headers || {}),
    ...(state.accessToken ? { Authorization: `Bearer ${state.accessToken}` } : {}),
  };
  const response = await fetch(url, { ...options, headers });
  if (response.status === 401 && retry && (await refreshAdminAuthentication())) {
    return adminFetch(url, options, false);
  }
  return response;
}

export async function expectAdminOk(response: Response): Promise<Response> {
  if (!response.ok) {
    throw new ApiError(await parseApiError(response), response.status);
  }
  return response;
}
