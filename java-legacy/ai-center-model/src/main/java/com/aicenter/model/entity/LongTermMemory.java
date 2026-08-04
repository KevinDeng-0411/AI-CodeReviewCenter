package com.aicenter.model.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.experimental.Accessors;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 长期记忆实体（向量存储）
 *
 * @author aicenter
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("long_term_memories")
public class LongTermMemory implements Serializable {

    private static final long serialVersionUID = 1L;

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    /** 来源会话 ID */
    private String sessionId;

    /** 记忆内容 */
    private String content;

    /** 记忆类型：FACT/PREFERENCE/KNOWLEDGE/EXPERIENCE */
    private String memoryType;

    /** bge-m3 1024 维向量（以逗号分隔的字符串存储，操作时转换） */
    private String embedding;

    /** 附加元数据 */
    private String metadata;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;
}
