<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useAuthStore } from "@/stores/auth";
import { useToastStore } from "@/stores/toast";
import { handleDialogKeydown } from "@/lib/focusTrap";
import { resetPassword } from "@/api/client";

const auth = useAuthStore();
const toast = useToastStore();

const mode = ref<"login" | "register" | "reset">("login");
const username = ref("");
const password = ref("");
const recoveryCode = ref("");
const replacementRecoveryCode = ref("");
const error = ref("");
const submitting = ref(false);
const showPassword = ref(false);
const usernameInput = ref<HTMLInputElement | null>(null);
const dialogRef = ref<HTMLElement | null>(null);

async function submit() {
  if (!username.value || !password.value) return;
  error.value = "";
  submitting.value = true;
  try {
    if (mode.value === "reset") {
      const result = await resetPassword(
        username.value,
        recoveryCode.value,
        password.value,
      );
      replacementRecoveryCode.value = result.recovery_code;
      toast.show("密码已重置，所有旧会话已退出", "success");
    } else if (mode.value === "login") {
      await auth.login(username.value, password.value);
    } else {
      await auth.register(username.value, password.value);
    }
    toast.show(`欢迎,${auth.username}`, "success");
  } catch (e) {
    error.value = e instanceof Error ? e.message : "认证失败";
  } finally {
    submitting.value = false;
  }
}

function toggleMode() {
  mode.value = mode.value === "login" ? "register" : "login";
  error.value = "";
}

function startReset() {
  mode.value = "reset";
  error.value = "";
  password.value = "";
}

function finishReset() {
  replacementRecoveryCode.value = "";
  recoveryCode.value = "";
  password.value = "";
  mode.value = "login";
}

onMounted(() => usernameInput.value?.focus());
</script>

<template>
  <Teleport to="body">
  <div class="auth-overlay" role="presentation">
    <section
      ref="dialogRef"
      class="auth-card"
      role="dialog"
      aria-modal="true"
      aria-labelledby="auth-title"
      @keydown="handleDialogKeydown($event, dialogRef)"
    >
      <div class="brand-mark" aria-hidden="true">IL</div>
      <span class="eyebrow">登录工作区</span>
      <h2 id="auth-title">
        {{
          mode === "login"
            ? "登录 Interview Lab"
            : mode === "register"
              ? "创建 Interview Lab 账号"
              : "使用恢复码重置密码"
        }}
      </h2>
      <p>登录后，会话、模拟面试、能力画像和学习计划会安全地保存在你的账号中。</p>
      <div v-if="replacementRecoveryCode" class="recovery-result">
        <p>密码已重置。请保存新的恢复码，旧恢复码已失效：</p>
        <code class="recovery-code">{{ replacementRecoveryCode }}</code>
        <button class="primary-action" type="button" @click="finishReset">
          已保存，返回登录
        </button>
      </div>
      <form v-else class="interview-form" @submit.prevent="submit">
        <label>
          用户名
          <input
            ref="usernameInput"
            v-model="username"
            minlength="3"
            maxlength="100"
            autocomplete="username"
            required
            :disabled="submitting"
          />
        </label>
        <label v-if="mode === 'reset'">
          恢复码
          <input
            v-model="recoveryCode"
            minlength="20"
            maxlength="40"
            autocomplete="off"
            required
            :disabled="submitting"
          />
        </label>
        <label class="password-field">
          密码
          <span>
            <input
              v-model="password"
              :type="showPassword ? 'text' : 'password'"
              minlength="10"
              maxlength="200"
              :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
              required
              :disabled="submitting"
            />
            <button
              type="button"
              :aria-label="showPassword ? '隐藏密码' : '显示密码'"
              @click="showPassword = !showPassword"
            >
              <i class="ph" :class="showPassword ? 'ph-eye-slash' : 'ph-eye'" aria-hidden="true"></i>
            </button>
          </span>
        </label>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <button class="primary-action" type="submit" :disabled="submitting">
          {{
            submitting
              ? "处理中…"
              : mode === "login"
                ? "登录"
                : mode === "register"
                  ? "创建账号"
                  : "重置密码"
          }}
        </button>
      </form>
      <button v-if="mode !== 'reset' && !replacementRecoveryCode" class="auth-switch" type="button" @click="toggleMode">
        {{ mode === "login" ? "没有账号？创建账号" : "已有账号？返回登录" }}
      </button>
      <button
        v-if="mode === 'login'"
        class="auth-switch"
        type="button"
        @click="startReset"
      >
        忘记密码？使用恢复码
      </button>
      <button
        v-else-if="mode === 'reset' && !replacementRecoveryCode"
        class="auth-switch"
        type="button"
        @click="finishReset"
      >
        返回登录
      </button>
    </section>
  </div>
  </Teleport>
</template>
