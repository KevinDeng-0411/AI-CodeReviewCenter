"""P3-3：SemanticChunker - unstructured chunk_by_title（结构感知）。"""


def test_chunk_splits_by_markdown_headers(chunker):
    md = (
        "# 缓存\n## 穿透\n查询不存在的数据。方案：布隆过滤器。\n"
        "## 击穿\n热点Key失效。方案：互斥锁。\n# 性能\n时间复杂度分析。"
    )
    chunks = chunker.chunk(md)
    assert len(chunks) >= 3  # 按标题切出多块
    assert any("穿透" in c for c in chunks)
    assert any("击穿" in c for c in chunks)


def test_chunk_empty(chunker):
    assert chunker.chunk("") == []
    assert chunker.chunk("   ") == []


def test_chunk_plain_text(chunker):
    chunks = chunker.chunk("纯文本无标题，一段话。", content_type="text")
    assert len(chunks) >= 1
    assert "纯文本" in chunks[0]


def test_chunk_non_empty_strings(chunker):
    md = "# A\n内容一\n# B\n内容二"
    chunks = chunker.chunk(md)
    assert all(c.strip() for c in chunks)
