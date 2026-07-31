<!-- 由 `python -m scripts.generate_chinese_docs` 自动生成，请勿编辑。 -->

# 关系数据字典

来源：`app/database.py` 中的SQLAlchemy元数据。使用 `python -m scripts.generate_chinese_docs` 重新生成。

生产Schema历史以Alembic Revision为准。

## `users`

| 列 | 类型 | 约束 | 引用 |
|---|---|---|---|
| `user_id` | `String(128)` | PK |  |
| `username` | `String(100)` | 唯一, 非空 |  |
| `password_hash` | `String(128)` | 非空 |  |
| `password_salt` | `String(64)` | 非空 |  |
| `recovery_code_hash` | `String(64)` |  |  |
| `role` | `String(20)` | 非空 |  |
| `created_at` | `String(40)` | 非空 |  |
| `updated_at` | `String(40)` | 非空 |  |

## `auth_tokens`

| 列 | 类型 | 约束 | 引用 |
|---|---|---|---|
| `token_id` | `String(128)` | PK |  |
| `user_id` | `String(128)` | 非空 |  |
| `token_hash` | `String(64)` | 唯一, 非空 |  |
| `token_type` | `String(20)` | 非空 |  |
| `expires_at` | `String(40)` | 非空 |  |
| `revoked_at` | `String(40)` |  |  |
| `created_at` | `String(40)` | 非空 |  |

## `conversations`

| 列 | 类型 | 约束 | 引用 |
|---|---|---|---|
| `user_id` | `String(128)` | PK |  |
| `session_id` | `String(128)` | PK |  |
| `title` | `String(200)` | 非空 |  |
| `mode` | `String(30)` | 非空 |  |
| `archived_at` | `String(40)` |  |  |
| `next_chat_turn_index` | `Integer` | 非空 |  |
| `active_chat_turn_id` | `String(128)` |  |  |
| `chat_summary` | `Text` | 非空 |  |
| `chat_summary_through_message_id` | `Integer` |  |  |
| `created_at` | `String(40)` | 非空 |  |
| `updated_at` | `String(40)` | 非空 |  |

## `messages`

| 列 | 类型 | 约束 | 引用 |
|---|---|---|---|
| `id` | `Integer` | PK |  |
| `user_id` | `String(128)` | 非空 |  |
| `session_id` | `String(128)` | 非空 |  |
| `role` | `String(20)` | 非空 |  |
| `content` | `Text` | 非空 |  |
| `metadata_json` | `Text` |  |  |
| `created_at` | `String(40)` | 非空 |  |

## `interviews`

| 列 | 类型 | 约束 | 引用 |
|---|---|---|---|
| `user_id` | `String(128)` | PK |  |
| `interview_id` | `String(128)` | PK |  |
| `topic` | `String(200)` | 非空 |  |
| `level` | `String(30)` | 非空 |  |
| `total_questions` | `Integer` | 非空 |  |
| `status` | `String(30)` | 非空 |  |
| `source_type` | `String(20)` | 非空 |  |
| `source_resume_id` | `String(128)` |  |  |
| `source_analysis_id` | `String(128)` |  |  |
| `source_display_name` | `String(255)` |  |  |
| `resume_context_json` | `Text` |  |  |
| `question_prompt_version` | `String(80)` |  |  |
| `question_schema_version` | `String(80)` |  |  |
| `question_model_version` | `String(100)` |  |  |
| `archived_at` | `String(40)` |  |  |
| `created_at` | `String(40)` | 非空 |  |
| `updated_at` | `String(40)` | 非空 |  |

## `user_profiles`

| 列 | 类型 | 约束 | 引用 |
|---|---|---|---|
| `user_id` | `String(128)` | PK |  |
| `target_role` | `String(100)` | 非空 |  |
| `experience_level` | `String(30)` | 非空 |  |
| `focus_areas` | `String(300)` | 非空 |  |
| `interview_date` | `String(40)` |  |  |
| `job_description` | `Text` | 非空 |  |
| `reminder_enabled` | `Boolean` | 非空 |  |
| `reminder_time` | `String(5)` | 非空 |  |
| `reminder_timezone` | `String(64)` | 非空 |  |
| `avatar_data_url` | `Text` |  |  |
| `created_at` | `String(40)` | 非空 |  |
| `updated_at` | `String(40)` | 非空 |  |

