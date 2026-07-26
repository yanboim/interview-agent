<script setup lang="ts">
import { computed } from "vue";
import { renderMarkdown } from "@/lib/markdown";

const props = defineProps<{
  content: string;
  streaming?: boolean;
}>();

// 将 Markdown 解析隔离在消息子组件内。父级流式更新时，内容未变化的历史
// 消息不会重复执行 marked、highlight.js 和 DOMPurify。
const html = computed(() => renderMarkdown(props.content, props.streaming));
</script>

<template>
  <div
    class="markdown-content"
    :aria-busy="streaming ? 'true' : undefined"
    aria-live="polite"
    v-html="html"
  ></div>
</template>
