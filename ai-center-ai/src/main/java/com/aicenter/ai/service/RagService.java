package com.aicenter.ai.service;

import com.aicenter.ai.rag.HybridRetriever;
import com.aicenter.ai.rag.QueryRewriter;
import com.aicenter.ai.rag.SemanticChunker;
import com.aicenter.model.entity.KnowledgeDocument;
import com.aicenter.model.mapper.KnowledgeDocumentMapper;
import dev.langchain4j.data.embedding.Embedding;
import dev.langchain4j.model.embedding.EmbeddingModel;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * RAG 检索增强生成服务
 * <p>
 * 「查询重写 → 语义分块 → 混合检索 → 知识注入」全流程编排
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

    /**
     * 上传知识文档（自动分块 + 向量化入库）
     */
    public int uploadDocument(String title, String content, String sourceType, String projectName) {
        // 1. 语义分块
        List<String> chunks = semanticChunker.chunk(content);
        log.info("文档分块完成: title={}, chunks={}", title, chunks.size());

        // 2. 逐块向量化并存储
        int count = 0;
        for (int i = 0; i < chunks.size(); i++) {
            // 向量化
            Embedding embedding = embeddingModel.embed(chunks.get(i)).content();
            String embeddingStr = Arrays.toString(embedding.vector());

            KnowledgeDocument doc = new KnowledgeDocument()
                    .setTitle(title)
                    .setContent(content)
                    .setChunkIndex(i)
                    .setChunkContent(chunks.get(i))
                    .setEmbedding(embeddingStr)
                    .setSourceType(sourceType)
                    .setProjectName(projectName);
            documentMapper.insert(doc);
            count++;
        }

        log.info("知识文档上传完成: title={}, chunks={}", title, count);
        return count;
    }

    /**
     * RAG 检索：查询重写 + 混合检索
     */
    public List<HybridRetriever.ScoredDocument> search(String query, int topK) {
        // 1. 查询重写
        List<String> queries = queryRewriter.rewrite(query);

        // 2. 对每个变体做混合检索，合并去重
        List<HybridRetriever.ScoredDocument> allResults = new ArrayList<>();
        for (String q : queries) {
            List<HybridRetriever.ScoredDocument> results = hybridRetriever.search(q, topK * 2);
            allResults.addAll(results);
        }

        // 3. 去重（按文档 ID），保留最高分
        allResults.sort((a, b) -> Double.compare(b.fusionScore(), a.fusionScore()));
        List<HybridRetriever.ScoredDocument> deduplicated = new ArrayList<>();
        java.util.Set<Long> seen = new java.util.HashSet<>();
        for (HybridRetriever.ScoredDocument doc : allResults) {
            if (seen.add(doc.document().getId())) {
                deduplicated.add(doc);
            }
        }

        List<HybridRetriever.ScoredDocument> topResults = deduplicated.stream()
                .limit(topK)
                .toList();

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
    }
}