## `resume_documents`

| 列 | 类型 | 约束 | 引用 |
|---|---|---|---|
| `resume_id` | `String(128)` | PK |  |
| `user_id` | `String(128)` | 非空 |  |
| `original_filename` | `String(255)` | 非空 |  |
| `content_type` | `String(120)` | 非空 |  |
| `size_bytes` | `Integer` | 非空 |  |
| `sha256` | `String(64)` | 非空 |  |
| `storage_key` | `String(500)` | 非空 |  |
| `idempotency_key` | `String(128)` | 非空 |  |
| `request_digest` | `String(64)` | 非空 |  |
| `status` | `String(20)` | 非空 |  |
| `error` | `Text` |  |  |
| `created_at` | `String(40)` | 非空 |  |
| `updated_at` | `String(40)` | 非空 |  |

## `resume_analyses`

| 列 | 类型 | 约束 | 引用 |
|---|---|---|---|
| `analysis_id` | `String(128)` | PK |  |
| `user_id` | `String(128)` | 非空 |  |
| `resume_id` | `String(128)` | 非空 |  |
| `idempotency_key` | `String(128)` | 非空 |  |
| `request_digest` | `String(64)` | 非空 |  |
| `status` | `String(20)` | 非空 |  |
| `claim_token` | `String(128)` |  |  |
| `job_description` | `Text` | 非空 |  |
| `target_role` | `String(100)` | 非空 |  |
| `experience_level` | `String(30)` | 非空 |  |
| `parsed_text` | `Text` |  |  |
| `report_json` | `Text` |  |  |
| `draft_json` | `Text` |  |  |
| `warnings_json` | `Text` | 非空 |  |
| `revision` | `Integer` | 非空 |  |
| `prompt_version` | `String(80)` | 非空 |  |
| `schema_version` | `String(80)` | 非空 |  |
| `model_version` | `String(100)` | 非空 |  |
| `error` | `Text` |  |  |
| `created_at` | `String(40)` | 非空 |  |
| `updated_at` | `String(40)` | 非空 |  |

## `interview_reviews`

| 列 | 类型 | 约束 | 引用 |
|---|---|---|---|
| `review_id` | `String(128)` | PK |  |
| `user_id` | `String(128)` | 非空 |  |
| `input_type` | `String(20)` | 非空 |  |
| `original_filename` | `String(255)` |  |  |
| `content_type` | `String(120)` |  |  |
| `size_bytes` | `Integer` |  |  |
| `sha256` | `String(64)` |  |  |
| `storage_key` | `String(500)` |  |  |
| `external_processing_consent` | `Boolean` | 非空 |  |
| `consent_at` | `String(40)` |  |  |
| `status` | `String(40)` | 非空 |  |
| `transcript_json` | `Text` |  |  |
| `transcript_revision` | `Integer` | 非空 |  |
| `confirmed_revision` | `Integer` |  |  |
| `create_idempotency_key` | `String(128)` | 非空 |  |
| `create_request_digest` | `String(64)` | 非空 |  |
| `analysis_idempotency_key` | `String(128)` |  |  |
| `analysis_request_digest` | `String(64)` |  |  |
| `claim_token` | `String(128)` |  |  |
| `report_json` | `Text` |  |  |
| `prompt_version` | `String(80)` |  |  |
| `schema_version` | `String(80)` |  |  |
| `model_version` | `String(100)` |  |  |
| `error_category` | `String(80)` |  |  |
| `error` | `Text` |  |  |
| `processing_started_at` | `String(40)` |  |  |
| `created_at` | `String(40)` | 非空 |  |
| `updated_at` | `String(40)` | 非空 |  |

## `interview_review_turns`

| 列 | 类型 | 约束 | 引用 |
|---|---|---|---|
| `id` | `Integer` | PK |  |
| `user_id` | `String(128)` | 非空 |  |
| `review_id` | `String(128)` | 非空 |  |
| `turn_index` | `Integer` | 非空 |  |
| `question` | `Text` | 非空 |  |
| `answer` | `Text` | 非空 |  |
| `score` | `Float` |  |  |
| `dimensions_json` | `Text` |  |  |
| `strengths_json` | `Text` |  |  |
| `weaknesses_json` | `Text` |  |  |
| `feedback` | `Text` |  |  |
| `improved_answer` | `Text` |  |  |
| `created_at` | `String(40)` | 非空 |  |

