<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useInterviewsStore } from "@/stores/interviews";
import { useResumesStore } from "@/stores/resumes";
import { useToastStore } from "@/stores/toast";
import { confirm } from "@/composables/confirm";
import { formatProfileDate } from "@/lib/format";
import { normalizeLooseMarkdown, renderInlineMarkdown } from "@/lib/markdown";
import MarkdownContent from "@/components/MarkdownContent.vue";
import type { InterviewSummary } from "@/types";

const props = defineProps<{
  mode: "interview" | "report";
}>();

const emit = defineEmits<{
  (e: "go-report"): void;
  (e: "go-learning"): void;
}>();

const store = useInterviewsStore();
const resumes = useResumesStore();
const toast = useToastStore();
const auth = useAuthStore();
const route = useRoute();
const router = useRouter();

const topic = ref(auth.interviewGoal?.focusAreas || auth.interviewGoal?.targetRole || "Java、Spring 与微服务");
const level = ref(auth.interviewGoal?.experienceLevel || "高级");
const count = ref(5);
const answer = ref("");
const retryAnswer = ref("");
const showRetryForm = ref(false);
const view = ref<"setup" | "session">("setup");
const interviewSource = ref<"general" | "resume">("general");
const resumeAnalysisId = ref("");
const readyResumeOptions = computed(() =>
  resumes.items
    .filter((item) => item.latest_analysis?.status === "ready")
    .map((item) => ({
      resumeId: item.resume_id,
      analysisId: item.latest_analysis!.analysis_id,
      label: `${item.original_filename} · ${item.latest_analysis!.target_role || "未指定岗位"}`,
    })),
);

const showHistoryDetail = ref(false);
const renderedQuestion = computed(() =>
  renderInlineMarkdown(store.active?.question || ""),
);
const renderedReferenceAnswer = computed(() =>
  normalizeLooseMarkdown(store.lastAnswer?.reference_answer || ""),
);
const dimensionLabels: Record<string, string> = {
  accuracy: "技术准确性",
  depth: "原理深度",
  communication: "表达结构",
  practicality: "工程实践",
};

async function start() {
  try {
    await store.start(
      topic.value,
      level.value,
      count.value,
      interviewSource.value === "resume" ? resumeAnalysisId.value : undefined,
    );
    view.value = "session";
    await router.replace(`/interviews/${store.active?.interview_id}`);
    answer.value = "";
    store.lastAnswer = null;
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "启动失败", "error");
  }
}

async function submitAnswer() {
  const text = answer.value.trim();
  if (!text || store.answering) return;
  try {
    await store.answer(text);
    answer.value = "";
    // 阶段 2:移除硬编码 setTimeout,数据就绪即推进;用户主动点「下一题」
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "评分失败", "error");
  }
}

async function submitRetry() {
  const text = retryAnswer.value.trim();
  if (!text || store.answering) return;
  try {
    await store.retryAnswer(text);
    retryAnswer.value = "";
    showRetryForm.value = false;
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "重新评分失败", "error");
  }
}

function nextQuestion() {
  if (!store.active) return;
  store.lastAnswer = null;
}

async function backToHistory() {
  view.value = "setup";
  store.lastAnswer = null;
  showHistoryDetail.value = false;
  await store.loadHistory();
  await router.push("/interviews");
}

async function resume(interviewId: string) {
  try {
    await store.resume(interviewId);
    view.value = "session";
    await router.push(`/interviews/${interviewId}`);
    answer.value = "";
    store.lastAnswer = null;
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "恢复失败", "error");
  }
}

async function viewItem(interviewId: string) {
  try {
    await store.viewDetail(interviewId);
    showHistoryDetail.value = true;
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "详情加载失败", "error");
  }
}

async function toggleArchive(item: InterviewSummary) {
  try {
    await store.archive(item.interview_id, !item.archived_at);
    toast.show(item.archived_at ? "已恢复" : "已归档", "success");
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "归档失败", "error");
  }
}

