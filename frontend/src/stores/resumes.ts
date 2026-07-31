// 简历状态以服务端分析 revision 为并发版本，保存旧草稿时由后端拒绝覆盖新版本。
import { defineStore } from "pinia";
import * as api from "@/api/resumes";
import type { ResumeAnalysis, ResumeDocument, ResumeDraft } from "@/types";

export const useResumesStore = defineStore("resumes", {
  state: () => ({
    items: [] as ResumeDocument[],
    active: null as ResumeDocument | null,
    loading: false,
    error: "",
  }),
  getters: {
    activeAnalysis(state): ResumeAnalysis | null {
      return state.active?.analyses?.[0] || state.active?.latest_analysis || null;
    },
  },
  actions: {
    async load() {
      this.loading = true;
      this.error = "";
      try {
        this.items = await api.listResumes();
      } catch (error) {
        this.error = error instanceof Error ? error.message : "简历加载失败";
      } finally {
        this.loading = false;
      }
    },
    async open(resumeId: string) {
      this.loading = true;
      this.error = "";
      try {
        this.active = await api.getResume(resumeId);
      } catch (error) {
        this.error = error instanceof Error ? error.message : "简历加载失败";
      } finally {
        this.loading = false;
      }
    },
    async upload(file: File, jobDescription: string) {
      this.loading = true;
      this.error = "";
      try {
        this.active = await api.uploadResume(file, jobDescription);
        await this.load();
        return this.active;
      } finally {
        this.loading = false;
      }
    },
    async reanalyze(resumeId: string, jobDescription: string) {
      this.active = await api.reanalyzeResume(resumeId, jobDescription);
      await this.load();
    },
    async saveDraft(draft: ResumeDraft) {
      const analysis = this.activeAnalysis;
      if (!analysis) return;
      // 携带当前 revision 做乐观并发控制，不在客户端静默合并冲突草稿。
      const updated = await api.updateResumeDraft(
        analysis.analysis_id,
        analysis.revision,
        draft,
      );
      if (this.active?.analyses) {
        this.active.analyses[0] = updated;
      } else if (this.active) {
        this.active.latest_analysis = updated;
      }
    },
    async remove(resumeId: string) {
      await api.deleteResume(resumeId);
      if (this.active?.resume_id === resumeId) this.active = null;
      await this.load();
    },
  },
});
