<script setup lang="ts">
// 目标设置对话框：引导新用户填写目标岗位、方向、经验与面试日期。
import { onMounted, ref } from "vue";
import { useAuthStore } from "@/stores/auth";
import { useToastStore } from "@/stores/toast";
import type { InterviewGoal } from "@/types";
import { handleDialogKeydown } from "@/lib/focusTrap";

const emit = defineEmits<{ (e: "complete"): void }>();
const auth = useAuthStore();
const toast = useToastStore();
const firstInput = ref<HTMLInputElement | null>(null);
const dialogRef = ref<HTMLElement | null>(null);
const form = ref<InterviewGoal>({
  targetRole: "",
  experienceLevel: "高级",
  focusAreas: "",
  interviewDate: "",
  jobDescription: "",
});

async function submit() {
  if (!form.value.targetRole.trim()) return;
  try {
    await auth.saveInterviewGoal({
      ...form.value,
      targetRole: form.value.targetRole.trim(),
      focusAreas: form.value.focusAreas.trim(),
      jobDescription: form.value.jobDescription.trim(),
    });
    emit("complete");
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "目标保存失败", "error");
  }
}

onMounted(() => firstInput.value?.focus());
</script>

<template>
  <Teleport to="body">
  <div class="auth-overlay" role="presentation">
    <section
      ref="dialogRef"
      class="auth-card goal-card"
      role="dialog"
      aria-modal="true"
      aria-labelledby="goal-title"
      @keydown="handleDialogKeydown($event, dialogRef)"
    >
      <span class="eyebrow">只需一分钟</span>
      <h2 id="goal-title">先确定你的面试目标</h2>
      <p>我们会据此推荐问题、设置面试难度，并安排后续复习。</p>
      <form class="interview-form" @submit.prevent="submit">
        <label>
          目标岗位
          <input ref="firstInput" v-model="form.targetRole" required maxlength="100" placeholder="例如：高级 Java 工程师" />
        </label>
        <label>
          当前级别
          <select v-model="form.experienceLevel">
            <option>中级</option>
            <option>高级</option>
            <option>专家</option>
          </select>
        </label>
        <label>
          重点方向
          <input v-model="form.focusAreas" maxlength="200" placeholder="例如：JVM、微服务、系统设计" />
        </label>
        <details class="goal-optional">
          <summary>
            <span>完善面试信息</span>
            <small>日期、JD（可选）</small>
          </summary>
          <div class="goal-optional-fields">
            <label>
              预计面试日期
              <input v-model="form.interviewDate" type="date" />
            </label>
            <label>
              职位描述
              <textarea v-model="form.jobDescription" rows="3" maxlength="3000" placeholder="粘贴 JD，后续训练会更贴近目标岗位"></textarea>
            </label>
          </div>
        </details>
        <button class="primary-action" type="submit" :disabled="auth.goalLoading">
          {{ auth.goalLoading ? "正在保存…" : "保存并开始训练" }}
        </button>
      </form>
    </section>
  </div>
  </Teleport>
</template>
