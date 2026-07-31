// 模拟面试状态：answerCommand 保留到成功返回，使网络重试复用同一幂等键。
import { defineStore } from "pinia";
import type {
  ActiveInterview,
  AnswerResult,
  InterviewDetail,
  InterviewSummary,
} from "@/types";
import * as api from "@/api/client";
import { useAuthStore } from "@/stores/auth";

export const useInterviewsStore = defineStore("interviews", {
  state: () => ({
    history: [] as InterviewSummary[],
    historyLoading: false,
    historyError: null as string | null,
    includeArchived: false,
    active: null as ActiveInterview | null,
    /** 当前查看详情的面试(展开历史项时填充)。 */
    detail: null as InterviewDetail | null,
    detailLoading: false,
    starting: false,
    answering: false,
    lastAnswer: null as AnswerResult | null,
    answerCommand: null as { answer: string; key: string } | null,
  }),
  actions: {
    async initForUser() {
      const auth = useAuthStore();
      await this.loadHistory();
      const active = this.history.find(
        (item) => item.status === "active" && !item.archived_at,
      );
      if (active) {
        this.active = await api.resumeInterview(auth.userId, active.interview_id);
      } else {
        this.active = null;
      }
      this.answerCommand = null;
    },

    async loadHistory() {
      const auth = useAuthStore();
      this.historyLoading = true;
      this.historyError = null;
      try {
        this.history = await api.fetchInterviews(auth.userId, this.includeArchived);
      } catch (error) {
        this.historyError = error instanceof Error ? error.message : "历史加载失败";
      } finally {
        this.historyLoading = false;
      }
    },

    async start(
      topic: string,
      level: string,
      questionCount: number,
      resumeAnalysisId?: string,
    ) {
      const auth = useAuthStore();
      this.starting = true;
      try {
        this.active = await api.startInterview({
          userId: auth.userId,
          topic,
          level,
          questionCount,
          resumeAnalysisId,
        });
        this.lastAnswer = null;
        this.answerCommand = null;
        api.trackEvent(auth.userId, "interview.started", {
          interview_id: this.active.interview_id,
          topic,
          level,
          question_count: questionCount,
          source_type: this.active.source_type,
        });
        return this.active;
      } finally {
        this.starting = false;
      }
    },

    async resume(interviewId: string) {
      const auth = useAuthStore();
      this.active = await api.resumeInterview(auth.userId, interviewId);
      this.lastAnswer = null;
      this.answerCommand = null;
    },

    async answer(answer: string): Promise<AnswerResult> {
      const auth = useAuthStore();
      if (!this.active) throw new Error("没有进行中的面试");
      this.answering = true;
      // 只有回答正文变化才生成新命令；同一正文失败重试必须复用旧键。
      if (!this.answerCommand || this.answerCommand.answer !== answer) {
        this.answerCommand = {
          answer,
          key: globalThis.crypto.randomUUID(),
        };
      }
      try {
        const result = await api.answerInterview(
          auth.userId,
          this.active.interview_id,
          answer,
          this.answerCommand.key,
        );
        this.answerCommand = null;
        this.lastAnswer = result;
        if (result.next_question && this.active) {
          this.active.turn_index = result.turn_index + 1;
          this.active.question = result.next_question;
          this.active.status = result.status;
        } else if (this.active) {
          this.active.status = "completed";
          api.trackEvent(auth.userId, "interview.completed", {
            interview_id: this.active.interview_id,
          });
        }
        return result;
      } finally {
        this.answering = false;
      }
    },

    async retryAnswer(answer: string): Promise<AnswerResult> {
      const auth = useAuthStore();
      if (!this.active || !this.lastAnswer) {
        throw new Error("没有可重新回答的题目");
      }
      this.answering = true;
      try {
        const result = await api.retryInterviewAnswer(
          auth.userId,
          this.active.interview_id,
          this.lastAnswer.turn_index,
          answer,
        );
        this.lastAnswer = {
          ...result,
          next_question: this.lastAnswer.next_question,
        };
        api.trackEvent(auth.userId, "interview.answer_retried", {
          interview_id: this.active.interview_id,
          turn_index: result.turn_index,
          score_delta: result.comparison?.score_delta,
        });
        return this.lastAnswer;
      } finally {
        this.answering = false;
      }
    },

    async viewDetail(interviewId: string) {
      const auth = useAuthStore();
      this.detailLoading = true;
      try {
        this.detail = await api.fetchInterviewDetail(auth.userId, interviewId);
      } finally {
        this.detailLoading = false;
      }
    },

    clearDetail() {
      this.detail = null;
    },

    async archive(interviewId: string, archived: boolean) {
      const auth = useAuthStore();
      await api.archiveInterview(auth.userId, interviewId, archived);
      if (archived && this.active?.interview_id === interviewId) {
        this.active = null;
      }
      await this.loadHistory();
    },

    async remove(interviewId: string) {
      const auth = useAuthStore();
      await api.deleteInterview(auth.userId, interviewId);
      if (this.active?.interview_id === interviewId) {
        this.active = null;
      }
      this.detail = null;
      await this.loadHistory();
    },

    dismissActive() {
      this.active = null;
    },
  },
});
