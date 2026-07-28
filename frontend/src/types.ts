// 与后端 API 契约对齐的类型定义。
// 后端接口契约保持不变(见 app/main.py),这些类型对应接口返回结构。

export interface AuthPayload {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
  user: AuthUser;
  recovery_code?: string;
}

export interface AuthUser {
  user_id: string;
  username: string;
  role: "user" | "admin";
}

export interface InterviewGoal {
  targetRole: string;
  experienceLevel: "初级" | "中级" | "高级" | "专家";
  focusAreas: string;
  interviewDate: string;
  jobDescription: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  pending?: boolean;
  feedback?: "up" | "down";
  knowledgeUsed?: boolean;
  sources?: ChatSource[];
}

export interface ChatSource {
  label: string;
  kind: "private" | "public";
  url?: string;
  fetched_at?: string;
  snippet?: string;
}

/** 服务端历史消息(含时间戳)。 */
export interface HistoryMessage {
  role: string;
  content: string;
  created_at: string;
  metadata?: {
    knowledge_used?: boolean;
    sources?: ChatSource[];
  };
}

/** /api/chat/stream 的 NDJSON 事件之一。 */
export type StreamEvent =
  | { type: "token"; content: string }
  | { type: "sources"; knowledge_used: boolean; sources: ChatSource[] }
  | { type: "error"; detail: string }
  | {
      type: "done";
      user_id?: string;
      session_id?: string;
      turn_id?: string;
      replayed?: boolean;
    };

export interface ConversationMeta {
  session_id: string;
  title: string;
  mode: string;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface InterviewSummary {
  interview_id: string;
  topic: string;
  level: string;
  status: "active" | "completed";
  total_questions: number;
  answered_questions: number;
  average_score: number | null;
  archived_at: string | null;
  updated_at: string;
}

export interface InterviewTurn {
  turn_index: number;
  question: string;
  answer: string;
  score: number | null;
  feedback: string | null;
  reference_answer?: string | null;
}

export interface InterviewDetail {
  interview: InterviewSummary;
  turns: InterviewTurn[];
}

export interface ActiveInterview {
  interview_id: string;
  topic: string;
  level: string;
  status: "active" | "completed";
  turn_index: number;
  question_count: number;
  question: string;
}

export interface AnswerResult {
  score: number;
  feedback: string;
  reference_answer: string;
  dimensions: Record<string, number>;
  strengths: string[];
  weaknesses: string[];
  next_question: string | null;
  turn_index: number;
  status: "active" | "completed";
  comparison?: {
    attempt_index: number;
    previous_answer: string;
    previous_score: number;
    score_delta: number;
  };
}

/** 评分四维(后端 app/interview_engine.py 定义)。 */
export interface DimensionScores {
  accuracy?: number;
  depth?: number;
  communication?: number;
  practicality?: number;
  [key: string]: number | undefined;
}

export interface CapabilityProfile {
  summary: {
    average_score: number;
    interviews: number;
    completed_interviews: number;
    answered_questions: number;
    improvement: number;
  };
  dimension_scores: Record<string, number>;
  trend: Array<{ updated_at: string; average_score: number }>;
  topic_breakdown: Array<{
    topic: string;
    interviews: number;
    answered_questions: number;
    average_score: number;
  }>;
  weaknesses: Array<{ label: string; count: number }>;
  recent_training: Array<{
    topic: string;
    level: string;
    answered_questions: number;
    average_score: number;
    updated_at: string;
  }>;
  frequent_questions: Array<{ question: string; count: number }>;
  available_topics: string[];
  filter: { topic: string | null };
  job_readiness: {
    score: number;
    confidence: "low" | "medium" | "high";
    target_role: string | null;
    has_job_description: boolean;
    priorities: Array<{ label: string; reason: string }>;
  };
}

export interface LearningTask {
  task_id: string;
  dimension: string;
  weakness: string;
  action: string;
  status: "todo" | "in_progress" | "completed";
  due_at: string;
  review_count: number;
  next_review_at: string | null;
}

export type LearningStatus = LearningTask["status"];

/** 后台相关类型 */
export interface AdminSummary {
  operator: string;
  role: string;
  counts: Record<string, number>;
}

export interface AdminRuntime {
  dependencies: Record<string, { status: "ok" | "error"; detail: string }>;
  features: Record<string, boolean>;
  agent: {
    mode: string;
    specialists: Array<{ name: string; responsibility: string }>;
  };
}

export type AdminResourceStatus =
  | "healthy"
  | "unavailable"
  | "configured"
  | "disabled"
  | "unknown";

export type AdminResourceExposure =
  | "public_gateway"
  | "loopback"
  | "private_network"
  | "external_provider";

export interface AdminResource {
  id: string;
  name: string;
  category: string;
  status: AdminResourceStatus;
  detail: string;
  exposure: AdminResourceExposure;
  critical: boolean;
  description: string;
  runbook: string;
  latency_ms: number | null;
  console_url: string | null;
}

export interface AdminResourceCenter {
  operator: string;
  overall_status: "healthy" | "degraded";
  checked_at: string;
  summary: Record<AdminResourceStatus, number>;
  resources: AdminResource[];
}

export interface AdminKnowledgeFile {
  filename: string;
  size: number;
  updated_at: string;
}

export interface AdminUser {
  user_id: string;
  username: string;
  role: "user" | "admin";
  conversation_count: number;
  interview_count: number;
  created_at: string;
}

export interface AdminAudit {
  audit_id: string;
  created_at: string;
  user_id: string;
  tool_name: string;
  status: "success" | "error" | "denied";
  duration_ms: number;
  input_summary: string;
}

export interface AdminAuditEvent {
  event_id: string;
  request_id: string;
  actor_user_id: string | null;
  actor_username: string | null;
  actor_role: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  outcome: "success" | "error" | "denied";
  method: string;
  path: string;
  status_code: number;
  duration_ms: number;
  detail_json: string;
  created_at: string;
}

export interface AdminInteraction {
  interaction_type: "chat" | "interview";
  interaction_id: string;
  user_id: string;
  username: string;
  container_id: string;
  container_title: string;
  prompt_text: string;
  input_text: string;
  output_text: string;
  status: string;
  error: string;
  metadata_json: string;
  created_at: string;
  updated_at: string;
}

export interface AdminExecutionTrace {
  trace_id: string;
  request_id: string;
  user_id: string;
  interaction_type: "chat" | "interview";
  interaction_id: string;
  stage: string;
  status: string;
  duration_ms: number | null;
  detail_json: string;
  created_at: string;
}

export interface ProductEvent {
  event_id: string;
  user_id: string;
  session_id: string | null;
  event_name: string;
  properties_json: string;
  created_at: string;
}

export type DeploymentReleaseStatus =
  | "deploying"
  | "succeeded"
  | "failed"
  | "rolled_back";

export interface DeploymentRelease {
  release_id: string;
  version: string;
  title: string;
  summary: string;
  environment: "canary" | "production";
  status: DeploymentReleaseStatus;
  commit_sha: string | null;
  changes: string[];
  verification: Record<string, string>;
  app_image: string | null;
  worker_image: string | null;
  migration_revision: string | null;
  recovery_point: string | null;
  triggered_by: string;
  started_at: string;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}
