package com.aicenter.ai.config;

import dev.langchain4j.data.embedding.Embedding;
import dev.langchain4j.data.segment.TextSegment;
import dev.langchain4j.model.embedding.EmbeddingModel;
import dev.langchain4j.model.openai.OpenAiChatModel;
import dev.langchain4j.model.openai.OpenAiEmbeddingModel;
import dev.langchain4j.model.openai.OpenAiStreamingChatModel;
import dev.langchain4j.store.embedding.EmbeddingMatch;
import dev.langchain4j.store.embedding.EmbeddingSearchRequest;
import dev.langchain4j.store.embedding.EmbeddingSearchResult;
import dev.langchain4j.store.embedding.EmbeddingStore;
import dev.langchain4j.store.embedding.pinecone.PineconeEmbeddingStore;
import lombok.Data;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ConcurrentHashMap;

/**
 * AI 核心配置 — LangChain4j Bean 定义
 *
 * @author aicenter
 */
@Slf4j
@Configuration
public class AIConfig {

    // ======================== LLM Chat (DeepSeek) ========================

    @Bean
    @ConfigurationProperties(prefix = "ai.llm")
    public LlmProperties llmProperties() {
        return new LlmProperties();
    }

    @Bean
    public OpenAiChatModel chatModel(LlmProperties props) {
        return OpenAiChatModel.builder()
                .apiKey(props.getApiKey())
                .baseUrl(props.getBaseUrl())
                .modelName(props.getModel())
                .temperature(props.getTemperature())
                .maxTokens(props.getMaxTokens())
                .timeout(Duration.ofSeconds(120))
                .logRequests(true)
                .logResponses(true)
                .build();
    }

    @Bean
    public OpenAiStreamingChatModel streamingChatModel(LlmProperties props) {
        return OpenAiStreamingChatModel.builder()
                .apiKey(props.getApiKey())
                .baseUrl(props.getBaseUrl())
                .modelName(props.getModel())
                .temperature(props.getTemperature())
                .maxTokens(props.getMaxTokens())
                .timeout(Duration.ofSeconds(120))
                .build();
    }

    // ======================== Embedding Model ========================

    @Bean
    @ConfigurationProperties(prefix = "ai.embedding")
    public EmbeddingProperties embeddingProperties() {
        return new EmbeddingProperties();
    }

    @Bean
    public EmbeddingModel embeddingModel(EmbeddingProperties props) {
        // 即使 API Key 无效也创建 Bean，调用层有 try-catch 容错
        return OpenAiEmbeddingModel.builder()
                .apiKey(props.getApiKey())
                .baseUrl(props.getBaseUrl())
                .modelName(props.getModel())
                .dimensions(props.getDimensions())
                .timeout(Duration.ofSeconds(60))
                .logRequests(true)
                .logResponses(false)
                .build();
    }

    // ======================== Embedding Store ========================

    @Bean
    @ConfigurationProperties(prefix = "ai.pinecone")
    public PineconeProperties pineconeProperties() {
        return new PineconeProperties();
    }

    @Bean
    public EmbeddingStore<TextSegment> embeddingStore(PineconeProperties props) {
        if (props.getApiKey() == null || props.getApiKey().isBlank()
                || props.getApiKey().contains("your-pinecone-api-key")) {
            log.warn("Pinecone 未配置，使用内存向量存储（不持久化）");
            return new SimpleInMemoryEmbeddingStore();
        }
        try {
            return PineconeEmbeddingStore.builder()
                    .apiKey(props.getApiKey())
                    .index(props.getIndex())
                    .build();
        } catch (Exception e) {
            log.error("Pinecone 连接失败: {}，降级为内存存储", e.getMessage());
            return new SimpleInMemoryEmbeddingStore();
        }
    }

    // ======================== Properties ========================

    @Data
    public static class LlmProperties {
        private String apiKey;
        private String baseUrl = "https://api.deepseek.com/v1";
        private String model = "deepseek-chat";
        private Double temperature = 0.1;
        private Integer maxTokens = 4096;
    }

    @Data
    public static class EmbeddingProperties {
        private String apiKey;
        private String baseUrl = "https://api.openai.com/v1";
        private String model = "text-embedding-3-large";
        private Integer dimensions = 1024;
    }

    @Data
    public static class PineconeProperties {
        private String apiKey;
        private String index = "ai-center";
    }

    // ======================== Simple In-Memory Embedding Store ========================

    /**
     * 简易内存向量存储 — 用于 Pinecone 未配置时的降级
     */
    static class SimpleInMemoryEmbeddingStore implements EmbeddingStore<TextSegment> {

        private final ConcurrentHashMap<String, EmbeddingEntry> store = new ConcurrentHashMap<>();

        @Override
        public String add(Embedding embedding) {
            String id = java.util.UUID.randomUUID().toString();
            store.put(id, new EmbeddingEntry(id, embedding, null));
            return id;
        }

        @Override
        public void add(String id, Embedding embedding) {
            store.put(id, new EmbeddingEntry(id, embedding, null));
        }

        @Override
        public String add(Embedding embedding, TextSegment segment) {
            String id = java.util.UUID.randomUUID().toString();
            store.put(id, new EmbeddingEntry(id, embedding, segment));
            return id;
        }

        @Override
        public List<String> addAll(List<Embedding> embeddings) {
            List<String> ids = new ArrayList<>();
            for (Embedding e : embeddings) ids.add(add(e));
            return ids;
        }

        @Override
        public List<String> addAll(List<Embedding> embeddings, List<TextSegment> segments) {
            List<String> ids = new ArrayList<>();
            for (int i = 0; i < embeddings.size(); i++) {
                TextSegment seg = i < segments.size() ? segments.get(i) : null;
                ids.add(add(embeddings.get(i), seg));
            }
            return ids;
        }

        @Override
        public void removeAll() { store.clear(); }

        @Override
        public void remove(String id) { store.remove(id); }

        @Override
        public void removeAll(java.util.Collection<String> ids) { ids.forEach(store::remove); }

        @Override
        public EmbeddingSearchResult<TextSegment> search(EmbeddingSearchRequest request) {
            float[] queryVector = request.queryEmbedding().vector();
            double minScore = request.minScore();
            int maxResults = request.maxResults();

            List<EmbeddingMatch<TextSegment>> matches = new ArrayList<>();
            for (EmbeddingEntry entry : store.values()) {
                double score = cosineSimilarity(queryVector, entry.embedding.vector());
                if (score >= minScore) {
                    matches.add(new EmbeddingMatch<>(score, entry.id, entry.embedding, entry.segment));
                }
            }
            matches.sort(Comparator.comparingDouble((EmbeddingMatch<TextSegment> m) -> m.score()).reversed());
            int limit = Math.min(maxResults, matches.size());
            return new EmbeddingSearchResult<>(new ArrayList<>(matches.subList(0, limit)));
        }

        private double cosineSimilarity(float[] a, float[] b) {
            if (a.length != b.length) return 0;
            double dot = 0, normA = 0, normB = 0;
            for (int i = 0; i < a.length; i++) {
                dot += a[i] * b[i];
                normA += a[i] * a[i];
                normB += b[i] * b[i];
            }
            return (normA == 0 || normB == 0) ? 0 : dot / (Math.sqrt(normA) * Math.sqrt(normB));
        }

        record EmbeddingEntry(String id, Embedding embedding, TextSegment segment) {}
    }
}
