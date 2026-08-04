package com.aicenter.model.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.experimental.Accessors;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * Prompt 模板实体
 *
 * @author aicenter
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("prompt_templates")
public class PromptTemplate implements Serializable {

    private static final long serialVersionUID = 1L;

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    /** 模板名称 */
    private String name;

    /** 模板类型：CODE_REVIEW/UNIT_TEST/AI_README/CHAT */
    private String type;

    /** 角色设定 */
    private String roleSetting;

    /** 评审维度数组 */
    private String[] reviewDimensions;

    /** 问题等级：Critical/Warning/Info */
    private String[] severityLevels;

    /** 模板正文（含占位符 {{source_code}}） */
    private String templateBody;

    /** 版本号 */
    private Integer version;

    /** 是否启用 */
    private Boolean isActive;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;
}
