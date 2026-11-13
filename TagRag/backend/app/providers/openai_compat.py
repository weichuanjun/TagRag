"""OpenAI 兼容 Chat Completions（DeepSeek、通义、vLLM、Ollama 等），作为 Claude 之外的备选。"""
import json
import logging
from typing import AsyncIterator, List, Optional

import httpx

from ..config import get_settings
from .base import LLMUnavailable, parse_json

logger = logging.getLogger(__name__)


class OpenAICompatLLM:
    def __init__(self):
        s = get_settings()
        self.base_url = s.llm_base_url.rstrip("/")
        self.api_key = s.llm_api_key
        self.model = s.llm_model
        self.temperature = s.llm_temperature
        self.timeout = s.llm_timeout
        self.name = f"openai-compat:{self.model}"

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _payload(self, system: str, messages: List[dict], stream: bool, json_mode: bool, temperature: float):
        p = {"model": self.model, "messages": [{"role": "system", "content": system}] + messages,
             "temperature": temperature, "stream": stream}
        if json_mode:
            p["response_format"] = {"type": "json_object"}
        return p

    async def _post(self, payload: dict) -> str:
        if not self.enabled:
            raise LLMUnavailable("未配置 TAGRAG_LLM_API_KEY")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            headers = {"Authorization": f"Bearer {self.api_key}"}
            resp = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            if resp.status_code == 400 and "response_format" in payload:
                payload = {k: v for k, v in payload.items() if k != "response_format"}
                resp = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"] or ""

    async def chat(self, system: str, messages: List[dict], effort: Optional[str] = None) -> str:
        return await self._post(self._payload(system, messages, False, False, self.temperature))

    async def chat_json(self, system: str, messages: List[dict], schema: dict,
                        effort: Optional[str] = None) -> dict:
        system = f"{system}\n\n只输出符合以下 JSON Schema 的 JSON：\n{json.dumps(schema, ensure_ascii=False)}"
        return parse_json(await self._post(self._payload(system, messages, False, True, 0)))

    async def stream(self, system: str, messages: List[dict], effort: Optional[str] = None) -> AsyncIterator[str]:
        if not self.enabled:
            raise LLMUnavailable("未配置 TAGRAG_LLM_API_KEY")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            async with client.stream(
                "POST", f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=self._payload(system, messages, True, False, self.temperature),
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
