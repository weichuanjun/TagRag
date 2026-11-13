"""检索评测：对比「纯稠密 / 混合 / 混合+标签」在你自己的问题集上的 Hit@K 与 MRR。

用法（服务已启动）：
    python scripts/evaluate.py --kb 1 --data eval.jsonl [--base http://localhost:8000] [--k 5]

eval.jsonl 每行一个样本，命中条件二选一：
    {"query": "一线城市住宿标准", "expected_doc": "差旅报销制度.pdf"}
    {"query": "年假几天", "expected_text": "5天带薪年假"}

提示：问答页面「👎」反馈会记录在 query_logs 表，可整理成评测集。
"""
import argparse
import json

import httpx

MODES = {
    "hybrid+tags": {"use_tags": True},
    "hybrid": {"use_tags": False},
}


def hit_rank(results, sample):
    for i, r in enumerate(results, start=1):
        if sample.get("expected_doc") and r["filename"] == sample["expected_doc"]:
            return i
        if sample.get("expected_text") and sample["expected_text"] in r["text"]:
            return i
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kb", type=int, required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--api-key", default=None)
    args = ap.parse_args()

    samples = [json.loads(l) for l in open(args.data, encoding="utf-8") if l.strip()]
    headers = {"X-API-Key": args.api_key, "X-User-Groups": "admin"} if args.api_key else {}
    with httpx.Client(base_url=args.base, headers=headers, timeout=60) as c:
        for mode, opts in MODES.items():
            hits, rr = 0, 0.0
            misses = []
            for s in samples:
                res = c.post(f"/api/kbs/{args.kb}/search",
                             json={"query": s["query"], "top_k": args.k, **opts}).json()["results"]
                rank = hit_rank(res, s)
                if rank:
                    hits += 1
                    rr += 1 / rank
                else:
                    misses.append(s["query"])
            n = len(samples) or 1
            print(f"{mode:12s}  Hit@{args.k}={hits / n:.3f}  MRR={rr / n:.3f}  (n={len(samples)})")
            for q in misses[:5]:
                print(f"    miss: {q}")


if __name__ == "__main__":
    main()
