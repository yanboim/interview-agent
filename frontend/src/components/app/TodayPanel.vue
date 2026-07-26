<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { fetchInterviews, fetchLearningTasks, fetchTodayPlan } from "@/api/client";
import type { TodayPlan } from "@/api/today";
import type { InterviewSummary, LearningTask } from "@/types";
import UiButton from "@/components/ui/UiButton.vue";
import UiState from "@/components/ui/UiState.vue";

const auth = useAuthStore();
const router = useRouter();
const interviews = ref<InterviewSummary[]>([]);
const tasks = ref<LearningTask[]>([]);
const loading = ref(true);
const plan = ref<TodayPlan | null>(null);

const activeInterview = computed(() =>
  interviews.value.find((item) => item.status === "active" && !item.archived_at),
);
const dueTasks = computed(() =>
  tasks.value.filter(
    (task) => task.status !== "completed" && new Date(task.due_at) <= new Date(),
  ),
);
const firstDueTask = computed(() => dueTasks.value[0] || tasks.value.find((task) => task.status !== "completed"));

onMounted(async () => {
  try {
    [interviews.value, tasks.value, plan.value] = await Promise.all([
      fetchInterviews(auth.userId, false),
      fetchLearningTasks(auth.userId, null),
      fetchTodayPlan(auth.userId),
    ]);
  } catch {
    // 首页摘要不可用时仍保留主要训练入口。
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <section class="today-panel">
    <div class="today-hero">
      <span class="eyebrow">今日训练</span>
      <h1>
        {{ auth.interviewGoal?.targetRole ? `向 ${auth.interviewGoal.targetRole} 再进一步` : "开始今天的面试训练" }}
      </h1>
      <p>
        每次只完成一个清晰动作：训练、复盘，再针对薄弱点复习。
      </p>
    </div>

    <UiState v-if="loading" kind="loading" title="正在准备今日训练…" />
    <div v-else class="today-grid">
      <article class="today-primary-card">
        <span class="today-card-kicker">今日优先行动</span>
        <h2>{{ plan?.recommendation.title || activeInterview?.topic || "开始一场针对性模拟面试" }}</h2>
        <p>{{ plan?.recommendation.reason || "根据你的目标岗位创建一场 15–30 分钟的结构化面试。" }}</p>
        <small v-if="plan?.has_job_description">推荐已结合目标 JD 与历史薄弱项</small>
        <UiButton
          @click="router.push(plan?.recommendation.href || (activeInterview ? `/interviews/${activeInterview.interview_id}` : '/interviews'))"
        >
          {{ plan?.recommendation.type === "review" ? "开始复习" : activeInterview ? "继续面试" : "创建模拟面试" }}
          <i class="ph ph-arrow-right" aria-hidden="true"></i>
        </UiButton>
      </article>

      <article class="today-card">
        <span class="today-card-kicker">待复习</span>
        <strong>{{ dueTasks.length }}</strong>
        <h3>{{ firstDueTask?.weakness || "暂无到期任务" }}</h3>
        <p>{{ firstDueTask?.action || "完成一次模拟面试后，系统会生成专项任务。" }}</p>
        <UiButton variant="text" @click="router.push('/learning')">
          查看学习计划
        </UiButton>
      </article>

      <article class="today-card">
        <span class="today-card-kicker">随时提问</span>
        <strong><i class="ph ph-chat-circle" aria-hidden="true"></i></strong>
        <h3>完善一个技术表达</h3>
        <p>结合私人知识库拆解原理、组织答案并继续追问。</p>
        <UiButton variant="text" @click="router.push('/chat')">
          进入知识问答
        </UiButton>
      </article>
    </div>
  </section>
</template>
