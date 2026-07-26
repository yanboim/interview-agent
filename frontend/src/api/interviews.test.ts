import { beforeEach, describe, expect, it, vi } from "vitest";
import { answerInterview } from "@/api/interviews";


beforeEach(() => {
  vi.restoreAllMocks();
  vi.stubGlobal("localStorage", {
    getItem: () => null,
    setItem: () => undefined,
  });
});


describe("answerInterview", () => {
  it("forwards the durable idempotency key", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          interview_id: "interview-1",
          turn_index: 1,
          score: 8,
          dimensions: {},
          strengths: [],
          weaknesses: [],
          feedback: "ok",
          reference_answer: "reference",
          next_question: null,
          status: "completed",
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    await answerInterview(
      "user-1",
      "interview-1",
      "我的回答",
      "answer-command-1",
    );

    expect(fetchMock).toHaveBeenCalledOnce();
    const [, options] = fetchMock.mock.calls[0];
    expect(options.headers["Idempotency-Key"]).toBe("answer-command-1");
  });
});
