"""Claude 提供方：用假的 Anthropic 客户端记录请求参数，验证打标 / 作答 / 流式 / 拒答的完整链路。"""
import json
from types import SimpleNamespace

import pytest

from conftest import wait_ready


def _msg(text, stop_reason="end_turn"):
    return SimpleNamespace(content=[SimpleNamespace(type="thinking", thinking=""),
                                    SimpleNamespace(type="text", text=text)],
                           stop_reason=stop_reason,
                           stop_details=SimpleNamespace(category="general_harms") if stop_reason == "refusal" else None)


class FakeStream:
    def __init__(self, parts, final):
        self.parts, self.final = parts, final

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    @property
    def text_stream(self):
        async def gen():
            for p in self.parts:
                yield p
        return gen()

    async def get_final_message(self):
        return self.final


class FakeAnthropic:
    def __init__(self, answer="员工满一年享有5天年假[1]。", refuse=False):
        self.calls = []
        self.answer, self.refuse = answer, refuse
        outer = self

        class Messages:
            async def create(self, **kw):
                outer.calls.append(kw)
                if "format" in kw["output_config"]:
                    n = kw["messages"][-1]["content"].count("\n[") + 1
                    return _msg(json.dumps({"results": [
                        {"i": i, "tags": ["休假", "不存在的标签"], "new_tags": [{"name": "带薪年假", "facet": "topic"}]}
                        for i in range(n)]}, ensure_ascii=False))
                return _msg("", "refusal") if outer.refuse else _msg(outer.answer)

            def stream(self, **kw):
                outer.calls.append(kw)
                return FakeStream(["员工满一年", "享有5天年假[1]。"], _msg(outer.answer))

        self.beta = SimpleNamespace(messages=Messages())


@pytest.fixture()
def fake_claude(client, monkeypatch):
    from app.providers.claude import ClaudeLLM
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    fake = FakeAnthropic()
    monkeypatch.setattr(ClaudeLLM, "client", property(lambda self: fake))
    return fake


def _setup(client):
    kid = client.post("/api/kbs", json={"name": "kb"}).json()["id"]
    client.post(f"/api/kbs/{kid}/tags", json={"name": "休假"})
    client.post(f"/api/kbs/{kid}/documents",
                files=[("files", ("hr.md", "# 年假\n入职满一年享有5天带薪年假，满十年享有10天。".encode(), "text/markdown"))])
    docs = wait_ready(client, kid)
    assert docs[0]["status"] == "ready", docs
    return kid, docs[0]["id"]


def test_claude_tagging_and_answer(client, fake_claude):
    assert client.get("/api/health").json()["llm"] == "claude:claude-opus-5-5"
    kid, doc_id = _setup(client)

    # 打标请求：结构化输出 + low effort + 可缓存的 system + 拒答兜底；不发送 temperature
    tag_call = fake_claude.calls[0]
    assert tag_call["model"] == "claude-opus-5-5"
    assert tag_call["output_config"]["effort"] == "low"
    assert tag_call["output_config"]["format"]["type"] == "json_schema"
    assert tag_call["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "休假" in tag_call["system"][0]["text"]
    assert tag_call["fallbacks"] == "default" and tag_call["betas"] == ["server-side-fallback-2026-07-01"]
    assert "temperature" not in tag_call and "thinking" not in tag_call

    chunks = client.get(f"/api/kbs/{kid}/documents/{doc_id}/chunks").json()
    assert next(t for t in chunks[0]["tags"] if t["name"] == "休假")["source"] == "llm"
    cands = client.get(f"/api/kbs/{kid}/tags", params={"status": "candidate"}).json()
    assert [c["name"] for c in cands] == ["带薪年假"]

    # 作答：medium effort，参考资料带编号，历史以 user 开头
    ans = client.post(f"/api/kbs/{kid}/chat", json={
        "query": "年假几天", "history": [{"role": "assistant", "content": "你好"}]}).json()
    assert ans["answer"].startswith("员工满一年") and ans["cited"] == [1]
    call = fake_claude.calls[-1]
    assert call["output_config"] == {"effort": "medium"}
    assert call["messages"][0]["role"] == "user" and "[1] 来源：hr.md" in call["messages"][-1]["content"]

    # 流式
    with client.stream("POST", f"/api/kbs/{kid}/chat/stream", json={"query": "年假几天"}) as r:
        body = "".join(r.iter_text())
    assert "享有5天年假" in body and "event: done" in body
    assert fake_claude.calls[-1]["max_tokens"] == 64000


def test_claude_refusal_is_reported(client, fake_claude):
    kid, _ = _setup(client)
    fake_claude.refuse = True
    ans = client.post(f"/api/kbs/{kid}/chat", json={"query": "年假几天"}).json()
    assert "拒绝回答" in ans["answer"]
