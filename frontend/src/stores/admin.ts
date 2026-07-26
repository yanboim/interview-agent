import { defineStore } from "pinia";
import type {
  AdminAudit,
  AdminKnowledgeFile,
  AdminRuntime,
  AdminSummary,
  AdminUser,
  ProductEvent,
} from "@/types";
import * as api from "@/api/client";

export const useAdminStore = defineStore("admin", {
  state: () => ({
    summary: null as AdminSummary | null,
    runtime: null as AdminRuntime | null,
    knowledgeFiles: [] as AdminKnowledgeFile[],
    users: [] as AdminUser[],
    audits: [] as AdminAudit[],
    productEvents: [] as ProductEvent[],
    overviewLoading: false,
    knowledgeLoading: false,
    usersLoading: false,
    auditsLoading: false,
    analyticsLoading: false,
    jobId: null as string | null,
    jobStatus: null as string | null,
    jobError: null as string | null,
  }),
  actions: {
    async loadOverview() {
      this.overviewLoading = true;
      try {
        const [summary, runtime] = await Promise.all([
          api.fetchAdminSummary(),
          api.fetchAdminRuntime(),
        ]);
        this.summary = summary;
        this.runtime = runtime;
      } finally {
        this.overviewLoading = false;
      }
    },

    async loadKnowledge() {
      this.knowledgeLoading = true;
      try {
        this.knowledgeFiles = await api.fetchAdminKnowledgeFiles();
      } finally {
        this.knowledgeLoading = false;
      }
    },

    async uploadFile(filename: string, content: string) {
      await api.uploadKnowledgeFile(filename, content);
      await this.loadKnowledge();
    },

    async deleteFile(filename: string) {
      await api.deleteKnowledgeFile(filename);
      await this.loadKnowledge();
    },

    async startImport() {
      const { job_id } = await api.enqueueKnowledgeImport();
      this.jobId = job_id;
      this.jobStatus = "queued";
      this.jobError = null;
    },

    async pollImport() {
      if (!this.jobId) return false;
      const job = await api.fetchImportJob(this.jobId);
      this.jobStatus = job.status;
      this.jobError = job.error || null;
      return ["completed", "failed", "ignored"].includes(job.status);
    },

    async loadUsers() {
      this.usersLoading = true;
      try {
        this.users = await api.fetchAdminUsers();
      } finally {
        this.usersLoading = false;
      }
    },

    async loadAudits() {
      this.auditsLoading = true;
      try {
        this.audits = await api.fetchAdminAudits();
      } finally {
        this.auditsLoading = false;
      }
    },

    async loadAnalytics() {
      this.analyticsLoading = true;
      try {
        this.productEvents = await api.fetchAdminProductEvents();
      } finally {
        this.analyticsLoading = false;
      }
    },
  },
});
