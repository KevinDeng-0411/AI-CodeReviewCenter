package com.aicenter.model.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.experimental.Accessors;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * 知识文档实体（向量存储）
 *
 * @author aicenter
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("knowledge_documents")
public class KnowledgeDocument implements Serializable {

    private static final long serialVersionUID = 1L;

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    /** 文档标题 */
    private String title;

    /** 原始内容 */
    private String content;

    /** 分块索引 */
    private Integer chunkIndex;

    /** 分块内容 */
    private String chunkContent;

    /** bge-m3 向量 */
    private String embedding;

    /** 来源类型：AI_README/MANUAL/CODE/DOC */
    private String sourceType;

    /** 所属项目 */
    private String projectName;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;
}
