"""应用配置 - pydantic-settings，对应 Java application.yml。

字段一一对应 application.yml:64-101，从 .env 读取。LLM_API_KEY 默认空串，
P0 骨架无 LLM 调用可空启动；P2 起未配置将调用失败（明确报错）。
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_nested_delimiter="__", extra="ignore")

    # Web
    app_name: str = "codeaware"

    # PostgreSQL + pgvector（Python 版默认独立库 ai_center_py，与 Java ai_center 共存）
    pg_host: str = "localhost"
    pg_port: int = 5433
    pg_user: str = "aicenter"
    pg_password: str = "aicenter123"
    pg_db: str = "ai_center_py"

    # Redis（对应 application.yml:24-33）
    redis_host: str = "localhost"
    redis_port: int = 6380

    # LLM: DeepSeek（OpenAI 兼容，对应 application.yml:64-71）
    llm_api_key: str = ""
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_model: str = "deepseek-v4-flash"
    llm_temperature: float = 0.1
    llm_max_tokens: int = 4096

    # Embedding: Ollama bge-m3（对应 application.yml:73-76）
    ollama_base_url: str = "http://localhost:11434"
    ollama_embedding_model: str = "bge-m3"

    # 记忆（对应 application.yml:86-93）
    mem_window_size: int = 20
    mem_summary_threshold: int = 10

    # RAG（对应 application.yml:95-101）
    rag_chunk_size: int = 500
    rag_chunk_overlap: int = 50
    rag_bm25_weight: float = 0.3
    rag_vector_weight: float = 0.7

    @property
    def pg_url_async(self) -> str:
        return (
            f"postgresql+asyncpg://{self.pg_user}:{self.pg_password}"
            f"@{self.pg_host}:{self.pg_port}/{self.pg_db}"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"


settings = Settings()
