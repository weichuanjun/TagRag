"""Claude（Anthropic 官方 SDK）。

- 默认模型 claude-opus-5-5；思考由模型自适应，深度用 effort 控制（打标 low，作答 medium）
- 开启服务端拒答兜底（fallbacks="default"）：被安全策略拒答时由服务端自动换模型重试
- 稳定的 system（指令 + 标签体系）带 cache_control，批量打标时命中提示缓存
- JSON 输出走结构化输出（output_config.format），保证可解析
- 凭证按 SDK 默认顺序解析：ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN / `ant auth login` 配置
"""
import json
import logging
import os
from typing import AsyncIterator, List, Optional

import anthropic

from ..config import get_settings
from .base import LLMRefused, LLMUnavailable

logger = logging.getLogger(__name__)

FALLBACK_BETA = "server-side-fallback-2026-07-01"


def _has_credentials(api_key: Optional[str]) -> bool:
    if api_key:
        return True
    return any(os.environ.get(k) for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"))


class ClaudeLLM:
    def __init__(self):
        s = get_settings()
        self.model = s.claude_model
        self.effort = s.claude_effort
        self.api_key = s.anthropic_api_key or None
        self.base_url = s.anthropic_base_url or None
        self.timeout = s.llm_timeout
        self.name = f"claude:{self.model}"
        self._client: Optional[anthropic.AsyncAnthropic] = None

    @property
    def enabled(self) -> bool:
        return _has_credentials(self.api_key)

    @property
    def client(self) -> anthropic.AsyncAnthropic:
        if not self.enabled:
            raise LLMUnavailable("未配置 Claude 凭证（ANTHROPIC_API_KEY 或 TAGRAG_ANTHROPIC_API_KEY）")
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(api_key=self.api_key, base_url=self.base_url,
                                                    timeout=self.timeout)
        return self._client

    def _params(self, system: str, messages: List[dict], effort: Optional[str], max_tokens: int,
                schema: Optional[dict] = None) -> dict:
        output_config: dict = {"effort": effort or self.effort}
        if schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        return {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": messages,
            "output_config": output_config,
            "betas": [FALLBACK_BETA],
            "fallbacks": "default",
        }

    @staticmethod
    def _text(message) -> str:
        if message.stop_reason == "refusal":
            category = getattr(message.stop_details, "category", None) if message.stop_details else None
            raise LLMRefused(f"Claude 拒绝回答（类别：{category}）")
        return "".join(b.text for b in message.content if b.type == "text")

    async def chat(self, system: str, messages: List[dict], effort: Optional[str] = None) -> str:
        msg = await self.client.beta.messages.create(**self._params(system, messages, effort, 16000))
        return self._text(msg)

    async def chat_json(self, system: str, messages: List[dict], schema: dict,
                        effort: Optional[str] = None) -> dict:
        msg = await self.client.beta.messages.create(**self._params(system, messages, effort, 16000, schema))
        return json.loads(self._text(msg))

    async def stream(self, system: str, messages: List[dict], effort: Optional[str] = None) -> AsyncIterator[str]:
        async with self.client.beta.messages.stream(**self._params(system, messages, effort, 64000)) as s:
            async for text in s.text_stream:
                yield text
            final = await s.get_final_message()
        if final.stop_reason == "refusal":
            raise LLMRefused("Claude 在生成过程中拒绝继续回答")
