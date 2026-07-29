"""P3-4：ChatService - 三级上下文 + CHAT 模板 + 多轮（ADR-0004/0005）。mock LLM。"""

import pytest

from app.ai.prompt.template_manager import PromptTemplateManager
from app.core.enums import PromptType


@pytest.fixture
async def chat_template(db_session):
    pm = PromptTemplateManager(db_session)
    return await pm.save_and_activate(
        PromptType.CHAT,
        name="v1",
        role_setting="你是技术助手",
        template_body=(
            "## 长期记忆\n{{long_term_memory}}\n\n"
            "{{rag_context}}\n\n"
            "## 对话历史\n{{conversation_history}}\n\n"
            "## 用户问题\n{{user_message}}"
        ),
    )


async def test_chat_creates_conversation_and_replies(chat_service, db_session, chat_template):
    vo = await chat_service.chat(None, "什么是缓存穿透")
    assert vo.conversation_id  # 自动创建
    assert vo.reply == "pong"  # FakeLLM
    msgs = await chat_service.get_messages(vo.conversation_id)
    assert len(msgs) == 2  # USER + ASSISTANT


async def test_chat_multi_turn(chat_service, db_session, chat_template):
    vo1 = await chat_service.chat(None, "问题一")
    vo2 = await chat_service.chat(vo1.conversation_id, "问题二")
    assert vo2.conversation_id == vo1.conversation_id
    msgs = await chat_service.get_messages(vo1.conversation_id)
    assert len(msgs) == 4  # 2 轮 × 2


async def test_chat_with_rag_context(chat_service, db_session, chat_template, rag_service):
    """上传知识后 chat，RAG 检索注入上下文（FakeLLM 仍返回 pong）。"""
    await rag_service.upload_document(
        "缓存", "# 缓存\n## 穿透\n布隆过滤器缓存空值方案", "MANUAL", "p"
    )
    vo = await chat_service.chat(None, "布隆过滤器缓存空值")
    assert vo.reply == "pong"
    assert vo.conversation_id


async def test_chat_delete_conversation(chat_service, db_session, chat_template):
    vo = await chat_service.chat(None, "测试删除")
    cid = vo.conversation_id
    await chat_service.delete_conversation(cid)
    msgs = await chat_service.get_messages(cid)
    # PG messages 被 delete；Redis 被 clear；get_messages fallback PG 返回空
    assert len(msgs) == 0 or all(m.content != "测试删除" for m in msgs)
