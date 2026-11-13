import logging
import os
from contextlib import asynccontextmanager
from threading import Thread

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from .api import chat, documents, knowledge_bases, tags
from .config import get_settings
from .db import SessionLocal, init_db
from .models import DocStatus, Document
from .providers.llm import get_llm

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("tagrag")


def _resume_unfinished() -> None:
    """服务重启后，继续处理中断的入库任务。"""
    from .ingestion.pipeline import ingest_document
    db = SessionLocal()
    try:
        ids = list(db.scalars(select(Document.id).where(
            Document.status.in_([DocStatus.PENDING, DocStatus.PROCESSING]))))
    finally:
        db.close()
    for doc_id in ids:
        ingest_document(doc_id)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    Thread(target=_resume_unfinished, daemon=True).start()
    s = get_settings()
    llm = get_llm()
    logger.info("TagRAG 启动：LLM=%s, embedding=%s", llm.name if llm.enabled else f"{llm.name}（未配置凭证）",
                s.embedding_provider)
    yield


app = FastAPI(title="TagRAG", version="2.0.0", lifespan=lifespan,
              description="基于受控标签体系的企业级检索增强问答系统")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",")],
    allow_methods=["*"], allow_headers=["*"],
)

app.include_router(knowledge_bases.router)
app.include_router(documents.router)
app.include_router(tags.router)
app.include_router(chat.router)
app.include_router(chat.feedback_router)


@app.get("/api/health")
def health():
    s = get_settings()
    llm = get_llm()
    return {"status": "ok", "llm": llm.name, "llm_ready": llm.enabled, "embedding": s.embedding_provider}


_web_dir = get_settings().web_dir
if _web_dir:
    _web_root = os.path.realpath(_web_dir)

    @app.get("/{path:path}", include_in_schema=False)
    def web(path: str):
        """前端页面（单页应用）：存在的静态文件直接返回，其余路由回退到 index.html。"""
        if path.startswith("api/"):
            raise HTTPException(404)
        target = os.path.realpath(os.path.join(_web_root, path))
        if path and target.startswith(_web_root + os.sep) and os.path.isfile(target):
            return FileResponse(target)
        return FileResponse(os.path.join(_web_root, "index.html"))
