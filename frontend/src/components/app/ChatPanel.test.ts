// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";
import { beforeEach, describe, expect, it } from "vitest";

import ChatPanel from "@/components/app/ChatPanel.vue";
import { useChatStore } from "@/stores/chat";

describe("ChatPanel claim citations", () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it("renders citation Markdown safely while keeping evidence status visible", () => {
    const pinia = createPinia();
    setActivePinia(pinia);
    const chat = useChatStore();
    chat.messages = [
      {
        role: "assistant",
        content: "正文",
        citations: [
          {
            claim: "> ⚠️ **公开资料**：使用 `JDK 21`。 ``",
            evidence_ids: [],
            support: "unsupported",
          },
          {
            claim: "- 使用 **SATB (Snapshot-At-The-Beginning) ** 算法。",
            evidence_ids: ["chunk-1"],
            support: "supported",
          },
          {
            claim: '<img src="x" onerror="alert(1)">安全内容',
            evidence_ids: [],
            support: "conflicting",
          },
        ],
      },
    ];

    const wrapper = mount(ChatPanel, { global: { plugins: [pinia] } });
    const citations = wrapper.get('[aria-label="逐条引用与证据状态"]');

    expect(citations.find("blockquote").exists()).toBe(true);
    expect(citations.find(".citation-claim strong").text()).toContain("公开资料");
    expect(citations.find("code").text()).toBe("JDK 21");
    expect(citations.find(".citation-claim ul").exists()).toBe(true);
    expect(citations.text()).not.toContain("**");
    expect(citations.text()).not.toContain("``");
    expect(citations.text()).toContain("暂无证据支持");
    expect(citations.text()).toContain("证据 chunk-1");
    expect(citations.text()).toContain("证据冲突");
    expect(citations.html()).not.toContain("onerror");
  });
});
