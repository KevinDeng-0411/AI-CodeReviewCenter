package com.aicenter.ai.config;

import dev.langchain4j.data.segment.TextSegment;
import dev.langchain4j.model.embedding.EmbeddingModel;
import dev.langchain4j.model.ollama.OllamaEmbeddingModel;
import dev.langchain4j.model.openai.OpenAiChatModel;
import dev.langchain4j.model.openai.OpenAiStreamingChatModel;
import dev.langchain4j.store.embedding.EmbeddingStore;
import dev.langchain4j.store.embedding.pgvector.PgVectorEmbeddingStore;
import dev.langchain4j.store.embedding.pinecone.PineconeEmbeddingStore;
import lombok.Data;
import lombok.extern.slf4j.Slf4j;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import javax.sql.DataSource;
import java.time.Duration;

/**
 * AI 核心配置 — LangChain4j Bean 定义
 * <p>
 * LLM: DeepSeek V4 Flash (OpenAI 兼容 API)
 * Embedding: Ollama bge-m3 (本地，1024 维)
 * 向量存储: PGVector (默认) / Pinecone (可选云托管)
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

    // ======================== Embedding Store (PGVector / Pinecone) ========================

    @Bean
    @ConfigurationProperties(prefix = "ai.pinecone")
    public PineconeProperties pineconeProperties() {
        return new PineconeProperties();
    }

    @Bean
    public EmbeddingStore<TextSegment> embeddingStore(
            DataSource dataSource, PineconeProperties pineProps) {
        // Pinecone API Key 已配置时优先使用
        if (pineProps.getApiKey() != null && !pineProps.getApiKey().isBlank()
                && !pineProps.getApiKey().contains("your-pinecone-api-key")) {
            log.info("使用 Pinecone 向量存储");
            try {
                return PineconeEmbeddingStore.builder()
                        .apiKey(pineProps.getApiKey())
                        .index(pineProps.getIndex())
                        .build();
            } catch (Exception e) {
                log.error("Pinecone 连接失败: {}", e.getMessage());
            }
        }
        // 默认使用 PGVector（本地 PostgreSQL + pgvector）
        log.info("使用 PGVector 向量存储");
        return PgVectorEmbeddingStore.datasourceBuilder()
                .datasource(dataSource)
                .table("ai_embeddings")
                .dimension(1024)
                .build();
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
}
