import random
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Chunk, ChunkTag, Tag, TagStatus
from ..security import UserContext, get_user, require_admin
from ..tagging.tagger import suggest_taxonomy
from ..tagging.taxonomy import (bump_version, find_tag, merge_tags, normalize_name, propose_candidate,
                                refresh_tag_embedding)
from .knowledge_bases import get_kb_or_404

router = APIRouter(prefix="/api/kbs/{kb_id}/tags", tags=["tags"])


class TagIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    facet: str = "topic"
    description: Optional[str] = None
    aliases: List[str] = []
    parent_id: Optional[int] = None
    status: str = TagStatus.ACTIVE


class TagPatch(BaseModel):
    name: Optional[str] = None
    facet: Optional[str] = None
    description: Optional[str] = None
    aliases: Optional[List[str]] = None
    parent_id: Optional[int] = None
    clear_parent: bool = False
    status: Optional[str] = None


class TaxonomyItem(BaseModel):
    name: str
    facet: str = "topic"
    description: Optional[str] = None
    aliases: List[str] = []
    parent: Optional[str] = None  # 父标签名称


def tag_out(t: Tag, usage: int = 0) -> dict:
    return {"id": t.id, "name": t.name, "facet": t.facet, "description": t.description,
            "aliases": t.aliases or [], "parent_id": t.parent_id, "status": t.status,
            "mention_count": t.mention_count, "chunk_count": usage, "created_at": t.created_at}


def _get_tag(db: Session, kb_id: int, tag_id: int) -> Tag:
    t = db.get(Tag, tag_id)
    if t is None or t.kb_id != kb_id:
        raise HTTPException(404, "标签不存在")
    return t


def _check_parent(db: Session, kb_id: int, tag_id: Optional[int], parent_id: Optional[int]) -> None:
    if parent_id is None:
        return
    p = _get_tag(db, kb_id, parent_id)
    seen = set()
    while p is not None:  # 防止形成环
        if p.id == tag_id or p.id in seen:
            raise HTTPException(400, "父标签设置会形成循环")
        seen.add(p.id)
        p = db.get(Tag, p.parent_id) if p.parent_id else None


def _check_name_free(db: Session, kb_id: int, names: List[str], exclude_id: Optional[int] = None) -> None:
    for n in names:
        other = find_tag(db, kb_id, n)
        if other is not None and other.id != exclude_id:
            raise HTTPException(409, f"名称/别名「{n}」已被标签「{other.name}」使用")


def _check_status(status: str) -> None:
    if status not in (TagStatus.ACTIVE, TagStatus.CANDIDATE, TagStatus.DEPRECATED):
        raise HTTPException(400, "status 只能是 active / candidate / deprecated")


@router.get("")
def list_tags(kb_id: int, status: Optional[str] = None, facet: Optional[str] = None,
              db: Session = Depends(get_db), user: UserContext = Depends(get_user)):
    get_kb_or_404(db, kb_id)
    q = select(Tag).where(Tag.kb_id == kb_id).order_by(Tag.facet, Tag.name)
    if status:
        q = q.where(Tag.status == status)
    if facet:
        q = q.where(Tag.facet == facet)
    usage = dict(db.execute(select(ChunkTag.tag_id, func.count()).join(Chunk, Chunk.id == ChunkTag.chunk_id)
                            .where(Chunk.kb_id == kb_id).group_by(ChunkTag.tag_id)).all())
    return [tag_out(t, usage.get(t.id, 0)) for t in db.scalars(q)]


@router.post("", status_code=201)
def create_tag(kb_id: int, body: TagIn, db: Session = Depends(get_db), user: UserContext = Depends(get_user)):
    require_admin(user)
    get_kb_or_404(db, kb_id)
    _check_status(body.status)
    aliases = [a.strip() for a in body.aliases if a.strip()]
    _check_name_free(db, kb_id, [body.name] + aliases)
    _check_parent(db, kb_id, None, body.parent_id)
    t = Tag(kb_id=kb_id, name=body.name.strip(), facet=body.facet.strip() or "topic",
            description=body.description, aliases=aliases, parent_id=body.parent_id, status=body.status)
    refresh_tag_embedding(t)
    db.add(t)
    db.commit()
    bump_version(kb_id)
    return tag_out(t)


