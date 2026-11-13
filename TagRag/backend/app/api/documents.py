import hashlib
import os
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import get_settings
from ..db import get_db
from ..ingestion.parsers import SUPPORTED_EXTENSIONS
from ..ingestion.pipeline import ingest_document, retag_document
from ..models import Chunk, ChunkTag, DocStatus, Document, DocumentTag, Tag
from ..retrieval.index import invalidate
from ..security import UserContext, acl_groups_for, get_user, require_admin
from ..tagging.taxonomy import bump_version
from .knowledge_bases import get_kb_or_404

router = APIRouter(prefix="/api/kbs/{kb_id}/documents", tags=["documents"])


def _split_csv(v: Optional[str]) -> List[str]:
    return [x.strip() for x in (v or "").split(",") if x.strip()]


def _visible(doc: Document, user: UserContext) -> bool:
    groups = acl_groups_for(user)
    return groups is None or not doc.acl_groups or bool(set(doc.acl_groups) & set(groups))


def doc_out(doc: Document) -> dict:
    return {
        "id": doc.id, "kb_id": doc.kb_id, "filename": doc.filename, "status": doc.status, "error": doc.error,
        "chunk_count": doc.chunk_count, "acl_groups": doc.acl_groups or [], "meta": doc.meta or {},
        "created_at": doc.created_at, "updated_at": doc.updated_at,
        "tags": [{"id": dt.tag.id, "name": dt.tag.name, "facet": dt.tag.facet, "source": dt.source}
                 for dt in doc.doc_tags if dt.tag is not None],
    }


def _get_doc(db: Session, kb_id: int, doc_id: int, user: UserContext) -> Document:
    doc = db.get(Document, doc_id)
    if doc is None or doc.kb_id != kb_id or not _visible(doc, user):
        raise HTTPException(404, "文档不存在")
    return doc


def _validate_tag_ids(db: Session, kb_id: int, tag_ids: List[int]) -> List[int]:
    if not tag_ids:
        return []
    found = set(db.scalars(select(Tag.id).where(Tag.kb_id == kb_id, Tag.id.in_(tag_ids))))
    missing = set(tag_ids) - found
    if missing:
        raise HTTPException(400, f"标签不存在或不属于该知识库: {sorted(missing)}")
    return list(dict.fromkeys(tag_ids))


@router.post("", status_code=201)
async def upload(kb_id: int, background: BackgroundTasks, files: List[UploadFile] = File(...),
                 tag_ids: Optional[str] = Form(None, description="逗号分隔的标签ID，会继承到所有 chunk"),
                 acl_groups: Optional[str] = Form(None, description="逗号分隔的可访问用户组，空=公开"),
                 db: Session = Depends(get_db), user: UserContext = Depends(get_user)):
    require_admin(user)
    get_kb_or_404(db, kb_id)
    s = get_settings()
    try:
        manual_tags = _validate_tag_ids(db, kb_id, [int(x) for x in _split_csv(tag_ids)])
    except ValueError:
        raise HTTPException(400, "tag_ids 格式错误")
    acl = _split_csv(acl_groups)
    storage = os.path.join(s.data_dir, "files", str(kb_id))
    os.makedirs(storage, exist_ok=True)

    results = []
    for f in files:
        name = os.path.basename(f.filename or "unnamed")
        ext = os.path.splitext(name)[1].lower()
        if ext not in SUPPORTED_EXTENSIONS:
            results.append({"filename": name, "error": f"不支持的类型 {ext}"})
            continue
        content = await f.read()
        if len(content) > s.max_upload_mb * 1024 * 1024:
            results.append({"filename": name, "error": f"超过 {s.max_upload_mb}MB 限制"})
            continue
        digest = hashlib.sha256(content).hexdigest()
        existing = db.scalar(select(Document).where(Document.kb_id == kb_id, Document.content_hash == digest))
        if existing is not None:
            results.append({**doc_out(existing), "duplicate": True})
            continue
        path = os.path.join(storage, f"{digest}{ext}")
        with open(path, "wb") as out:
            out.write(content)
        doc = Document(kb_id=kb_id, filename=name, content_hash=digest, file_path=path,
                       acl_groups=acl, meta={"size": len(content)}, status=DocStatus.PENDING)
        db.add(doc)
        db.flush()
        for tid in manual_tags:
            db.add(DocumentTag(document_id=doc.id, tag_id=tid, source="manual"))
        db.commit()
        db.refresh(doc)
        background.add_task(ingest_document, doc.id)
        results.append(doc_out(doc))
    return results


