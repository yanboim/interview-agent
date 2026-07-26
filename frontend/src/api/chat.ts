import type { ConversationMeta, HistoryMessage, StreamEvent } from "@/types";
import { ApiError, apiFetch, expectOk, parseApiError } from "@/api/core";

export function parseStreamLine(line: string): StreamEvent | null {
  if (!line.trim()) return null;
  return JSON.parse(line) as StreamEvent;
}

export async function streamChat(
  body: {
    userId: string;
    sessionId: string;
    message: string;
    idempotencyKey: string;
  },
  onEvent: (event: StreamEvent) => void,
  signal?: AbortSignal,
): Promise<string> {
  const response = await apiFetch("/api/chat/stream", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": body.idempotencyKey,
    },
    body: JSON.stringify({
      user_id: body.userId,
      session_id: body.sessionId,
      message: body.message,
    }),
    signal,
  });
  if (!response.ok) {
    throw new ApiError(await parseApiError(response), response.status);
  }
  if (!response.body) throw new ApiError("流式响应缺少内容", 500);

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let answer = "";
  let finished = false;

  const consumeLine = (line: string) => {
    const event = parseStreamLine(line);
    if (!event) return;
    onEvent(event);
    if (event.type === "error") {
      throw new ApiError(event.detail || "流式响应失败", 500);
    }
    if (event.type === "token") answer += event.content || "";
  };

  while (!finished) {
    const { value, done } = await reader.read();
    finished = done;
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";
    lines.forEach(consumeLine);
  }
  // 兼容服务端最后一行没有换行符的情况。
  consumeLine(buffer);
  return answer;
}

export async function fetchConversations(
  userId: string,
  includeArchived = false,
): Promise<ConversationMeta[]> {
  const response = await apiFetch(
    `/api/conversations?user_id=${encodeURIComponent(userId)}&include_archived=${includeArchived}`,
  );
  await expectOk(response);
  return response.json();
}

export async function archiveConversations(
  userId: string,
  sessionIds: string[],
  archived: boolean,
): Promise<number> {
  const response = await apiFetch("/api/conversations/archive", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: userId,
      session_ids: sessionIds,
      archived,
    }),
  });
  await expectOk(response);
  const payload = await response.json();
  return payload.updated;
}

export async function fetchMessages(
  userId: string,
  sessionId: string,
): Promise<HistoryMessage[]> {
  const response = await apiFetch(
    `/api/conversations/${encodeURIComponent(sessionId)}/messages?user_id=${encodeURIComponent(userId)}`,
  );
  await expectOk(response);
  return response.json();
}

export async function deleteConversation(userId: string, sessionId: string): Promise<void> {
  const response = await apiFetch(
    `/api/conversations/${encodeURIComponent(sessionId)}?user_id=${encodeURIComponent(userId)}`,
    { method: "DELETE" },
  );
  await expectOk(response);
}

export async function renameConversation(
  userId: string,
  sessionId: string,
  title: string,
): Promise<ConversationMeta> {
  const response = await apiFetch(
    `/api/conversations/${encodeURIComponent(sessionId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, title }),
    },
  );
  await expectOk(response);
  return response.json();
}
