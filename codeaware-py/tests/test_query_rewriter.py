"""P3-3：QueryRewriter - 改写+变体（ainvoke + JSON 数组解析）。"""

from app.ai.rag.query_rewriter import QueryRewriter


class _LLM:
    def __init__(self, content):
        self._c = content

    async def ainvoke(self, prompt, **kw):
        class _R:
            def __init__(self, c):
                self.content = c

        return _R(self._c)


async def test_rewrite_parses_json_array():
    rw = QueryRewriter(_LLM('["缓存穿透 解决方案","布隆过滤器 缓存空值","缓存穿透 如何修复"]'))
    res = await rw.rewrite("这玩意怎么跑起来")
    assert res[0] == "缓存穿透 解决方案"
    assert len(res) == 3


async def test_rewrite_fallback_on_invalid():
    rw = QueryRewriter(_LLM("不是 JSON"))
    res = await rw.rewrite("原始查询")
    assert res == ["原始查询"]
