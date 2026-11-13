from conftest import wait_ready

POLICY = """# 差旅报销制度

## 住宿标准
一线城市住宿费每晚不超过600元，其他城市每晚不超过400元。超出部分由员工自理。

## 交通标准
高铁二等座、飞机经济舱可直接报销。乘坐出租车需在报销单中注明事由。

# 采购管理办法

## 采购审批
单笔采购金额超过5万元，需要提交采购委员会审批，并至少比价三家供应商。
"""

HR = """# 员工休假制度

## 年假
员工入职满一年后享有5天带薪年假，满十年享有10天年假。年假需提前一周在OA系统申请。

## 病假
病假需提供医院证明，三天以内由直属主管审批。
"""


def _setup(client):
    kb = client.post("/api/kbs", json={"name": "制度库"}).json()
    kid = kb["id"]
    items = [
        {"name": "财务", "facet": "department"},
        {"name": "人力资源", "facet": "department", "aliases": ["HR", "人事"]},
        {"name": "报销", "facet": "topic", "parent": "财务", "aliases": ["差旅费"]},
        {"name": "采购", "facet": "topic", "parent": "财务"},
        {"name": "休假", "facet": "topic", "parent": "人力资源", "aliases": ["年假", "请假"]},
    ]
    r = client.post(f"/api/kbs/{kid}/tags/import", json=items)
    assert r.status_code == 201, r.text
    tags = {t["name"]: t for t in client.get(f"/api/kbs/{kid}/tags").json()}
    return kid, tags


def _upload(client, kid, name, text, **form):
    r = client.post(f"/api/kbs/{kid}/documents", files=[("files", (name, text.encode(), "text/markdown"))],
                    data=form)
    assert r.status_code == 201, r.text
    return r.json()[0]


def test_ingest_tag_and_answer(client):
    kid, tags = _setup(client)
    _upload(client, kid, "finance.md", POLICY)
    _upload(client, kid, "hr.md", HR, tag_ids=str(tags["人力资源"]["id"]))
    docs = wait_ready(client, kid)
    assert all(d["status"] == "ready" for d in docs), docs

    # chunk 级标签：住宿标准那块应有「报销」，年假那块应继承「人力资源」并命中「休假」
    fin = next(d for d in docs if d["filename"] == "finance.md")
    chunks = client.get(f"/api/kbs/{kid}/documents/{fin['id']}/chunks").json()
    assert any("差旅报销制度" in c["heading_path"] and "住宿标准" in c["text"] for c in chunks)
    stay = next(c for c in chunks if "住宿" in c["text"])
    assert "报销" in {t["name"] for t in stay["tags"]}

    hr = next(d for d in docs if d["filename"] == "hr.md")
    hr_chunks = client.get(f"/api/kbs/{kid}/documents/{hr['id']}/chunks").json()
    names = {t["name"] for c in hr_chunks for t in c["tags"]}
    assert {"人力资源", "休假"} <= names

    # 查询标签匹配（别名「年假」->「休假」）+ 检索
    res = client.post(f"/api/kbs/{kid}/search", json={"query": "年假有几天？"}).json()
    assert "休假" in {t["name"] for t in res["query_tags"]}
    assert "年假" in res["results"][0]["text"]

    # 问答（无 LLM 时为抽取式降级），带来源与日志
    ans = client.post(f"/api/kbs/{kid}/chat", json={"query": "一线城市住宿每晚多少钱"}).json()
    assert ans["sources"] and "600" in ans["sources"][0]["text"]
    assert client.post(f"/api/feedback/{ans['log_id']}", json={"rating": 1}).status_code == 200


def test_hard_filter_includes_descendants(client):
    kid, tags = _setup(client)
    _upload(client, kid, "finance.md", POLICY)
    _upload(client, kid, "hr.md", HR)
    wait_ready(client, kid)
    # 过滤「财务」应包含子标签「报销」「采购」的内容，且不含 HR
    res = client.post(f"/api/kbs/{kid}/search",
                      json={"query": "审批", "filter_tag_ids": [tags["财务"]["id"]]}).json()
    assert res["results"]
    assert all(r["filename"] == "finance.md" for r in res["results"])


def test_acl_filtering(client):
    kid, _ = _setup(client)
    _upload(client, kid, "finance.md", POLICY, acl_groups="finance")
    _upload(client, kid, "hr.md", HR)
    wait_ready(client, kid)
    # 非 finance 组的用户看不到财务文档
    res = client.post(f"/api/kbs/{kid}/search", json={"query": "住宿费标准"},
                      headers={"X-User-Groups": "sales"}).json()
    assert all(r["filename"] != "finance.md" for r in res["results"])
    docs = client.get(f"/api/kbs/{kid}/documents", headers={"X-User-Groups": "sales"}).json()
    assert [d["filename"] for d in docs] == ["hr.md"]
    res = client.post(f"/api/kbs/{kid}/search", json={"query": "住宿费标准"},
                      headers={"X-User-Groups": "finance"}).json()
    assert res["results"][0]["filename"] == "finance.md"


def test_dedupe_and_delete(client):
    kid, _ = _setup(client)
    _upload(client, kid, "a.md", HR)
    dup = _upload(client, kid, "b.md", HR)
    assert dup["duplicate"] is True
    docs = wait_ready(client, kid)
    assert len(docs) == 1
    assert client.delete(f"/api/kbs/{kid}/documents/{docs[0]['id']}").json()["ok"]
    res = client.post(f"/api/kbs/{kid}/search", json={"query": "年假"}).json()
    assert res["results"] == []


def test_tag_governance(client):
    kid, tags = _setup(client)
    _upload(client, kid, "hr.md", HR)
    wait_ready(client, kid)
    # 候选标签不参与检索；审核通过后可用；合并后原名变别名
    cand = client.post(f"/api/kbs/{kid}/tags", json={"name": "带薪假", "status": "candidate"}).json()
    res = client.post(f"/api/kbs/{kid}/search", json={"query": "带薪假"}).json()
    assert "带薪假" not in {t["name"] for t in res["query_tags"]}
    client.post(f"/api/kbs/{kid}/tags/{cand['id']}/approve")
    merged = client.post(f"/api/kbs/{kid}/tags/{cand['id']}/merge/{tags['休假']['id']}").json()
    assert "带薪假" in merged["aliases"]
    # 名称冲突与循环父子关系被拒绝
    assert client.post(f"/api/kbs/{kid}/tags", json={"name": "HR"}).status_code == 409
    r = client.patch(f"/api/kbs/{kid}/tags/{tags['财务']['id']}", json={"parent_id": tags["报销"]["id"]})
    assert r.status_code == 400
    # 冷启动建议（无 LLM 时基于词频），进入候选池
    sugg = client.post(f"/api/kbs/{kid}/tags/suggest").json()
    assert all(t["status"] == "candidate" for t in sugg)
    assert client.post(f"/api/kbs/{kid}/retag").json()["ok"]


def test_stream_endpoint(client):
    kid, _ = _setup(client)
    _upload(client, kid, "hr.md", HR)
    wait_ready(client, kid)
    with client.stream("POST", f"/api/kbs/{kid}/chat/stream", json={"query": "病假怎么审批"}) as r:
        body = "".join(r.iter_text())
    assert "event: meta" in body and "event: delta" in body and "event: done" in body


def test_no_context_refuses(client):
    kid, _ = _setup(client)
    ans = client.post(f"/api/kbs/{kid}/chat", json={"query": "公司股价是多少"}).json()
    assert ans["sources"] == [] and "没有找到" in ans["answer"]
