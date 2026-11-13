"""Embedding 提供方。所有向量都做 L2 归一化，点积即余弦相似度。"""
import hashlib
import logging
from functools import lru_cache
from typing import List

import httpx
import numpy as np

from ..config import get_settings
from ..text import tokenize

logger = logging.getLogger(__name__)


def _normalize(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (m / norms).astype(np.float32)


class Embedder:
    dim: int
    name: str

    def embed(self, texts: List[str], input_type: str = "document") -> np.ndarray:
        """input_type: document（入库内容）/ query（检索问题）。部分模型（如 Voyage）据此优化向量。"""
        raise NotImplementedError

    def embed_one(self, text: str, input_type: str = "document") -> np.ndarray:
        return self.embed([text], input_type)[0]


class HashEmbedder(Embedder):
    """无需模型的特征哈希向量（字/词 n-gram）。仅用于离线开发与测试，语义能力有限。"""

    def __init__(self, dim: int):
        self.dim = dim
        self.name = f"hash-{dim}"

    def embed(self, texts: List[str], input_type: str = "document") -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            for tok in tokenize(t):
                h = int.from_bytes(hashlib.md5(tok.encode("utf-8")).digest()[:8], "little")
                sign = 1.0 if (h >> 63) & 1 else -1.0
                out[i, h % self.dim] += sign
        return _normalize(out)


class OpenAIEmbedder(Embedder):
    """OpenAI 兼容的 /embeddings 接口（OpenAI、Azure、通义、智谱、硅基流动、vLLM、Ollama 等）。"""

    def __init__(self, base_url: str, api_key: str, model: str, batch_size: int, timeout: float):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.batch_size = batch_size
        self.timeout = timeout
        self.name = f"openai:{model}"
        self.dim = 0

    def _body(self, batch: List[str], input_type: str) -> dict:
        return {"model": self.model, "input": batch}

    def embed(self, texts: List[str], input_type: str = "document") -> np.ndarray:
        vecs: List[List[float]] = []
        with httpx.Client(timeout=self.timeout) as client:
            for i in range(0, len(texts), self.batch_size):
                batch = [t if t.strip() else " " for t in texts[i:i + self.batch_size]]
                resp = client.post(
                    f"{self.base_url}/embeddings",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=self._body(batch, input_type),
                )
                resp.raise_for_status()
                data = sorted(resp.json()["data"], key=lambda d: d["index"])
                vecs.extend(d["embedding"] for d in data)
        m = _normalize(np.asarray(vecs, dtype=np.float32))
        self.dim = m.shape[1]
        return m


class VoyageEmbedder(OpenAIEmbedder):
    """Voyage AI（Anthropic 推荐的 embedding 服务）。接口形状与 OpenAI 相同，额外区分 query / document。"""

    def __init__(self, api_key: str, model: str, batch_size: int, timeout: float, base_url: str):
        super().__init__(base_url, api_key, model, batch_size, timeout)
        self.name = f"voyage:{model}"

    def _body(self, batch: List[str], input_type: str) -> dict:
        return {"model": self.model, "input": batch, "input_type": input_type}


class LocalEmbedder(Embedder):
    """本地 sentence-transformers 模型（推荐中文：BAAI/bge-m3、BAAI/bge-small-zh-v1.5）。"""

    def __init__(self, model: str, batch_size: int):
        from sentence_transformers import SentenceTransformer  # 可选依赖
        self.model = SentenceTransformer(model)
        self.batch_size = batch_size
        self.dim = self.model.get_sentence_embedding_dimension()
        self.name = f"local:{model}"

    def embed(self, texts: List[str], input_type: str = "document") -> np.ndarray:
        m = self.model.encode(texts, batch_size=self.batch_size, normalize_embeddings=True)
        return np.asarray(m, dtype=np.float32)


@lru_cache
def get_embedder() -> Embedder:
    s = get_settings()
    if s.embedding_provider == "openai":
        return OpenAIEmbedder(
            base_url=s.embedding_base_url or s.llm_base_url,
            api_key=s.embedding_api_key or s.llm_api_key,
            model=s.embedding_model,
            batch_size=s.embedding_batch_size,
            timeout=s.llm_timeout,
        )
    if s.embedding_provider == "voyage":
        return VoyageEmbedder(api_key=s.embedding_api_key or "", model=s.embedding_model,
                              batch_size=s.embedding_batch_size, timeout=s.llm_timeout,
                              base_url=s.embedding_base_url or "https://api.voyageai.com/v1")
    if s.embedding_provider == "local":
        return LocalEmbedder(s.embedding_model, s.embedding_batch_size)
    if s.embedding_provider != "hash":
        raise ValueError(f"未知 embedding_provider: {s.embedding_provider}")
    logger.warning("使用 hash embedding（仅适合开发/测试）。生产请设置 TAGRAG_EMBEDDING_PROVIDER=openai 或 local")
    return HashEmbedder(s.embedding_dim)


def to_bytes(v: np.ndarray) -> bytes:
    return np.asarray(v, dtype=np.float32).tobytes()


def from_bytes(b: bytes) -> np.ndarray:
    return np.frombuffer(b, dtype=np.float32)
