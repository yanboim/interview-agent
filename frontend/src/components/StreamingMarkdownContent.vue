<script setup lang="ts">
import MarkdownRender from "markstream-vue";
import "markstream-vue/index.css";

defineProps<{
  content: string;
}>();
</script>

<template>
  <MarkdownRender
    mode="chat"
    :content="content"
    :final="false"
    html-policy="safe"
    smooth-streaming="auto"
    :parse-coalesce-ms="80"
    :fade="false"
    :defer-nodes-until-visible="true"
    :viewport-priority="true"
    :max-live-nodes="220"
    :live-node-buffer="40"
  />
</template>
