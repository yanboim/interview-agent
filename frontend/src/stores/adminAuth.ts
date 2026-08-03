// 管理端会话状态：与产品用户隔离，令牌仅存 sessionStorage。
import { defineStore } from "pinia";
import type { AuthPayload } from "@/types";
import {
  adminFetch,
  clearAdminState,
  expectAdminOk,
  loadAdminState,
  saveAdminState,
} from "@/api/adminCore";

export const useAdminAuthStore = defineStore("admin-auth", {
  state: () => {
    const persisted = loadAdminState();
    return {
      accessToken: persisted.accessToken,
      refreshToken: persisted.refreshToken,
      username: persisted.username || "",
      initializing: true,
    };
  },
  getters: {
    isAuthenticated: (state) => Boolean(state.accessToken),
  },
  actions: {
    async initialize() {
      if (!this.accessToken) {
        this.initializing = false;
        return;
      }
      try {
        const response = await adminFetch("/api/auth/me");
        await expectAdminOk(response);
        const user: AuthPayload["user"] = await response.json();
        if (user.role !== "admin") throw new Error("管理员身份无效");
        this.username = user.username;
      } catch {
        this.clear();
      } finally {
        this.initializing = false;
      }
    },

    async login(username: string, password: string) {
      const response = await fetch("/api/admin/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      await expectAdminOk(response);
      const payload: AuthPayload = await response.json();
      this.accessToken = payload.access_token;
      this.refreshToken = payload.refresh_token;
      this.username = payload.user.username;
      saveAdminState({
        accessToken: this.accessToken,
        refreshToken: this.refreshToken,
        username: this.username,
      });
    },

    async logout() {
      try {
        await adminFetch(
          "/api/auth/logout",
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ refresh_token: this.refreshToken || null }),
          },
          false,
        );
      } finally {
        this.clear();
      }
    },

    clear() {
      this.accessToken = undefined;
      this.refreshToken = undefined;
      this.username = "";
      clearAdminState();
    },
  },
});
