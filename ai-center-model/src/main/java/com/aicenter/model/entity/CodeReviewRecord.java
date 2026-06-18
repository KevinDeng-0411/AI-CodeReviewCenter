package com.aicenter.model.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.EqualsAndHashCode;
import lombok.experimental.Accessors;

import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * AI Code Review 记录实体
 *
 * @author aicenter
 */
@Data
@EqualsAndHashCode(callSuper = false)
@Accessors(chain = true)
@TableName("code_review_records")
public class CodeReviewRecord implements Serializable {

    private static final long serialVersionUID = 1L;

    @TableId(value = "id", type = IdType.AUTO)
    private Long id;

    /** 项目名称 */
    private String projectName;

    /** 评审文件路径 */
    private String filePath;

    /** 原始代码 */
    private String sourceCode;

    /** 结构化评审结果 JSON */
    private String reviewResult;

    /** 问题总数 */
    private Integer issuesCount;

    /** Critical 问题数 */
    private Integer criticalCount;

    /** Warning 问题数 */
    private Integer warningCount;

    /** Info 问题数 */
    private Integer infoCount;

    /** 使用的 Prompt 模板 ID */
    private Long promptTemplateId;

    /** 使用的 AI 模型 */
    private String aiModel;

    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;
}
