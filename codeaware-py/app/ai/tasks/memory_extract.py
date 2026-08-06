"""Post-turn 记忆抽取异步任务。"""
import logging
import asyncio
from app.ai.celery_app import celery_app
from app.ai.infra.vector_recall import VectorRecallService
from app.ai.tasks.base import CodeAwareTask
from app.db.session import AsyncSessionLocal
from app.models import Message

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, base=CodeAwareTask, name="memory.extract", max_retries=2)
def extract_memory_task(self, conversation_id: str, message_count: int) -> dict:
    async def _run():
        from app.ai.config import get_embedding_model, get_chat_model
        from app.ai.memory.long_term import LongTermMemoryManager

        vector_recall = VectorRecallService(get_embedding_model())
        chat_model = get_chat_model()

        async with AsyncSessionLocal() as session:
            lt = LongTermMemoryManager(session, vector_recall)
            has_mem = await lt.has_memories(conversation_id)
            if has_mem:
                return {"conversation_id": conversation_id, "facts_count": 0,
                        "reason": "already_has_memories"}

            messages = await lt.read_recent_messages(conversation_id)
            if len(messages) < message_count:
                return {"conversation_id": conversation_id, "facts_count": 0,
                        "reason": f"insufficient_messages ({len(messages)} < {message_count})"}

            tuples = [(m[0], m[1]) for m in messages]
            facts = await lt.extract_facts_text(tuples, chat_model)
            if not facts:
                return {"conversation_id": conversation_id, "facts_count": 0,
                        "reason": "no_facts_extracted"}

            prepared = await lt.prepare_facts(facts)

        async with AsyncSessionLocal() as s2:
            lt2 = LongTermMemoryManager(s2, vector_recall)
            await lt2.save_prepared_facts(conversation_id, prepared)
            await s2.commit()

        return {"conversation_id": conversation_id, "facts_count": len(prepared)}

    return asyncio.run(_run())