import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";

import * as api from "@/api/chat";
import { useChatStore } from "@/stores/chat";


describe("chat citation history", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.restoreAllMocks();
    vi.stubGlobal("localStorage", {
      getItem: () => null,
      setItem: () => undefined,
    });
  });

  it("restores claim citations and unsupported state from stored metadata", async () => {
    vi.spyOn(api, "fetchMessages").mockResolvedValue([
      {
        role: "assistant",
        content: "JDK 21 是 LTS。",
        created_at: "2026-07-31T00:00:00Z",
        metadata: {
          turn_id: "turn-1",
          knowledge_used: true,
          schema_version: 1,
          sources: [
            { evidence_id: "chunk-1", label: "jvm.md", kind: "private" },
          ],
          citations: [
            {
              claim: "JDK 21 是 LTS。",
              evidence_ids: ["chunk-1"],
              support: "supported",
            },
          ],
          unsupported_claims: ["未来版本尚未确认。"],
        },
      },
    ]);
    const store = useChatStore();

    await store.loadHistory("user-a", "session-a");

    expect(store.messages[0].citations?.[0].evidence_ids).toEqual(["chunk-1"]);
    expect(store.messages[0].turnId).toBe("turn-1");
    expect(store.messages[0].unsupportedClaims).toEqual(["未来版本尚未确认。"]);
  });
});
