<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { confirm } from "@/composables/confirm";
import { useAuthStore } from "@/stores/auth";
import { useReviewsStore } from "@/stores/reviews";
import { useToastStore } from "@/stores/toast";
import type { TranscriptSegment } from "@/types";
import UiButton from "@/components/ui/UiButton.vue";
import UiState from "@/components/ui/UiState.vue";

const auth = useAuthStore();
const store = useReviewsStore();
const toast = useToastStore();
const route = useRoute();
const router = useRouter();
const transcript = ref("");
const audio = ref<File | null>(null);
const consent = ref(false);
const segments = ref<TranscriptSegment[]>([]);
const saving = ref(false);
let pollTimer: number | undefined;

const processing = computed(() =>
  ["transcribing", "analyzing"].includes(store.active?.status || ""),
);
const hasUnknown = computed(() =>
  segments.value.some((segment) => segment.speaker === "unknown"),
);
const statusLabels: Record<string, string> = {
  transcribing: "转写中",
  awaiting_confirmation: "待确认",
  analyzing: "分析中",
  ready: "已完成",
  failed: "处理失败",
};
const dimensionLabels: Record<string, string> = {
  accuracy: "准确性",
  depth: "专业深度",
  communication: "表达沟通",
  practicality: "实战能力",
};

function statusLabel(status: string) {
  return statusLabels[status] || status;
}

function dimensionLabel(name: string) {
  return dimensionLabels[name] || name;
}

function scoreWidth(score: number) {
  return `${Math.max(0, Math.min(100, score * 10))}%`;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

async function chooseTranscriptFile(event: Event) {
  const selected = (event.target as HTMLInputElement).files?.[0];
  if (!selected) return;
  transcript.value = await selected.text();
}

watch(
  () => `${store.active?.review_id || ""}:${store.active?.transcript_revision || 0}`,
  () => {
    segments.value = structuredClone(store.active?.segments || []);
  },
  { immediate: true },
);

watch(
  processing,
  (active) => {
    window.clearInterval(pollTimer);
    if (active && store.active) {
      pollTimer = window.setInterval(
        () => store.open(store.active!.review_id),
        3000,
      );
    }
  },
  { immediate: true },
);

async function createText() {
  try {
    const created = await store.createText(transcript.value);
    transcript.value = "";
    await router.push(`/reviews/${created.review_id}`);
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "创建失败", "error");
  }
}

async function createAudio() {
  if (!audio.value) return;
  try {
    const created = await store.createAudio(audio.value, consent.value);
    await router.push(`/reviews/${created.review_id}`);
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "上传失败", "error");
  }
}

async function openReview(reviewId: string) {
  await router.push(`/reviews/${reviewId}`);
  await store.open(reviewId);
}

function splitSegment(index: number) {
  const current = segments.value[index];
  const point = Math.floor(current.text.length / 2);
  if (point < 1) return;
  segments.value.splice(
    index,
    1,
    { ...current, text: current.text.slice(0, point).trim() },
    {
      ...current,
      segment_id: crypto.randomUUID(),
      text: current.text.slice(point).trim(),
    },
  );
}

function mergePrevious(index: number) {
  if (index < 1) return;
  segments.value[index - 1].text += `\n${segments.value[index].text}`;
  segments.value.splice(index, 1);
}

async function save() {
  saving.value = true;
  try {
    await store.save(segments.value);
    toast.show("逐字稿已保存，旧确认已失效", "success");
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "保存失败", "error");
    if (store.active) await store.open(store.active.review_id);
  } finally {
    saving.value = false;
  }
}

async function confirmAndAnalyze() {
  try {
    await store.confirm();
    toast.show("逐字稿已确认，正在生成复盘", "success");
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "确认失败", "error");
  }
}

async function remove() {
  if (!store.active) return;
  const approved = await confirm({
    title: "删除面试复盘？",
    message: "逐字稿、报告、问答回合和残留音频都会删除。",
    confirmText: "删除",
    danger: true,
  });
  if (!approved) return;
  await store.remove(store.active.review_id);
  await router.push("/reviews");
}

onMounted(async () => {
  await store.load();
  const reviewId = route.params.reviewId;
  if (typeof reviewId === "string" && reviewId) await store.open(reviewId);
});

onUnmounted(() => window.clearInterval(pollTimer));
</script>

