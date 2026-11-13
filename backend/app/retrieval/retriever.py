"""Tag-aware 混合检索。

  query ──► 向量化 ──► 匹配标签 T(q)（关键词 + 向量，零 LLM 调用）
                     │
     ┌───────────────┼────────────────┐
  稠密召回          BM25 召回        标签召回（命中 T(q) 及其后代的 chunk，按语义排序）
     └───────────────┼────────────────┘
                RRF 融合（加权）
                     │
          标签加权：+ boost × max(层级衰减 × 置信度)
                     │
             MMR 去冗余 ──► Top-K ──► token 预算内组装上下文

与旧版 T-CUS 的区别：
- 标签是「软信号」（独立召回通道 + 加权），不会因为标签打错导致整段召回为 0；
- 「硬过滤」只用于用户显式选择的维度（如 部门=财务），并自动包含子标签；
- ACL 在召回前过滤，无权限的内容永远不会进入 LLM 上下文。
"""
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np
from sqlalchemy.orm import Session

from ..config import get_settings
from ..providers.embeddings import get_embedder
from ..tagging.tagger import TagHit, match_query_tags
from ..tagging.taxonomy import TagIndex, load_tag_index
from ..text import tokenize
from .index import KBIndex, get_kb_index


@dataclass
class RetrievedChunk:
    chunk_id: int
    document_id: int
    filename: str
    heading_path: str
    text: str
    token_count: int
    score: float
    dense: float
    sparse_rank: Optional[int]
    dense_rank: Optional[int]
    tag_score: float
    matched_tags: List[str]
    tags: List[str]


@dataclass
class RetrievalResult:
    query: str
    query_tags: List[dict]
    chunks: List[RetrievedChunk]
    candidates: int
    timings_ms: Dict[str, float] = field(default_factory=dict)


@dataclass
class RetrievalOptions:
    top_k: Optional[int] = None
    filter_tag_ids: Sequence[int] = ()      # 硬过滤（含后代），同一维度内为 OR、不同维度间为 AND
    use_tags: bool = True                    # 关闭则退化为纯混合检索（用于 A/B 评测）
    use_sparse: bool = True
    use_dense: bool = True
    use_mmr: bool = True


def _allowed_mask(index: KBIndex, tag_index: TagIndex, user_groups: Optional[Sequence[str]],
                  filter_tag_ids: Sequence[int]) -> np.ndarray:
    mask = np.ones(index.size, dtype=bool)
    if user_groups is not None:
        groups = set(user_groups)
        for i, m in enumerate(index.metas):
            if m.acl and not (m.acl & groups):
                mask[i] = False
    if filter_tag_ids:
        by_facet: Dict[str, set] = {}
        for tid in filter_tag_ids:
            t = tag_index.by_id.get(tid)
            facet = t.facet if t else "_"
            by_facet.setdefault(facet, set()).update(tag_index.expand([tid]))
        for tag_set in by_facet.values():
            facet_mask = np.zeros(index.size, dtype=bool)
            for tid in tag_set:
                rows = index.tag_postings.get(tid)
                if rows is not None:
                    facet_mask[rows] = True
            mask &= facet_mask
    return mask


def _rank(scores: np.ndarray, mask: np.ndarray, k: int, min_score: float = -np.inf) -> List[int]:
    cand = np.where(mask & (scores > min_score))[0]
    if cand.size == 0:
        return []
    k = min(k, cand.size)
    top = cand[np.argpartition(-scores[cand], k - 1)[:k]]
    return top[np.argsort(-scores[top])].tolist()


def _tag_affinity(query_tags: List[TagHit], chunk_tags: Dict[int, float], tag_index: TagIndex,
                  decay: float) -> tuple:
    best, matched = 0.0, []
    for qt in query_tags:
        for ct, conf in chunk_tags.items():
            d = tag_index.distance(qt.tag_id, ct)
            if d is None:
                continue
            s = qt.confidence * conf * (decay ** d)
            if s > 0.05 and ct in tag_index.by_id:
                matched.append(tag_index.by_id[ct].name)
            best = max(best, s)
    return min(best, 1.0), sorted(set(matched))


def _mmr(cands: List[int], rel: Dict[int, float], matrix: np.ndarray, k: int, lam: float) -> List[int]:
    if len(cands) <= 1:
        return cands[:k]
    vecs = matrix[cands]
    sim = vecs @ vecs.T
    chosen: List[int] = []
    remaining = list(range(len(cands)))
    while remaining and len(chosen) < k:
        best_j, best_v = None, -1e9
        for j in remaining:
            redundancy = max((sim[j, c] for c in chosen), default=0.0)
            v = lam * rel[cands[j]] - (1 - lam) * redundancy
            if v > best_v:
                best_j, best_v = j, v
        chosen.append(best_j)
        remaining.remove(best_j)
    return [cands[j] for j in chosen]


