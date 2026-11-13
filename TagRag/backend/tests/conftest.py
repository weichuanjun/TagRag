import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TAGRAG_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TAGRAG_LLM_API_KEY", "")
    monkeypatch.setenv("TAGRAG_EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("TAGRAG_API_KEYS", "")
    monkeypatch.setenv("TAGRAG_LLM_PROVIDER", "claude")
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE", "TAGRAG_ANTHROPIC_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    from app import config, db
    from app.providers import embeddings
    from app.retrieval import index
    from app.tagging import taxonomy
    config.get_settings.cache_clear()
    embeddings.get_embedder.cache_clear()
    db.reset_engine()
    index.invalidate()
    taxonomy._tag_index_cache.clear()

    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c
    db.reset_engine()
    config.get_settings.cache_clear()


def wait_ready(client, kb_id, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        docs = client.get(f"/api/kbs/{kb_id}/documents").json()
        if docs and all(d["status"] in ("ready", "failed") for d in docs):
            return docs
        time.sleep(0.05)
    raise TimeoutError("documents not processed")
