// 前端 API 基础设施：统一封装 fetch、令牌持久化、自动刷新与错误解析。
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

/** 生成带前缀的唯一 ID，优先用原生 randomUUID，否则回退到时间+随机数。 */
export function makeId(prefix: string): string {
  if (typeof globalThis.crypto?.randomUUID === "function") {
    return `${prefix}-${crypto.randomUUID()}`;
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/** 从 localStorage 读取访问令牌并组装带 Authorization 的请求头。 */
function buildHeaders(): HeadersInit {
  const state = loadPersistedState();
  const headers: Record<string, string> = {};
  if (state.accessToken) headers.Authorization = `Bearer ${state.accessToken}`;
  return headers;
}

/** 用刷新令牌换取新的访问令牌并持久化；成功返回 true，失败/无令牌返回 false。 */
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

/** 统一 API 错误类型，携带 HTTP 状态码与可展示的 detail 文案。 */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * 统一的带鉴权 fetch：自动注入令牌头，遇 401 时尝试刷新令牌并重试一次。
 * @param retry 是否允许在 401 后自动刷新重试（内部递归时置 false 防止死循环）。
 */
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

/** 解析响应错误体为可展示文案，失败时回退到「请求失败（状态码）」。 */
export async function parseApiError(response: Response): Promise<string> {
  try {
    const payload = await response.json();
    return payload.detail || `请求失败（${response.status}）`;
  } catch {
    return `请求失败（${response.status}）`;
  }
}

/** 断言响应成功，否则抛出携带状态码与文案的 ApiError。 */
export async function expectOk(response: Response): Promise<Response> {
  if (!response.ok) {
    throw new ApiError(await parseApiError(response), response.status);
  }
  return response;
}
