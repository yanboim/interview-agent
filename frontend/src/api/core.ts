import type { AuthPayload } from "@/types";

const STORAGE_KEY = "interview-lab-state-v1";

interface PersistedState {
  accessToken?: string;
  refreshToken?: string;
  username?: string;
  role?: "user" | "admin";
}

function loadPersistedState(): PersistedState {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function savePersistedState(state: PersistedState) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}

export function makeId(prefix: string): string {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function buildHeaders(): HeadersInit {
  const state = loadPersistedState();
  const headers: Record<string, string> = {};
  if (state.accessToken) headers.Authorization = `Bearer ${state.accessToken}`;
  return headers;
}

async function refreshAuthentication(): Promise<boolean> {
  const state = loadPersistedState();
  if (!state.refreshToken) return false;
  try {
    const response = await fetch("/api/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: state.refreshToken }),
    });
    if (!response.ok) return false;
    const payload: AuthPayload = await response.json();
    savePersistedState({
      ...state,
      accessToken: payload.access_token,
      refreshToken: payload.refresh_token,
      username: payload.user.username,
      role: payload.user.role,
    });
    return true;
  } catch {
    return false;
  }
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiFetch(
  url: string,
  options: RequestInit = {},
  retry = true,
): Promise<Response> {
  const headers = {
    ...(options.headers || {}),
    ...buildHeaders(),
  };
  const response = await fetch(url, { ...options, headers });
  if (response.status === 401 && retry && (await refreshAuthentication())) {
    return apiFetch(url, options, false);
  }
  return response;
}

export async function parseApiError(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    return payload.detail || `请求失败（${response.status}）`;
  } catch {
    return `请求失败（${response.status}）`;
  }
}

export async function expectOk(response: Response): Promise<Response> {
  if (!response.ok) {
    throw new ApiError(await parseApiError(response), response.status);
  }
  return response;
}
