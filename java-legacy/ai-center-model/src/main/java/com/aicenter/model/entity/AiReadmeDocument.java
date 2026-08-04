package com.aicenter.model.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.experimental.Accessors;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * AIReadMe 文档实体
 *
 * @author aicenter
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("ai_readme_documents")
public class AiReadmeDocument implements Serializable {

    private static final long serialVersionUID = 1L;

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    /** 项目名称 */
    private String projectName;

    /** 章节：ARCHITECTURE/CORE_FLOW/DEV_GUIDE/STRUCTURE/BUSINESS/EXPERIENCE */
    private String section;

    /** 章节内容 */
    private String content;

    /** 版本号 */
    private Integer version;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;
}
