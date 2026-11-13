"""Chunk 级打标 + 查询标签匹配。

入库打标（三路合并，取置信度最高的若干个）：
  1. 关键词：标签名/别名出现在 chunk 中             -> 高置信，可解释
  2. 向量：chunk 向量与标签向量相似度超过阈值         -> 召回同义表达
  3. LLM：在受控词表里做多标签分类（批量），并可提议新候选标签
查询阶段：只做「匹配」（关键词 + 向量），不调用 LLM、不新建标签 —— 快、稳定、可控。
"""
import logging
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np
from sqlalchemy.orm import Session

from ..config import get_settings
from ..providers.llm import LLMClient, get_llm
from ..text import tokenize
from .taxonomy import TagIndex, propose_candidate

logger = logging.getLogger(__name__)


@dataclass
class TagHit:
    tag_id: int
    confidence: float
    source: str


def keyword_hits(text: str, index: TagIndex) -> Dict[int, float]:
    low = text.lower()
    hits: Dict[int, float] = {}
    for key, tag_id in index.name_lookup.items():
        if len(key) >= 2 and key in low:
            # 名称越长越具体，置信度越高
            hits[tag_id] = max(hits.get(tag_id, 0), min(1.0, 0.8 + 0.04 * len(key)))
    return hits


def embedding_hits(vec: np.ndarray, index: TagIndex, threshold: float) -> Dict[int, float]:
    if index.matrix is None:
        return {}
    sims = index.matrix @ vec
    return {index.tags[i].id: float(sims[i]) for i in np.where(sims >= threshold)[0]}


def _merge(*sources: Sequence[tuple], limit: int) -> List[TagHit]:
    best: Dict[int, TagHit] = {}
    for hits, src in sources:
        for tid, conf in hits.items():
            if tid not in best or conf > best[tid].confidence:
                best[tid] = TagHit(tid, round(float(conf), 4), src)
    return sorted(best.values(), key=lambda h: -h.confidence)[:limit]


_LLM_TAGGING_PROMPT = """你是企业知识库的标签分类器。请为每个文本片段，从【标签体系】中选择最贴切的标签（多标签，0~{max_tags}个）。
要求：
- 只选择真正描述片段主题/对象的标签，不要牵强附会；
- 优先选择最具体（层级最深）的标签；
- 若片段包含标签体系中没有、但对检索很重要的主题，可在 new_tags 里提议（每片段最多2个，名称简短、通用、可复用，不要整句话）。

【标签体系】（格式：维度 / 标签名：说明）
{taxonomy}

【文本片段】
{chunks}

只输出 JSON：{{"results": [{{"i": 片段编号, "tags": ["标签名", ...], "new_tags": [{{"name": "...", "facet": "维度"}}]}}]}}"""


def _taxonomy_prompt(index: TagIndex) -> str:
    lines = []
    for t in sorted(index.tags, key=lambda t: (t.facet, t.name)):
        path = [t.name]
        p = index.parent.get(t.id)
        while p is not None and p in index.by_id and len(path) < 4:
            path.insert(0, index.by_id[p].name)
            p = index.parent.get(p)
        desc = f"：{t.description}" if t.description else ""
        lines.append(f"- {t.facet} / {' > '.join(path)}{desc}")
    return "\n".join(lines) or "（暂无，可通过 new_tags 提议）"


async def llm_tag_batch(llm: LLMClient, db: Session, kb_id: int, index: TagIndex,
                        texts: List[str]) -> List[Dict[int, float]]:
    s = get_settings()
    chunks = "\n\n".join(f"[{i}] {t[:1200]}" for i, t in enumerate(texts))
    prompt = _LLM_TAGGING_PROMPT.format(max_tags=s.max_tags_per_chunk,
                                        taxonomy=_taxonomy_prompt(index), chunks=chunks)
    data = await llm.chat_json([{"role": "user", "content": prompt}])
    results: List[Dict[int, float]] = [dict() for _ in texts]
    for item in (data.get("results", []) if isinstance(data, dict) else []):
        try:
            i = int(item.get("i"))
        except (TypeError, ValueError):
            continue
        if not 0 <= i < len(texts):
            continue
        for name in item.get("tags", []) or []:
            tid = index.resolve(str(name))
            if tid is not None:
                results[i][tid] = 0.95
        for nt in (item.get("new_tags", []) or [])[:2]:
            if isinstance(nt, dict) and nt.get("name"):
                propose_candidate(db, kb_id, str(nt["name"]), str(nt.get("facet") or "topic"))
    return results


