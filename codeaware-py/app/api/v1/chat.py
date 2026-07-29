"""Chat API - /api/chat（核心域，SSE 流式 + conversation_id）。"""

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.api.v1.deps import get_chat_service
from app.core.response import Result
from app.schemas.chat import ChatRequest

router = APIRouter(prefix="/api/chat", tags=["Chat"])


@router.post("/send")
async def send(req: ChatRequest, svc=Depends(get_chat_service)):
    vo = await svc.chat(req.conversation_id, req.message)
    return Result.ok(vo)


@router.post("/send/stream")
async def send_stream(req: ChatRequest, svc=Depends(get_chat_service)):
    gen = await svc.chat_stream(req.conversation_id, req.message)
    return StreamingResponse(gen, media_type="text/event-stream")


@router.get("/conversations")
async def list_conversations(svc=Depends(get_chat_service)):
    convs = await svc.list_conversations()
    return Result.ok(
        [
            {"id": c.id, "conversation_id": c.conversation_id, "title": c.title, "summary": c.summary}
            for c in convs
        ]
    )


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, svc=Depends(get_chat_service)):
    msgs = await svc.get_messages(conversation_id)
    return Result.ok([{"role": m.role, "content": m.content} for m in msgs])


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, svc=Depends(get_chat_service)):
    await svc.delete_conversation(conversation_id)
    return Result.ok()