@router.post("/import", status_code=201)
def import_taxonomy(kb_id: int, items: List[TaxonomyItem], db: Session = Depends(get_db),
                    user: UserContext = Depends(get_user)):
    """批量导入标签体系（按父标签名称建立层级；已存在的同名标签会被更新）。"""
    require_admin(user)
    get_kb_or_404(db, kb_id)
    by_name = {}
    for it in items:
        t = find_tag(db, kb_id, it.name)
        if t is None:
            t = Tag(kb_id=kb_id, name=it.name.strip(), aliases=[])
            db.add(t)
        t.facet = it.facet or "topic"
        t.description = it.description or t.description
        t.aliases = list(dict.fromkeys((t.aliases or []) + [a for a in it.aliases if a.strip()]))
        t.status = TagStatus.ACTIVE
        by_name[normalize_name(it.name)] = t
    db.flush()
    for it in items:
        if it.parent:
            parent = by_name.get(normalize_name(it.parent)) or find_tag(db, kb_id, it.parent)
            if parent is not None and parent.id != by_name[normalize_name(it.name)].id:
                by_name[normalize_name(it.name)].parent_id = parent.id
    for t in by_name.values():
        refresh_tag_embedding(t)
    db.commit()
    bump_version(kb_id)
    return [tag_out(t) for t in by_name.values()]


@router.post("/suggest")
async def suggest(kb_id: int, sample_size: int = 40, db: Session = Depends(get_db),
                  user: UserContext = Depends(get_user)):
    """冷启动：根据已入库内容自动建议标签体系，结果进入候选池等待审核。"""
    require_admin(user)
    get_kb_or_404(db, kb_id)
    texts = list(db.scalars(select(Chunk.text).where(Chunk.kb_id == kb_id)))
    if not texts:
        raise HTTPException(400, "知识库中还没有已处理的文档")
    samples = random.sample(texts, min(sample_size, len(texts)))
    proposals = await suggest_taxonomy(samples)
    created = []
    for p in proposals:
        t = propose_candidate(db, kb_id, str(p["name"]), str(p.get("facet") or "topic"), p.get("description"))
        if t is not None and t.status == TagStatus.CANDIDATE:
            t.aliases = list(dict.fromkeys((t.aliases or []) + [str(a) for a in p.get("aliases") or []]))
            if p.get("parent"):
                parent = find_tag(db, kb_id, str(p["parent"]))
                if parent is not None and parent.id != t.id:
                    t.parent_id = parent.id
            created.append(t)
    db.commit()
    return [tag_out(t) for t in created]


@router.patch("/{tag_id}")
def update_tag(kb_id: int, tag_id: int, body: TagPatch, db: Session = Depends(get_db),
               user: UserContext = Depends(get_user)):
    require_admin(user)
    t = _get_tag(db, kb_id, tag_id)
    if body.name is not None:
        _check_name_free(db, kb_id, [body.name], exclude_id=t.id)
        t.name = body.name.strip()
    if body.aliases is not None:
        aliases = [a.strip() for a in body.aliases if a.strip()]
        _check_name_free(db, kb_id, aliases, exclude_id=t.id)
        t.aliases = aliases
    if body.facet is not None:
        t.facet = body.facet.strip() or "topic"
    if body.description is not None:
        t.description = body.description
    if body.clear_parent:
        t.parent_id = None
    elif body.parent_id is not None:
        _check_parent(db, kb_id, t.id, body.parent_id)
        t.parent_id = body.parent_id
    if body.status is not None:
        _check_status(body.status)
        t.status = body.status
    refresh_tag_embedding(t)
    db.commit()
    bump_version(kb_id)
    return tag_out(t)


@router.post("/{tag_id}/approve")
def approve(kb_id: int, tag_id: int, db: Session = Depends(get_db), user: UserContext = Depends(get_user)):
    require_admin(user)
    t = _get_tag(db, kb_id, tag_id)
    t.status = TagStatus.ACTIVE
    refresh_tag_embedding(t)
    db.commit()
    bump_version(kb_id)
    return tag_out(t)


@router.post("/{tag_id}/merge/{target_id}")
def merge(kb_id: int, tag_id: int, target_id: int, db: Session = Depends(get_db),
          user: UserContext = Depends(get_user)):
    """把 tag_id 合并进 target_id（原名称成为别名）。用于治理同义/重复标签。"""
    require_admin(user)
    if tag_id == target_id:
        raise HTTPException(400, "不能合并到自身")
    source, target = _get_tag(db, kb_id, tag_id), _get_tag(db, kb_id, target_id)
    merge_tags(db, source, target)
    db.commit()
    return tag_out(target)


@router.delete("/{tag_id}")
def delete_tag(kb_id: int, tag_id: int, db: Session = Depends(get_db), user: UserContext = Depends(get_user)):
    require_admin(user)
    t = _get_tag(db, kb_id, tag_id)
    for child in db.scalars(select(Tag).where(Tag.parent_id == t.id)):
        child.parent_id = t.parent_id
    db.delete(t)
    db.commit()
    bump_version(kb_id)
    return {"ok": True}
