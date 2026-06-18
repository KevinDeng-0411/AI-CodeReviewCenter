package com.aicenter.ai.config;

import dev.langchain4j.data.embedding.Embedding;
import dev.langchain4j.data.segment.TextSegment;
import dev.langchain4j.model.embedding.EmbeddingModel;
import dev.langchain4j.model.ollama.OllamaEmbeddingModel;
import dev.langchain4j.model.openai.OpenAiChatModel;
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
 * <p>
 * LLM: DeepSeek V4 Flash (OpenAI 兼容 API)
 * Embedding: Ollama bge-m3 (本地，1024 维)
 * 向量存储: Pinecone (云托管) / InMemory (降级)
 *
 * @author aicenter
 */
@Slf4j
@Configuration
public class AIConfig {

    // ======================== LLM Chat (DeepSeek V4) ========================

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

    // ======================== Embedding Model (Ollama bge-m3) ========================

    @Bean
    @ConfigurationProperties(prefix = "ai.ollama")
    public OllamaProperties ollamaProperties() {
        return new OllamaProperties();
    }

    @Bean
    public EmbeddingModel embeddingModel(OllamaProperties props) {
        return OllamaEmbeddingModel.builder()
                .baseUrl(props.getBaseUrl())
                .modelName(props.getEmbeddingModel())
                .timeout(Duration.ofSeconds(60))
                .build();
    }

    // ======================== Embedding Store (Pinecone / InMemory) ========================

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
        private String model = "deepseek-v4-flash";
        private Double temperature = 0.1;
        private Integer maxTokens = 4096;
    }

    @Data
    public static class OllamaProperties {
        private String baseUrl = "http://localhost:11434";
        private String embeddingModel = "bge-m3";
    }

    @Data
    public static class PineconeProperties {
        private String apiKey;
        private String index = "ai-center";
    }

    // ======================== In-Memory Embedding Store (Pinecone 降级) ========================

    static class SimpleInMemoryEmbeddingStore implements EmbeddingStore<TextSegment> {

        private final ConcurrentHashMap<String, EmbeddingEntry> store = new ConcurrentHashMap<>();

        @Override public String add(Embedding e) { String id = java.util.UUID.randomUUID().toString(); store.put(id, new EmbeddingEntry(id, e, null)); return id; }
        @Override public void add(String id, Embedding e) { store.put(id, new EmbeddingEntry(id, e, null)); }
        @Override public String add(Embedding e, TextSegment s) { String id = java.util.UUID.randomUUID().toString(); store.put(id, new EmbeddingEntry(id, e, s)); return id; }
        @Override public List<String> addAll(List<Embedding> es) { List<String> ids = new ArrayList<>(); for (Embedding e : es) ids.add(add(e)); return ids; }
        @Override public List<String> addAll(List<Embedding> es, List<TextSegment> ss) { List<String> ids = new ArrayList<>(); for (int i = 0; i < es.size(); i++) ids.add(add(es.get(i), i < ss.size() ? ss.get(i) : null)); return ids; }
        @Override public void removeAll() { store.clear(); }
        @Override public void remove(String id) { store.remove(id); }
        @Override public void removeAll(java.util.Collection<String> ids) { ids.forEach(store::remove); }

        @Override
        public EmbeddingSearchResult<TextSegment> search(EmbeddingSearchRequest req) {
            float[] qv = req.queryEmbedding().vector();
            double minS = req.minScore();
            int maxR = req.maxResults();
            List<EmbeddingMatch<TextSegment>> matches = new ArrayList<>();
            for (EmbeddingEntry e : store.values()) {
                double s = cosine(e.embedding.vector(), qv);
                if (s >= minS) matches.add(new EmbeddingMatch<>(s, e.id, e.embedding, e.segment));
            }
            matches.sort(Comparator.comparingDouble((EmbeddingMatch<TextSegment> m) -> m.score()).reversed());
            return new EmbeddingSearchResult<>(new ArrayList<>(matches.subList(0, Math.min(maxR, matches.size()))));
        }

        private double cosine(float[] a, float[] b) {
            double d = 0, nA = 0, nB = 0;
            for (int i = 0; i < a.length; i++) { d += a[i] * b[i]; nA += a[i] * a[i]; nB += b[i] * b[i]; }
            return (nA == 0 || nB == 0) ? 0 : d / (Math.sqrt(nA) * Math.sqrt(nB));
        }

        record EmbeddingEntry(String id, Embedding embedding, TextSegment segment) {}
    }
}
