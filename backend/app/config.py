from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),  # works from backend/ and from project root
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = ""  # loaded from env at runtime; default silences mypy
    tavily_api_key: str = ""    # optional — research_node skips gracefully when absent

    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "medium_agent_factory"

    environment: str = "development"
    log_level: str = "INFO"

    langchain_tracing_v2: bool = False
    langchain_api_key: str = ""
    langchain_project: str = "medium-agent-factory"

    # Claude model — supervisor uses Sonnet, workers use Haiku for cost
    supervisor_model: str = "claude-sonnet-4-6"
    worker_model: str = "claude-haiku-4-5-20251001"

    # Local LLM via Ollama — set USE_LOCAL_LLM=true to skip Anthropic entirely
    use_local_llm: bool = False
    local_llm_model: str = "llama3.2"
    local_llm_base_url: str = "http://ollama:11434"

    # DeepSeek — set USE_DEEPSEEK=true + DEEPSEEK_API_KEY for cheap cloud inference
    use_deepseek: bool = False
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"  # deepseek-chat = V3, deepseek-reasoner = R1

    # Quality gates — three independent checks, all must pass to approve
    min_quality_score: float = 0.90      # overall earnings-potential score
    min_read_ratio: float = 0.65         # predicted 30-sec read rate (65% = Medium "Strong")
    block_high_ai_patterns: bool = True  # any HIGH-severity AI pattern issue blocks the post
    max_revision_cycles: int = 2


settings = Settings()
