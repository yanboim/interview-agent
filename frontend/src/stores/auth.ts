import { defineStore } from "pinia";
import type { AuthPayload, AuthUser, InterviewGoal } from "@/types";
import * as api from "@/api/client";

const STORAGE_KEY = "interview-lab-state-v1";
const GOAL_KEY = "interview-lab-goal";

function loadGoal(userId: string): InterviewGoal | null {
  try {
    const raw = localStorage.getItem(`${GOAL_KEY}:${userId}`);
    return raw ? (JSON.parse(raw) as InterviewGoal) : null;
  } catch {
    return null;
  }
}

interface PersistShape {
  accessToken?: string;
  refreshToken?: string;
  username?: string;
  role?: AuthUser["role"];
  userId?: string;
  sessionId?: string;
}

/** 顶层应用持久化结构(与旧 app.js 兼容)。 */
interface AppPersist extends PersistShape {
  messages?: unknown[];
  mode?: string;
}

function loadPersisted(): AppPersist {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : {};
  } catch {
    return {};
  }
}

function savePersisted(patch: Partial<PersistShape>) {
  const current = loadPersisted();
  localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...current, ...patch }));
}

export const useAuthStore = defineStore("auth", {
  state: () => {
    const persisted = loadPersisted();
    return {
      authRequired: false,
      accessToken: persisted.accessToken || undefined,
      refreshToken: persisted.refreshToken || undefined,
      userId: persisted.userId || api.makeId("user"),
      sessionId: persisted.sessionId || api.makeId("web"),
      username: persisted.username || "",
      role: persisted.role as AuthUser["role"] | undefined,
      interviewGoal: loadGoal(persisted.userId || "anonymous") as InterviewGoal | null,
      pendingRecoveryCode: "" as string,
      goalLoading: false,
      initializing: true,
    };
  },
  getters: {
    isAuthenticated: (state) => Boolean(state.accessToken),
    hasInterviewGoal: (state) => Boolean(state.interviewGoal?.targetRole),
  },
  actions: {
    applyPayload(payload: AuthPayload) {
      this.accessToken = payload.access_token;
      this.refreshToken = payload.refresh_token;
      this.userId = payload.user.user_id;
      this.username = payload.user.username;
      this.role = payload.user.role;
      // 登录后开启新的服务端会话
      this.sessionId = api.makeId("web");
      this.interviewGoal = loadGoal(this.userId);
      savePersisted({
        accessToken: this.accessToken,
        refreshToken: this.refreshToken,
        username: this.username,
        role: this.role,
        userId: this.userId,
        sessionId: this.sessionId,
      });
    },

    async saveInterviewGoal(goal: InterviewGoal) {
      this.goalLoading = true;
      try {
        const saved = await api.updateInterviewGoal(this.userId, goal);
        this.interviewGoal = saved;
        localStorage.setItem(`${GOAL_KEY}:${this.userId}`, JSON.stringify(saved));
        api.trackEvent(this.userId, "profile.goal_saved", {
          has_job_description: Boolean(saved.jobDescription),
          experience_level: saved.experienceLevel,
        });
      } finally {
        this.goalLoading = false;
      }
    },

    async loadInterviewGoal() {
      const cached = loadGoal(this.userId);
      if (cached) this.interviewGoal = cached;
      this.goalLoading = true;
      try {
        const serverGoal = await api.fetchInterviewGoal(this.userId);
        this.interviewGoal = serverGoal;
        if (serverGoal) {
          localStorage.setItem(`${GOAL_KEY}:${this.userId}`, JSON.stringify(serverGoal));
        }
      } catch {
        this.interviewGoal = cached;
      } finally {
        this.goalLoading = false;
      }
    },

    newSession() {
      this.sessionId = api.makeId("web");
      const persisted = loadPersisted();
      savePersisted({ ...persisted, sessionId: this.sessionId });
    },

    async initialize() {
      try {
        const config = await api.fetchPublicConfig();
        this.authRequired = config.auth_required;
        if (!config.auth_required) {
          this.initializing = false;
          return;
        }
        if (this.accessToken) {
          try {
            const user = await api.fetchCurrentUser();
            if (user.role !== "user") {
              this.accessToken = undefined;
              this.refreshToken = undefined;
              this.username = "";
              this.role = undefined;
              const current = loadPersisted();
              savePersisted({
                ...current,
                accessToken: undefined,
                refreshToken: undefined,
                username: "",
                role: undefined,
              });
              this.initializing = false;
              return;
            }
            this.userId = user.user_id;
            this.username = user.username;
            this.role = user.role;
            await this.loadInterviewGoal();
            savePersisted({
              username: this.username,
              role: this.role,
              userId: this.userId,
            });
            this.initializing = false;
            return;
          } catch {
            // token 失效,落到登录界面
          }
        }
      } catch {
        // 配置读取失败,默认要求登录
        this.authRequired = true;
      }
      this.initializing = false;
    },

    async login(username: string, password: string) {
      const payload = await api.login(username, password);
      this.applyPayload(payload);
      await this.loadInterviewGoal();
    },

    async register(username: string, password: string) {
      const payload = await api.register(username, password);
      this.applyPayload(payload);
      this.pendingRecoveryCode = payload.recovery_code || "";
      await this.loadInterviewGoal();
    },

    acknowledgeRecoveryCode() {
      this.pendingRecoveryCode = "";
    },

    async logout() {
      try {
        await api.logout(this.refreshToken);
      } catch {
        // 即使后端撤销失败也清理本地态
      }
      this.accessToken = undefined;
      this.refreshToken = undefined;
      this.username = "";
      this.role = undefined;
      this.interviewGoal = null;
      this.pendingRecoveryCode = "";
      this.userId = api.makeId("user");
      this.sessionId = api.makeId("web");
      const persisted = loadPersisted();
      savePersisted({
        ...persisted,
        accessToken: undefined,
        refreshToken: undefined,
        username: "",
        role: undefined,
        userId: this.userId,
        sessionId: this.sessionId,
      });
    },
  },
});
