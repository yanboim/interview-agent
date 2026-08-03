// 产品埋点上报：异步发送，失败静默不阻塞用户主流程。
import { apiFetch } from "@/api/core";

export function trackEvent(
  userId: string,
  eventName: string,
  properties: Record<string, unknown> = {},
  sessionId?: string,
) {
  void apiFetch("/api/product-events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      session_id: sessionId,
      event_name: eventName,
      properties,
    }),
  }).catch(() => {
    // 埋点失败不能阻塞用户主流程。
  });
}
