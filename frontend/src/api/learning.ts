import type { LearningTask } from "@/types";
import { apiFetch, expectOk } from "@/api/core";

export async function fetchLearningTasks(
  userId: string,
  status: string | null,
): Promise<LearningTask[]> {
  const statusQuery = status ? `&status=${encodeURIComponent(status)}` : "";
  const response = await apiFetch(
    `/api/learning-tasks?user_id=${encodeURIComponent(userId)}${statusQuery}`,
  );
  await expectOk(response);
  return response.json();
}

export async function generateLearningTasks(
  userId: string,
  topic: string | null,
): Promise<{ tasks: LearningTask[] }> {
  const response = await apiFetch("/api/learning-tasks/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, topic }),
  });
  await expectOk(response);
  return response.json();
}

export async function updateLearningTask(
  userId: string,
  taskId: string,
  changes: Partial<Pick<LearningTask, "status" | "due_at">>,
): Promise<LearningTask> {
  const response = await apiFetch(`/api/learning-tasks/${encodeURIComponent(taskId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, ...changes }),
  });
  await expectOk(response);
  return response.json();
}

export async function reviewLearningTask(userId: string, taskId: string): Promise<void> {
  const response = await apiFetch(
    `/api/learning-tasks/${encodeURIComponent(taskId)}/review`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId }),
    },
  );
  await expectOk(response);
}

export async function deleteLearningTask(userId: string, taskId: string): Promise<void> {
  const response = await apiFetch(
    `/api/learning-tasks/${encodeURIComponent(taskId)}?user_id=${encodeURIComponent(userId)}`,
    { method: "DELETE" },
  );
  await expectOk(response);
}
