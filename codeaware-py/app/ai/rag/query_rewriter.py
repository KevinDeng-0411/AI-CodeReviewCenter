"""QueryRewriter - 查询改写 + 变体（ainvoke + JSON 数组解析）。

用 ainvoke + 手写 JSON 数组解析，避免 with_structured_output 在 DeepSeek thinking
模式下的兼容问题（见 docs/integration/deepseek-notes.md）。
"""

import json
import logging
import re

logger = logging.getLogger(__name__)


class QueryRewriter:
    _MAX_QUERIES = 4
    _MAX_QUERY_CHARS = 1_000

    def __init__(self, chat_model) -> None:
        self.chat_model = chat_model

    async def rewrite(self, query: str, *, failure_hint: str | None = None) -> list[str]:
        """改写为搜索友好格式 + 2-3 变体。返回 [主查询, 变体1, ...]。

        failure_hint：LangGraph 自我纠错重试时传入"上次检索失败"信息，
        让模型从不同角度改写（防原地打转）。service 路径不传，行为不变。
        """
        hint = (
            f"\n\n附加要求：{failure_hint}" if failure_hint else ""
        )
        prompt = (
            "你是一个查询优化专家。请将用户的搜索查询改写为更适合文档检索的格式。\n"
            "规则：\n1. 修正口语化表达为正式技术用语\n2. 补充缺失的上下文关键词\n"
            "3. 过于简短则扩展为完整技术问题\n4. 生成 2-3 个语义相近但表述不同的变体\n\n"
            f"用户查询：{query}\n"
            f"{hint}\n\n"
            '请以 JSON 数组返回，第一个为增强后的主查询，后续为变体：["增强主查询","变体1","变体2"]'
        )
        try:
            resp = await self.chat_model.ainvoke(prompt)
            text = resp.content if hasattr(resp, "content") else str(resp)
        except Exception as exc:
            logger.warning(
                "query rewrite degraded code=QUERY_REWRITE_FAILED type=%s",
                type(exc).__name__,
            )
            return [query]
        parsed = self._parse(text, query)
        if parsed == [query]:
            logger.warning(
                "query rewrite degraded code=QUERY_REWRITE_INVALID_OUTPUT"
            )
        return parsed

    @classmethod
    def _parse(cls, text: str, fallback: str) -> list[str]:
        m = re.search(r"\[.*?\]", text, re.S)
        if m:
            try:
                arr = json.loads(m.group())
                if isinstance(arr, list):
                    queries: list[str] = []
                    for item in arr:
                        value = str(item).strip()
                        if (
                            value
                            and len(value) <= cls._MAX_QUERY_CHARS
                            and value not in queries
                        ):
                            queries.append(value)
                        if len(queries) >= cls._MAX_QUERIES:
                            break
                    if queries:
                        return queries
            except (json.JSONDecodeError, TypeError):
                pass
        return [fallback]