@router.get("")
def list_documents(kb_id: int, status: Optional[str] = None, tag_id: Optional[int] = None,
                   db: Session = Depends(get_db), user: UserContext = Depends(get_user)):
    get_kb_or_404(db, kb_id)
    q = (select(Document).where(Document.kb_id == kb_id)
         .options(selectinload(Document.doc_tags).selectinload(DocumentTag.tag)).order_by(Document.id.desc()))
    if status:
        q = q.where(Document.status == status)
    if tag_id:
        q = q.where(Document.id.in_(select(DocumentTag.document_id).where(DocumentTag.tag_id == tag_id)))
    return [doc_out(d) for d in db.scalars(q) if _visible(d, user)]


@router.get("/{doc_id}")
def get_document(kb_id: int, doc_id: int, db: Session = Depends(get_db), user: UserContext = Depends(get_user)):
    return doc_out(_get_doc(db, kb_id, doc_id, user))


@router.get("/{doc_id}/chunks")
def get_chunks(kb_id: int, doc_id: int, db: Session = Depends(get_db), user: UserContext = Depends(get_user)):
    _get_doc(db, kb_id, doc_id, user)
    chunks = db.scalars(select(Chunk).where(Chunk.document_id == doc_id).order_by(Chunk.ordinal)
                        .options(selectinload(Chunk.chunk_tags).selectinload(ChunkTag.tag))).all()
    return [{
        "id": c.id, "ordinal": c.ordinal, "heading_path": c.heading_path, "text": c.text,
        "token_count": c.token_count,
        "tags": sorted([{"id": ct.tag.id, "name": ct.tag.name, "status": ct.tag.status,
                         "confidence": ct.confidence, "source": ct.source} for ct in c.chunk_tags],
                       key=lambda t: -t["confidence"]),
    } for c in chunks]


class DocUpdate(BaseModel):
    tag_ids: Optional[List[int]] = None     # 人工标签（覆盖原人工标签）
    acl_groups: Optional[List[str]] = None


@router.patch("/{doc_id}")
def update_document(kb_id: int, doc_id: int, body: DocUpdate, db: Session = Depends(get_db),
                    user: UserContext = Depends(get_user)):
    require_admin(user)
    doc = _get_doc(db, kb_id, doc_id, user)
    if body.acl_groups is not None:
        doc.acl_groups = [g.strip() for g in body.acl_groups if g.strip()]
    if body.tag_ids is not None:
        tag_ids = _validate_tag_ids(db, kb_id, body.tag_ids)
        for dt in list(doc.doc_tags):
            if dt.source == "manual" or dt.tag_id in tag_ids:
                doc.doc_tags.remove(dt)
        db.flush()
        for tid in tag_ids:
            db.add(DocumentTag(document_id=doc.id, tag_id=tid, source="manual"))
        db.flush()
        db.refresh(doc)
        if doc.status == DocStatus.READY:
            retag_document(db, doc)
    db.commit()
    db.refresh(doc)
    bump_version(kb_id)
    return doc_out(doc)


@router.post("/{doc_id}/reindex")
def reindex(kb_id: int, doc_id: int, background: BackgroundTasks, db: Session = Depends(get_db),
            user: UserContext = Depends(get_user)):
    """重新解析 + 向量化 + 打标（例如切换 embedding 模型或切块参数后）。"""
    require_admin(user)
    doc = _get_doc(db, kb_id, doc_id, user)
    doc.status = DocStatus.PENDING
    db.commit()
    background.add_task(ingest_document, doc.id)
    return doc_out(doc)


@router.delete("/{doc_id}")
def delete_document(kb_id: int, doc_id: int, db: Session = Depends(get_db), user: UserContext = Depends(get_user)):
    require_admin(user)
    doc = _get_doc(db, kb_id, doc_id, user)
    path = doc.file_path
    db.delete(doc)
    db.commit()
    bump_version(kb_id)
    invalidate(kb_id)
    try:
        os.remove(path)
    except OSError:
        pass
    return {"ok": True}
