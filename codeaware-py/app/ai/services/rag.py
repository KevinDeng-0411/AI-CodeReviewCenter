"""RagService - RAG 检索增强生成（ADR-0001/0002）。

上传知识文档 -> SemanticChunker 分块 -> VectorRecallService 内联向量化 -> 父子表存储；
检索 -> QueryRewriter 多查询改写 -> HybridRetriever 混合检索 -> 去重 -> 知识注入。
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.infra.vector_recall import VectorRecallService
from app.ai.rag.hybrid_retriever import HybridRetriever, ScoredChunk
from app.ai.rag.query_rewriter import QueryRewriter
from app.ai.rag.semantic_chunker import SemanticChunker
from app.models import Document, KnowledgeChunk


class RagService:
    def __init__(
        self,
        session: AsyncSession,
        chunker: SemanticChunker,
        vector_recall: VectorRecallService,
        query_rewriter: QueryRewriter,
        hybrid_retriever: HybridRetriever,
    ) -> None:
        self.session = session
        self.chunker = chunker
        self.vector_recall = vector_recall
        self.query_rewriter = query_rewriter
        self.hybrid_retriever = hybrid_retriever

    async def upload_document(
        self,
        title: str,
        content: str,
        source_type: str = "MANUAL",
        project_name: str | None = None,
        content_type: str = "md",
    ) -> Document:
        """上传知识文档：父表存全文一次 + 子表分块内联向量化（ADR-0002）。"""
        doc = Document(title=title, source_type=source_type, project_name=project_name, content=content)
        self.session.add(doc)
        await self.session.flush()
        chunks = self.chunker.chunk(content, content_type=content_type)
        for i, chunk_text in enumerate(chunks):
            kc = KnowledgeChunk(document_id=doc.id, chunk_index=i, chunk_content=chunk_text)
            await self.vector_recall.store(self.session, kc, chunk_text)  # embed + 内联
        return doc

    async def search(self, query: str, top_k: int = 5) -> list[ScoredChunk]:
        """多查询改写 -> 混合检索 -> 去重 -> Top-K。"""
        queries = await self.query_rewriter.rewrite(query)
        seen: set[int] = set()
        all_results: list[ScoredChunk] = []
        for q in queries:
            results = await self.hybrid_retriever.search(q, top_k=top_k * 2)
            for r in results:
                if r.chunk.id not in seen:
                    seen.add(r.chunk.id)
                    all_results.append(r)
        all_results.sort(key=lambda x: x.score, reverse=True)
        return all_results[:top_k]

    def format_context(self, results: list[ScoredChunk]) -> str:
        if not results:
            return ""
        parts = ["## 相关知识库文档\n"]
        for i, r in enumerate(results):
            parts.append(f"### 文档{i + 1} (相关度:{r.score:.2f}, 来源:{r.match_type})\n{r.chunk.chunk_content}\n")
        return "\n".join(parts)

    async def delete_document(self, doc_id: int) -> None:
        doc = await self.session.get(Document, doc_id)
        if doc:
            await self.session.delete(doc)  # CASCADE 删 chunks（ADR-0002）
            await self.session.flush()