async function removeItem(item: InterviewSummary) {
  const confirmed = await confirm({
    title: "永久删除这场面试？",
    message: "将删除这场面试及其全部问答记录,无法恢复。",
    detail: item.topic,
    confirmText: "删除",
    danger: true,
  });
  if (!confirmed) return;
  try {
    await store.remove(item.interview_id);
    toast.show("面试已删除", "success");
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "删除失败", "error");
  }
}

function statusLabel(item: InterviewSummary) {
  if (item.archived_at) return "已归档";
  if (item.status === "completed") return "已完成";
  return "进行中";
}

// 当切到面试/画像模式时,若有进行中的面试直接进入会话视图,否则进入设置/历史
watch(
  () => props.mode,
  (mode) => {
    if (mode === "interview") {
      if (store.active?.status === "active") {
        view.value = "session";
      } else {
        view.value = "setup";
      }
      store.loadHistory();
      store.lastAnswer = null;
    }
  },
  { immediate: true },
);

onMounted(async () => {
  if (props.mode !== "interview") return;
  if (auth.resumeFeatureEnabled) {
    await resumes.load();
    if (readyResumeOptions.value.length) {
      resumeAnalysisId.value = readyResumeOptions.value[0].analysisId;
    }
  }
  await store.initForUser();
  const interviewId = route.params.interviewId;
  if (
    typeof interviewId === "string"
    && interviewId
    && store.active?.interview_id !== interviewId
  ) {
    await resume(interviewId);
  } else if (store.active?.status === "active") {
    view.value = "session";
  }
});
</script>

