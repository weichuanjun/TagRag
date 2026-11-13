"""集中配置：全部通过环境变量（或 .env）覆盖。"""
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="TAGRAG_", extra="ignore")

    # ---- 存储 ----
    data_dir: str = "./data"
    database_url: Optional[str] = None  # 默认 sqlite:///{data_dir}/tagrag.db；生产建议 PostgreSQL

    # ---- 安全 ----
    # 逗号分隔的 API Key；为空则不校验（仅限本地开发）
    api_keys: str = ""
    cors_origins: str = "*"
    max_upload_mb: int = 50

    # ---- LLM ----
    llm_provider: str = "claude"              # claude（默认，Anthropic 官方 SDK）/ openai（OpenAI 兼容服务）
    # Claude：凭证默认读 ANTHROPIC_API_KEY（或 `ant auth login`），也可用 TAGRAG_ANTHROPIC_API_KEY
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""
    claude_model: str = "claude-opus-5-5"
    claude_effort: str = "medium"             # 作答的思考深度：low / medium / high / xhigh / max
    tagging_effort: str = "low"               # 打标是分类任务，用 low 即可
    # OpenAI 兼容（llm_provider=openai 时使用：OpenAI / Azure / DeepSeek / 通义 / vLLM / Ollama）
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.1
    llm_timeout: float = 60.0

    # ---- Embedding ----
    # Claude 没有 embedding 接口，Anthropic 推荐 Voyage AI：
    # voyage: Voyage AI（需 TAGRAG_EMBEDDING_API_KEY）; openai: OpenAI 兼容 /embeddings;
    # local: sentence-transformers（如 BAAI/bge-m3，日中英皆可）; hash: 离线/测试用
    embedding_provider: str = "hash"
    embedding_base_url: Optional[str] = None  # 默认复用 llm_base_url
    embedding_api_key: Optional[str] = None   # 默认复用 llm_api_key
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 512                  # 仅 hash 模式使用
    embedding_batch_size: int = 64

    # ---- 切块 ----
    chunk_tokens: int = 450
    chunk_overlap_tokens: int = 60

    # ---- 打标 ----
    tagging_mode: str = "auto"  # auto: 有 LLM 用 LLM，否则用 embedding+关键词; llm; embedding
    tagging_batch_size: int = 6
    tag_embedding_threshold: float = 0.45     # embedding 打标阈值
    max_tags_per_chunk: int = 5
    # 候选标签被多少个 chunk 提到后自动转正（0 = 永不自动转正，必须人工审核）
    candidate_auto_promote: int = 0

    # ---- 检索 ----
    dense_top_k: int = 50
    sparse_top_k: int = 50
    rrf_k: int = 60
    query_tag_threshold: float = 0.5          # 查询->标签 匹配阈值
    max_query_tags: int = 5
    tag_boost: float = 0.35                   # 标签加权强度 (0 = 关闭)
    hierarchy_decay: float = 0.5              # 父/子标签每跨一层的衰减
    mmr_lambda: float = 0.75
    final_top_k: int = 8
    context_token_budget: int = 3000
    min_relevance: float = 0.0                # 融合分数低于此值的片段丢弃

    @property
    def resolved_database_url(self) -> str:
        return self.database_url or f"sqlite:///{self.data_dir}/tagrag.db"


    @property
    def api_key_set(self) -> set:
        return {k.strip() for k in self.api_keys.split(",") if k.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
