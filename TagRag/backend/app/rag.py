"""答案生成：带编号引用、基于证据作答、证据不足时明确拒答。"""
import re
from typing import AsyncIterator, List, Optional

from .providers.llm import get_llm
from .retrieval.retriever import RetrievedChunk

SYSTEM_PROMPT = """你是企业知识库问答助手。严格依据【参考资料】回答用户问题：
1. 只使用参考资料中的信息；资料不足以回答时，直接说明“知识库中没有找到相关信息”，并指出缺少什么，不要编造。
2. 每个事实性陈述后用方括号标注来源编号，例如 [1] 或 [2][3]。
3. 先给出直接结论，再分点说明细节；涉及数字、日期、流程步骤时保持原文准确。
4. 资料之间有冲突时，指出冲突并分别引用。
5. 使用与用户提问相同的语言作答。"""

NO_CONTEXT_ANSWER = "知识库中没有找到与该问题相关的信息。可以尝试换个说法，或确认相关文档已上传并完成处理。"


def format_sources(chunks: List[RetrievedChunk]) -> str:
    parts = []
    for i, c in enumerate(chunks, start=1):
        loc = f"{c.filename}" + (f" › {c.heading_path}" if c.heading_path else "")
        parts.append(f"[{i}] 来源：{loc}\n{c.text}")
    return "\n\n".join(parts)


def build_messages(query: str, chunks: List[RetrievedChunk],
                   history: Optional[List[dict]] = None) -> List[dict]:
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in (history or [])[-6:]:
        if h.get("role") in ("user", "assistant") and h.get("content"):
            msgs.append({"role": h["role"], "content": str(h["content"])[:2000]})
    msgs.append({"role": "user", "content": f"【参考资料】\n{format_sources(chunks)}\n\n【问题】\n{query}"})
    return msgs


def extractive_answer(chunks: List[RetrievedChunk]) -> str:
    """未配置 LLM 时的降级：直接返回最相关的原文片段。"""
    lines = ["（未配置大模型，以下为检索到的最相关原文）", ""]
    top = chunks[0].score
    for i, c in enumerate(chunks[:3], start=1):
        if i > 1 and c.score < top * 0.6:
            break
        snippet = re.sub(r"\s+", " ", c.text)[:300]
        lines.append(f"- {snippet} [{i}]")
    return "\n".join(lines)


async def generate_answer(query: str, chunks: List[RetrievedChunk], history=None) -> str:
    if not chunks:
        return NO_CONTEXT_ANSWER
    llm = get_llm()
    if not llm.enabled:
        return extractive_answer(chunks)
    return await llm.chat(build_messages(query, chunks, history))


async def stream_answer(query: str, chunks: List[RetrievedChunk], history=None) -> AsyncIterator[str]:
    if not chunks:
        yield NO_CONTEXT_ANSWER
        return
    llm = get_llm()
    if not llm.enabled:
        yield extractive_answer(chunks)
        return
    async for delta in llm.stream(build_messages(query, chunks, history)):
        yield delta


def cited_indices(answer: str, n: int) -> List[int]:
    return sorted({int(x) for x in re.findall(r"\[(\d+)\]", answer) if 1 <= int(x) <= n})
