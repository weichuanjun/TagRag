from app.ingestion.chunker import chunk_blocks
from app.ingestion.parsers import parse_html, parse_markdown, parse_plaintext
from app.retrieval.index import BM25
from app.text import tokenize


def test_markdown_heading_path():
    blocks = parse_markdown("# A\n内容一\n## B\n内容二\n```\n# 不是标题\n```\n")
    assert blocks[0].headings == ["A"]
    assert blocks[1].headings == ["A", "B"] and "# 不是标题" in blocks[1].text


def test_chinese_numbered_headings():
    blocks = parse_plaintext("第一章 总则\n本制度适用于全体员工。\n一、适用范围\n全体正式员工。")
    assert blocks[-1].headings == ["第一章 总则", "一、适用范围"]


def test_html_parse():
    blocks = parse_html("<h1>标题</h1><script>x()</script><p>正文内容</p>")
    assert blocks[0].headings == ["标题"] and "x()" not in blocks[0].text


def test_chunker_respects_budget():
    text = "。".join(f"这是第{i}句话，内容用于测试切块逻辑" for i in range(200))
    drafts = chunk_blocks(parse_markdown(f"# 标题\n{text}"), chunk_tokens=120, overlap_tokens=20)
    assert len(drafts) > 3
    assert all(d.token_count <= 160 for d in drafts)
    assert all(d.heading_path == "标题" for d in drafts)


def test_bm25_ranks_relevant_first():
    docs = ["年假需要提前申请", "住宿费标准每晚六百元", "采购需要比价"]
    bm = BM25([tokenize(d) for d in docs])
    scores = bm.scores(tokenize("住宿标准"))
    assert scores.argmax() == 1
