"""jieba 中文分词工具（C4 后续优化：BM25 default tokenizer 不拆中文，应用层预处理）。

分词后空格连接，配合 BM25 default tokenizer（以空格/标点切分），实现中文词级检索。
纯英文/数字文本原样通过，不影响稀有标识符（如 summary_message_count）。
"""

import jieba


def segment_chinese(text: str) -> str:
    """含 CJK 字符时 jieba 分词 + 空格连接；纯 ASCII 原样返回。"""
    if not _has_cjk(text):
        return text
    return " ".join(jieba.cut(text))


def _has_cjk(text: str) -> bool:
    """检测文本是否包含 CJK 统一表意文字（U+4E00-U+9FFF + U+3400-U+4DBF）。"""
    for ch in text:
        cp = ord(ch)
        if 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF:
            return True
    return False