## `chat_turns`

| 列 | 类型 | 约束 | 引用 |
|---|---|---|---|
| `turn_id` | `String(128)` | PK |  |
| `user_id` | `String(128)` | 非空 |  |
| `session_id` | `String(128)` | 非空 |  |
| `turn_index` | `Integer` | 非空 |  |
| `idempotency_key` | `String(128)` | 非空 |  |
| `request_digest` | `String(64)` | 非空 |  |
| `request_content` | `Text` | 非空 |  |
| `status` | `String(20)` | 非空 |  |
| `claim_token` | `String(128)` |  |  |
| `assistant_content` | `Text` |  |  |
| `metadata_json` | `Text` |  |  |
| `error` | `Text` |  |  |
| `created_at` | `String(40)` | 非空 |  |
| `updated_at` | `String(40)` | 非空 |  |

## `interview_turns`

| 列 | 类型 | 约束 | 引用 |
|---|---|---|---|
| `id` | `Integer` | PK |  |
| `user_id` | `String(128)` | 非空 |  |
| `interview_id` | `String(128)` | 非空 |  |
| `turn_index` | `Integer` | 非空 |  |
| `question` | `Text` | 非空 |  |
| `answer` | `Text` |  |  |
| `score` | `Float` |  |  |
| `feedback` | `Text` |  |  |
| `dimensions_json` | `Text` |  |  |
| `strengths_json` | `Text` |  |  |
| `weaknesses_json` | `Text` |  |  |
| `reference_answer` | `Text` |  |  |
| `assessment_prompt_version` | `String(80)` |  |  |
| `assessment_schema_version` | `String(80)` |  |  |
| `assessment_model_version` | `String(100)` |  |  |
| `submission_status` | `String(20)` | 非空 |  |
| `idempotency_key` | `String(128)` |  |  |
| `answer_digest` | `String(64)` |  |  |
| `claim_token` | `String(128)` |  |  |
| `result_json` | `Text` |  |  |
| `submission_error` | `Text` |  |  |
| `processing_started_at` | `String(40)` |  |  |
| `created_at` | `String(40)` | 非空 |  |
| `updated_at` | `String(40)` | 非空 |  |

## `interview_answer_attempts`

| 列 | 类型 | 约束 | 引用 |
|---|---|---|---|
| `attempt_id` | `String(128)` | PK |  |
| `user_id` | `String(128)` | 非空 |  |
| `interview_id` | `String(128)` | 非空 |  |
| `turn_index` | `Integer` | 非空 |  |
| `attempt_index` | `Integer` | 非空 |  |
| `answer` | `Text` | 非空 |  |
| `score` | `Float` | 非空 |  |
| `feedback` | `Text` | 非空 |  |
| `dimensions_json` | `Text` | 非空 |  |
| `strengths_json` | `Text` | 非空 |  |
| `weaknesses_json` | `Text` | 非空 |  |
| `reference_answer` | `Text` |  |  |
| `prompt_version` | `String(80)` |  |  |
| `schema_version` | `String(80)` |  |  |
| `model_version` | `String(100)` |  |  |
| `created_at` | `String(40)` | 非空 |  |

## `learning_tasks`

| 列 | 类型 | 约束 | 引用 |
|---|---|---|---|
| `task_id` | `String(128)` | PK |  |
| `user_id` | `String(128)` | 非空 |  |
| `source_interview_id` | `String(128)` |  |  |
| `dimension` | `String(100)` | 非空 |  |
| `weakness` | `String(300)` | 非空 |  |
| `action` | `Text` | 非空 |  |
| `status` | `String(30)` | 非空 |  |
| `due_at` | `String(40)` | 非空 |  |
| `review_count` | `Integer` | 非空 |  |
| `last_reviewed_at` | `String(40)` |  |  |
| `next_review_at` | `String(40)` |  |  |
| `recall_outcome` | `String(20)` |  |  |
| `difficulty_rating` | `Integer` |  |  |
| `lapse_count` | `Integer` | 非空 |  |
| `review_confidence` | `Float` | 非空 |  |
| `created_at` | `String(40)` | 非空 |  |
| `updated_at` | `String(40)` | 非空 |  |

