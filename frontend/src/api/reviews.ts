// 真实面试复盘 API：文本/音频创建、逐字稿编辑、确认分析与重试。
import { apiFetch, expectOk } from "@/api/core";
import type { InterviewReview, TranscriptSegment } from "@/types";

export async function createTextReview(transcript: string): Promise<InterviewReview> {
  const response = await apiFetch("/api/interview-reviews/text", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify({ transcript }),
  });
  await expectOk(response);
  return response.json();
}

export async function createAudioReview(
  file: File,
  consent: boolean,
): Promise<InterviewReview> {
  const form = new FormData();
  form.append("file", file);
  form.append("external_processing_consent", String(consent));
  const response = await apiFetch("/api/interview-reviews/audio", {
    method: "POST",
    headers: { "Idempotency-Key": crypto.randomUUID() },
    body: form,
  });
  await expectOk(response);
  return response.json();
}

export async function listReviews(): Promise<InterviewReview[]> {
  const response = await apiFetch("/api/interview-reviews");
  await expectOk(response);
  return response.json();
}

export async function getReview(reviewId: string): Promise<InterviewReview> {
  const response = await apiFetch(
    `/api/interview-reviews/${encodeURIComponent(reviewId)}`,
  );
  await expectOk(response);
  return response.json();
}

export async function updateReviewTranscript(
  reviewId: string,
  expectedRevision: number,
  segments: TranscriptSegment[],
): Promise<InterviewReview> {
  const response = await apiFetch(
    `/api/interview-reviews/${encodeURIComponent(reviewId)}/transcript`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        expected_revision: expectedRevision,
        segments,
      }),
    },
  );
  await expectOk(response);
  return response.json();
}

export async function confirmReview(
  reviewId: string,
  expectedRevision: number,
): Promise<InterviewReview> {
  const response = await apiFetch(
    `/api/interview-reviews/${encodeURIComponent(reviewId)}/confirm-and-analyze`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Idempotency-Key": crypto.randomUUID(),
      },
      body: JSON.stringify({ expected_revision: expectedRevision }),
    },
  );
  await expectOk(response);
  return response.json();
}

export async function retryReview(reviewId: string): Promise<InterviewReview> {
  const response = await apiFetch(
    `/api/interview-reviews/${encodeURIComponent(reviewId)}/retry`,
    { method: "POST" },
  );
  await expectOk(response);
  return response.json();
}

export async function deleteReview(reviewId: string): Promise<void> {
  const response = await apiFetch(
    `/api/interview-reviews/${encodeURIComponent(reviewId)}`,
    { method: "DELETE" },
  );
  await expectOk(response);
}
