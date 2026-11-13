"""知识库内存索引：稠密向量矩阵 + BM25 倒排 + chunk 标签/ACL 元数据。

- 由数据库构建，按知识库版本号自动失效重建（文档入库/删除/重打标都会递增版本）
- 规模参考：单机内存可支撑数十万 chunk 的暴力检索（numpy 矩阵乘，毫秒级）
- 更大规模时，实现同样接口替换为 pgvector / Milvus / Qdrant / Elasticsearch 即可
"""
import math
import threading
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Chunk, ChunkTag, DocStatus, Document, Tag, TagStatus
from ..providers.embeddings import from_bytes
from ..tagging.taxonomy import get_version
from ..text import tokenize


class BM25:
    def __init__(self, docs_tokens: List[List[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.n = len(docs_tokens)
        self.doc_len = np.array([len(t) for t in docs_tokens], dtype=np.float32)
        self.avgdl = float(self.doc_len.mean()) if self.n else 0.0
        self.postings: Dict[str, List[tuple]] = defaultdict(list)
        for i, toks in enumerate(docs_tokens):
            for term, tf in Counter(toks).items():
                self.postings[term].append((i, tf))
        self.idf = {t: math.log(1 + (self.n - len(p) + 0.5) / (len(p) + 0.5)) for t, p in self.postings.items()}

    def scores(self, query_tokens: List[str]) -> np.ndarray:
        out = np.zeros(self.n, dtype=np.float32)
        if not self.n:
            return out
        for term in set(query_tokens):
            postings = self.postings.get(term)
            if not postings:
                continue
            idf = self.idf[term]
            for i, tf in postings:
                denom = tf + self.k1 * (1 - self.b + self.b * self.doc_len[i] / (self.avgdl or 1))
                out[i] += idf * tf * (self.k1 + 1) / denom
        return out


@dataclass
class ChunkMeta:
    chunk_id: int
    document_id: int
    filename: str
    heading_path: str
    text: str
    token_count: int
    acl: Set[str]
    tags: Dict[int, float]  # tag_id -> confidence


@dataclass
class KBIndex:
    kb_id: int
    version: int
    metas: List[ChunkMeta] = field(default_factory=list)
    matrix: Optional[np.ndarray] = None
    bm25: Optional[BM25] = None
    tag_postings: Dict[int, np.ndarray] = field(default_factory=dict)  # tag_id -> chunk 行号

    @property
    def size(self) -> int:
        return len(self.metas)


_cache: Dict[int, KBIndex] = {}
_build_lock = threading.Lock()


def get_kb_index(db: Session, kb_id: int) -> KBIndex:
    version = get_version(kb_id)
    idx = _cache.get(kb_id)
    if idx is not None and idx.version == version:
        return idx
    with _build_lock:
        idx = _cache.get(kb_id)
        if idx is not None and idx.version == version:
            return idx
        idx = _build(db, kb_id, version)
        _cache[kb_id] = idx
        return idx


def _build(db: Session, kb_id: int, version: int) -> KBIndex:
    rows = db.execute(
        select(Chunk.id, Chunk.document_id, Chunk.heading_path, Chunk.text, Chunk.token_count, Chunk.embedding,
               Document.filename, Document.acl_groups)
        .join(Document, Document.id == Chunk.document_id)
        .where(Chunk.kb_id == kb_id, Document.status == DocStatus.READY)
        .order_by(Chunk.document_id, Chunk.ordinal)
    ).all()
    idx = KBIndex(kb_id=kb_id, version=version)
    if not rows:
        return idx
    tags_by_chunk: Dict[int, Dict[int, float]] = defaultdict(dict)
    for ct_chunk, ct_tag, conf in db.execute(
        select(ChunkTag.chunk_id, ChunkTag.tag_id, ChunkTag.confidence)
        .join(Tag, Tag.id == ChunkTag.tag_id)
        .where(Tag.kb_id == kb_id, Tag.status == TagStatus.ACTIVE)
    ).all():
        tags_by_chunk[ct_chunk][ct_tag] = conf
    vecs, toks = [], []
    postings: Dict[int, List[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        tags = tags_by_chunk.get(r.id, {})
        idx.metas.append(ChunkMeta(r.id, r.document_id, r.filename, r.heading_path or "", r.text,
                                   r.token_count or 0, set(r.acl_groups or []), tags))
        vecs.append(from_bytes(r.embedding))
        toks.append(tokenize(f"{r.heading_path or ''}\n{r.text}"))
        for t in tags:
            postings[t].append(i)
    dims = {v.shape[0] for v in vecs}
    if len(dims) != 1:
        raise RuntimeError("知识库中存在不同维度的向量，切换 embedding 模型后请对文档执行重新索引")
    idx.matrix = np.vstack(vecs)
    idx.bm25 = BM25(toks)
    idx.tag_postings = {t: np.array(v, dtype=np.int64) for t, v in postings.items()}
    return idx


def invalidate(kb_id: Optional[int] = None) -> None:
    if kb_id is None:
        _cache.clear()
    else:
        _cache.pop(kb_id, None)
