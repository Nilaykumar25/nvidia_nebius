from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    neo4j_uri: str = "neo4j+s://localhost"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"

    github_token: str = ""
    repo_owner: str = "redis"
    repo_name: str = "redis"
    repo_local_path: str = "data/repo"
    subsystem_paths: str = "src/replication.c,src/rdb.c,src/aof.c,redis.conf"
    max_prs: int = 400
    max_commits: int = 3000

    # ── LLM (OpenAI-compatible — Nebius Token Factory / Nemotron) ────────────
    # Set these from your Nebius dashboard. Never hardcode values here.
    llm_base_url: str = ""           # e.g. https://api.studio.nebius.ai/v1
    llm_api_key: str = ""            # Nebius Token Factory API key
    llm_model: str = ""              # e.g. nvidia/Llama-3_1-Nemotron-Ultra-253B-v1
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 3

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384

    cache_dir: str = "data/cache"
    max_graph_hops: int = 3
    refusal_threshold: float = 0.35
    allowed_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def paths(self) -> list[str]:
        return [p.strip() for p in self.subsystem_paths.split(",") if p.strip()]


settings = Settings()
