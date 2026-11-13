import json
import time
from dataclasses import asdict
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import SessionLocal, get_db
from ..models import QueryLog
from ..rag import cited_indices, generate_answer, stream_answer
from ..retrieval.retriever import RetrievalOptions, assemble_context, assess_sufficiency, retrieve
from ..security import UserContext, acl_groups_for, get_user
from .knowledge_bases import get_kb_or_404

router = APIRouter(prefix="/api/kbs/{kb_id}", tags=["chat"])


class SearchIn(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: Optional[int] = Field(default=None, ge=1, le=50)
    filter_tag_ids: List[int] = []
    use_tags: bool = True


class ChatIn(SearchIn):
    history: List[dict] = []


def _source_out(i: int, c) -> dict:
    d = asdict(c)
    d["index"] = i
    return d


def _run_retrieval(db: Session, kb_id: int, body: SearchIn, user: UserContext):
    get_kb_or_404(db, kb_id)
    res = retrieve(db, kb_id, body.query, acl_groups_for(user),
                   RetrievalOptions(top_k=body.top_k, filter_tag_ids=body.filter_tag_ids, use_tags=body.use_tags))
    context = assemble_context(res.chunks, get_settings().context_token_budget)
    return res, context


def _log(kb_id: int, user: UserContext, query: str, tags: list, sources: list, answer, t0: float,
         kind: str = "chat") -> int:
    db = SessionLocal()
    try:
        log = QueryLog(kb_id=kb_id, user=user.actor, kind=kind, query=query, matched_tags=tags,
                       sources=[{"chunk_id": s["chunk_id"], "document_id": s["document_id"], "score": s["score"]}
                                for s in sources],
                       source_count=len(sources), answer=answer,
                       latency_ms=int((time.perf_counter() - t0) * 1000))
        db.add(log)
        db.commit()
        return log.id
    finally:
        db.close()


@router.post("/search")
def search(kb_id: int, body: SearchIn, db: Session = Depends(get_db), user: UserContext = Depends(get_user)):
    """仅检索（不生成）：给 Agent 取根拠，也用于调试和评测。返回根拠充分度与各路分数明细。"""
    t0 = time.perf_counter()
    res, _ = _run_retrieval(db, kb_id, body, user)
    results = [_source_out(i, c) for i, c in enumerate(res.chunks, start=1)]
    log_id = _log(kb_id, user, body.query, res.query_tags, results, None, t0, kind="search")
    return {"query": res.query, "query_tags": res.query_tags, "candidates": res.candidates,
            "sufficiency": assess_sufficiency(res.chunks), "log_id": log_id,
            "timings_ms": res.timings_ms, "results": results}


@router.post("/chat")
async def chat(kb_id: int, body: ChatIn, db: Session = Depends(get_db), user: UserContext = Depends(get_user)):
    t0 = time.perf_counter()
    res, context = _run_retrieval(db, kb_id, body, user)
    answer = await generate_answer(body.query, context, body.history)
    sources = [_source_out(i, c) for i, c in enumerate(context, start=1)]
    log_id = _log(kb_id, user, body.query, res.query_tags, sources, answer, t0)
    return {"answer": answer, "sources": sources, "cited": cited_indices(answer, len(sources)),
            "query_tags": res.query_tags, "log_id": log_id, "timings_ms": res.timings_ms}


@router.post("/chat/stream")
async def chat_stream(kb_id: int, body: ChatIn, db: Session = Depends(get_db),
                      user: UserContext = Depends(get_user)):
    """SSE 流式输出。事件：meta（来源与标签）→ delta（增量文本）→ done（日志ID、引用）。"""
    t0 = time.perf_counter()
    res, context = _run_retrieval(db, kb_id, body, user)
    sources = [_source_out(i, c) for i, c in enumerate(context, start=1)]

    def sse(event: str, data) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"

    async def gen():
        yield sse("meta", {"sources": sources, "query_tags": res.query_tags, "timings_ms": res.timings_ms})
        parts: List[str] = []
        try:
            async for delta in stream_answer(body.query, context, body.history):
                parts.append(delta)
                yield sse("delta", {"text": delta})
        except Exception as e:  # 上游 LLM 失败时告知前端
            yield sse("error", {"message": f"生成失败: {e}"})
        answer = "".join(parts)
        log_id = _log(kb_id, user, body.query, res.query_tags, sources, answer, t0)
        yield sse("done", {"log_id": log_id, "cited": cited_indices(answer, len(sources))})

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


class FeedbackIn(BaseModel):
    rating: int = Field(ge=-1, le=1)
    comment: Optional[str] = None


feedback_router = APIRouter(prefix="/api/feedback", tags=["chat"])


@feedback_router.post("/{log_id}")
def feedback(log_id: int, body: FeedbackIn, db: Session = Depends(get_db), user: UserContext = Depends(get_user)):
    log = db.get(QueryLog, log_id)
    if log is None:
        raise HTTPException(404, "记录不存在")
    log.feedback, log.feedback_comment = body.rating, body.comment
    db.commit()
    return {"ok": True}
