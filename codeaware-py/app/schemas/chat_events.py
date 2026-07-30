"""C1-A: typed SSE 事件契约 - 冻结 Chat 流式协议。

所有事件继承 ChatEventBase（protocol_version/conversation_id/turn_id/sequence）。
事件类型只由 SSE `event:` 行承载；data 是单行 JSON。SSE `id` 必须等于十进制 sequence。
sequence 从 1 开始、单 stream 内严格递增。
"""

from typing import Literal

from pydantic import BaseModel, Field

ProtocolVersion = Literal[1]

# phase: 失败发生的阶段
Phase = Literal["start", "context", "model", "persist", "post_turn", "cancelled"]
# component: 降级发生的子系统（不用异常类名）
Component = Literal[
    "message_cache",
    "summary_cache",
    "memory_recall",
    "rag_retrieval",
    "summary",
    "memory_extraction",
]


class ChatEventBase(BaseModel):
    protocol_version: ProtocolVersion = 1
    conversation_id: str
    turn_id: str
    sequence: int = Field(ge=1)


class ChatStarted(ChatEventBase):
    """首事件：Conversation + USER Message 已 PG commit。"""

    created: bool  # 是否新建了会话


class ContextWarning(ChatEventBase):
    """上下文增益降级（出现在 started 之后、模型完成之前）。"""

    component: Component
    code: str
    message: str
    retryable: bool


class TokenDelta(ChatEventBase):
    """单个非空模型 chunk；delta 原样 JSON 编码，不 trim。"""

    delta: str = Field(min_length=1)


class PostTurnWarning(ChatEventBase):
    """assistant 已持久化后的 post-turn 降级（摘要/记忆/缓存刷新）。"""

    component: Component
    code: str
    message: str
    retryable: bool


class ErrorInfo(BaseModel):
    code: str
    message: str
    retryable: bool


class ChatCompleted(ChatEventBase):
    """成功终态：assistant 已 commit，post-turn 已完成或转 warning。"""

    assistant_message_id: int = Field(ge=1)
    warning_count: int = Field(ge=0)


class ChatFailed(ChatEventBase):
    """失败终态：partial assistant 固定不持久化。"""

    phase: Phase
    error: ErrorInfo
    partial_output_persisted: Literal[False] = False


# 事件名 -> 类型映射（供序列化/反序列化对齐）
EVENT_TYPES = {
    "chat.started": ChatStarted,
    "context.warning": ContextWarning,
    "token.delta": TokenDelta,
    "post_turn.warning": PostTurnWarning,
    "chat.completed": ChatCompleted,
    "chat.failed": ChatFailed,
}
