<script setup lang="ts">
// 通用分页组件：根据总数与页码计算可点击页码列表。
import { computed } from "vue";

const props = defineProps<{
  page: number;
  totalPages: number;
}>();

const emit = defineEmits<{
  (e: "update:page", page: number): void;
}>();

/** 简单分页:显示首、尾、当前及相邻页,其余用省略号。 */
const pages = computed<(number | string)[]>(() => {
  const total = props.totalPages;
  const current = props.page;
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  const result: (number | string)[] = [1];
  const start = Math.max(2, current - 1);
  const end = Math.min(total - 1, current + 1);
  if (start > 2) result.push("…");
  for (let i = start; i <= end; i++) result.push(i);
  if (end < total - 1) result.push("…");
  result.push(total);
  return result;
});

function go(target: number | string) {
  if (typeof target !== "number") return;
  if (target < 1 || target > props.totalPages || target === props.page) return;
  emit("update:page", target);
}
</script>

<template>
  <nav class="pagination" aria-label="分页">
    <button
      type="button"
      class="page-btn"
      :disabled="page <= 1"
      aria-label="上一页"
      @click="go(page - 1)"
    >
      <i class="ph ph-caret-left" aria-hidden="true"></i>
    </button>
    <button
      v-for="(p, i) in pages"
      :key="i"
      type="button"
      class="page-btn"
      :class="{ active: p === page, ellipsis: typeof p !== 'number' }"
      :disabled="typeof p !== 'number'"
      :aria-current="p === page ? 'page' : undefined"
      @click="go(p)"
    >
      {{ p }}
    </button>
    <button
      type="button"
      class="page-btn"
      :disabled="page >= totalPages"
      aria-label="下一页"
      @click="go(page + 1)"
    >
      <i class="ph ph-caret-right" aria-hidden="true"></i>
    </button>
  </nav>
</template>
