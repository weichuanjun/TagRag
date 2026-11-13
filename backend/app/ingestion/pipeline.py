"""入库流水线：解析 -> 结构化切块 -> 向量化 -> chunk 级打标 -> 聚合文档标签 -> 索引失效。

设计为同步函数，由后台线程执行；LLM 打标部分内部用 asyncio 运行。
"""
import asyncio
import logging
from collections import Counter
from typing import List

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import SessionLocal
from ..models import Chunk, ChunkTag, DocStatus, Document, DocumentTag
from ..providers.embeddings import from_bytes, get_embedder, to_bytes
from ..tagging.tagger import tag_texts
from ..tagging.taxonomy import bump_version, load_tag_index
from .chunker import chunk_blocks
from .parsers import parse_file

logger = logging.getLogger(__name__)


def _embed_text(c: Chunk) -> str:
    return f"{c.heading_path}\n{c.text}" if c.heading_path else c.text


def ingest_document(document_id: int) -> None:
    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if doc is None:
            return
        doc.status, doc.error = DocStatus.PROCESSING, None
        db.commit()
        try:
            _ingest(db, doc)
            doc.status = DocStatus.READY
        except Exception as e:
            logger.exception("文档 %s 入库失败", document_id)
            db.rollback()
            doc = db.get(Document, document_id)
            doc.status, doc.error = DocStatus.FAILED, f"{type(e).__name__}: {e}"[:2000]
        db.commit()
        bump_version(doc.kb_id)
    finally:
        db.close()


def _ingest(db: Session, doc: Document) -> None:
    s = get_settings()
    blocks = parse_file(doc.file_path, doc.filename)
    drafts = chunk_blocks(blocks, s.chunk_tokens, s.chunk_overlap_tokens)
    if not drafts:
        raise ValueError("文档中没有可提取的文本内容（扫描件 PDF 需先 OCR）")

    db.execute(delete(Chunk).where(Chunk.document_id == doc.id))
    vectors = get_embedder().embed([d.embed_text for d in drafts])
    chunks: List[Chunk] = []
    for i, (d, v) in enumerate(zip(drafts, vectors)):
        c = Chunk(document_id=doc.id, kb_id=doc.kb_id, ordinal=i, text=d.text,
                  heading_path=d.heading_path, token_count=d.token_count, embedding=to_bytes(v))
        db.add(c)
        chunks.append(c)
    db.flush()
    doc.chunk_count = len(chunks)
    if drafts and drafts[0].page is not None:
        doc.meta = {**(doc.meta or {}), "pages": max(d.page or 0 for d in drafts)}
    _tag_chunks(db, doc, chunks, vectors)


def _tag_chunks(db: Session, doc: Document, chunks: List[Chunk], vectors: np.ndarray) -> None:
    index = load_tag_index(db, doc.kb_id)
    hits = asyncio.run(tag_texts(db, doc.kb_id, index, [_embed_text(c) for c in chunks], vectors))

    manual = [dt.tag_id for dt in doc.doc_tags if dt.source == "manual"]
    counter: Counter = Counter()
    for c, chunk_hits in zip(chunks, hits):
        seen = set()
        for h in chunk_hits:
            db.add(ChunkTag(chunk_id=c.id, tag_id=h.tag_id, confidence=h.confidence, source=h.source))
            seen.add(h.tag_id)
            counter[h.tag_id] += 1
        for tid in manual:  # 人工给文档打的标签（如部门、密级）继承到所有 chunk
            if tid not in seen:
                db.add(ChunkTag(chunk_id=c.id, tag_id=tid, confidence=1.0, source="inherited"))

    # 文档级派生标签：覆盖至少 20% 的 chunk 或出现 >=3 次
    db.execute(delete(DocumentTag).where(DocumentTag.document_id == doc.id, DocumentTag.source == "derived"))
    threshold = max(1, min(3, int(len(chunks) * 0.2)))
    for tid, cnt in counter.most_common(10):
        if cnt >= threshold and tid not in manual:
            db.add(DocumentTag(document_id=doc.id, tag_id=tid, source="derived"))


def retag_document(db: Session, doc: Document) -> None:
    """标签体系变化后，对已有 chunk 重新打标（不重新解析/向量化）。"""
    chunks = list(db.scalars(select(Chunk).where(Chunk.document_id == doc.id).order_by(Chunk.ordinal)))
    if not chunks:
        return
    db.execute(delete(ChunkTag).where(ChunkTag.chunk_id.in_([c.id for c in chunks])))
    vectors = np.vstack([from_bytes(c.embedding) for c in chunks])
    _tag_chunks(db, doc, chunks, vectors)


def retag_knowledge_base(kb_id: int) -> None:
    db = SessionLocal()
    try:
        docs = db.scalars(select(Document).where(Document.kb_id == kb_id,
                                                 Document.status == DocStatus.READY)).all()
        for doc in docs:
            try:
                retag_document(db, doc)
                db.commit()
            except Exception:
                logger.exception("重新打标失败 doc=%s", doc.id)
                db.rollback()
        bump_version(kb_id)
    finally:
        db.close()
