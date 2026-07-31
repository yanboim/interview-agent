// 面试复盘状态以 transcript_revision 保护逐字稿编辑和确认之间的并发边界。
import { defineStore } from "pinia";
import * as api from "@/api/reviews";
import type { InterviewReview, TranscriptSegment } from "@/types";

export const useReviewsStore = defineStore("reviews", {
  state: () => ({
    items: [] as InterviewReview[],
    active: null as InterviewReview | null,
    loading: false,
    error: "",
  }),
  actions: {
    async load() {
      this.loading = true;
      try {
        this.items = await api.listReviews();
      } finally {
        this.loading = false;
      }
    },
    async open(reviewId: string) {
      this.active = await api.getReview(reviewId);
      return this.active;
    },
    async createText(transcript: string) {
      this.active = await api.createTextReview(transcript);
      await this.load();
      return this.active;
    },
    async createAudio(file: File, consent: boolean) {
      this.active = await api.createAudioReview(file, consent);
      await this.load();
      return this.active;
    },
    async save(segments: TranscriptSegment[]) {
      if (!this.active) return;
      this.active = await api.updateReviewTranscript(
        this.active.review_id,
        this.active.transcript_revision,
        segments,
      );
    },
    async confirm() {
      if (!this.active) return;
      // 确认后后台分析只接受这个 revision，避免分析用户随后又修改的旧文本。
      this.active = await api.confirmReview(
        this.active.review_id,
        this.active.transcript_revision,
      );
    },
    async retry() {
      if (!this.active) return;
      this.active = await api.retryReview(this.active.review_id);
    },
    async remove(reviewId: string) {
      await api.deleteReview(reviewId);
      if (this.active?.review_id === reviewId) this.active = null;
      await this.load();
    },
  },
});
