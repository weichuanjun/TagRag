"""标签体系（taxonomy）服务：受控词表、别名解析、层级关系、候选标签治理。"""
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ChunkTag, DocumentTag, Tag, TagStatus
from ..providers.embeddings import from_bytes, get_embedder, to_bytes


def normalize_name(name: str) -> str:
    return " ".join(name.strip().split()).lower()


def tag_embed_text(tag: Tag) -> str:
    parts = [tag.name] + list(tag.aliases or [])
    if tag.description:
        parts.append(tag.description)
    return "；".join(parts)


def refresh_tag_embedding(tag: Tag) -> None:
    tag.embedding = to_bytes(get_embedder().embed_one(tag_embed_text(tag)))


# ---------------------------------------------------------------------------
# 版本号：标签或文档变化时递增，用于让内存索引失效
# ---------------------------------------------------------------------------
_versions: Dict[int, int] = {}
_lock = threading.Lock()


def bump_version(kb_id: int) -> None:
    with _lock:
        _versions[kb_id] = _versions.get(kb_id, 0) + 1


def get_version(kb_id: int) -> int:
    return _versions.get(kb_id, 0)


@dataclass
class TagIndex:
    """某知识库 active 标签的内存视图。"""
    kb_id: int
    version: int
    tags: List[Tag] = field(default_factory=list)
    by_id: Dict[int, Tag] = field(default_factory=dict)
    name_lookup: Dict[str, int] = field(default_factory=dict)  # 规范化名称/别名 -> tag_id
    parent: Dict[int, Optional[int]] = field(default_factory=dict)
    children: Dict[int, List[int]] = field(default_factory=dict)
    matrix: Optional[np.ndarray] = None  # active 标签向量矩阵（行顺序同 tags）

    def resolve(self, name: str) -> Optional[int]:
        return self.name_lookup.get(normalize_name(name))

    def ancestors(self, tag_id: int, max_depth: int = 3) -> Dict[int, int]:
        out, cur, d = {}, self.parent.get(tag_id), 1
        while cur is not None and d <= max_depth and cur not in out:
            out[cur] = d
            cur, d = self.parent.get(cur), d + 1
        return out

    def descendants(self, tag_id: int, max_depth: int = 3) -> Dict[int, int]:
        out, frontier, d = {}, [tag_id], 1
        while frontier and d <= max_depth:
            nxt = []
            for t in frontier:
                for c in self.children.get(t, []):
                    if c not in out and c != tag_id:
                        out[c] = d
                        nxt.append(c)
            frontier, d = nxt, d + 1
        return out

    def distance(self, a: int, b: int, max_depth: int = 3) -> Optional[int]:
        """层级距离：同一标签 0；祖先/后代为层数；兄弟（同父）为 2；无关返回 None。"""
        if a == b:
            return 0
        anc_a = self.ancestors(a, max_depth)
        if b in anc_a:
            return anc_a[b]
        anc_b = self.ancestors(b, max_depth)
        if a in anc_b:
            return anc_b[a]
        pa, pb = self.parent.get(a), self.parent.get(b)
        if pa is not None and pa == pb:
            return 2
        return None

    def expand(self, tag_ids: List[int]) -> Set[int]:
        """标签 + 全部后代（用于硬过滤：选「财务」应包含「报销」「预算」）。"""
        out = set(tag_ids)
        for t in tag_ids:
            out.update(self.descendants(t, max_depth=10))
        return out


_tag_index_cache: Dict[int, TagIndex] = {}


def load_tag_index(db: Session, kb_id: int) -> TagIndex:
    version = get_version(kb_id)
    cached = _tag_index_cache.get(kb_id)
    if cached and cached.version == version:
        return cached
    all_tags = db.scalars(select(Tag).where(Tag.kb_id == kb_id)).all()
    idx = TagIndex(kb_id=kb_id, version=version)
    for t in all_tags:
        idx.parent[t.id] = t.parent_id
        if t.parent_id:
            idx.children.setdefault(t.parent_id, []).append(t.id)
        if t.status != TagStatus.ACTIVE:
            continue
        idx.tags.append(t)
        idx.by_id[t.id] = t
        for n in [t.name] + list(t.aliases or []):
            idx.name_lookup.setdefault(normalize_name(n), t.id)
    need_commit = False
    for t in idx.tags:
        if t.embedding is None:
            refresh_tag_embedding(t)
            need_commit = True
    if need_commit:
        db.commit()
    if idx.tags:
        idx.matrix = np.vstack([from_bytes(t.embedding) for t in idx.tags])
    _tag_index_cache[kb_id] = idx
    return idx


def find_tag(db: Session, kb_id: int, name: str) -> Optional[Tag]:
    """按名称或别名查找任意状态的标签。"""
    key = normalize_name(name)
    for t in db.scalars(select(Tag).where(Tag.kb_id == kb_id)).all():
        if normalize_name(t.name) == key or key in {normalize_name(a) for a in (t.aliases or [])}:
            return t
    return None


def propose_candidate(db: Session, kb_id: int, name: str, facet: str = "topic",
                      description: Optional[str] = None) -> Optional[Tag]:
    """LLM 提议的新标签进入候选池；被多次提议后可按配置自动转正。"""
    name = name.strip()[:100]
    if not name:
        return None
    t = find_tag(db, kb_id, name)
    if t is None:
        t = Tag(kb_id=kb_id, name=name, facet=facet or "topic", description=description,
                aliases=[], status=TagStatus.CANDIDATE, mention_count=0)
        db.add(t)
        db.flush()
    if t.status == TagStatus.CANDIDATE:
        t.mention_count += 1
        threshold = get_settings().candidate_auto_promote
        if threshold and t.mention_count >= threshold:
            t.status = TagStatus.ACTIVE
            refresh_tag_embedding(t)
            bump_version(kb_id)
    return t


def merge_tags(db: Session, source: Tag, target: Tag) -> None:
    """把 source 合并进 target：迁移 chunk/文档关联、名称变为别名、子标签挂到 target 下。"""
    if source.id == target.id:
        return
    existing_chunk = {ct.chunk_id for ct in db.scalars(select(ChunkTag).where(ChunkTag.tag_id == target.id))}
    for ct in db.scalars(select(ChunkTag).where(ChunkTag.tag_id == source.id)).all():
        if ct.chunk_id in existing_chunk:
            db.delete(ct)
        else:
            db.add(ChunkTag(chunk_id=ct.chunk_id, tag_id=target.id, confidence=ct.confidence, source=ct.source))
            db.delete(ct)
    existing_doc = {dt.document_id for dt in db.scalars(select(DocumentTag).where(DocumentTag.tag_id == target.id))}
    for dt in db.scalars(select(DocumentTag).where(DocumentTag.tag_id == source.id)).all():
        if dt.document_id not in existing_doc:
            db.add(DocumentTag(document_id=dt.document_id, tag_id=target.id, source=dt.source))
        db.delete(dt)
    for child in db.scalars(select(Tag).where(Tag.parent_id == source.id)).all():
        child.parent_id = target.id
    aliases = list(target.aliases or [])
    for n in [source.name] + list(source.aliases or []):
        if normalize_name(n) != normalize_name(target.name) and n not in aliases:
            aliases.append(n)
    target.aliases = aliases
    db.flush()
    db.delete(source)
    refresh_tag_embedding(target)
    bump_version(target.kb_id)
