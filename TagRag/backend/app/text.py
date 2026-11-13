"""文本工具：分词与 token 估算。

中文分词默认使用「单字 + 相邻二元组」，对 BM25 来说召回稳健且零依赖；
如安装了 jieba 会额外加入词级 token。
"""
import re
from typing import List

try:  # 可选依赖
    import jieba  # type: ignore
    jieba.setLogLevel(60)
except Exception:  # pragma: no cover
    jieba = None

_CJK = r"一-鿿㐀-䶿豈-﫿"
_TOKEN_RE = re.compile(rf"[{_CJK}]+|[A-Za-z0-9_][A-Za-z0-9_\-\.]*")
_CJK_RE = re.compile(rf"[{_CJK}]")

STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "或", "及", "等", "对", "把", "被", "我", "你", "他", "她", "它",
    "我们", "你们", "什么", "怎么", "如何", "哪些", "哪个", "吗", "呢", "吧", "啊", "请", "一下",
    "the", "a", "an", "of", "to", "in", "is", "are", "and", "or", "for", "on", "with", "how", "what",
}


def tokenize(text: str) -> List[str]:
    tokens: List[str] = []
    for seg in _TOKEN_RE.findall(text.lower()):
        if _CJK_RE.match(seg):
            chars = [c for c in seg]
            tokens.extend(c for c in chars if c not in STOPWORDS)
            tokens.extend(seg[i:i + 2] for i in range(len(seg) - 1))
            if jieba is not None and len(seg) > 2:
                tokens.extend(w for w in jieba.cut(seg) if len(w) > 2 and w not in STOPWORDS)
        elif seg not in STOPWORDS:
            tokens.append(seg.strip(".-"))
    return [t for t in tokens if t]


def count_tokens(text: str) -> int:
    """近似 token 数：CJK 每字约 1 token，英文单词约 1.3 token。"""
    cjk = len(_CJK_RE.findall(text))
    words = len(re.findall(r"[A-Za-z0-9]+", text))
    return int(cjk + words * 1.3 + 1)