async def tag_texts(db: Session, kb_id: int, index: TagIndex, texts: List[str],
                    vectors: np.ndarray) -> List[List[TagHit]]:
    """为一批 chunk 打标，返回每个 chunk 的标签命中列表。"""
    s = get_settings()
    llm = get_llm()
    use_llm = s.tagging_mode == "llm" or (s.tagging_mode == "auto" and llm.enabled)
    llm_results: List[Dict[int, float]] = [dict() for _ in texts]
    if use_llm:
        for start in range(0, len(texts), s.tagging_batch_size):
            batch = texts[start:start + s.tagging_batch_size]
            try:
                res = await llm_tag_batch(llm, db, kb_id, index, batch)
                llm_results[start:start + len(batch)] = res
            except Exception as e:  # LLM 失败不阻断入库，降级到向量+关键词
                logger.warning("LLM 打标失败，降级: %s", e)
                use_llm = False
                break
    out = []
    for i, text in enumerate(texts):
        kw = keyword_hits(text, index)
        emb = {} if use_llm else embedding_hits(vectors[i], index, s.tag_embedding_threshold)
        out.append(_merge((llm_results[i], "llm"), (kw, "keyword"), (emb, "embedding"),
                          limit=s.max_tags_per_chunk))
    return out


def match_query_tags(query: str, query_vec: np.ndarray, index: TagIndex) -> List[TagHit]:
    s = get_settings()
    kw = keyword_hits(query, index)
    emb = embedding_hits(query_vec, index, s.query_tag_threshold)
    return _merge((kw, "keyword"), (emb, "embedding"), limit=s.max_query_tags)


# ---------------------------------------------------------------------------
# 冷启动：从已有文档中建议标签体系
# ---------------------------------------------------------------------------
_SUGGEST_PROMPT = """你是企业知识管理专家。以下是某知识库中抽样的文本片段。请为它设计一套用于检索过滤的标签体系。
要求：
- 2~4 个维度（facet），例如 topic(主题)、product(产品/系统)、department(部门)、doc_type(文档类型)；
- 每个维度下 3~12 个标签，可有一层父子关系；标签名简短、互斥、可复用；
- 每个标签给一句说明，以及常见同义词（aliases）。

【样本】
{samples}

只输出 JSON：{{"tags": [{{"name": "...", "facet": "...", "parent": "父标签名或null", "description": "...", "aliases": ["..."]}}]}}"""


async def suggest_taxonomy(samples: List[str], top_keywords: int = 20) -> List[dict]:
    llm = get_llm()
    if llm.enabled:
        text = "\n---\n".join(s[:600] for s in samples[:30])
        data = await llm.chat_json([{"role": "user", "content": _SUGGEST_PROMPT.format(samples=text)}])
        tags = data.get("tags", []) if isinstance(data, dict) else []
        return [t for t in tags if isinstance(t, dict) and t.get("name")]
    # 无 LLM：基于文档频率挑选高区分度的中文二元词/英文词
    df = Counter()
    for s in samples:
        df.update({t for t in tokenize(s) if len(t) >= 2 and not t.isdigit()})
    n = max(1, len(samples))
    ranked = [(t, c) for t, c in df.items() if 1 < c <= max(2, int(n * 0.6))]
    ranked.sort(key=lambda x: -x[1])
    return [{"name": t, "facet": "topic", "parent": None, "description": None, "aliases": []}
            for t, _ in ranked[:top_keywords]]


__all__ = ["TagHit", "tag_texts", "match_query_tags", "suggest_taxonomy"]
