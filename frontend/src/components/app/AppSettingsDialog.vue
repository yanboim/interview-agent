<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { useAuthStore } from "@/stores/auth";
import { useToastStore } from "@/stores/toast";
import type { CoachingMemory, InterviewGoal } from "@/types";
import { handleDialogKeydown } from "@/lib/focusTrap";
import {
  changePassword,
  fetchReminderPreferences,
  regenerateRecoveryCode,
  saveReminderPreferences,
  updateProfileAvatar,
  deleteCoachingMemory,
  fetchCoachingMemories,
  proposeCoachingMemory,
  updateCoachingMemory,
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
const avatarInput = ref<HTMLInputElement | null>(null);
const avatarPreview = ref(auth.avatarDataUrl);
const avatarDirty = ref(false);
const memories = ref<CoachingMemory[]>([]);
const memoryKind = ref<CoachingMemory["kind"]>("preference");
const memoryContent = ref("");
const memoryLoading = ref(false);
const editingMemoryId = ref("");
const editingMemoryContent = ref("");
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
    if (avatarDirty.value) {
      const savedAvatar = await updateProfileAvatar(
        auth.userId,
        avatarPreview.value || null,
      );
      auth.setAvatar(savedAvatar);
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

function loadAvatarImage(source: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("无法读取头像图片"));
    image.src = source;
  });
}

function readAvatarFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") resolve(reader.result);
      else reject(new Error("无法读取头像图片"));
    };
    reader.onerror = () => reject(new Error("无法读取头像图片"));
    reader.readAsDataURL(file);
  });
}

async function chooseAvatar(event: Event) {
  const input = event.currentTarget as HTMLInputElement;
  const file = input.files?.[0];
  if (!file) return;
  if (!["image/jpeg", "image/png", "image/webp"].includes(file.type)) {
    toast.show("头像仅支持 JPEG、PNG 或 WebP 图片", "error");
    input.value = "";
    return;
  }
  if (file.size > 5 * 1024 * 1024) {
    toast.show("原始头像图片不能超过 5 MB", "error");
    input.value = "";
    return;
  }
  try {
    const image = await loadAvatarImage(await readAvatarFile(file));
    const size = Math.min(image.naturalWidth, image.naturalHeight);
    if (!size) throw new Error("头像图片尺寸无效");
    const canvas = document.createElement("canvas");
    canvas.width = 256;
    canvas.height = 256;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("当前浏览器无法处理头像图片");
    context.drawImage(
      image,
      (image.naturalWidth - size) / 2,
      (image.naturalHeight - size) / 2,
      size,
      size,
      0,
      0,
      256,
      256,
    );
    avatarPreview.value = canvas.toDataURL("image/webp", 0.84);
    avatarDirty.value = true;
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "头像处理失败", "error");
  } finally {
    input.value = "";
  }
}

function removeAvatar() {
  avatarPreview.value = "";
  avatarDirty.value = true;
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

async function reloadMemories() {
  if (!auth.isAuthenticated) return;
  memories.value = await fetchCoachingMemories(auth.userId);
}

async function addMemory() {
  if (!memoryContent.value.trim()) return;
  memoryLoading.value = true;
  try {
    await proposeCoachingMemory(
      auth.userId,
      memoryKind.value,
      memoryContent.value.trim(),
    );
    memoryContent.value = "";
    await reloadMemories();
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "记忆保存失败", "error");
  } finally {
    memoryLoading.value = false;
  }
}

