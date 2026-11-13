"""按配置选择 LLM 提供方（默认 Claude）。"""
from ..config import get_settings
from .base import LLM, LLMRefused, LLMUnavailable, parse_json  # noqa: F401


def get_llm() -> LLM:
    provider = get_settings().llm_provider
    if provider == "claude":
        from .claude import ClaudeLLM
        return ClaudeLLM()
    if provider == "openai":
        from .openai_compat import OpenAICompatLLM
        return OpenAICompatLLM()
    raise ValueError(f"未知 llm_provider: {provider}（可选 claude / openai）")
