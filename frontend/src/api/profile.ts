import type { InterviewGoal } from "@/types";
import { apiFetch, expectOk } from "@/api/core";

interface ProfileResponse {
  target_role: string;
  experience_level: InterviewGoal["experienceLevel"];
  focus_areas: string;
  interview_date: string | null;
  job_description: string;
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
