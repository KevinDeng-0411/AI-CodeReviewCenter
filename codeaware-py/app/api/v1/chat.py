"""Chat API - /api/chat（核心域，C1-A typed SSE + TurnCoordinator）。"""

import anyio
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.services.chat import ChatService
from app.ai.services.turn_coordinator import ChatTurnFailed, ChatTurnInProgress, TurnCoordinator
from app.api.v1.deps import get_chat_service, get_db, get_turn_coordinator
from app.core.response import Result
from app.models import Conversation, Message
from app.schemas.chat import ChatRequest, ChatResponseVO
from app.schemas.chat_events import EVENT_TYPES

router = APIRouter(prefix="/api/chat", tags=["Chat"])

# 事件类 -> SSE event 名
_EVENT_NAME = {cls: name for name, cls in EVENT_TYPES.items()}


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


@router.post("/send")
async def send(req: ChatRequest, coordinator: TurnCoordinator = Depends(get_turn_coordinator),
               svc: ChatService = Depends(get_chat_service)):
    """同步对话：drain TurnCoordinator -> ChatResponseVO。"""
    if req.conversation_id and not await svc.conversation_exists(req.conversation_id):
        return _error(404, "会话不存在")
    try:
        coordinator.acquire_turn(req.conversation_id)
    except ChatTurnInProgress:
        return _error(409, "CHAT_TURN_IN_PROGRESS")
    try:
        result = await coordinator.run_sync(req.conversation_id, req.message)
    except ChatTurnFailed as e:
        return _error(500, e.event.error.message)
    return Result.ok(ChatResponseVO(
        conversation_id=result.conversation_id,
        reply=result.reply,
        warnings=result.warnings,
    ))


@router.post("/send/stream")
async def send_stream(req: ChatRequest, coordinator: TurnCoordinator = Depends(get_turn_coordinator),
                      svc: ChatService = Depends(get_chat_service)):
    """流式对话：typed SSE。"""
    if req.conversation_id and not await svc.conversation_exists(req.conversation_id):
        return _error(404, "会话不存在")
    try:
        coordinator.acquire_turn(req.conversation_id)
    except ChatTurnInProgress:
        return _error(409, "CHAT_TURN_IN_PROGRESS")
    event_gen = coordinator.run(req.conversation_id, req.message)
    return _ClosingStreamingResponse(
        _format_sse(event_gen),
        event_gen=event_gen,
        on_close=lambda: coordinator.release_turn(req.conversation_id),
        media_type="text/event-stream",
    )


@router.get("/conversations")
async def list_conversations(svc: ChatService = Depends(get_chat_service)):
    convs = await svc.list_conversations()
    return Result.ok(
        [
            {"id": c.id, "conversation_id": c.conversation_id, "title": c.title, "summary": c.summary}
            for c in convs
        ]
    )


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, db: AsyncSession = Depends(get_db)):
    """会话消息历史（PG 真相，按时间正序）。"""
    from sqlalchemy import select

    r = await db.execute(
        select(Message).where(Message.conversation_id == conversation_id).order_by(Message.id.asc())
    )
    msgs = list(r.scalars().all())
    return Result.ok([{"role": m.role, "content": m.content} for m in msgs])


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, svc: ChatService = Depends(get_chat_service)):
    await svc.delete_conversation(conversation_id)
    return Result.ok()
