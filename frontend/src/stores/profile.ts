import { defineStore } from "pinia";
import type { CapabilityProfile } from "@/types";
import * as api from "@/api/client";
import { useAuthStore } from "@/stores/auth";

const TOPIC_KEY = "interview-lab-profile-topic";

export const useProfileStore = defineStore("profile", {
  state: () => ({
    data: null as CapabilityProfile | null,
    loading: false,
    error: null as string | null,
    selectedTopic: (localStorage.getItem(TOPIC_KEY) || null) as string | null,
  }),
  actions: {
    setTopic(topic: string | null) {
      this.selectedTopic = topic;
      if (topic) localStorage.setItem(TOPIC_KEY, topic);
      else localStorage.removeItem(TOPIC_KEY);
    },

    async load() {
      const auth = useAuthStore();
      this.loading = true;
      this.error = null;
      try {
        this.data = await api.fetchCapabilityProfile(auth.userId, this.selectedTopic);
      } catch (error) {
        this.error = error instanceof Error ? error.message : "能力画像加载失败";
      } finally {
        this.loading = false;
      }
    },
  },
});
