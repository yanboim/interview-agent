import type {
  ActiveInterview,
  AnswerResult,
  CapabilityProfile,
  InterviewDetail,
  InterviewSummary,
} from "@/types";
import { apiFetch, expectOk } from "@/api/core";

export async function startInterview(body: {
  userId: string;
  topic: string;
  level: string;
  questionCount: number;
}): Promise<ActiveInterview> {
  const response = await apiFetch("/api/interviews/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: body.userId,
      topic: body.topic,
      level: body.level,
      question_count: body.questionCount,
    }),
  });
  await expectOk(response);
  return response.json();
}

export async function fetchInterviews(
  userId: string,
  includeArchived: boolean,
): Promise<InterviewSummary[]> {
  const response = await apiFetch(
    `/api/interviews?user_id=${encodeURIComponent(userId)}&include_archived=${includeArchived ? "true" : "false"}`,
  );
  await expectOk(response);
  return response.json();
}

export async function fetchInterviewDetail(
  userId: string,
  interviewId: string,
): Promise<InterviewDetail> {
  const response = await apiFetch(
    `/api/interviews/${encodeURIComponent(interviewId)}?user_id=${encodeURIComponent(userId)}`,
  );
  await expectOk(response);
  return response.json();
}

export async function resumeInterview(userId: string, interviewId: string) {
  const response = await apiFetch(
    `/api/interviews/${encodeURIComponent(interviewId)}/resume`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId }),
    },
  );
  await expectOk(response);
  return response.json();
}

export async function archiveInterview(
  userId: string,
  interviewId: string,
  archived: boolean,
) {
  const response = await apiFetch(
    `/api/interviews/${encodeURIComponent(interviewId)}/archive`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, archived }),
    },
  );
  await expectOk(response);
  return response.json();
}

export async function deleteInterview(userId: string, interviewId: string): Promise<void> {
  const response = await apiFetch(
    `/api/interviews/${encodeURIComponent(interviewId)}?user_id=${encodeURIComponent(userId)}`,
    { method: "DELETE" },
  );
  await expectOk(response);
}

export async function answerInterview(
  userId: string,
  interviewId: string,
  answer: string,
): Promise<AnswerResult> {
  const response = await apiFetch(
    `/api/interviews/${encodeURIComponent(interviewId)}/answer`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, answer }),
    },
  );
  await expectOk(response);
  return response.json();
}

export async function retryInterviewAnswer(
  userId: string,
  interviewId: string,
  turnIndex: number,
  answer: string,
): Promise<AnswerResult> {
  const response = await apiFetch(
    `/api/interviews/${encodeURIComponent(interviewId)}/turns/${turnIndex}/retry`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, answer }),
    },
  );
  await expectOk(response);
  return response.json();
}

export async function fetchCapabilityProfile(
  userId: string,
  topic: string | null,
): Promise<CapabilityProfile> {
  const topicQuery = topic ? `&topic=${encodeURIComponent(topic)}` : "";
  const response = await apiFetch(
    `/api/capability-profile?user_id=${encodeURIComponent(userId)}${topicQuery}`,
  );
  await expectOk(response);
  return response.json();
}
