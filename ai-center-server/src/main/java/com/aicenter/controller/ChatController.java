package com.aicenter.controller;

import com.aicenter.ai.service.ChatService;
import com.aicenter.common.result.Result;
import com.aicenter.model.dto.ChatRequest;
import com.aicenter.model.entity.ChatConversation;
import com.aicenter.model.vo.ChatResponseVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * 智能问答控制器
 *
 * @author aicenter
 */
@RestController
@RequestMapping("/api/chat")
@RequiredArgsConstructor
@Tag(name = "智能问答", description = "整合记忆与 RAG 的智能对话")
public class ChatController {

    private final ChatService chatService;

    @PostMapping("/send")
    @Operation(summary = "发送消息", description = "发送消息并获取 AI 回复（自动关联记忆与知识库）")
    public Result<ChatResponseVO> send(@RequestBody ChatRequest request) {
        ChatResponseVO result = chatService.chat(request.getSessionId(), request.getMessage());
        return Result.success(result);
    }

    @GetMapping("/conversations")
    @Operation(summary = "会话列表", description = "获取所有会话列表")
    public Result<List<ChatConversation>> listConversations() {
        return Result.success(chatService.listConversations());
    }

    @GetMapping("/conversations/{sessionId}")
    @Operation(summary = "会话消息历史", description = "获取指定会话的消息记录")
    public Result<List<?>> getMessages(@PathVariable String sessionId) {
        return Result.success(chatService.getConversationMessages(sessionId));
    }

    @DeleteMapping("/conversations/{sessionId}")
    @Operation(summary = "删除会话", description = "删除会话及其所有消息")
    public Result<Void> deleteConversation(@PathVariable String sessionId) {
        chatService.deleteConversation(sessionId);
        return Result.success();
    }
}
