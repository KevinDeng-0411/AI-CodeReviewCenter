package com.aicenter.ai.service;

import com.aicenter.ai.memory.LongTermMemoryManager;
import com.aicenter.ai.memory.ShortTermMemoryManager;
import com.aicenter.ai.rag.HybridRetriever;
import com.aicenter.model.entity.ChatConversation;
import com.aicenter.model.mapper.ChatConversationMapper;
import com.aicenter.model.mapper.ChatMessageMapper;
import com.aicenter.model.vo.ChatResponseVO;
import com.aicenter.model.vo.LongTermMemoryVO;
import dev.langchain4j.data.message.AiMessage;
import dev.langchain4j.model.StreamingResponseHandler;
import dev.langchain4j.model.chat.ChatLanguageModel;
import dev.langchain4j.model.chat.StreamingChatLanguageModel;
import dev.langchain4j.model.output.Response;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.UUID;
import java.util.function.Consumer;
import java.util.stream.Collectors;

/**
 * 智能问答服务 — 支持同步 + SSE 流式
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class ChatService {

    private final ChatLanguageModel chatModel;
    private final StreamingChatLanguageModel streamingChatModel;
    private final ShortTermMemoryManager shortTermMemory;
    private final LongTermMemoryManager longTermMemory;
    private final RagService ragService;
    private final ChatConversationMapper conversationMapper;
    private final ChatMessageMapper messageMapper;

    // ======================== 同步模式 ========================

    public ChatResponseVO chat(String sessionId, String message) {
        String sid = ensureSession(sessionId, message);
        shortTermMemory.saveMessage(sid, "USER", message);
        String systemPrompt = buildContextPrompt(sid, message);
        String reply = chatModel.generate(systemPrompt);
        shortTermMemory.saveMessage(sid, "ASSISTANT", reply);
        ChatResponseVO vo = new ChatResponseVO();
        vo.setSessionId(sid);
        vo.setReply(reply);
        return vo;
    }

    // ======================== SSE 流式模式 ========================

    public void chatStream(String sessionId, String message,
                           Consumer<String> onToken,
                           Consumer<ChatStreamResult> onComplete,
                           Consumer<Throwable> onError) {
        String sid = ensureSession(sessionId, message);
        shortTermMemory.saveMessage(sid, "USER", message);
        String systemPrompt = buildContextPrompt(sid, message);
        StringBuilder fullReply = new StringBuilder();

        streamingChatModel.generate(systemPrompt, new StreamingResponseHandler<AiMessage>() {
            @Override public void onNext(String token) {
                fullReply.append(token);
                onToken.accept(token);
            }
            @Override public void onComplete(Response<AiMessage> r) {
                String reply = fullReply.toString();
                shortTermMemory.saveMessage(sid, "ASSISTANT", reply);
                onComplete.accept(new ChatStreamResult(sid, reply));
            }
            @Override public void onError(Throwable e) {
                log.error("流式异常 sessionId={}", sid, e);
                onError.accept(e);
            }
        });
    }

    // ======================== 上下文构建 ========================

    private String ensureSession(String sessionId, String message) {
        if (sessionId == null || sessionId.isEmpty()) {
            String sid = UUID.randomUUID().toString().replace("-", "");
            conversationMapper.insert(new ChatConversation()
                    .setSessionId(sid)
                    .setTitle(message.length() > 30 ? message.substring(0, 30) + "..." : message));
            return sid;
        }
        return sessionId;
    }

    private String buildContextPrompt(String sessionId, String message) {
        String longTermContext = "";
        try {
            var recalled = longTermMemory.recall(message, 0.6, 5);
            longTermContext = recalled.isEmpty() ? "" : recalled.stream()
                    .map(m -> "- " + m.getContent() + " (相似度: " + m.getSimilarity() + ")")
                    .collect(Collectors.joining("\n"));
        } catch (Exception e) { log.warn("长期记忆召回失败: {}", e.getMessage()); }

        String ragContext = "";
        try {
            var docs = ragService.search(message, 5);
            ragContext = docs.isEmpty() ? "" : ragService.formatContext(docs);
        } catch (Exception e) { log.warn("RAG 检索失败: {}", e.getMessage()); }

        String shortTermContext = shortTermMemory.getContextWindow(sessionId);

        StringBuilder sb = new StringBuilder();
        sb.append("你是一个知识渊博的技术助手，服务于一个 Java 开发团队。\n\n");
        if (!longTermContext.isEmpty()) sb.append("## 长期记忆\n").append(longTermContext).append("\n\n");
        if (!ragContext.isEmpty()) sb.append(ragContext);
        sb.append("## 对话历史\n");
        sb.append(!shortTermContext.isEmpty() ? shortTermContext : "（新对话）\n");
        sb.append("\n请基于以上上下文回答。超出范围的请基于你的专业知识回答。");
        return sb.toString();
    }

    // ======================== 会话管理 ========================

    public List<ChatConversation> listConversations() {
        return conversationMapper.selectList(
                new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<ChatConversation>()
                        .orderByDesc(ChatConversation::getCreatedAt));
    }

    public List<ShortTermMemoryManager.MessageEntry> getConversationMessages(String sessionId) {
        return shortTermMemory.getMessages(sessionId);
    }

    public void deleteConversation(String sessionId) {
        shortTermMemory.clearMemory(sessionId);
        conversationMapper.delete(new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<ChatConversation>()
                .eq(ChatConversation::getSessionId, sessionId));
        messageMapper.delete(new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<com.aicenter.model.entity.ChatMessage>()
                .eq(com.aicenter.model.entity.ChatMessage::getSessionId, sessionId));
    }

    public record ChatStreamResult(String sessionId, String fullReply) {}
}
