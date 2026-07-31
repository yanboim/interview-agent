import type { CoachingMemory, InterviewGoal } from "@/types";
import { apiFetch, expectOk } from "@/api/core";

interface ProfileResponse {
  target_role: string;
  experience_level: InterviewGoal["experienceLevel"];
  focus_areas: string;
  interview_date: string | null;
  job_description: string;
  avatar_data_url: string | null;
}

function fromResponse(profile: ProfileResponse): InterviewGoal | null {
  if (!profile.target_role) return null;
  return {
    targetRole: profile.target_role,
    experienceLevel: profile.experience_level,
    focusAreas: profile.focus_areas,
    interviewDate: profile.interview_date || "",
    jobDescription: profile.job_description,
  };
}

export async function fetchInterviewGoal(userId: string): Promise<InterviewGoal | null> {
  const response = await apiFetch(`/api/profile?user_id=${encodeURIComponent(userId)}`);
  await expectOk(response);
  return fromResponse(await response.json());
}

export async function fetchProfileAvatar(userId: string): Promise<string | null> {
  const response = await apiFetch(`/api/profile?user_id=${encodeURIComponent(userId)}`);
  await expectOk(response);
  const profile = (await response.json()) as ProfileResponse;
  return profile.avatar_data_url || null;
}

export async function updateProfileAvatar(
  userId: string,
  avatarDataUrl: string | null,
): Promise<string | null> {
  const response = await apiFetch("/api/profile/avatar", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      avatar_data_url: avatarDataUrl,
    }),
  });
  await expectOk(response);
  const payload = (await response.json()) as { avatar_data_url: string | null };
  return payload.avatar_data_url || null;
}

export async function updateInterviewGoal(
  userId: string,
  goal: InterviewGoal,
): Promise<InterviewGoal> {
  const response = await apiFetch("/api/profile", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      target_role: goal.targetRole,
      experience_level: goal.experienceLevel,
      focus_areas: goal.focusAreas,
      interview_date: goal.interviewDate || null,
      job_description: goal.jobDescription,
    }),
  });
  await expectOk(response);
  return fromResponse(await response.json()) as InterviewGoal;
}

export async function fetchCoachingMemories(userId: string): Promise<CoachingMemory[]> {
  const response = await apiFetch(
    `/api/coaching-memories?user_id=${encodeURIComponent(userId)}`,
  );
  await expectOk(response);
  return response.json();
}

export async function proposeCoachingMemory(
  userId: string,
  kind: CoachingMemory["kind"],
  content: string,
): Promise<CoachingMemory> {
  const response = await apiFetch("/api/coaching-memories", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId, kind, content }),
  });
  await expectOk(response);
  return response.json();
}

export async function updateCoachingMemory(
  userId: string,
  memoryId: string,
  action: "confirm" | "reject" | "correct",
  content?: string,
): Promise<CoachingMemory> {
  const response = await apiFetch(
    `/api/coaching-memories/${encodeURIComponent(memoryId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, action, content }),
    },
  );
  await expectOk(response);
  return response.json();
}

export async function deleteCoachingMemory(
  userId: string,
  memoryId: string,
): Promise<void> {
  const response = await apiFetch(
    `/api/coaching-memories/${encodeURIComponent(memoryId)}?user_id=${encodeURIComponent(userId)}`,
    { method: "DELETE" },
  );
  await expectOk(response);
}
