<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { useAuthStore } from "@/stores/auth";
import { useToastStore } from "@/stores/toast";
import type { InterviewGoal } from "@/types";
import { handleDialogKeydown } from "@/lib/focusTrap";
import {
  changePassword,
  fetchReminderPreferences,
  regenerateRecoveryCode,
  saveReminderPreferences,
} from "@/api/client";

const emit = defineEmits<{ (e: "close"): void }>();
const auth = useAuthStore();
const toast = useToastStore();
const firstInput = ref<HTMLInputElement | null>(null);
const dialogRef = ref<HTMLElement | null>(null);
const reminderEnabled = ref(false);
const reminderTime = ref("09:00");
const reminderTimezone = ref(
  Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
);
const currentPassword = ref("");
const newPassword = ref("");
const passwordChanging = ref(false);
const recoveryCode = ref("");
const recoveryCodeLoading = ref(false);
const goal = ref<InterviewGoal>({
  targetRole: auth.interviewGoal?.targetRole || "",
  experienceLevel: auth.interviewGoal?.experienceLevel || "高级",
  focusAreas: auth.interviewGoal?.focusAreas || "",
  interviewDate: auth.interviewGoal?.interviewDate || "",
  jobDescription: auth.interviewGoal?.jobDescription || "",
});

async function save() {
  try {
    if (goal.value.targetRole.trim()) {
      await auth.saveInterviewGoal({
        ...goal.value,
        targetRole: goal.value.targetRole.trim(),
        focusAreas: goal.value.focusAreas.trim(),
        jobDescription: goal.value.jobDescription.trim(),
      });
    }
    await saveReminderPreferences(auth.userId, {
      enabled: reminderEnabled.value,
      reminder_time: reminderTime.value,
      timezone: reminderTimezone.value,
    });
    if (
      reminderEnabled.value
      && "Notification" in window
      && Notification.permission === "default"
    ) {
      await Notification.requestPermission();
    }
    toast.show("设置已保存", "success", 2000);
    emit("close");
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "设置保存失败", "error");
  }
}

async function submitPasswordChange() {
  if (!currentPassword.value || !newPassword.value) return;
  passwordChanging.value = true;
  try {
    await changePassword(currentPassword.value, newPassword.value);
    toast.show("密码已更新，请重新登录", "success", 2500);
    await auth.logout();
    emit("close");
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "密码更新失败", "error");
  } finally {
    passwordChanging.value = false;
  }
}

async function createRecoveryCode() {
  recoveryCodeLoading.value = true;
  try {
    recoveryCode.value = await regenerateRecoveryCode();
    toast.show("新的恢复码已生成，旧恢复码已失效", "success");
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "恢复码生成失败", "error");
  } finally {
    recoveryCodeLoading.value = false;
  }
}

function onKeydown(event: KeyboardEvent) {
  handleDialogKeydown(event, dialogRef.value, () => emit("close"));
}

onMounted(() => {
  firstInput.value?.focus();
  window.addEventListener("keydown", onKeydown);
  void fetchReminderPreferences(auth.userId)
    .then((preferences) => {
      reminderEnabled.value = preferences.enabled;
      reminderTime.value = preferences.reminder_time;
      reminderTimezone.value = preferences.timezone;
    })
    .catch(() => {
      // 使用浏览器时区默认值。
    });
});
onUnmounted(() => window.removeEventListener("keydown", onKeydown));
</script>

<template>
  <Teleport to="body">
  <div class="confirm-overlay" role="presentation" @mousedown.self="emit('close')">
    <section
      ref="dialogRef"
      class="settings-card"
      role="dialog"
      aria-modal="true"
      aria-labelledby="settings-title"
    >
      <div class="settings-heading">
        <div>
          <span class="eyebrow">偏好设置</span>
          <h2 id="settings-title">训练目标与高级设置</h2>
        </div>
        <button class="icon-button" type="button" aria-label="关闭设置" @click="emit('close')">
          <i class="ph ph-x" aria-hidden="true"></i>
        </button>
      </div>
      <form class="interview-form" @submit.prevent="save">
        <label>
          目标岗位
          <input ref="firstInput" v-model="goal.targetRole" maxlength="100" />
        </label>
        <label>
          当前级别
          <select v-model="goal.experienceLevel">
            <option>中级</option>
            <option>高级</option>
            <option>专家</option>
          </select>
        </label>
        <label>
          重点方向
          <input v-model="goal.focusAreas" maxlength="200" />
        </label>
        <label>
          预计面试日期
          <input v-model="goal.interviewDate" type="date" />
        </label>
        <label>
          职位描述
          <textarea
            v-model="goal.jobDescription"
            rows="4"
            maxlength="10000"
            placeholder="粘贴目标职位 JD，用于定制题目与训练建议"
          ></textarea>
        </label>
        <fieldset class="settings-section">
          <legend>训练提醒</legend>
          <label class="inline-check">
            <input v-model="reminderEnabled" type="checkbox" />
            开启每日到期复习提醒
          </label>
          <label v-if="reminderEnabled">
            提醒时间
            <input v-model="reminderTime" type="time" />
          </label>
          <small>按 {{ reminderTimezone }} 时区计算；提醒数据会跟随账号同步。</small>
        </fieldset>
        <details v-if="auth.isAuthenticated" class="advanced-settings">
          <summary>账号安全</summary>
          <div class="interview-form">
            <label>
              当前密码
              <input v-model="currentPassword" type="password" autocomplete="current-password" />
            </label>
            <label>
              新密码
              <input
                v-model="newPassword"
                type="password"
                minlength="12"
                autocomplete="new-password"
              />
            </label>
            <small>至少 12 位，并包含大小写字母、数字中的至少两类。修改后会退出所有设备。</small>
            <button
              class="text-action"
              type="button"
              :disabled="passwordChanging || !currentPassword || !newPassword"
              @click="submitPasswordChange"
            >
              {{ passwordChanging ? "正在更新…" : "更新密码" }}
            </button>
            <div class="recovery-settings">
              <p>恢复码可在忘记密码时恢复账号。生成新码会立即废止旧码。</p>
              <code v-if="recoveryCode" class="recovery-code">{{ recoveryCode }}</code>
              <button
                class="text-action"
                type="button"
                :disabled="recoveryCodeLoading"
                @click="createRecoveryCode"
              >
                {{ recoveryCodeLoading ? "正在生成…" : "生成新的恢复码" }}
              </button>
            </div>
          </div>
        </details>
        <div class="settings-actions">
          <button class="text-action" type="button" @click="emit('close')">取消</button>
          <button class="primary-action" type="submit" :disabled="auth.goalLoading">
            {{ auth.goalLoading ? "正在保存…" : "保存设置" }}
          </button>
        </div>
      </form>
    </section>
  </div>
  </Teleport>
</template>
