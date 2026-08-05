"""Chat API - /api/chat（核心域，C1-A typed SSE + TurnCoordinator）。"""

import anyio
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.services.chat import ChatService
from app.ai.services.turn_coordinator import (
    ChatConversationNotFound,
    ChatTurnFailed,
    ChatTurnInProgress,
    ChatTurnStartFailed,
    TurnCoordinator,
)
from app.api.v1.deps import get_chat_service, get_current_user, get_db, get_turn_coordinator
from app.core.response import Result
from app.models import Conversation, Message, User
from app.schemas.chat import (
    ChatMessageVO,
    ChatRequest,
    ChatResponseVO,
    ConversationItem,
)
from app.schemas.chat_events import EVENT_TYPES

router = APIRouter(prefix="/api/chat", tags=["Chat"])

# 事件类 -> SSE event 名
_EVENT_NAME = {cls: name for name, cls in EVENT_TYPES.items()}

_CHAT_COMMON_ERROR_RESPONSES = {
    422: {
        "model": Result[None],
        "description": "请求字段校验失败",
        "content": {
            "application/json": {
                "example": {
                    "code": 0,
                    "msg": "CHAT_REQUEST_INVALID",
                    "data": None,
                }
            }
        },
    },
    404: {
        "model": Result[None],
        "description": "conversation_id 不存在",
        "content": {
            "application/json": {
                "example": {
                    "code": 0,
                    "msg": "CHAT_CONVERSATION_NOT_FOUND",
                    "data": None,
                }
            }
        },
    },
    409: {
        "model": Result[None],
        "description": "同一会话已有 turn 正在执行",
        "content": {
            "application/json": {
                "example": {
                    "code": 0,
                    "msg": "CHAT_TURN_IN_PROGRESS",
                    "data": None,
                }
            }
        },
    },
}

_SYNC_CHAT_ERROR_RESPONSES = {
    **_CHAT_COMMON_ERROR_RESPONSES,
    500: {
        "model": Result[None],
        "description": "初始化失败或同步 Chat 核心失败",
        "content": {
            "application/json": {
                "examples": {
                    code: {
                        "summary": code,
                        "value": {"code": 0, "msg": code, "data": None},
                    }
                    for code in [
                        "CHAT_START_FAILED",
                        "CONTEXT_FAILED",
                        "MODEL_STREAM_FAILED",
                        "PERSIST_FAILED",
                        "POST_TURN_FAILED",
                    ]
                }
            }
        },
    },
}

_STREAM_CHAT_ERROR_RESPONSES = {
    **_CHAT_COMMON_ERROR_RESPONSES,
    500: {
        "model": Result[None],
        "description": "SSE 响应建立前 Transaction A 初始化失败",
        "content": {
            "application/json": {
                "example": {
                    "code": 0,
                    "msg": "CHAT_START_FAILED",
                    "data": None,
                }
            }
        },
    },
}


class _ClosingStreamingResponse(StreamingResponse):
    """无论迭代、socket send 或断开监听在哪一步退出，都确定性关闭流。"""

    def __init__(self, content, *args, event_gen=None, on_close=None, **kwargs) -> None:
        super().__init__(content, *args, **kwargs)
        self._event_gen = event_gen
        self._on_close = on_close

    async def stream_response(self, send) -> None:
        try:
            await super().stream_response(send)
        finally:
            # 旧 ASGI 规范下 Starlette 会在取消域中终止发送任务；shield 保证
            # cleanup 仍能执行完，从而取消模型并释放 per-cid guard。
            try:
                with anyio.CancelScope(shield=True):
                    try:
                        close_body = getattr(self.body_iterator, "aclose", None)
                        if close_body is not None:
                            await close_body()
                    finally:
                        # async generator 若尚未开始迭代，aclose() 不会进入函数体，
                        # 因而外层 formatter 的 finally 也不会运行。响应直接持有并
                        # 关闭内层 generator，覆盖 response-start send 失败的边界。
                        close_events = getattr(self._event_gen, "aclose", None)
                        if close_events is not None:
                            await close_events()
            finally:
                if self._on_close is not None:
                    self._on_close()


def _error(status: int, msg: str) -> JSONResponse:
    return JSONResponse(status_code=status, content=Result.error(msg).model_dump())


