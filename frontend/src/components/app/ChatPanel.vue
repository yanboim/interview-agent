<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { useChatStore } from "@/stores/chat";
import { useAuthStore } from "@/stores/auth";
import { useToastStore } from "@/stores/toast";
import MarkdownContent from "@/components/MarkdownContent.vue";

const chat = useChatStore();
const auth = useAuthStore();
const toast = useToastStore();

const input = ref("");
const textareaRef = ref<HTMLTextAreaElement | null>(null);
const showSuggestions = ref(true);
const followStream = ref(true);
let scrollFrame = 0;
let scrollContainer: HTMLElement | null = null;

const defaultPrompts = [
  {
    index: "01",
    title: "拆解 RAG 流程",
    desc: "检索、重排与生成",
    text: "请从高级工程师面试角度,解释 RAG 的完整工作流程",
  },
  {
    index: "02",
    title: "JVM 深度追问",
    desc: "G1、ZGC 与选型",
    text: "请比较 G1 和 ZGC,并说明生产环境如何选型",
  },
  {
    index: "03",
    title: "微服务治理",
    desc: "超时、重试与幂等",
    text: "微服务如何设计超时、重试、熔断和幂等,避免级联故障？",
  },
];
const prompts = computed(() => {
  const goal = auth.interviewGoal;
  if (!goal?.targetRole) return defaultPrompts;
  const focus = goal.focusAreas || goal.targetRole;
  return [
    {
      index: "01",
      title: `${goal.targetRole} 核心题`,
      desc: focus,
      text: `请按照${goal.experienceLevel}级${goal.targetRole}面试标准，围绕${focus}提出一个核心问题，并告诉我优秀回答应具备什么结构。`,
    },
    ...defaultPrompts.slice(1),
  ];
});

const showWelcome = computed(() => !chat.hasMessages);
// 有消息后仍可展开「建议追问」,持续引导(阶段 2 #11)
const showSuggestionsBar = computed(
  () => chat.hasMessages && showSuggestions.value && !chat.sending,
);

function autoResize() {
  const el = textareaRef.value;
  if (!el) return;
  el.style.height = "auto";
  el.style.height = `${Math.min(el.scrollHeight, 145)}px`;
}

function isNearBottom(threshold = 180) {
  const container = scrollContainer;
  if (container) {
    return container.scrollHeight - container.clientHeight - container.scrollTop < threshold;
  }
  return (
    document.documentElement.scrollHeight - window.innerHeight - window.scrollY <
    threshold
  );
}

function scrollToBottom() {
  nextTick(() => {
    if (scrollFrame) return;
    scrollFrame = window.requestAnimationFrame(() => {
      scrollFrame = 0;
      if (!followStream.value) return;
      const container = scrollContainer;
      if (container) {
        container.scrollTo({ top: container.scrollHeight, behavior: "auto" });
      } else {
        window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "auto" });
      }
    });
  });
}

const latestAssistantContent = computed(() => {
  const last = chat.messages[chat.messages.length - 1];
  return last?.role === "assistant" ? last.content : "";
});

watch(
  latestAssistantContent,
  () => {
    if (chat.sending && followStream.value) scrollToBottom();
  },
  { flush: "post" },
);

function updateFollowState() {
  if (chat.sending) followStream.value = isNearBottom(80);
}

onMounted(() => {
  scrollContainer = document.querySelector<HTMLElement>(".main");
  (scrollContainer || window).addEventListener("scroll", updateFollowState, { passive: true });
  const draft = sessionStorage.getItem("interview-lab-draft-prompt");
  if (draft) {
    input.value = draft;
    sessionStorage.removeItem("interview-lab-draft-prompt");
    nextTick(autoResize);
  }
});
onUnmounted(() => {
  (scrollContainer || window).removeEventListener("scroll", updateFollowState);
  scrollContainer = null;
  if (scrollFrame) window.cancelAnimationFrame(scrollFrame);
});

