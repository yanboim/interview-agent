<script setup lang="ts">
withDefaults(
  defineProps<{
    variant?: "primary" | "text" | "danger";
    type?: "button" | "submit";
    loading?: boolean;
    disabled?: boolean;
  }>(),
  {
    variant: "primary",
    type: "button",
    loading: false,
    disabled: false,
  },
);
</script>

<template>
  <button
    :class="variant === 'primary' ? 'primary-action' : variant === 'danger' ? 'danger-action' : 'text-action'"
    :type="type"
    :disabled="disabled || loading"
    :aria-busy="loading || undefined"
  >
    <span v-if="loading" class="typing compact" aria-hidden="true"><i></i><i></i><i></i></span>
    <slot />
  </button>
</template>
