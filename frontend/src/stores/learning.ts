import { defineStore } from "pinia";
import type { LearningStatus, LearningTask } from "@/types";
import * as api from "@/api/client";
import { useAuthStore } from "@/stores/auth";

const STATUS_KEY = "interview-lab-learning-status";

export const useLearningStore = defineStore("learning", {
  state: () => ({
    tasks: [] as LearningTask[],
    loading: false,
    error: null as string | null,
    statusFilter: (localStorage.getItem(STATUS_KEY) || "") as LearningStatus | "",
    generating: false,
    totalCount: 0,
    dueCountValue: 0,
  }),
  getters: {
    dueCount: (state) => state.dueCountValue,
  },
  actions: {
    setStatusFilter(status: LearningStatus | "") {
      this.statusFilter = status;
      if (status) localStorage.setItem(STATUS_KEY, status);
      else localStorage.removeItem(STATUS_KEY);
    },

    async load() {
      const auth = useAuthStore();
      this.loading = true;
      this.error = null;
      try {
        const allTasks = await api.fetchLearningTasks(auth.userId, null);
        this.totalCount = allTasks.length;
        this.dueCountValue = allTasks.filter(
          (task) => task.status !== "completed" && new Date(task.due_at) < new Date(),
        ).length;
        this.tasks = this.statusFilter
          ? allTasks.filter((task) => task.status === this.statusFilter)
          : allTasks;
      } catch (error) {
        this.error = error instanceof Error ? error.message : "学习任务加载失败";
      } finally {
        this.loading = false;
      }
    },

    async generate(topic: string | null = null) {
      const auth = useAuthStore();
      this.generating = true;
      try {
        const payload = await api.generateLearningTasks(
          auth.userId,
          topic,
        );
        this.tasks = payload.tasks;
        this.totalCount = payload.tasks.length;
        this.dueCountValue = payload.tasks.filter(
          (task) => task.status !== "completed" && new Date(task.due_at) < new Date(),
        ).length;
        api.trackEvent(auth.userId, "learning.plan_generated", {
          topic,
          task_count: payload.tasks.length,
        });
      } finally {
        this.generating = false;
      }
    },

    async update(taskId: string, changes: Partial<Pick<LearningTask, "status" | "due_at">>) {
      const auth = useAuthStore();
      await api.updateLearningTask(auth.userId, taskId, changes);
      await this.load();
    },

    async review(taskId: string) {
      const auth = useAuthStore();
      await api.reviewLearningTask(auth.userId, taskId);
      api.trackEvent(auth.userId, "learning.task_reviewed", { task_id: taskId });
      await this.load();
    },

    async remove(taskId: string) {
      const auth = useAuthStore();
      await api.deleteLearningTask(auth.userId, taskId);
      await this.load();
    },
  },
});
