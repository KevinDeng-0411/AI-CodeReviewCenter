package com.aicenter.ai.service;

import com.aicenter.ai.memory.LongTermMemoryManager;
import com.aicenter.ai.memory.ShortTermMemoryManager;
import com.aicenter.ai.rag.HybridRetriever;
import com.aicenter.model.entity.ChatConversation;
import com.aicenter.model.mapper.ChatConversationMapper;
import com.aicenter.model.mapper.ChatMessageMapper;
import com.aicenter.model.vo.ChatResponseVO;
import com.aicenter.model.vo.LongTermMemoryVO;
import dev.langchain4j.model.chat.ChatLanguageModel;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.UUID;
import java.util.stream.Collectors;

/**
 * 智能问答服务
 * <p>
 * 整合短期记忆、长期记忆、RAG 检索，构成完整对话链路：
 * 用户消息 → [长期记忆召回] → [RAG检索] → [短期记忆上下文] → LLM → 回复
 *
 * @author aicenter
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class ChatService {

    private final ChatLanguageModel chatModel;
    private final ShortTermMemoryManager shortTermMemory;
    private final LongTermMemoryManager longTermMemory;
    private final RagService ragService;
    private final ChatConversationMapper conversationMapper;
    private final ChatMessageMapper messageMapper;

    /**
     * 发送消息（完整链路）
     */
    public ChatResponseVO chat(String sessionId, String message) {
        boolean isNewSession = (sessionId == null || sessionId.isEmpty());
        if (isNewSession) {
            sessionId = UUID.randomUUID().toString().replace("-", "");
            // 创建新会话
            ChatConversation conversation = new ChatConversation()
                    .setSessionId(sessionId)
                    .setTitle(message.length() > 30 ? message.substring(0, 30) + "..." : message);
            conversationMapper.insert(conversation);
        }

        // 1. 保存用户消息到短期记忆
        shortTermMemory.saveMessage(sessionId, "USER", message);

        // 2. 长期记忆召回（Ollama 未启动时降级跳过）
        String longTermContext = "";
        try {
            List<LongTermMemoryVO> recalledMemories = longTermMemory.recall(message, 0.6, 5);
            longTermContext = recalledMemories.isEmpty() ? "" :
                    recalledMemories.stream()
                            .map(m -> "- " + m.getContent() + " (相似度: " + m.getSimilarity() + ")")
                            .collect(Collectors.joining("\n"));
        } catch (Exception e) {
            log.warn("长期记忆召回失败（Ollama 可能未启动）: {}", e.getMessage());
        }

        // 3. RAG 检索（Ollama 未启动时降级跳过）
        String ragContext = "";
        try {
            List<HybridRetriever.ScoredDocument> docs = ragService.search(message, 5);
            ragContext = docs.isEmpty() ? "" : ragService.formatContext(docs);
        } catch (Exception e) {
            log.warn("RAG 检索失败（Ollama 可能未启动）: {}", e.getMessage());
        }

        // 4. 短期记忆上下文
        String shortTermContext = shortTermMemory.getContextWindow(sessionId);

        // 5. 构建完整 Prompt
        String systemPrompt = buildSystemPrompt(longTermContext, ragContext, shortTermContext);
        log.debug("Chat System Prompt 长度: {}", systemPrompt.length());

        // 6. 调用 LLM
        String reply = chatModel.generate(systemPrompt);

        // 7. 保存 AI 回复到短期记忆
        shortTermMemory.saveMessage(sessionId, "ASSISTANT", reply);

        // 8. 返回
        ChatResponseVO vo = new ChatResponseVO();
        vo.setSessionId(sessionId);
        vo.setReply(reply);
        vo.setMemorySummary(longTermContext.isEmpty() ? null :
                longTermContext.replace("- ", "").replace("\n", "; "));
        return vo;
    }

    /**
     * 构建 System Prompt（融合所有记忆和知识）
     */
    private String buildSystemPrompt(String longTermContext, String ragContext,
                                      String shortTermContext) {
        StringBuilder sb = new StringBuilder();
        sb.append("你是一个知识渊博的技术助手，服务于一个 Java 开发团队。\n\n");

        if (longTermContext != null && !longTermContext.isEmpty()) {
            sb.append("## 你的长期记忆（团队知识沉淀）\n")
                    .append(longTermContext).append("\n\n");
        }

        if (ragContext != null && !ragContext.isEmpty()) {
            sb.append(ragContext);
        }

        sb.append("## 对话历史\n");
        if (shortTermContext != null && !shortTermContext.isEmpty()) {
            sb.append(shortTermContext);
        } else {
            sb.append("（新对话）\n");
        }

        sb.append("\n请基于以上上下文回答用户的最新问题。如果问题超出上下文范围，请基于你的专业知识回答。");
        return sb.toString();
    }

    /**
     * 获取会话列表
     */
    public List<ChatConversation> listConversations() {
        return conversationMapper.selectList(
                new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<ChatConversation>()
                        .orderByDesc(ChatConversation::getCreatedAt)
        );
    }

    /**
     * 获取会话消息历史
     */
    public List<ShortTermMemoryManager.MessageEntry> getConversationMessages(String sessionId) {
        return shortTermMemory.getMessages(sessionId);
    }

    /**
     * 删除会话
     */
    public void deleteConversation(String sessionId) {
        shortTermMemory.clearMemory(sessionId);
        conversationMapper.delete(
                new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<ChatConversation>()
                        .eq(ChatConversation::getSessionId, sessionId)
        );
        messageMapper.delete(
                new com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper<com.aicenter.model.entity.ChatMessage>()
                        .eq(com.aicenter.model.entity.ChatMessage::getSessionId, sessionId)
        );
    }
}