<template>
  <section class="review-panel">
    <aside class="review-sidebar">
      <header class="review-sidebar-intro">
        <p class="eyebrow">INTERVIEW REVIEW</p>
        <h1>面试复盘</h1>
        <p>导入真实面试记录，获得逐题反馈和下一步训练建议。</p>
      </header>

      <form class="review-create-card" @submit.prevent="createText">
        <div class="review-card-heading">
          <div>
            <h2>新建复盘</h2>
            <p>支持 TXT、Markdown 或直接粘贴内容</p>
          </div>
          <span aria-hidden="true">01</span>
        </div>
        <label class="review-field">
          <span>上传逐字稿</span>
          <input
            type="file"
            accept=".txt,.md,text/plain,text/markdown"
            @change="chooseTranscriptFile"
          />
        </label>
        <div class="review-or"><span>或</span></div>
        <label class="review-field">
          <span>粘贴逐字稿</span>
          <textarea
            v-model="transcript"
            rows="7"
            required
            placeholder="面试官：请介绍项目&#10;&#10;候选人：我负责……"
          />
        </label>
        <UiButton type="submit" :disabled="!transcript.trim()">创建文本复盘</UiButton>
      </form>
      <form v-if="auth.transcriptionEnabled" class="review-audio-card" @submit.prevent="createAudio">
        <label class="review-field">
          <span>上传音频</span>
          <input
            type="file"
            accept=".mp3,.m4a,.wav,.webm,audio/*"
            required
            @change="audio = ($event.target as HTMLInputElement).files?.[0] || null"
          />
        </label>
        <label class="review-consent">
          <input v-model="consent" type="checkbox" required />
          我同意音频发送给 {{ auth.transcriptionProviderName || "已配置转写服务" }}；
          转写入库后原音频会删除。
        </label>
        <UiButton type="submit" :disabled="!audio || !consent">上传并转写</UiButton>
      </form>
      <p v-else class="review-note">
        <span aria-hidden="true"></span>
        音频转写暂未开放，文本复盘可正常使用
      </p>

      <section class="review-history">
        <div class="review-history-heading">
          <h2>最近记录</h2>
          <span>{{ store.items.length }}</span>
        </div>
        <div v-if="store.items.length" class="review-list">
        <button
          v-for="item in store.items"
          :key="item.review_id"
          type="button"
          :class="{ active: item.review_id === store.active?.review_id }"
          @click="openReview(item.review_id)"
        >
          <span class="review-list-main">
            <strong>{{ item.original_filename || "文本逐字稿" }}</strong>
            <small>{{ formatDate(item.updated_at) }}</small>
          </span>
          <span class="review-status" :class="`status-${item.status}`">
            {{ statusLabel(item.status) }}
          </span>
        </button>
        </div>
        <p v-else class="review-history-empty">还没有复盘记录</p>
      </section>
    </aside>

    <main class="review-detail">
      <UiState
        v-if="!store.active"
        title="选择或创建一场面试复盘"
        detail="自动结果仅用于训练辅助，不代表招聘结论。"
      />
      <template v-else>
        <header class="review-heading">
          <div>
            <p class="eyebrow">面试复盘 · 训练辅助</p>
            <h1>{{ store.active.original_filename || "文本逐字稿" }}</h1>
            <div class="review-meta">
              <span class="review-status" :class="`status-${store.active.status}`">
                {{ statusLabel(store.active.status) }}
              </span>
              <span>{{ store.active.input_type === "audio" ? "音频记录" : "文本记录" }}</span>
              <span>更新于 {{ formatDate(store.active.updated_at) }}</span>
            </div>
          </div>
          <UiButton variant="danger" @click="remove">删除</UiButton>
        </header>

        <UiState
          v-if="processing"
          kind="loading"
          :title="store.active.status === 'transcribing' ? '正在转写音频' : '正在生成复盘'"
          detail="可以离开页面，稍后返回会恢复最新状态。"
        />
        <UiState
          v-else-if="store.active.status === 'failed'"
          kind="error"
          title="处理失败"
          :detail="store.active.error || '请检查内容后重试'"
        >
          <UiButton v-if="store.active.input_type === 'audio'" @click="store.retry()">重试转写</UiButton>
        </UiState>

        <section
          v-if="store.active.status === 'awaiting_confirmation'"
          class="transcript-editor"
        >
          <div class="review-section-heading">
            <div>
              <h3>确认逐字稿与说话人</h3>
              <p>只有最新保存版本可进入复盘；未知说话人会阻止分析。</p>
            </div>
            <span>版本 {{ store.active.transcript_revision }}</span>
          </div>
          <article v-for="(segment, index) in segments" :key="segment.segment_id">
            <select v-model="segment.speaker" :aria-label="`片段${index + 1}说话人`">
              <option value="unknown">待确认</option>
              <option value="interviewer">面试官</option>
              <option value="candidate">候选人</option>
            </select>
            <textarea v-model="segment.text" rows="4" :aria-label="`片段${index + 1}内容`" />
            <div>
              <button type="button" @click="splitSegment(index)">拆分</button>
              <button v-if="index" type="button" @click="mergePrevious(index)">与上一段合并</button>
            </div>
          </article>
          <p v-if="hasUnknown" class="review-warning" role="alert">
            仍有待确认的说话人。
          </p>
          <div class="review-actions">
            <UiButton :loading="saving" @click="save">保存逐字稿</UiButton>
            <UiButton :disabled="hasUnknown || saving" @click="confirmAndAnalyze">
              确认并生成复盘
            </UiButton>
          </div>
        </section>

        <template v-if="store.active.status === 'ready' && store.active.report">
          <section class="review-report">
            <div class="review-section-title">
              <div>
                <p class="eyebrow">OVERVIEW</p>
                <h2>整体复盘</h2>
              </div>
              <span>{{ store.active.turns?.length || 0 }} 道题</span>
            </div>
            <p class="review-summary">{{ store.active.report.overall_summary }}</p>

            <div class="review-dimensions" aria-label="能力评分">
              <article
                v-for="(score, name) in store.active.report.dimension_scores"
                :key="name"
                class="review-score-card"
              >
                <header>
                  <span>{{ dimensionLabel(String(name)) }}</span>
                  <strong>{{ Number(score).toFixed(1) }}</strong>
                </header>
                <div class="review-score-track" aria-hidden="true">
                  <i :style="{ width: scoreWidth(Number(score)) }"></i>
                </div>
              </article>
            </div>

            <div
              v-if="store.active.report.strengths.length || store.active.report.weaknesses.length"
              class="review-insights"
            >
              <section>
                <h3><span class="insight-mark strength" aria-hidden="true"></span>表现亮点</h3>
                <ul>
                  <li v-for="item in store.active.report.strengths" :key="item">{{ item }}</li>
                </ul>
              </section>
              <section>
                <h3><span class="insight-mark weakness" aria-hidden="true"></span>重点提升</h3>
                <ul>
                  <li v-for="item in store.active.report.weaknesses" :key="item">{{ item }}</li>
                </ul>
              </section>
            </div>

            <div class="review-action-plan">
              <h3>行动计划</h3>
              <ol>
                <li v-for="item in store.active.report.action_plan" :key="item">
                  <span>{{ item }}</span>
                </li>
              </ol>
            </div>
          </section>
          <section class="review-turns">
            <div class="review-section-title">
              <div>
                <p class="eyebrow">QUESTION BY QUESTION</p>
                <h2>逐题复盘</h2>
              </div>
              <p>点击题目展开详情</p>
            </div>
            <div class="review-turn-list">
              <details
                v-for="turn in store.active.turns"
                :key="turn.turn_index"
                class="review-turn-card"
                :open="turn.turn_index === 1"
              >
                <summary>
                  <span class="review-turn-index">{{ String(turn.turn_index).padStart(2, "0") }}</span>
                  <strong>{{ turn.question }}</strong>
                  <span class="review-turn-score">{{ turn.score?.toFixed(1) || "—" }}</span>
                  <span class="review-turn-chevron" aria-hidden="true"></span>
                </summary>
                <div class="review-turn-body">
                  <section>
                    <h3>候选人回答</h3>
                    <p>{{ turn.answer }}</p>
                  </section>
                  <section class="review-feedback">
                    <h3>教练反馈</h3>
                    <p>{{ turn.feedback }}</p>
                  </section>
                  <section class="review-improved-answer">
                    <h3>参考改进回答</h3>
                    <p>{{ turn.improved_answer }}</p>
                  </section>
                </div>
              </details>
            </div>
          </section>
        </template>
      </template>
    </main>
  </section>
</template>

<style src="@/styles/review.css"></style>
