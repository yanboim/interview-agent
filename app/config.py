"""集中声明环境配置、默认值和跨字段安全校验。"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置：从环境变量或 ``.env`` 加载，集中声明默认值与跨字段安全校验。

    所有功能开关、模型/向量库参数、预算与超时、密钥文件路径都汇聚于此，
    便于运维集中治理。敏感凭据支持「直接值」与「密钥文件路径」两种配置，
    在 ``model_post_init`` 中把文件内容回填到对应字段。
    """

    zhipu_api_key: str = ""
    zhipu_api_base: str = "https://open.bigmodel.cn/api/coding/paas/v4"
    zhipu_model: str = "glm-5.2"
    llm_model_knowledge: str = ""
    llm_model_interviewer: str = ""
    llm_model_evaluator: str = ""
    llm_model_planner: str = ""
    llm_model_summarization: str = ""
    llm_model_schema_repair: str = ""
    llm_fallback_enabled: bool = False
    llm_fallback_model: str = ""
    llm_fallback_approved_purposes: str = ""
    llm_fallback_evaluation_approved: bool = False
    llm_price_version: str = "zhipu-2026-07"
    llm_input_usd_per_million: float = 0.0
    llm_output_usd_per_million: float = 0.0
    llm_timeout_seconds: float = 45.0
    llm_max_retries: int = 2
    # Provider response headers can succeed while the SSE body stalls. Restart
    # only a stream that failed before yielding any chunk; partial streams are
    # never replayed because doing so could duplicate text or tool calls.
    llm_zero_chunk_stream_restarts: int = 1
    llm_max_concurrency: int = 8
    llm_input_char_budget: int = 60000
    llm_max_output_tokens: int = 2000
    # 上下文窗口预算。估算为 UTF-8 字节长度的保守上界(中文每字≈3 字节),
    # 因此该值需显著小于模型真实 token 窗口。GLM-5.2 支持 128K token,
    # 32000 字节预算在中文场景约等价于 ~10K 真实 token 的历史,留足响应与系统提示空间。
    chat_context_token_budget: int = 32000
    chat_summary_token_budget: int = 4000
    # 单次 chat 请求的端到端墙钟上限（显式路由、专家与工具）。
    # 超时后中止并返回降级错误,避免多 Agent 串行时无界等待。
    chat_agent_timeout_seconds: float = 90.0
    # LangGraph ReAct 递归步数上限(模型↔工具循环次数)。
    # 多 Agent 嵌套时步数消耗翻倍,需高于单 Agent 默认值 25。
    agent_recursion_limit: int = 40
    multi_agent_enabled: bool = True
    agent_max_model_calls: int = 5
    agent_max_total_tokens: int = 16000
    agent_max_cost_usd: float = 1.0
    agent_chat_max_model_calls: int = 5
    agent_chat_max_total_tokens: int = 16000
    agent_chat_max_cost_usd: float = 1.0
    # Explicit Workflow V2 can execute up to four deterministic specialists.
    # Keep one bounded call allowance per specialist while retaining the shared
    # request token and cost ceilings above.
    # A tool-using structured specialist can require: decide tool, consume tool
    # result, produce schema, and one provider/schema-repair continuation. Live
    # pre-release evidence showed four calls can reject a valid completion, so
    # allow five while retaining the shared token, cost, and wall-clock caps.
    agent_workflow_v2_max_model_calls_per_route: int = 5
    agent_evaluation_max_model_calls: int = 2
    agent_evaluation_max_total_tokens: int = 8000
    agent_evaluation_max_cost_usd: float = 0.5
    zhipu_embedding_api_key: str = ""
    zhipu_embedding_api_base: str = "https://open.bigmodel.cn/api/paas/v4"
    zhipu_embedding_model: str = "embedding-2"
    sparse_embedding_model: str = "Qdrant/bm25"
    sparse_embedding_cache_dir: Path = Path("data/fastembed-cache")
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "interview_knowledge"
    qdrant_collection_alias: str = "interview_knowledge_current"
    knowledge_publish_lock_seconds: int = 3600
    conversation_db_path: Path = Path("data/interview-agent.db")
    database_url: str = ""
    auto_create_schema: bool = True
    app_api_key: str = ""
    auth_required: bool = False
    access_token_minutes: int = 60
    refresh_token_days: int = 30
    rate_limit_requests: int = 30
    rate_limit_window_seconds: int = 60
    retrieval_candidate_k: int = 20
    retrieval_final_k: int = 4
    retrieval_min_score: float = 0.0
    dense_relevance_min_score: float = 0.4
    lexical_reranker_enabled: bool = False
    lexical_retrieval_weight: float = 0.35
    llm_reranker_enabled: bool = False
    reranker_enabled: bool = False
    reranker_model: str = "Xenova/bge-reranker-base"
    reranker_min_score: float = 0.0
    web_search_enabled: bool = False
    web_search_api_key: str = ""
    web_search_api_url: str = "https://api.tavily.com/search"
    web_search_max_results: int = 5
    web_search_timeout_seconds: float = 10.0
    ingest_run_evaluation: bool = False
    rag_regression_min_ndcg: float = 0.0
    redis_url: str = ""
    redis_cache_ttl_seconds: int = 300
    redis_queue_name: str = "interview-agent:jobs"
    job_lease_seconds: int = 900
    job_max_attempts: int = 3
    job_retry_base_seconds: int = 30
    job_poll_seconds: float = 1.0
    worker_heartbeat_interval_seconds: float = 5.0
    worker_heartbeat_ttl_seconds: int = 20
    resume_feature_enabled: bool = False
    user_files_dir: Path = Path("data/user-files")
    resume_max_upload_bytes: int = 10 * 1024 * 1024
    resume_prompt_version: str = "resume-analysis-v1"
    resume_analysis_timeout_seconds: float = 180.0
    resume_analysis_max_retries: int = 0
    review_feature_enabled: bool = False
    transcription_enabled: bool = False
    transcription_api_url: str = ""
    transcription_api_key: str = ""
    transcription_api_key_file: str = ""
    transcription_provider_name: str = "configured-provider"
    transcription_timeout_seconds: float = 120.0
    review_max_audio_bytes: int = 25 * 1024 * 1024
    review_prompt_version: str = "interview-review-v1"
    review_analysis_batch_size: int = 6
    review_analysis_timeout_seconds: float = 180.0
    review_analysis_max_retries: int = 0
    agent_prompt_version: str = "agent-system-v1"
    agent_context_reserve_tokens: int = 4000
    interview_question_prompt_version: str = "interview-question-v1"
    interview_assessment_prompt_version: str = "interview-assessment-v1"
    log_level: str = "INFO"
    json_logs: bool = True
    otel_enabled: bool = False
    otel_service_name: str = "interview-agent"
    otel_exporter_otlp_endpoint: str = ""
    resource_probe_timeout_seconds: float = 2.0
    resource_gateway_health_url: str = ""
    resource_prometheus_health_url: str = ""
    resource_grafana_health_url: str = ""
    admin_prometheus_url: str = ""
    admin_grafana_url: str = ""
    zhipu_api_key_file: str = ""
    zhipu_embedding_api_key_file: str = ""
    web_search_api_key_file: str = ""
    app_api_key_file: str = ""
    # 前端产物目录(Vue 构建输出)。为空时回退到旧的内嵌静态页 app/web/。
    frontend_dist: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def model_post_init(self, _context: object) -> None:
        """加载完成后做跨字段校验与密钥文件回填。

        校验 Agent 路由灰度参数、预算上限的合法性；对每个「密钥值/密钥
        文件」字段对，当值为空但文件路径已配置时，读取文件内容回填到值
        字段，使两种配置方式等价。

        异常:
            ValueError: 灰度阶段、百分比或预算参数越界时抛出。
        """
        if (
            self.agent_max_model_calls < 1
            or self.agent_max_total_tokens < 1
            or self.agent_chat_max_model_calls < 1
            or self.agent_chat_max_total_tokens < 1
            or self.agent_workflow_v2_max_model_calls_per_route < 1
        ):
            raise ValueError("Agent model budgets must be positive")
        if not 0 <= self.llm_zero_chunk_stream_restarts <= 2:
            raise ValueError("LLM zero-chunk stream restarts must be between 0 and 2")
        secret_pairs = (
            ("zhipu_api_key", "zhipu_api_key_file"),
            ("zhipu_embedding_api_key", "zhipu_embedding_api_key_file"),
            ("web_search_api_key", "web_search_api_key_file"),
            ("app_api_key", "app_api_key_file"),
            ("transcription_api_key", "transcription_api_key_file"),
        )
        for value_field, file_field in secret_pairs:
            if getattr(self, value_field) or not getattr(self, file_field):
                continue
            secret_path = Path(getattr(self, file_field))
            object.__setattr__(
                self,
                value_field,
                secret_path.read_text(encoding="utf-8").strip(),
            )


@lru_cache
def get_settings() -> Settings:
    """返回进程级缓存的配置单例。

    缓存避免在每次读取时重复解析 ``.env`` 与执行校验；测试需要刷新配置时
    应调用 ``get_settings.cache_clear()``。
    """
    return Settings()
