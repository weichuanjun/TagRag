"""结构感知切块：不跨章节、按段落/句子边界、带重叠。"""
import re
from dataclasses import dataclass
from typing import List, Optional

from ..text import count_tokens
from .parsers import Block

_SENT_SPLIT = re.compile(r"(?<=[。！？；!?;])|(?<=\.)\s+|\n")


@dataclass
class ChunkDraft:
    text: str
    heading_path: str
    token_count: int
    page: Optional[int] = None

    @property
    def embed_text(self) -> str:
        """用于 embedding / 打标的文本：标题路径 + 正文（上下文增强）。"""
        return f"{self.heading_path}\n{self.text}" if self.heading_path else self.text


def _split_long(text: str, max_tokens: int) -> List[str]:
    sentences = [s for s in _SENT_SPLIT.split(text) if s and s.strip()]
    pieces, cur = [], ""
    for s in sentences:
        if count_tokens(s) > max_tokens:  # 超长句子硬切
            if cur:
                pieces.append(cur)
                cur = ""
            step = max(50, max_tokens)
            pieces.extend(s[i:i + step] for i in range(0, len(s), step))
            continue
        if cur and count_tokens(cur + s) > max_tokens:
            pieces.append(cur)
            cur = s
        else:
            cur += s
    if cur.strip():
        pieces.append(cur)
    return pieces


def _tail(text: str, overlap_tokens: int) -> str:
    if overlap_tokens <= 0:
        return ""
    sents = [s for s in _SENT_SPLIT.split(text) if s and s.strip()]
    out = ""
    for s in reversed(sents):
        if count_tokens(s + out) > overlap_tokens:
            break
        out = s + out
    return out


def chunk_blocks(blocks: List[Block], chunk_tokens: int = 450, overlap_tokens: int = 60,
                 min_tokens: int = 40) -> List[ChunkDraft]:
    # 1) 把相邻的小章节合并成一组：标题路径取公共前缀，各自的子标题写入正文
    merged: List[Block] = []
    group: List[Block] = []

    def flush_group():
        if not group:
            return
        if len(group) == 1:
            merged.append(group[0])
        else:
            prefix = group[0].headings
            for g in group[1:]:
                n = 0
                while n < min(len(prefix), len(g.headings)) and prefix[n] == g.headings[n]:
                    n += 1
                prefix = prefix[:n]
            parts = []
            for g in group:
                sub = " > ".join(g.headings[len(prefix):])
                parts.append(f"{sub}\n{g.text}" if sub else g.text)
            merged.append(Block(headings=list(prefix), text="\n".join(parts), page=group[0].page))
        group.clear()

    for b in blocks:
        if count_tokens(b.text) >= min_tokens:
            flush_group()
            merged.append(b)
            continue
        group.append(b)
        if sum(count_tokens(g.text) for g in group) >= min_tokens:
            flush_group()
    flush_group()

    # 2) 章节内按段落累积，超长段落按句子切
    drafts: List[ChunkDraft] = []
    for b in merged:
        path = " > ".join(h for h in b.headings if h)
        paras = [p.strip() for p in re.split(r"\n\s*\n|\n", b.text) if p.strip()]
        units: List[str] = []
        for p in paras:
            units.extend(_split_long(p, chunk_tokens) if count_tokens(p) > chunk_tokens else [p])
        cur = ""
        for u in units:
            if cur and count_tokens(cur) + count_tokens(u) > chunk_tokens:
                drafts.append(ChunkDraft(cur.strip(), path, count_tokens(cur), b.page))
                tail = _tail(cur, overlap_tokens)
                cur = (tail + "\n" if tail else "") + u
            else:
                cur = f"{cur}\n{u}" if cur else u
        if cur.strip():
            drafts.append(ChunkDraft(cur.strip(), path, count_tokens(cur), b.page))
    return drafts