## `agent_action_confirmations`

| 列 | 类型 | 约束 | 引用 |
|---|---|---|---|
| `confirmation_id` | `String(128)` | PK |  |
| `user_id` | `String(128)` | 非空 |  |
| `action_type` | `String(80)` | 非空 |  |
| `payload_json` | `Text` | 非空 |  |
| `payload_digest` | `String(64)` | 非空 |  |
| `status` | `String(20)` | 非空 |  |
| `result_json` | `Text` |  |  |
| `expires_at` | `String(40)` | 非空 |  |
| `consumed_at` | `String(40)` |  |  |
| `created_at` | `String(40)` | 非空 |  |

## `agent_runs`

| 列 | 类型 | 约束 | 引用 |
|---|---|---|---|
| `run_id` | `String(128)` | PK |  |
| `user_id` | `String(128)` | 非空 |  |
| `run_type` | `String(80)` | 非空 |  |
| `status` | `String(30)` | 非空 |  |
| `idempotency_key` | `String(128)` | 非空 |  |
| `input_digest` | `String(64)` | 非空 |  |
| `input_json` | `Text` | 非空 |  |
| `proposal_json` | `Text` |  |  |
| `result_json` | `Text` |  |  |
| `error_code` | `String(80)` |  |  |
| `created_at` | `String(40)` | 非空 |  |
| `updated_at` | `String(40)` | 非空 |  |

## `agent_steps`

| 列 | 类型 | 约束 | 引用 |
|---|---|---|---|
| `step_id` | `String(128)` | PK |  |
| `run_id` | `String(128)` | 非空 |  |
| `user_id` | `String(128)` | 非空 |  |
| `step_key` | `String(80)` | 非空 |  |
| `step_type` | `String(30)` | 非空 |  |
| `status` | `String(30)` | 非空 |  |
| `idempotency_key` | `String(160)` | 非空 |  |
| `input_digest` | `String(64)` | 非空 |  |
| `claim_owner` | `String(128)` |  |  |
| `claimed_at` | `String(40)` |  |  |
| `attempt_count` | `Integer` | 非空 |  |
| `result_json` | `Text` |  |  |
| `error_code` | `String(80)` |  |  |
| `created_at` | `String(40)` | 非空 |  |
| `updated_at` | `String(40)` | 非空 |  |

## `assistant_feedback`

| 列 | 类型 | 约束 | 引用 |
|---|---|---|---|
| `feedback_id` | `String(128)` | PK |  |
| `user_id` | `String(128)` | 非空 |  |
| `turn_id` | `String(128)` | 非空 |  |
| `rating` | `String(10)` | 非空 |  |
| `reason_code` | `String(40)` |  |  |
| `comment` | `Text` |  |  |
| `prompt_version` | `String(80)` |  |  |
| `schema_version` | `String(80)` |  |  |
| `model_version` | `String(100)` |  |  |
| `source_ids_json` | `Text` | 非空 |  |
| `created_at` | `String(40)` | 非空 |  |
| `updated_at` | `String(40)` | 非空 |  |

## `evaluation_candidates`

| 列 | 类型 | 约束 | 引用 |
|---|---|---|---|
| `candidate_id` | `String(128)` | PK |  |
| `feedback_id` | `String(128)` | 唯一, 非空 |  |
| `user_id` | `String(128)` | 非空 |  |
| `status` | `String(30)` | 非空 |  |
| `reviewed_by` | `String(128)` |  |  |
| `reviewed_at` | `String(40)` |  |  |
| `approved_payload_json` | `Text` |  |  |
| `created_at` | `String(40)` | 非空 |  |

## `coaching_memories`

| 列 | 类型 | 约束 | 引用 |
|---|---|---|---|
| `memory_id` | `String(128)` | PK |  |
| `user_id` | `String(128)` | 非空 |  |
| `kind` | `String(30)` | 非空 |  |
| `content` | `Text` | 非空 |  |
| `status` | `String(20)` | 非空 |  |
| `source_type` | `String(40)` | 非空 |  |
| `source_id` | `String(128)` |  |  |
| `source_revision` | `Integer` |  |  |
| `expires_at` | `String(40)` |  |  |
| `confirmed_at` | `String(40)` |  |  |
| `created_at` | `String(40)` | 非空 |  |
| `updated_at` | `String(40)` | 非空 |  |

