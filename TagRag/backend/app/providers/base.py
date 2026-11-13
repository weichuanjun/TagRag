"""LLM 提供方的公共接口。

所有提供方都实现同一组方法，调用方不关心背后是 Claude 还是 OpenAI 兼容服务：
- chat(system, messages, effort)            -> str
- chat_json(system, messages, schema, effort) -> dict
- stream(system, messages, effort)          -> AsyncIterator[str]
messages 只含 user / assistant 两种角色；system 单独传入（便于 Claude 做提示缓存）。
"""
import json
import re
from typing import AsyncIterator, List, Optional, Protocol


class LLMUnavailable(RuntimeError):
    """未配置可用的大模型。"""


class LLMRefused(RuntimeError):
    """模型拒绝回答（安全策略），且兜底模型也未能回答。"""


class LLM(Protocol):
    name: str

    @property
    def enabled(self) -> bool: ...

    async def chat(self, system: str, messages: List[dict], effort: Optional[str] = None) -> str: ...

    async def chat_json(self, system: str, messages: List[dict], schema: dict,
                        effort: Optional[str] = None) -> dict: ...

    def stream(self, system: str, messages: List[dict], effort: Optional[str] = None) -> AsyncIterator[str]: ...


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
