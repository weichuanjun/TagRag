import shutil
import os
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..ingestion.pipeline import retag_knowledge_base
from ..models import Chunk, DocStatus, Document, KnowledgeBase, QueryLog, Tag, TagStatus
from ..retrieval.index import invalidate
from ..security import UserContext, get_user, require_admin

router = APIRouter(prefix="/api/kbs", tags=["knowledge-bases"])


class KBIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None


def get_kb_or_404(db: Session, kb_id: int) -> KnowledgeBase:
    kb = db.get(KnowledgeBase, kb_id)
    if kb is None:
        raise HTTPException(404, "知识库不存在")
    return kb


def kb_out(db: Session, kb: KnowledgeBase) -> dict:
    doc_counts = dict(db.execute(select(Document.status, func.count()).where(Document.kb_id == kb.id)
                                 .group_by(Document.status)).all())
    tag_counts = dict(db.execute(select(Tag.status, func.count()).where(Tag.kb_id == kb.id)
                                 .group_by(Tag.status)).all())
    chunks = db.scalar(select(func.count()).select_from(Chunk).where(Chunk.kb_id == kb.id))
    return {
        "id": kb.id, "name": kb.name, "description": kb.description, "created_at": kb.created_at,
        "documents": sum(doc_counts.values()), "documents_by_status": doc_counts,
        "chunks": chunks, "tags": tag_counts.get(TagStatus.ACTIVE, 0),
        "candidate_tags": tag_counts.get(TagStatus.CANDIDATE, 0),
    }


@router.get("")
def list_kbs(db: Session = Depends(get_db), user: UserContext = Depends(get_user)):
    return [kb_out(db, kb) for kb in db.scalars(select(KnowledgeBase).order_by(KnowledgeBase.id))]


@router.post("", status_code=201)
def create_kb(body: KBIn, db: Session = Depends(get_db), user: UserContext = Depends(get_user)):
    require_admin(user)
    kb = KnowledgeBase(name=body.name.strip(), description=body.description)
    db.add(kb)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "同名知识库已存在")
    return kb_out(db, kb)


@router.get("/{kb_id}")
def get_kb(kb_id: int, db: Session = Depends(get_db), user: UserContext = Depends(get_user)):
    return kb_out(db, get_kb_or_404(db, kb_id))


@router.put("/{kb_id}")
def update_kb(kb_id: int, body: KBIn, db: Session = Depends(get_db), user: UserContext = Depends(get_user)):
    require_admin(user)
    kb = get_kb_or_404(db, kb_id)
    kb.name, kb.description = body.name.strip(), body.description
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "同名知识库已存在")
    return kb_out(db, kb)


@router.delete("/{kb_id}")
def delete_kb(kb_id: int, db: Session = Depends(get_db), user: UserContext = Depends(get_user)):
    require_admin(user)
    kb = get_kb_or_404(db, kb_id)
    db.delete(kb)
    db.commit()
    invalidate(kb_id)
    shutil.rmtree(os.path.join(get_settings().data_dir, "files", str(kb_id)), ignore_errors=True)
    return {"ok": True}


@router.post("/{kb_id}/retag")
def retag(kb_id: int, background: BackgroundTasks, db: Session = Depends(get_db),
          user: UserContext = Depends(get_user)):
    """标签体系调整后（新增/审核/合并标签），对全部文档重新打标。"""
    require_admin(user)
    get_kb_or_404(db, kb_id)
    background.add_task(retag_knowledge_base, kb_id)
    return {"ok": True, "message": "已开始后台重新打标"}


@router.get("/{kb_id}/stats")
def stats(kb_id: int, db: Session = Depends(get_db), user: UserContext = Depends(get_user)):
    get_kb_or_404(db, kb_id)
    total = db.scalar(select(func.count()).select_from(QueryLog).where(QueryLog.kb_id == kb_id))
    up = db.scalar(select(func.count()).select_from(QueryLog).where(QueryLog.kb_id == kb_id, QueryLog.feedback == 1))
    down = db.scalar(select(func.count()).select_from(QueryLog).where(QueryLog.kb_id == kb_id, QueryLog.feedback == -1))
    avg = db.scalar(select(func.avg(QueryLog.latency_ms)).where(QueryLog.kb_id == kb_id))
    no_answer = db.scalar(select(func.count()).select_from(QueryLog)
                          .where(QueryLog.kb_id == kb_id, QueryLog.source_count == 0))
    failed = db.scalar(select(func.count()).select_from(Document)
                       .where(Document.kb_id == kb_id, Document.status == DocStatus.FAILED))
    return {"queries": total, "thumbs_up": up, "thumbs_down": down, "avg_latency_ms": round(avg or 0),
            "queries_without_sources": no_answer, "failed_documents": failed}
