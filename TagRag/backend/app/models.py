"""数据模型。

核心思想：标签是「按知识库治理的受控词表（taxonomy）」，而不是 LLM 随手生成的字符串。
- Tag 归属于某个知识库，带维度(facet)、层级(parent)、别名(aliases)、状态(active/candidate/deprecated)
- 标签打在 Chunk 级别（ChunkTag），带置信度和来源；文档级标签由 chunk 标签聚合 + 人工指定
- 查询阶段只「匹配」已有 active 标签，绝不新建标签
"""
import datetime as dt
from typing import List, Optional

from sqlalchemy import (JSON, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text,
                        UniqueConstraint)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, default=None)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    documents: Mapped[List["Document"]] = relationship(back_populates="kb", cascade="all, delete-orphan")
    tags: Mapped[List["Tag"]] = relationship(back_populates="kb", cascade="all, delete-orphan")


class TagStatus:
    ACTIVE = "active"          # 参与检索
    CANDIDATE = "candidate"    # LLM 提议的新标签，待审核，不参与检索
    DEPRECATED = "deprecated"  # 已废弃


class Tag(Base):
    __tablename__ = "tags"
    __table_args__ = (UniqueConstraint("kb_id", "name", name="uq_tag_kb_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    facet: Mapped[str] = mapped_column(String(50), default="topic")  # 维度：topic/product/department/doc_type...
    description: Mapped[Optional[str]] = mapped_column(Text, default=None)
    aliases: Mapped[list] = mapped_column(JSON, default=list)        # 同义词，用于匹配与合并
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tags.id", ondelete="SET NULL"), default=None)
    status: Mapped[str] = mapped_column(String(20), default=TagStatus.ACTIVE, index=True)
    mention_count: Mapped[int] = mapped_column(Integer, default=0)   # 候选标签被提议次数
    embedding: Mapped[Optional[bytes]] = mapped_column(LargeBinary, default=None)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)

    kb: Mapped[KnowledgeBase] = relationship(back_populates="tags")
    parent: Mapped[Optional["Tag"]] = relationship(remote_side="Tag.id")


class DocStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("kb_id", "content_hash", name="uq_doc_kb_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kb_id: Mapped[int] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(500))
    content_hash: Mapped[str] = mapped_column(String(64))
    file_path: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(20), default=DocStatus.PENDING, index=True)
    error: Mapped[Optional[str]] = mapped_column(Text, default=None)
    # 访问控制：空列表 = 知识库内公开；否则仅这些用户组可检索
    acl_groups: Mapped[list] = mapped_column(JSON, default=list)
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    kb: Mapped[KnowledgeBase] = relationship(back_populates="documents")
    chunks: Mapped[List["Chunk"]] = relationship(back_populates="document", cascade="all, delete-orphan",
                                                 order_by="Chunk.ordinal")
    doc_tags: Mapped[List["DocumentTag"]] = relationship(cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    kb_id: Mapped[int] = mapped_column(Integer, index=True)
    ordinal: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    heading_path: Mapped[str] = mapped_column(String(1000), default="")  # 例如 "报销制度 > 差旅 > 住宿标准"
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    embedding: Mapped[Optional[bytes]] = mapped_column(LargeBinary, default=None)

    document: Mapped[Document] = relationship(back_populates="chunks")
    chunk_tags: Mapped[List["ChunkTag"]] = relationship(cascade="all, delete-orphan")


class ChunkTag(Base):
    __tablename__ = "chunk_tags"

    chunk_id: Mapped[int] = mapped_column(ForeignKey("chunks.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    source: Mapped[str] = mapped_column(String(20), default="llm")  # llm / embedding / keyword / manual / inherited

    tag: Mapped[Tag] = relationship()


class DocumentTag(Base):
    __tablename__ = "document_tags"

    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True)
    source: Mapped[str] = mapped_column(String(20), default="derived")  # manual / derived

    tag: Mapped[Tag] = relationship()


class QueryLog(Base):
    """问答日志：用于审计、效果分析、收集反馈做评测集。"""
    __tablename__ = "query_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kb_id: Mapped[int] = mapped_column(Integer, index=True)
    user: Mapped[Optional[str]] = mapped_column(String(200), default=None)
    query: Mapped[str] = mapped_column(Text)
    matched_tags: Mapped[list] = mapped_column(JSON, default=list)
    sources: Mapped[list] = mapped_column(JSON, default=list)
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    answer: Mapped[Optional[str]] = mapped_column(Text, default=None)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    feedback: Mapped[Optional[int]] = mapped_column(Integer, default=None)  # 1 赞 / -1 踩
    feedback_comment: Mapped[Optional[str]] = mapped_column(Text, default=None)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=_now)
