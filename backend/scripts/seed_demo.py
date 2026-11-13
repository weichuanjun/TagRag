"""导入演示数据：一个知识库 + 标签体系 + 三份制度文档（财务文档仅 finance 组可见）。

用法（后端已启动）：python scripts/seed_demo.py [--base http://localhost:8000]
"""
import argparse
import os
import time

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
TAXONOMY = [
    {"name": "财务", "facet": "department", "description": "财务部负责的制度与流程"},
    {"name": "人力资源", "facet": "department", "aliases": ["HR", "人事"], "description": "人力资源部负责的制度"},
    {"name": "报销", "facet": "topic", "parent": "财务", "aliases": ["差旅费", "费用报销"], "description": "差旅与费用报销标准和流程"},
    {"name": "采购", "facet": "topic", "parent": "财务", "aliases": ["供应商"], "description": "采购审批与供应商管理"},
    {"name": "休假", "facet": "topic", "parent": "人力资源", "aliases": ["年假", "请假", "病假", "婚假"], "description": "各类假期规定"},
]
DOCS = [("差旅报销制度.md", "finance"), ("采购管理办法.md", "finance"), ("员工休假制度.md", "")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8000")
    args = ap.parse_args()
    with httpx.Client(base_url=args.base, timeout=60) as c:
        kbs = {k["name"]: k for k in c.get("/api/kbs").json()}
        kb = kbs.get("演示：公司制度库") or c.post("/api/kbs", json={
            "name": "演示：公司制度库", "description": "TagRAG 演示数据"}).json()
        kid = kb["id"]
        c.post(f"/api/kbs/{kid}/tags/import", json=TAXONOMY).raise_for_status()
        for name, acl in DOCS:
            with open(os.path.join(HERE, "demo_docs", name), "rb") as f:
                r = c.post(f"/api/kbs/{kid}/documents", data={"acl_groups": acl},
                           files=[("files", (name, f.read(), "text/markdown"))])
            r.raise_for_status()
        for _ in range(100):
            docs = c.get(f"/api/kbs/{kid}/documents").json()
            if docs and all(d["status"] in ("ready", "failed") for d in docs):
                break
            time.sleep(0.2)
        for d in docs:
            print(f"{d['filename']}: {d['status']}  标签={[t['name'] for t in d['tags']]}  权限={d['acl_groups'] or '公开'}")
        print(f"知识库 ID = {kid}")


if __name__ == "__main__":
    main()
