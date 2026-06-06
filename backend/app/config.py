from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str
    tavily_api_key: str = ""

    medium_access_token: str = ""
    medium_user_email: str = ""
    medium_user_password: str = ""

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

    # Quality gate: min read-ratio score (0-1) before allowing publish
    min_quality_score: float = 0.75
    max_revision_cycles: int = 2


settings = Settings()
