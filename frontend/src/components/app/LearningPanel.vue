<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import { useAuthStore } from "@/stores/auth";
import { useLearningStore } from "@/stores/learning";
import { useToastStore } from "@/stores/toast";
import { confirm } from "@/composables/confirm";
import { dateInputValue, formatProfileDate } from "@/lib/format";
import type { LearningStatus, LearningTask } from "@/types";

const store = useLearningStore();
const toast = useToastStore();
const auth = useAuthStore();
const router = useRouter();
const generationTopic = ref(auth.interviewGoal?.focusAreas || "");

const statusLabel: Record<LearningStatus, string> = {
  todo: "待开始",
  in_progress: "进行中",
  completed: "已完成",
};

const summary = computed(() => `${store.totalCount} 项任务 · ${store.dueCount} 项已到期`);

async function generate() {
  try {
    await store.generate(generationTopic.value.trim() || null);
    toast.show(`已生成 ${store.tasks.length} 项学习任务`, "success");
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "任务生成失败", "error");
  }
}

async function startPractice(task: LearningTask) {
  sessionStorage.setItem(
    "interview-lab-draft-prompt",
    `请围绕“${task.weakness}”带我完成一次专项复习。先用简洁结构讲清核心知识，再给我一道面试题并根据回答继续追问。重点行动：${task.action}`,
  );
  await router.push("/chat");
}

async function changeStatus(task: LearningTask, event: Event) {
  const status = (event.target as HTMLSelectElement).value as LearningStatus;
  try {
    await store.update(task.task_id, { status });
    toast.show("任务状态已更新", "success", 2000);
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "更新失败", "error");
    await store.load();
  }
}

async function changeDue(task: LearningTask, event: Event) {
  const value = (event.target as HTMLInputElement).value;
  if (!value) return;
  const due_at = new Date(`${value}T23:59:59`).toISOString();
  try {
    await store.update(task.task_id, { due_at });
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "更新失败", "error");
  }
}

async function review(task: LearningTask) {
  try {
    await store.review(task.task_id);
    toast.show("已记录一次复习", "success", 2000);
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "复习记录失败", "error");
  }
}

async function remove(task: LearningTask) {
  const confirmed = await confirm({
    title: "删除这项学习任务？",
    detail: task.weakness,
    confirmText: "删除",
    danger: true,
  });
  if (!confirmed) return;
  try {
    await store.remove(task.task_id);
    toast.show("任务已删除", "success");
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "删除失败", "error");
  }
}

onMounted(() => store.load());
</script>

<template>
  <section class="learning-panel">
    <div class="interview-card learning-card">
      <div class="learning-heading">
        <div>
          <span class="eyebrow">学习与复习</span>
          <h2>学习与复习计划</h2>
          <p>把能力画像中的薄弱点变成任务,并按间隔复习持续巩固。</p>
        </div>
        <button
          class="primary-action"
          type="button"
          :disabled="store.generating"
          @click="generate"
        >
          {{ store.generating ? "生成中…" : "从画像生成任务" }}
        </button>
      </div>

      <div class="learning-toolbar">
        <label>
          任务状态
          <select
            :value="store.statusFilter"
            @change="
              store.setStatusFilter(($event.target as HTMLSelectElement).value as LearningStatus | '');
              store.load();
            "
          >
            <option value="">全部</option>
            <option value="todo">待开始</option>
            <option value="in_progress">进行中</option>
            <option value="completed">已完成</option>
          </select>
        </label>
        <label>
          生成主题
          <input v-model="generationTopic" maxlength="200" placeholder="全部薄弱点" />
        </label>
        <span>{{ store.loading ? "正在加载…" : summary }}</span>
      </div>

      <div v-if="store.error" class="list-state error">
        {{ store.error }}
        <button class="retry-link" @click="store.load()">重试</button>
      </div>
      <div v-else-if="store.loading" class="list-state">正在加载学习任务…</div>
      <div v-else-if="!store.tasks.length" class="profile-empty profile-empty-large">
        <strong>当前没有学习任务</strong>
        <span>先完成模拟面试,再从能力画像生成专项计划。</span>
      </div>
      <div v-else class="learning-task-list">
        <article
          v-for="task in store.tasks"
          :key="task.task_id"
          class="learning-task"
          :class="`status-${task.status}`"
        >
          <div class="task-status-mark"></div>
          <div class="task-content">
            <div class="task-heading">
              <span>{{ task.dimension }}</span>
              <b>{{ statusLabel[task.status] }}</b>
            </div>
            <h3>{{ task.weakness }}</h3>
            <p>{{ task.action }}</p>
            <div class="task-schedule">
              <label>
                截止日期
                <input
                  type="date"
                  :value="dateInputValue(task.due_at)"
                  @change="changeDue(task, $event)"
                />
              </label>
              <span>已复习 {{ task.review_count }} 次</span>
              <span>下次复习：{{ task.next_review_at ? formatProfileDate(task.next_review_at) : "待安排" }}</span>
            </div>
          </div>
          <div class="task-actions">
            <select
              :value="task.status"
              aria-label="修改任务状态"
              @change="changeStatus(task, $event)"
            >
              <option value="todo">待开始</option>
              <option value="in_progress">进行中</option>
              <option value="completed">已完成</option>
            </select>
            <button type="button" @click="review(task)">完成复习</button>
            <button type="button" @click="startPractice(task)">开始专项练习</button>
            <button class="danger-action" type="button" @click="remove(task)">删除</button>
          </div>
        </article>
      </div>
    </div>
  </section>
</template>
