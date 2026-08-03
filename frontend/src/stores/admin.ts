// 管理端资源中心状态：用户/审计/交互/知识/发版等只读观察数据。
import { defineStore } from "pinia";
import type {
  AdminAudit,
  AdminAuditEvent,
  AdminExecutionTrace,
  AdminInteraction,
  AdminKnowledgeFile,
  AdminRuntime,
  AdminResourceCenter,
  AdminSummary,
  AdminUser,
  DeploymentRelease,
  ProductEvent,
} from "@/types";
import * as api from "@/api/client";

export const useAdminStore = defineStore("admin", {
  state: () => ({
    summary: null as AdminSummary | null,
    runtime: null as AdminRuntime | null,
    resourceCenter: null as AdminResourceCenter | null,
    knowledgeFiles: [] as AdminKnowledgeFile[],
    users: [] as AdminUser[],
    audits: [] as AdminAudit[],
    auditEvents: [] as AdminAuditEvent[],
    interactions: [] as AdminInteraction[],
    executionTrace: [] as AdminExecutionTrace[],
    productEvents: [] as ProductEvent[],
    releases: [] as DeploymentRelease[],
    overviewLoading: false,
    resourcesLoading: false,
    knowledgeLoading: false,
    usersLoading: false,
    auditsLoading: false,
    interactionLoading: false,
    traceLoading: false,
    analyticsLoading: false,
    releasesLoading: false,
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

    async loadResources() {
      this.resourcesLoading = true;
      try {
        this.resourceCenter = await api.fetchAdminResources();
      } finally {
        this.resourcesLoading = false;
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
        const [auditEvents, interactions] = await Promise.all([
          api.fetchAdminAuditEvents(),
          api.fetchAdminInteractions(),
        ]);
        this.auditEvents = auditEvents;
        this.interactions = interactions;
      } finally {
        this.auditsLoading = false;
      }
    },

    async loadInteractionTrace(interaction: AdminInteraction) {
      this.traceLoading = true;
      this.executionTrace = [];
      try {
        this.executionTrace = await api.fetchAdminInteractionTrace(
          interaction,
        );
      } finally {
        this.traceLoading = false;
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

    async loadReleases() {
      this.releasesLoading = true;
      try {
        this.releases = await api.fetchAdminReleases();
      } finally {
        this.releasesLoading = false;
      }
    },
  },
});
