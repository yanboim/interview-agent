from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or ``.env``."""

    zhipu_api_key: str = ""
    zhipu_api_base: str = "https://open.bigmodel.cn/api/coding/paas/v4"
    zhipu_model: str = "glm-5.2"
    llm_timeout_seconds: float = 45.0
    llm_max_retries: int = 2
    llm_max_concurrency: int = 8
    llm_input_char_budget: int = 60000
    llm_max_output_tokens: int = 2000
    chat_context_token_budget: int = 12000
    chat_summary_token_budget: int = 2000
    multi_agent_enabled: bool = True
    zhipu_embedding_api_key: str = ""
    zhipu_embedding_api_base: str = "https://open.bigmodel.cn/api/paas/v4"
    zhipu_embedding_model: str = "embedding-2"
    sparse_embedding_model: str = "Qdrant/bm25"
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
    log_level: str = "INFO"
    json_logs: bool = True
    otel_enabled: bool = False
    otel_service_name: str = "interview-agent"
    otel_exporter_otlp_endpoint: str = ""
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
        secret_pairs = (
            ("zhipu_api_key", "zhipu_api_key_file"),
            ("zhipu_embedding_api_key", "zhipu_embedding_api_key_file"),
            ("web_search_api_key", "web_search_api_key_file"),
            ("app_api_key", "app_api_key_file"),
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
    return Settings()
