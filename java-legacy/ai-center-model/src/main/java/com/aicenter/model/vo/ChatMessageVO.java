package com.aicenter.model.vo;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * 聊天消息视图
 *
 * @author aicenter
 */
@Data
@NoArgsConstructor
@AllArgsConstructor
@Schema(description = "聊天消息")
public class ChatMessageVO {

    @Schema(description = "角色", example = "ASSISTANT")
    private String role;

    @Schema(description = "消息内容")
    private String content;
}
