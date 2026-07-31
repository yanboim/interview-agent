import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  confirmReview,
  createAudioReview,
  updateReviewTranscript,
} from "@/api/reviews";

describe("review API contract", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() =>
        Promise.resolve(
          new Response(JSON.stringify({ review_id: "review-1" }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        ),
      ),
    );
  });

  it("sends explicit audio consent and idempotency", async () => {
    await createAudioReview(
      new File(["RIFF....WAVE"], "synthetic.wav", { type: "audio/wav" }),
      true,
    );
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect((init?.headers as Record<string, string>)["Idempotency-Key"]).toBeTruthy();
    expect((init?.body as FormData).get("external_processing_consent")).toBe("true");
  });

  it("sends optimistic transcript revision and confirmation revision", async () => {
    const segments = [
      { segment_id: "s1", speaker: "interviewer" as const, text: "问题" },
      { segment_id: "s2", speaker: "candidate" as const, text: "回答" },
    ];
    await updateReviewTranscript("review-1", 3, segments);
    let body = JSON.parse(String(vi.mocked(fetch).mock.calls[0][1]?.body));
    expect(body.expected_revision).toBe(3);
    expect(body.segments).toEqual(segments);

    await confirmReview("review-1", 4);
    body = JSON.parse(String(vi.mocked(fetch).mock.calls[1][1]?.body));
    expect(body.expected_revision).toBe(4);
    expect(
      (vi.mocked(fetch).mock.calls[1][1]?.headers as Record<string, string>)[
        "Idempotency-Key"
      ],
    ).toBeTruthy();
  });
});