async function actOnMemory(
  memory: CoachingMemory,
  action: "confirm" | "reject" | "correct" | "delete",
) {
  memoryLoading.value = true;
  try {
    if (action === "delete") {
      await deleteCoachingMemory(auth.userId, memory.memory_id);
    } else {
      await updateCoachingMemory(
        auth.userId,
        memory.memory_id,
        action,
        action === "correct" ? editingMemoryContent.value.trim() : undefined,
      );
    }
    editingMemoryId.value = "";
    await reloadMemories();
  } catch (error) {
    toast.show(error instanceof Error ? error.message : "记忆更新失败", "error");
  } finally {
    memoryLoading.value = false;
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
  void reloadMemories().catch(() => {
    // 记忆区域保持为空，不阻塞其他设置。
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
        <section class="avatar-settings" aria-labelledby="avatar-settings-title">
          <div class="avatar-preview" aria-hidden="true">
            <img v-if="avatarPreview" :src="avatarPreview" alt="" />
            <span v-else>
              {{ auth.username ? Array.from(auth.username).slice(0, 2).join("").toUpperCase() : "ME" }}
            </span>
          </div>
          <div class="avatar-settings-copy">
            <strong id="avatar-settings-title">个人头像</strong>
            <small>上传后会自动裁成方形，并在账号设备间同步。</small>
            <div class="avatar-settings-actions">
              <button class="text-action" type="button" @click="avatarInput?.click()">
                {{ avatarPreview ? "更换头像" : "上传头像" }}
              </button>
              <button
                v-if="avatarPreview"
                class="text-action avatar-remove"
                type="button"
                @click="removeAvatar"
              >
                移除
              </button>
            </div>
            <input
              ref="avatarInput"
              class="visually-hidden"
              type="file"
              accept="image/jpeg,image/png,image/webp"
              aria-label="选择头像图片"
              @change="chooseAvatar"
            />
          </div>
        </section>
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
          <label class="reminder-switch">
            <input v-model="reminderEnabled" type="checkbox" />
            <span class="reminder-switch-track" aria-hidden="true">
              <span></span>
            </span>
            <span>开启每日到期复习提醒</span>
          </label>
          <label v-if="reminderEnabled">
            提醒时间
            <input v-model="reminderTime" type="time" />
          </label>
          <small>按 {{ reminderTimezone }} 时区计算；提醒数据会跟随账号同步。</small>
        </fieldset>
        <fieldset v-if="auth.isAuthenticated" class="settings-section">
          <legend>教练记忆</legend>
          <small>只有你明确确认的内容会进入后续 Agent 上下文；可随时纠正、拒绝或删除。</small>
          <label>
            记忆类型
            <select v-model="memoryKind">
              <option value="fact">个人事实</option>
              <option value="preference">回答偏好</option>
              <option value="goal">长期目标</option>
              <option value="observation">训练观察</option>
            </select>
          </label>
          <label>
            新记忆
            <textarea v-model="memoryContent" maxlength="2000" rows="2"></textarea>
          </label>
          <button
            class="text-action"
            type="button"
            :disabled="memoryLoading || !memoryContent.trim()"
            @click="addMemory"
          >添加待确认记忆</button>
          <ul v-if="memories.length" class="memory-settings-list">
            <li v-for="memory in memories" :key="memory.memory_id">
              <template v-if="editingMemoryId === memory.memory_id">
                <textarea v-model="editingMemoryContent" maxlength="2000" rows="2"></textarea>
                <button class="text-action" type="button" @click="actOnMemory(memory, 'correct')">保存纠正</button>
              </template>
              <template v-else>
                <span>{{ memory.content }}</span>
                <small>{{ memory.status === "confirmed" ? "已确认" : memory.status === "rejected" ? "已拒绝" : "待确认" }}</small>
                <div class="avatar-settings-actions">
                  <button v-if="memory.status === 'proposed'" class="text-action" type="button" @click="actOnMemory(memory, 'confirm')">确认</button>
                  <button v-if="memory.status === 'proposed'" class="text-action" type="button" @click="actOnMemory(memory, 'reject')">拒绝</button>
                  <button class="text-action" type="button" @click="editingMemoryId = memory.memory_id; editingMemoryContent = memory.content">纠正</button>
                  <button class="text-action avatar-remove" type="button" @click="actOnMemory(memory, 'delete')">删除</button>
                </div>
              </template>
            </li>
          </ul>
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
