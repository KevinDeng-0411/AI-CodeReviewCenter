package com.aicenter.controller;

import com.aicenter.ai.service.ChatService;
import com.aicenter.common.result.Result;
import com.aicenter.model.dto.ChatRequest;
import com.aicenter.model.entity.ChatConversation;
import com.aicenter.model.vo.ChatResponseVO;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.util.List;

/**
 * 智能问答控制器
 *
 * @author aicenter
 */
@Slf4j
@RestController
@RequestMapping("/api/chat")
@RequiredArgsConstructor
@Tag(name = "智能问答", description = "整合记忆与 RAG 的智能对话（同步 + SSE 流式）")
public class ChatController {

    private final ChatService chatService;

    @PostMapping("/send")
    @Operation(summary = "发送消息（同步）", description = "一次性返回完整 AI 回复")
    public Result<ChatResponseVO> send(@RequestBody ChatRequest request) {
        ChatResponseVO result = chatService.chat(request.getSessionId(), request.getMessage());
        return Result.success(result);
    }

    @PostMapping(value = "/send/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    @Operation(summary = "发送消息（SSE 流式）", description = "逐 token 推送 AI 回复，类似 ChatGPT 打字效果")
    public SseEmitter sendStream(@RequestBody ChatRequest request) {
        SseEmitter emitter = new SseEmitter(120000L); // 2 分钟超时

        chatService.chatStream(
                request.getSessionId(),
                request.getMessage(),
                token -> {
                    try { emitter.send(SseEmitter.event().data(token)); }
                    catch (Exception e) { emitter.completeWithError(e); }
                },
                result -> {
                    try { emitter.send(SseEmitter.event().name("done").data(result.sessionId())); }
                    catch (Exception e) { /* ignore */ }
                    emitter.complete();
                },
                error -> emitter.completeWithError(error)
        );

        return emitter;
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
