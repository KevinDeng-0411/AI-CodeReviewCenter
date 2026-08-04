package com.aicenter.model.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.experimental.Accessors;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 会话实体
 *
 * @author aicenter
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("chat_conversations")
public class ChatConversation implements Serializable {

    private static final long serialVersionUID = 1L;

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    /** 会话标识 */
    private String sessionId;

    /** 会话标题 */
    private String title;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;
}
