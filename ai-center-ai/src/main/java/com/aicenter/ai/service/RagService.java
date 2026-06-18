package com.aicenter.ai.service;

import com.aicenter.ai.rag.HybridRetriever;
import com.aicenter.ai.rag.QueryRewriter;
import com.aicenter.ai.rag.SemanticChunker;
import com.aicenter.model.entity.KnowledgeDocument;
import com.aicenter.model.mapper.KnowledgeDocumentMapper;
import dev.langchain4j.data.embedding.Embedding;
import dev.langchain4j.data.segment.TextSegment;
import dev.langchain4j.model.embedding.EmbeddingModel;
import dev.langchain4j.store.embedding.EmbeddingStore;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.*;

/**
 * RAG 检索增强生成服务
 * <p>
 * 「查询重写 → 语义分块 → 混合检索(BM25+Pinecone) → 知识注入」
 *
 * @author aicenter
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class RagService {

    private final QueryRewriter queryRewriter;
    private final SemanticChunker semanticChunker;
    private final HybridRetriever hybridRetriever;
    private final KnowledgeDocumentMapper documentMapper;
    private final EmbeddingModel embeddingModel;
    private final EmbeddingStore<TextSegment> embeddingStore;

    /**
     * 上传知识文档（自动分块 + 向量化 → Pinecone）
     */
    public int uploadDocument(String title, String content, String sourceType, String projectName) {
        List<String> chunks = semanticChunker.chunk(content);
        log.info("文档分块完成: title={}, chunks={}", title, chunks.size());

        int count = 0;
        for (int i = 0; i < chunks.size(); i++) {
            // 先插入 MySQL 获取自增 ID
            KnowledgeDocument doc = new KnowledgeDocument()
                    .setTitle(title)
                    .setContent(content)
                    .setChunkIndex(i)
                    .setChunkContent(chunks.get(i))
                    .setSourceType(sourceType)
                    .setProjectName(projectName);
            documentMapper.insert(doc);

            // 向量化并存入 Pinecone
            // 向量化存入 Pinecone，内容从 MySQL 查找
            Embedding embedding = embeddingModel.embed(chunks.get(i)).content();
            embeddingStore.add("doc:" + doc.getId(), embedding);
            count++;
        }

        log.info("知识文档上传完成(Pinecone): title={}, chunks={}", title, count);
        return count;
    }

    /**
     * RAG 检索：查询重写 + 混合检索 (BM25 + Pinecone)
     */
    public List<HybridRetriever.ScoredDocument> search(String query, int topK) {
        List<String> queries = queryRewriter.rewrite(query);

        List<HybridRetriever.ScoredDocument> allResults = new ArrayList<>();
        for (String q : queries) {
            allResults.addAll(hybridRetriever.search(q, topK * 2));
        }

        allResults.sort((a, b) -> Double.compare(b.fusionScore(), a.fusionScore()));
        List<HybridRetriever.ScoredDocument> deduplicated = new ArrayList<>();
        Set<Long> seen = new HashSet<>();
        for (HybridRetriever.ScoredDocument doc : allResults) {
            if (seen.add(doc.document().getId())) {
                deduplicated.add(doc);
            }
        }

        var topResults = deduplicated.stream().limit(topK).toList();
        log.info("RAG 检索完成: query={}, rewrites={}, results={}",
                query, queries.size(), topResults.size());
        return topResults;
    }

    /**
     * 将检索结果格式化为 LLM 可用的上下文
     */
    public String formatContext(List<HybridRetriever.ScoredDocument> documents) {
        StringBuilder sb = new StringBuilder();
        sb.append("## 相关知识库文档\n\n");
        for (int i = 0; i < documents.size(); i++) {
            var doc = documents.get(i);
            sb.append("### 文档 ").append(i + 1)
                    .append("：").append(doc.document().getTitle())
                    .append(" (相关度: ").append(String.format("%.2f", doc.fusionScore()))
                    .append(")\n");
            sb.append(doc.document().getChunkContent()).append("\n\n");
        }
        return sb.toString();
    }

    /**
     * 删除知识文档
     */
    public void deleteDocument(Long id) {
        documentMapper.deleteById(id);
        embeddingStore.remove("doc:" + id);
    }
}