async function send(text: string) {
  followStream.value = isNearBottom();
  const request = chat.send(text);
  await nextTick();
  if (followStream.value) scrollToBottom();
  await request;
  if (followStream.value) scrollToBottom();
}

async function submit() {
  const text = input.value.trim();
  if (!text || chat.sending) return;
  input.value = "";
  await nextTick(autoResize);
  await send(text);
}

async function sendPrompt(text: string) {
  if (chat.sending) return;
  await send(text);
}

function stop() {
  chat.abort();
}

function onKeydown(event: KeyboardEvent) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    submit();
  }
}

function onCopy(event: Event) {
  const button = (event.target as HTMLElement).closest(".copy-code");
  if (!button) return;
  const code = button.closest(".code-block")?.querySelector("code")?.textContent || "";
  navigator.clipboard
    .writeText(code)
    .then(() => {
      button.textContent = "已复制";
      window.setTimeout(() => {
        button.textContent = "复制";
      }, 1400);
    })
    .catch(() => {
      button.textContent = "复制失败";
    });
}

async function copyMessage(content: string) {
  try {
    await navigator.clipboard.writeText(content);
    toast.show("回答已复制", "success", 1600);
  } catch {
    toast.show("复制失败，请手动选择文本", "error");
  }
}

function rateMessage(index: number, value: "up" | "down") {
  const message = chat.messages[index];
  if (!message) return;
  message.feedback = message.feedback === value ? undefined : value;
  chat.persist(auth.sessionId);
  toast.show(value === "up" ? "感谢反馈" : "已记录，我们会继续改进", "success", 1600);
}

async function retryLast() {
  if (chat.sending) return;
  let userIndex = -1;
  for (let index = chat.messages.length - 1; index >= 0; index -= 1) {
    if (chat.messages[index].role === "user") {
      userIndex = index;
      break;
    }
  }
  if (userIndex < 0) return;
  const text = chat.messages[userIndex].content;
  chat.messages.splice(userIndex);
  await send(text);
}
</script>

