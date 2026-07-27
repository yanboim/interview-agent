import { defineStore } from "pinia";
import type { ChatMessage } from "@/types";
import * as api from "@/api/client";
import { useAuthStore } from "@/stores/auth";

const MESSAGE_CACHE_KEY = "interview-lab-msgs";

/** 只缓存当前会话的最近消息(便于刷新后恢复),长历史走服务端。 */
function loadCachedMessages(sessionId: string): ChatMessage[] {
  try {
    const raw = sessionStorage.getItem(`${MESSAGE_CACHE_KEY}:${sessionId}`);
    return raw ? (JSON.parse(raw) as ChatMessage[]) : [];
  } catch {
    return [];
  }
}

function saveCachedMessages(sessionId: string, messages: ChatMessage[]) {
  try {
    sessionStorage.setItem(
      `${MESSAGE_CACHE_KEY}:${sessionId}`,
      JSON.stringify(messages.slice(-50)),
    );
  } catch {
    // 容量超限等错误时静默放弃缓存
  }
}

export const useChatStore = defineStore("chat", {
  state: () => ({
    messages: [] as ChatMessage[],
    sending: false,
    /** 当前流式请求的 AbortController,用于支持「停止生成」。 */
    abortController: null as AbortController | null,
    /** 单调递增的请求编号,用于阻止已取消请求继续写入新会话。 */
    streamRequestId: 0,
    /** 最近一次发送完成的时间戳,用于通知外部(如侧边栏刷新会话列表)。 */
    lastSentAt: 0,
    lastErrorDetail: "",
    chatCommand: null as {
      sessionId: string;
      message: string;
      key: string;
    } | null,
  }),
  getters: {
    hasMessages: (state) => state.messages.length > 0,
  },
  actions: {
    initForSession(sessionId: string) {
      this.abortController?.abort();
      this.abortController = null;
      this.streamRequestId += 1;
      this.sending = false;
      this.messages = loadCachedMessages(sessionId);
      this.lastErrorDetail = "";
      this.chatCommand = null;
    },

    /** 从服务端加载某会话的完整历史(切换历史会话时调用)。 */
    async loadHistory(userId: string, sessionId: string) {
      try {
        const history = await api.fetchMessages(userId, sessionId);
        this.messages = history.map((m) => ({
          role: (m.role === "assistant" ? "assistant" : "user") as ChatMessage["role"],
          content: m.content,
          knowledgeUsed: m.metadata?.knowledge_used,
          sources: m.metadata?.sources,
        }));
        saveCachedMessages(sessionId, this.messages);
      } catch {
        // 加载失败时保留本地缓存,不阻塞用户
      }
    },

    clear() {
      this.messages = [];
    },

    persist(sessionId: string) {
      saveCachedMessages(sessionId, this.messages);
    },

    abort() {
      this.abortController?.abort();
      this.abortController = null;
    },

    async send(message: string) {
      const text = message.trim();
      if (!text || this.sending) return;
      const auth = useAuthStore();
      const isRetry =
        this.chatCommand?.sessionId === auth.sessionId
        && this.chatCommand.message === text;
      if (isRetry) {
        const assistant = this.messages[this.messages.length - 1];
        const user = this.messages[this.messages.length - 2];
        if (
          assistant?.role === "assistant"
          && user?.role === "user"
          && user.content === text
        ) {
          this.messages.splice(-2, 2);
        }
      } else {
        this.chatCommand = {
          sessionId: auth.sessionId,
          message: text,
          key: api.makeId("chat-turn"),
        };
      }

      this.messages.push({ role: "user", content: text });
      this.messages.push({ role: "assistant", content: "", pending: true });
      this.lastErrorDetail = "";
      this.sending = true;
      this.abortController = new AbortController();
      const requestId = ++this.streamRequestId;
      const requestSessionId = auth.sessionId;
      let streamedContent = "";
      let streamFrame = 0;

      const flushStream = () => {
        streamFrame = 0;
        if (this.streamRequestId !== requestId) return;
        const last = this.messages[this.messages.length - 1];
        if (last && last.role === "assistant") {
          last.content = streamedContent;
          last.pending = false;
        }
      };

      const queueStreamFlush = () => {
        if (!streamFrame) streamFrame = window.requestAnimationFrame(flushStream);
      };

      persist(this.messages, requestSessionId);

      try {
        const answer = await api.streamChat(
          {
            userId: auth.userId,
            sessionId: requestSessionId,
            message: text,
            idempotencyKey: this.chatCommand!.key,
          },
          (event) => {
            if (event.type === "token") {
              streamedContent += event.content || "";
              queueStreamFlush();
            } else if (event.type === "sources") {
              const last = this.messages[this.messages.length - 1];
              if (last?.role === "assistant") {
                last.knowledgeUsed = event.knowledge_used;
                last.sources = event.sources;
              }
            }
          },
          this.abortController.signal,
        );
        if (streamFrame) window.cancelAnimationFrame(streamFrame);
        streamedContent = answer;
        flushStream();
        const last = this.messages[this.messages.length - 1];
        if (this.streamRequestId === requestId && last?.role === "assistant") {
          this.chatCommand = null;
          last.pending = false;
          if (!answer) last.content = "Agent 没有返回文本内容。";
          api.trackEvent(
            auth.userId,
            "chat.answer_completed",
            {
              answer_length: answer.length,
              knowledge_used: Boolean(last.knowledgeUsed),
              source_count: last.sources?.length || 0,
            },
            requestSessionId,
          );
        }
      } catch (error) {
        if (streamFrame) window.cancelAnimationFrame(streamFrame);
        flushStream();
        const last = this.messages[this.messages.length - 1];
        const message = error instanceof Error ? error.message : "未知错误";
        if (this.streamRequestId !== requestId) {
          return;
        } else if ((error as Error).name === "AbortError") {
          // 用户主动中止:保留已生成内容,移除 pending
          if (last && last.role === "assistant") last.pending = false;
        } else if (last && last.role === "assistant") {
          last.pending = false;
          this.lastErrorDetail = message;
          last.content = "暂时无法生成回答。你可以重试，或稍后再试。";
        }
      } finally {
        if (streamFrame) window.cancelAnimationFrame(streamFrame);
        if (this.streamRequestId === requestId) {
          this.sending = false;
          this.abortController = null;
          this.lastSentAt = Date.now();
          persist(this.messages, requestSessionId);
        }
      }
    },
  },
});

function persist(messages: ChatMessage[], sessionId: string) {
  saveCachedMessages(sessionId, messages.slice(-50));
}
