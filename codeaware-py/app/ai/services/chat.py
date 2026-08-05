"""ChatService - 会话查询/删除（C1-A：Turn 编排移至 TurnCoordinator）。

PG 真相源：list/get 走 PG；delete 清 PG + Redis 缓存。
"""

import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, LongTermMemory, Message
from app.core.exceptions import BusinessException

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self, session: AsyncSession, redis_client=None) -> None:
        self.session = session
        self.redis = redis_client

    async def conversation_exists(self, cid: str, user_id: int | None = None) -> bool:
        """存在性 + 归属校验。user_id=None 时只校验存在性（直连服务测试）。"""
        stmt = select(Conversation.id).where(Conversation.conversation_id == cid)
        if user_id is not None:
            # 归属校验：user_id 为 null 的会话（直连测试/遗留）对所有用户可见
            stmt = stmt.where(
                (Conversation.user_id == user_id) | (Conversation.user_id.is_(None))
            )
        r = await self.session.scalar(stmt)
        return r is not None

    async def list_conversations(self, user_id: int | None = None) -> list[Conversation]:
        """列出会话。user_id=None 时返回全部（直连服务测试）；否则按归属过滤。"""
        stmt = select(Conversation)
        if user_id is not None:
            stmt = stmt.where(Conversation.user_id == user_id)
        stmt = stmt.order_by(Conversation.id.desc())
        r = await self.session.execute(stmt)
        return list(r.scalars().all())

    async def get_messages(self, cid: str) -> list[Message]:
        r = await self.session.execute(
            select(Message).where(Message.conversation_id == cid).order_by(Message.id.asc())
        )
        return list(r.scalars().all())

    async def delete_conversation(self, cid: str, user_id: int | None = None) -> None:
        stmt = select(Conversation.id).where(Conversation.conversation_id == cid)
        if user_id is not None:
            stmt = stmt.where(
                (Conversation.user_id == user_id) | (Conversation.user_id.is_(None))
            )
        exists = await self.session.scalar(stmt)
        if exists is None:
            raise BusinessException(
                "CHAT_CONVERSATION_NOT_FOUND",
                status_code=404,
            )
        await self.session.execute(delete(Message).where(Message.conversation_id == cid))
        await self.session.execute(
            delete(LongTermMemory).where(LongTermMemory.conversation_id == cid)
        )
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
