"""RouteRouter - LangGraph 智能路由：区分"需要检索"和"常识/闲聊直接回答"。

LLM 单次判断 route ∈ {retrieve, direct}。失败降级 retrieve（宁可多检索不漏）。
使用 with_structured_output json_mode（DeepSeek thinking 兼容）。
"""

import logging
from typing import Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)

RouteType = Literal["retrieve", "direct"]


class _RouteResult(BaseModel):
    route: RouteType = "retrieve"


class RouteRouter:
    def __init__(self, chat_model) -> None:
        self.chat_model = chat_model

    async def decide(self, message: str) -> RouteType:
        """判断消息是否需要检索知识库。

        - retrieve：问题可能由知识库文档回答（技术/规范/项目资料相关）
        - direct：常识/闲聊/与知识库无关（今天天气、你是谁、谢谢等）
        """
        # 注意：json_object response_format 要求 prompt 必须出现 "json" 字眼，
        # 否则 DeepSeek 返回 400（Prompt must contain the word 'json'）。
        prompt = (
            "你是知识库问答系统的路由判断器。判断用户问题是否需要检索项目知识库。\n"
            "规则：\n"
            "1. 技术问题（缓存、架构、编码规范、框架、系统设计）→ retrieve\n"
            "2. 需要参考项目文档或资料的问题 → retrieve\n"
            "3. 常识问答、闲聊、问候、与项目无关的话题（天气、美食、个人信息等）→ direct\n"
            "4. 不确定时选择 retrieve（宁可多检索，不漏检）\n"
            "请只输出一个 JSON 对象，格式如下，不要输出任何其他内容：\n"
            '{"route": "retrieve"} 或 {"route": "direct"}\n\n'
            f"用户问题：{message}"
        )
        try:
            structured = self.chat_model.with_structured_output(_RouteResult, method="json_mode")
            resp = await structured.ainvoke(prompt)
            route = resp.route if hasattr(resp, "route") else "retrieve"
            if route not in ("retrieve", "direct"):
                route = "retrieve"
            return route
        except Exception as exc:
            logger.warning(
                "route router degraded code=ROUTE_DECIDE_FAILED type=%s route=retrieve",
                type(exc).__name__,
            )
            return "retrieve"
