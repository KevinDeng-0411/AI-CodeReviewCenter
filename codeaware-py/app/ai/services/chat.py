"""ChatService - 会话查询/删除（C1-A：Turn 编排移至 TurnCoordinator）。

PG 真相源：list/get 走 PG；delete 清 PG + Redis 缓存。
"""

import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Message

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self, session: AsyncSession, redis_client=None) -> None:
        self.session = session
        self.redis = redis_client

    async def conversation_exists(self, cid: str) -> bool:
        r = await self.session.scalar(
            select(Conversation.id).where(Conversation.conversation_id == cid)
        )
        return r is not None

    async def list_conversations(self) -> list[Conversation]:
        r = await self.session.execute(select(Conversation).order_by(Conversation.id.desc()))
        return list(r.scalars().all())

    async def get_messages(self, cid: str) -> list[Message]:
        r = await self.session.execute(
            select(Message).where(Message.conversation_id == cid).order_by(Message.id.asc())
        )
        return list(r.scalars().all())

    async def delete_conversation(self, cid: str) -> None:
        await self.session.execute(delete(Message).where(Message.conversation_id == cid))
        await self.session.execute(delete(Conversation).where(Conversation.conversation_id == cid))
        await self.session.commit()
        if self.redis:
            try:
                await self.redis.delete(f"msgs:{cid}", f"summary:{cid}")
            except Exception:
                # PG 删除已经提交；缓存清理只能降级，且日志不得包含连接信息或异常正文。
                logger.warning(
                    "conversation cache invalidation failed "
                    "code=conversation_cache_delete_failed conversation_id=%s",
                    cid,
                )