## `tool_audit_logs`

| 列 | 类型 | 约束 | 引用 |
|---|---|---|---|
| `audit_id` | `String(128)` | PK |  |
| `user_id` | `String(128)` | 非空 |  |
| `role` | `String(20)` | 非空 |  |
| `tool_name` | `String(100)` | 非空 |  |
| `input_summary` | `String(500)` | 非空 |  |
| `status` | `String(30)` | 非空 |  |
| `duration_ms` | `Integer` | 非空 |  |
| `result_summary` | `String(500)` |  |  |
| `request_id` | `String(128)` |  |  |
| `interaction_type` | `String(30)` |  |  |
| `interaction_id` | `String(256)` |  |  |
| `created_at` | `String(40)` | 非空 |  |

## `audit_events`

| 列 | 类型 | 约束 | 引用 |
|---|---|---|---|
| `event_id` | `String(128)` | PK |  |
| `request_id` | `String(128)` | 非空 |  |
| `actor_user_id` | `String(128)` |  |  |
| `actor_username` | `String(100)` |  |  |
| `actor_role` | `String(20)` |  |  |
| `action` | `String(160)` | 非空 |  |
| `resource_type` | `String(80)` | 非空 |  |
| `resource_id` | `String(256)` |  |  |
| `outcome` | `String(20)` | 非空 |  |
| `method` | `String(10)` | 非空 |  |
| `path` | `String(300)` | 非空 |  |
| `status_code` | `Integer` | 非空 |  |
| `duration_ms` | `Integer` | 非空 |  |
| `detail_json` | `Text` | 非空 |  |
| `created_at` | `String(40)` | 非空 |  |

## `execution_traces`

| 列 | 类型 | 约束 | 引用 |
|---|---|---|---|
| `trace_id` | `String(128)` | PK |  |
| `request_id` | `String(128)` | 非空 |  |
| `user_id` | `String(128)` | 非空 |  |
| `interaction_type` | `String(30)` | 非空 |  |
| `interaction_id` | `String(256)` | 非空 |  |
| `stage` | `String(80)` | 非空 |  |
| `status` | `String(30)` | 非空 |  |
| `duration_ms` | `Integer` |  |  |
| `detail_json` | `Text` | 非空 |  |
| `prompt_version` | `String(80)` |  |  |
| `schema_version` | `String(80)` |  |  |
| `model_version` | `String(100)` |  |  |
| `created_at` | `String(40)` | 非空 |  |

## `product_events`

| 列 | 类型 | 约束 | 引用 |
|---|---|---|---|
| `event_id` | `String(128)` | PK |  |
| `user_id` | `String(128)` | 非空 |  |
| `session_id` | `String(128)` |  |  |
| `event_name` | `String(100)` | 非空 |  |
| `properties_json` | `Text` | 非空 |  |
| `created_at` | `String(40)` | 非空 |  |

## `deployment_releases`

| 列 | 类型 | 约束 | 引用 |
|---|---|---|---|
| `release_id` | `String(128)` | PK |  |
| `version` | `String(100)` | 非空 |  |
| `title` | `String(200)` | 非空 |  |
| `summary` | `Text` | 非空 |  |
| `environment` | `String(20)` | 非空 |  |
| `status` | `String(20)` | 非空 |  |
| `commit_sha` | `String(64)` |  |  |
| `changes_json` | `Text` | 非空 |  |
| `verification_json` | `Text` | 非空 |  |
| `app_image` | `String(200)` |  |  |
| `worker_image` | `String(200)` |  |  |
| `migration_revision` | `String(64)` |  |  |
| `recovery_point` | `String(200)` |  |  |
| `triggered_by` | `String(100)` | 非空 |  |
| `started_at` | `String(40)` | 非空 |  |
| `completed_at` | `String(40)` |  |  |
| `created_at` | `String(40)` | 非空 |  |
| `updated_at` | `String(40)` | 非空 |  |
