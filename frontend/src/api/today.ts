import { apiFetch, expectOk } from "@/api/core";

export interface ReminderPreferences {
  enabled: boolean;
  reminder_time: string;
  timezone: string;
}

export interface TodayPlan {
  recommendation: {
    type: "resume_interview" | "review" | "new_interview";
    title: string;
    reason: string;
    href: string;
  };
  top_weakness: string | null;
  target_role: string | null;
  has_job_description: boolean;
  due_count: number;
}

export async function fetchTodayPlan(userId: string): Promise<TodayPlan> {
  const response = await apiFetch(`/api/today-plan?user_id=${encodeURIComponent(userId)}`);
  await expectOk(response);
  return response.json();
}

export async function fetchReminderPreferences(
  userId: string,
): Promise<ReminderPreferences> {
  const response = await apiFetch(
    `/api/reminders/preferences?user_id=${encodeURIComponent(userId)}`,
  );
  await expectOk(response);
  return response.json();
}

export async function saveReminderPreferences(
  userId: string,
  preferences: ReminderPreferences,
): Promise<ReminderPreferences> {
  const response = await apiFetch("/api/reminders/preferences", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      enabled: preferences.enabled,
      reminder_time: preferences.reminder_time,
      timezone: preferences.timezone,
    }),
  });
  await expectOk(response);
  return response.json();
}

export async function fetchDueReminders(
  userId: string,
): Promise<{
  due: boolean;
  items: Array<{ type: string; id: string; title: string; action: string }>;
  local_date?: string;
}> {
  const response = await apiFetch(
    `/api/reminders/due?user_id=${encodeURIComponent(userId)}`,
  );
  await expectOk(response);
  return response.json();
}
