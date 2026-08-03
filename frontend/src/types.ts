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

export interface CoachingMemory {
  memory_id: string;
  kind: "fact" | "preference" | "goal" | "observation";
  content: string;
  status: "proposed" | "confirmed" | "rejected";
  source_type: string;
  source_id?: string | null;
  expires_at?: string | null;
  updated_at: string;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  turnId?: string;
  pending?: boolean;
  feedback?: "up" | "down";
  knowledgeUsed?: boolean;
  sources?: ChatSource[];
  citations?: AnswerCitation[];
  unsupportedClaims?: string[];
}

export interface ChatSource {
  evidence_id?: string;
  label: string;
  kind: "private" | "public";
  url?: string;
  fetched_at?: string;
  snippet?: string;
}

export interface AnswerCitation {
  claim: string;
  evidence_ids: string[];
  support: "supported" | "unsupported" | "conflicting";
}

/** 服务端历史消息(含时间戳)。 */
export interface HistoryMessage {
  role: string;
  content: string;
  created_at: string;
  metadata?: {
    turn_id?: string;
    knowledge_used?: boolean;
    sources?: ChatSource[];
    schema_version?: number | string;
    citations?: AnswerCitation[];
    unsupported_claims?: string[];
    prompt_version?: string;
    model_version?: string;
  };
}

/** /api/chat/stream 的 NDJSON 事件之一。 */
export type StreamEvent =
  | { type: "token"; content: string }
  | { type: "sources"; knowledge_used: boolean; sources: ChatSource[] }
  | {
      type: "citations";
      schema_version: number | string;
      citations: AnswerCitation[];
      unsupported_claims: string[];
    }
  | { type: "error"; detail: string; code?: string; retryable?: boolean }
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
  source_type: "general" | "resume";
  source_resume?: InterviewResumeSource | null;
}

export interface InterviewResumeSource {
  resume_id: string;
  analysis_id: string;
  display_name: string;
  available: boolean;
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
  source_type: "general" | "resume";
  source_resume?: InterviewResumeSource | null;
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
  calibrated_dimension_scores: Record<string, number>;
  calibration: {
    version: string;
    sample_count: number;
    confidence: number;
    recency_weighted_score: number;
    cohorts: Record<string, Array<{
      cohort: string;
      sample_count: number;
      confidence: number;
      recency_weighted_score: number;
    }>>;
  };
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

export interface AgentRunStep {
  step_id: string;
  step_key: string;
  step_type: "read" | "model" | "command";
  status: "pending" | "claimed" | "completed" | "failed" | "skipped";
  attempt_count: number;
  error_code: string | null;
}

export interface TrainingProgramRun {
  run_id: string;
  run_type: "personalized_training_program";
  status:
    | "proposed"
    | "awaiting_confirmation"
    | "running"
    | "completed"
    | "failed"
    | "cancelled";
  proposal: {
    schema_version: "training-program-proposal-v1";
    target_role: string;
    topic: string;
    answered_questions: number;
    candidates: Array<{ dimension: string; weakness: string; action: string }>;
    interview_create_url: string;
  };
  result: {
    task_ids: string[];
    task_count: number;
    interview_create_url: string;
  } | null;
  steps: AgentRunStep[];
  events: Array<{ event: string; run_id: string; step_id?: string; step_key?: string }>;
  error_code: string | null;
}

export interface ResumeIssue {
  severity: "high" | "medium" | "low" | string;
  category: string;
  message: string;
  evidence: string;
  suggestion: string;
}

export interface ResumeDraftSection {
  title: string;
  items: string[];
}

export interface ResumeDraft {
  name: string;
  headline: string;
  summary: string;
  sections: ResumeDraftSection[];
  pending_questions: string[];
}

export interface ResumeAnalysis {
  analysis_id: string;
  resume_id: string;
  status: "pending" | "processing" | "ready" | "failed";
  job_description: string;
  target_role: string;
  experience_level: string;
  report: {
    scores: Record<string, number>;
    keyword_matches: string[];
    keyword_gaps: string[];
    issues: ResumeIssue[];
  } | null;
  draft: ResumeDraft | null;
  warnings: Array<{ code: string; message: string }>;
  revision: number;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface ResumeDocument {
  resume_id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  status: "uploaded" | "processing" | "ready" | "failed";
  error: string | null;
  created_at: string;
  updated_at: string;
  latest_analysis?: ResumeAnalysis | null;
  analyses?: ResumeAnalysis[];
}

export interface TranscriptSegment {
  segment_id: string;
  speaker: "interviewer" | "candidate" | "unknown";
  text: string;
  start_seconds?: number | null;
  end_seconds?: number | null;
}

export interface InterviewReviewTurn {
  turn_index: number;
  question: string;
  answer: string;
  score: number | null;
  dimensions: Record<string, number>;
  strengths: string[];
  weaknesses: string[];
  feedback: string | null;
  improved_answer: string | null;
}

export interface InterviewReview {
  review_id: string;
  input_type: "audio" | "text";
  original_filename?: string | null;
  status:
    | "transcribing"
    | "awaiting_confirmation"
    | "analyzing"
    | "ready"
    | "failed";
  transcript_revision: number;
  confirmed_revision?: number | null;
  segments?: TranscriptSegment[];
  report?: {
    overall_summary: string;
    dimension_scores: Record<string, number>;
    strengths: string[];
    weaknesses: string[];
    action_plan: string[];
  } | null;
  turns?: InterviewReviewTurn[];
  error_category?: string | null;
  error?: string | null;
  created_at: string;
  updated_at: string;
}

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
    workflow?: {
      version: string;
      planner: string;
      max_specialists: number;
    } | null;
    specialists: Array<{ name: string; responsibility: string }>;
  };
  operator_links: Array<{
    id: "prometheus" | "grafana";
    name: string;
    url: string;
  }>;
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
