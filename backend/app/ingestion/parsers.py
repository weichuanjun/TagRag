"""文档解析：把各种格式统一成带「标题路径」的结构化段落块（Block）。

保留标题层级是关键：标题路径既用于切块边界，也会拼接到 chunk 前面参与 embedding 和打标，
显著提升召回（「报销制度 > 差旅 > 住宿标准」比孤立的一段话信息量大得多）。
"""
import csv
import io
import os
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import List, Optional


@dataclass
class Block:
    headings: List[str] = field(default_factory=list)
    text: str = ""
    page: Optional[int] = None


SUPPORTED_EXTENSIONS = {".md", ".markdown", ".txt", ".pdf", ".docx", ".html", ".htm", ".csv", ".xlsx"}

_MD_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
# 中文常见编号标题：第一章 / 一、 / （一） / 1. / 1.1 / 1.1.1
_CN_HEADINGS = [
    (1, re.compile(r"^第[一二三四五六七八九十百零\d]+[章部篇]\s*\S.{0,40}$")),
    (2, re.compile(r"^第[一二三四五六七八九十百零\d]+[节条]\s*\S.{0,40}$")),
    (2, re.compile(r"^[一二三四五六七八九十]+、\s*\S.{0,40}$")),
    (3, re.compile(r"^[（(][一二三四五六七八九十]+[)）]\s*\S.{0,40}$")),
    (2, re.compile(r"^\d+[\.、]\s*[^\d\s].{0,40}$")),
    (3, re.compile(r"^\d+\.\d+\s+\S.{0,40}$")),
    (4, re.compile(r"^\d+\.\d+\.\d+\s+\S.{0,40}$")),
]


def parse_file(path: str, filename: Optional[str] = None) -> List[Block]:
    ext = os.path.splitext(filename or path)[1].lower()
    if ext in (".md", ".markdown"):
        return parse_markdown(_read_text(path))
    if ext == ".txt":
        return parse_plaintext(_read_text(path))
    if ext == ".pdf":
        return parse_pdf(path)
    if ext == ".docx":
        return parse_docx(path)
    if ext in (".html", ".htm"):
        return parse_html(_read_text(path))
    if ext == ".csv":
        return parse_csv(_read_text(path))
    if ext == ".xlsx":
        return parse_xlsx(path)
    raise ValueError(f"不支持的文件类型: {ext}")


def _read_text(path: str) -> str:
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="ignore")


class _HeadingStack:
    def __init__(self):
        self.stack: List[tuple] = []  # (level, title)

    def push(self, level: int, title: str):
        while self.stack and self.stack[-1][0] >= level:
            self.stack.pop()
        self.stack.append((level, title.strip()))

    @property
    def path(self) -> List[str]:
        return [t for _, t in self.stack]


def _flush(blocks: List[Block], hs: _HeadingStack, buf: List[str], page=None):
    text = "\n".join(buf).strip()
    if text:
        blocks.append(Block(headings=hs.path, text=text, page=page))
    buf.clear()


def parse_markdown(text: str) -> List[Block]:
    blocks: List[Block] = []
    hs, buf = _HeadingStack(), []
    in_code = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            buf.append(line)
            continue
        m = None if in_code else _MD_HEADING.match(line)
        if m:
            _flush(blocks, hs, buf)
            hs.push(len(m.group(1)), m.group(2))
        else:
            buf.append(line)
    _flush(blocks, hs, buf)
    return blocks


def _cn_heading_level(line: str) -> Optional[int]:
    s = line.strip()
    if not s or len(s) > 45 or s.endswith(("。", "；", ";", "，", ",")):
        return None
    for level, pat in _CN_HEADINGS:
        if pat.match(s):
            return level
    return None


def parse_plaintext(text: str) -> List[Block]:
    if any(_MD_HEADING.match(l) for l in text.splitlines()[:200]):
        return parse_markdown(text)
    blocks: List[Block] = []
    hs, buf = _HeadingStack(), []
    for line in text.splitlines():
        lvl = _cn_heading_level(line)
        if lvl:
            _flush(blocks, hs, buf)
            hs.push(lvl, line.strip())
        else:
            buf.append(line)
    _flush(blocks, hs, buf)
    return blocks