def retrieve(db: Session, kb_id: int, query: str, user_groups: Optional[Sequence[str]] = None,
             opts: Optional[RetrievalOptions] = None) -> RetrievalResult:
    s = get_settings()
    opts = opts or RetrievalOptions()
    top_k = opts.top_k or s.final_top_k
    t0 = time.perf_counter()
    timings: Dict[str, float] = {}

    index = get_kb_index(db, kb_id)
    tag_index = load_tag_index(db, kb_id)
    qvec = get_embedder().embed_one(query, "query")
    timings["embed"] = (time.perf_counter() - t0) * 1000

    query_tags = match_query_tags(query, qvec, tag_index) if opts.use_tags else []
    query_tags_out = [{"id": h.tag_id, "name": tag_index.by_id[h.tag_id].name,
                       "facet": tag_index.by_id[h.tag_id].facet, "confidence": h.confidence, "via": h.source}
                      for h in query_tags]
    if index.size == 0:
        return RetrievalResult(query, query_tags_out, [], 0, timings)

    mask = _allowed_mask(index, tag_index, user_groups, opts.filter_tag_ids)
    dense = index.matrix @ qvec

    # ---- 三路召回 ----
    t1 = time.perf_counter()
    channels: List[tuple] = []  # (ranked rows, weight)
    dense_ranked = _rank(dense, mask, s.dense_top_k) if opts.use_dense else []
    if dense_ranked:
        channels.append((dense_ranked, 1.0))
    sparse_ranked: List[int] = []
    if opts.use_sparse and index.bm25 is not None:
        sparse_ranked = _rank(index.bm25.scores(tokenize(query)), mask, s.sparse_top_k, min_score=0.0)
        if sparse_ranked:
            channels.append((sparse_ranked, 1.0))
    if query_tags:
        tag_rows = np.zeros(index.size, dtype=bool)
        for qt in query_tags:
            for tid in tag_index.expand([qt.tag_id]):
                rows = index.tag_postings.get(tid)
                if rows is not None:
                    tag_rows[rows] = True
        tag_ranked = _rank(dense, mask & tag_rows, s.dense_top_k)
        if tag_ranked:
            channels.append((tag_ranked, 0.8))
    timings["recall"] = (time.perf_counter() - t1) * 1000

    # ---- RRF 融合 ----
    rrf: Dict[int, float] = {}
    for ranked, w in channels:
        for r, row in enumerate(ranked):
            rrf[row] = rrf.get(row, 0.0) + w / (s.rrf_k + r + 1)
    if not rrf:
        return RetrievalResult(query, query_tags_out, [], 0, timings)
    max_rrf = sum(w for _, w in channels) / (s.rrf_k + 1)
    dense_pos = {row: i for i, row in enumerate(dense_ranked)}
    sparse_pos = {row: i for i, row in enumerate(sparse_ranked)}

    # ---- 标签加权 ----
    final: Dict[int, float] = {}
    tag_info: Dict[int, tuple] = {}
    for row, v in rrf.items():
        rel = v / max_rrf
        aff, matched = (_tag_affinity(query_tags, index.metas[row].tags, tag_index, s.hierarchy_decay)
                        if query_tags else (0.0, []))
        tag_info[row] = (aff, matched)
        final[row] = rel + s.tag_boost * aff
    ordered = sorted(final, key=lambda r: -final[r])
    ordered = [r for r in ordered if final[r] >= s.min_relevance]

    # ---- MMR 去冗余 ----
    pool = ordered[: max(top_k * 4, 20)]
    picked = _mmr(pool, final, index.matrix, top_k, s.mmr_lambda) if opts.use_mmr else pool[:top_k]
    timings["total"] = (time.perf_counter() - t0) * 1000

    out = []
    for row in picked:
        m = index.metas[row]
        aff, matched = tag_info[row]
        out.append(RetrievedChunk(
            chunk_id=m.chunk_id, document_id=m.document_id, filename=m.filename, heading_path=m.heading_path,
            text=m.text, token_count=m.token_count, score=round(final[row], 4), dense=round(float(dense[row]), 4),
            sparse_rank=sparse_pos.get(row), dense_rank=dense_pos.get(row), tag_score=round(aff, 4),
            matched_tags=matched,
            tags=[tag_index.by_id[t].name for t in m.tags if t in tag_index.by_id],
        ))
    return RetrievalResult(query, query_tags_out, out, len(rrf), timings)


def assess_sufficiency(chunks: List[RetrievedChunk]) -> str:
    """根拠充分度（启发式，供 Agent 决定继续 / 停止 / 移交）：
    sufficient: 最相关片段同时被语义与关键词召回靠前，或命中查询标签且至少一路靠前
    weak: 有结果但信号不一致，Agent 应谨慎表述或补充检索
    none: 没有任何可用根拠，Agent 不应作答
    阈值需用评测集校准。"""
    if not chunks:
        return "none"
    top = chunks[0]
    dense_top = top.dense_rank is not None and top.dense_rank < 3
    sparse_top = top.sparse_rank is not None and top.sparse_rank < 3
    if (dense_top and sparse_top) or (top.tag_score >= 0.5 and (dense_top or sparse_top)):
        return "sufficient"
    return "weak"


def assemble_context(chunks: List[RetrievedChunk], budget: int) -> List[RetrievedChunk]:
    """按相关性顺序在 token 预算内选取片段（不再按「分数/长度」密度排序——那会偏爱碎片）。"""
    out, used = [], 0
    for c in chunks:
        if used + c.token_count > budget and out:
            continue
        out.append(c)
        used += c.token_count
    return out
