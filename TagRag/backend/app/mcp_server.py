"""TagRAG MCP 服务器：把 TagRAG 作为「受治理的根拠层」提供给 Claude（Claude Code / Claude Desktop / 自建 Agent）。

它是 TagRAG REST API 的一个薄客户端，因此 Agent 拿到的结果与人看到的一致，
并且同样受 API Key、用户组 ACL 约束，每次调用都以 agent:<id> 记入审计日志。

运行（stdio）：
    TAGRAG_URL=http://localhost:8000 TAGRAG_AGENT_ID=claude-code python -m app.mcp_server

在 Claude Code 中注册：
    claude mcp add tagrag --env TAGRAG_URL=http://localhost:8000 --env TAGRAG_AGENT_ID=claude-code \\
        -- python -m app.mcp_server

环境变量：
    TAGRAG_URL           TagRAG 后端地址（默认 http://localhost:8000）
    TAGRAG_API_KEY       后端开启 API Key 时需要
    TAGRAG_AGENT_ID      Agent 名称，写入审计日志（默认 claude）
    TAGRAG_AGENT_GROUPS  Agent 所属用户组（逗号分隔），决定它能看到哪些文档——按最小权限配置
    TAGRAG_KB            默认知识库（ID 或名称），工具调用未指定时使用
"""
import os
from typing import Any, Dict, List, Optional

import httpx
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

INSTRUCTIONS = """TagRAG is the organization's governed knowledge base. Use it as the source of evidence for
questions about internal policies, processes, products and documents.
- Call search_evidence before answering such questions. Answer only from the returned evidence and cite it as [E1], [E2].
- Respect the `sufficiency` field: "none" means there is no evidence - say so and do not answer from general knowledge;
  "weak" means answer cautiously, quote the source, or refine the query or scopes.
- Use list_scopes to see the tag taxonomy, and pass scope names to narrow a search to a department, product or topic.
- Use read_context to read the text around a piece of evidence before relying on it for details.
You only see documents your agent identity is allowed to see."""

READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False)

mcp = MCPServer("tagrag", instructions=INSTRUCTIONS)


class TagRAGError(ToolError):
    """预期内的错误（如未知 scope、无权限），消息会原样返回给 Agent，便于它自行纠正。"""


def _client() -> httpx.AsyncClient:
    headers = {"X-Agent-Id": os.environ.get("TAGRAG_AGENT_ID", "claude")}
    if os.environ.get("TAGRAG_API_KEY"):
        headers["X-API-Key"] = os.environ["TAGRAG_API_KEY"]
    if os.environ.get("TAGRAG_AGENT_GROUPS") is not None:
        headers["X-User-Groups"] = os.environ["TAGRAG_AGENT_GROUPS"]
    return httpx.AsyncClient(base_url=os.environ.get("TAGRAG_URL", "http://localhost:8000"),
                             headers=headers, timeout=60)


async def _get(path: str, **params) -> Any:
    async with _client() as c:
        r = await c.get(path, params=params)
    return _check(r)


async def _post(path: str, body: dict) -> Any:
    async with _client() as c:
        r = await c.post(path, json=body)
    return _check(r)


def _check(r: httpx.Response) -> Any:
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail")
        except ValueError:
            detail = r.text
        raise TagRAGError(f"TagRAG {r.status_code}: {detail}")
    return r.json()


async def _resolve_kb(kb: Optional[str]) -> dict:
    kb = kb or os.environ.get("TAGRAG_KB")
    kbs = await _get("/api/kbs")
    if not kbs:
        raise TagRAGError("No knowledge base exists yet.")
    if not kb:
        if len(kbs) == 1:
            return kbs[0]
        raise TagRAGError("Several knowledge bases exist; pass `kb`. Available: "
                          + ", ".join(f"{k['id']}:{k['name']}" for k in kbs))
    for k in kbs:
        if str(k["id"]) == str(kb) or k["name"].lower() == str(kb).lower():
            return k
    raise TagRAGError(f"Unknown knowledge base '{kb}'. Available: " + ", ".join(k["name"] for k in kbs))


