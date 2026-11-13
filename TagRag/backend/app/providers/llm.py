"""LLM 客户端（OpenAI 兼容 Chat Completions），支持流式输出与 JSON 解析。"""
import json
import logging
import re
from typing import AsyncIterator, List, Optional

import httpx

from ..config import get_settings

logger = logging.getLogger(__name__)


class LLMUnavailable(RuntimeError):
    pass


class LLMClient:
    def __init__(self):
        s = get_settings()
        self.base_url = s.llm_base_url.rstrip("/")
        self.api_key = s.llm_api_key
        self.model = s.llm_model
        self.temperature = s.llm_temperature
        self.timeout = s.llm_timeout

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _payload(self, messages: List[dict], stream: bool, json_mode: bool, temperature: Optional[float]):
        p = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "stream": stream,
        }
        if json_mode:
            p["response_format"] = {"type": "json_object"}
        return p

    async def chat(self, messages: List[dict], json_mode: bool = False,
                   temperature: Optional[float] = None) -> str:
        if not self.enabled:
            raise LLMUnavailable("未配置 TAGRAG_LLM_API_KEY")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=self._payload(messages, False, json_mode, temperature),
            )
            if resp.status_code == 400 and json_mode:
                # 部分兼容服务不支持 response_format，降级重试
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=self._payload(messages, False, False, temperature),
                )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"] or ""

    async def stream(self, messages: List[dict]) -> AsyncIterator[str]:
        if not self.enabled:
            raise LLMUnavailable("未配置 TAGRAG_LLM_API_KEY")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST", f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=self._payload(messages, True, False, None),
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        delta = json.loads(data)["choices"][0].get("delta", {}).get("content")
                    except (ValueError, KeyError, IndexError):
                        continue
                    if delta:
                        yield delta

    async def chat_json(self, messages: List[dict]):
        raw = await self.chat(messages, json_mode=True, temperature=0)
        return parse_json(raw)


def parse_json(raw: str):
    raw = raw.strip()
    m = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if m:
        raw = m.group(1).strip()
    try:
        return json.loads(raw)
    except ValueError:
        m = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", raw)
        if m:
            return json.loads(m.group(1))
        raise


def get_llm() -> LLMClient:
    return LLMClient()
