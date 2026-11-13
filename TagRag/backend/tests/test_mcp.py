"""MCP 端到端：启动真实后端进程，用 MCP 客户端通过 stdio 拉起 TagRAG MCP 服务器并调用工具。"""
import asyncio
import json
import os
import socket
import subprocess
import sys
import time

import httpx
import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

POLICY = "# 差旅报销制度\n\n## 住宿标准\n一线城市住宿费每晚不超过600元，其他城市每晚不超过400元。超出部分由员工自理，需在报销单中说明。\n"
HR = "# 员工休假制度\n\n## 年假\n员工入职满一年后享有5天带薪年假，满十年享有10天年假。年假需提前一周在OA系统申请。\n"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def backend(tmp_path):
    port = _free_port()
    env = {**os.environ, "TAGRAG_DATA_DIR": str(tmp_path), "TAGRAG_EMBEDDING_PROVIDER": "hash",
           "TAGRAG_LLM_PROVIDER": "claude", "TAGRAG_API_KEYS": ""}
    for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"):
        env.pop(k, None)
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
                            cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if httpx.get(f"{url}/api/health").status_code == 200:
                    break
            except httpx.HTTPError:
                time.sleep(0.1)
        kid = httpx.post(f"{url}/api/kbs", json={"name": "制度库"}).json()["id"]
        httpx.post(f"{url}/api/kbs/{kid}/tags/import", json=[
            {"name": "财务", "facet": "department"}, {"name": "人力资源", "facet": "department"},
            {"name": "报销", "facet": "topic", "parent": "财务"},
            {"name": "休假", "facet": "topic", "parent": "人力资源", "aliases": ["年假"]}])
        httpx.post(f"{url}/api/kbs/{kid}/documents", data={"acl_groups": "finance"},
                   files=[("files", ("finance.md", POLICY.encode(), "text/markdown"))])
        httpx.post(f"{url}/api/kbs/{kid}/documents", files=[("files", ("hr.md", HR.encode(), "text/markdown"))])
        for _ in range(100):
            docs = httpx.get(f"{url}/api/kbs/{kid}/documents").json()
            if len(docs) == 2 and all(d["status"] == "ready" for d in docs):
                break
            time.sleep(0.1)
        yield url, kid
    finally:
        proc.terminate()
        proc.wait(timeout=10)


async def _session_calls(url: str, groups: str, calls):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    params = StdioServerParameters(command=sys.executable, args=["-m", "app.mcp_server"], cwd=BACKEND,
                                   env={**os.environ, "TAGRAG_URL": url, "TAGRAG_AGENT_ID": "claude-test",
                                        "TAGRAG_AGENT_GROUPS": groups})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = {t.name for t in (await session.list_tools()).tools}
            out = {"tools": tools}
            for name, args in calls:
                res = await session.call_tool(name, args)
                out[name + json.dumps(args, ensure_ascii=False)] = (
                    res.is_error, json.loads(res.content[0].text) if not res.is_error else res.content[0].text)
            return out


def test_mcp_tools_with_agent_acl(backend):
    url, kid = backend
    calls = [
        ("list_scopes", {}),
        ("search_evidence", {"query": "年假有几天"}),
        ("search_evidence", {"query": "一线城市住宿标准"}),
        ("search_evidence", {"query": "审批", "scopes": ["不存在"]}),
    ]
    out = asyncio.run(_session_calls(url, "staff", calls))
    assert out["tools"] == {"list_knowledge_bases", "list_scopes", "search_evidence", "read_context"}

    _, scopes = out['list_scopes{}']
    assert {t["name"] for t in scopes["facets"]["topic"]} == {"报销", "休假"}

    _, leave = out['search_evidence{"query": "年假有几天"}']
    assert leave["evidence"][0]["source"] == "hr.md" and leave["evidence"][0]["ref"] == "E1"
    assert leave["sufficiency"] in ("sufficient", "weak") and "休假" in leave["query_tags"]

    # staff 组的 Agent 看不到仅限 finance 的文档
    _, stay = out['search_evidence{"query": "一线城市住宿标准"}']
    assert all(e["source"] != "finance.md" for e in stay["evidence"])

    is_err, msg = out['search_evidence{"query": "审批", "scopes": ["不存在"]}']
    assert is_err and "list_scopes" in msg

    # finance 组的 Agent 能看到，并能展开上下文；调用被记入审计日志
    out = asyncio.run(_session_calls(url, "finance", [("search_evidence", {"query": "一线城市住宿标准"})]))
    _, stay = out['search_evidence{"query": "一线城市住宿标准"}']
    top = stay["evidence"][0]
    assert top["source"] == "finance.md" and "600" in top["text"]
    ctx = asyncio.run(_session_calls(url, "finance", [
        ("read_context", {"document_id": top["document_id"], "chunk_id": top["chunk_id"]})]))
    _, context = list(ctx.values())[-1]
    assert any(c["is_target"] and "600" in c["text"] for c in context["chunks"])