@mcp.tool(annotations=READ_ONLY)
async def list_knowledge_bases() -> List[Dict[str, Any]]:
    """List the knowledge bases this agent can search, with document counts."""
    return [{"id": k["id"], "name": k["name"], "description": k["description"], "documents": k["documents"]}
            for k in await _get("/api/kbs")]


@mcp.tool(annotations=READ_ONLY)
async def list_scopes(kb: Optional[str] = None) -> Dict[str, Any]:
    """List the tag taxonomy of a knowledge base, grouped by facet (e.g. department, topic).
    Pass tag names from here as `scopes` to search_evidence to restrict a search; a scope includes its child tags."""
    k = await _resolve_kb(kb)
    tags = await _get(f"/api/kbs/{k['id']}/tags", status="active")
    by_id = {t["id"]: t["name"] for t in tags}
    facets: Dict[str, list] = {}
    for t in tags:
        facets.setdefault(t["facet"], []).append({
            "name": t["name"], "description": t["description"], "aliases": t["aliases"],
            "parent": by_id.get(t["parent_id"]), "chunks": t["chunk_count"]})
    return {"knowledge_base": k["name"], "facets": facets}


_GUIDANCE = {
    "sufficient": "Answer only from this evidence and cite it as [E1], [E2].",
    "weak": "Evidence is partial or inconsistent. Answer cautiously and quote the source, "
            "or refine the query or scopes and search again.",
    "none": "No evidence found. Do not answer from general knowledge: tell the user the knowledge base "
            "has no source for this, or hand the question to a person.",
}


@mcp.tool(annotations=READ_ONLY)
async def search_evidence(query: str, kb: Optional[str] = None, scopes: Optional[List[str]] = None,
                          top_k: int = 6) -> Dict[str, Any]:
    """Search the governed knowledge base for evidence. Returns cited passages (E1, E2, ...), their source document
    and section, the tags each passage carries, and a `sufficiency` judgment (sufficient / weak / none) with guidance
    on whether to answer, refine, or stop. `scopes` are tag names from list_scopes (child tags included)."""
    k = await _resolve_kb(kb)
    filter_ids: List[int] = []
    if scopes:
        tags = await _get(f"/api/kbs/{k['id']}/tags", status="active")
        lookup = {}
        for t in tags:
            for n in [t["name"]] + t["aliases"]:
                lookup[n.lower()] = t["id"]
        unknown = [s for s in scopes if s.lower() not in lookup]
        if unknown:
            raise TagRAGError(f"Unknown scopes {unknown}. Call list_scopes to see valid names.")
        filter_ids = [lookup[s.lower()] for s in scopes]
    res = await _post(f"/api/kbs/{k['id']}/search",
                      {"query": query, "top_k": max(1, min(top_k, 20)), "filter_tag_ids": filter_ids})
    return {
        "knowledge_base": k["name"],
        "sufficiency": res["sufficiency"],
        "guidance": _GUIDANCE[res["sufficiency"]],
        "query_tags": [t["name"] for t in res["query_tags"]],
        "evidence": [{
            "ref": f"E{r['index']}", "source": r["filename"], "section": r["heading_path"], "text": r["text"],
            "tags": r["tags"], "score": r["score"], "document_id": r["document_id"], "chunk_id": r["chunk_id"],
        } for r in res["results"]],
        "audit_log_id": res["log_id"],
    }


@mcp.tool(annotations=READ_ONLY)
async def read_context(document_id: int, chunk_id: int, window: int = 1, kb: Optional[str] = None) -> Dict[str, Any]:
    """Read a piece of evidence together with the passages before and after it (window = how many on each side,
    max 5). Use the document_id and chunk_id from search_evidence."""
    k = await _resolve_kb(kb)
    return await _get(f"/api/kbs/{k['id']}/documents/{document_id}/context", chunk_id=chunk_id, window=window)


def main() -> None:
    mcp.run("stdio")


if __name__ == "__main__":
    main()