<template>
  <section
    class="conversation"
    :aria-busy="chat.sending"
    @click="onCopy"
  >
    <div v-if="showWelcome" class="welcome">
      <div class="eyebrow">你的私人面试教练</div>
      <h1>把知识，练成<br /><em>面试表达力。</em></h1>
      <p>基于你的私人知识库,拆解原理、组织答案,并继续追问。像真正的高级工程师面试一样思考。</p>

      <div class="prompt-grid">
        <button
          v-for="p in prompts"
          :key="p.index"
          class="prompt-card"
          type="button"
          :disabled="chat.sending"
          @click="sendPrompt(p.text)"
        >
          <span class="prompt-index">{{ p.index }}</span>
          <strong>{{ p.title }}</strong>
          <small>{{ p.desc }}</small>
          <i class="ph ph-arrow-right arrow" aria-hidden="true"></i>
        </button>
      </div>
    </div>

    <div v-else class="messages">
      <article
        v-for="(msg, i) in chat.messages"
        :key="i"
        class="message"
        :class="msg.role"
      >
        <span class="message-avatar">
          {{ msg.role === "assistant" ? "AI" : "ME" }}
        </span>
        <div class="bubble">
          <span
            v-if="msg.pending && !msg.content"
            class="typing"
            aria-label="Agent 正在思考"
          >
            <i></i><i></i><i></i>
          </span>
          <div
            v-else-if="msg.role === 'assistant'"
          >
            <MarkdownContent
              :content="msg.content"
              :streaming="chat.sending && i === chat.messages.length - 1"
            />
            <aside v-if="msg.knowledgeUsed || msg.sources?.length" class="answer-sources">
              <strong>
                <i class="ph ph-books" aria-hidden="true"></i>
                {{ msg.knowledgeUsed ? "已使用私人知识库" : "回答来源" }}
              </strong>
              <ul v-if="msg.sources?.length">
                <li
                  v-for="source in msg.sources"
                  :key="`${source.kind}:${source.label}:${source.url || ''}`"
                >
                  <a
                    v-if="source.url"
                    :href="source.url"
                    target="_blank"
                    rel="noopener noreferrer"
                  >{{ source.label }}</a>
                  <span v-else>{{ source.label }}</span>
                  <small v-if="source.fetched_at">抓取于 {{ source.fetched_at }}</small>
                </li>
              </ul>
              <span v-else>本次检索未返回可展示的来源文件。</span>
            </aside>
          </div>
          <template v-else>{{ msg.content }}</template>
          <div
            v-if="msg.role === 'assistant' && !msg.pending && msg.content"
            class="message-actions"
          >
            <button type="button" aria-label="复制回答" title="复制回答" @click="copyMessage(msg.content)">
              <i class="ph ph-copy" aria-hidden="true"></i>
            </button>
            <button
              type="button"
              aria-label="回答有帮助"
              title="回答有帮助"
              :class="{ active: msg.feedback === 'up' }"
              @click="rateMessage(i, 'up')"
            >
              <i class="ph ph-thumbs-up" aria-hidden="true"></i>
            </button>
            <button
              type="button"
              aria-label="回答需要改进"
              title="回答需要改进"
              :class="{ active: msg.feedback === 'down' }"
              @click="rateMessage(i, 'down')"
            >
              <i class="ph ph-thumbs-down" aria-hidden="true"></i>
            </button>
            <button
              v-if="i === chat.messages.length - 1"
              type="button"
              aria-label="重新生成"
              title="重新生成"
              @click="retryLast"
            >
              <i class="ph ph-arrow-clockwise" aria-hidden="true"></i>
            </button>
            <details v-if="chat.lastErrorDetail && i === chat.messages.length - 1" class="error-details">
              <summary>错误详情</summary>
              {{ chat.lastErrorDetail }}
            </details>
          </div>
        </div>
      </article>

      <!-- 建议追问条(阶段 2 #11):有消息后仍可一键继续 -->
      <div v-if="showSuggestionsBar" class="suggest-bar">
        <div class="suggest-header">
          <span class="nav-label-inline">建议追问</span>
          <button
            type="button"
            class="suggest-toggle"
            aria-label="收起建议"
            @click="showSuggestions = false"
          >
            收起
          </button>
        </div>
        <div class="suggest-chips">
          <button
            v-for="p in prompts"
            :key="p.index"
            type="button"
            class="suggest-chip"
            @click="sendPrompt(p.text)"
          >
            {{ p.title }}
          </button>
        </div>
      </div>
    </div>
  </section>

  <section class="composer-wrap">
    <form class="composer" @submit.prevent="submit">
      <textarea
        ref="textareaRef"
        v-model="input"
        rows="1"
        maxlength="10000"
        placeholder="输入一个面试问题,Shift + Enter 换行…"
        aria-label="输入面试问题"
        :disabled="chat.sending"
        @input="autoResize"
        @keydown="onKeydown"
      ></textarea>
      <div class="composer-footer">
        <div class="composer-hint">
          <span>Enter 发送 · Shift + Enter 换行</span>
        </div>
        <button
          v-if="chat.sending"
          class="send-button stop"
          type="button"
          aria-label="停止生成"
          @click="stop"
        >
          <i class="ph ph-stop" aria-hidden="true"></i>
          <span>停止</span>
        </button>
        <button
          v-else
          class="send-button"
          type="submit"
          aria-label="发送消息"
          :disabled="!input.trim()"
        >
          <span>发送</span>
          <i class="ph ph-paper-plane-tilt send-icon" aria-hidden="true"></i>
        </button>
      </div>
    </form>
    <p class="disclaimer">AI 可能会犯错,请结合实际项目经验判断 · Enter 发送</p>
  </section>
</template>
