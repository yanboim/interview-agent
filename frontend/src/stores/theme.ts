// 主题状态：浅色/深色/跟随系统，持久化并应用 ``data-theme`` 到根元素。
import { defineStore } from "pinia";

export type ThemePreference = "light" | "dark" | "auto";

const THEME_KEY = "interview-lab-theme";

function detectInitial(): ThemePreference {
  const stored = localStorage.getItem(THEME_KEY) as ThemePreference | null;
  if (stored === "light" || stored === "dark" || stored === "auto") return stored;
  return "auto";
}

function systemPrefersDark(): boolean {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

export const useThemeStore = defineStore("theme", {
  state: () => ({
    preference: detectInitial(),
  }),
  getters: {
    isDark: (state) =>
      state.preference === "dark" || (state.preference === "auto" && systemPrefersDark()),
  },
  actions: {
    apply() {
      document.documentElement.dataset.theme = this.isDark ? "dark" : "light";
    },
    set(preference: ThemePreference) {
      this.preference = preference;
      localStorage.setItem(THEME_KEY, preference);
      this.apply();
    },
    init() {
      this.apply();
      // 跟随系统变化(仅当处于 auto)
      const mql = window.matchMedia?.("(prefers-color-scheme: dark)");
      if (mql && typeof mql.addEventListener === "function") {
        mql.addEventListener("change", () => {
          if (this.preference === "auto") this.apply();
        });
      }
    },
  },
});
