"""Chat API - /api/chat（核心域，C1-A typed SSE + TurnCoordinator）。"""

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


def _error(status: int, msg: str) -> JSONResponse:
    return JSONResponse(status_code=status, content=Result.error(msg).model_dump())


async def _format_sse(event_gen):
    """Typed ChatEvent -> SSE 帧：id/event/data 单行 JSON。"""
    async for ev in event_gen:
        name = _EVENT_NAME.get(type(ev), "unknown")
        yield f"id: {ev.sequence}\nevent: {name}\ndata: {ev.model_dump_json()}\n\n"


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
    return StreamingResponse(_format_sse(coordinator.run(req.conversation_id, req.message)),
                             media_type="text/event-stream")


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