<template>
  <section v-show="props.mode === 'interview'" class="interview-panel">
    <!-- 创建面试 -->
    <div v-if="view === 'setup'" class="interview-card">
      <span class="eyebrow">模拟面试</span>
      <h2>创建一场模拟面试</h2>
      <p>系统将逐题追问，并从准确性、深度、表达和工程实践四个维度评分。</p>
      <form class="interview-form" @submit.prevent="start">
        <fieldset v-if="auth.resumeFeatureEnabled" class="interview-source-fieldset">
          <legend>面试依据</legend>
          <label>
            <input v-model="interviewSource" type="radio" value="general" />
            通用模拟面试
          </label>
          <label>
            <input
              v-model="interviewSource"
              type="radio"
              value="resume"
              :disabled="!readyResumeOptions.length"
            />
            基于简历追问
          </label>
          <select
            v-if="interviewSource === 'resume'"
            v-model="resumeAnalysisId"
            required
            aria-label="选择简历评估版本"
          >
            <option
              v-for="option in readyResumeOptions"
              :key="option.analysisId"
              :value="option.analysisId"
            >
              {{ option.label }}
            </option>
          </select>
          <small v-if="!readyResumeOptions.length">
            完成一份简历评估后即可开启定向面试。
          </small>
        </fieldset>
        <label>
          面试主题
          <input v-model="topic" maxlength="200" required :disabled="store.starting" />
        </label>
        <label>
          难度
          <select v-model="level" :disabled="store.starting">
            <option>中级</option>
            <option>高级</option>
            <option>专家</option>
          </select>
        </label>
        <label>
          题目数量
          <input
            v-model.number="count"
            type="number"
            min="1"
            max="20"
            required
            :disabled="store.starting"
          />
        </label>
        <p class="interview-duration">
          预计用时 {{ count <= 3 ? "10–15" : count <= 5 ? "20–30" : "35–60" }} 分钟
        </p>
        <button class="primary-action" type="submit" :disabled="store.starting">
          {{ store.starting ? "正在出题…" : "开始面试" }}
        </button>
      </form>

      <!-- 历史面试 -->
      <section class="interview-history-section">
        <div class="history-heading">
          <div>
            <h3>历史面试</h3>
            <span>恢复未完成训练,或查看每轮评分</span>
          </div>
          <label>
            <input v-model="store.includeArchived" type="checkbox" @change="store.loadHistory()" />
            显示已归档
          </label>
        </div>

        <!-- 列表状态(不再清空区域) -->
        <div v-if="store.historyError" class="list-state error">
          {{ store.historyError }}
          <button class="retry-link" @click="store.loadHistory()">重试</button>
        </div>
        <div v-else-if="store.historyLoading" class="list-state">正在加载历史面试…</div>
        <div v-else-if="!store.history.length" class="list-state">暂无历史面试</div>
        <div v-else class="interview-history-list">
          <article
            v-for="item in store.history"
            :key="item.interview_id"
            class="history-item"
            :class="{ archived: item.archived_at }"
          >
            <div class="history-score">
              <strong>{{ item.average_score ?? "—" }}</strong>
              <small>平均分</small>
            </div>
            <div class="history-meta">
              <strong>{{ item.topic }}</strong>
              <em v-if="item.source_type === 'resume'">
                基于简历 ·
                {{ item.source_resume?.available ? item.source_resume.display_name : "来源简历已删除" }}
              </em>
              <span>
                {{ item.level }} · {{ item.answered_questions }}/{{ item.total_questions }} 题 ·
                {{ formatProfileDate(item.updated_at) }}
              </span>
              <b>{{ statusLabel(item) }}</b>
            </div>
            <div class="history-actions">
              <button
                v-if="item.status === 'active' && !item.archived_at"
                type="button"
                @click="resume(item.interview_id)"
              >
                继续
              </button>
              <button type="button" @click="viewItem(item.interview_id)">查看</button>
              <button type="button" @click="toggleArchive(item)">
                {{ item.archived_at ? "恢复归档" : "归档" }}
              </button>
              <button class="danger-action" type="button" @click="removeItem(item)">删除</button>
            </div>
          </article>
        </div>

        <!-- 详情面板 -->
        <div v-if="showHistoryDetail" class="interview-history-detail">
          <div v-if="store.detailLoading" class="list-state">正在加载面试详情…</div>
          <template v-else-if="store.detail">
            <div class="history-detail-heading">
              <div>
                <strong>{{ store.detail.interview.topic }}</strong>
                <span>{{ store.detail.interview.level }}</span>
                <span v-if="store.detail.interview.source_type === 'resume'">
                  基于简历 ·
                  {{
                    store.detail.interview.source_resume?.available
                      ? store.detail.interview.source_resume.display_name
                      : "来源简历已删除"
                  }}
                </span>
              </div>
              <button class="text-action" type="button" @click="showHistoryDetail = false">
                关闭
              </button>
            </div>
            <article
              v-for="turn in store.detail.turns"
              :key="turn.turn_index"
              class="history-turn"
            >
              <div>
                <span>第 {{ turn.turn_index }} 题</span>
                <strong>{{ turn.score ?? "未评分" }}</strong>
              </div>
              <h4>{{ turn.question }}</h4>
              <p><b>回答：</b>{{ turn.answer || "尚未回答" }}</p>
              <p v-if="turn.feedback"><b>反馈：</b>{{ turn.feedback }}</p>
            </article>
          </template>
        </div>
      </section>
    </div>

    <!-- 进行中面试 -->
    <div v-else-if="view === 'session' && store.active" class="interview-card">
      <div class="interview-session-heading">
        <div class="interview-progress">
          第 {{ store.active.turn_index }} / {{ store.active.question_count }} 题
          <span v-if="store.active.source_type === 'resume'">
            · 基于简历
          </span>
        </div>
        <button class="text-action" type="button" @click="backToHistory">返回历史</button>
      </div>
      <h2 class="interview-question" v-html="renderedQuestion"></h2>

      <!-- 评分中骨架(阶段 2 #7):替代旧的硬编码 setTimeout,提供明确进度反馈 -->
      <div v-if="store.answering" class="scoring-pending" aria-live="polite">
        <span class="typing"><i></i><i></i><i></i></span>
        <span>正在对回答进行四维评分…</span>
      </div>

      <!-- 评分反馈(数据就绪即显示,不再硬延时) -->
      <div v-if="store.lastAnswer" class="interview-feedback">
        <div class="feedback-score-heading">
          <span>本题评分</span>
          <strong>{{ store.lastAnswer.score }}<small>/ 10</small></strong>
        </div>
        <div class="feedback-dimensions">
          <div v-for="(score, name) in store.lastAnswer.dimensions" :key="name">
            <span>{{ dimensionLabels[String(name)] || name }}</span>
            <strong>{{ score }}</strong>
          </div>
        </div>
        <p>{{ store.lastAnswer.feedback }}</p>
        <div class="feedback-columns">
          <section>
            <h3>做得好的地方</h3>
            <ul>
              <li v-for="item in store.lastAnswer.strengths" :key="item">{{ item }}</li>
              <li v-if="!store.lastAnswer.strengths.length">当前回答有可继续展开的基础。</li>
            </ul>
          </section>
          <section>
            <h3>下一步改进</h3>
            <ul>
              <li v-for="item in store.lastAnswer.weaknesses" :key="item">{{ item }}</li>
              <li v-if="!store.lastAnswer.weaknesses.length">保持当前结构，并补充项目证据。</li>
            </ul>
          </section>
        </div>
        <details v-if="store.lastAnswer.reference_answer" class="reference-answer">
          <summary>查看参考回答</summary>
          <MarkdownContent :content="renderedReferenceAnswer" />
        </details>
        <div v-if="store.lastAnswer.comparison" class="answer-comparison" aria-live="polite">
          <strong>
            第 {{ store.lastAnswer.comparison.attempt_index }} 次回答：
            {{ store.lastAnswer.comparison.score_delta >= 0 ? "+" : "" }}{{
              store.lastAnswer.comparison.score_delta
            }} 分
          </strong>
          <span>上次 {{ store.lastAnswer.comparison.previous_score }} 分</span>
        </div>
        <button
          v-if="!showRetryForm"
          class="text-action"
          type="button"
          @click="showRetryForm = true"
        >
          针对同一题重新回答
        </button>
        <form
          v-else
          class="interview-form retry-answer-form"
          @submit.prevent="submitRetry"
        >
          <label>
            改进后的回答
            <textarea
              v-model="retryAnswer"
              rows="6"
              maxlength="20000"
              required
              :disabled="store.answering"
            ></textarea>
          </label>
          <div class="settings-actions">
            <button class="text-action" type="button" @click="showRetryForm = false">
              取消
            </button>
            <button class="primary-action" type="submit" :disabled="store.answering">
              {{ store.answering ? "正在重新评分…" : "重新评分并对比" }}
            </button>
          </div>
        </form>
      </div>

      <!-- 有下一题:展示「下一题」按钮 -->
      <button
        v-if="store.lastAnswer?.next_question"
        class="primary-action"
        type="button"
        @click="nextQuestion"
      >
        下一题
        <i class="ph ph-arrow-right" aria-hidden="true"></i>
      </button>

      <!-- 最后一题已完成:不强制跳报告(阶段 2 #9),提供入口让用户自选 -->
      <div
        v-else-if="store.lastAnswer && store.active.status === 'completed'"
        class="interview-complete-actions"
      >
        <p class="interview-complete-tip">本场面试已完成,可查看跨场次能力画像。</p>
        <div class="interview-complete-buttons">
          <button class="text-action" type="button" @click="backToHistory">查看历史</button>
          <button class="primary-action" type="button" @click="emit('go-report')">
            查看能力画像
            <i class="ph ph-arrow-right" aria-hidden="true"></i>
          </button>
          <button class="text-action" type="button" @click="emit('go-learning')">
            生成专项计划
          </button>
        </div>
      </div>

      <!-- 未在评分、未完成:展示答题表单 -->
      <form
        v-else-if="!store.answering"
        class="interview-form"
        @submit.prevent="submitAnswer"
      >
        <label>
          你的回答
          <textarea
            v-model="answer"
            rows="8"
            maxlength="20000"
            required
            :disabled="store.answering"
          ></textarea>
        </label>
        <button class="primary-action" type="submit" :disabled="store.answering">
          {{ store.answering ? "正在评分…" : "提交并评分" }}
        </button>
      </form>
    </div>
  </section>
</template>
