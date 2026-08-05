"""SQLAlchemy ORM 模型 - 9 表，严格遵循 ADR-0001~0007 + 团队化升级阶段 A。

表组成（与 Java 不同：合并 CR/UT 记录、拆分 Knowledge 父子、内联向量、conversation_id）：
  users / prompt_templates / ai_operation_records / conversations / messages /
  long_term_memories / documents / knowledge_chunks / ai_readme_documents
"""

from app.models.ai_operation_record import AiOperationRecord
from app.models.ai_readme_document import AiReadmeDocument
from app.models.conversation import Conversation
from app.models.document import Document
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.long_term_memory import LongTermMemory
from app.models.message import Message
from app.models.prompt_template import PromptTemplate
from app.models.user import User

__all__ = [
    "User",
    "PromptTemplate",
    "AiOperationRecord",
    "Conversation",
    "Message",
    "LongTermMemory",
    "Document",
    "KnowledgeChunk",
    "AiReadmeDocument",
]