def parse_pdf(path: str) -> List[Block]:
    from pypdf import PdfReader
    reader = PdfReader(path)
    blocks: List[Block] = []
    hs = _HeadingStack()
    for i, page in enumerate(reader.pages, start=1):
        buf: List[str] = []
        for line in (page.extract_text() or "").splitlines():
            lvl = _cn_heading_level(line)
            if lvl:
                _flush(blocks, hs, buf, page=i)
                hs.push(lvl, line.strip())
            else:
                buf.append(line)
        _flush(blocks, hs, buf, page=i)
    return blocks


def parse_docx(path: str) -> List[Block]:
    import docx  # python-docx
    d = docx.Document(path)
    blocks: List[Block] = []
    hs, buf = _HeadingStack(), []
    body = d.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            para = docx.text.paragraph.Paragraph(child, d)
            style = (para.style.name if para.style is not None else "") or ""
            text = para.text.strip()
            m = re.match(r"(?:Heading|标题)\s*(\d)", style)
            if m and text:
                _flush(blocks, hs, buf)
                hs.push(int(m.group(1)), text)
            elif style == "Title" and text:
                _flush(blocks, hs, buf)
                hs.push(0, text)
            elif text:
                buf.append(text)
        elif tag == "tbl":
            table = docx.table.Table(child, d)
            buf.append(_table_to_text([[c.text.strip() for c in r.cells] for r in table.rows]))
    _flush(blocks, hs, buf)
    return blocks


class _HTMLToBlocks(HTMLParser):
    def __init__(self):
        super().__init__()
        self.blocks: List[Block] = []
        self.hs, self.buf = _HeadingStack(), []
        self._skip = 0
        self._heading_level: Optional[int] = None
        self._heading_text: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1
        elif re.fullmatch(r"h[1-6]", tag):
            _flush(self.blocks, self.hs, self.buf)
            self._heading_level, self._heading_text = int(tag[1]), []
        elif tag in ("p", "br", "li", "tr", "div"):
            self.buf.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self._skip = max(0, self._skip - 1)
        elif re.fullmatch(r"h[1-6]", tag) and self._heading_level:
            self.hs.push(self._heading_level, "".join(self._heading_text))
            self._heading_level = None

    def handle_data(self, data):
        if self._skip:
            return
        if self._heading_level:
            self._heading_text.append(data)
        else:
            self.buf.append(data)

    def close(self):
        super().close()
        text = re.sub(r"\n\s*\n+", "\n", "".join(self.buf))
        self.buf = [text]
        _flush(self.blocks, self.hs, self.buf)


def parse_html(text: str) -> List[Block]:
    p = _HTMLToBlocks()
    p.feed(text)
    p.close()
    return p.blocks


def _table_to_text(rows: List[List[str]], header: Optional[List[str]] = None) -> str:
    """表格按「列名: 值」逐行展开，避免切块后丢失表头语义。"""
    rows = [r for r in rows if any(c for c in r)]
    if not rows:
        return ""
    if header is None:
        header, rows = rows[0], rows[1:]
    lines = []
    for r in rows:
        pairs = [f"{h or f'列{j + 1}'}: {v}" for j, (h, v) in enumerate(zip(header, r)) if str(v).strip()]
        lines.append("；".join(pairs))
    return "\n".join(lines) if lines else " | ".join(header)


def parse_csv(text: str) -> List[Block]:
    rows = list(csv.reader(io.StringIO(text)))
    return [Block(headings=[], text=_table_to_text(rows))] if rows else []


def parse_xlsx(path: str) -> List[Block]:
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    blocks = []
    for ws in wb.worksheets:
        rows = [["" if v is None else str(v) for v in row] for row in ws.iter_rows(values_only=True)]
        text = _table_to_text(rows)
        if text:
            blocks.append(Block(headings=[ws.title], text=text))
    return blocks