async def _format_sse(event_gen):
    """Typed ChatEvent -> SSE 帧：id/event/data 单行 JSON。"""
    try:
        async for ev in event_gen:
            name = _EVENT_NAME.get(type(ev), "unknown")
            yield f"id: {ev.sequence}\nevent: {name}\ndata: {ev.model_dump_json()}\n\n"
    finally:
        # StreamingResponse 在客户端断开时会关闭外层 body iterator。显式关闭
        # TurnCoordinator generator，才能继续向内取消模型流并立即释放 turn guard。
        close_event_gen = getattr(event_gen, "aclose", None)
        if close_event_gen is not None:
            await close_event_gen()


@router.post(
    "/send",
    response_model=Result[ChatResponseVO],
    responses=_SYNC_CHAT_ERROR_RESPONSES,
)
async def send(req: ChatRequest, coordinator: TurnCoordinator = Depends(get_turn_coordinator), user: User | None = Depends(get_current_user)):
    """同步对话：drain TurnCoordinator -> ChatResponseVO。

    user 经 DI 解析为 User（HTTP）；直连调用时为 Depends 实例或 None，跳过归属校验。
    """
    uid = user.id if isinstance(user, User) else None
    try:
        prepared = await coordinator.prepare_turn(req.conversation_id, req.message, user_id=uid)
    except ChatConversationNotFound:
        return _error(404, "CHAT_CONVERSATION_NOT_FOUND")
    except ChatTurnInProgress:
        return _error(409, "CHAT_TURN_IN_PROGRESS")
    except ChatTurnStartFailed:
        return _error(500, "CHAT_START_FAILED")
    try:
        result = await coordinator.run_sync(prepared, req.message)
    except ChatTurnFailed as e:
        return _error(500, e.event.error.code)
    return Result.ok(ChatResponseVO(
        conversation_id=result.conversation_id,
        reply=result.reply,
        warnings=result.warnings,
    ))


@router.post(
    "/send/stream",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "版本化 typed SSE Chat 事件流",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        },
        **_STREAM_CHAT_ERROR_RESPONSES,
    },
)
async def send_stream(req: ChatRequest, coordinator: TurnCoordinator = Depends(get_turn_coordinator), user: User | None = Depends(get_current_user)):
    """流式对话：typed SSE。user 经 DI 解析；直连调用时跳过归属校验。"""
    uid = user.id if isinstance(user, User) else None
    try:
        prepared = await coordinator.prepare_turn(req.conversation_id, req.message, user_id=uid)
    except ChatConversationNotFound:
        return _error(404, "CHAT_CONVERSATION_NOT_FOUND")
    except ChatTurnInProgress:
        return _error(409, "CHAT_TURN_IN_PROGRESS")
    except ChatTurnStartFailed:
        return _error(500, "CHAT_START_FAILED")
    try:
        event_gen = coordinator.run(prepared, req.message)
        return _ClosingStreamingResponse(
            _format_sse(event_gen),
            event_gen=event_gen,
            on_close=lambda: coordinator.release_turn(prepared.conversation_id),
            media_type="text/event-stream",
        )
    except BaseException:
        coordinator.release_turn(prepared.conversation_id)
        raise


@router.get("/conversations", response_model=Result[list[ConversationItem]])
async def list_conversations(svc: ChatService = Depends(get_chat_service), user: User = Depends(get_current_user)):
    convs = await svc.list_conversations(user_id=user.id)
    return Result.ok(
        [
            {"id": c.id, "conversation_id": c.conversation_id, "title": c.title, "summary": c.summary}
            for c in convs
        ]
    )


@router.get(
    "/conversations/{conversation_id}",
    response_model=Result[list[ChatMessageVO]],
)
async def get_conversation(conversation_id: str, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """会话消息历史（PG 真相，按时间正序）。归属不匹配返回 404（不泄露存在性）。"""
    from sqlalchemy import select

    exists = await db.scalar(
        select(Conversation.id).where(
            Conversation.conversation_id == conversation_id,
            # 归属校验：user_id 为 null 的会话（直连测试/遗留）对所有用户可见
            (Conversation.user_id == user.id) | (Conversation.user_id.is_(None)),
        )
    )
    if exists is None:
        return _error(404, "CHAT_CONVERSATION_NOT_FOUND")
    r = await db.execute(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id.asc())
    )
    msgs = list(r.scalars().all())
    return Result.ok([{"role": m.role, "content": m.content} for m in msgs])


@router.delete(
    "/conversations/{conversation_id}",
    response_model=Result[None],
)
async def delete_conversation(conversation_id: str, svc: ChatService = Depends(get_chat_service), user: User = Depends(get_current_user)):
    await svc.delete_conversation(conversation_id, user_id=user.id)
    return Result.ok()
