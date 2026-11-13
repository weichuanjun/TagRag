import json

from conftest import wait_ready


def test_llm_tagging_and_generation(client, monkeypatch):
    from app.config import get_settings
    from app.providers.llm import LLMClient

    monkeypatch.setattr(get_settings(), "llm_api_key", "fake")
    calls = []

    async def fake_chat(self, messages, json_mode=False, temperature=None):
        prompt = messages[-1]["content"]
        calls.append(prompt)
        if "标签分类器" in prompt:
            n = prompt.count("\n[")
            return json.dumps({"results": [
                {"i": i, "tags": ["休假", "不存在的标签"], "new_tags": [{"name": "带薪年假", "facet": "topic"}]}
                for i in range(n + 1)]}, ensure_ascii=False)
        return "员工满一年享有5天年假[1]。"

    monkeypatch.setattr(LLMClient, "chat", fake_chat)

    kid = client.post("/api/kbs", json={"name": "kb"}).json()["id"]
    client.post(f"/api/kbs/{kid}/tags", json={"name": "休假"})
    client.post(f"/api/kbs/{kid}/documents",
                files=[("files", ("hr.md", "# 年假\n入职满一年享有5天带薪年假，满十年享有10天。".encode(), "text/markdown"))])
    docs = wait_ready(client, kid)
    assert docs[0]["status"] == "ready", docs

    chunks = client.get(f"/api/kbs/{kid}/documents/{docs[0]['id']}/chunks").json()
    tag = next(t for t in chunks[0]["tags"] if t["name"] == "休假")
    assert tag["source"] == "llm"
    cands = client.get(f"/api/kbs/{kid}/tags", params={"status": "candidate"}).json()
    assert [c["name"] for c in cands] == ["带薪年假"]

    ans = client.post(f"/api/kbs/{kid}/chat", json={"query": "年假几天"}).json()
    assert ans["answer"].startswith("员工满一年") and ans["cited"] == [1]
    assert "【参考资料】" in calls[-1] and "[1] 来源：hr.md" in calls[-1]
